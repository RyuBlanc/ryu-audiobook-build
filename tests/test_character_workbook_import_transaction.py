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
    def test_manual_assignment_replaces_only_stale_broad_ai_span_and_persists_passage_identity(self):
        with tempfile.TemporaryDirectory(prefix="ryu-manual-child-assignment-") as tmp:
            folder = Path(tmp)
            source = '“Hello, Mira!” “How are you?”'
            first = '“Hello, Mira!”'
            second = '“How are you?”'
            first_start = source.index(first)
            second_start = source.index(second)
            revision = "revision-current-002"
            stale_parent = {
                "start": first_start,
                "end": len(source),
                "text": source,
                "speaker": "Legacy AI",
                "source": "ai",
                "confidence": 0.51,
            }
            chapter = SimpleNamespace(
                number=1,
                title="The Opening",
                chapter_id="chapter-001",
                text=source,
                dialogue_assignments=[stale_parent],
            )
            project = SimpleNamespace(
                folder=folder,
                title="The Silver Archive",
                chapters=[chapter],
                save=Mock(),
            )
            state = {
                "characters": [{
                    "name": "Mira",
                    "series": "Silver Archive",
                    "aliases": ["Captain Mira"],
                }],
                "character_dialogue_suggestions": [],
            }
            passage_index = {
                "passages": [
                    {
                        "passage_id": "ps-first",
                        "chapter_id": "chapter-001",
                        "chapter_revision": revision,
                        "start": first_start,
                        "end": first_start + len(first),
                        "text": first,
                    },
                    {
                        "passage_id": "ps-second",
                        "chapter_id": "chapter-001",
                        "chapter_revision": revision,
                        "start": second_start,
                        "end": second_start + len(second),
                        "text": second,
                    },
                ]
            }

            class _Bridge:
                _chapter_dialogue_assign = host.PremiumV2Bridge._chapter_dialogue_assign

                def __init__(self):
                    self._character_review_state_lock = threading.RLock()

                def _active_project(self):
                    return project

                def _project_series_name(self, _project, _state=None):
                    return "Silver Archive"

                def _now(self):
                    return "2026-11-25T17:00:00+00:00"

            bridge = _Bridge()
            with (
                patch.object(host, "load_state", side_effect=[state, state]),
                patch.object(host, "save_state") as save_project_state,
                patch(
                    "app.chapters.passage_index.load_or_build_passage_index",
                    return_value=passage_index,
                ),
                patch("app.chapters.character_learning.record_assignment_feedback"),
            ):
                result = bridge._chapter_dialogue_assign({
                    "dialogue_text": first,
                    "speakers": ["Mira"],
                    "series": "Silver Archive",
                    "chapter_number": 1,
                    "start": first_start,
                    "end": first_start + len(first),
                    "passage_id": "ps-first",
                    "chapter_revision": revision,
                    "mode": "single",
                    "source": "manual",
                    "confidence": 1.0,
                })

            self.assertTrue(result["saved"])
            self.assertEqual(len(chapter.dialogue_assignments), 1)
            saved = chapter.dialogue_assignments[0]
            self.assertEqual(saved["source"], "manual")
            self.assertEqual(saved["speaker"], "Mira")
            self.assertEqual(saved["passage_id"], "ps-first")
            self.assertEqual(saved["chapter_revision"], revision)
            self.assertEqual((saved["start"], saved["end"]), (first_start, first_start + len(first)))
            project.save.assert_called_once_with()
            save_project_state.assert_called_once()

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
                "chapter_revision": "revision-1",
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


    def test_commit_applies_gpt_source_text_proposal_and_rebases_manual_speaker_assignment(self):
        with tempfile.TemporaryDirectory(prefix="ryu-workbook-text-correction-commit-") as tmp:
            folder = Path(tmp)
            bridge, project, chapter, _state, plan, document = self._fixture(folder)
            original_text = str(chapter.text)
            corrected_text = "“Mira, are you ready?”"
            chapter.dialogue_assignments = [{
                "start": 0, "end": len(original_text), "text": original_text,
                "speaker": "Mira", "speakers": ["Mira"], "source": "manual",
                "series": "Silver Archive", "confidence": 1.0,
                "passage_id": "old-passage-id", "chapter_revision": "old-revision",
            }]
            plan["characters"] = []
            plan["assignments"] = []
            plan["superseded_assignments"] = []
            plan["text_corrections"] = [{
                "passage_id": "old-passage-id", "chapter_id": "chapter-001",
                "chapter_number": 1, "chapter_title": "The Arrival",
                "chapter_revision": "revision-1", "passage_type": "Dialogue",
                "start": 0, "end": len(original_text),
                "source_text": original_text, "proposed_text": corrected_text,
                "reason": "Corrected the source transcription without changing the speaker.",
            }]
            plan["passage_reclassifications"] = []
            plan["summary"] = {
                "matched_characters": 0, "new_characters": 0,
                "aliases_to_merge": 0, "dialogue_assignments": 0,
                "saved_assignments_replaced": 0, "passage_reclassifications": 0,
                "text_corrections": 1, "third_person_assignments": 0,
            }
            bridge._character_workbook_import_sessions["preview-token"]["plan_sha256"] = (
                character_workbook_plan_fingerprint(plan)
            )
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
            self.assertEqual(result["text_corrections_applied"], 1)
            self.assertEqual(chapter.text, corrected_text)
            self.assertEqual(len(chapter.dialogue_assignments), 1)
            saved = chapter.dialogue_assignments[0]
            self.assertEqual(saved["speaker"], "Mira")
            self.assertEqual(saved["speakers"], ["Mira"])
            self.assertEqual(saved["source"], "manual")
            self.assertEqual(saved["text"], corrected_text)
            self.assertEqual((saved["start"], saved["end"]), (0, len(corrected_text)))
            self.assertNotIn("passage_id", saved)
            self.assertNotIn("chapter_revision", saved)
            project.save.assert_called_once_with()

    def test_commit_persists_multiple_speakers_and_split_source_metadata(self):
        with tempfile.TemporaryDirectory(prefix="ryu-workbook-multi-speaker-commit-") as tmp:
            folder = Path(tmp)
            bridge, project, chapter, state, plan, document = self._fixture(folder)
            line = str(chapter.text)
            plan["characters"].append({
                "canonical_name": "Rina", "identity_base_name": "Rina",
                "identity_variant": "", "aliases": [], "aliases_to_add": [], "notes": "Confirmed",
                "library_id": "", "existing_voice_name": "", "action": "create", "series": "Silver Archive",
            })
            plan["assignments"] = [{
                "passage_id": "passage-001::subturn-1", "chapter_id": "chapter-001",
                "chapter_revision": "revision-1",
                "start": 0, "end": len(line), "text": line, "speaker": "Mira",
                "speakers": ["Mira", "Rina"], "multi_speaker_mode": "chorus",
                "series": "Silver Archive", "confidence": 0.98,
                "source_passage_id": "passage-001", "source_passage_text": line,
                "source_passage_start": 0, "source_passage_end": len(line),
                "source_context_before": "The previous sentence.", "source_context_after": "The following sentence.",
                "source_start_relative": 0, "source_end_relative": len(line),
            }]
            plan["summary"]["new_characters"] = 2
            plan["summary"]["dialogue_assignments"] = 1
            bridge._character_workbook_import_sessions["preview-token"]["plan_sha256"] = (
                character_workbook_plan_fingerprint(plan)
            )
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
            self.assertEqual(result["dialogue_assignments"], 1)
            saved = chapter.dialogue_assignments[0]
            self.assertEqual(saved["speaker"], "Mira")
            self.assertEqual(saved["speakers"], ["Mira", "Rina"])
            self.assertEqual(saved["multi_speaker_mode"], "chorus")
            self.assertEqual(saved["passage_id"], "passage-001::subturn-1")
            self.assertEqual(saved["chapter_revision"], "revision-1")
            self.assertEqual(saved["source_passage_id"], "passage-001")
            self.assertEqual(saved["source_passage_text"], line)
            self.assertEqual(saved["source_start_relative"], 0)
            self.assertEqual(saved["source_end_relative"], len(line))
            self.assertEqual(saved["source_context_before"], "The previous sentence.")
            self.assertEqual(saved["source_context_after"], "The following sentence.")

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

    def test_commit_persists_narrator_only_stale_ai_cleanup_without_new_dialogue_rows(self):
        with tempfile.TemporaryDirectory(prefix="ryu-workbook-narrator-cleanup-") as tmp:
            folder = Path(tmp)
            bridge, project, chapter, state, plan, document = self._fixture(folder)
            stale_text = str(chapter.text)
            chapter.dialogue_assignments = [{
                "start": 0, "end": len(stale_text), "text": stale_text,
                "speaker": "Legacy AI speaker", "source": "ai",
            }]
            plan["assignments"] = []
            plan["superseded_assignments"] = [{
                "chapter_id": "chapter-001",
                "start": 0, "end": len(stale_text),
                "text": stale_text, "source": "ai",
                "speakers": ["Legacy AI speaker"],
            }]
            plan["summary"]["dialogue_assignments"] = 0
            plan["summary"]["saved_assignments_replaced"] = 1
            bridge._character_workbook_import_sessions["preview-token"]["plan_sha256"] = (
                character_workbook_plan_fingerprint(plan)
            )

            library = folder / "character-library.json"
            library.write_text(
                json.dumps({"version": 1, "active": [], "deleted": []}),
                encoding="utf-8",
            )

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
            self.assertEqual(result["dialogue_assignments"], 0)
            self.assertEqual(result["saved_assignments_replaced"], 1)
            self.assertEqual(result["chapters_updated"], 1)
            self.assertEqual(chapter.dialogue_assignments, [])
            self.assertTrue(project.save.called)

    def test_refreshed_workbook_save_cannot_overwrite_the_original_gpt_workbook(self):
        with tempfile.TemporaryDirectory(prefix="ryu-workbook-refresh-safe-save-") as tmp:
            folder = Path(tmp)
            original = folder / "completed.xlsx"
            original.write_bytes(b"original GPT workbook")
            original_bytes = original.read_bytes()
            chapter = SimpleNamespace(
                number=1, title="The Arrival", chapter_id="chapter-001",
                text="“Mira, listen!”", dialogue_assignments=[],
            )
            project = SimpleNamespace(
                folder=folder, title="The Silver Archive", chapters=[chapter],
            )
            state = {
                "author": "", "publisher": "", "language": "", "genre": "",
                "year": "", "series_volume": "",
            }
            book_chapters = [{
                "chapter_id": "chapter-001", "chapter_number": 1,
                "chapter_title": "The Arrival", "chapter_revision": "revision-001",
                "text": chapter.text, "current_passages": [], "current_assignments": [],
            }]

            class _RefreshBridge:
                _character_workbook_refresh_after_segmentation = (
                    host.PremiumV2Bridge._character_workbook_refresh_after_segmentation
                )

                def _character_workbook_book_snapshot(self, _project):
                    return state, "Silver Archive", book_chapters

                def _character_library_bootstrap(self):
                    return None

                def _character_workbook_dialog_parent(self):
                    return None

            bridge = _RefreshBridge()
            with (
                patch.object(host, "list_reusable_characters", return_value=[]),
                patch.object(
                    host, "refresh_complete_book_character_workbook_bytes",
                    return_value=(b"refreshed workbook", {"gpt_assignments_carried": 0}),
                ),
                patch.object(host.QFileDialog, "getSaveFileName", return_value=(str(original), "")),
            ):
                with self.assertRaisesRegex(ValueError, "original GPT-completed workbook is protected"):
                    bridge._character_workbook_refresh_after_segmentation(
                        project, {"schema_version": 2}, str(original)
                    )

            self.assertEqual(original.read_bytes(), original_bytes)
            self.assertEqual(list(folder.iterdir()), [original])

    def test_import_preview_routes_segmentation_mismatch_to_safe_workbook_refresh(self):
        class _RefreshPreviewBridge:
            _character_workbook_import_preview = host.PremiumV2Bridge._character_workbook_import_preview

            def _character_workbook_dialog_parent(self):
                return None

            def _active_project(self):
                return object()

            def _character_workbook_import_plan(self, _project, _document):
                raise ValueError(
                    "Chapter 1 dialogue/narration segmentation changed after workbook export "
                    "(workbook: 10 passages; active project: 11)."
                )

            def _character_workbook_refresh_after_segmentation(self, _project, document, selected_path):
                return {
                    "cancelled": False, "refreshed": True,
                    "path": selected_path.replace(".xlsx", "_Refreshed.xlsx"),
                    "gpt_assignments_carried": 8,
                }

        bridge = _RefreshPreviewBridge()
        document = {"schema_version": 2, "info": {"Export Scope": "complete_book"}}
        with (
            patch.object(host.QFileDialog, "getOpenFileName", return_value=("completed.xlsx", "")),
            patch.object(host, "read_character_workbook", return_value=document),
        ):
            result = bridge._character_workbook_import_preview({})

        self.assertTrue(result["refreshed"])
        self.assertEqual(result["gpt_assignments_carried"], 8)
        self.assertEqual(result["path"], "completed_Refreshed.xlsx")

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

    def test_commit_replaces_reviewed_stale_ai_overlap_but_preserves_unrelated_manual_assignment(self):
        with tempfile.TemporaryDirectory(prefix="ryu-workbook-replace-stale-ai-") as tmp:
            folder = Path(tmp)
            bridge, project, chapter, state, plan, document = self._fixture(folder)
            line = str(chapter.text)
            other_line = "“Ren, I am here.”"
            chapter.text = line + "\n" + other_line
            other_start = len(line) + 1
            preserved_manual = {
                "start": other_start, "end": other_start + len(other_line),
                "text": other_line, "speaker": "Ren", "source": "manual",
            }
            stale_ai = {
                "start": 0, "end": len(line) + 1,
                "text": line + "\n", "speaker": "Legacy AI speaker", "source": "ai",
            }
            chapter.dialogue_assignments = [stale_ai, preserved_manual]
            plan["superseded_assignments"] = [{
                "chapter_id": "chapter-001", "start": 0, "end": len(line) + 1,
                "source": "ai", "speakers": ["Legacy AI speaker"], "text": line + "\n",
            }]
            plan["summary"]["saved_assignments_replaced"] = 1
            bridge._character_workbook_import_sessions["preview-token"]["plan_sha256"] = (
                character_workbook_plan_fingerprint(plan)
            )
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
            self.assertEqual(result["saved_assignments_replaced"], 1)
            self.assertEqual(len(chapter.dialogue_assignments), 2)
            self.assertFalse(any(
                row.get("source") == "ai" and row.get("start") == 0
                for row in chapter.dialogue_assignments
            ))
            self.assertTrue(any(
                row.get("source") == "outsourced" and row.get("speaker") == "Mira"
                for row in chapter.dialogue_assignments
            ))
            self.assertIn(preserved_manual, chapter.dialogue_assignments)

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
