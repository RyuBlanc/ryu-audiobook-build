from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET

from app.core.character_library import (
    list_characters,
    merge_imported_character_records,
)
from app.core.character_workbook import (
    create_character_workbook_bytes,
    create_complete_book_character_workbook_bytes,
    plan_character_workbook_import,
    plan_complete_book_character_workbook_import,
    read_character_workbook,
    character_workbook_plan_fingerprint,
)


class CharacterWorkbookRoundTripTests(unittest.TestCase):
    def _export(self, folder: Path):
        text = "Narration introduces Mira.\n\n“Captain Mira, are you ready?”\n\nShe nodded."
        start = text.index("“Captain Mira")
        dialogue = text[start:start + len("“Captain Mira, are you ready?”")]
        metadata = {
            "project_title": "The Silver Archive",
            "series_name": "Silver Archive",
            "chapter_id": "chapter-001",
            "chapter_number": 1,
            "chapter_title": "The Arrival",
            "chapter_revision": "revision-abc",
        }
        passages = [
            {
                "passage_id": "ps_narration", "chapter_id": "chapter-001",
                "chapter_number": 1, "chapter_title": "The Arrival",
                "chapter_revision": "revision-abc", "start": 0,
                "end": text.index("\n\n"), "text": "Narration introduces Mira.",
                "kind": "narration", "speakers": [],
            },
            {
                "passage_id": "ps_dialogue", "chapter_id": "chapter-001",
                "chapter_number": 1, "chapter_title": "The Arrival",
                "chapter_revision": "revision-abc", "start": start,
                "end": start + len(dialogue), "text": dialogue,
                "kind": "character_dialogue", "speakers": [],
            },
        ]
        path = folder / "chapter.xlsx"
        path.write_bytes(create_character_workbook_bytes(metadata, passages, text))
        return path, text, passages

    def test_export_contains_blank_dialogue_fill_narrator_and_empty_character_register(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, chapter_text, expected = self._export(Path(tmp))
            document = read_character_workbook(path)
            rows = {row["Passage ID"]: row for row in document["dialogue_rows"]}
            self.assertEqual(rows["ps_dialogue"]["GPT Assigned Character"], "")
            self.assertEqual(rows["ps_dialogue"]["GPT Confidence (0–1)"], "")
            self.assertEqual(rows["ps_narration"]["GPT Assigned Character"], "Narrator")
            self.assertEqual(rows["ps_narration"]["GPT Confidence (0–1)"], "")
            self.assertEqual(rows["ps_dialogue"]["Dialogue Text"], expected[1]["text"])
            self.assertEqual(document["characters"], [])
            self.assertEqual(document["info"]["Series Name"], "Silver Archive")
            self.assertEqual(document["info"]["Chapter Revision"], "revision-abc")
            self.assertEqual(document["info"]["Passage Count"], "2")

    def test_export_includes_read_only_series_character_reference_without_voice_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, chapter_text, passages = self._export(Path(tmp))
            metadata = {
                "project_title": "The Silver Archive",
                "series_name": "Silver Archive",
                "chapter_id": "chapter-001", "chapter_number": 1,
                "chapter_title": "The Arrival", "chapter_revision": "revision-abc",
                "series_character_reference": [
                    {
                        "primary_name": "Mira",
                        "aliases": ["Captain Mira", "Mira-sama", "Captain Mira"],
                        "identity_base_name": "Mira", "identity_variant": "",
                        "voice_name": "This must not be exported",
                    },
                    {
                        "primary_name": "Mira (Younger Version)",
                        "aliases": ["Young Mira", "Childhood Mira"],
                        "identity_base_name": "Mira", "identity_variant": "Younger Version",
                    },
                ],
            }
            path.write_bytes(create_character_workbook_bytes(metadata, passages, chapter_text))
            with ZipFile(path, "r") as archive:
                book_xml = ET.fromstring(archive.read("xl/workbook.xml"))
                rels_xml = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
                package_ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
                document_ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
                relationship_items = rels_xml.findall(package_ns + "Relationship")
                relationship_ids = [item.get("Id") for item in relationship_items]
                self.assertEqual(len(relationship_ids), len(set(relationship_ids)))
                sheet_nodes = book_xml.findall(".//" + document_ns + "sheet")
                self.assertEqual(
                    [sheet.get("name") for sheet in sheet_nodes],
                    ["Dialogue Assignment", "Character Register", "Chapter Context", "Workbook Info"],
                )
                relationships = {item.get("Id"): item for item in relationship_items}
                sheet_rel_ids = [
                    sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                    for sheet in sheet_nodes
                ]
                self.assertTrue(all(relationships[rid].get("Type", "").endswith("/worksheet") for rid in sheet_rel_ids))
                info_relationship = relationships[sheet_rel_ids[3]]
                self.assertEqual(info_relationship.get("Target"), "worksheets/sheet4.xml")
                styles = [
                    item for item in relationship_items
                    if item.get("Type", "").endswith("/styles")
                ]
                self.assertEqual(len(styles), 1)
                self.assertNotIn(styles[0].get("Id"), sheet_rel_ids)
                info_xml = ET.fromstring(archive.read("xl/worksheets/sheet4.xml"))
                protection = info_xml.find(document_ns + "sheetProtection")
                self.assertIsNotNone(protection)
                self.assertEqual(protection.get("sheet"), "1")
                first_row = info_xml.find(".//" + document_ns + "sheetData/" + document_ns + "row")
                header_cells = {
                    cell.get("r"): "".join(node.text or "" for node in cell.iter(document_ns + "t"))
                    for cell in first_row.findall(document_ns + "c")
                }
                self.assertEqual(header_cells["D1"], "Canonical Character")
                self.assertEqual(header_cells["E1"], "Known Alias")
            parsed = read_character_workbook(path)
            self.assertEqual(len(parsed["series_character_reference"]), 2)
            adult, younger = parsed["series_character_reference"]
            self.assertEqual(adult["canonical_name"], "Mira")
            self.assertEqual(adult["aliases"], ["Captain Mira", "Mira-sama"])
            self.assertEqual(adult["identity_base_name"], "Mira")
            self.assertEqual(younger["canonical_name"], "Mira (Younger Version)")
            self.assertEqual(younger["aliases"], ["Young Mira", "Childhood Mira"])
            self.assertEqual(younger["identity_variant"], "Younger Version")
            self.assertNotIn("voice_name", adult)
            self.assertEqual(parsed["characters"], [])
            plan = plan_character_workbook_import(
                parsed, series="Silver Archive", registry_rows=[],
                project_characters=[], chapter_id="chapter-001",
                chapter_revision="revision-abc", current_passages=passages,
                current_assignments=[], book_title="The Silver Archive",
            )
            self.assertEqual(plan["characters"], [])
            self.assertEqual(plan["assignments"], [])

    def test_series_reference_supports_large_alias_lists_without_multiline_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, chapter_text, passages = self._export(Path(tmp))
            aliases = ["Alias %03d" % index for index in range(1, 181)]
            metadata = {
                "project_title": "The Silver Archive",
                "series_name": "Silver Archive",
                "chapter_id": "chapter-001", "chapter_number": 1,
                "chapter_title": "The Arrival", "chapter_revision": "revision-abc",
                "series_character_reference": [{
                    "primary_name": "Mira",
                    "aliases": aliases,
                    "identity_base_name": "Mira", "identity_variant": "",
                }],
            }
            path.write_bytes(create_character_workbook_bytes(metadata, passages, chapter_text))
            with ZipFile(path, "r") as archive:
                sheet = ET.fromstring(archive.read("xl/worksheets/sheet4.xml"))
                main_ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
                rows = sheet.findall(".//" + main_ns + "sheetData/" + main_ns + "row")
                self.assertEqual(len(rows), len(aliases) + 1)
            parsed = read_character_workbook(path)
            self.assertEqual(len(parsed["series_character_reference"]), 1)
            self.assertEqual(parsed["series_character_reference"][0]["aliases"], aliases)

    def test_edited_xlsx_file_is_reopened_and_planned_from_real_sheet_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _text, passages = self._export(Path(tmp))
            edited = Path(tmp) / "gpt-completed.xlsx"
            ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

            def set_inline_cell(root, row_number, reference, value):
                row = root.find(".//%srow[@r='%s']" % (ns, row_number))
                self.assertIsNotNone(row)
                cell = next((item for item in row.findall("%sc" % ns)
                             if item.get("r") == reference), None)
                if cell is None:
                    cell = ET.SubElement(row, ns + "c", {"r": reference})
                else:
                    cell.clear()
                    cell.set("r", reference)
                cell.set("t", "inlineStr")
                inline = ET.SubElement(cell, ns + "is")
                text_node = ET.SubElement(inline, ns + "t")
                text_node.text = value

            with ZipFile(path, "r") as source, ZipFile(edited, "w", ZIP_DEFLATED) as target:
                for item in source.infolist():
                    data = source.read(item.filename)
                    if item.filename == "xl/worksheets/sheet1.xml":
                        root = ET.fromstring(data)
                        set_inline_cell(root, 3, "G3", "Captain Mira")
                        set_inline_cell(root, 3, "O3", "The narration identifies Captain Mira.")
                        row = root.find(".//%srow[@r='3']" % ns)
                        confidence = ET.SubElement(row, ns + "c", {"r": "H3"})
                        ET.SubElement(confidence, ns + "v").text = "0.93"
                        data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    elif item.filename == "xl/worksheets/sheet2.xml":
                        root = ET.fromstring(data)
                        set_inline_cell(root, 2, "A2", "Captain Mira")
                        set_inline_cell(root, 2, "B2", "Mira-sama")
                        data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    target.writestr(item, data)

            document = read_character_workbook(edited)
            self.assertEqual(document["characters"][0]["full_name"], "Captain Mira")
            self.assertEqual(document["characters"][0]["aliases"], ["Mira-sama"])
            self.assertEqual(document["dialogue_rows"][1]["GPT Assigned Character"], "Captain Mira")
            self.assertEqual(document["dialogue_rows"][1]["GPT Confidence (0–1)"], "0.93")
            plan = plan_character_workbook_import(
                document, series="Silver Archive", book_title="The Silver Archive",
                registry_rows=[{
                    "id": "library-mira", "series": "Silver Archive",
                    "primary_name": "Mira", "aliases": ["Captain Mira"],
                    "voice_name": "Mira Voice", "identity_variant": "",
                }],
                project_characters=[], chapter_id="chapter-001",
                chapter_revision="revision-abc", current_passages=passages,
                current_assignments=[],
            )
            self.assertTrue(plan["ready"], plan["issues"])
            self.assertEqual(plan["assignments"][0]["speaker"], "Mira")
            self.assertEqual(plan["characters"][0]["action"], "merge")

    def test_import_plan_merges_existing_alias_into_series_canonical_character(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _text, passages = self._export(Path(tmp))
            document = read_character_workbook(path)
            document["characters"] = [{
                "full_name": "Captain Mira",
                "aliases": ["Mira-sama", "The Captain"],
                "version": "",
                "notes": "The same adult character.",
            }]
            document["dialogue_rows"][1]["GPT Assigned Character"] = "Captain Mira"
            document["dialogue_rows"][1]["GPT Confidence (0–1)"] = "0.93"
            plan = plan_character_workbook_import(
                document,
                series="Silver Archive",
                registry_rows=[{
                    "id": "library-mira", "series": "Silver Archive",
                    "primary_name": "Mira", "aliases": ["Captain Mira"],
                    "voice_name": "Mira Voice", "identity_variant": "",
                }],
                project_characters=[],
                chapter_id="chapter-001",
                chapter_revision="revision-abc",
                current_passages=passages,
                current_assignments=[],
            )
            self.assertTrue(plan["ready"], plan["issues"])
            self.assertEqual(plan["characters"][0]["canonical_name"], "Mira")
            self.assertEqual(plan["characters"][0]["action"], "merge")
            self.assertIn("Mira-sama", plan["characters"][0]["aliases"])
            self.assertEqual(plan["assignments"][0]["speaker"], "Mira")


    def test_new_imported_full_name_matching_existing_primary_becomes_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _text, passages = self._export(Path(tmp))
            document = read_character_workbook(path)
            document["characters"] = [{
                "full_name": "Captain Mira", "aliases": ["Mira", "The Captain"],
                "version": "", "notes": "",
            }]
            document["dialogue_rows"][1]["GPT Assigned Character"] = "Captain Mira"
            document["dialogue_rows"][1]["GPT Confidence (0–1)"] = "0.93"
            plan = plan_character_workbook_import(
                document, series="Silver Archive",
                registry_rows=[{
                    "id": "library-mira", "series": "Silver Archive",
                    "primary_name": "Mira", "aliases": [],
                    "voice_name": "Mira Voice",
                }],
                project_characters=[], chapter_id="chapter-001",
                chapter_revision="revision-abc", current_passages=passages,
                current_assignments=[],
            )
            self.assertTrue(plan["ready"], plan["issues"])
            self.assertEqual(plan["characters"][0]["canonical_name"], "Mira")
            self.assertIn("Captain Mira", plan["characters"][0]["aliases"])
            self.assertIn("The Captain", plan["characters"][0]["aliases"])
            self.assertEqual(plan["assignments"][0]["speaker"], "Mira")

    def test_import_plan_keeps_younger_version_as_separate_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _text, passages = self._export(Path(tmp))
            document = read_character_workbook(path)
            document["characters"] = [{
                "full_name": "Mira",
                "aliases": ["Young Mira", "Childhood Mira"],
                "version": "Younger Version",
                "notes": "",
            }]
            document["dialogue_rows"][1]["GPT Assigned Character"] = "Mira (Younger Version)"
            document["dialogue_rows"][1]["GPT Confidence (0–1)"] = "0.93"
            plan = plan_character_workbook_import(
                document,
                series="Silver Archive",
                registry_rows=[{
                    "id": "library-mira", "series": "Silver Archive",
                    "primary_name": "Mira", "aliases": ["Captain Mira"],
                    "voice_name": "Mira Voice",
                }],
                project_characters=[],
                chapter_id="chapter-001",
                chapter_revision="revision-abc",
                current_passages=passages,
                current_assignments=[],
            )
            self.assertTrue(plan["ready"], plan["issues"])
            self.assertEqual(plan["characters"][0]["canonical_name"], "Mira (Younger Version)")
            self.assertEqual(plan["characters"][0]["action"], "create")
            self.assertEqual(plan["assignments"][0]["speaker"], "Mira (Younger Version)")


    def test_import_plan_requires_explicit_gpt_confidence_for_new_assignments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _text, passages = self._export(Path(tmp))
            document = read_character_workbook(path)
            document["characters"] = [{
                "full_name": "Mira", "aliases": [], "version": "", "notes": "",
            }]
            document["dialogue_rows"][1]["GPT Assigned Character"] = "Mira"
            document["dialogue_rows"][1]["GPT Confidence (0–1)"] = ""
            plan = plan_character_workbook_import(
                document, series="Silver Archive", registry_rows=[],
                project_characters=[], chapter_id="chapter-001",
                chapter_revision="revision-abc", current_passages=passages,
                current_assignments=[],
            )
            self.assertFalse(plan["ready"])
            self.assertEqual(plan["assignments"], [])
            self.assertTrue(any("blank confidence is not accepted" in issue for issue in plan["issues"]))

    def test_import_plan_rejects_overlong_character_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _text, passages = self._export(Path(tmp))
            document = read_character_workbook(path)
            document["characters"] = [{
                "full_name": "M" * 161, "aliases": [], "version": "", "notes": "",
            }]
            plan = plan_character_workbook_import(
                document, series="Silver Archive", registry_rows=[],
                project_characters=[], chapter_id="chapter-001",
                chapter_revision="revision-abc", current_passages=passages,
                current_assignments=[],
            )
            self.assertFalse(plan["ready"])
            self.assertTrue(any("160 characters or fewer" in issue for issue in plan["issues"]))

    def test_workbook_plan_fingerprint_is_stable_and_changes_with_identity_decisions(self):
        plan = {
            "ready": True, "issues": [],
            "characters": [{
                "canonical_name": "Mira", "identity_variant": "",
                "aliases": ["Captain Mira"], "action": "merge", "library_id": "mira-id",
            }],
            "assignments": [{"passage_id": "p1", "speaker": "Mira", "confidence": 0.93}],
            "summary": {"matched_characters": 1, "dialogue_assignments": 1},
        }
        fingerprint = character_workbook_plan_fingerprint(plan)
        self.assertEqual(fingerprint, character_workbook_plan_fingerprint(dict(plan)))
        changed = {
            **plan,
            "characters": [{**plan["characters"][0], "library_id": "different-id"}],
        }
        self.assertNotEqual(fingerprint, character_workbook_plan_fingerprint(changed))
        changed_assignment = {
            **plan,
            "assignments": [{**plan["assignments"][0], "speaker": "Ren"}],
        }
        self.assertNotEqual(fingerprint, character_workbook_plan_fingerprint(changed_assignment))

    def test_dialogue_speaker_must_appear_in_character_register(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _text, passages = self._export(Path(tmp))
            document = read_character_workbook(path)
            document["dialogue_rows"][1]["GPT Assigned Character"] = "Mira"
            document["dialogue_rows"][1]["GPT Confidence (0–1)"] = "0.93"
            plan = plan_character_workbook_import(
                document, series="Silver Archive",
                registry_rows=[{
                    "id": "library-mira", "series": "Silver Archive",
                    "primary_name": "Mira", "aliases": [],
                }],
                project_characters=[], chapter_id="chapter-001",
                chapter_revision="revision-abc", current_passages=passages,
                current_assignments=[],
            )
            self.assertFalse(plan["ready"])
            self.assertTrue(any("not listed in Character Register" in issue for issue in plan["issues"]))

    def test_import_plan_blocks_alias_collision_and_stale_chapter_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _text, passages = self._export(Path(tmp))
            document = read_character_workbook(path)
            document["characters"] = [{
                "full_name": "Captain Mira", "aliases": [], "version": "", "notes": "",
            }]
            plan = plan_character_workbook_import(
                document,
                series="Silver Archive",
                registry_rows=[
                    {"id": "mira", "series": "Silver Archive", "primary_name": "Mira",
                     "aliases": ["Captain Mira"]},
                    {"id": "ren", "series": "Silver Archive", "primary_name": "Ren",
                     "aliases": ["Captain Mira"]},
                ],
                project_characters=[],
                chapter_id="chapter-001",
                chapter_revision="revision-abc",
                current_passages=passages,
                current_assignments=[],
            )
            self.assertFalse(plan["ready"])
            self.assertTrue(any("multiple existing" in issue for issue in plan["issues"]))

            stale = read_character_workbook(path)
            stale["dialogue_rows"][1]["GPT Assigned Character"] = "Mira"
            with self.assertRaisesRegex(ValueError, "changed after export"):
                plan_character_workbook_import(
                    stale,
                    series="Silver Archive",
                    registry_rows=[],
                    project_characters=[],
                    chapter_id="chapter-001",
                    chapter_revision="changed-revision",
                    current_passages=passages,
                    current_assignments=[],
                )


    def test_import_plan_rejects_removed_passage_rows_and_edited_reference_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _text, passages = self._export(Path(tmp))
            document = read_character_workbook(path)
            document["dialogue_rows"].pop()
            plan = plan_character_workbook_import(
                document, series="Silver Archive", registry_rows=[], project_characters=[],
                chapter_id="chapter-001", chapter_revision="revision-abc",
                current_passages=passages, current_assignments=[],
            )
            self.assertFalse(plan["ready"])
            self.assertTrue(any("complete set" in issue for issue in plan["issues"]))

    def test_import_plan_keeps_existing_assignment_that_uses_an_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _text, passages = self._export(Path(tmp))
            document = read_character_workbook(path)
            document["characters"] = [{
                "full_name": "Captain Mira", "aliases": ["Mira-sama"],
                "version": "", "notes": "",
            }]
            document["dialogue_rows"][1]["GPT Assigned Character"] = "Captain Mira"
            document["dialogue_rows"][1]["GPT Confidence (0–1)"] = "0.93"
            current_assignment = {
                "start": passages[1]["start"], "end": passages[1]["end"],
                "text": passages[1]["text"], "speakers": ["Mira-sama"],
                "source": "manual", "series": "Silver Archive",
            }
            plan = plan_character_workbook_import(
                document, series="Silver Archive",
                registry_rows=[{
                    "id": "library-mira", "series": "Silver Archive",
                    "primary_name": "Mira", "aliases": ["Captain Mira", "Mira-sama"],
                    "voice_name": "Mira Voice",
                }],
                project_characters=[], chapter_id="chapter-001",
                chapter_revision="revision-abc", current_passages=passages,
                current_assignments=[current_assignment],
            )
            self.assertTrue(plan["ready"], plan["issues"])
            self.assertEqual(plan["assignments"], [])

    def test_import_plan_blocks_recovery_bin_identity_collisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _text, passages = self._export(Path(tmp))
            document = read_character_workbook(path)
            document["characters"] = [{
                "full_name": "Captain Mira", "aliases": ["Mira-sama"], "version": "", "notes": "",
            }]
            plan = plan_character_workbook_import(
                document, series="Silver Archive", book_title="The Silver Archive",
                registry_rows=[{
                    "id": "library-mira", "series": "Silver Archive",
                    "primary_name": "Mira", "aliases": ["Captain Mira"], "identity_variant": "",
                }],
                deleted_registry_rows=[{
                    "id": "deleted-old", "series": "Silver Archive",
                    "primary_name": "Old Mira", "aliases": ["Mira-sama"],
                }],
                project_characters=[], chapter_id="chapter-001",
                chapter_revision="revision-abc", current_passages=passages,
                current_assignments=[],
            )
            self.assertFalse(plan["ready"])
            self.assertTrue(any("Recovery Bin" in issue for issue in plan["issues"]))

    def test_import_plan_blocks_duplicate_project_cast_identity_before_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _text, passages = self._export(Path(tmp))
            document = read_character_workbook(path)
            document["characters"] = [{
                "full_name": "Mira", "aliases": [], "version": "", "notes": "",
            }]
            duplicate_cast = [
                {"name": "Mira", "series": "Silver Archive", "aliases": []},
                {"name": "Mira", "series": "Silver Archive", "aliases": []},
            ]
            plan = plan_character_workbook_import(
                document, series="Silver Archive", registry_rows=[],
                project_characters=duplicate_cast, chapter_id="chapter-001",
                chapter_revision="revision-abc", current_passages=passages,
                current_assignments=[],
            )
            self.assertFalse(plan["ready"])
            self.assertTrue(any("Duplicate project Character Studio cast" in issue for issue in plan["issues"]))

    def test_import_plan_rejects_workbook_from_different_book(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _text, passages = self._export(Path(tmp))
            document = read_character_workbook(path)
            with self.assertRaisesRegex(ValueError, "different book"):
                plan_character_workbook_import(
                    document, series="Silver Archive", book_title="Another Book",
                    registry_rows=[], project_characters=[], chapter_id="chapter-001",
                    chapter_revision="revision-abc", current_passages=passages,
                    current_assignments=[],
                )

    def test_character_register_accepts_alias_columns_above_thirty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _text, _passages = self._export(Path(tmp))
            edited = Path(tmp) / "extended-alias-register.xlsx"
            ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

            def set_inline_cell(root, row_number, reference, value):
                sheet_data = root.find("%ssheetData" % ns)
                row = next((item for item in sheet_data.findall("%srow" % ns)
                            if item.get("r") == str(row_number)), None)
                if row is None:
                    row = ET.SubElement(sheet_data, ns + "row", {"r": str(row_number)})
                cell = next((item for item in row.findall("%sc" % ns)
                             if item.get("r") == reference), None)
                if cell is None:
                    cell = ET.SubElement(row, ns + "c", {"r": reference})
                else:
                    cell.clear()
                    cell.set("r", reference)
                cell.set("t", "inlineStr")
                inline = ET.SubElement(cell, ns + "is")
                ET.SubElement(inline, ns + "t").text = value

            with ZipFile(path, "r") as source, ZipFile(edited, "w", ZIP_DEFLATED) as target:
                for item in source.infolist():
                    data = source.read(item.filename)
                    if item.filename == "xl/worksheets/sheet2.xml":
                        root = ET.fromstring(data)
                        set_inline_cell(root, 1, "AH1", "Alias 31")
                        set_inline_cell(root, 2, "A2", "Mira")
                        set_inline_cell(root, 2, "AH2", "Thirty-First Alias")
                        dimension = root.find("%sdimension" % ns)
                        if dimension is not None:
                            dimension.set("ref", "A1:AH2")
                        data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    target.writestr(item, data)

            document = read_character_workbook(edited)
            self.assertEqual(len(document["characters"]), 1)
            self.assertEqual(document["characters"][0]["full_name"], "Mira")
            self.assertEqual(document["characters"][0]["aliases"], ["Thirty-First Alias"])

    def test_registry_merge_accepts_more_than_five_aliases_and_preserves_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "characters.json"
            from app.core.character_library import sync_characters
            sync_characters(
                "Silver Archive",
                [{"name": "Mira", "aliases": ["Captain Mira"], "voice": "Mira Voice"}],
                path=store,
            )
            before = list_characters(series="Silver Archive", path=store)
            aliases = ["Mira Name %d" % index for index in range(1, 18)]
            merged = merge_imported_character_records(
                "Silver Archive",
                [{
                    "canonical_name": "Mira", "identity_base_name": "Mira",
                    "identity_variant": "", "aliases": aliases,
                    "library_id": before[0]["id"], "notes": "",
                }],
                path=store,
            )
            saved = list_characters(series="Silver Archive", path=store)
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["voice_name"], "Mira Voice")
            self.assertTrue(set(aliases).issubset(set(saved[0]["aliases"])))
            self.assertEqual(len(merged), 1)


    def _complete_book_fixture(self, folder: Path):
        chapters = []
        all_passages = []
        source_specs = [
            (1, "chapter-001", "The Arrival", "revision-001",
             "“Mira, listen!”\nThe corridor was silent.",
             [("p1-dialogue", "“Mira, listen!”", "character_dialogue"),
              ("p1-narration", "The corridor was silent.", "narration")]),
            (2, "chapter-002", "The Warning", "revision-002",
             "“Captain Mira, wait!”\nShe turned back.",
             [("p2-dialogue", "“Captain Mira, wait!”", "character_dialogue"),
              ("p2-narration", "She turned back.", "narration")]),
        ]
        for number, chapter_id, title, revision, text, specs in source_specs:
            passages = []
            for passage_id, passage_text, kind in specs:
                start = text.index(passage_text)
                row = {
                    "passage_id": passage_id,
                    "chapter_id": chapter_id,
                    "chapter_number": number,
                    "chapter_title": title,
                    "chapter_revision": revision,
                    "start": start,
                    "end": start + len(passage_text),
                    "text": passage_text,
                    "kind": kind,
                    "speakers": [],
                }
                passages.append(row)
                all_passages.append(row)
            chapters.append({
                "chapter_id": chapter_id,
                "chapter_number": number,
                "chapter_title": title,
                "chapter_revision": revision,
                "text": text,
                "current_passages": passages,
                "current_assignments": [],
            })
        metadata = {
            "project_title": "The Silver Archive",
            "author": "A. Writer",
            "publisher": "North Star Press",
            "language": "English",
            "genre": "Fantasy",
            "year": "2024",
            "series_name": "Silver Archive",
            "series_volume": "Volume 2",
            "series_character_reference": [{
                "primary_name": "Mira",
                "aliases": ["Captain Mira", "Mira-sama"],
                "identity_base_name": "Mira",
                "identity_variant": "",
                "voice_name": "Do not export voice assets or local profile data",
            }],
        }
        path = folder / "complete-book.xlsx"
        path.write_bytes(create_complete_book_character_workbook_bytes(metadata, chapters, all_passages))
        document = read_character_workbook(path)
        return path, chapters, all_passages, document

    def test_complete_book_v2_exports_all_chapters_context_passages_and_separate_series_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, chapters, passages, document = self._complete_book_fixture(Path(tmp))
            with ZipFile(path, "r") as archive:
                book_xml = ET.fromstring(archive.read("xl/workbook.xml"))
                ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
                names = [sheet.get("name") for sheet in book_xml.findall(".//" + ns + "sheet")]
                self.assertEqual(names, [
                    "Dialogue Assignment", "Character Register", "Chapter Register",
                    "Chapter Context", "Series Character Reference", "Workbook Info",
                ])
                self.assertGreater(archive.getinfo("xl/worksheets/sheet4.xml").file_size, 0)
                self.assertGreater(archive.getinfo("xl/worksheets/sheet5.xml").file_size, 0)
            self.assertEqual(document["schema_version"], 2)
            self.assertEqual(document["info"]["Export Scope"], "complete_book")
            self.assertEqual(document["info"]["Author"], "A. Writer")
            self.assertEqual(document["info"]["Publisher"], "North Star Press")
            self.assertEqual(document["info"]["Language"], "English")
            self.assertEqual(document["info"]["Genre"], "Fantasy")
            self.assertEqual(document["info"]["Publication Year"], "2024")
            self.assertEqual(document["info"]["Series Volume"], "Volume 2")
            self.assertEqual(len(document["chapter_references"]), 2)
            self.assertEqual(len(document["dialogue_rows"]), len(passages))
            self.assertEqual(document["chapter_references"][0]["chapter_number"], 1)
            self.assertEqual(document["chapter_references"][1]["chapter_number"], 2)
            self.assertEqual(document["series_character_reference"][0]["canonical_name"], "Mira")
            self.assertEqual(document["series_character_reference"][0]["aliases"], ["Captain Mira", "Mira-sama"])
            self.assertNotIn("voice_name", document["series_character_reference"][0])
            self.assertEqual(document["characters"], [])


    def test_complete_book_reader_parses_gpt_character_names_aliases_and_book_inclusion_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            original, _chapters, _passages, _document = self._complete_book_fixture(Path(tmp))
            edited = Path(tmp) / "gpt-filled-book.xlsx"
            ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

            def set_inline_cell(root, row_number, reference, value):
                row = root.find(".//%srow[@r='%s']" % (ns, row_number))
                self.assertIsNotNone(row)
                cell = next((item for item in row.findall("%sc" % ns)
                             if item.get("r") == reference), None)
                if cell is None:
                    cell = ET.SubElement(row, ns + "c", {"r": reference})
                else:
                    cell.clear()
                    cell.set("r", reference)
                cell.set("t", "inlineStr")
                inline = ET.SubElement(cell, ns + "is")
                text_node = ET.SubElement(inline, ns + "t")
                text_node.text = value

            with ZipFile(original, "r") as source, ZipFile(edited, "w", ZIP_DEFLATED) as target:
                for item in source.infolist():
                    data = source.read(item.filename)
                    if item.filename == "xl/worksheets/sheet1.xml":
                        root = ET.fromstring(data)
                        set_inline_cell(root, 2, "G2", "Mira")
                        set_inline_cell(root, 2, "O2", "The direct address confirms the speaker.")
                        row = root.find(".//%srow[@r='2']" % ns)
                        confidence = ET.SubElement(row, ns + "c", {"r": "H2"})
                        ET.SubElement(confidence, ns + "v").text = "0.97"
                        data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    elif item.filename == "xl/worksheets/sheet2.xml":
                        root = ET.fromstring(data)
                        set_inline_cell(root, 2, "A2", "Mira")
                        set_inline_cell(root, 2, "B2", "Captain Mira")
                        set_inline_cell(root, 2, "AH2", "YES")
                        set_inline_cell(root, 3, "A3", "Young Mira")
                        set_inline_cell(root, 3, "AF3", "Younger Version")
                        set_inline_cell(root, 3, "AH3", "NO")
                        data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    target.writestr(item, data)

            parsed = read_character_workbook(edited)
            self.assertEqual(parsed["schema_version"], 2)
            self.assertEqual(len(parsed["chapter_references"]), 2)
            self.assertEqual(parsed["characters"][0]["full_name"], "Mira")
            self.assertEqual(parsed["characters"][0]["aliases"], ["Captain Mira"])
            self.assertTrue(parsed["characters"][0]["included_in_book"])
            self.assertEqual(parsed["characters"][1]["version"], "Younger Version")
            self.assertFalse(parsed["characters"][1]["included_in_book"])
            self.assertEqual(parsed["dialogue_rows"][0]["GPT Assigned Character"], "Mira")
            self.assertEqual(parsed["dialogue_rows"][0]["GPT Confidence (0–1)"], "0.97")


    def test_complete_book_import_plans_cross_chapter_assignments_and_series_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            _path, chapters, _passages, document = self._complete_book_fixture(Path(tmp))
            document["characters"] = [{
                "full_name": "Mira",
                "aliases": ["Captain Mira", "Mira-sama"],
                "version": "",
                "notes": "Confirmed from the complete narrative.",
                "included_in_book": True,
            }]
            for row in document["dialogue_rows"]:
                if row["Passage ID"] == "p1-dialogue":
                    row["GPT Assigned Character"] = "Mira"
                    row["GPT Confidence (0–1)"] = "0.97"
                elif row["Passage ID"] == "p2-dialogue":
                    row["GPT Assigned Character"] = "Captain Mira"
                    row["GPT Confidence (0–1)"] = "0.94"
            plan = plan_complete_book_character_workbook_import(
                document,
                series="Silver Archive",
                book_title="The Silver Archive",
                registry_rows=[{
                    "id": "library-mira",
                    "series": "Silver Archive",
                    "primary_name": "Mira",
                    "aliases": ["Captain Mira"],
                    "identity_variant": "",
                    "voice_name": "Existing Mira Voice",
                }],
                project_characters=[{
                    "name": "Mira",
                    "series": "Silver Archive",
                    "aliases": ["Captain Mira"],
                    "voice_profile": "Saved Qwen Mira Profile",
                }],
                current_chapters=chapters,
            )
            self.assertTrue(plan["ready"], plan["issues"])
            self.assertEqual(plan["scope"], "book")
            self.assertEqual(plan["summary"]["chapters"], 2)
            self.assertEqual(plan["summary"]["matched_characters"], 1)
            self.assertEqual(plan["summary"]["new_characters"], 0)
            self.assertEqual(plan["summary"]["dialogue_assignments"], 2)
            self.assertEqual(
                [(row["chapter_id"], row["passage_id"], row["speaker"]) for row in plan["assignments"]],
                [
                    ("chapter-001", "p1-dialogue", "Mira"),
                    ("chapter-002", "p2-dialogue", "Mira"),
                ],
            )
            self.assertEqual(plan["characters"][0]["existing_voice_name"], "Existing Mira Voice")
            self.assertEqual(
                character_workbook_plan_fingerprint(plan),
                character_workbook_plan_fingerprint(plan),
            )

    def test_complete_book_import_rejects_stale_chapter_context_or_missing_chapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            _path, chapters, _passages, document = self._complete_book_fixture(Path(tmp))
            changed = [dict(row) for row in chapters]
            changed[1] = {**changed[1], "text": changed[1]["text"] + "New sentence."}
            with self.assertRaisesRegex(ValueError, "context does not match"):
                plan_complete_book_character_workbook_import(
                    document, series="Silver Archive", book_title="The Silver Archive",
                    registry_rows=[], project_characters=[], current_chapters=changed,
                )
            with self.assertRaisesRegex(ValueError, "exact active book chapter set"):
                plan_complete_book_character_workbook_import(
                    document, series="Silver Archive", book_title="The Silver Archive",
                    registry_rows=[], project_characters=[], current_chapters=chapters[:1],
                )

    def test_complete_book_import_ignores_character_rows_not_marked_for_this_book(self):
        with tempfile.TemporaryDirectory() as tmp:
            _path, chapters, _passages, document = self._complete_book_fixture(Path(tmp))
            document["characters"] = [{
                "full_name": "Future Volume Character",
                "aliases": ["Future Hero"],
                "version": "",
                "notes": "",
                "included_in_book": False,
            }]
            plan = plan_complete_book_character_workbook_import(
                document, series="Silver Archive", book_title="The Silver Archive",
                registry_rows=[], project_characters=[], current_chapters=chapters,
            )
            self.assertTrue(plan["ready"], plan["issues"])
            self.assertEqual(plan["characters"], [])
            self.assertEqual(plan["summary"]["new_characters"], 0)



if __name__ == "__main__":
    unittest.main()
