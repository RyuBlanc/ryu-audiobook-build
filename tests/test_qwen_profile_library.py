"""Stage D4 saved Voice Library taxonomy, compatibility and asset-inspection tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch

from app.tts.voice_profile import VoiceProfile
from app.tts.voice_profile_library import (
    profile_asset_integrity,
    profile_library_category,
    profile_library_model_group,
    profile_library_record,
    profile_revision_history,
    qwen_profile_compatibility,
)


def write_wav(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = b"\x00\x00" * 2400
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(frames)
    return path.read_bytes()


class VoiceProfileLibraryTaxonomyTests(unittest.TestCase):
    def test_all_existing_library_categories_are_mapped_by_profile_mode(self):
        cases = [
            (VoiceProfile(name="Designed", provider="qwen-character", voice_id="Ryan",
                          qwen_mode="design"), "Designed"),
            (VoiceProfile(name="Cloned", provider="qwen-character", voice_id="clone",
                          qwen_mode="clone", sample_path="reference.wav"), "Cloned"),
            (VoiceProfile(name="CustomVoice", provider="qwen-character", voice_id="Serena",
                          qwen_mode="custom"), "Preset"),
            (VoiceProfile(name="Chatterbox clone", provider="chatterbox", voice_id="clone",
                          sample_path="reference.wav"), "Cloned"),
            (VoiceProfile(name="Cloud voice", provider="elevenlabs", voice_id="eleven"),
             "Cloud"),
            (VoiceProfile(name="Online voice", provider="edge-tts", voice_id="en-US-AvaNeural"),
             "Cloud"),
            (VoiceProfile(name="Piper preset", provider="piper", voice_id="en_US-amy-medium"),
             "Preset"),
            (VoiceProfile(name="Kokoro preset", provider="kokoro", voice_id="af_heart"),
             "Preset"),
            (VoiceProfile(name="Windows voice", provider="windows-sapi", voice_id="David"),
             "Preset"),
        ]
        for profile, expected in cases:
            with self.subTest(profile=profile.name):
                self.assertEqual(profile_library_category(profile), expected)

    def test_all_model_filter_groups_distinguish_qwen_modes_and_sizes(self):
        custom06 = VoiceProfile(
            name="Custom 06", provider="qwen-character", voice_id="Serena",
            model_id="custom-0.6b", qwen_mode="custom",
        )
        clone17 = VoiceProfile(
            name="Clone 17", provider="qwen-character", voice_id="Clone",
            model_id="base-1.7b", qwen_mode="clone",
        )
        design06 = VoiceProfile(
            name="Design 06", provider="qwen-character", voice_id="Ryan",
            model_id="auto", qwen_mode="design",
        )
        with patch("app.tts.qwen_model_preference.get_qwen_model_preference", return_value="auto"):
            self.assertEqual(profile_library_model_group(custom06), "Qwen3-TTS · CustomVoice 0.6B")
            self.assertEqual(profile_library_model_group(clone17), "Qwen3-TTS · Base 1.7B")
            design_group = profile_library_model_group(design06)
        self.assertIn("VoiceDesign 1.7B", design_group)
        self.assertIn("Auto", design_group)

        with patch("app.tts.qwen_model_preference.get_qwen_model_preference", return_value="0.6b"):
            design_group_06 = profile_library_model_group(design06)
        self.assertIn("VoiceDesign 1.7B", design_group_06)
        self.assertIn("Base 0.6B", design_group_06)

    def test_model_preference_is_never_reported_as_an_installed_model(self):
        profile = VoiceProfile(
            name="Missing custom model", provider="qwen-character",
            voice_id="Ryan", model_id="custom-0.6b", qwen_mode="custom",
        )
        with (
            patch("app.tts.qwen_model_preference.get_qwen_model_preference", return_value="0.6b"),
            patch("app.tts.qwen_model_preference.get_qwen_backend_preference", return_value="automatic"),
            patch("app.tts.qwen_character_runtime.model_installed", return_value=False),
            patch("app.tts.qwen_character_runtime.runtime_ready", return_value=False),
        ):
            result = qwen_profile_compatibility(profile)
        self.assertFalse(result["runtime_ready"])
        self.assertFalse(result["model_roles_ready"])
        self.assertEqual(result["status"], "Runtime missing or not ready")
        self.assertEqual(result["models"][0]["selected_model_kind"], "custom-0.6b")
        self.assertEqual(result["models"][0]["available_variants"], [])

    def test_auto_preference_reports_available_variants_without_silent_substitution(self):
        profile = VoiceProfile(
            name="Auto custom", provider="qwen-character",
            voice_id="Ryan", model_id="auto", qwen_mode="custom",
        )

        def installed(kind):
            return kind == "custom-1.7b"

        with (
            patch("app.tts.qwen_model_preference.get_qwen_model_preference", return_value="auto"),
            patch("app.tts.qwen_model_preference.get_qwen_backend_preference", return_value="cuda"),
            patch("app.tts.qwen_character_runtime.model_installed", side_effect=installed),
            patch("app.tts.qwen_character_runtime.runtime_ready", return_value=True),
        ):
            result = qwen_profile_compatibility(profile)
        self.assertTrue(result["runtime_ready"])
        self.assertTrue(result["model_roles_ready"])
        self.assertEqual(result["status"], "Ready")
        self.assertIsNone(result["models"][0]["selected_model_kind"])
        self.assertEqual(result["models"][0]["available_variants"], ["custom-1.7b"])
        self.assertEqual(result["backend_preference"], "cuda")

    def test_design_reports_both_design_and_long_form_base_roles(self):
        profile = VoiceProfile(
            name="Design profile", provider="qwen-character",
            voice_id="Ryan", model_id="auto", qwen_mode="design",
        )
        with (
            patch("app.tts.qwen_model_preference.get_qwen_model_preference", return_value="0.6b"),
            patch("app.tts.qwen_model_preference.get_qwen_backend_preference", return_value="automatic"),
            patch("app.tts.qwen_character_runtime.model_installed", return_value=True),
            patch("app.tts.qwen_character_runtime.runtime_ready", return_value=True),
        ):
            result = qwen_profile_compatibility(profile)
        self.assertTrue(result["model_roles_ready"])
        self.assertEqual(
            [item["role"] for item in result["models"]],
            ["voice_design", "long_form_base"],
        )
        self.assertEqual(result["models"][0]["selected_model_kind"], "design-1.7b")
        self.assertEqual(result["models"][1]["selected_model_kind"], "base-0.6b")

    def test_revision_history_reports_verified_snapshot_and_current_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            voices = Path(directory) / "Voices"
            profile = VoiceProfile(
                name="Revision history voice",
                provider="qwen-character",
                voice_id="Ryan",
                qwen_mode="custom",
                model_id="custom-0.6b",
                qwen_profile_id="d4-revision-history",
            )
            revision_dir = voices / "Qwen Profile Revisions" / profile.qwen_profile_id
            asset_path = revision_dir / "assets" / "previous-reference.wav"
            asset_bytes = write_wav(asset_path)
            old_revision = "a" * 64
            snapshot = {
                "profile_id": profile.qwen_profile_id,
                "revision_id": old_revision,
                "saved_at": "2026-11-14T10:00:00Z",
                "source_bundle_sha256": "b" * 64,
                "assets": [{
                    "snapshot_path": "assets/previous-reference.wav",
                    "sha256": hashlib.sha256(asset_bytes).hexdigest(),
                    "size_bytes": len(asset_bytes),
                    "role": "clone_reference_conditioning",
                }],
            }
            revision_dir.mkdir(parents=True, exist_ok=True)
            (revision_dir / (old_revision + ".json")).write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            with patch("app.core.paths.voices_root", return_value=voices):
                result = profile_revision_history(profile)
        self.assertRegex(result["current_revision_id"], r"^[0-9a-f]{64}$")
        self.assertEqual(result["history_count"], 1)
        self.assertEqual(result["verified_history_count"], 1)
        self.assertEqual(result["history"][0]["revision_id"], old_revision)
        self.assertTrue(result["history"][0]["integrity_valid"])
        self.assertEqual(result["history"][0]["status"], "Verified snapshot")
        self.assertNotIn(str(voices), str(result))

    def test_revision_history_marks_missing_or_modified_snapshot_assets_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            voices = Path(directory) / "Voices"
            profile = VoiceProfile(
                name="Damaged revision history",
                provider="qwen-character",
                voice_id="Ryan",
                qwen_mode="custom",
                qwen_profile_id="d4-damaged-revision",
            )
            revision_id = "c" * 64
            revision_dir = voices / "Qwen Profile Revisions" / profile.qwen_profile_id
            revision_dir.mkdir(parents=True, exist_ok=True)
            (revision_dir / (revision_id + ".json")).write_text(
                json.dumps({
                    "profile_id": profile.qwen_profile_id,
                    "revision_id": revision_id,
                    "saved_at": "2026-11-14T11:00:00Z",
                    "assets": [{
                        "snapshot_path": "assets/missing.wav",
                        "sha256": "d" * 64,
                        "size_bytes": 100,
                    }],
                }),
                encoding="utf-8",
            )
            with patch("app.core.paths.voices_root", return_value=voices):
                result = profile_revision_history(profile)
        self.assertEqual(result["history_count"], 1)
        self.assertEqual(result["verified_history_count"], 0)
        self.assertFalse(result["history"][0]["integrity_valid"])
        self.assertEqual(result["history"][0]["status"], "Missing or corrupt snapshot asset")


    def test_non_qwen_provider_does_not_receive_qwen_readiness_claim(self):
        profile = VoiceProfile(name="Edge", provider="edge-tts", voice_id="en-US-AvaNeural")
        result = qwen_profile_compatibility(profile)
        self.assertFalse(result["applicable"])
        self.assertEqual(result["status"], "Provider-specific")
        self.assertIsNone(result["runtime_ready"])


class VoiceProfileLibraryAssetTests(unittest.TestCase):
    def test_clone_reference_reports_byte_exact_sha256_and_required_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "reference.wav"
            expected = write_wav(source)
            profile = VoiceProfile(
                name="Clone profile", provider="qwen-character",
                voice_id="Clone", qwen_mode="clone",
                sample_path=str(source), authorized=True,
                qwen_profile_id="d4-clone-profile",
            )
            result = profile_asset_integrity(profile)
        asset = result["assets"][0]
        self.assertEqual(asset["role"], "Clone reference audio")
        self.assertTrue(asset["present"])
        self.assertEqual(asset["status"], "verified")
        self.assertEqual(asset["sha256"], hashlib.sha256(expected).hexdigest())
        self.assertTrue(result["required_assets_ready"])
        self.assertEqual(result["status"], "Verified")

    def test_missing_clone_reference_is_reported_as_required_failure(self):
        profile = VoiceProfile(
            name="Missing clone reference", provider="qwen-character",
            voice_id="Clone", qwen_mode="clone",
            sample_path="Z:/missing/reference.wav",
        )
        result = profile_asset_integrity(profile)
        self.assertFalse(result["required_assets_ready"])
        self.assertEqual(result["assets"][0]["status"], "missing or unreadable")
        self.assertEqual(result["status"], "Missing required assets")

    def test_missing_derived_voice_design_anchor_is_not_misreported_as_verified(self):
        with patch("app.core.paths.runtimes_root", return_value=Path("Z:/missing/qwen-models")):
            profile = VoiceProfile(
                name="Design without cache", provider="qwen-character",
                voice_id="Ryan", qwen_mode="design",
                qwen_profile_id="d4-design-no-cache",
            )
            result = profile_asset_integrity(profile)
        self.assertEqual(result["assets"][0]["status"], "not cached on this PC")
        self.assertTrue(result["required_assets_ready"])

    def test_detail_record_preserves_identity_and_does_not_expose_absolute_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "voice.wav"
            write_wav(source)
            profile = VoiceProfile(
                name="日本語の声", provider="qwen-character", voice_id="Ono_Anna",
                model_id="custom-1.7b", language="Japanese", qwen_mode="custom",
                qwen_prompt="Saved Japanese delivery.", qwen_seed=314,
                qwen_profile_id="d4-unicode-profile", sample_path=str(source),
                extra_fields={"future_flag": {"keep": True}},
            )
            with (
                patch("app.tts.qwen_model_preference.get_qwen_model_preference", return_value="auto"),
                patch("app.tts.qwen_model_preference.get_qwen_backend_preference", return_value="automatic"),
                patch("app.tts.qwen_character_runtime.model_installed", return_value=True),
                patch("app.tts.qwen_character_runtime.runtime_ready", return_value=True),
            ):
                result = profile_library_record(profile, inspect_assets=True)
        self.assertEqual(result["profile_kind"], "Preset")
        self.assertEqual(result["qwen_profile_id"], "d4-unicode-profile")
        self.assertEqual(result["qwen_prompt"], "Saved Japanese delivery.")
        self.assertEqual(result["qwen_seed"], 314)
        self.assertEqual(result["language"], "Japanese")
        self.assertNotIn(str(source), str(result))
        self.assertEqual(result["asset_integrity"]["verified_count"], 1)


if __name__ == "__main__":
    unittest.main()
