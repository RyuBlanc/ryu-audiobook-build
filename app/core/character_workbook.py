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

def _sheet(rows, widths, wrap):
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
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="%s"><dimension ref="A1:%s%d"/>'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews><sheetFormatPr defaultRowHeight="19"/><cols>%s</cols>'
        '<sheetData>%s</sheetData>%s</worksheet>') % (
            MAIN, last_col, end_row, cols, "".join(rendered), filt
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
        "Instructions": ("Fill GPT Assigned Character only for dialogue. Leave uncertain dialogue blank. "
            "Use GPT Confidence (0–1) as a numeric score from 0.0 to 1.0, and explain evidence in its notes. "
            "Narration is protected as Narrator. Add canonical full names and all other names as aliases. "
            "A younger/older version needing a different voice must be a separate Character Register row. "
            "Use Version / Age Variant and assign it by its distinct name, for example Mira (Younger Version). "
            "Use the read-only Series Character Reference sheet to reuse existing canonical names and known aliases. "
            "Do not edit that reference sheet; add genuinely new identities in Character Register. "
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
    reference_rows = None
    if "series_character_reference" in metadata:
        reference_rows = [[
            "Canonical Character", "Known Aliases", "Identity Base Name", "Version / Age Variant"
        ]]
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
            reference_rows.append([
                primary, "\\n".join(cleaned_aliases),
                _clean(source.get("identity_base_name") or primary),
                _clean(source.get("identity_variant") or source.get("version")),
            ])
    text = str(chapter_text or "")
    chunks = [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)] or [""]
    for i, chunk in enumerate(chunks, 1):
        context.append([i, metadata.get("chapter_number", ""), info["Chapter Title"], chunk])
    sheets = [
        ("Dialogue Assignment", dialogue, [38,38,14,32,16,72,34,18,34,22,18,14,14,42,46], {6,8,9,14,15}),
        ("Character Register", characters, [34] + [24] * ALIAS_COLUMNS + [26,48], set(range(1, ALIAS_COLUMNS + 4))),
        ("Chapter Context", context, [14,14,32,100], {4}),
        ("Workbook Info", [["Field","Value"]] + [[k,v] for k,v in info.items()], [28,110], {2}),
    ]
    if reference_rows is not None:
        sheets.append(("Series Character Reference", reference_rows, [36, 76, 36, 28], {2}))
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
        rels += '<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        z.writestr("xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="%s">%s</Relationships>' % (PKG, rels))
        z.writestr("xl/styles.xml", _styles())
        for n, (name, rows, widths, wrap) in enumerate(sheets, 1):
            z.writestr("xl/worksheets/sheet%d.xml" % n, _sheet(rows, widths, wrap))
    return output.getvalue()

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
            rels = {x.get("Id"): x.get("Target") for x in relroot.findall("{%s}Relationship" % PKG)}
            targets = {s.get("name"): rels.get(s.get("{%s}id" % REL)) for s in book.findall(".//" + _t("sheet"))}
            required = {"Dialogue Assignment", "Character Register", "Chapter Context", "Workbook Info"}
            if not required.issubset(targets): raise ValueError("Required Character Studio workbook sheets are missing.")
            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
                shared = ["".join(n.text or "" for n in x.iter(_t("t"))) for x in ss.findall(_t("si"))]
            sheets = {name: _read_sheet(z, targets[name], shared) for name in required}
            if "Series Character Reference" in targets:
                sheets["Series Character Reference"] = _read_sheet(z, targets["Series Character Reference"], shared)
    except (zipfile.BadZipFile, ET.ParseError, KeyError) as exc:
        raise ValueError("The .xlsx workbook is damaged or unsupported.") from exc
    info_rows = _records(sheets["Workbook Info"])
    info = {r.get("Field",""): _clean(r.get("Value","")) for r in info_rows}
    if info.get("Workbook Schema") != "ryu.character-studio-workbook":
        raise ValueError("This workbook was not exported by Character Studio.")
    try: version = int(float(info.get("Workbook Version", "0")))
    except (TypeError, ValueError, OverflowError): version = 0
    if version != 1: raise ValueError("This Character Studio workbook version is not supported.")
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
    reference_rows = _records(sheets.get("Series Character Reference", []))
    series_character_reference = []
    for row in reference_rows:
        primary = _clean(row.get("Canonical Character"))
        if not primary:
            continue
        aliases = [
            _clean(value) for value in str(row.get("Known Aliases") or "").splitlines()
            if _clean(value)
        ]
        series_character_reference.append({
            "canonical_name": primary,
            "aliases": aliases,
            "identity_base_name": _clean(row.get("Identity Base Name") or primary),
            "identity_variant": _clean(row.get("Version / Age Variant")),
        })

    characters = []
    for n, row in enumerate(char_rows, 2):
        name = _clean(row.get("Full Name"))
        if not name:
            continue
        if len(name) > MAX_CHARACTER_NAME_LENGTH:
            raise ValueError("Character Register names must be 160 characters or fewer.")
        version = _clean(row.get("Version / Age Variant"))
        if len(version) > MAX_IDENTITY_VARIANT_LENGTH:
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
        characters.append({
            "full_name": name,
            "aliases": list(dict.fromkeys(a for a in aliases if _key(a) != _key(name))),
            "version": version,
            "notes": notes,
            "row_number": n,
        })
    return {
        "info": info,
        "dialogue_rows": dialogue,
        "characters": characters,
        "series_character_reference": series_character_reference,
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
    workbook_ids = {_clean(row.get("Passage ID")) for row in document.get("dialogue_rows") or []}
    if workbook_ids != set(by_id):
        issues.append("The workbook does not contain the complete set of chapter passages. Restore every exported row and try again.")
    for row in document.get("dialogue_rows") or []:
        pid = _clean(row.get("Passage ID"))
        current = by_id.get(pid)
        if not current: issues.append("Passage %s is no longer in this chapter." % pid); continue
        if pid in seen: issues.append("Duplicate Passage ID %s." % pid); continue
        seen.add(pid)
        try:
            raw_start = float(row.get("Start (Reference)") or -1)
            raw_end = float(row.get("End (Reference)") or -1)
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
        if workbook_type not in {"dialogue", "narration"} or (workbook_type == "narration") != source_is_narration:
            issues.append("Passage %s has an edited or invalid Passage Type. Export the chapter again." % pid)
            continue
        narration = source_is_narration
        assigned = _clean(row.get("GPT Assigned Character"))
        if narration:
            if _key(assigned) != "narrator":
                issues.append("Narration passage %s must retain the protected Narrator assignment." % pid)
            continue
        if not assigned: continue
        if _key(assigned) == "narrator": issues.append("Narrator cannot be assigned to dialogue."); continue
        matches = token_map.get(_key(assigned), set())
        if len(matches) != 1:
            issues.append("'%s' is missing or ambiguous. Add it to Character Register or resolve its alias." % assigned); continue
        identity_key = next(iter(matches))
        if identity_key not in registered_keys:
            issues.append(
                "Speaker '%s' is not listed in Character Register. Add the canonical character and aliases there before importing dialogue."
                % assigned
            )
            continue
        identity = identities[identity_key]
        start, end = int(current["start"]), int(current["end"])
        if str(current.get("assignment_state") or "").casefold() == "conflict":
            issues.append("Passage %s already has conflicting saved assignments. Resolve it in Character Studio before import." % pid)
            continue
        old = by_span.get((start,end),{})
        speakers = old.get("speakers")
        if not isinstance(speakers,(list,tuple)): speakers=[old.get("speaker")] if old.get("speaker") else []
        old_names = [_clean(x) for x in speakers if _clean(x)]
        canonical = identity["canonical_name"]
        valid_identity_tokens = {_key(value) for value in identity.get("tokens", [])}
        if old_names and not all(_key(value) in valid_identity_tokens for value in old_names):
            issues.append("Passage %s already belongs to %s; resolve this assignment before import." % (pid," + ".join(old_names)))
            continue
        if any(isinstance(x,dict) and int(x.get("start",-1))<end and int(x.get("end",-1))>start
               and (int(x.get("start",-1)),int(x.get("end",-1)))!=(start,end) for x in current_assignments):
            issues.append("Passage %s overlaps another saved assignment." % pid); continue
        if old_names: continue
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
    return {"ready":not issues,"issues":list(dict.fromkeys(issues)),"characters":planned,"assignments":assignments,
        "summary":{"matched_characters":sum(x["action"]=="merge" for x in planned),
        "new_characters":sum(x["action"]=="create" for x in planned),
        "aliases_to_merge":sum(len(x.get("aliases_to_add", [])) for x in planned),
        "dialogue_assignments":len(assignments),"characters_in_register":len(planned)}}



def character_workbook_plan_fingerprint(plan: dict) -> str:
    """Digest every identity and assignment decision the user reviewed before commit."""
    if not isinstance(plan, dict):
        raise ValueError("A valid character workbook plan is required.")
    reviewed = {
        key: plan.get(key)
        for key in ("ready", "issues", "characters", "assignments", "summary")
    }
    try:
        encoded = json.dumps(
            reviewed, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("The character workbook plan contains unsupported values.") from exc
    return sha256(encoded).hexdigest()
