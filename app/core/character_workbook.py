"""Versioned Character Studio workbook export/import using only the Python standard library."""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import posixpath, re, unicodedata, uuid, zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT = "http://schemas.openxmlformats.org/package/2006/content-types"
MAX_BYTES = 25 * 1024 * 1024
MAX_EXPANDED = 100 * 1024 * 1024
MAX_ROWS = 50000
MAX_CHARACTER_NAME_LENGTH = 160
MAX_CHARACTER_ALIAS_LENGTH = 160
MAX_IDENTITY_VARIANT_LENGTH = 120
MAX_CHARACTER_NOTES_LENGTH = 4000
ALIAS_COLUMNS = 30
CHUNK = 15000
ET.register_namespace("", MAIN)
ET.register_namespace("r", REL)

def _t(name): return "{%s}%s" % (MAIN, name)
def _clean(value): return unicodedata.normalize("NFC", str(value or "")).strip()
def _key(value): return _clean(value).casefold()

def _col_name(number):
    result = ""
    while number:
        number, rem = divmod(number - 1, 26)
        result = chr(65 + rem) + result
    return result

def _col_number(reference):
    match = re.match(r"([A-Z]+)", str(reference or "").upper())
    if not match: return 0
    value = 0
    for char in match.group(1): value = value * 26 + ord(char) - 64
    return value

def _cell(ref, value, style):
    if value is None or value == "": return ""
    if isinstance(value, bool):
        return '<c r="%s" s="%d" t="b"><v>%d</v></c>' % (ref, style, int(value))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return '<c r="%s" s="%d"><v>%s</v></c>' % (ref, style, value)
    raw = str(value)
    raw = "".join(char for char in raw if char in "\t\n\r" or ord(char) >= 32)
    return '<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (
        ref, style, escape(raw)
    )

def _sheet(rows, widths, wrap, protect=False):
    cols = "".join('<col min="%d" max="%d" width="%.2f" customWidth="1"/>' % (
        i + 1, i + 1, widths[i] if i < len(widths) else 20
    ) for i in range(max([len(row) for row in rows] or [1])))
    last_col = _col_name(max([len(row) for row in rows] or [1]))
    rendered = []
    for ri, row in enumerate(rows, 1):
        cells = "".join(_cell(_col_name(ci) + str(ri), value,
                              1 if ri == 1 else (2 if ci in wrap else 0))
                        for ci, value in enumerate(row, 1))
        height = ' ht="30" customHeight="1"' if ri == 1 else (
            ' ht="42" customHeight="1"' if any(isinstance(v, str) and len(v) > 90 for v in row) else ""
        )
        rendered.append('<row r="%d"%s>%s</row>' % (ri, height, cells))
    end_row = max(1, len(rows))
    filt = '<autoFilter ref="A1:%s%d"/>' % (last_col, end_row) if len(rows) > 1 else ""
    protection = '<sheetProtection sheet="1" objects="1" scenarios="1"/>' if protect else ""
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="%s"><dimension ref="A1:%s%d"/>'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews><sheetFormatPr defaultRowHeight="19"/><cols>%s</cols>'
        '<sheetData>%s</sheetData>%s%s</worksheet>') % (
            MAIN, last_col, end_row, cols, "".join(rendered), protection, filt
        )

def _styles():
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
      '<styleSheet xmlns="%s"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
      '<font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts>'
      '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
      '<fill><patternFill patternType="solid"><fgColor rgb="FF263449"/><bgColor indexed="64"/></patternFill></fill></fills>'
      '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
      '<border><left style="thin"><color rgb="FFD7DEE8"/></left><right style="thin"><color rgb="FFD7DEE8"/></right>'
      '<top style="thin"><color rgb="FFD7DEE8"/></top><bottom style="thin"><color rgb="FFD7DEE8"/></bottom><diagonal/></border></borders>'
      '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
      '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
      '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
      '<alignment vertical="center" horizontal="center" wrapText="1"/></xf>'
      '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1">'
      '<alignment vertical="top" wrapText="1"/></xf></cellXfs>'
      '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>') % MAIN

def create_character_workbook_bytes(metadata, passages, chapter_text):
    """Create a workbook for one chapter. Dialogue fill cells start blank; narration is Narrator."""
    info = {
        "Workbook Schema": "ryu.character-studio-workbook", "Workbook Version": 1,
        "Export ID": str(metadata.get("export_id") or uuid.uuid4().hex),
        "Passage Count": len(passages),
        "Book Title": _clean(metadata.get("project_title")), "Series Name": _clean(metadata.get("series_name")),
        "Chapter ID": _clean(metadata.get("chapter_id")), "Chapter Number": metadata.get("chapter_number", ""),
        "Chapter Title": _clean(metadata.get("chapter_title")), "Chapter Revision": _clean(metadata.get("chapter_revision")),
        "Exported At (UTC)": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "Instructions": ("Fill GPT Assigned Character for every Dialogue row when its speaker is supported by the source. "
            "Do not guess. If a dialogue speaker is uncertain, leave the cell blank; import preview will block the workbook "
            "until that passage is resolved manually or with a confirmed Character Register identity. "
            "Use GPT Confidence (0–1) as a numeric score from 0.0 to 1.0, and explain evidence in its notes. "
            "Narration is protected as Narrator. Add canonical full names and all other names as aliases. "
            "A younger/older version needing a different voice must be a separate Character Register row. "
            "Use Version / Age Variant and assign it by its distinct name, for example Mira (Younger Version). "
            "Use the read-only Series Character Reference table on the Workbook Info tab to reuse existing canonical names and known aliases. "
            "Do not edit that reference table; add genuinely new identities in Character Register. "
            "For more than 30 aliases, add columns named Alias 31, Alias 32, and so on. "
            "Do not edit Passage ID, Dialogue Text, chapter identity, offsets, or revision columns.")
    }
    dialogue_headers = [
        "Passage ID", "Chapter ID", "Chapter Number", "Chapter Title", "Passage Type", "Dialogue Text",
        "GPT Assigned Character", "GPT Confidence (0–1)", "Existing Assignment (Reference)", "Assignment Source (Reference)",
        "Confidence (Reference)", "Start (Reference)", "End (Reference)",
        "Chapter Revision (Reference)", "Evidence / Notes (GPT)"
    ]
    dialogue = [dialogue_headers]
    for row in passages:
        source_text = str(row.get("text") or "")
        if len(source_text.encode("utf-16-le")) // 2 > 32767:
            raise ValueError("A dialogue passage exceeds Excel's 32,767-character cell limit. Split the passage before exporting.")
        narration = str(row.get("kind") or "").casefold() == "narration"
        speakers = row.get("existing_speakers") or row.get("speakers") or []
        if isinstance(speakers, str): speakers = [speakers]
        dialogue.append([
            str(row.get("passage_id") or ""), str(row.get("chapter_id") or info["Chapter ID"]),
            int(row.get("chapter_number") or metadata.get("chapter_number") or 0),
            str(row.get("chapter_title") or info["Chapter Title"]),
            "Narration" if narration else "Dialogue", str(row.get("text") or ""),
            "Narrator" if narration else "", "",
            " + ".join(str(x) for x in speakers if str(x or "").strip()),
            str(row.get("assignment_source") or ""),
            row.get("confidence") if row.get("confidence") is not None else "",
            int(row.get("start") or 0), int(row.get("end") or 0),
            str(row.get("chapter_revision") or info["Chapter Revision"]), ""
        ])
    if len(dialogue) - 1 > MAX_ROWS:
        raise ValueError("This chapter exceeds the 50,000 passage workbook export limit.")
    char_headers = ["Full Name"] + ["Alias %d" % n for n in range(1, ALIAS_COLUMNS + 1)] + [
        "Version / Age Variant", "Character Notes"
    ]
    characters = [char_headers] + [[""] * len(char_headers) for _ in range(30)]
    context = [["Context Part", "Chapter Number", "Chapter Title", "Chapter Text"]]
    reference_rows = []
    if "series_character_reference" in metadata:
        for source in metadata.get("series_character_reference") or []:
            if not isinstance(source, dict):
                continue
            primary = _clean(source.get("primary_name") or source.get("name"))
            if not primary:
                continue
            aliases = source.get("aliases") or []
            if isinstance(aliases, str):
                aliases = [aliases]
            cleaned_aliases = []
            seen_aliases = {_key(primary)}
            for raw_alias in aliases:
                alias = _clean(raw_alias)
                if alias and _key(alias) not in seen_aliases:
                    seen_aliases.add(_key(alias))
                    cleaned_aliases.append(alias)
            base_name = _clean(source.get("identity_base_name") or primary)
            variant = _clean(source.get("identity_variant") or source.get("version"))
            if len(primary) > MAX_CHARACTER_NAME_LENGTH or len(base_name) > MAX_CHARACTER_NAME_LENGTH:
                raise ValueError("Series Character Reference names must be 160 characters or fewer.")
            if len(variant) > MAX_IDENTITY_VARIANT_LENGTH:
                raise ValueError("Series Character Reference age/version labels must be 120 characters or fewer.")
            if any(len(alias) > MAX_CHARACTER_ALIAS_LENGTH for alias in cleaned_aliases):
                raise ValueError("Series Character Reference aliases must be 160 characters or fewer.")
            # One alias per row keeps every Excel cell bounded, regardless of alias count.
            for alias in (cleaned_aliases or [""]):
                reference_rows.append([primary, alias, base_name, variant])
                if len(reference_rows) - 1 > MAX_ROWS:
                    raise ValueError("The Series Character Reference exceeds the 50,000 row limit.")
    text = str(chapter_text or "")
    chunks = [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)] or [""]
    for i, chunk in enumerate(chunks, 1):
        context.append([i, metadata.get("chapter_number", ""), info["Chapter Title"], chunk])
    workbook_info_rows = [[
        "Field", "Value", "", "Canonical Character", "Known Alias",
        "Identity Base Name", "Version / Age Variant",
    ]]
    info_entries = [[key, value] for key, value in info.items()]
    info_row_count = max(len(info_entries), len(reference_rows))
    if len(reference_rows) > MAX_ROWS:
        raise ValueError("The Series Character Reference exceeds the 50,000 row limit.")
    for index in range(info_row_count):
        metadata_row = info_entries[index] if index < len(info_entries) else ["", ""]
        reference_row = reference_rows[index] if index < len(reference_rows) else ["", "", "", ""]
        workbook_info_rows.append([
            metadata_row[0], metadata_row[1], "", *reference_row,
        ])
    sheets = [
        ("Dialogue Assignment", dialogue, [38,38,14,32,16,72,34,18,34,22,18,14,14,42,46], {6,8,9,14,15}),
        ("Character Register", characters, [34] + [24] * ALIAS_COLUMNS + [26,48], set(range(1, ALIAS_COLUMNS + 4))),
        ("Chapter Context", context, [14,14,32,100], {4}),
        ("Workbook Info", workbook_info_rows, [28,110,4,36,32,36,28], {2,4,5,6,7}),
    ]
    import io
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="%s"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>%s</Types>' %
            (CONTENT, "".join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % n for n in range(1,len(sheets) + 1))))
        z.writestr("_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="%s"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>' % PKG)
        sheet_nodes = "".join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(name), n, n)
                              for n, (name, _, _, _) in enumerate(sheets, 1))
        z.writestr("xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="%s" xmlns:r="%s"><bookViews><workbookView activeTab="0"/></bookViews>'
            '<sheets>%s</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>' % (MAIN, REL, sheet_nodes))
        rels = "".join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (n,n) for n in range(1,len(sheets) + 1))
        rels += '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>' % (len(sheets) + 1)
        z.writestr("xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="%s">%s</Relationships>' % (PKG, rels))
        z.writestr("xl/styles.xml", _styles())
        for n, (name, rows, widths, wrap) in enumerate(sheets, 1):
            z.writestr(
                "xl/worksheets/sheet%d.xml" % n,
                _sheet(rows, widths, wrap, protect=(name == "Workbook Info")),
            )
    return output.getvalue()


def character_workbook_book_revision(chapters):
    """Stable revision for the exact ordered chapter set in a complete-book workbook."""
    rows = []
    seen_ids, seen_numbers = set(), set()
    for row in chapters or []:
        if not isinstance(row, dict):
            raise ValueError("Every book-workbook chapter reference must be an object.")
        chapter_id = _clean(row.get("chapter_id"))
        revision = _clean(row.get("chapter_revision"))
        try:
            number = int(row.get("chapter_number"))
        except (TypeError, ValueError, OverflowError):
            raise ValueError("A book-workbook chapter has an invalid chapter number.")
        title = _clean(row.get("chapter_title"))
        if not chapter_id or not revision or number < 1:
            raise ValueError("Every book-workbook chapter needs an ID, number and source revision.")
        if chapter_id in seen_ids or number in seen_numbers:
            raise ValueError("The book-workbook chapter register contains duplicate chapter identities.")
        seen_ids.add(chapter_id)
        seen_numbers.add(number)
        rows.append({
            "chapter_id": chapter_id,
            "chapter_number": number,
            "chapter_title": title,
            "chapter_revision": revision,
        })
    rows.sort(key=lambda item: (item["chapter_number"], item["chapter_id"]))
    if not rows:
        raise ValueError("The active book has no chapters to export.")
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def create_complete_book_character_workbook_bytes(metadata, chapters, passages):
    """Create a v2 GPT workbook containing every chapter, passage and source context."""
    chapter_rows = []
    chapter_by_id = {}
    for source in chapters or []:
        row = dict(source)
        chapter_id = _clean(row.get("chapter_id"))
        try:
            number = int(row.get("chapter_number"))
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Every exported chapter needs a valid chapter number.")
        title = _clean(row.get("chapter_title"))
        revision = _clean(row.get("chapter_revision"))
        text = str(row.get("text") or "")
        if not chapter_id or not revision or number < 1 or chapter_id in chapter_by_id:
            raise ValueError("The complete-book export contains an invalid or duplicate chapter reference.")
        row.update({
            "chapter_id": chapter_id, "chapter_number": number,
            "chapter_title": title, "chapter_revision": revision, "text": text,
        })
        row["context_sha256"] = sha256(text.encode("utf-8")).hexdigest()
        row["word_count"] = len(re.findall(r"\S+", text))
        row["passage_count"] = 0
        chapter_rows.append(row)
        chapter_by_id[chapter_id] = row
    if not chapter_rows:
        raise ValueError("The active book has no chapters to export.")
    chapter_rows.sort(key=lambda item: (item["chapter_number"], item["chapter_id"]))
    book_revision = character_workbook_book_revision(chapter_rows)

    dialogue_headers = [
        "Passage ID", "Chapter ID", "Chapter Number", "Chapter Title", "Passage Type", "Dialogue Text",
        "GPT Assigned Character", "GPT Confidence (0–1)", "Existing Assignment (Reference)",
        "Assignment Source (Reference)", "Confidence (Reference)", "Start (Reference)",
        "End (Reference)", "Chapter Revision (Reference)", "Evidence / Notes (GPT)",
    ]
    dialogue = [dialogue_headers]
    seen_passages = set()
    for source in passages or []:
        row = dict(source)
        chapter_id = _clean(row.get("chapter_id"))
        chapter = chapter_by_id.get(chapter_id)
        if chapter is None:
            raise ValueError("A passage belongs to a chapter outside the complete-book chapter register.")
        text = str(row.get("text") or "")
        if len(text.encode("utf-16-le")) // 2 > 32767:
            raise ValueError("A dialogue passage exceeds Excel's 32,767-character cell limit. Split the passage before exporting.")
        narration = str(row.get("kind") or "").casefold() == "narration"
        speakers = row.get("existing_speakers") or row.get("speakers") or []
        if isinstance(speakers, str):
            speakers = [speakers]
        try:
            start, end = int(row.get("start")), int(row.get("end"))
        except (TypeError, ValueError, OverflowError):
            raise ValueError("A source passage has invalid offsets and cannot be exported safely.")
        passage_id = _clean(row.get("passage_id"))
        if not passage_id or passage_id in seen_passages or start < 0 or end <= start:
            raise ValueError("Every source passage needs a unique Passage ID and valid offsets.")
        if str(chapter["text"])[start:end] != text:
            raise ValueError("A source passage does not match the chapter source text. Refresh Character Studio and export again.")
        if _clean(row.get("chapter_revision")) not in {"", chapter["chapter_revision"]}:
            raise ValueError("A source passage revision does not match its Chapter Register entry.")
        seen_passages.add(passage_id)
        gpt_assigned = _clean(
            row.get("gpt_assigned_character") or row.get("GPT Assigned Character")
        )
        gpt_confidence = (
            row.get("gpt_confidence")
            if row.get("gpt_confidence") not in (None, "")
            else row.get("GPT Confidence (0–1)", "")
        )
        gpt_evidence = _clean(
            row.get("gpt_evidence") or row.get("Evidence / Notes (GPT)")
        )
        dialogue.append([
            passage_id, chapter_id, chapter["chapter_number"], chapter["chapter_title"],
            "Narration" if narration else "Dialogue", text,
            "Narrator" if narration else gpt_assigned, gpt_confidence if not narration else "",
            " + ".join(str(value) for value in speakers if str(value or "").strip()),
            str(row.get("assignment_source") or row.get("source") or ""),
            row.get("confidence") if row.get("confidence") is not None else "",
            start, end, chapter["chapter_revision"], "" if narration else gpt_evidence,
        ])
        chapter["passage_count"] += 1
    if len(dialogue) - 1 > MAX_ROWS:
        raise ValueError("The complete book exceeds the 50,000 passage workbook export limit.")

    supplied_register = [
        dict(row) for row in (metadata.get("character_register") or [])
        if isinstance(row, dict)
    ]
    cleaned_register = []
    for row in supplied_register:
        full_name = _clean(row.get("full_name"))
        if not full_name:
            continue
        raw_aliases = row.get("aliases") or []
        if isinstance(raw_aliases, str):
            raw_aliases = [raw_aliases]
        aliases = []
        seen_aliases = {_key(full_name)}
        for raw_alias in raw_aliases:
            alias = _clean(raw_alias)
            if not alias or _key(alias) in seen_aliases:
                continue
            if len(alias) > MAX_CHARACTER_ALIAS_LENGTH:
                raise ValueError("Character Register aliases must be 160 characters or fewer.")
            seen_aliases.add(_key(alias))
            aliases.append(alias)
        if len(full_name) > MAX_CHARACTER_NAME_LENGTH:
            raise ValueError("Character Register names must be 160 characters or fewer.")
        version = _clean(row.get("version"))
        notes = _clean(row.get("notes"))
        if len(version) > MAX_IDENTITY_VARIANT_LENGTH:
            raise ValueError("Character age/version labels must be 120 characters or fewer.")
        if len(notes) > MAX_CHARACTER_NOTES_LENGTH:
            raise ValueError("Character Register notes must be 4,000 characters or fewer.")
        included_raw = row.get("included_in_book", True)
        included = (
            included_raw.strip().casefold() in {"yes", "y", "true", "1", "x"}
            if isinstance(included_raw, str) else bool(included_raw)
        )
        cleaned_register.append({
            "full_name": full_name, "aliases": aliases,
            "version": version, "notes": notes, "included_in_book": included,
        })

    alias_column_count = max(
        [ALIAS_COLUMNS] + [len(row["aliases"]) for row in cleaned_register]
    )
    char_headers = ["Full Name"] + [
        "Alias %d" % n for n in range(1, alias_column_count + 1)
    ] + ["Version / Age Variant", "Character Notes", "Included in This Book?"]
    characters = [char_headers]
    for row in cleaned_register:
        aliases = list(row["aliases"])
        characters.append([
            row["full_name"], *aliases,
            *([""] * (alias_column_count - len(aliases))),
            row["version"], row["notes"],
            "YES" if row["included_in_book"] else "NO",
        ])
    characters.extend([[""] * len(char_headers) for _ in range(40)])

    chapter_register = [[
        "Chapter ID", "Chapter Number", "Chapter Title", "Chapter Revision (Reference)",
        "Passage Count (Reference)", "Word Count (Reference)", "Context SHA256 (Reference)",
    ]]
    context = [[
        "Chapter ID", "Chapter Number", "Chapter Title", "Context Part",
        "Context Parts", "Chapter Text",
    ]]
    total_context_rows = 0
    for chapter in chapter_rows:
        chapter_register.append([
            chapter["chapter_id"], chapter["chapter_number"], chapter["chapter_title"],
            chapter["chapter_revision"], chapter["passage_count"], chapter["word_count"],
            chapter["context_sha256"],
        ])
        source_text = chapter["text"]
        chunks = [source_text[i:i + CHUNK] for i in range(0, len(source_text), CHUNK)] or [""]
        for part, chunk in enumerate(chunks, 1):
            context.append([
                chapter["chapter_id"], chapter["chapter_number"], chapter["chapter_title"],
                part, len(chunks), chunk,
            ])
            total_context_rows += 1
            if total_context_rows > MAX_ROWS:
                raise ValueError("The book's Chapter Context exceeds the 50,000-row workbook limit.")

    reference_headers = [
        "Canonical Character", "Known Alias", "Identity Base Name", "Version / Age Variant",
        "Character Notes (Reference)", "Dialogue Sample (Reference)", "Pronunciation (Reference)",
    ]
    reference_rows = [reference_headers]
    for source in metadata.get("series_character_reference") or []:
        if not isinstance(source, dict):
            continue
        primary = _clean(source.get("primary_name") or source.get("name"))
        if not primary:
            continue
        base_name = _clean(source.get("identity_base_name") or primary)
        variant = _clean(source.get("identity_variant") or source.get("version"))
        aliases = source.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        cleaned_aliases = []
        seen_aliases = {_key(primary)}
        for raw_alias in aliases:
            alias = _clean(raw_alias)
            if alias and _key(alias) not in seen_aliases:
                seen_aliases.add(_key(alias))
                cleaned_aliases.append(alias)
        if len(primary) > MAX_CHARACTER_NAME_LENGTH or len(base_name) > MAX_CHARACTER_NAME_LENGTH:
            raise ValueError("Series Character Reference names must be 160 characters or fewer.")
        if len(variant) > MAX_IDENTITY_VARIANT_LENGTH:
            raise ValueError("Series Character Reference age/version labels must be 120 characters or fewer.")
        if any(len(alias) > MAX_CHARACTER_ALIAS_LENGTH for alias in cleaned_aliases):
            raise ValueError("Series Character Reference aliases must be 160 characters or fewer.")
        notes = str(source.get("notes") or "").strip()[:4000]
        sample = str(source.get("dialogue_sample") or "").strip()[:4000]
        pronunciation = str(source.get("pronunciation") or "").strip()[:500]
        for alias in (cleaned_aliases or [""]):
            reference_rows.append([primary, alias, base_name, variant, notes, sample, pronunciation])
            if len(reference_rows) - 1 > MAX_ROWS:
                raise ValueError("The Series Character Reference exceeds the 50,000-row workbook limit.")

    info = [
        ["Field", "Value"],
        ["Workbook Schema", "ryu.character-studio-workbook"],
        ["Workbook Version", 2],
        ["Export Scope", "complete_book"],
        ["Export ID", str(metadata.get("export_id") or uuid.uuid4().hex)],
        ["Passage Count", len(dialogue) - 1],
        ["Chapter Count", len(chapter_rows)],
        ["Book Title", _clean(metadata.get("project_title"))],
        ["Author", _clean(metadata.get("author"))],
        ["Publisher", _clean(metadata.get("publisher"))],
        ["Language", _clean(metadata.get("language"))],
        ["Genre", _clean(metadata.get("genre"))],
        ["Publication Year", _clean(metadata.get("year"))],
        ["Series Name", _clean(metadata.get("series_name"))],
        ["Series Volume", _clean(metadata.get("series_volume"))],
        ["Book Revision", book_revision],
        ["Exported At (UTC)", datetime.now(timezone.utc).isoformat(timespec="seconds")],
        ["Instructions",
         "This is a COMPLETE-BOOK workbook. Read every chapter in Chapter Context before assigning dialogue. "
         "Dialogue Assignment contains every source-verified passage from every chapter. Assign a confirmed "
         "Character Register identity to every genuine spoken Dialogue row. Read the full surrounding scene and earlier/later "
         "chapters; do not decide from the isolated quote alone. Reuse the exact canonical identity from Series Character "
         "Reference whenever the speaker is the same person, and use aliases only as alternate names for that same identity. "
         "Never infer a speaker from a nearby name alone. Never invent a personal name from the book title, series title, "
         "chapter title, narrator text or an unverified honorific. If the source identifies a speaker only by a stable role "
         "and gives no personal name, add one clearly descriptive role identity such as 'Unnamed Classroom Teacher' and "
         "state in Character Notes that this is an unnamed role, not a supplied personal name; reuse it consistently only "
         "when the source supports the same speaker. Use source-supported labels for identifiable non-human speakers or "
         "collectives, and explain the evidence. Do not assign a speaker to a quoted word, thought, emphasized term or other "
         "quotation embedded inside narration; those are not spoken dialogue. Do not combine distinct turns or speakers "
         "into one identity. If the source truly cannot identify a speaker or role, leave that row blank and explain why "
         "in Evidence / Notes (GPT); do not guess. A blank row is a deliberate unresolved review item and will block import. "
         "Narration is protected as Narrator. "
         "Use numeric GPT Confidence from 0.0 to 1.0 and add concise evidence in Evidence / Notes (GPT). "
         "Add every character appearing in this book to Character Register. Copy an existing canonical name and "
         "its known aliases from Series Character Reference when it is the same person. Add newly discovered "
         "characters with their full name and aliases. Use Version / Age Variant only for genuinely distinct "
         "versions of one identity. Set Included in This Book? to YES for each character who appears in this book. "
         "Only rows marked YES are imported into the series Character Library and this book's cast. "
         "Series Character Reference, Chapter Register, Chapter Context and Workbook Info are read-only references. "
         "Do not change Passage ID, Chapter ID, dialogue text, chapter revision, offsets or other reference columns. "
         "Do not remove or duplicate passage rows. For more than 30 aliases, add Alias 31, Alias 32, and so on."],
    ]

    sheets = [
        ("Dialogue Assignment", dialogue, [38,38,14,32,16,72,34,18,34,22,18,14,14,42,46], {6,8,9,14,15}),
        ("Character Register", characters, [34] + [24] * alias_column_count + [26,48,24], set(range(1, alias_column_count + 5))),
        ("Chapter Register", chapter_register, [38,14,32,42,22,20,66], set(range(1,8))),
        ("Chapter Context", context, [38,14,32,14,14,100], {6}),
        ("Series Character Reference", reference_rows, [38,34,38,26,56,64,32], {1,2,3,4,5,6,7}),
        ("Workbook Info", info, [30,120], {2}),
    ]
    import io
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="%s"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>%s</Types>'
            % (CONTENT, "".join(
                '<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                % number for number in range(1, len(sheets) + 1)
            )),
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="%s"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
            % PKG,
        )
        sheet_nodes = "".join(
            '<sheet name="%s" sheetId="%d" r:id="rId%d"/>'
            % (escape(name), number, number)
            for number, (name, _, _, _) in enumerate(sheets, 1)
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="%s" xmlns:r="%s"><bookViews><workbookView activeTab="0"/></bookViews>'
            '<sheets>%s</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>'
            % (MAIN, REL, sheet_nodes),
        )
        relationships = "".join(
            '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>'
            % (number, number)
            for number in range(1, len(sheets) + 1)
        )
        relationships += (
            '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            % (len(sheets) + 1)
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="%s">%s</Relationships>'
            % (PKG, relationships),
        )
        archive.writestr("xl/styles.xml", _styles())
        for number, (name, rows, widths, wrap) in enumerate(sheets, 1):
            archive.writestr(
                "xl/worksheets/sheet%d.xml" % number,
                _sheet(
                    rows, widths, wrap,
                    protect=name in {"Chapter Register", "Chapter Context", "Series Character Reference", "Workbook Info"},
                ),
            )
    result = output.getvalue()
    if len(result) > MAX_BYTES:
        raise ValueError("The complete-book workbook exceeds the 25 MB safe import/export limit. Split the book into smaller volumes.")
    return result

def refresh_complete_book_character_workbook_bytes(
    document, *, metadata, chapters, passages
):
    """Rebuild a current book workbook, carrying forward only exact unchanged GPT rows."""
    if int(document.get("schema_version") or 0) != 2:
        raise ValueError("Only a version 2 complete-book workbook can be refreshed safely.")
    old_info = document.get("info") or {}
    if _clean(old_info.get("Export Scope")) != "complete_book":
        raise ValueError("Choose a complete-book Character Studio workbook to refresh.")
    if _key(old_info.get("Series Name")) != _key(metadata.get("series_name")):
        raise ValueError("The old workbook belongs to a different series. Refresh was not created.")
    if _key(old_info.get("Book Title")) != _key(metadata.get("project_title")):
        raise ValueError("The old workbook belongs to a different book. Refresh was not created.")

    old_references = list(document.get("chapter_references") or [])
    current_chapters = [
        dict(row) for row in (chapters or []) if isinstance(row, dict)
    ]
    old_by_id = {_clean(row.get("chapter_id")): row for row in old_references}
    current_by_id = {_clean(row.get("chapter_id")): row for row in current_chapters}
    if (
        not old_by_id or len(old_by_id) != len(old_references)
        or set(old_by_id) != set(current_by_id)
    ):
        raise ValueError("The active book chapter set changed after export. Workbook refresh cannot reconcile different chapters.")

    current_book_revision = character_workbook_book_revision(current_chapters)
    if current_book_revision != _clean(old_info.get("Book Revision")):
        raise ValueError("One or more chapter identities or revisions changed after export. Workbook refresh cannot copy assignments.")
    for chapter_id, current in current_by_id.items():
        old = old_by_id[chapter_id]
        current_text = str(current.get("text") or "")
        if (
            int(current.get("chapter_number") or 0) != int(old.get("chapter_number") or 0)
            or _clean(current.get("chapter_title")) != _clean(old.get("chapter_title"))
            or _clean(current.get("chapter_revision")) != _clean(old.get("chapter_revision"))
            or sha256(current_text.encode("utf-8")).hexdigest() != _clean(old.get("context_sha256"))
            or len(re.findall(r"\S+", current_text)) != int(old.get("word_count") or 0)
        ):
            raise ValueError(
                "Chapter %s source text or revision changed after export. Workbook refresh will not transfer GPT assignments."
                % (old.get("chapter_number") or "?")
            )

    old_rows_by_chapter = {chapter_id: [] for chapter_id in old_by_id}
    for row in document.get("dialogue_rows") or []:
        if not isinstance(row, dict):
            continue
        chapter_id = _clean(row.get("Chapter ID"))
        if chapter_id in old_rows_by_chapter:
            try:
                start = int(float(row.get("Start (Reference)")))
                end = int(float(row.get("End (Reference)")))
            except (TypeError, ValueError, OverflowError):
                continue
            old_rows_by_chapter[chapter_id].append({
                "passage_id": _clean(row.get("Passage ID")),
                "start": start,
                "end": end,
                "text": str(row.get("Dialogue Text") or ""),
                "kind": _clean(row.get("Passage Type")).casefold(),
                "assigned": _clean(row.get("GPT Assigned Character")),
                "confidence": _clean(row.get("GPT Confidence (0–1)")),
                "evidence": _clean(row.get("Evidence / Notes (GPT)")),
            })

    refreshed_passages = []
    exact_rows_carried = 0
    assignments_carried = 0
    review_required = 0
    reclassified_as_narration = 0
    for source in passages or []:
        if not isinstance(source, dict):
            continue
        row = dict(source)
        chapter_id = _clean(row.get("chapter_id"))
        chapter = current_by_id.get(chapter_id)
        if chapter is None:
            raise ValueError("A refreshed passage belongs to a chapter outside the active book.")
        start, end = int(row.get("start", -1)), int(row.get("end", -1))
        text = str(row.get("text") or "")
        source_text = str(chapter.get("text") or "")
        if start < 0 or end <= start or source_text[start:end] != text:
            raise ValueError("A refreshed passage does not match the unchanged chapter source text.")
        old_rows = old_rows_by_chapter.get(chapter_id, [])
        exact = [
            old for old in old_rows
            if old["start"] == start and old["end"] == end and old["text"] == text
        ]
        narration = _key(row.get("kind")) == "narration"
        if narration:
            if any(old["kind"] == "dialogue" for old in exact):
                reclassified_as_narration += 1
            refreshed_passages.append(row)
            continue

        exact_dialogue = [old for old in exact if old["kind"] == "dialogue"]
        if len(exact_dialogue) == 1 and len(exact) == 1:
            old = exact_dialogue[0]
            row["gpt_assigned_character"] = old["assigned"]
            row["gpt_confidence"] = old["confidence"]
            row["gpt_evidence"] = old["evidence"]
            exact_rows_carried += 1
            if old["assigned"]:
                assignments_carried += 1
            refreshed_passages.append(row)
            continue

        overlapping = [
            old for old in old_rows
            if old["end"] > start and old["start"] < end
        ]
        if overlapping:
            previous = []
            for old in overlapping[:4]:
                label = old["passage_id"] or "%s:%s" % (old["start"], old["end"])
                assigned = old["assigned"] or "unassigned"
                previous.append(
                    "previous passage %s (%s; %s:%s)" %
                    (label, assigned, old["start"], old["end"])
                )
            row["gpt_evidence"] = (
                "REVIEW REQUIRED — this passage no longer exactly matches one old workbook row. "
                + "; ".join(previous)
                + ". Previous speaker values were not copied because the old passage may have split or changed boundaries. "
                "Read the full scene and assign the speaker for this passage only."
            )
        else:
            row["gpt_evidence"] = (
                "REVIEW REQUIRED — this is a new dialogue passage with no exact match in the previous workbook. "
                "Read the full scene and assign a source-supported Character Register identity; do not guess."
            )
        review_required += 1
        refreshed_passages.append(row)

    refreshed_metadata = dict(metadata or {})
    refreshed_metadata["character_register"] = list(document.get("characters") or [])
    unresolved_dialogue = 0
    for row in refreshed_passages:
        if _key(row.get("kind")) == "narration":
            continue
        assigned = _clean(row.get("gpt_assigned_character"))
        saved_speakers = row.get("existing_speakers") or row.get("speakers") or []
        if isinstance(saved_speakers, str):
            saved_speakers = [saved_speakers]
        has_saved_identity = any(_clean(value) for value in saved_speakers)
        if not assigned and not has_saved_identity:
            unresolved_dialogue += 1
    workbook_bytes = create_complete_book_character_workbook_bytes(
        refreshed_metadata, current_chapters, refreshed_passages
    )
    return workbook_bytes, {
        "exact_dialogue_rows_carried": exact_rows_carried,
        "gpt_assignments_carried": assignments_carried,
        "new_or_changed_dialogue_rows_for_review": review_required,
        "unresolved_dialogue_passages": unresolved_dialogue,
        "dialogue_rows_reclassified_as_narration": reclassified_as_narration,
        "character_register_entries_preserved": len(refreshed_metadata["character_register"]),
        "chapter_count": len(current_chapters),
        "passage_count": len(refreshed_passages),
    }


def _read_sheet(archive, target, shared):
    normalized_target = str(target or "").replace("\\", "/")
    path = (
        posixpath.normpath(normalized_target.lstrip("/"))
        if normalized_target.startswith("/")
        else posixpath.normpath(posixpath.join("xl", normalized_target))
    )
    if not path.startswith("xl/") or path.startswith("../") or path not in archive.namelist():
        raise ValueError("The workbook references a missing or invalid worksheet.")
    root = ET.fromstring(archive.read(path))
    data = root.find(_t("sheetData"))
    result = []
    if data is None: return result
    for row in data.findall(_t("row")):
        cells = []
        for cell in row.findall(_t("c")):
            if cell.find(_t("f")) is not None:
                raise ValueError("Character Studio workbooks must contain plain values, not formulas.")
            col = _col_number(cell.get("r"))
            if col <= 0:
                raise ValueError("The workbook contains a cell with an invalid address.")
            while len(cells) < col: cells.append("")
            typ = cell.get("t") or ""
            value = cell.find(_t("v"))
            if typ == "inlineStr":
                raw = "".join(node.text or "" for node in cell.iter(_t("t")))
            elif value is None: raw = ""
            elif typ == "s":
                try: raw = shared[int(value.text or "0")]
                except (ValueError, IndexError): raise ValueError("Invalid Excel shared-string reference.")
            elif typ == "b": raw = "TRUE" if value.text == "1" else "FALSE"
            else: raw = value.text or ""
            cells[col - 1] = raw
        result.append(cells)
    return result

def _records(rows):
    if not rows: return []
    headers = [_clean(x) for x in rows[0]]
    found = []
    for row in rows[1:]:
        values = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers)) if headers[i]}
        if any(_clean(v) for v in values.values()): found.append(values)
    return found

def read_character_workbook(path):
    """Read Excel/LibreOffice-authored XLSX, including shared and inline strings."""
    source = Path(path).expanduser()
    if not source.is_file(): raise FileNotFoundError("Choose an existing Character Studio workbook.")
    if source.stat().st_size <= 0 or source.stat().st_size > MAX_BYTES:
        raise ValueError("The workbook must be between 1 byte and 25 MB.")
    if not zipfile.is_zipfile(source): raise ValueError("The selected file is not a valid .xlsx workbook.")
    try:
        with zipfile.ZipFile(source) as z:
            infos = z.infolist()
            if len(infos) > 100 or sum(x.file_size for x in infos) > MAX_EXPANDED:
                raise ValueError("The workbook exceeds the safe size or file-count limits.")
            for name in ("xl/workbook.xml", "xl/_rels/workbook.xml.rels"):
                if name not in z.namelist(): raise ValueError("The file is missing required Excel workbook data.")
            book = ET.fromstring(z.read("xl/workbook.xml"))
            relroot = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
            relationship_items = relroot.findall("{%s}Relationship" % PKG)
            relationship_ids = [item.get("Id") for item in relationship_items]
            if not all(relationship_ids) or len(relationship_ids) != len(set(relationship_ids)):
                raise ValueError("The workbook contains duplicate or invalid relationship IDs.")
            relationships = {item.get("Id"): item for item in relationship_items}
            targets = {}
            for sheet in book.findall(".//" + _t("sheet")):
                sheet_name = _clean(sheet.get("name"))
                relationship = relationships.get(sheet.get("{%s}id" % REL))
                if not sheet_name or relationship is None:
                    raise ValueError("A workbook sheet has a missing or invalid relationship.")
                if not str(relationship.get("Type") or "").endswith("/worksheet"):
                    raise ValueError("A workbook sheet does not reference a valid worksheet.")
                if sheet_name in targets:
                    raise ValueError("The workbook contains duplicate worksheet names.")
                targets[sheet_name] = relationship.get("Target")
            required = {"Dialogue Assignment", "Character Register", "Chapter Context", "Workbook Info"}
            if not required.issubset(targets): raise ValueError("Required Character Studio workbook sheets are missing.")
            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
                shared = ["".join(n.text or "" for n in x.iter(_t("t"))) for x in ss.findall(_t("si"))]
            sheets = {name: _read_sheet(z, targets[name], shared) for name in required}
            for optional_sheet in ("Series Character Reference", "Chapter Register"):
                if optional_sheet in targets:
                    sheets[optional_sheet] = _read_sheet(z, targets[optional_sheet], shared)
    except (zipfile.BadZipFile, ET.ParseError, KeyError) as exc:
        raise ValueError("The .xlsx workbook is damaged or unsupported.") from exc
    info_rows = _records(sheets["Workbook Info"])
    info = {
        _clean(row.get("Field")): _clean(row.get("Value", ""))
        for row in info_rows if _clean(row.get("Field"))
    }
    if info.get("Workbook Schema") != "ryu.character-studio-workbook":
        raise ValueError("This workbook was not exported by Character Studio.")
    try: workbook_version = int(float(info.get("Workbook Version", "0")))
    except (TypeError, ValueError, OverflowError): workbook_version = 0
    if workbook_version not in {1, 2}: raise ValueError("This Character Studio workbook version is not supported.")
    if workbook_version == 2:
        if info.get("Export Scope") != "complete_book":
            raise ValueError("Version 2 Character Studio workbooks must use the complete-book export scope.")
        if not {"Chapter Register", "Series Character Reference"}.issubset(sheets):
            raise ValueError("The complete-book workbook is missing its Chapter Register or Series Character Reference sheet.")
        reference_headers = {_clean(value) for value in (sheets["Series Character Reference"][0] if sheets["Series Character Reference"] else [])}
        if not {"Canonical Character", "Known Alias", "Identity Base Name", "Version / Age Variant"}.issubset(reference_headers):
            raise ValueError("The Series Character Reference is missing its canonical-name or alias columns.")
        context_headers = {_clean(value) for value in (sheets["Chapter Context"][0] if sheets["Chapter Context"] else [])}
        if not {"Chapter ID", "Chapter Number", "Chapter Title", "Context Part", "Context Parts", "Chapter Text"}.issubset(context_headers):
            raise ValueError("The Chapter Context sheet is missing required chapter text or part-reference columns.")
    dialogue_headers = {_clean(value) for value in (sheets["Dialogue Assignment"][0] if sheets["Dialogue Assignment"] else [])}
    required_dialogue_headers = {
        "Passage ID", "Chapter ID", "Passage Type", "Dialogue Text",
        "GPT Assigned Character", "GPT Confidence (0–1)", "Start (Reference)",
        "End (Reference)", "Chapter Revision (Reference)",
    }
    if not required_dialogue_headers.issubset(dialogue_headers):
        raise ValueError("The Dialogue Assignment sheet is missing required columns. Restore the exported headers and try again.")
    character_headers = {_clean(value) for value in (sheets["Character Register"][0] if sheets["Character Register"] else [])}
    if not {"Full Name", "Version / Age Variant"}.issubset(character_headers):
        raise ValueError("The Character Register sheet is missing its Full Name or Version / Age Variant column.")
    if workbook_version == 2 and "Included in This Book?" not in character_headers:
        raise ValueError("The complete-book Character Register is missing the Included in This Book? column.")
    dialogue = _records(sheets["Dialogue Assignment"])
    try:
        expected_passages = int(float(info.get("Passage Count", "-1")))
    except (TypeError, ValueError, OverflowError):
        expected_passages = -1
    if expected_passages < 0 or len(dialogue) != expected_passages:
        raise ValueError("The workbook is missing or has added dialogue rows. Keep every exported Passage ID row; leave unassigned entries blank instead.")
    char_rows = _records(sheets["Character Register"])
    if len(dialogue) > MAX_ROWS or len(char_rows) > 2000:
        raise ValueError("The workbook exceeds the supported row limits.")
    seen = set()
    for row in dialogue:
        passage = _clean(row.get("Passage ID"))
        if not passage or not str(row.get("Dialogue Text") or ""):
            raise ValueError("Each dialogue row must retain its Passage ID and original text.")
        if passage in seen: raise ValueError("The workbook contains a duplicate Passage ID.")
        seen.add(passage)
    # New exports store the reference table beside Workbook Info in the original four-tab layout.
    # The optional fifth sheet is accepted only for compatibility with earlier experimental exports.
    reference_rows = [
        row for row in info_rows if _clean(row.get("Canonical Character"))
    ]
    legacy_reference_rows = _records(sheets.get("Series Character Reference", []))
    for legacy_row in legacy_reference_rows:
        if "Known Alias" not in legacy_row and _clean(legacy_row.get("Known Aliases")):
            legacy_values = [
                _clean(value) for value in str(legacy_row.get("Known Aliases") or "").splitlines()
                if _clean(value)
            ]
            for alias_value in (legacy_values or [""]):
                reference_rows.append({
                    **legacy_row,
                    "Known Alias": alias_value,
                })
        else:
            reference_rows.append(legacy_row)
    if len(reference_rows) > MAX_ROWS:
        raise ValueError("The Series Character Reference exceeds the 50,000 row limit.")
    reference_by_identity = {}
    for row in reference_rows:
        primary = _clean(row.get("Canonical Character"))
        if not primary:
            continue
        base_name = _clean(row.get("Identity Base Name") or primary)
        variant = _clean(row.get("Version / Age Variant"))
        if len(primary) > MAX_CHARACTER_NAME_LENGTH or len(base_name) > MAX_CHARACTER_NAME_LENGTH:
            raise ValueError("Series Character Reference names must be 160 characters or fewer.")
        if len(variant) > MAX_IDENTITY_VARIANT_LENGTH:
            raise ValueError("Series Character Reference age/version labels must be 120 characters or fewer.")
        identity = (_key(primary), _key(base_name), _key(variant))
        record = reference_by_identity.setdefault(identity, {
            "canonical_name": primary, "aliases": [],
            "identity_base_name": base_name, "identity_variant": variant,
        })
        alias = _clean(row.get("Known Alias"))
        if alias and len(alias) > MAX_CHARACTER_ALIAS_LENGTH:
            raise ValueError("Series Character Reference aliases must be 160 characters or fewer.")
        if alias and _key(alias) != _key(primary) and _key(alias) not in {_key(value) for value in record["aliases"]}:
            record["aliases"].append(alias)
    series_character_reference = list(reference_by_identity.values())

    characters = []
    for n, row in enumerate(char_rows, 2):
        name = _clean(row.get("Full Name"))
        if not name:
            continue
        if len(name) > MAX_CHARACTER_NAME_LENGTH:
            raise ValueError("Character Register names must be 160 characters or fewer.")
        identity_variant = _clean(row.get("Version / Age Variant"))
        if len(identity_variant) > MAX_IDENTITY_VARIANT_LENGTH:
            raise ValueError("Character age/version labels must be 120 characters or fewer.")
        notes = _clean(row.get("Character Notes"))
        if len(notes) > MAX_CHARACTER_NOTES_LENGTH:
            raise ValueError("Character Register notes must be 4,000 characters or fewer.")
        aliases = []
        for column, value in row.items():
            if re.fullmatch(r"Alias\s+\d+", column, re.I) and _clean(value):
                alias = _clean(value)
                if len(alias) > MAX_CHARACTER_ALIAS_LENGTH:
                    raise ValueError("Character aliases must be 160 characters or fewer.")
                aliases.append(alias)
        included_raw = _clean(row.get("Included in This Book?")).casefold()
        included = (included_raw in {"yes", "y", "true", "1", "x"}) if workbook_version == 2 else True
        characters.append({
            "full_name": name,
            "aliases": list(dict.fromkeys(a for a in aliases if _key(a) != _key(name))),
            "version": identity_variant,
            "notes": notes,
            "included_in_book": included,
            "row_number": n,
        })

    chapter_references = []
    if workbook_version == 2:
        chapter_rows = _records(sheets["Chapter Register"])
        chapter_headers = {_clean(value) for value in (sheets["Chapter Register"][0] if sheets["Chapter Register"] else [])}
        required_chapter_headers = {
            "Chapter ID", "Chapter Number", "Chapter Title", "Chapter Revision (Reference)",
            "Passage Count (Reference)", "Word Count (Reference)", "Context SHA256 (Reference)",
        }
        if not required_chapter_headers.issubset(chapter_headers):
            raise ValueError("The Chapter Register is missing required source-reference columns.")
        if not chapter_rows or len(chapter_rows) > 10000:
            raise ValueError("The complete-book workbook must contain between 1 and 10,000 chapters.")
        seen_chapter_ids, seen_chapter_numbers = set(), set()
        for row in chapter_rows:
            chapter_id = _clean(row.get("Chapter ID"))
            try:
                chapter_number = int(float(row.get("Chapter Number") or 0))
                passage_count = int(float(row.get("Passage Count (Reference)") or -1))
                word_count = int(float(row.get("Word Count (Reference)") or -1))
            except (TypeError, ValueError, OverflowError):
                raise ValueError("The Chapter Register contains an invalid number or count.")
            title = _clean(row.get("Chapter Title"))
            revision = _clean(row.get("Chapter Revision (Reference)"))
            context_digest = _clean(row.get("Context SHA256 (Reference)"))
            if not chapter_id or chapter_number < 1 or passage_count < 0 or word_count < 0 or not revision:
                raise ValueError("Every Chapter Register row needs a valid chapter identity, revision and counts.")
            if chapter_id in seen_chapter_ids or chapter_number in seen_chapter_numbers:
                raise ValueError("The Chapter Register contains a duplicate chapter ID or number.")
            if not re.fullmatch(r"[0-9a-f]{64}", context_digest):
                raise ValueError("A Chapter Register context fingerprint is invalid.")
            seen_chapter_ids.add(chapter_id)
            seen_chapter_numbers.add(chapter_number)
            chapter_references.append({
                "chapter_id": chapter_id, "chapter_number": chapter_number,
                "chapter_title": title, "chapter_revision": revision,
                "passage_count": passage_count, "word_count": word_count,
                "context_sha256": context_digest,
            })
        try:
            declared_chapters = int(float(info.get("Chapter Count") or 0))
        except (TypeError, ValueError, OverflowError):
            declared_chapters = 0
        if len(chapter_references) != declared_chapters:
            raise ValueError("The Chapter Register count does not match Workbook Info.")
        if character_workbook_book_revision(chapter_references) != _clean(info.get("Book Revision")):
            raise ValueError("The Chapter Register was edited or no longer matches the exported book revision.")
        context_rows = _records(sheets["Chapter Context"])
        if len(context_rows) > MAX_ROWS:
            raise ValueError("Chapter Context exceeds the 50,000-row workbook limit.")
        context_chapter_ids = {_clean(row.get("Chapter ID")) for row in context_rows}
        if context_chapter_ids != seen_chapter_ids:
            raise ValueError("Chapter Context does not contain the exact Chapter Register chapter set.")
        for chapter in chapter_references:
            rows_for_chapter = [row for row in context_rows if _clean(row.get("Chapter ID")) == chapter["chapter_id"]]
            if not rows_for_chapter:
                raise ValueError("Chapter %s is missing from Chapter Context." % chapter["chapter_number"])
            try:
                numbered = sorted(
                    ((int(float(row.get("Context Part") or 0)), int(float(row.get("Context Parts") or 0)), row)
                     for row in rows_for_chapter),
                    key=lambda item: (item[0], item[1]),
                )
            except (TypeError, ValueError, OverflowError):
                raise ValueError("Chapter Context contains an invalid part number.")
            part_total = numbered[0][1]
            if any(
                int(float(item[2].get("Chapter Number") or 0)) != chapter["chapter_number"]
                or _clean(item[2].get("Chapter Title")) != chapter["chapter_title"]
                for item in numbered
            ):
                raise ValueError("Chapter %s Context metadata does not match the Chapter Register." % chapter["chapter_number"])
            if part_total < 1 or len(numbered) != part_total or [item[0] for item in numbered] != list(range(1, part_total + 1)):
                raise ValueError("Chapter %s has missing, duplicated or reordered context parts." % chapter["chapter_number"])
            if any(item[1] != part_total for item in numbered):
                raise ValueError("Chapter %s has inconsistent context part counts." % chapter["chapter_number"])
            context_text = "".join(str(item[2].get("Chapter Text") or "") for item in numbered)
            if sha256(context_text.encode("utf-8")).hexdigest() != chapter["context_sha256"]:
                raise ValueError("Chapter %s context was changed or truncated. Restore the exported Chapter Context." % chapter["chapter_number"])
            if len(re.findall(r"\S+", context_text)) != chapter["word_count"]:
                raise ValueError("Chapter %s context word count does not match its source reference." % chapter["chapter_number"])
        chapters_by_id = {row["chapter_id"]: row for row in chapter_references}
        passage_counts = {chapter_id: 0 for chapter_id in chapters_by_id}
        for row in dialogue:
            chapter_id = _clean(row.get("Chapter ID"))
            chapter = chapters_by_id.get(chapter_id)
            if chapter is None:
                raise ValueError("A Dialogue Assignment row references a chapter outside the Chapter Register.")
            try:
                number = int(float(row.get("Chapter Number") or 0))
            except (TypeError, ValueError, OverflowError):
                raise ValueError("A Dialogue Assignment row has an invalid chapter number.")
            if (number != chapter["chapter_number"]
                or _clean(row.get("Chapter Title")) != chapter["chapter_title"]
                or _clean(row.get("Chapter Revision (Reference)")) != chapter["chapter_revision"]):
                raise ValueError("A Dialogue Assignment row no longer matches its Chapter Register reference.")
            passage_counts[chapter_id] += 1
        for chapter in chapter_references:
            if passage_counts[chapter["chapter_id"]] != chapter["passage_count"]:
                raise ValueError("Chapter %s is missing or has added dialogue passage rows." % chapter["chapter_number"])

    return {
        "info": info,
        "dialogue_rows": dialogue,
        "characters": characters,
        "series_character_reference": series_character_reference,
        "chapter_references": chapter_references,
        "schema_version": workbook_version,
        "path": str(source.resolve()),
        "sha256": sha256(source.read_bytes()).hexdigest(),
    }

def plan_character_workbook_import(document, *, series, registry_rows, project_characters,
                                   chapter_id, chapter_revision, current_passages, current_assignments,
                                   deleted_registry_rows=None, book_title=""):
    """Preflight name/alias merges and exact source-passage assignments without writing."""
    info = document.get("info") or {}
    active_series = _clean(series)
    if not active_series: raise ValueError("The active project must belong to a series before import.")
    if _key(info.get("Series Name")) != _key(active_series):
        raise ValueError("Workbook series '%s' does not match active series '%s'." % (info.get("Series Name",""), active_series))
    if _clean(info.get("Chapter ID")) != _clean(chapter_id):
        raise ValueError("This workbook belongs to a different chapter. Export the active chapter again.")
    if _clean(info.get("Chapter Revision")) != _clean(chapter_revision):
        raise ValueError("The chapter changed after export. Export it again before importing.")
    if _clean(book_title) and _key(info.get("Book Title")) != _key(book_title):
        raise ValueError("This workbook belongs to a different book. Select the correct project or export the active book again.")

    issues, existing = [], {}
    deleted_tokens = {}
    for row in (deleted_registry_rows or []):
        if not isinstance(row, dict) or _key(row.get("series") or active_series) != _key(active_series):
            continue
        deleted_name = _clean(row.get("primary_name") or row.get("name"))
        deleted_aliases = row.get("aliases") or []
        if isinstance(deleted_aliases, str):
            deleted_aliases = [deleted_aliases]
        for token in [deleted_name, *(deleted_aliases if isinstance(deleted_aliases, (list, tuple)) else [])]:
            if _clean(token):
                deleted_tokens.setdefault(_key(token), set()).add(deleted_name or _clean(token))

    sources = [(r, True) for r in (registry_rows or []) if isinstance(r, dict)]
    sources += [(r, False) for r in (project_characters or []) if isinstance(r, dict)]
    for row, is_library in sources:
        if _key(row.get("series") or active_series) != _key(active_series): continue
        name = _clean(row.get("primary_name") or row.get("name"))
        if not name: continue
        version = _clean(row.get("identity_variant"))
        key = _key(name) + "|" + _key(version)
        entry = existing.setdefault(key, {"canonical_name":name, "identity_variant":version,
            "identity_base_name":_clean(row.get("identity_base_name")) or name, "aliases":[],
            "library_id":"","voice_name":"","project_voice_profile":"","project_cast_count":0})
        aliases = row.get("aliases") or []
        if isinstance(aliases, str): aliases = [aliases]
        for alias in aliases if isinstance(aliases,(list,tuple)) else []:
            alias = _clean(alias)
            if alias and _key(alias) != _key(name) and _key(alias) not in {_key(x) for x in entry["aliases"]}:
                entry["aliases"].append(alias)
        if is_library:
            incoming_id = _clean(row.get("id"))
            if entry["library_id"] and incoming_id and entry["library_id"] != incoming_id:
                issues.append("Duplicate canonical Character Library records exist for '%s'." % name)
            entry["library_id"] = incoming_id or entry["library_id"]
            entry["voice_name"] = _clean(row.get("voice_name") or row.get("voice"))
        else:
            entry["project_cast_count"] = int(entry.get("project_cast_count") or 0) + 1
            if entry["project_cast_count"] > 1:
                issues.append("Duplicate project Character Studio cast records exist for '%s'. Resolve the duplicate before importing." % name)
            entry["project_voice_profile"] = _clean(row.get("voice_profile"))

    existing_tokens = {}
    for key, row in existing.items():
        for token in [row["canonical_name"], *row["aliases"]]:
            existing_tokens.setdefault(_key(token), set()).add(key)

    planned, imported_keys, owners = [], set(), {}
    for source in document.get("characters") or []:
        if source.get("included_in_book") is False:
            continue
        name = _clean(source.get("full_name"))
        if not name:
            continue
        if len(name) > MAX_CHARACTER_NAME_LENGTH:
            issues.append("Character Register names must be 160 characters or fewer.")
            continue
        version = _clean(source.get("version"))
        if len(version) > MAX_IDENTITY_VARIANT_LENGTH:
            issues.append("Character age/version labels must be 120 characters or fewer.")
            continue
        notes = _clean(source.get("notes"))
        if len(notes) > MAX_CHARACTER_NOTES_LENGTH:
            issues.append("Character Register notes must be 4,000 characters or fewer.")
            continue
        if _key(name) == "narrator":
            issues.append("Narrator is a protected automatic narration role and cannot be added to Character Register.")
            continue
        canonical = name if not version or name.casefold().endswith((" (" + version + ")").casefold()) else "%s (%s)" % (name, version)
        aliases = []
        alias_too_long = False
        for raw in source.get("aliases") or []:
            alias = _clean(raw)
            if len(alias) > MAX_CHARACTER_ALIAS_LENGTH:
                issues.append("Character aliases must be 160 characters or fewer.")
                alias_too_long = True
                continue
            if _key(alias) == "narrator":
                issues.append("Narrator is a protected role and cannot be used as a character alias.")
                continue
            if alias and _key(alias) not in {_key(name),_key(canonical)} and _key(alias) not in {_key(x) for x in aliases}:
                aliases.append(alias)
        if alias_too_long:
            continue
        ikey = _key(canonical) + "|" + _key(version)
        if ikey in imported_keys:
            issues.append("Character Register repeats '%s'." % canonical)
            continue
        imported_keys.add(ikey)
        tokens = [canonical, *aliases]
        recovery_matches = set()
        for token in tokens:
            recovery_matches.update(deleted_tokens.get(_key(token), set()))
        if recovery_matches:
            issues.append(
                "'%s' matches a deleted Character Library identity in Recovery Bin (%s). "
                "Restore or resolve that identity before importing." %
                (canonical, ", ".join(sorted(recovery_matches)[:4]))
            )
            continue
        for token in tokens:
            prior = owners.get(_key(token))
            if prior and prior != ikey: issues.append("Imported name or alias '%s' belongs to more than one character." % token)
            owners[_key(token)] = ikey
        matches = set()
        for token in tokens: matches.update(existing_tokens.get(_key(token), set()))
        if len(matches) > 1:
            issues.append("'%s' matches multiple existing series characters. Resolve the alias conflict." % canonical)
            continue
        match_key = next(iter(matches), "")
        match = existing.get(match_key) if match_key else None
        if match and _key(match.get("identity_variant")) != _key(version):
            issues.append(
                "'%s' matches an existing character with a different version/age identity. "
                "Do not merge age variants; resolve the version or keep a separate canonical name." % canonical
            )
            continue
        final_name = match["canonical_name"] if match else canonical
        merged_aliases = list(match["aliases"] if match else [])
        aliases_to_add = list(aliases)
        # A new full-name spelling that matched an existing alias is itself
        # another confirmed alias, unless the register declares a separate age variant.
        if match and not version and _key(name) != _key(final_name):
            aliases_to_add.insert(0, name)
        added_aliases = []
        for alias in aliases_to_add:
            if _key(alias) != _key(final_name) and _key(alias) not in {_key(x) for x in merged_aliases}:
                merged_aliases.append(alias)
                added_aliases.append(alias)
        planned.append({
            "canonical_name":final_name, "identity_base_name":name, "identity_variant":version,
            "aliases":merged_aliases, "aliases_to_add":added_aliases, "notes":notes,
            "library_id":_clean(match.get("library_id")) if match else "",
            "existing_voice_name":_clean((match or {}).get("voice_name") or (match or {}).get("project_voice_profile")),
            "action":"merge" if match else "create", "series":active_series,
        })

    identities = {}
    for key, row in existing.items():
        identities[key] = {"canonical_name":row["canonical_name"],"tokens":[row["canonical_name"],*row["aliases"]]}
    for row in planned:
        key = _key(row["canonical_name"]) + "|" + _key(row["identity_variant"])
        identities[key] = {"canonical_name":row["canonical_name"],"tokens":[row["canonical_name"],*row["aliases"]]}
    token_map = {}
    for key, row in identities.items():
        for token in row["tokens"]: token_map.setdefault(_key(token),set()).add(key)
    registered_keys = {
        _key(row["canonical_name"]) + "|" + _key(row.get("identity_variant"))
        for row in planned
    }

    by_id = {_clean(x.get("passage_id")):x for x in current_passages if isinstance(x,dict) and _clean(x.get("passage_id"))}
    by_span = {(int(x.get("start",-1)),int(x.get("end",-1))):x for x in current_assignments if isinstance(x,dict)}
    assignments, seen = [], set()
    superseded_assignments = {}
    workbook_rows = [row for row in (document.get("dialogue_rows") or []) if isinstance(row, dict)]
    workbook_row_by_id = {_clean(row.get("Passage ID")): row for row in workbook_rows}
    workbook_ids = {_clean(row.get("Passage ID")) for row in workbook_rows}
    if workbook_ids != set(by_id):
        issues.append("The workbook does not contain the complete set of chapter passages. Export the active book again after source passage structure changes.")
    for row in document.get("dialogue_rows") or []:
        if not isinstance(row, dict):
            issues.append("The workbook contains an invalid dialogue row.")
            continue
        pid = _clean(row.get("Passage ID"))
        if pid in seen: issues.append("Duplicate Passage ID %s." % pid); continue
        seen.add(pid)
        current = by_id.get(pid)
        if not current: issues.append("Passage %s is no longer in this chapter." % pid); continue
        try:
            start_value = row.get("Start (Reference)")
            end_value = row.get("End (Reference)")
            raw_start = float(start_value) if start_value not in (None, "") else -1
            raw_end = float(end_value) if end_value not in (None, "") else -1
            start_ref, end_ref = int(raw_start), int(raw_end)
            if raw_start != start_ref or raw_end != end_ref:
                raise ValueError("Non-integer source offset")
        except (TypeError, ValueError, OverflowError):
            start_ref = end_ref = -1
        if (str(row.get("Dialogue Text") or "") != str(current.get("text") or "")
            or int(current.get("start",-1)) != start_ref or int(current.get("end",-1)) != end_ref
            or _clean(row.get("Chapter ID")) != _clean(chapter_id)
            or _clean(row.get("Chapter Revision (Reference)")) != _clean(chapter_revision)):
            issues.append("Passage %s text, offsets or source revision changed. Export again." % pid); continue
        workbook_type = _clean(row.get("Passage Type")).casefold()
        source_is_narration = _key(current.get("kind")) == "narration"
        legacy_inline_quote = (
            source_is_narration
            and _clean(current.get("source")) == "automatic_embedded_quote"
            and workbook_type == "dialogue"
        )
        if (
            workbook_type not in {"dialogue", "narration"}
            or ((workbook_type == "narration") != source_is_narration and not legacy_inline_quote)
        ):
            issues.append("Passage %s has an edited or invalid Passage Type. Export the chapter again." % pid)
            continue
        narration = source_is_narration
        assigned = _clean(row.get("GPT Assigned Character"))
        if narration:
            if _clean(current.get("source")) == "automatic_embedded_quote":
                quote_start, quote_end = int(current.get("start", -1)), int(current.get("end", -1))
                for saved in current_assignments:
                    if not isinstance(saved, dict):
                        continue
                    saved_source = _clean(saved.get("source") or "manual").casefold()
                    if saved_source not in {"ai", "outsourced"}:
                        continue
                    try:
                        saved_start = int(saved.get("start", -1))
                        saved_end = int(saved.get("end", -1))
                    except (TypeError, ValueError, OverflowError):
                        continue
                    if saved_start >= quote_end or saved_end <= quote_start:
                        continue
                    impacted = [
                        item for item in current_passages
                        if isinstance(item, dict)
                        and int(item.get("start", -1)) < saved_end
                        and int(item.get("end", -1)) > saved_start
                    ]
                    exact_quote = saved_start == quote_start and saved_end == quote_end
                    only_embedded_narration = bool(impacted) and all(
                        _key(item.get("kind")) == "narration"
                        and _clean(item.get("source")) == "automatic_embedded_quote"
                        for item in impacted
                    )
                    if exact_quote or only_embedded_narration:
                        speakers_value = saved.get("speakers")
                        if not isinstance(speakers_value, (list, tuple)):
                            speakers_value = [saved.get("speaker")] if saved.get("speaker") else []
                        key = (saved_start, saved_end, saved_source)
                        superseded_assignments.setdefault(key, {
                            "chapter_id": _clean(chapter_id),
                            "start": saved_start,
                            "end": saved_end,
                            "source": saved_source,
                            "speakers": [_clean(value) for value in speakers_value if _clean(value)],
                            "text": str(saved.get("text") or ""),
                        })
            if not legacy_inline_quote and _key(assigned) != "narrator":
                issues.append("Narration passage %s must retain the protected Narrator assignment." % pid)
            continue

        # Resolve the current assignment before considering a blank workbook
        # cell. Blank is safe only when this exact dialogue span already has
        # one known, unambiguous character assignment in the active project or
        # series library. Otherwise the complete import must stop; silently
        # skipping the row would leave dialogue without a character.
        start, end = int(current["start"]), int(current["end"])
        if str(current.get("assignment_state") or "").casefold() == "conflict":
            issues.append("Passage %s already has conflicting saved assignments. Resolve it in Character Studio before import." % pid)
            continue
        old = by_span.get((start, end), {})
        speakers = old.get("speakers")
        if not isinstance(speakers, (list, tuple)):
            speakers = [old.get("speaker")] if old.get("speaker") else []
        old_names = [_clean(value) for value in speakers if _clean(value)]

        # Older AI/outsourced assignments may span multiple newly segmented source
        # passages. Replace only non-manual records, only when every impacted
        # current dialogue passage has an explicit workbook identity, and only
        # through the explicit import-review/confirmation transaction.
        overlap_blocked = False
        for saved in current_assignments:
            if not isinstance(saved, dict):
                continue
            try:
                saved_start, saved_end = int(saved.get("start", -1)), int(saved.get("end", -1))
            except (TypeError, ValueError, OverflowError):
                continue
            if saved_start >= end or saved_end <= start or (saved_start, saved_end) == (start, end):
                continue
            saved_source = _clean(saved.get("source") or "manual").casefold()
            if saved_source not in {"ai", "outsourced"}:
                issues.append(
                    "Passage %s (Chapter %s, %s:%s) overlaps a saved %s assignment at %s:%s. "
                    "Review that existing assignment in Character Studio; workbook import will not overwrite manual or unknown-source assignments."
                    % (pid, chapter_id, start, end, saved_source or "manual", saved_start, saved_end)
                )
                overlap_blocked = True
                continue
            impacted_passages = [
                item for item in current_passages
                if isinstance(item, dict)
                and int(item.get("start", -1)) < saved_end
                and int(item.get("end", -1)) > saved_start
            ]
            impacted_rows = [
                workbook_row_by_id.get(_clean(item.get("passage_id")))
                for item in impacted_passages
                if _key(item.get("kind")) != "narration"
            ]
            blocking_narration = any(
                _key(item.get("kind")) == "narration"
                and _clean(item.get("source")) != "automatic_embedded_quote"
                for item in impacted_passages
            )
            if (
                not impacted_passages
                or blocking_narration
                or not impacted_rows
                or any(not isinstance(item, dict) or not _clean(item.get("GPT Assigned Character")) for item in impacted_rows)
            ):
                issues.append(
                    "Passage %s overlaps a stale AI assignment at %s:%s, but not every impacted dialogue passage "
                    "has a confirmed workbook character. Resolve all affected rows before replacing it."
                    % (pid, saved_start, saved_end)
                )
                overlap_blocked = True
                continue
            speakers_value = saved.get("speakers")
            if not isinstance(speakers_value, (list, tuple)):
                speakers_value = [saved.get("speaker")] if saved.get("speaker") else []
            key = (saved_start, saved_end, saved_source)
            superseded_assignments.setdefault(key, {
                "chapter_id": _clean(chapter_id),
                "start": saved_start,
                "end": saved_end,
                "source": saved_source,
                "speakers": [_clean(value) for value in speakers_value if _clean(value)],
                "text": str(saved.get("text") or ""),
            })
        if overlap_blocked:
            continue

        if not assigned:
            if not old_names:
                passage_excerpt = re.sub(r"\s+", " ", str(current.get("text") or "")).strip()[:120]
                issues.append(
                    "Dialogue passage %s in Chapter %s (%s) has no confirmed character assignment: %s. "
                    "Resolve it with a source-supported Character Register identity or leave the book import blocked; do not guess."
                    % (
                        pid,
                        _clean(current.get("chapter_number")) or _clean(chapter_id),
                        _clean(current.get("chapter_title")),
                        passage_excerpt,
                    )
                )
                continue
            old_identity_keys = set()
            unresolved_old_names = []
            for old_name in old_names:
                old_matches = token_map.get(_key(old_name), set())
                if len(old_matches) != 1:
                    unresolved_old_names.append(old_name)
                else:
                    old_identity_keys.update(old_matches)
            if unresolved_old_names or len(old_identity_keys) != 1:
                issues.append(
                    "Existing assignment for dialogue passage %s is missing, ambiguous or split across characters (%s). "
                    "Resolve it before importing."
                    % (pid, " + ".join(old_names))
                )
                continue
            # A valid saved assignment already covers this dialogue span.
            continue

        if _key(assigned) == "narrator":
            issues.append("Narrator cannot be assigned to dialogue.")
            continue
        matches = token_map.get(_key(assigned), set())
        if len(matches) != 1:
            issues.append("'%s' is missing or ambiguous. Add it to Character Register or resolve its alias." % assigned)
            continue
        identity_key = next(iter(matches))
        if identity_key not in registered_keys:
            issues.append(
                "Speaker '%s' is not listed in Character Register. Add the canonical character and aliases there before importing dialogue."
                % assigned
            )
            continue
        identity = identities[identity_key]
        canonical = identity["canonical_name"]
        valid_identity_tokens = {_key(value) for value in identity.get("tokens", [])}
        if old_names and not all(_key(value) in valid_identity_tokens for value in old_names):
            exact_source = _clean(old.get("source") or "manual").casefold()
            if exact_source not in {"ai", "outsourced"}:
                issues.append(
                    "Passage %s already has a different saved %s speaker (%s). Resolve the manual or unknown-source assignment before import."
                    % (pid, exact_source or "manual", " + ".join(old_names))
                )
                continue
            exact_key = (start, end, exact_source)
            superseded_assignments.setdefault(exact_key, {
                "chapter_id": _clean(chapter_id),
                "start": start,
                "end": end,
                "source": exact_source,
                "speakers": old_names,
                "text": str(old.get("text") or ""),
            })
            old_names = []
        if old_names:
            continue
        raw_confidence = _clean(row.get("GPT Confidence (0–1)"))
        if not raw_confidence:
            issues.append("Passage %s requires an explicit GPT Confidence value from 0.0 to 1.0; blank confidence is not accepted." % pid)
            continue
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError, OverflowError):
            issues.append("Passage %s has an invalid GPT Confidence value; use a number from 0.0 to 1.0." % pid)
            continue
        if not 0.0 <= confidence <= 1.0:
            issues.append("Passage %s GPT Confidence must be between 0.0 and 1.0." % pid)
            continue
        assignments.append({"passage_id":pid,"chapter_id":chapter_id,"start":start,"end":end,
            "text":str(current.get("text") or ""),"speaker":canonical,"series":active_series,"confidence":confidence})
    unique_issues = list(dict.fromkeys(issues))
    return {
        "ready": not unique_issues,
        "issues": unique_issues,
        "characters": planned,
        "assignments": assignments,
        "superseded_assignments": list(superseded_assignments.values()),
        "summary": {
            "matched_characters": sum(x["action"] == "merge" for x in planned),
            "new_characters": sum(x["action"] == "create" for x in planned),
            "aliases_to_merge": sum(len(x.get("aliases_to_add", [])) for x in planned),
            "dialogue_assignments": len(assignments),
            "characters_in_register": len(planned),
            "unresolved_dialogue_passages": sum("no confirmed character assignment" in issue for issue in unique_issues),
            "saved_assignments_replaced": len(superseded_assignments),
        },
    }



def plan_complete_book_character_workbook_import(
    document, *, series, registry_rows, project_characters, current_chapters,
    deleted_registry_rows=None, book_title="",
):
    """Preflight all chapter revisions, identity merges and assignments as one book plan."""
    info = document.get("info") or {}
    if int(document.get("schema_version") or 0) != 2 or _clean(info.get("Export Scope")) != "complete_book":
        raise ValueError("Choose a version 2 complete-book Character Studio workbook.")
    active_series = _clean(series)
    if not active_series or _key(info.get("Series Name")) != _key(active_series):
        raise ValueError("The complete-book workbook series does not match the active book's series.")
    if _clean(book_title) and _key(info.get("Book Title")) != _key(book_title):
        raise ValueError("This workbook belongs to a different book. Select the correct project or export the active book again.")
    references = list(document.get("chapter_references") or [])
    current = list(current_chapters or [])
    if not references or not current:
        raise ValueError("The complete-book workbook or active project has no chapters.")
    current_by_id = {_clean(row.get("chapter_id")): row for row in current if isinstance(row, dict)}
    reference_ids = {_clean(row.get("chapter_id")) for row in references}
    if len(reference_ids) != len(references) or reference_ids != set(current_by_id):
        raise ValueError("The workbook does not contain the exact active book chapter set. Export the complete book again.")
    current_revision = character_workbook_book_revision([
        {
            "chapter_id": row.get("chapter_id"),
            "chapter_number": row.get("chapter_number"),
            "chapter_title": row.get("chapter_title"),
            "chapter_revision": row.get("chapter_revision"),
        }
        for row in current
    ])
    if current_revision != _clean(info.get("Book Revision")):
        raise ValueError("One or more chapters changed after export. Export the complete book again.")
    rows_by_chapter = {chapter_id: [] for chapter_id in reference_ids}
    for row in document.get("dialogue_rows") or []:
        chapter_id = _clean(row.get("Chapter ID"))
        if chapter_id not in rows_by_chapter:
            raise ValueError("A Dialogue Assignment row references an unknown chapter.")
        rows_by_chapter[chapter_id].append(row)

    chapter_plans, issues = [], []
    superseded_assignments = []
    identity_plan_json = None
    identity_plan = []
    for reference in sorted(references, key=lambda item: (int(item["chapter_number"]), item["chapter_id"])):
        chapter_id = _clean(reference.get("chapter_id"))
        active = current_by_id[chapter_id]
        if (int(active.get("chapter_number") or 0) != int(reference["chapter_number"])
            or _clean(active.get("chapter_title")) != _clean(reference.get("chapter_title"))
            or _clean(active.get("chapter_revision")) != _clean(reference.get("chapter_revision"))):
            raise ValueError("Chapter %s changed after export. Export the complete book again." % reference["chapter_number"])
        passages = list(active.get("current_passages") or [])
        assignments = list(active.get("current_assignments") or [])
        exported_passage_count = int(reference.get("passage_count") or 0)
        if len(passages) != exported_passage_count:
            raise ValueError(
                "Chapter %s dialogue/narration segmentation changed after workbook export "
                "(workbook: %s passages; active project: %s). A previously combined turn may now be split "
                "into separate speakers. Export a fresh complete-book workbook before importing; the original "
                "GPT workbook remains unchanged."
                % (reference["chapter_number"], exported_passage_count, len(passages))
            )
        active_text = str(active.get("text") or "")
        if sha256(active_text.encode("utf-8")).hexdigest() != _clean(reference.get("context_sha256")):
            raise ValueError("Chapter %s context does not match the active source text. Export the complete book again." % reference["chapter_number"])
        if len(re.findall(r"\S+", active_text)) != int(reference.get("word_count") or 0):
            raise ValueError("Chapter %s word count does not match the active source text. Export the complete book again." % reference["chapter_number"])
        chapter_info = dict(info)
        chapter_info.update({
            "Chapter ID": chapter_id,
            "Chapter Number": str(reference["chapter_number"]),
            "Chapter Title": _clean(reference.get("chapter_title")),
            "Chapter Revision": _clean(reference.get("chapter_revision")),
            "Passage Count": str(len(passages)),
        })
        chapter_document = dict(document)
        chapter_document.update({
            "info": chapter_info,
            "dialogue_rows": rows_by_chapter[chapter_id],
        })
        plan = plan_character_workbook_import(
            chapter_document,
            series=active_series,
            registry_rows=registry_rows,
            project_characters=project_characters,
            chapter_id=chapter_id,
            chapter_revision=_clean(reference.get("chapter_revision")),
            current_passages=passages,
            current_assignments=assignments,
            deleted_registry_rows=deleted_registry_rows,
            book_title=book_title,
        )
        identity_json = json.dumps(
            plan.get("characters") or [], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        if identity_plan_json is None:
            identity_plan_json = identity_json
            identity_plan = list(plan.get("characters") or [])
        elif identity_plan_json != identity_json:
            issues.append("The character merge plan changed between chapters. Resolve the series identity conflict before importing.")
        issues.extend(plan.get("issues") or [])
        for saved_assignment in plan.get("superseded_assignments") or []:
            item = dict(saved_assignment)
            item["chapter_id"] = chapter_id
            item["chapter_number"] = int(reference["chapter_number"])
            superseded_assignments.append(item)
        chapter_entry = {
            "chapter_id": chapter_id,
            "chapter_number": int(reference["chapter_number"]),
            "chapter_title": _clean(reference.get("chapter_title")),
            "chapter_revision": _clean(reference.get("chapter_revision")),
            "passage_count": int(reference.get("passage_count") or 0),
            "assignments": [],
        }
        for assignment in plan.get("assignments") or []:
            imported = dict(assignment)
            imported["chapter_number"] = int(reference["chapter_number"])
            imported["chapter_revision"] = _clean(reference.get("chapter_revision"))
            chapter_entry["assignments"].append(imported)
        chapter_plans.append(chapter_entry)

    issues = list(dict.fromkeys(issues))
    # A complete-book import is one atomic operation. Do not expose a partial
    # set of accepted dialogue rows when any chapter has an unresolved issue.
    if issues:
        for chapter in chapter_plans:
            chapter["assignments"] = []
    assignments = [
        assignment
        for chapter in chapter_plans
        for assignment in chapter["assignments"]
    ]
    reviewed_chapters = [
        {key: value for key, value in row.items() if key != "assignments"}
        for row in chapter_plans
    ]
    summary = {
        "matched_characters": sum(row.get("action") == "merge" for row in identity_plan),
        "new_characters": sum(row.get("action") == "create" for row in identity_plan),
        "aliases_to_merge": sum(len(row.get("aliases_to_add") or []) for row in identity_plan),
        "dialogue_assignments": len(assignments),
        "characters_in_register": len(identity_plan),
        "chapters": len(chapter_plans),
        "unresolved_dialogue_passages": sum("no confirmed character assignment" in issue for issue in issues),
        "saved_assignments_replaced": len(superseded_assignments),
    }
    return {
        "ready": not issues,
        "issues": issues,
        "scope": "book",
        "book_revision": current_revision,
        "chapters": reviewed_chapters,
        "chapter_assignments": chapter_plans,
        "characters": identity_plan,
        "assignments": assignments,
        "superseded_assignments": superseded_assignments,
        "summary": summary,
    }



def character_workbook_plan_fingerprint(plan: dict) -> str:
    """Digest every identity and assignment decision the user reviewed before commit."""
    if not isinstance(plan, dict):
        raise ValueError("A valid character workbook plan is required.")
    reviewed = {
        key: plan.get(key)
        for key in ("ready", "issues", "scope", "book_revision", "chapters", "chapter_assignments", "characters", "assignments", "superseded_assignments", "summary")
    }
    try:
        encoded = json.dumps(
            reviewed, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("The character workbook plan contains unsupported values.") from exc
    return sha256(encoded).hexdigest()
