from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.character_library import list_characters
from app.core.character_workbook import character_workbook_plan_fingerprint
from app.ui import premium_v2_host as host


class _WorkbookCommitBridge:
    _character_workbook_import_commit = host.PremiumV2Bridge._character_workbook_import_commit

    def __init__(self, project, chapter, state, plan, session):
        self.project = project
        self.chapter = chapter
        self.state = state
        self.plan = plan
        self._character_review_state_lock = threading.RLock()
        self._character_workbook_import_sessions = {"preview-token": dict(session)}

    def _active_project(self):
        return self.project

    def _project_series_name(self, _project, _state=None):
        return "Silver Archive"

    def _now(self):
        return "2026-11-22T12:00:00+00:00"

    def _character_workbook_import_plan(self, _project, _document):
        return self.state, "Silver Archive", self.chapter, self.plan


class CharacterWorkbookImportTransactionTests(unittest.TestCase):
    def _fixture(self, folder: Path):
        series = "Silver Archive"
        line = "“Captain Mira, are you ready?”"
        chapter = SimpleNamespace(
            number=1, title="The Arrival", chapter_id="chapter-001",
            text=line, dialogue_assignments=[],
        )
        project = SimpleNamespace(
            folder=folder, title="The Silver Archive", chapters=[chapter],
        )
        state = {"characters": [], "modified_at": ""}
        plan = {
            "ready": True, "issues": [],
            "characters": [{
                "canonical_name": "Mira", "identity_base_name": "Mira",
                "identity_variant": "", "aliases": ["Captain Mira"],
                "aliases_to_add": ["Captain Mira"], "notes": "Confirmed by GPT",
                "library_id": "", "existing_voice_name": "",
                "action": "create", "series": series,
            }],
            "assignments": [{
                "passage_id": "passage-001", "chapter_id": "chapter-001",
                "start": 0, "end": len(line), "text": line,
                "speaker": "Mira", "series": series, "confidence": 0.92,
            }],
            "summary": {
                "matched_characters": 0, "new_characters": 1,
                "aliases_to_merge": 1, "dialogue_assignments": 1,
            },
        }
        workbook_path = folder / "gpt-completed.xlsx"
        workbook_path.write_bytes(b"test xlsx bytes")
        workbook_sha = hashlib.sha256(workbook_path.read_bytes()).hexdigest()
        document = {"sha256": workbook_sha, "info": {"Export ID": "export-001"}}
        session = {
            "path": str(workbook_path.resolve()),
            "sha256": workbook_sha,
            "project_folder": str(folder.resolve()),
            "export_id": "export-001",
            "chapter_number": 1,
            "plan_sha256": character_workbook_plan_fingerprint(plan),
        }
        bridge = _WorkbookCommitBridge(project, chapter, state, plan, session)
        return bridge, project, chapter, state, plan, document

    def test_commit_persists_character_identity_and_outsourced_dialogue(self):
        with tempfile.TemporaryDirectory(prefix="ryu-workbook-commit-") as tmp:
            folder = Path(tmp)
            bridge, project, chapter, state, _plan, document = self._fixture(folder)
            library = folder / "character-library.json"
            library.write_text(json.dumps({"version": 1, "active": [], "deleted": []}), encoding="utf-8")

            def save_project():
                (folder / "project.json").write_text("project saved", encoding="utf-8")
                (folder / "chapters.json").write_text("chapters saved", encoding="utf-8")

            project.save = Mock(side_effect=save_project)

            def save_project_state(project_folder, payload):
                (Path(project_folder) / "state.json").write_text(
                    json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
                )

            with (
                patch.object(host, "reusable_character_library_path", return_value=library),
                patch.object(host, "read_character_workbook", return_value=document),
                patch.object(host, "save_state", side_effect=save_project_state),
            ):
                result = bridge._character_workbook_import_commit({"token": "preview-token"})

            self.assertTrue(result["imported"])
            self.assertEqual(result["characters_created"], 1)
            self.assertEqual(result["dialogue_assignments"], 1)
            saved = list_characters(series="Silver Archive", path=library)
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["primary_name"], "Mira")
            self.assertEqual(saved[0]["aliases"], ["Captain Mira"])
            self.assertTrue(saved[0]["imported_from_workbook"])
            self.assertEqual(chapter.dialogue_assignments[0]["source"], "outsourced")
            self.assertAlmostEqual(chapter.dialogue_assignments[0]["confidence"], 0.92)
            self.assertEqual(len(state["characters"]), 1)
            self.assertEqual(state["characters"][0]["character_origin"], "outsourced")
            self.assertEqual(state["characters"][0]["character_library_id"], saved[0]["id"])
            self.assertEqual(state["characters"][0]["identity_variant"], "")

    def test_complete_book_import_adds_new_alias_to_library_and_preserves_local_voice(self):
        with tempfile.TemporaryDirectory(prefix="ryu-workbook-alias-commit-") as tmp:
            folder = Path(tmp)
            first_line = "“Mira, listen!”"
            first = SimpleNamespace(
                number=1, title="The Arrival", chapter_id="chapter-001",
                text=first_line, dialogue_assignments=[],
            )
            project = SimpleNamespace(
                folder=folder, title="The Silver Archive", chapters=[first],
            )
            state = {"characters": [{
                "name": "Mira", "series": "Silver Archive",
                "aliases": ["Captain Mira"],
                "voice_profile": "Saved Qwen Mira Profile",
                "voice_profile_id": "qwen-profile-123",
                "voice_model": "Qwen3-TTS-0.6B",
            }], "modified_at": ""}
            library = folder / "character-library.json"
            from app.core.character_library import sync_characters
            sync_characters(
                "Silver Archive",
                [{"name": "Mira", "aliases": ["Captain Mira"], "voice": "Local Library Mira Voice"}],
                path=library,
            )
            existing_library = list_characters(series="Silver Archive", path=library)[0]
            plan = {
                "ready": True, "issues": [], "scope": "book",
                "book_revision": "book-revision",
                "chapters": [{
                    "chapter_id": "chapter-001", "chapter_number": 1,
                    "chapter_title": "The Arrival",
                }],
                "characters": [{
                    "canonical_name": "Mira", "identity_base_name": "Mira",
                    "identity_variant": "", "aliases": ["Captain Mira", "Mira-sama"],
                    "aliases_to_add": ["Mira-sama"], "notes": "Confirmed alias",
                    "library_id": existing_library["id"],
                    "existing_voice_name": "Local Library Mira Voice",
                    "action": "merge", "series": "Silver Archive",
                }],
                "assignments": [{
                    "passage_id": "passage-001", "chapter_id": "chapter-001",
                    "chapter_number": 1, "start": 0, "end": len(first_line),
                    "text": first_line, "speaker": "Mira",
                    "series": "Silver Archive", "confidence": 0.97,
                }],
                "summary": {
                    "matched_characters": 1, "new_characters": 0,
                    "aliases_to_merge": 1, "dialogue_assignments": 1,
                    "chapters": 1,
                },
            }
            workbook_path = folder / "complete-book.xlsx"
            workbook_path.write_bytes(b"complete book workbook")
            workbook_sha = hashlib.sha256(workbook_path.read_bytes()).hexdigest()
            document = {"sha256": workbook_sha, "info": {"Export ID": "export-book-alias"}}
            session = {
                "path": str(workbook_path.resolve()), "sha256": workbook_sha,
                "project_folder": str(folder.resolve()), "export_id": "export-book-alias",
                "scope": "book", "book_revision": "book-revision",
                "plan_sha256": character_workbook_plan_fingerprint(plan),
            }
            bridge = _WorkbookCommitBridge(project, first, state, plan, session)

            def save_project():
                (folder / "project.json").write_text("project saved", encoding="utf-8")
                (folder / "chapters.json").write_text("chapters saved", encoding="utf-8")
            project.save = Mock(side_effect=save_project)

            def save_project_state(project_folder, payload):
                (Path(project_folder) / "state.json").write_text(
                    json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
                )

            with (
                patch.object(host, "reusable_character_library_path", return_value=library),
                patch.object(host, "read_character_workbook", return_value=document),
                patch.object(host, "save_state", side_effect=save_project_state),
            ):
                result = bridge._character_workbook_import_commit({"token": "preview-token"})

            saved_library = list_characters(series="Silver Archive", path=library)
            self.assertTrue(result["imported"])
            self.assertEqual(result["aliases_merged"], 1)
            self.assertEqual(len(saved_library), 1)
            self.assertEqual(saved_library[0]["primary_name"], "Mira")
            self.assertTrue({"Captain Mira", "Mira-sama"}.issubset(set(saved_library[0]["aliases"])))
            self.assertEqual(saved_library[0]["voice_name"], "Local Library Mira Voice")
            self.assertEqual(state["characters"][0]["name"], "Mira")
            self.assertTrue({"Captain Mira", "Mira-sama"}.issubset(set(state["characters"][0]["aliases"])))
            self.assertEqual(state["characters"][0]["voice_profile"], "Saved Qwen Mira Profile")
            self.assertEqual(state["characters"][0]["voice_profile_id"], "qwen-profile-123")
            self.assertEqual(first.dialogue_assignments[0]["speaker"], "Mira")

    def test_failed_save_rolls_back_library_files_and_live_chapter_assignments(self):
        with tempfile.TemporaryDirectory(prefix="ryu-workbook-rollback-") as tmp:
            folder = Path(tmp)
            bridge, project, chapter, _state, _plan, document = self._fixture(folder)
            library = folder / "character-library.json"
            original_library = b'{"version":1,"active":[],"deleted":[]}'
            library.write_bytes(original_library)
            snapshots = {
                "project.json": b"old project",
                "chapters.json": b"old chapters",
                "state.json": b"old state",
            }
            for name, content in snapshots.items():
                (folder / name).write_bytes(content)

            def partially_save_project():
                (folder / "project.json").write_bytes(b"new project")
                (folder / "chapters.json").write_bytes(b"new chapters")

            project.save = Mock(side_effect=partially_save_project)

            def fail_after_partial_state_write(project_folder, _payload):
                (Path(project_folder) / "state.json").write_bytes(b"partial state")
                raise OSError("simulated state.json disk failure")

            with (
                patch.object(host, "reusable_character_library_path", return_value=library),
                patch.object(host, "read_character_workbook", return_value=document),
                patch.object(host, "save_state", side_effect=fail_after_partial_state_write),
            ):
                with self.assertRaisesRegex(OSError, "simulated state.json"):
                    bridge._character_workbook_import_commit({"token": "preview-token"})

            self.assertEqual(library.read_bytes(), original_library)
            for name, content in snapshots.items():
                self.assertEqual((folder / name).read_bytes(), content)
            self.assertEqual(chapter.dialogue_assignments, [])

    def test_commit_refuses_identity_plan_changes_after_confirmation(self):
        with tempfile.TemporaryDirectory(prefix="ryu-workbook-stale-plan-") as tmp:
            folder = Path(tmp)
            bridge, project, chapter, _state, plan, document = self._fixture(folder)
            library = folder / "character-library.json"
            original_library = b'{"version":1,"active":[],"deleted":[]}'
            library.write_bytes(original_library)
            bridge.plan = {
                **plan,
                "characters": [{
                    **plan["characters"][0],
                    "canonical_name": "Ren",
                    "aliases": ["Captain Mira"],
                }],
            }
            project.save = Mock()

            with (
                patch.object(host, "reusable_character_library_path", return_value=library),
                patch.object(host, "read_character_workbook", return_value=document),
            ):
                with self.assertRaisesRegex(ValueError, "changed after preview"):
                    bridge._character_workbook_import_commit({"token": "preview-token"})

            project.save.assert_not_called()
            self.assertEqual(library.read_bytes(), original_library)
            self.assertEqual(chapter.dialogue_assignments, [])


    def test_complete_book_commit_applies_assignments_to_each_chapter_atomically(self):
        with tempfile.TemporaryDirectory(prefix="ryu-workbook-book-commit-") as tmp:
            folder = Path(tmp)
            first_line = "“Mira, listen!”"
            second_line = "“Captain Mira, wait!”"
            first = SimpleNamespace(
                number=1, title="The Arrival", chapter_id="chapter-001",
                text=first_line, dialogue_assignments=[],
            )
            second = SimpleNamespace(
                number=2, title="The Warning", chapter_id="chapter-002",
                text=second_line, dialogue_assignments=[],
            )
            project = SimpleNamespace(
                folder=folder, title="The Silver Archive", chapters=[first, second],
            )
            state = {"characters": [{
                "name": "Mira", "series": "Silver Archive",
                "aliases": ["Captain Mira"],
                "voice_profile": "Saved Qwen Mira Profile",
                "voice_profile_id": "qwen-profile-123",
                "voice_model": "Qwen3-TTS-0.6B",
            }], "modified_at": ""}
            plan = {
                "ready": True, "issues": [], "scope": "book", "book_revision": "book-revision",
                "chapters": [
                    {"chapter_id": "chapter-001", "chapter_number": 1, "chapter_title": "The Arrival"},
                    {"chapter_id": "chapter-002", "chapter_number": 2, "chapter_title": "The Warning"},
                ],
                "characters": [{
                    "canonical_name": "Mira", "identity_base_name": "Mira",
                    "identity_variant": "", "aliases": ["Captain Mira"],
                    "aliases_to_add": ["Captain Mira"], "notes": "Confirmed in both chapters",
                    "library_id": "", "existing_voice_name": "",
                    "action": "create", "series": "Silver Archive",
                }],
                "assignments": [
                    {
                        "passage_id": "passage-001", "chapter_id": "chapter-001",
                        "chapter_number": 1, "start": 0, "end": len(first_line),
                        "text": first_line, "speaker": "Mira", "series": "Silver Archive",
                        "confidence": 0.95,
                    },
                    {
                        "passage_id": "passage-002", "chapter_id": "chapter-002",
                        "chapter_number": 2, "start": 0, "end": len(second_line),
                        "text": second_line, "speaker": "Mira", "series": "Silver Archive",
                        "confidence": 0.93,
                    },
                ],
                "summary": {
                    "matched_characters": 0, "new_characters": 1,
                    "aliases_to_merge": 1, "dialogue_assignments": 2, "chapters": 2,
                },
            }
            workbook_path = folder / "complete-book.xlsx"
            workbook_path.write_bytes(b"complete book workbook")
            workbook_sha = hashlib.sha256(workbook_path.read_bytes()).hexdigest()
            document = {"sha256": workbook_sha, "info": {"Export ID": "export-book-001"}}
            session = {
                "path": str(workbook_path.resolve()),
                "sha256": workbook_sha,
                "project_folder": str(folder.resolve()),
                "export_id": "export-book-001",
                "scope": "book",
                "book_revision": "book-revision",
                "plan_sha256": character_workbook_plan_fingerprint(plan),
            }
            bridge = _WorkbookCommitBridge(project, first, state, plan, session)
            library = folder / "character-library.json"
            library.write_text(json.dumps({"version": 1, "active": [], "deleted": []}), encoding="utf-8")

            def save_project():
                (folder / "project.json").write_text("project saved", encoding="utf-8")
                (folder / "chapters.json").write_text("chapters saved", encoding="utf-8")

            project.save = Mock(side_effect=save_project)

            def save_project_state(project_folder, payload):
                (Path(project_folder) / "state.json").write_text(
                    json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
                )

            with (
                patch.object(host, "reusable_character_library_path", return_value=library),
                patch.object(host, "read_character_workbook", return_value=document),
                patch.object(host, "save_state", side_effect=save_project_state),
            ):
                result = bridge._character_workbook_import_commit({"token": "preview-token"})

            self.assertTrue(result["imported"])
            self.assertEqual(result["scope"], "book")
            self.assertEqual(result["chapter_count"], 2)
            self.assertEqual(result["chapters_updated"], 2)
            self.assertEqual(result["dialogue_assignments"], 2)
            self.assertEqual(len(first.dialogue_assignments), 1)
            self.assertEqual(len(second.dialogue_assignments), 1)
            self.assertEqual(first.dialogue_assignments[0]["source"], "outsourced")
            self.assertEqual(second.dialogue_assignments[0]["source"], "outsourced")
            self.assertEqual(first.dialogue_assignments[0]["speaker"], "Mira")
            self.assertEqual(second.dialogue_assignments[0]["speaker"], "Mira")
            self.assertEqual(len(state["characters"]), 1)
            self.assertEqual(state["characters"][0]["character_library_id"], list_characters(series="Silver Archive", path=library)[0]["id"])
            self.assertEqual(state["characters"][0]["voice_profile"], "Saved Qwen Mira Profile")
            self.assertEqual(state["characters"][0]["voice_profile_id"], "qwen-profile-123")
            self.assertEqual(state["characters"][0]["voice_model"], "Qwen3-TTS-0.6B")



if __name__ == "__main__":
    unittest.main()
