"""Stage D1 schema, compatibility and revision-contract regressions."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.tts.profile_provider import ProfileBoundProvider
from app.tts.qwen_profile_schema import (
    CURRENT_QWEN_PROFILE_SCHEMA_VERSION,
    QWEN_MODEL_IDS,
    qwen_model_compatibility,
    qwen_profile_revision_id,
)
from app.tts.voice_profile import VoiceProfile, load_saved_profiles, save_profiles


class QwenProfileSchemaTests(unittest.TestCase):
    def test_legacy_qwen_record_gets_schema_version_and_identity_is_kept(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Voices"
            root.mkdir()
            record = {
                "name": "Legacy Japanese Design",
                "provider": "qwen-character",
                "voice_id": "design-legacy",
                "model_id": "design-1.7b",
                "backend": "automatic",
                "language": "Japanese",
                "qwen_mode": "design",
                "qwen_prompt": "Calm Japanese voice.",
                "qwen_seed": 17001,
                "qwen_profile_id": "legacy-design-id",
            }
            (root / "voices.json").write_text(json.dumps([record]), encoding="utf-8")
            with patch("app.tts.voice_profile.voices_root", return_value=root):
                loaded = load_saved_profiles()
                self.assertEqual(len(loaded), 1)
                self.assertEqual(loaded[0].qwen_profile_id, "legacy-design-id")
                self.assertEqual(loaded[0].qwen_profile_schema_version, CURRENT_QWEN_PROFILE_SCHEMA_VERSION)
                migrated = json.loads((root / "voices.json").read_text(encoding="utf-8"))[0]
                self.assertEqual(migrated["qwen_profile_id"], "legacy-design-id")
                self.assertEqual(migrated["qwen_profile_schema_version"], CURRENT_QWEN_PROFILE_SCHEMA_VERSION)

    def test_unknown_future_fields_survive_load_and_save_without_nested_wrapping(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Voices"
            root.mkdir()
            future = {"anchor_pipeline": "v99", "custom_flags": ["identity-lock", "keep"]}
            record = {
                "name": "Future Compatible Profile",
                "provider": "qwen-character",
                "voice_id": "Ryan",
                "model_id": "custom-0.6b",
                "backend": "automatic",
                "language": "English",
                "qwen_mode": "custom",
                "qwen_profile_id": "future-compatible-id",
                "qwen_profile_schema_version": 99,
                "future_profile_metadata": future,
            }
            (root / "voices.json").write_text(json.dumps([record]), encoding="utf-8")
            with (
                patch("app.tts.voice_profile.voices_root", return_value=root),
                patch("app.tts.voice_profile.builtin_voice_profiles", return_value=[]),
            ):
                loaded = load_saved_profiles()
                self.assertEqual(loaded[0].extra_fields["future_profile_metadata"], future)
                self.assertEqual(loaded[0].qwen_profile_schema_version, 99)
                save_profiles(loaded)
            persisted = json.loads((root / "voices.json").read_text(encoding="utf-8"))[0]
            self.assertEqual(persisted["future_profile_metadata"], future)
            self.assertEqual(persisted["qwen_profile_schema_version"], 99)
            self.assertNotIn("extra_fields", persisted)

    def test_revision_is_independent_of_machine_local_paths_but_tracks_asset_hashes(self):
        first = VoiceProfile(
            name="Portable Clone", provider="qwen-character", voice_id="Clone",
            model_id="base-0.6b", language="English", qwen_mode="clone",
            qwen_profile_id="portable-clone-id", sample_path="C:/Source/Voices/Clone/reference.wav",
            reference_text="Hello there.",
        )
        moved = VoiceProfile(
            name="Portable Clone", provider="qwen-character", voice_id="Clone",
            model_id="base-0.6b", language="English", qwen_mode="clone",
            qwen_profile_id="portable-clone-id", sample_path="D:/Destination/Voices/Clone/reference.wav",
            reference_text="Hello there.",
        )
        original_digest = {"sample_path": "a" * 64}
        self.assertEqual(
            qwen_profile_revision_id(first, original_digest),
            qwen_profile_revision_id(moved, original_digest),
        )
        changed_asset = {"sample_path": "b" * 64}
        self.assertNotEqual(
            qwen_profile_revision_id(first, original_digest),
            qwen_profile_revision_id(moved, changed_asset),
        )
        moved.qwen_prompt = "A different voice instruction."
        self.assertNotEqual(
            qwen_profile_revision_id(first, original_digest),
            qwen_profile_revision_id(moved, original_digest),
        )

    def test_customvoice_model_compatibility_reports_variants_and_source_preference(self):
        profile = VoiceProfile(
            name="Custom", provider="qwen-character", voice_id="Ryan",
            model_id="auto", qwen_mode="custom",
        )
        requirements = qwen_model_compatibility(profile, "0.6b")
        model = requirements["required_models"][0]
        self.assertEqual(model["role"], "custom_voice")
        self.assertEqual(model["selected_source_model_kind"], "custom-0.6b")
        self.assertEqual(model["allowed_model_kinds"], ["custom-0.6b", "custom-1.7b"])
        self.assertEqual(model["upstream_model_ids"][0], QWEN_MODEL_IDS["custom-0.6b"])

    def test_clone_model_compatibility_uses_base_role(self):
        profile = VoiceProfile(
            name="Clone", provider="qwen-character", voice_id="Clone",
            model_id="auto", qwen_mode="clone",
        )
        requirements = qwen_model_compatibility(profile, "1.7b")
        model = requirements["required_models"][0]
        self.assertEqual(model["role"], "clone_base")
        self.assertEqual(model["selected_source_model_kind"], "base-1.7b")
        self.assertEqual(model["upstream_model_ids"][1], QWEN_MODEL_IDS["base-1.7b"])

    def test_voicedesign_requires_design_model_and_separates_long_form_base(self):
        profile = VoiceProfile(
            name="Design", provider="qwen-character", voice_id="design-voice",
            model_id="design-1.7b", qwen_mode="design", language="Japanese",
        )
        requirements = qwen_model_compatibility(profile, "0.6b")
        self.assertEqual(requirements["required_models"][0]["required_model_kind"], "design-1.7b")
        base = requirements["required_models"][1]
        self.assertEqual(base["role"], "long_form_base")
        self.assertEqual(base["selected_source_model_kind"], "base-0.6b")
        self.assertEqual(base["allowed_model_kinds"], ["base-0.6b", "base-1.7b"])

    def test_auto_voicedesign_does_not_claim_a_specific_destination_base_model(self):
        profile = VoiceProfile(
            name="Design", provider="qwen-character", voice_id="design-voice",
            model_id="design-1.7b", qwen_mode="design",
        )
        requirements = qwen_model_compatibility(profile, "auto")
        self.assertIsNone(requirements["required_models"][1]["selected_source_model_kind"])

    def test_schema_version_does_not_change_audio_generation_signature(self):
        class StubProvider:
            def generation_signature(self):
                return "same-engine"

        first = VoiceProfile(
            name="Signature", provider="qwen-character", voice_id="Ryan",
            qwen_mode="custom", qwen_profile_id="same-id",
            qwen_profile_schema_version=1,
        )
        migrated = VoiceProfile(
            name="Signature", provider="qwen-character", voice_id="Ryan",
            qwen_mode="custom", qwen_profile_id="same-id",
            qwen_profile_schema_version=99,
        )
        self.assertEqual(
            ProfileBoundProvider(StubProvider(), first).generation_signature(),
            ProfileBoundProvider(StubProvider(), migrated).generation_signature(),
        )


if __name__ == "__main__":
    unittest.main()
