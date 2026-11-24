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
    refresh_complete_book_character_workbook_bytes,
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


    def test_import_plan_blocks_dialogue_without_character_and_preserves_known_existing_assignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _text, passages = self._export(Path(tmp))
            document = read_character_workbook(path)
            document["characters"] = [{
                "full_name": "Mira", "aliases": ["Captain Mira"],
                "version": "", "notes": "",
            }]
            plan = plan_character_workbook_import(
                document, series="Silver Archive",
                registry_rows=[{
                    "id": "library-mira", "series": "Silver Archive",
                    "primary_name": "Mira", "aliases": ["Captain Mira"],
                }],
                project_characters=[], chapter_id="chapter-001",
                chapter_revision="revision-abc", current_passages=passages,
                current_assignments=[],
            )
            self.assertFalse(plan["ready"])
            self.assertEqual(plan["assignments"], [])
            self.assertTrue(any(
                "has no confirmed character assignment" in issue and "ps_dialogue" in issue
                for issue in plan["issues"]
            ))

            existing_assignment = {
                "start": passages[1]["start"], "end": passages[1]["end"],
                "text": passages[1]["text"], "speakers": ["Captain Mira"],
                "source": "manual", "series": "Silver Archive",
            }
            preserved = plan_character_workbook_import(
                document, series="Silver Archive",
                registry_rows=[{
                    "id": "library-mira", "series": "Silver Archive",
                    "primary_name": "Mira", "aliases": ["Captain Mira"],
                }],
                project_characters=[], chapter_id="chapter-001",
                chapter_revision="revision-abc", current_passages=passages,
                current_assignments=[existing_assignment],
            )
            self.assertTrue(preserved["ready"], preserved["issues"])
            self.assertEqual(preserved["assignments"], [])

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
                ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
                relationship_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
                package_ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
                book_xml = ET.fromstring(archive.read("xl/workbook.xml"))
                relationship_xml = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
                relationships = {
                    item.get("Id"): item.get("Target")
                    for item in relationship_xml.findall(package_ns + "Relationship")
                }
                sheet_targets = {}
                for sheet in book_xml.findall(".//" + ns + "sheet"):
                    target = relationships[sheet.get(relationship_ns + "id")]
                    target = target.lstrip("/")
                    if not target.startswith("xl/"):
                        target = "xl/" + target
                    sheet_targets[sheet.get("name")] = target

                names = [sheet.get("name") for sheet in book_xml.findall(".//" + ns + "sheet")]
                self.assertEqual(names, [
                    "GPT Prompt", "Dialogue Assignment", "Character Register", "Chapter Register",
                    "Chapter Context", "Series Character Reference", "Workbook Info",
                ])
                prompt_xml = ET.fromstring(archive.read(sheet_targets["GPT Prompt"]))
                prompt_text = "\n".join(
                    node.text or "" for node in prompt_xml.iter(ns + "t")
                )
                prompt_lower = prompt_text.casefold()
                self.assertIn("review required", prompt_lower)
                self.assertIn("does not mean the speaker is unknowable", prompt_lower)
                self.assertIn("newly split dialogue rows are independent turns", prompt_lower)
                self.assertIn("do not change passage id", prompt_lower)
                self.assertGreater(len(prompt_text.splitlines()), 20)
                self.assertGreater(archive.getinfo(sheet_targets["Chapter Context"]).file_size, 0)
                self.assertGreater(archive.getinfo(sheet_targets["Series Character Reference"]).file_size, 0)
            self.assertEqual(document["schema_version"], 2)
            self.assertEqual(document["info"]["Export Scope"], "complete_book")
            self.assertEqual(document["info"]["Author"], "A. Writer")
            self.assertEqual(document["info"]["Publisher"], "North Star Press")
            self.assertEqual(document["info"]["Language"], "English")
            self.assertEqual(document["info"]["Genre"], "Fantasy")
            self.assertEqual(document["info"]["Publication Year"], "2024")
            self.assertEqual(document["info"]["Series Volume"], "Volume 2")
            self.assertIn("GPT Prompt", document["info"]["Instructions"])
            self.assertEqual(document["info"]["GPT Prompt Version"], "1.0")
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
                book_xml = ET.fromstring(source.read("xl/workbook.xml"))
                relationship_xml = ET.fromstring(source.read("xl/_rels/workbook.xml.rels"))
                relationship_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
                package_ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
                relationships = {
                    item.get("Id"): item.get("Target")
                    for item in relationship_xml.findall(package_ns + "Relationship")
                }
                sheet_targets = {}
                for sheet in book_xml.findall(".//%s%s" % (ns, "sheet")):
                    path = relationships[sheet.get(relationship_ns + "id")].lstrip("/")
                    if not path.startswith("xl/"):
                        path = "xl/" + path
                    sheet_targets[sheet.get("name")] = path

                for item in source.infolist():
                    data = source.read(item.filename)
                    if item.filename == sheet_targets["Dialogue Assignment"]:
                        root = ET.fromstring(data)
                        set_inline_cell(root, 2, "G2", "Mira")
                        set_inline_cell(root, 2, "O2", "The direct address confirms the speaker.")
                        row = root.find(".//%srow[@r='2']" % ns)
                        confidence = ET.SubElement(row, ns + "c", {"r": "H2"})
                        ET.SubElement(confidence, ns + "v").text = "0.97"
                        data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    elif item.filename == sheet_targets["Character Register"]:
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

    def test_complete_book_import_reconciles_stale_ai_overlap_only_when_all_impacted_rows_are_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _path, chapters, _passages, document = self._complete_book_fixture(Path(tmp))
            document["characters"] = [{
                "full_name": "Mira", "aliases": [], "version": "",
                "notes": "Named character confirmed in the source.", "included_in_book": True,
            }]
            for row in document["dialogue_rows"]:
                if row["Passage Type"] == "Dialogue":
                    row["GPT Assigned Character"] = "Mira"
                    row["GPT Confidence (0–1)"] = "0.97"

            first = chapters[0]
            first_dialogue = next(row for row in first["current_passages"] if row["kind"] != "narration")
            stale_end = int(first_dialogue["end"]) + 1
            first["current_assignments"] = [{
                "start": int(first_dialogue["start"]),
                "end": stale_end,
                "text": first["text"][int(first_dialogue["start"]):stale_end],
                "speaker": "Legacy AI speaker",
                "source": "ai",
                "confidence": 0.72,
            }]
            plan = plan_complete_book_character_workbook_import(
                document, series="Silver Archive", book_title="The Silver Archive",
                registry_rows=[], project_characters=[], current_chapters=chapters,
            )
            self.assertTrue(plan["ready"], plan["issues"])
            self.assertEqual(len(plan["superseded_assignments"]), 1)
            self.assertEqual(plan["superseded_assignments"][0]["source"], "ai")
            self.assertEqual(plan["summary"]["saved_assignments_replaced"], 1)
            self.assertEqual(plan["summary"]["dialogue_assignments"], 2)

            first["current_assignments"][0]["source"] = "manual"
            protected = plan_complete_book_character_workbook_import(
                document, series="Silver Archive", book_title="The Silver Archive",
                registry_rows=[], project_characters=[], current_chapters=chapters,
            )
            self.assertFalse(protected["ready"])
            self.assertEqual(protected["superseded_assignments"], [])
            self.assertTrue(any("will not overwrite manual" in issue for issue in protected["issues"]))

    def test_import_plan_removes_only_stale_ai_records_for_verified_embedded_quote_narration(self):
        source = 'She causes these sorts of “accidents” and keeps walking.'
        start = source.index('“accidents”')
        end = start + len('“accidents”')
        quote = source[start:end]
        document = {
            "schema_version": 1,
            "info": {
                "Series Name": "Silver Archive",
                "Book Title": "The Silver Archive",
                "Chapter ID": "chapter-001",
                "Chapter Revision": "revision-001",
            },
            "characters": [],
            "dialogue_rows": [{
                "Passage ID": "ps_embedded_quote",
                "Chapter ID": "chapter-001",
                "Chapter Revision (Reference)": "revision-001",
                "Passage Type": "Narration",
                "Dialogue Text": quote,
                "GPT Assigned Character": "Narrator",
                "GPT Confidence (0–1)": "",
                "Start (Reference)": start,
                "End (Reference)": end,
            }],
        }
        current_passages = [{
            "passage_id": "ps_embedded_quote", "chapter_id": "chapter-001",
            "chapter_number": 1, "chapter_title": "The Opening",
            "chapter_revision": "revision-001", "start": start, "end": end,
            "text": quote, "kind": "narration", "source": "automatic_embedded_quote",
            "assignment_state": "narrator",
        }]
        for assignment_source in ("ai", "outsourced"):
            plan = plan_character_workbook_import(
                document, series="Silver Archive", book_title="The Silver Archive",
                registry_rows=[], project_characters=[], chapter_id="chapter-001",
                chapter_revision="revision-001", current_passages=current_passages,
                current_assignments=[{
                    "start": start, "end": end, "text": quote,
                    "speaker": "Legacy AI speaker", "source": assignment_source,
                }],
            )
            self.assertTrue(plan["ready"], plan["issues"])
            self.assertEqual(len(plan["superseded_assignments"]), 1)
            self.assertEqual(plan["superseded_assignments"][0]["source"], assignment_source)
            self.assertEqual(plan["summary"]["saved_assignments_replaced"], 1)

    def test_broad_stale_ai_span_can_be_replaced_across_confirmed_dialogue_and_embedded_narration(self):
        source = '“Mira, I heard you.” She calls it “accidents” and walks away.'
        dialogue = '“Mira, I heard you.”'
        quote = '“accidents”'
        dialogue_start = source.index(dialogue)
        dialogue_end = dialogue_start + len(dialogue)
        quote_start = source.index(quote)
        quote_end = quote_start + len(quote)
        document = {
            "schema_version": 1,
            "info": {
                "Series Name": "Silver Archive", "Book Title": "The Silver Archive",
                "Chapter ID": "chapter-001", "Chapter Revision": "revision-001",
            },
            "characters": [{
                "full_name": "Mira", "aliases": [], "version": "",
                "notes": "Confirmed in the source.", "included_in_book": True,
            }],
            "dialogue_rows": [
                {
                    "Passage ID": "ps-dialogue", "Chapter ID": "chapter-001",
                    "Chapter Revision (Reference)": "revision-001",
                    "Passage Type": "Dialogue", "Dialogue Text": dialogue,
                    "GPT Assigned Character": "Mira", "GPT Confidence (0–1)": "0.99",
                    "Start (Reference)": dialogue_start, "End (Reference)": dialogue_end,
                },
                {
                    "Passage ID": "ps-embedded", "Chapter ID": "chapter-001",
                    "Chapter Revision (Reference)": "revision-001",
                    "Passage Type": "Narration", "Dialogue Text": quote,
                    "GPT Assigned Character": "Narrator", "GPT Confidence (0–1)": "",
                    "Start (Reference)": quote_start, "End (Reference)": quote_end,
                },
            ],
        }
        passages = [
            {
                "passage_id": "ps-dialogue", "chapter_id": "chapter-001",
                "chapter_number": 1, "chapter_title": "The Opening",
                "chapter_revision": "revision-001", "start": dialogue_start,
                "end": dialogue_end, "text": dialogue, "kind": "character_dialogue",
                "source": "quoted_or_dash_dialogue", "assignment_state": "pending",
            },
            {
                "passage_id": "ps-embedded", "chapter_id": "chapter-001",
                "chapter_number": 1, "chapter_title": "The Opening",
                "chapter_revision": "revision-001", "start": quote_start,
                "end": quote_end, "text": quote, "kind": "narration",
                "source": "automatic_embedded_quote", "assignment_state": "narrator",
            },
        ]
        stale = {
            "start": dialogue_start, "end": quote_end,
            "text": source[dialogue_start:quote_end],
            "speaker": "Legacy AI speaker", "source": "ai",
        }
        ready = plan_character_workbook_import(
            document, series="Silver Archive", book_title="The Silver Archive",
            registry_rows=[], project_characters=[], chapter_id="chapter-001",
            chapter_revision="revision-001", current_passages=passages,
            current_assignments=[stale],
        )
        self.assertTrue(ready["ready"], ready["issues"])
        self.assertEqual(len(ready["superseded_assignments"]), 1)
        self.assertEqual(ready["assignments"][0]["speaker"], "Mira")

        manual = {**stale, "source": "manual"}
        protected = plan_character_workbook_import(
            document, series="Silver Archive", book_title="The Silver Archive",
            registry_rows=[], project_characters=[], chapter_id="chapter-001",
            chapter_revision="revision-001", current_passages=passages,
            current_assignments=[manual],
        )
        self.assertFalse(protected["ready"])
        self.assertEqual(protected["superseded_assignments"], [])
        self.assertTrue(any("will not overwrite manual" in issue for issue in protected["issues"]))

    def test_legacy_inline_quoted_term_row_remains_importable_as_narration(self):
        source = 'She causes these sorts of “accidents” and keeps walking.'
        start = source.index('“accidents”')
        quote = source[start:start + len('“accidents”')]
        document = {
            "schema_version": 1,
            "info": {
                "Series Name": "Silver Archive",
                "Book Title": "The Silver Archive",
                "Chapter ID": "chapter-001",
                "Chapter Revision": "revision-001",
            },
            "characters": [],
            "dialogue_rows": [{
                "Passage ID": "ps_legacy_inline_quote",
                "Chapter ID": "chapter-001",
                "Chapter Revision (Reference)": "revision-001",
                "Passage Type": "Dialogue",
                "Dialogue Text": quote,
                "GPT Assigned Character": "Mira",
                "GPT Confidence (0–1)": "0.86",
                "Start (Reference)": start,
                "End (Reference)": start + len(quote),
            }],
        }
        current_passages = [{
            "passage_id": "ps_legacy_inline_quote",
            "chapter_id": "chapter-001",
            "chapter_number": 1,
            "chapter_title": "The Opening",
            "chapter_revision": "revision-001",
            "start": start,
            "end": start + len(quote),
            "text": quote,
            "kind": "narration",
            "source": "automatic_embedded_quote",
        }]
        plan = plan_character_workbook_import(
            document,
            series="Silver Archive",
            book_title="The Silver Archive",
            registry_rows=[],
            project_characters=[],
            chapter_id="chapter-001",
            chapter_revision="revision-001",
            current_passages=current_passages,
            current_assignments=[{
                "start": start, "end": start + len(quote), "text": quote,
                "speaker": "Legacy AI speaker", "source": "ai",
            }],
        )
        self.assertTrue(plan["ready"], plan["issues"])
        self.assertEqual(plan["assignments"], [])
        self.assertEqual(plan["summary"]["dialogue_assignments"], 0)
        self.assertEqual(len(plan["superseded_assignments"]), 1)
        self.assertEqual(plan["superseded_assignments"][0]["source"], "ai")
        self.assertEqual(plan["summary"]["saved_assignments_replaced"], 1)

    def test_refresh_carries_only_exact_unchanged_assignments_and_preserves_character_register(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_path, chapters, _passages, document = self._complete_book_fixture(Path(tmp))
            original_bytes = original_path.read_bytes()
            document["characters"] = [
                {
                    "full_name": "Mira",
                    "aliases": ["Captain Mira", "Mira-sama"],
                    "version": "",
                    "notes": "Canonical series character.",
                    "included_in_book": True,
                },
                {
                    "full_name": "Future Volume Character",
                    "aliases": ["Future Hero"],
                    "version": "",
                    "notes": "Appears in a later volume only.",
                    "included_in_book": False,
                },
            ]
            old_first = next(row for row in document["dialogue_rows"] if row["Passage ID"] == "p1-dialogue")
            old_first["GPT Assigned Character"] = "Ren"
            old_first["GPT Confidence (0–1)"] = "0.98"
            old_first["Evidence / Notes (GPT)"] = "Speaker tag in the source."
            old_second = next(row for row in document["dialogue_rows"] if row["Passage ID"] == "p2-dialogue")
            old_second["GPT Assigned Character"] = "Mira"
            old_second["GPT Confidence (0–1)"] = "0.94"
            old_second["Evidence / Notes (GPT)"] = "Canonical alias confirmed in the series reference."

            first = dict(chapters[0])
            first_passages = [dict(row) for row in first["current_passages"]]
            old_dialogue = next(row for row in first_passages if row["passage_id"] == "p1-dialogue")
            split_text = old_dialogue["text"]
            split_at = split_text.index(" ") + 1
            left_text = split_text[:split_at].rstrip()
            right_text = split_text[split_at:].lstrip()
            left_start = int(old_dialogue["start"])
            right_start = left_start + split_text.index(right_text)
            first_passages = [
                row for row in first_passages if row["passage_id"] != "p1-dialogue"
            ]
            first_passages.extend([
                {
                    **old_dialogue,
                    "passage_id": "p1-dialogue-split-a",
                    "start": left_start,
                    "end": left_start + len(left_text),
                    "text": left_text,
                },
                {
                    **old_dialogue,
                    "passage_id": "p1-dialogue-split-b",
                    "start": right_start,
                    "end": right_start + len(right_text),
                    "text": right_text,
                },
            ])
            first["current_passages"] = sorted(
                first_passages, key=lambda row: (row["start"], row["end"])
            )
            refreshed_chapters = [first, dict(chapters[1])]
            refreshed_passages = [
                passage
                for chapter in refreshed_chapters
                for passage in chapter["current_passages"]
            ]
            metadata = {
                "project_title": document["info"]["Book Title"],
                "series_name": document["info"]["Series Name"],
                "author": document["info"]["Author"],
                "publisher": document["info"]["Publisher"],
                "language": document["info"]["Language"],
                "genre": document["info"]["Genre"],
                "year": document["info"]["Publication Year"],
                "series_volume": document["info"]["Series Volume"],
                "series_character_reference": document["series_character_reference"],
            }

            workbook_bytes, summary = refresh_complete_book_character_workbook_bytes(
                document,
                metadata=metadata,
                chapters=refreshed_chapters,
                passages=refreshed_passages,
            )
            refreshed_path = Path(tmp) / "complete-book-refreshed.xlsx"
            refreshed_path.write_bytes(workbook_bytes)
            refreshed = read_character_workbook(refreshed_path)

            split_rows = [
                row for row in refreshed["dialogue_rows"]
                if row["Passage ID"] in {"p1-dialogue-split-a", "p1-dialogue-split-b"}
            ]
            self.assertEqual(len(split_rows), 2)
            self.assertTrue(all(not row["GPT Assigned Character"] for row in split_rows))
            self.assertTrue(all(
                row["Evidence / Notes (GPT)"].startswith("REVIEW REQUIRED")
                and "Ren" in row["Evidence / Notes (GPT)"]
                and "GPT Prompt sheet" in row["Evidence / Notes (GPT)"]
                for row in split_rows
            ))
            carried = next(row for row in refreshed["dialogue_rows"] if row["Passage ID"] == "p2-dialogue")
            self.assertEqual(carried["GPT Assigned Character"], "Mira")
            self.assertEqual(carried["GPT Confidence (0–1)"], "0.94")
            self.assertEqual(
                carried["Evidence / Notes (GPT)"],
                "Canonical alias confirmed in the series reference.",
            )
            self.assertEqual(
                [(row["full_name"], row["included_in_book"]) for row in refreshed["characters"]],
                [("Mira", True), ("Future Volume Character", False)],
            )
            self.assertEqual(refreshed["characters"][0]["aliases"], ["Captain Mira", "Mira-sama"])
            self.assertEqual(summary["gpt_assignments_carried"], 1)
            self.assertEqual(summary["new_or_changed_dialogue_rows_for_review"], 2)
            self.assertEqual(summary["unresolved_dialogue_passages"], 2)
            self.assertEqual(summary["character_register_entries_preserved"], 2)
            self.assertEqual(original_path.read_bytes(), original_bytes)

    def test_refresh_refuses_to_transfer_gpt_assignments_when_chapter_text_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _path, chapters, passages, document = self._complete_book_fixture(Path(tmp))
            changed = [dict(row) for row in chapters]
            changed[0]["text"] += "New source sentence."
            metadata = {
                "project_title": document["info"]["Book Title"],
                "series_name": document["info"]["Series Name"],
                "series_character_reference": document["series_character_reference"],
            }
            with self.assertRaisesRegex(ValueError, "source text or revision changed"):
                refresh_complete_book_character_workbook_bytes(
                    document, metadata=metadata, chapters=changed, passages=passages,
                )

    def test_complete_book_import_blocks_any_dialogue_without_a_character(self):
        with tempfile.TemporaryDirectory() as tmp:
            _path, chapters, _passages, document = self._complete_book_fixture(Path(tmp))
            document["characters"] = [{
                "full_name": "Mira", "aliases": ["Captain Mira"],
                "version": "", "notes": "", "included_in_book": True,
            }]
            for row in document["dialogue_rows"]:
                if row["Passage ID"] == "p1-dialogue":
                    row["GPT Assigned Character"] = "Mira"
                    row["GPT Confidence (0–1)"] = "0.97"
            # p2-dialogue is deliberately left blank. Import must not silently
            # accept the first chapter while omitting this second-chapter line.
            plan = plan_complete_book_character_workbook_import(
                document, series="Silver Archive", book_title="The Silver Archive",
                registry_rows=[], project_characters=[], current_chapters=chapters,
            )
            self.assertFalse(plan["ready"])
            self.assertEqual(plan["assignments"], [])
            self.assertTrue(all(not chapter["assignments"] for chapter in plan["chapter_assignments"]))
            self.assertEqual(plan["summary"]["dialogue_assignments"], 0)
            self.assertTrue(any(
                "has no confirmed character assignment" in issue and "p2-dialogue" in issue
                for issue in plan["issues"]
            ))

    def test_complete_book_import_explicitly_rejects_changed_dialogue_segmentation(self):
        with tempfile.TemporaryDirectory() as tmp:
            _path, chapters, _passages, document = self._complete_book_fixture(Path(tmp))
            changed = [dict(row) for row in chapters]
            changed[0] = dict(changed[0])
            changed[0]["current_passages"] = [
                *changed[0]["current_passages"],
                {
                    **changed[0]["current_passages"][0],
                    "passage_id": "new-split-passage",
                    "start": changed[0]["current_passages"][0]["start"] + 1,
                },
            ]
            with self.assertRaisesRegex(ValueError, "segmentation changed after workbook export"):
                plan_complete_book_character_workbook_import(
                    document, series="Silver Archive", book_title="The Silver Archive",
                    registry_rows=[], project_characters=[], current_chapters=changed,
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
            # The only Character Register row is for a future volume, but the
            # current book already has confirmed assignments for both dialogue
            # spans. Blank workbook cells may preserve these exact assignments.
            registry_rows = [{
                "id": "library-mira", "series": "Silver Archive",
                "primary_name": "Mira", "aliases": ["Captain Mira"],
            }]
            for chapter in chapters:
                for passage in chapter["current_passages"]:
                    if passage["kind"] == "character_dialogue":
                        chapter["current_assignments"].append({
                            "start": passage["start"], "end": passage["end"],
                            "text": passage["text"], "speakers": ["Mira"],
                            "source": "manual", "series": "Silver Archive",
                        })
            plan = plan_complete_book_character_workbook_import(
                document, series="Silver Archive", book_title="The Silver Archive",
                registry_rows=registry_rows, project_characters=[], current_chapters=chapters,
            )
            self.assertTrue(plan["ready"], plan["issues"])
            self.assertEqual(plan["characters"], [])
            self.assertEqual(plan["summary"]["new_characters"], 0)
            self.assertEqual(plan["summary"]["dialogue_assignments"], 0)



if __name__ == "__main__":
    unittest.main()
