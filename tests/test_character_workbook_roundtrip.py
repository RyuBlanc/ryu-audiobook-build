from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from app.core.character_library import (
    list_characters,
    merge_imported_character_records,
)
from app.core.character_workbook import (
    create_character_workbook_bytes,
    plan_character_workbook_import,
    read_character_workbook,
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
                "full_name": "Captain Mira", "aliases": ["The Captain"],
                "version": "", "notes": "",
            }]
            document["dialogue_rows"][1]["GPT Assigned Character"] = "Captain Mira"
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


    def test_dialogue_speaker_must_appear_in_character_register(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _text, passages = self._export(Path(tmp))
            document = read_character_workbook(path)
            document["dialogue_rows"][1]["GPT Assigned Character"] = "Mira"
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


if __name__ == "__main__":
    unittest.main()
