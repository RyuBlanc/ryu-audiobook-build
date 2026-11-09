from __future__ import annotations

import ast
from pathlib import Path
import tempfile
import unittest

from app.tts.voice_profile import stable_qwen_profile_id


ROOT = Path(__file__).resolve().parents[1]


class QwenDraftIdentityRegressionTests(unittest.TestCase):
    def test_voice_design_draft_identity_is_stable_between_preview_and_save_inputs(self):
        arguments = {
            "mode": "design",
            "voice_id": "Ryan",
            "language": "English",
            "prompt": "Dynamic English anime hero with confident, expressive delivery.",
            "seed": 1103,
            "anchor_text": "A stable neutral voice identity sample.",
        }
        preview_identity = stable_qwen_profile_id(**arguments)
        saved_identity = stable_qwen_profile_id(**arguments)
        self.assertEqual(preview_identity, saved_identity)
        self.assertEqual(32, len(preview_identity))

    def test_voice_design_identity_changes_when_voice_defining_settings_change(self):
        base = {
            "mode": "design",
            "voice_id": "Ryan",
            "language": "English",
            "prompt": "Dynamic English anime hero.",
            "seed": 1103,
        }
        original = stable_qwen_profile_id(**base)
        changed_prompt = stable_qwen_profile_id(**{**base, "prompt": "Calm English anime rival."})
        changed_seed = stable_qwen_profile_id(**{**base, "seed": 1104})
        changed_speaker = stable_qwen_profile_id(**{**base, "voice_id": "Aiden"})
        self.assertNotEqual(original, changed_prompt)
        self.assertNotEqual(original, changed_seed)
        self.assertNotEqual(original, changed_speaker)

    def test_clone_identity_includes_reference_audio_signature_and_transcript(self):
        with tempfile.TemporaryDirectory() as temp:
            reference = Path(temp) / "voice.wav"
            reference.write_bytes(b"first-reference")
            base = {
                "mode": "clone",
                "voice_id": "saved-clone",
                "language": "English",
                "sample_path": str(reference),
                "reference_text": "Hello, this is the reference.",
            }
            first = stable_qwen_profile_id(**base)
            reference.write_bytes(b"changed-reference-content")
            second = stable_qwen_profile_id(**base)
            changed_text = stable_qwen_profile_id(**{**base, "reference_text": "A different transcript."})
        self.assertNotEqual(first, second)
        self.assertNotEqual(second, changed_text)

    def test_preview_and_save_paths_both_use_the_shared_stable_identity_helper(self):
        source = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        preview_start = source.index("    def _preview_profile_from_payload(")
        preview_end = source.index("    def _release_preview_provider(", preview_start)
        save_start = source.index("    def _voice_save(")
        save_end = source.index("    def _migrate_saved_voice_profile_references(", save_start)
        self.assertIn("stable_qwen_profile_id(", source[preview_start:preview_end])
        self.assertIn("stable_qwen_profile_id(", source[save_start:save_end])


class StartupAndNavigationRegressionTests(unittest.TestCase):
    def test_premium_entrypoint_does_not_eagerly_import_legacy_page_modules(self):
        source = (ROOT / "run_app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        top_level_imports = [
            node for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        imported = []
        for node in top_level_imports:
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif node.module:
                imported.append(node.module)
        self.assertFalse(any(name.startswith("app.ui.") for name in imported))

    def test_compatibility_workflow_is_imported_only_in_native_mode(self):
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        top_level_modules = [
            node.module for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module
        ]
        self.assertNotIn("app.ui.workflow", top_level_modules)
        self.assertIn('if ui_mode == "native":', source)
        self.assertIn("from app.ui.workflow import ProjectWorkflow", source)

    def test_voice_studio_does_not_await_cold_model_inventory_before_loading_profiles(self):
        source = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        start = source.index("async function refreshVoices()")
        end = source.index("function renderLiveChapterInsights()", start)
        refresh = source[start:end]
        self.assertIn("const inventoryTask = loadModelInventory(false)", refresh)
        self.assertIn("const loadedVoices = await call('voice.list')", refresh)
        self.assertNotIn("await loadModelInventory(false)", refresh)

    def test_qwen_preview_heartbeat_preserves_the_last_real_worker_phase(self):
        source = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        start = source.index("    def _preview_worker(")
        end = source.index("\n    def ", start + 12)
        worker = source[start:end]
        self.assertIn("preview_status_lock", worker)
        self.assertIn('current_stage = str(preview_status.get("stage")', worker)
        self.assertIn("stage=current_stage", worker)
        self.assertIn('current_detail = "Synthesis is still running"', worker)
        self.assertNotIn('job_id, stage="synthesizing",', worker)


    def test_startup_batches_durable_history_writes_instead_of_flushing_each_job(self):
        source = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        start = source.index("    def _load_durable_jobs(")
        end = source.index("\n    def _new_job(", start)
        loader = source[start:end]
        self.assertNotIn("self._record_history_job(row)", loader)
        self.assertIn("history_changed = False", loader)
        self.assertIn("if history_changed:", loader)
        self.assertEqual(1, loader.count("self._persist_history()"))
        self.assertEqual(1, loader.count("self._persist_jobs()"))


    def test_voice_design_preset_edits_clear_implicit_rename_target(self):
        source = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        start = source.index("const detachForEdit=()=>{")
        end = source.index("      };", start)
        detach = source[start:end]
        self.assertIn("profileEditOriginalName=''", detach)
        self.assertIn("selectedVoice=null", detach)
        self.assertNotIn("profileEditOriginalName=profile.name", detach)

    def test_voice_studio_preview_does_not_route_through_project_character_cast(self):
        source = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        start = source.index("async function previewVoice()")
        end = source.index("function setPlaybackButtonState()", start)
        preview = source[start:end]
        self.assertIn("route_character_cast:false", preview)


if __name__ == "__main__":
    unittest.main()
