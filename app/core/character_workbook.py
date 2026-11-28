"""Versioned Character Studio workbook export/import using only the Python standard library."""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import math
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


def _normalize_workbook_confidence(value):
    """Normalize decimal and percentage-style GPT confidence to the 0..1 scale."""
    raw = _clean(value)
    if not raw:
        raise ValueError("confidence is blank")
    explicit_percent = raw.endswith("%")
    numeric_text = raw[:-1].strip() if explicit_percent else raw
    try:
        confidence = float(numeric_text)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("confidence must be a number from 0 to 1 or a percentage from 0 to 100") from exc
    if not math.isfinite(confidence) or confidence < 0 or confidence > 100:
        raise ValueError("confidence must be finite and within 0 to 1 (or 0 to 100 percent)")
    if explicit_percent or confidence > 1.0:
        confidence /= 100.0
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must normalize to the 0 to 1 range")
    return confidence


def _workbook_speaker_names(row):
    """Read a legacy single speaker or a JSON/comma-separated list of canonical names."""
    raw_json = str(row.get("GPT Assigned Characters (JSON)") or "").strip()
    single = _clean(row.get("GPT Assigned Character"))
    if raw_json:
        if raw_json.startswith("["):
            try:
                values = json.loads(raw_json)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError("GPT Assigned Characters (JSON) must be a valid JSON array.") from exc
        else:
            values = [part.strip() for part in re.split(r"[;,]", raw_json) if part.strip()]
        if not isinstance(values, list):
            raise ValueError("GPT Assigned Characters (JSON) must be a JSON array of character names.")
        names = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("GPT Assigned Characters (JSON) may contain only non-empty character names.")
            name = _clean(value)
            if name.casefold() not in {item.casefold() for item in names}:
                names.append(name)
        if names and single and single.casefold() != names[0].casefold():
            raise ValueError("GPT Assigned Character must match the first name in GPT Assigned Characters (JSON).")
        return names or ([single] if single else [])
    return [single] if single else []


def _workbook_multi_speaker_mode(row, speaker_count):
    if speaker_count <= 1:
        return "single"
    mode = _clean(row.get("GPT Multi-Speaker Mode")).casefold() or "chorus"
    if mode not in {"chorus", "sequential", "alternating"}:
        raise ValueError("GPT Multi-Speaker Mode must be chorus, sequential, or alternating.")
    return mode


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

def _sheet(rows, widths, wrap, protect=False, auto_filter=True):
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
    filt = '<autoFilter ref="A1:%s%d"/>' % (last_col, end_row) if auto_filter and len(rows) > 1 else ""
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
            "For multiple characters speaking the exact same words together, fill GPT Assigned Characters (JSON) with a JSON array of canonical names; use chorus for simultaneous delivery. "
            "For one app-merged passage containing different consecutive speakers, add one row per turn in Dialogue Split Corrections with exact source text and 0-based inclusive/exclusive relative offsets. "
            "Do not edit Passage ID, Dialogue Text, chapter identity, offsets, or revision columns.")
    }
    dialogue_headers = [
        "Passage ID", "Chapter ID", "Chapter Number", "Chapter Title", "Passage Type", "Dialogue Text",
        "GPT Assigned Character", "GPT Confidence (0–1)", "Existing Assignment (Reference)", "Assignment Source (Reference)",
        "Confidence (Reference)", "Start (Reference)", "End (Reference)",
        "Chapter Revision (Reference)", "Evidence / Notes (GPT)",
        "GPT Assigned Characters (JSON)", "GPT Multi-Speaker Mode",
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
            str(row.get("chapter_revision") or info["Chapter Revision"]), "", "", ""
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
    split_headers = [
        "Source Passage ID", "Chapter ID", "Subturn Index", "Start (Relative)", "End (Relative)",
        "Exact Source Text", "GPT Assigned Character", "GPT Assigned Characters (JSON)",
        "GPT Multi-Speaker Mode", "GPT Confidence (0–1)", "Evidence / Notes (GPT)",
    ]
    split_rows = [split_headers]
    for source in metadata.get("dialogue_split_corrections") or []:
        if not isinstance(source, dict):
            continue
        split_rows.append([
            _clean(source.get("Source Passage ID") or source.get("source_passage_id")),
            _clean(source.get("Chapter ID") or source.get("chapter_id") or info["Chapter ID"]),
            source.get("Subturn Index", source.get("subturn_index", "")),
            source.get("Start (Relative)", source.get("start_relative", "")),
            source.get("End (Relative)", source.get("end_relative", "")),
            str(source.get("Exact Source Text") or source.get("exact_source_text") or ""),
            _clean(source.get("GPT Assigned Character") or source.get("gpt_assigned_character")),
            str(source.get("GPT Assigned Characters (JSON)") or source.get("gpt_assigned_characters_json") or ""),
            _clean(source.get("GPT Multi-Speaker Mode") or source.get("gpt_multi_speaker_mode")),
            source.get("GPT Confidence (0–1)", source.get("gpt_confidence", "")),
            str(source.get("Evidence / Notes (GPT)") or source.get("evidence_notes") or ""),
        ])
        if len(split_rows) - 1 > MAX_ROWS:
            raise ValueError("Dialogue Split Corrections exceeds the 50,000-row workbook limit.")
    sheets = [
        ("Dialogue Assignment", dialogue, [38,38,14,32,16,72,34,18,34,22,18,14,14,42,46,46,22], {6,8,9,14,15,16}),
        ("Character Register", characters, [34] + [24] * ALIAS_COLUMNS + [26,48], set(range(1, ALIAS_COLUMNS + 4))),
        ("Chapter Context", context, [14,14,32,100], {4}),
        ("Workbook Info", workbook_info_rows, [28,110,4,36,32,36,28], {2,4,5,6,7}),
        ("Dialogue Split Corrections", split_rows, [30,26,14,18,18,72,34,48,22,18,48], {6,8,11}),
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


def complete_book_gpt_prompt() -> str:
    """Return the versioned task prompt embedded in every complete-book workbook."""
    return "\n".join([
        "You are the careful character-attribution assistant completing the attached Ryu Audiobook COMPLETE-BOOK Character Studio workbook. Return a completed .xlsx workbook file, not only a written report.",
        "",
        "SOURCE FIRST — READ THE WHOLE BOOK",
        "1. Read every row in Chapter Context. Reassemble each chapter by Chapter ID and ascending Context Part; do not skip later chunks or chapters.",
        "2. Read Source Correction History and treat its entries as examples of corrections already explicitly accepted by the user. Use them to understand recurring transcription/wording issues, but only apply a similar correction when the current source context independently supports it; never copy an earlier corrected line blindly.",
        "3. Read Workbook Info, all Character Register rows, and the complete Series Character Reference. Build a book-wide cast and alias map before assigning any dialogue.",
        "4. Use the workbook's chapter text as the primary source. Use an additionally attached original novel only to clarify text that is genuinely missing or corrupted; never invent missing source wording.",
        "",
        "CRITICAL MEANING OF REVIEW REQUIRED",
        "A REVIEW REQUIRED note means the app could not safely carry an old GPT answer onto a changed or newly split passage. It does NOT mean the speaker is unknowable, and it is NOT a reason to leave the row blank without investigation.",
        "Re-identify each such passage from the full chapter scene and the wider book context. Newly split dialogue rows are independent turns and must each receive their own speaker decision. Never copy the previous row's speaker merely because the rows are adjacent.",
        "",
        "HOW TO IDENTIFY THE SPEAKER",
        "For every row whose Passage Type is Dialogue, identify the person or source actually uttering those exact words — not the person being addressed, named, discussed, or quoted.",
        "Use evidence in this order: explicit speech tags; nearby action beats or narration that identify who spoke; the exchange's question/answer and turn-taking structure; established point of view and character voice; earlier and later scenes that confirm the same speaker.",
        "Read the sentences before and after the passage. A name inside a line (for example, 'Mira, listen') may identify the addressee, not the speaker. Do not assign a speaker from name proximity alone.",
        "Do not leave a row blank merely because it has no explicit 'X said' tag. Use the complete scene, conversational sequence, and consistent identities to make a well-supported contextual attribution when there is one clear answer.",
        "Treat each Dialogue Assignment row as one app-defined source passage. If two adjacent rows are separate turns, analyze them separately even when the old workbook had them combined.",
        "If one row itself contains two or more distinct turns by different speakers, do not force one name onto it and do not split, duplicate, delete, or rewrite the row. Leave its assignment blank and write 'STRUCTURAL SPLIT REQUIRED' in Evidence / Notes (GPT), identifying the exact sub-turns and the likely speaker of each for a later app-side segmentation correction.",
        "Distinguish the narrator's perspective from a character's spoken voice. First-person narration, third-person limited narration, free-indirect style, internal thought, memory, and a character's perception of events remain Narrator unless the source clearly presents aloud-spoken words as a dialogue turn. A viewpoint character is not automatically the speaker of the narration.",
        "Quotation marks alone do not prove that a passage is dialogue. A quoted word, nickname, title, idiom, remembered phrase, scare quote, or phrase embedded grammatically inside narration remains Narrator when it is being mentioned or described rather than spoken aloud. A verbatim quotation reported in narration is dialogue only when the scene clearly represents an actual utterance and identifies the utterer from a speech tag, action beat, or unmistakable turn-taking context.",
        "For an actual spoken quotation embedded in a longer narrative sentence, use the app's current Passage Type and exact passage boundaries; do not silently reclassify an entire narration passage as dialogue or turn narrative framing into a speaker assignment. Explain any mismatch for human review.",
        "Do not classify thoughts, emphasized words, quoted terms, or quotations embedded in narration as spoken dialogue. Narration rows remain Narrator; do not assign a character to them or change Passage Type.",
        "",
        "CHARACTER IDENTITY AND REGISTER",
        "For each identifiable speaker, use the exact canonical Full Name from Character Register. If the same person already exists in Series Character Reference, reuse that canonical identity and preserve its known aliases; do not create a duplicate.",
        "",
        "RESERVED SYSTEM ROLE — THIRD PERSON",
        "Use the exact canonical speaker value 'Third Person' only when the text clearly contains an actual spoken dialogue turn by an unidentified background bystander, standby, extra, or crowd member, and no reliable personal name or consistently identifiable recurring role can be established from whole-book context.",
        "Do not invent one-off names such as 'Unnamed Male Onlooker 1' or 'Unnamed Female Student 2' for anonymous background speakers. Use 'Third Person' for those unknown live speakers instead. A recurring, text-supported role such as a consistently identifiable classroom teacher or desk clerk may retain its stable role identity.",
        "'Third Person' is a reserved application role, not a real character identity: do not add it to Character Register, do not give it aliases or an age/version, and do not assign it a character-specific voice. The application routes it to the user's global Third Person voice profile and marks it for later user identification.",
        "Never use 'Third Person' for narration, internal thoughts, free-indirect narration, reported or remembered quotations, quoted references, sleep sounds, sound effects, or any passage that is not an actual spoken turn. Use Narrator for narration and reported/internal material.",
        "When assigning 'Third Person', record in Evidence / Notes (GPT): 'Unidentified background speaker; routed to Third Person fallback; user identification required.' Do not guess a personal name.",
        "If a real character appears in this book but is missing from Character Register, add a row with a source-supported canonical name, confirmed aliases, useful notes, and Included in This Book? = YES. Do not add characters merely mentioned in metadata or chapter titles.",
        "A nickname, title, surname, honorific, or spelling variant is an alias only when the book confirms it refers to the same person. Do not turn an addressee or descriptive phrase into a character.",
        "If the source gives no personal name but consistently identifies a speaker by a role (for example, an unnamed classroom teacher), use a clear role identity such as 'Unnamed Classroom Teacher'. State in Character Notes that this is an unnamed role, not a supplied personal name, and reuse it only when the text supports the same individual.",
        "Use source-supported collective or non-human identities only when the text clearly identifies that speaker. For a true group/chorus, create one clear collective identity rather than guessing an individual.",
        "Keep younger/older or otherwise distinct voice identities separate only when the source supports genuinely different identity versions. Use Version / Age Variant and preserve the base identity; do not merge distinct versions.",
        "Keep rows marked Included in This Book? = NO as NO. Do not remove existing Character Register identities, aliases, notes, or future-volume entries.",
        "",
        "FILL THE WORKBOOK — THE DIALOGUE ASSIGNMENT SHEET IS THE REQUIRED OUTPUT",
        "A populated Character Register is only a list of character identities. It does NOT assign any dialogue. You must fill the GPT Assigned Character cell (and, for true same-word multi-speaker delivery, GPT Assigned Characters (JSON)) on the corresponding Dialogue Assignment row itself. Do not return a workbook in which Character Register is populated but Dialogue Assignment speaker cells are blank unless the source genuinely cannot identify those speakers.",
        "Before returning the .xlsx, count the Dialogue Assignment rows whose Passage Type is Dialogue, the rows you filled with a speaker, and the rows you deliberately left unresolved. State those counts in your completion summary. Do not claim speaker assignments were completed merely because the Character Register was filled.",
        "For every Dialogue row with a supported speaker, fill GPT Assigned Character with the first canonical Full Name, GPT Assigned Characters (JSON) with a JSON array of every character who speaks those exact same words, GPT Multi-Speaker Mode when more than one character is assigned, GPT Confidence (0–1) with a numeric value from 0.75 to 1.00, and Evidence / Notes (GPT) with a concise source-based reason.",
        "For an actual but unidentified background speaker, use 'Third Person' exactly as defined above. It is valid in the speaker fields without being listed in Character Register; do not create a fake character record for it.",
        'Use one JSON array cell, for example ["Rias Gremory", "Akeno Himejima"]; do not create one column per character. JSON is preferred to comma-separated names because it safely preserves commas inside names. For simultaneous same-word delivery use chorus (the default); use sequential only when the exact same line should be repeated once per character; use alternating only when specifically supported by the scene.',
        "A chorus is one dialogue passage with multiple speakers, not multiple split corrections. Assign all clearly identified simultaneous speakers to the same row.",
        "Calibrate confidence: 0.95–1.00 for explicit attribution; 0.85–0.94 for clear action-beat or strong scene evidence; 0.75–0.84 for a strong contextual inference with no credible competing speaker. Do not use low confidence to disguise a guess.",
        "If whole-book context still cannot establish a defensible speaker, leave speaker cells blank and explain why. Do not invent a person, guess from an honorific, or use Narrator to bypass unresolved speech. Such rows require human review and block import.",
        "Evidence should identify the chapter and actual clue (speech tag, action beat, response pattern, or prior identity reference). Distinguish direct evidence from contextual inference.",
        "Do not overwrite a clearly confirmed existing manual assignment. If workbook evidence and a manual assignment conflict, explain the conflict and leave the row for human review.",
        "",
        "PROPOSE LINE-BY-LINE SOURCE TEXT CORRECTIONS",
        "Read every Dialogue Assignment row against its surrounding Chapter Context. If the original Dialogue Text contains an evident transcription, OCR, punctuation, missing-word, duplication, or wording error, you may propose corrected source wording in the separate 'GPT Proposed Source Text' column and explain the reason in 'GPT Text Correction Reason'. You may propose corrections for dialogue lines and for Narrator paragraphs; do not limit review to dialogue.",
        "The proposed text may differ from the original Dialogue Text, but preserve the source meaning, character identity, point of view, scene facts, authorial tone, and intended dialogue. Do not invent events, speakers, names, or motivations. Prefer minimal corrections that solve the identified problem; do not rewrite merely for stylistic preference.",
        "Never change the original Dialogue Text or any Passage ID, Chapter ID, Passage Type, revision, or reference offset. The two GPT proposal columns are the only place to put replacement wording. Leave both proposal columns blank when no correction is needed. Whenever proposed text is supplied, provide a specific reason. The application will show each proposed change and apply it to the book only after the user explicitly confirms the import.",
        "Do not change the speaker or character identity just because wording is corrected. Keep GPT Assigned Character / JSON tied to the same actual speaker. If the correction changes who is speaking or where a turn begins or ends, use Dialogue Split Corrections only when the original parent boundaries still support exact relative spans; otherwise leave a structural review note rather than guessing.",
        "Do not combine a whole-passage text replacement and Dialogue Split Corrections for the same parent passage. Resolve the wording proposal first, then export a fresh workbook before proposing structural subturns.",
        "",
        "CORRECT A PASSAGE THAT THE APP MERGED FROM DIFFERENT SPEAKERS",
        "If one Dialogue Assignment row contains two or more consecutive turns by different speakers, do not edit or split the original row. Add one row per turn to the separate Dialogue Split Corrections sheet.",
        "Each correction row repeats the parent Source Passage ID and Chapter ID; uses Subturn Index 1, 2, 3... in source order; provides 0-based Start (Relative) inclusive and End (Relative) exclusive offsets measured from the beginning of the parent's Dialogue Text; and copies Exact Source Text character-for-character from that slice, including source quote markers.",
        "Subturn ranges must be ordered, non-overlapping, inside the parent text, and cover each spoken turn. Leave narration or attribution prose between turns outside the ranges so it remains narration. Give every subturn its canonical speaker(s), mode, numeric confidence and evidence. A structural split requires at least two subturn rows.",
        "Use multiple speakers on one correction row only when those characters utter the exact same words simultaneously. Different consecutive turns require separate correction rows. Do not invent a split or guess a speaker.",
        "Do not use Dialogue Split Corrections for a correctly segmented single turn or a same-word chorus; use the multi-speaker JSON cell instead.",
        "",
        "DO NOT DAMAGE THE SOURCE OR WORKBOOK",
        "Do not change Passage ID, Chapter ID, chapter number/title/revision, Passage Type, Dialogue Text, Start/End offsets, Chapter Register, Chapter Context, Series Character Reference, Speaker Roles, Source Correction History, Workbook Info, or existing dialogue rows.",
        "Do not add, delete, duplicate, merge, split, reorder, or rewrite Dialogue Assignment rows. The app applies validated subturn corrections from Dialogue Split Corrections while preserving the original source passage.",
        "Only fill GPT answer columns, add source-supported Character Register identities, and add validated Dialogue Split Corrections rows. Preserve all other sheets, rows and references.",
        "Save the completed workbook as a NEW .xlsx copy. Never overwrite the original exported or refreshed workbook.",
        "",
        "FINAL CHECK BEFORE RETURNING THE FILE",
        "Check every Dialogue row across every chapter, especially REVIEW REQUIRED rows and adjacent newly split turns. Confirm that each assigned name exists as a canonical Character Register identity or its confirmed alias, except the reserved 'Third Person' placeholder; each confidence is numeric and within range; narration remains Narrator; every proposed wording correction has a clear reason; and no original reference columns or passage rows were changed.",
        "Return the completed .xlsx file and a short summary with: dialogue rows assigned; unresolved rows (with Passage IDs and reasons); new Character Register identities; aliases added; structural-split issues; and any manual-assignment conflicts. Do not claim full completion when unresolved rows remain.",
    ])


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
        "GPT Assigned Characters (JSON)", "GPT Multi-Speaker Mode",
        "GPT Proposed Source Text", "GPT Text Correction Reason",
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
        gpt_speakers = row.get("gpt_assigned_characters") or row.get("GPT Assigned Characters (JSON)") or []
        if isinstance(gpt_speakers, str):
            try:
                gpt_speakers = json.loads(gpt_speakers) if gpt_speakers.strip().startswith("[") else [part.strip() for part in re.split(r"[;,]", gpt_speakers) if part.strip()]
            except (TypeError, ValueError, json.JSONDecodeError):
                gpt_speakers = [part.strip() for part in re.split(r"[;,]", gpt_speakers) if part.strip()]
        if not isinstance(gpt_speakers, (list, tuple)):
            gpt_speakers = []
        dialogue.append([
            passage_id, chapter_id, chapter["chapter_number"], chapter["chapter_title"],
            "Narration" if narration else "Dialogue", text,
            "Narrator" if narration else gpt_assigned, gpt_confidence if not narration else "",
            " + ".join(str(value) for value in speakers if str(value or "").strip()),
            str(row.get("assignment_source") or row.get("source") or ""),
            row.get("confidence") if row.get("confidence") is not None else "",
            start, end, chapter["chapter_revision"], "" if narration else gpt_evidence,
            json.dumps(list(dict.fromkeys(_clean(value) for value in gpt_speakers if _clean(value))), ensure_ascii=False)
            if not narration and gpt_speakers else "",
            _clean(row.get("gpt_multi_speaker_mode") or row.get("GPT Multi-Speaker Mode")),
            str(row.get("gpt_proposed_source_text") or row.get("GPT Proposed Source Text") or ""),
            str(row.get("gpt_text_correction_reason") or row.get("GPT Text Correction Reason") or ""),
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

    source_correction_rows = [[
        "Chapter ID", "Chapter Number", "Chapter Title",
        "Source Passage ID (Before Correction)", "Original Source Text",
        "User-Approved Source Text", "Correction Reason", "Applied At",
    ]]
    for record in metadata.get("source_correction_history") or []:
        if not isinstance(record, dict):
            continue
        source_value = str(record.get("source_text") or "")
        approved_value = str(record.get("approved_text") or "")
        if not source_value or not approved_value or source_value == approved_value:
            continue
        source_correction_rows.append([
            _clean(record.get("chapter_id")),
            record.get("chapter_number", ""),
            _clean(record.get("chapter_title")),
            _clean(record.get("passage_id")),
            source_value,
            approved_value,
            str(record.get("reason") or ""),
            _clean(record.get("applied_at")),
        ])
        if len(source_correction_rows) - 1 > MAX_ROWS:
            raise ValueError("Source Correction History exceeds the 50,000-row workbook limit.")

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
        ["GPT Prompt Version", "2.3"],
        ["Instructions",
         "This is a COMPLETE-BOOK workbook. Start with the GPT Prompt tab: it contains the full ready-to-copy task prompt and explains how to analyze every chapter, resolve newly split dialogue turns, assign canonical identities, calibrate confidence, and preserve source references. " 
         "A REVIEW REQUIRED note means an old answer was not copied across a changed passage; it does not mean the speaker is unknowable. Use the full Chapter Context to re-identify each changed turn independently. " 
         "Use GPT Assigned Characters (JSON) for multiple characters speaking the same words together. Use Dialogue Split Corrections for a genuinely merged passage containing different consecutive turns. Use GPT Proposed Source Text and GPT Text Correction Reason for dialogue-line or Narrator-paragraph wording corrections; the app applies proposals only after explicit user confirmation. Use the reserved Third Person identity only for actual speech by an unidentified background speaker, never for narration or reported speech. Use Source Correction History as read-only examples of corrections the user already accepted; preserve it and do not reuse an old correction unless the current passage independently supports the same fix. Do not alter original passage rows or reference columns; return a new workbook copy. Unresolved speakers must remain explicit and will block import until confirmed."],
    ]

    split_headers = [
        "Source Passage ID", "Chapter ID", "Subturn Index", "Start (Relative)", "End (Relative)",
        "Exact Source Text", "GPT Assigned Character", "GPT Assigned Characters (JSON)",
        "GPT Multi-Speaker Mode", "GPT Confidence (0–1)", "Evidence / Notes (GPT)",
    ]
    split_rows = [split_headers]
    for source in metadata.get("dialogue_split_corrections") or []:
        if not isinstance(source, dict):
            continue
        split_rows.append([
            _clean(source.get("Source Passage ID") or source.get("source_passage_id")),
            _clean(source.get("Chapter ID") or source.get("chapter_id")),
            source.get("Subturn Index", source.get("subturn_index", "")),
            source.get("Start (Relative)", source.get("start_relative", "")),
            source.get("End (Relative)", source.get("end_relative", "")),
            str(source.get("Exact Source Text") or source.get("exact_source_text") or ""),
            _clean(source.get("GPT Assigned Character") or source.get("gpt_assigned_character")),
            str(source.get("GPT Assigned Characters (JSON)") or source.get("gpt_assigned_characters_json") or ""),
            _clean(source.get("GPT Multi-Speaker Mode") or source.get("multi_speaker_mode")),
            source.get("GPT Confidence (0–1)", source.get("gpt_confidence", "")),
            _clean(source.get("Evidence / Notes (GPT)") or source.get("gpt_evidence")),
        ])

    gpt_prompt_rows = [
        ["COPY THIS PROMPT INTO CHATGPT"],
        ["Upload this entire workbook to ChatGPT, then copy the prompt between BEGIN PROMPT and END PROMPT below. Ask GPT to return a completed .xlsx copy."],
        ["----- BEGIN PROMPT -----"],
        *[[line] for line in complete_book_gpt_prompt().splitlines()],
        ["----- END PROMPT -----"],
    ]

    sheets = [
        ("GPT Prompt", gpt_prompt_rows, [120], {1}),
        ("Dialogue Assignment", dialogue, [38,38,14,32,16,72,34,18,34,22,18,14,14,42,46,58,24,72,64], {6,8,9,14,15,16,17,18,19}),
        ("Dialogue Split Corrections", split_rows, [38,38,14,18,18,72,34,58,24,20,70], set(range(1,12))),
        ("Character Register", characters, [34] + [24] * alias_column_count + [26,48,24], set(range(1, alias_column_count + 5))),
        ("Speaker Roles", [
            ["Role Type", "Canonical Value", "Use When", "Do Not Use When", "Application Routing", "Follow-up"],
            ["Reserved unidentified speaker", "Third Person", "An actual spoken dialogue turn by an unidentified background bystander, standby, extra, or crowd member when no reliable personal or recurring role identity can be established.", "Narration, internal thought, reported or remembered quotations, quoted references, sleep sounds, or sound effects.", "Uses the user's global Third Person fallback voice; it is not a Character Register member and has no character-specific voice.", "User may replace the placeholder with a confirmed identity later."],
            ["Narration", "Narrator", "Narrative paragraphs, internal thought, free-indirect style, and reported speech that is not a live dialogue turn.", "A person actively speaking words as a dialogue turn.", "Uses the book/series narrator voice.", "No character identity is created."],
            ["Known speaker", "Canonical Character Register name", "The speaker is identified by source text or clear whole-book context.", "Do not infer the speaker from an addressee's name or proximity alone.", "Uses the saved character voice profile when one is assigned.", "Preserve canonical name and aliases."],
        ], [30,26,72,66,70,56], set(range(1,7))),
        ("Source Correction History", source_correction_rows, [24,14,32,38,72,72,72,30], set(range(1,9))),
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
                    protect=name in {"Chapter Register", "Chapter Context", "Series Character Reference", "Speaker Roles", "Source Correction History", "Workbook Info"},
                    auto_filter=name != "GPT Prompt",
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
                "assigned_speakers": _workbook_speaker_names(row),
                "multi_speaker_mode": _clean(row.get("GPT Multi-Speaker Mode")),
                "proposed_source_text": str(row.get("GPT Proposed Source Text") or ""),
                "text_correction_reason": str(row.get("GPT Text Correction Reason") or ""),
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
            exact_old = [old for old in exact if len(exact) == 1]
            if len(exact_old) == 1:
                row["gpt_proposed_source_text"] = exact_old[0].get("proposed_source_text") or ""
                row["gpt_text_correction_reason"] = exact_old[0].get("text_correction_reason") or ""
            refreshed_passages.append(row)
            continue

        exact_dialogue = [old for old in exact if old["kind"] == "dialogue"]
        if len(exact_dialogue) == 1 and len(exact) == 1:
            old = exact_dialogue[0]
            row["gpt_assigned_character"] = old["assigned"]
            row["gpt_confidence"] = old["confidence"]
            row["gpt_evidence"] = old["evidence"]
            row["gpt_assigned_characters"] = list(old.get("assigned_speakers") or ([old["assigned"]] if old["assigned"] else []))
            row["gpt_multi_speaker_mode"] = old.get("multi_speaker_mode") or ""
            row["gpt_proposed_source_text"] = old.get("proposed_source_text") or ""
            row["gpt_text_correction_reason"] = old.get("text_correction_reason") or ""
            exact_rows_carried += 1
            if old["assigned"] or old.get("assigned_speakers"):
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
                + ". The previous speaker was not copied because the old passage may have split or changed boundaries. "
                "Open the GPT Prompt sheet and re-identify this turn from the full Chapter Context. Treat this row independently; do not inherit the previous row speaker without source evidence."
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
    exact_refreshed_ids = {
        _clean(row.get("passage_id")): row
        for row in refreshed_passages
        if isinstance(row, dict) and _clean(row.get("passage_id"))
    }
    safe_split_corrections = []
    for correction in (document.get("dialogue_split_corrections") or []):
        if not isinstance(correction, dict):
            continue
        parent_id = _clean(correction.get("Source Passage ID"))
        parent = exact_refreshed_ids.get(parent_id)
        if not parent or _clean(correction.get("Chapter ID")) != _clean(parent.get("chapter_id")):
            continue
        try:
            rel_start = int(correction.get("Start (Relative)"))
            rel_end = int(correction.get("End (Relative)"))
        except (TypeError, ValueError, OverflowError):
            continue
        parent_text = str(parent.get("text") or "")
        if 0 <= rel_start < rel_end <= len(parent_text) and str(correction.get("Exact Source Text") or "") == parent_text[rel_start:rel_end]:
            safe_split_corrections.append(dict(correction))
    refreshed_metadata["dialogue_split_corrections"] = safe_split_corrections
    refreshed_metadata["source_correction_history"] = list(document.get("source_correction_history") or [])
    unresolved_dialogue = 0
    for row in refreshed_passages:
        if _key(row.get("kind")) == "narration":
            continue
        assigned = _clean(row.get("gpt_assigned_character"))
        saved_speakers = row.get("existing_speakers") or row.get("speakers") or []
        if isinstance(saved_speakers, str):
            saved_speakers = [saved_speakers]
        has_saved_identity = any(_clean(value) for value in saved_speakers)
        if not assigned and not row.get("gpt_assigned_characters") and not has_saved_identity:
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
            for optional_sheet in ("Series Character Reference", "Chapter Register", "Dialogue Split Corrections", "Speaker Roles", "Source Correction History"):
                if optional_sheet in targets:
                    sheets[optional_sheet] = _read_sheet(z, targets[optional_sheet], shared)
            split_rows = _records(sheets.get("Dialogue Split Corrections", []))
            if len(split_rows) > MAX_ROWS:
                raise ValueError("Dialogue Split Corrections exceeds the 50,000-row workbook limit.")
            if split_rows:
                split_headers = {_clean(value) for value in sheets["Dialogue Split Corrections"][0]}
                required_split_headers = {
                    "Source Passage ID", "Chapter ID", "Subturn Index", "Start (Relative)",
                    "End (Relative)", "Exact Source Text", "GPT Assigned Character",
                    "GPT Confidence (0–1)",
                }
                if not required_split_headers.issubset(split_headers):
                    raise ValueError("Dialogue Split Corrections is missing required source or speaker columns.")
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
        "dialogue_split_corrections": _records(sheets.get("Dialogue Split Corrections", [])),
        "speaker_roles": _records(sheets.get("Speaker Roles", [])),
        "source_correction_history": _records(sheets.get("Source Correction History", [])),
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
        if not name or _key(name) in {"narrator", "third person"}: continue
        version = _clean(row.get("identity_variant"))
        key = _key(name) + "|" + _key(version)
        entry = existing.setdefault(key, {"canonical_name":name, "identity_variant":version,
            "identity_base_name":_clean(row.get("identity_base_name")) or name, "aliases":[],
            "library_id":"","voice_name":"","project_voice_profile":"","project_cast_count":0})
        aliases = row.get("aliases") or []
        if isinstance(aliases, str): aliases = [aliases]
        for alias in aliases if isinstance(aliases,(list,tuple)) else []:
            alias = _clean(alias)
            if alias and _key(alias) not in {"narrator", "third person"} and _key(alias) != _key(name) and _key(alias) not in {_key(x) for x in entry["aliases"]}:
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
        if _key(name) == "third person":
            issues.append("'Third Person' is a reserved fallback speaker role and must not be added to Character Register.")
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
            if _key(alias) == "third person":
                issues.append("'Third Person' is a reserved fallback speaker role and cannot be used as a character alias.")
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
    assignments_by_span = {}
    for saved in current_assignments:
        if not isinstance(saved, dict):
            continue
        try:
            span_key = (int(saved.get("start", -1)), int(saved.get("end", -1)))
        except (TypeError, ValueError, OverflowError):
            continue
        assignments_by_span.setdefault(span_key, []).append(saved)

    def exact_saved_assignment_for_passage(passage):
        """Resolve one current assignment using passage identity, revision, offsets and exact text."""
        if not isinstance(passage, dict):
            return None
        try:
            span_key = (int(passage.get("start", -1)), int(passage.get("end", -1)))
        except (TypeError, ValueError, OverflowError):
            return None
        passage_id = _clean(passage.get("passage_id"))
        expected_revision = _clean(passage.get("chapter_revision")) or _clean(chapter_revision)
        expected_text = str(passage.get("text") or "")
        matches = []
        for saved in assignments_by_span.get(span_key, []):
            saved_id = _clean(saved.get("passage_id"))
            saved_revision = _clean(saved.get("chapter_revision"))
            saved_text = str(saved.get("text") or "")
            if saved_id and saved_id != passage_id:
                # A manually confirmed assignment can survive a Passage ID
                # regeneration only when its exact original text and absolute
                # offsets still identify this unique current source span.
                saved_source = _clean(saved.get("source") or "manual").casefold()
                if saved_source != "manual" or saved_text != expected_text:
                    continue
            if saved_revision and expected_revision and saved_revision != expected_revision:
                continue
            if saved_text and saved_text != expected_text:
                continue
            matches.append(saved)
        return matches[0] if len(matches) == 1 else None

    assignments, seen = [], set()
    superseded_assignments = {}
    workbook_rows = [row for row in (document.get("dialogue_rows") or []) if isinstance(row, dict)]
    workbook_row_by_id = {}
    workbook_row_by_source_id = {}
    workbook_source_to_current = {}
    passage_rebases = []
    passage_mappings = []
    passage_reclassifications = []
    text_corrections = []
    unmatched_workbook_rows = []
    active_chapter_text = str(document.get("_active_chapter_text") or "")
    stale_assignment_reviewed = set()

    def stale_ai_assignment_source_matches(start, end, source):
        """Require every duplicate AI record for a stale span to match the active chapter source."""
        if not active_chapter_text or start < 0 or end <= start or end > len(active_chapter_text):
            return False
        exact_source = active_chapter_text[start:end]
        candidates = [
            row for row in assignments_by_span.get((start, end), [])
            if _clean(row.get("source") or "manual").casefold() == source
        ]
        if not candidates:
            return False
        for candidate in candidates:
            saved_text = str(candidate.get("text") or "")
            if saved_text and saved_text != exact_source:
                return False
            saved_revision = _clean(candidate.get("chapter_revision"))
            if not saved_text and saved_revision and _clean(chapter_revision) and saved_revision != _clean(chapter_revision):
                return False
        return True

    def claim_stale_assignment_review(start, end, source):
        """Review one stale span once even when several current passages overlap it."""
        key = (start, end, source)
        if key in stale_assignment_reviewed:
            return False
        stale_assignment_reviewed.add(key)
        return True

    # Passage IDs are generated from the detected dialogue/narration structure.
    # A classifier update can legitimately replace an ID without changing the
    # chapter text. Rebase only when the workbook's chapter, full source text,
    # and absolute source offsets identify exactly one current passage.
    current_by_span_text = {}
    for passage in current_passages:
        if not isinstance(passage, dict):
            continue
        try:
            passage_start = int(passage.get("start", -1))
            passage_end = int(passage.get("end", -1))
        except (TypeError, ValueError, OverflowError):
            continue
        passage_text = str(passage.get("text") or "")
        if passage_start < 0 or passage_end <= passage_start or not passage_text:
            continue
        if active_chapter_text and active_chapter_text[passage_start:passage_end] != passage_text:
            continue
        current_by_span_text.setdefault((passage_start, passage_end, passage_text), []).append(passage)

    def workbook_reference_span(row):
        try:
            start_value = row.get("Start (Reference)")
            end_value = row.get("End (Reference)")
            if isinstance(start_value, bool) or isinstance(end_value, bool):
                raise ValueError("Boolean source offset")
            raw_start = float(start_value) if start_value not in (None, "") else -1
            raw_end = float(end_value) if end_value not in (None, "") else -1
            start_ref, end_ref = int(raw_start), int(raw_end)
            if raw_start != start_ref or raw_end != end_ref:
                raise ValueError("Non-integer source offset")
            return start_ref, end_ref
        except (TypeError, ValueError, OverflowError):
            return -1, -1

    def resolve_workbook_passage(row):
        source_id = _clean(row.get("Passage ID"))
        row_chapter_id = _clean(row.get("Chapter ID"))
        row_revision = _clean(row.get("Chapter Revision (Reference)"))
        start_ref, end_ref = workbook_reference_span(row)
        source_text = str(row.get("Dialogue Text") or "")
        if row_chapter_id != _clean(chapter_id):
            return None, "belongs to a different chapter"
        if row_revision != _clean(chapter_revision):
            return None, "references a different chapter revision"
        if start_ref < 0 or end_ref <= start_ref or not source_text:
            return None, "has invalid source text or absolute offsets"
        if active_chapter_text and active_chapter_text[start_ref:end_ref] != source_text:
            return None, "does not match the active chapter's exact source text at its recorded offsets"

        current = by_id.get(source_id)
        if current is not None:
            try:
                exact_current = (
                    int(current.get("start", -1)) == start_ref
                    and int(current.get("end", -1)) == end_ref
                    and str(current.get("text") or "") == source_text
                    and _clean(current.get("chapter_id") or chapter_id) == _clean(chapter_id)
                )
            except (TypeError, ValueError, OverflowError):
                exact_current = False
            if exact_current:
                return current, ""
            return None, "has a current Passage ID but its source text or offsets do not match"

        candidates = current_by_span_text.get((start_ref, end_ref, source_text), [])
        candidates = [
            candidate for candidate in candidates
            if _clean(candidate.get("chapter_id") or chapter_id) == _clean(chapter_id)
        ]
        if len(candidates) == 1:
            current = candidates[0]
            current_id = _clean(current.get("passage_id"))
            if not current_id:
                return None, "matches a source span that has no stable current Passage ID"
            return current, "rebased"
        if len(candidates) > 1:
            return None, "matches more than one current passage at the same source offsets; automatic rebasing is ambiguous"
        return None, "no current passage has the same exact source text and offsets"

    seen_source_ids = set()
    for row in workbook_rows:
        source_id = _clean(row.get("Passage ID"))
        if source_id and source_id in seen_source_ids:
            issues.append("Duplicate workbook Passage ID %s." % source_id)
            unmatched_workbook_rows.append(row)
            continue
        if source_id:
            seen_source_ids.add(source_id)
        current, resolution = resolve_workbook_passage(row)
        if current is None:
            unmatched_workbook_rows.append(row)
            try:
                assigned_names = _workbook_speaker_names(row)
            except ValueError:
                assigned_names = []
            has_source_text_proposal = bool(
                str(row.get("GPT Proposed Source Text") or "").strip()
                or str(row.get("GPT Text Correction Reason") or "").strip()
            )
            if _clean(row.get("Passage Type")).casefold() == "dialogue" or assigned_names or has_source_text_proposal:
                issues.append(
                    "Workbook passage %s could not be safely matched to the active chapter (%s). "
                    "Its GPT speaker assignment and/or source-text correction was not applied; review the current source passage(s) instead."
                    % (source_id or "(missing ID)", resolution)
                )
            continue
        current_id = _clean(current.get("passage_id"))
        if current_id in workbook_row_by_id:
            issues.append(
                "More than one workbook row maps to current passage %s. Resolve the duplicate source span before importing."
                % current_id
            )
            unmatched_workbook_rows.append(row)
            continue
        workbook_row_by_id[current_id] = row
        if source_id:
            workbook_row_by_source_id[source_id] = row
            workbook_source_to_current[source_id] = current_id
            passage_mappings.append({
                "workbook_passage_id": source_id,
                "current_passage_id": current_id,
                "chapter_id": _clean(chapter_id),
                "start": int(current.get("start", -1)),
                "end": int(current.get("end", -1)),
                "text": str(current.get("text") or ""),
            })
        if resolution == "rebased":
            passage_rebases.append({
                "workbook_passage_id": source_id,
                "current_passage_id": current_id,
                "chapter_id": _clean(chapter_id),
                "start": int(current.get("start", -1)),
                "end": int(current.get("end", -1)),
            })

    # A current dialogue passage may be absent from an older workbook after
    # resegmentation. Preserve an exact manual assignment, but never silently
    # accept an unassigned new passage or a stale AI-only assignment.
    for passage in current_passages:
        if not isinstance(passage, dict):
            continue
        current_id = _clean(passage.get("passage_id"))
        if not current_id or current_id in workbook_row_by_id or _key(passage.get("kind")) == "narration":
            continue
        saved = exact_saved_assignment_for_passage(passage)
        saved_speakers = saved.get("speakers") if isinstance(saved, dict) else []
        if not isinstance(saved_speakers, (list, tuple)):
            saved_speakers = [saved.get("speaker")] if isinstance(saved, dict) and saved.get("speaker") else []
        saved_source = _clean(saved.get("source") or "manual").casefold() if isinstance(saved, dict) else ""
        if saved and saved_source == "manual" and any(_clean(value) for value in saved_speakers):
            continue
        excerpt = re.sub(r"\\s+", " ", str(passage.get("text") or "")).strip()[:120]
        issues.append(
            "Current dialogue passage %s is missing from the workbook and has no exact saved manual assignment: %s. "
            "Review this current passage before importing."
            % (current_id, excerpt)
        )

    def resolve_workbook_names(raw_row, label):
        try:
            names = _workbook_speaker_names(raw_row)
        except ValueError as exc:
            issues.append("%s: %s" % (label, exc))
            return []
        canonical_names, identity_keys = [], set()
        for name in names:
            if _key(name) == "third person":
                if "third person" not in {_key(value) for value in canonical_names}:
                    canonical_names.append("Third Person")
                continue
            matches = token_map.get(_key(name), set())
            if len(matches) != 1:
                issues.append("%s speaker '%s' is missing or ambiguous. Add it to Character Register or resolve its alias." % (label, name))
                continue
            identity_key = next(iter(matches))
            if identity_key not in registered_keys:
                issues.append("%s speaker '%s' is not listed in Character Register for this book." % (label, name))
                continue
            if identity_key not in identity_keys:
                identity_keys.add(identity_key)
                canonical_names.append(identities[identity_key]["canonical_name"])
        return canonical_names

    split_groups = {}
    for correction in document.get("dialogue_split_corrections") or []:
        if not isinstance(correction, dict):
            issues.append("Dialogue Split Corrections contains an invalid row.")
            continue
        parent_id = _clean(correction.get("Source Passage ID"))
        if not parent_id:
            issues.append("A Dialogue Split Corrections row is missing Source Passage ID.")
            continue
        split_groups.setdefault(parent_id, []).append(correction)

    split_parent_ids = set()
    for parent_id, correction_rows in split_groups.items():
        parent_current_id = workbook_source_to_current.get(parent_id, parent_id if parent_id in by_id else "")
        parent_row = workbook_row_by_id.get(parent_current_id)
        parent_passage = by_id.get(parent_current_id)
        if not parent_row or not parent_passage:
            issues.append(
                "Dialogue Split Corrections references parent passage '%s', which could not be matched to one exact current source passage."
                % parent_id
            )
            continue
        if (_clean(parent_row.get("Chapter ID")) != _clean(chapter_id)
            or _clean(parent_passage.get("chapter_id")) != _clean(chapter_id)
            or _clean(parent_row.get("Passage Type")).casefold() != "dialogue"
            or _key(parent_passage.get("kind")) == "narration"
            or str(parent_passage.get("assignment_state") or "").casefold() == "conflict"):
            issues.append("Dialogue Split Corrections parent '%s' must be a Dialogue passage in the active chapter." % parent_id)
            continue
        parent_text = str(parent_passage.get("text") or "")
        parent_start, parent_end = int(parent_passage.get("start", -1)), int(parent_passage.get("end", -1))
        if (parent_start < 0 or parent_end <= parent_start
            or parent_text != str(parent_row.get("Dialogue Text") or "")
            or (active_chapter_text and active_chapter_text[parent_start:parent_end] != parent_text)):
            issues.append("Dialogue Split Corrections parent '%s' no longer matches its exact source passage." % parent_id)
            continue
        source_context_before = active_chapter_text[max(0, parent_start - 160):parent_start] if active_chapter_text else ""
        source_context_after = active_chapter_text[parent_end:min(len(active_chapter_text), parent_end + 160)] if active_chapter_text else ""
        try:
            parent_ref_start = int(float(parent_row.get("Start (Reference)")))
            parent_ref_end = int(float(parent_row.get("End (Reference)")))
        except (TypeError, ValueError, OverflowError):
            parent_ref_start = parent_ref_end = -1
        if parent_ref_start != parent_start or parent_ref_end != parent_end:
            issues.append("Dialogue Split Corrections parent '%s' has changed source offsets." % parent_id)
            continue
        try:
            if _workbook_speaker_names(parent_row):
                issues.append("Parent passage '%s' cannot have a whole-passage speaker and subturn corrections at the same time." % parent_id)
                continue
        except ValueError as exc:
            issues.append("Parent passage '%s': %s" % (parent_id, exc))
            continue

        ordered = []
        valid_group = True
        for correction in correction_rows:
            try:
                index = int(float(correction.get("Subturn Index")))
                rel_start = int(float(correction.get("Start (Relative)")))
                rel_end = int(float(correction.get("End (Relative)")))
                if any(isinstance(correction.get(key), bool) for key in ("Subturn Index", "Start (Relative)", "End (Relative)")):
                    raise ValueError("boolean position")
                if (float(correction.get("Subturn Index")) != index
                    or float(correction.get("Start (Relative)")) != rel_start
                    or float(correction.get("End (Relative)")) != rel_end):
                    raise ValueError("non-integer position")
            except (TypeError, ValueError, OverflowError):
                issues.append("Dialogue Split Corrections for '%s' contains an invalid subturn index or relative offset." % parent_id)
                valid_group = False
                break
            exact_text = str(correction.get("Exact Source Text") or "")
            if rel_start < 0 or rel_end <= rel_start or rel_end > len(parent_text) or parent_text[rel_start:rel_end] != exact_text:
                issues.append("Subturn %s for '%s' does not match its exact source text and relative offsets." % (index, parent_id))
                valid_group = False
                break
            ordered.append((index, rel_start, rel_end, correction))
        if not valid_group:
            continue
        ordered.sort(key=lambda item: (item[1], item[2]))
        if len(ordered) < 2 or [item[0] for item in ordered] != list(range(1, len(ordered) + 1)):
            issues.append("A structural split for '%s' requires at least two subturns indexed 1..N." % parent_id)
            continue
        if any(ordered[i][1] < ordered[i - 1][2] for i in range(1, len(ordered))):
            issues.append("Subturn ranges for '%s' overlap. Correct them so turns are in source order without overlap." % parent_id)
            continue

        # Never erase a manual/unknown source assignment. Only an exact old AI/outsourced
        # parent span may be superseded by the confirmed child subturns.
        blocked_saved = False
        for saved in current_assignments:
            if not isinstance(saved, dict):
                continue
            try:
                saved_start, saved_end = int(saved.get("start", -1)), int(saved.get("end", -1))
            except (TypeError, ValueError, OverflowError):
                continue
            if saved_start >= parent_end or saved_end <= parent_start:
                continue
            saved_source = _clean(saved.get("source") or "manual").casefold()
            if (saved_start, saved_end) != (parent_start, parent_end) or saved_source not in {"ai", "outsourced"}:
                issues.append("Merged parent '%s' overlaps a saved %s assignment at %s:%s. Resolve the manual or unknown-source assignment before applying subturn corrections." % (parent_id, saved_source or "manual", saved_start, saved_end))
                blocked_saved = True
                continue
            old_speakers = saved.get("speakers")
            if not isinstance(old_speakers, (list, tuple)):
                old_speakers = [saved.get("speaker")] if saved.get("speaker") else []
            superseded_assignments.setdefault((saved_start, saved_end, saved_source), {
                "chapter_id": _clean(chapter_id), "start": saved_start, "end": saved_end,
                "source": saved_source, "speakers": [_clean(value) for value in old_speakers if _clean(value)],
                "text": str(saved.get("text") or parent_text),
            })
        if blocked_saved:
            continue

        added = []
        for index, rel_start, rel_end, correction in ordered:
            label = "Subturn %s in passage %s" % (index, parent_id)
            canonical_names = resolve_workbook_names(correction, label)
            if not canonical_names:
                valid_group = False
                continue
            try:
                mode = _workbook_multi_speaker_mode(correction, len(canonical_names))
                confidence = _normalize_workbook_confidence(correction.get("GPT Confidence (0–1)"))
            except (TypeError, ValueError, OverflowError) as exc:
                issues.append("%s has an invalid multi-speaker mode or GPT Confidence: %s." % (label, exc))
                valid_group = False
                continue
            added.append({
                "passage_id": "%s::subturn-%d" % (parent_current_id, index),
                "source_passage_id": parent_current_id, "source_passage_text": parent_text,
                "source_passage_start": parent_start, "source_passage_end": parent_end,
                "source_context_before": source_context_before,
                "source_context_after": source_context_after,
                "source_start_relative": rel_start, "source_end_relative": rel_end,
                "chapter_id": _clean(chapter_id),
                "chapter_revision": _clean(parent_passage.get("chapter_revision")) or _clean(chapter_revision),
                "start": parent_start + rel_start, "end": parent_start + rel_end,
                "text": str(correction.get("Exact Source Text") or ""),
                "speaker": canonical_names[0], "speakers": canonical_names,
                "multi_speaker_mode": mode, "series": active_series, "confidence": confidence,
            })
        if valid_group and len(added) == len(ordered):
            assignments.extend(added)
            split_parent_ids.add(parent_current_id)

    for row in document.get("dialogue_rows") or []:
        if not isinstance(row, dict):
            issues.append("The workbook contains an invalid dialogue row.")
            continue
        source_pid = _clean(row.get("Passage ID"))
        # Do not fall back to Passage ID alone. A row may carry a current-looking
        # ID while failing its exact chapter/revision/offset/source-text match.
        # Only rows admitted by resolve_workbook_passage() may create assignments.
        pid = workbook_source_to_current.get(source_pid, "")
        if not pid:
            # The mapping failure is recorded during the preflight pass above.
            continue
        if pid in seen:
            issues.append("Duplicate workbook rows resolve to current Passage ID %s." % pid)
            continue
        seen.add(pid)
        current = by_id.get(pid)
        if not current:
            issues.append("Current passage %s disappeared during workbook preflight." % pid)
            continue
        # resolve_workbook_passage() already verified chapter, revision, exact
        # source text and absolute offsets before the row reached this loop.
        workbook_type = _clean(row.get("Passage Type")).casefold()
        source_is_narration = _key(current.get("kind")) == "narration"
        legacy_inline_quote = (
            source_is_narration
            and _clean(current.get("source")) == "automatic_embedded_quote"
            and workbook_type == "dialogue"
        )
        try:
            assigned_names = _workbook_speaker_names(row)
        except ValueError as exc:
            issues.append("Passage %s: %s" % (pid, exc))
            continue
        assigned = assigned_names[0] if assigned_names else ""
        # If the active source index has safely reclassified an unchanged,
        # unassigned Dialogue row as Narration, keep the active Narrator
        # classification and do not reject the entire workbook. Never discard
        # a real character speaker decision during this reconciliation.
        if (
            workbook_type == "dialogue"
            and source_is_narration
            and not legacy_inline_quote
            and all(_key(name) == "narrator" for name in assigned_names)
        ):
            passage_reclassifications.append({
                "passage_id": pid, "chapter_id": _clean(chapter_id),
                "chapter_number": int(current.get("chapter_number") or 0),
                "chapter_title": _clean(current.get("chapter_title")),
                "start": int(current.get("start", -1)), "end": int(current.get("end", -1)),
                "source_text": str(current.get("text") or ""),
                "from_type": "Dialogue", "to_type": "Narration",
            })
        elif (
            workbook_type not in {"dialogue", "narration"}
            or ((workbook_type == "narration") != source_is_narration and not legacy_inline_quote)
        ):
            issues.append("Passage %s has a Passage Type conflict. The active book classifies this exact source span as %s; resolve it in Check dialogues before importing." % (pid, "Narration" if source_is_narration else "Dialogue"))
            continue
        narration = source_is_narration

        proposed_text = row.get("GPT Proposed Source Text")
        proposed_text = "" if proposed_text is None else str(proposed_text)
        correction_reason = str(row.get("GPT Text Correction Reason") or "").strip()
        original_text = str(current.get("text") or "")
        if proposed_text and proposed_text != original_text:
            if not correction_reason:
                issues.append("Passage %s has GPT Proposed Source Text but no GPT Text Correction Reason. Explain the source-based correction." % pid)
            elif len(proposed_text.encode("utf-16-le")) // 2 > 32767:
                issues.append("Passage %s proposed text exceeds Excel's 32,767-character cell limit." % pid)
            elif pid in split_parent_ids:
                issues.append("Passage %s cannot have both a whole-passage text correction and Dialogue Split Corrections. Resolve the wording first, then export again for subturn corrections." % pid)
            elif not proposed_text.strip():
                issues.append("Passage %s proposed source text cannot be blank. Leave both proposal columns empty when no correction is needed." % pid)
            else:
                text_corrections.append({
                    "passage_id": pid, "chapter_id": _clean(chapter_id),
                    "chapter_number": int(current.get("chapter_number") or 0),
                    "chapter_title": _clean(current.get("chapter_title")),
                    "chapter_revision": _clean(current.get("chapter_revision") or chapter_revision),
                    "passage_type": "Narration" if narration else "Dialogue",
                    "start": int(current.get("start", -1)), "end": int(current.get("end", -1)),
                    "source_text": original_text, "proposed_text": proposed_text,
                    "reason": correction_reason,
                })
        elif correction_reason and not proposed_text:
            issues.append("Passage %s has a GPT Text Correction Reason but no GPT Proposed Source Text.")
        if narration:
            quote_start, quote_end = int(current.get("start", -1)), int(current.get("end", -1))
            for saved in current_assignments:
                if not isinstance(saved, dict):
                    continue
                saved_source = _clean(saved.get("source") or "manual").casefold()
                try:
                    saved_start, saved_end = int(saved.get("start", -1)), int(saved.get("end", -1))
                except (TypeError, ValueError, OverflowError):
                    continue
                if saved_start >= quote_end or saved_end <= quote_start:
                    continue
                if saved_source not in {"ai", "outsourced"}:
                    saved_speakers = saved.get("speakers")
                    if not isinstance(saved_speakers, (list, tuple)):
                        saved_speakers = [saved.get("speaker")] if saved.get("speaker") else []
                    if any(_key(value) != "narrator" for value in saved_speakers if _clean(value)):
                        issues.append(
                            "Narration passage %s overlaps a protected manual/unknown speaker assignment at %s:%s. "
                            "The assignment was not overwritten; resolve the source classification in Check dialogues."
                            % (pid, saved_start, saved_end)
                        )
                    continue

                if not claim_stale_assignment_review(saved_start, saved_end, saved_source):
                    continue
                if not stale_ai_assignment_source_matches(saved_start, saved_end, saved_source):
                    issues.append(
                        "Stale AI/outsourced assignment at %s:%s does not match the exact active chapter source. "
                        "It was preserved; refresh the source review before importing."
                        % (saved_start, saved_end)
                    )
                    continue

                # A stale AI/outsourced span may be retired when every current
                # passage it touches is Narration. If it also touches Dialogue,
                # every affected Dialogue passage must have an explicit workbook
                # identity or an exact saved manual identity.
                impacted_passages = [
                    item for item in current_passages
                    if isinstance(item, dict)
                    and int(item.get("start", -1)) < saved_end
                    and int(item.get("end", -1)) > saved_start
                ]
                impacted_dialogue = [
                    item for item in impacted_passages
                    if _key(item.get("kind")) != "narration"
                ]
                unresolved_impacts = []
                for impacted in impacted_dialogue:
                    impacted_id = _clean(impacted.get("passage_id"))
                    workbook_row = workbook_row_by_id.get(impacted_id)
                    workbook_speakers = []
                    if isinstance(workbook_row, dict):
                        try:
                            workbook_speakers = _workbook_speaker_names(workbook_row)
                        except ValueError:
                            workbook_speakers = []
                    exact_saved = exact_saved_assignment_for_passage(impacted)
                    exact_saved_speakers = exact_saved.get("speakers") if isinstance(exact_saved, dict) else []
                    if not isinstance(exact_saved_speakers, (list, tuple)):
                        exact_saved_speakers = (
                            [exact_saved.get("speaker")]
                            if isinstance(exact_saved, dict) and exact_saved.get("speaker") else []
                        )
                    has_exact_manual_identity = (
                        isinstance(exact_saved, dict)
                        and _clean(exact_saved.get("source") or "manual").casefold() == "manual"
                        and any(_clean(value) for value in exact_saved_speakers)
                    )
                    if not workbook_speakers and not has_exact_manual_identity:
                        unresolved_impacts.append(impacted_id or "an unidentified passage")
                if not impacted_passages:
                    issues.append(
                        "Stale AI/outsourced assignment at %s:%s no longer maps to a current source passage. "
                        "It was preserved; refresh the workbook and source review."
                        % (saved_start, saved_end)
                    )
                    continue
                if unresolved_impacts:
                    issues.append(
                        "Stale AI/outsourced assignment at %s:%s also overlaps Dialogue passages without confirmed speakers: %s. "
                        "The stale assignment was preserved; resolve those Dialogue identities before importing. Exact manual assignments are preserved."
                        % (saved_start, saved_end, ", ".join(unresolved_impacts[:8]))
                    )
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
            if not legacy_inline_quote and assigned and _key(assigned) != "narrator":
                issues.append("Narration passage %s must retain the protected Narrator assignment." % pid)
            continue

        if pid in split_parent_ids:
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
        old = exact_saved_assignment_for_passage(current) or {}
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
            if saved_start >= end or saved_end <= start or saved is old:
                continue
            saved_source = _clean(saved.get("source") or "manual").casefold()
            if saved_source not in {"ai", "outsourced"}:
                # A manual/unknown-source assignment is safe only when it belongs
                # to one exact current passage with the same source offsets/text
                # and (when recorded) the same passage ID and chapter revision.
                exact_manual_passage = next((
                    item for item in current_passages
                    if isinstance(item, dict)
                    and int(item.get("start", -1)) == saved_start
                    and int(item.get("end", -1)) == saved_end
                    and exact_saved_assignment_for_passage(item) is saved
                ), None)
                if exact_manual_passage is not None:
                    continue
                issues.append(
                    "Passage %s (Chapter %s, %s:%s) overlaps a saved %s assignment at %s:%s. "
                    "Review that existing assignment in Character Studio; workbook import will not overwrite manual or unknown-source assignments."
                    % (pid, chapter_id, start, end, saved_source or "manual", saved_start, saved_end)
                )
                overlap_blocked = True
                continue
            if not claim_stale_assignment_review(saved_start, saved_end, saved_source):
                continue
            if not stale_ai_assignment_source_matches(saved_start, saved_end, saved_source):
                issues.append(
                    "Stale AI/outsourced assignment at %s:%s does not match the exact active chapter source. "
                    "It was preserved; refresh the source review before importing."
                    % (saved_start, saved_end)
                )
                overlap_blocked = True
                continue
            impacted_passages = [
                item for item in current_passages
                if isinstance(item, dict)
                and int(item.get("start", -1)) < saved_end
                and int(item.get("end", -1)) > saved_start
            ]
            impacted_dialogue = [
                item for item in impacted_passages
                if _key(item.get("kind")) != "narration"
            ]
            unresolved_impacts = []
            for impacted in impacted_dialogue:
                impacted_id = _clean(impacted.get("passage_id"))
                workbook_row = workbook_row_by_id.get(impacted_id)
                workbook_speakers = []
                if isinstance(workbook_row, dict):
                    try:
                        workbook_speakers = _workbook_speaker_names(workbook_row)
                    except ValueError:
                        workbook_speakers = []
                exact_saved = exact_saved_assignment_for_passage(impacted)
                exact_saved_speakers = exact_saved.get("speakers") if isinstance(exact_saved, dict) else []
                if not isinstance(exact_saved_speakers, (list, tuple)):
                    exact_saved_speakers = [exact_saved.get("speaker")] if isinstance(exact_saved, dict) and exact_saved.get("speaker") else []
                has_exact_manual_identity = (
                    isinstance(exact_saved, dict)
                    and _clean(exact_saved.get("source") or "manual").casefold() == "manual"
                    and any(_clean(value) for value in exact_saved_speakers)
                )
                if not workbook_speakers and not has_exact_manual_identity:
                    unresolved_impacts.append(impacted_id or "an unidentified passage")
            if not impacted_passages:
                issues.append(
                    "Stale AI/outsourced assignment at %s:%s no longer maps to a current source passage. "
                    "It was preserved; refresh the workbook and source review."
                    % (saved_start, saved_end)
                )
                overlap_blocked = True
                continue
            if unresolved_impacts:
                issues.append(
                    "Stale AI/outsourced assignment at %s:%s also overlaps Dialogue passages without confirmed speakers: %s. "
                    "The stale assignment was preserved; resolve those Dialogue identities before importing. Exact manual assignments are preserved."
                    % (saved_start, saved_end, ", ".join(unresolved_impacts[:8]))
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

        if not assigned_names:
            if not old_names:
                passage_excerpt = re.sub(r"\s+", " ", str(current.get("text") or "")).strip()[:120]
                issues.append(
                    "Dialogue passage %s in Chapter %s (%s) has no confirmed character assignment: %s. "
                    "Resolve it with source-supported Character Register identities or leave the book import blocked; do not guess."
                    % (pid, _clean(current.get("chapter_number")) or _clean(chapter_id),
                       _clean(current.get("chapter_title")), passage_excerpt)
                )
                continue
            old_identity_keys, unresolved_old_names = set(), []
            for old_name in old_names:
                if _key(old_name) == "third person":
                    old_identity_keys.add("third person|reserved")
                    continue
                old_matches = token_map.get(_key(old_name), set())
                if len(old_matches) != 1:
                    unresolved_old_names.append(old_name)
                else:
                    old_identity_keys.update(old_matches)
            if unresolved_old_names or not old_identity_keys:
                issues.append("Existing assignment for dialogue passage %s is missing or ambiguous (%s). Resolve it before importing." % (pid, " + ".join(old_names)))
            continue

        if any(_key(name) == "narrator" for name in assigned_names):
            issues.append("Narrator cannot be assigned to dialogue.")
            continue
        canonical_speakers, incoming_keys = [], set()
        invalid_speaker = False
        for assigned_name in assigned_names:
            if _key(assigned_name) == "third person":
                if "third person" not in {_key(value) for value in canonical_speakers}:
                    canonical_speakers.append("Third Person")
                incoming_keys.add("third person|reserved")
                continue
            matches = token_map.get(_key(assigned_name), set())
            if len(matches) != 1:
                issues.append("'%s' is missing or ambiguous. Add it to Character Register or resolve its alias." % assigned_name)
                invalid_speaker = True
                continue
            identity_key = next(iter(matches))
            if identity_key not in registered_keys:
                issues.append("Speaker '%s' is not listed in Character Register. Add the canonical character and aliases there before importing dialogue." % assigned_name)
                invalid_speaker = True
                continue
            if identity_key not in incoming_keys:
                incoming_keys.add(identity_key)
                canonical_speakers.append(identities[identity_key]["canonical_name"])
        if invalid_speaker or not canonical_speakers:
            continue
        try:
            multi_mode = _workbook_multi_speaker_mode(row, len(canonical_speakers))
        except ValueError as exc:
            issues.append("Passage %s: %s" % (pid, exc))
            continue

        old_keys, unresolved_old_names = set(), []
        for old_name in old_names:
            if _key(old_name) == "third person":
                old_keys.add("third person|reserved")
                continue
            old_matches = token_map.get(_key(old_name), set())
            if len(old_matches) != 1:
                unresolved_old_names.append(old_name)
            else:
                old_keys.update(old_matches)
        if "third person|reserved" in old_keys and old_keys != incoming_keys:
            issues.append(
                "Passage %s already uses the reserved Third Person placeholder. GPT cannot silently replace or expand this unidentified speaker; confirm a named identity manually in Check dialogues."
                % pid
            )
            continue
        old_source = _clean(old.get("source") or "manual").casefold()
        old_mode = _clean(old.get("multi_speaker_mode")).casefold() or ("chorus" if len(old_names) > 1 else "single")
        if old_names and not unresolved_old_names and old_keys == incoming_keys and old_mode == multi_mode:
            continue
        if old_names:
            if old_source not in {"ai", "outsourced"}:
                issues.append("Passage %s already has a different saved %s speaker set (%s). Resolve the manual or unknown-source assignment before import." % (pid, old_source or "manual", " + ".join(old_names)))
                continue
            superseded_assignments.setdefault((start, end, old_source), {
                "chapter_id": _clean(chapter_id), "start": start, "end": end,
                "source": old_source, "speakers": old_names, "text": str(old.get("text") or ""),
            })
        raw_confidence = _clean(row.get("GPT Confidence (0–1)"))
        if not raw_confidence:
            issues.append("Passage %s requires an explicit GPT Confidence value from 0.0 to 1.0; blank confidence is not accepted." % pid)
            continue
        try:
            confidence = _normalize_workbook_confidence(raw_confidence)
        except (TypeError, ValueError, OverflowError) as exc:
            issues.append(
                "Passage %s has invalid GPT Confidence (%s); use a decimal from 0.0 to 1.0 or a percentage from 0 to 100."
                % (pid, exc)
            )
            continue
        assignments.append({
            "passage_id": pid, "chapter_id": chapter_id,
            "chapter_revision": _clean(current.get("chapter_revision")) or _clean(chapter_revision),
            "start": start, "end": end,
            "text": str(current.get("text") or ""), "speaker": canonical_speakers[0],
            "speakers": canonical_speakers, "multi_speaker_mode": multi_mode,
            "series": active_series, "confidence": confidence,
        })
    unique_issues = list(dict.fromkeys(issues))
    partial_summary = {
        "characters": len(planned),
        "dialogue_assignments": len(assignments),
        "stale_assignments_to_retire": len(superseded_assignments),
        "text_corrections": len(text_corrections),
        "passage_reclassifications": len(passage_reclassifications),
        "skipped_issues": len(unique_issues),
    }
    # A partial import must include a source-verified dialogue assignment.
    # Character Register entries alone must never be presented as an assignment import.
    partial_ready = bool(assignments)
    return {
        "ready": not unique_issues,
        "partial_ready": partial_ready,
        "partial_summary": partial_summary,
        "issues": unique_issues,
        "characters": planned,
        "assignments": assignments,
        "superseded_assignments": list(superseded_assignments.values()),
        "passage_rebases": passage_rebases,
        "passage_mappings": passage_mappings,
        "passage_reclassifications": passage_reclassifications,
        "text_corrections": text_corrections,
        "summary": {
            "matched_characters": sum(x["action"] == "merge" for x in planned),
            "new_characters": sum(x["action"] == "create" for x in planned),
            "aliases_to_merge": sum(len(x.get("aliases_to_add", [])) for x in planned),
            "dialogue_assignments": len(assignments),
            "characters_in_register": len(planned),
            "unresolved_dialogue_passages": sum("no confirmed character assignment" in issue for issue in unique_issues),
            "saved_assignments_replaced": len(superseded_assignments),
            "passage_reclassifications": len(passage_reclassifications),
            "text_corrections": len(text_corrections),
            "third_person_assignments": sum(
                1 for row in assignments
                if any(_key(name) == "third person" for name in row.get("speakers", []))
            ),
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
    split_rows_by_chapter = {chapter_id: [] for chapter_id in reference_ids}
    for row in document.get("dialogue_split_corrections") or []:
        chapter_id = _clean(row.get("Chapter ID"))
        if chapter_id not in split_rows_by_chapter:
            raise ValueError("A Dialogue Split Corrections row references an unknown chapter.")
        split_rows_by_chapter[chapter_id].append(row)

    chapter_plans, issues = [], []
    superseded_assignments = []
    passage_rebases = []
    passage_mappings = []
    passage_reclassifications = []
    text_corrections = []
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
        # Passage IDs/counts can change when dialogue classification is corrected.
        # The chapter text hash and revision below still must match exactly; each
        # workbook row is then rebased only by its unique exact text + source span.
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
            "dialogue_split_corrections": split_rows_by_chapter[chapter_id],
            "_active_chapter_text": active_text,
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
        for mapping in plan.get("passage_mappings") or []:
            item = dict(mapping)
            item["chapter_number"] = int(reference["chapter_number"])
            passage_mappings.append(item)
        for rebase in plan.get("passage_rebases") or []:
            item = dict(rebase)
            item["chapter_number"] = int(reference["chapter_number"])
            passage_rebases.append(item)
        for reclassification in plan.get("passage_reclassifications") or []:
            item = dict(reclassification)
            item["chapter_number"] = int(reference["chapter_number"])
            passage_reclassifications.append(item)
        for correction in plan.get("text_corrections") or []:
            item = dict(correction)
            item["chapter_number"] = int(reference["chapter_number"])
            text_corrections.append(item)
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
            "passage_count": len(passages),
            "assignments": [],
        }
        for assignment in plan.get("assignments") or []:
            imported = dict(assignment)
            imported["chapter_number"] = int(reference["chapter_number"])
            imported["chapter_revision"] = _clean(reference.get("chapter_revision"))
            chapter_entry["assignments"].append(imported)
        chapter_plans.append(chapter_entry)

    issues = list(dict.fromkeys(issues))
    # An inconsistent book-wide identity merge plan is a hard boundary: do not
    # apply assignments or retire stale records derived from different cast plans.
    identity_plan_conflict = any(
        "character merge plan changed between chapters" in issue.casefold()
        for issue in issues
    )
    if identity_plan_conflict:
        identity_plan = []
        superseded_assignments = []
        for chapter in chapter_plans:
            chapter["assignments"] = []
    # Otherwise keep each independently source-verified row. Unresolved rows
    # remain issues and will be skipped only after explicit partial-import consent.
    assignments = [
        assignment
        for chapter in chapter_plans
        for assignment in chapter["assignments"]
    ]
    reviewed_chapters = [
        {key: value for key, value in row.items() if key != "assignments"}
        for row in chapter_plans
    ]
    partial_summary = {
        "characters": len(identity_plan),
        "dialogue_assignments": len(assignments),
        "stale_assignments_to_retire": len(superseded_assignments),
        "text_corrections": len(text_corrections),
        "passage_reclassifications": len(passage_reclassifications),
        "skipped_issues": len(issues),
    }
    # Do not offer a partial commit that only adds Character Register rows or
    # source corrections while the dialogue assignments remain unresolved.
    partial_ready = bool(assignments)
    summary = {
        "matched_characters": sum(row.get("action") == "merge" for row in identity_plan),
        "new_characters": sum(row.get("action") == "create" for row in identity_plan),
        "aliases_to_merge": sum(len(row.get("aliases_to_add") or []) for row in identity_plan),
        "dialogue_assignments": len(assignments),
        "characters_in_register": len(identity_plan),
        "chapters": len(chapter_plans),
        "unresolved_dialogue_passages": sum("no confirmed character assignment" in issue for issue in issues),
        "saved_assignments_replaced": len(superseded_assignments),
        "passage_reclassifications": len(passage_reclassifications),
        "text_corrections": len(text_corrections),
        "third_person_assignments": sum(
            1 for row in assignments
            if any(_key(name) == "third person" for name in row.get("speakers", []))
        ),
    }
    return {
        "ready": not issues,
        "partial_ready": partial_ready,
        "partial_summary": partial_summary,
        "issues": issues,
        "scope": "book",
        "book_revision": current_revision,
        "chapters": reviewed_chapters,
        "chapter_assignments": chapter_plans,
        "characters": identity_plan,
        "assignments": assignments,
        "superseded_assignments": superseded_assignments,
        "passage_rebases": passage_rebases,
        "passage_mappings": passage_mappings,
        "passage_reclassifications": passage_reclassifications,
        "text_corrections": text_corrections,
        "summary": summary,
    }



def character_workbook_assignment_diagnostics(document: dict, plan: dict | None = None) -> dict:
    """Explain what the workbook contains and how many speaker rows passed import checks."""
    if not isinstance(document, dict):
        document = {}
    if not isinstance(plan, dict):
        plan = {}
    rows = [row for row in (document.get("dialogue_rows") or []) if isinstance(row, dict)]
    dialogue_rows = [
        row for row in rows
        if _clean(row.get("Passage Type")).casefold() == "dialogue"
    ]
    speaker_rows = []
    invalid_speaker_rows = 0
    json_speaker_rows = 0
    confidence_rows = 0
    for row in dialogue_rows:
        if _clean(row.get("GPT Assigned Characters (JSON)")):
            json_speaker_rows += 1
        if _clean(row.get("GPT Confidence (0–1)")):
            confidence_rows += 1
        try:
            names = _workbook_speaker_names(row)
        except ValueError:
            invalid_speaker_rows += 1
            continue
        if names:
            speaker_rows.append(row)
    mapped_ids = {
        _clean(mapping.get("workbook_passage_id"))
        for mapping in (plan.get("passage_mappings") or [])
        if isinstance(mapping, dict) and _clean(mapping.get("workbook_passage_id"))
    }
    mapped_speaker_rows = [
        row for row in speaker_rows
        if _clean(row.get("Passage ID")) in mapped_ids
    ]
    issues = [str(value) for value in (plan.get("issues") or [])]
    source_mismatch_issues = sum(
        1 for issue in issues
        if "could not be safely matched" in issue.casefold()
        or "does not match the active chapter" in issue.casefold()
        or "no current passage has the same exact source text" in issue.casefold()
        or "references a different chapter revision" in issue.casefold()
    )
    assignments = list(plan.get("assignments") or [])
    return {
        "dialogue_rows": len(dialogue_rows),
        "dialogue_rows_with_gpt_speakers": len(speaker_rows),
        "dialogue_rows_with_json_speakers": json_speaker_rows,
        "dialogue_rows_with_confidence": confidence_rows,
        "dialogue_rows_with_invalid_speaker_data": invalid_speaker_rows,
        "speaker_rows_exactly_mapped": len(mapped_speaker_rows),
        "speaker_rows_unmapped": max(0, len(speaker_rows) - len(mapped_speaker_rows)),
        "verified_dialogue_assignments": len(assignments),
        "character_register_entries": len(document.get("characters") or []),
        "source_mismatch_issue_count": source_mismatch_issues,
        "preflight_issue_count": len(issues),
    }


def character_workbook_plan_fingerprint(plan: dict) -> str:
    """Digest every identity and assignment decision the user reviewed before commit."""
    if not isinstance(plan, dict):
        raise ValueError("A valid character workbook plan is required.")
    reviewed = {
        key: plan.get(key)
        for key in ("ready", "partial_ready", "partial_summary", "issues", "scope", "book_revision", "chapters", "chapter_assignments", "characters", "assignments", "superseded_assignments", "passage_rebases", "passage_mappings", "passage_reclassifications", "text_corrections", "summary")
    }
    try:
        encoded = json.dumps(
            reviewed, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("The character workbook plan contains unsupported values.") from exc
    return sha256(encoded).hexdigest()
