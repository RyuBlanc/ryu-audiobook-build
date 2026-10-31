from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from app.ui.premium_v2_host import PremiumV2Bridge
from app.tts.voice_profile import VoiceProfile, load_profiles, save_profiles


class PremiumV2VoiceSaveTests(unittest.TestCase):
    def test_chatterbox_profile_is_persisted_without_explicit_voice_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sample = root / "reference.wav"
            sample.write_bytes(b"test reference placeholder")
            voices = root / "voices"

            with (
                patch("app.ui.premium_v2_host.ensure_roots"),
                patch.object(PremiumV2Bridge, "_load_durable_jobs"),
                patch("app.tts.voice_profile.voices_root", return_value=voices),
                patch("app.tts.voice_profile.builtin_voice_profiles", return_value=[]),
            ):
                bridge = PremiumV2Bridge()
                result = bridge._voice_save({
                    "name": "Test Chatterbox",
                    "provider": "chatterbox",
                    "sample_path": str(sample),
                    "authorized": True,
                })

                self.assertTrue(result["saved"])
                self.assertEqual(result["voice_id"], "Test Chatterbox")
                self.assertEqual(result["provider"], "chatterbox")
                self.assertEqual(result["count"], 1)

                catalogue = voices / "voices.json"
                self.assertTrue(catalogue.is_file())
                saved = catalogue.read_text(encoding="utf-8")
                self.assertIn('"name": "Test Chatterbox"', saved)
                self.assertIn('"voice_id": "Test Chatterbox"', saved)

    def test_chatterbox_profile_requires_authorization(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sample = root / "reference.wav"
            sample.write_bytes(b"test reference placeholder")
            voices = root / "voices"

            with (
                patch("app.ui.premium_v2_host.ensure_roots"),
                patch.object(PremiumV2Bridge, "_load_durable_jobs"),
                patch("app.tts.voice_profile.voices_root", return_value=voices),
                patch("app.tts.voice_profile.builtin_voice_profiles", return_value=[]),
            ):
                bridge = PremiumV2Bridge()
                with self.assertRaisesRegex(ValueError, "permission"):
                    bridge._voice_save({
                        "name": "Unauthorized Test",
                        "provider": "chatterbox",
                        "sample_path": str(sample),
                        "authorized": False,
                    })
                self.assertFalse((voices / "voices.json").exists())


class VoicePreviewSelectionTests(unittest.TestCase):
    def test_unsaved_installed_qwen_selection_can_be_previewed_in_memory(self):
        with (
            patch("app.ui.premium_v2_host.ensure_roots"),
            patch.object(PremiumV2Bridge, "_load_durable_jobs"),
        ):
            bridge = PremiumV2Bridge()
            with patch.object(bridge, "_find_profile", return_value=None):
                profile = bridge._preview_profile_from_payload({
                    "profile_name": "My Custom Preview",
                    "provider": "qwen-character",
                    "voice_id": "Ryan",
                    "model_id": "auto",
                    "qwen_mode": "design",
                    "qwen_prompt": "Warm and clear narration voice.",
                    "qwen_seed": "7301",
                    "language": "English",
                }, {})
        self.assertEqual(profile.name, "My Custom Preview")
        self.assertEqual(profile.provider, "qwen-character")
        self.assertEqual(profile.voice_id, "Ryan")
        self.assertEqual(profile.qwen_mode, "design")
        self.assertEqual(profile.qwen_prompt, "Warm and clear narration voice.")
        self.assertEqual(profile.qwen_seed, 7301)
        self.assertTrue(profile.qwen_profile_id)
        self.assertFalse(profile.qwen_profile_id is None)

    def test_unsaved_preview_requires_a_real_reference_for_clone_voice(self):
        with (
            patch("app.ui.premium_v2_host.ensure_roots"),
            patch.object(PremiumV2Bridge, "_load_durable_jobs"),
        ):
            bridge = PremiumV2Bridge()
            with patch.object(bridge, "_find_profile", return_value=None):
                with self.assertRaisesRegex(ValueError, "Save the Qwen Voice Clone profile first"):
                    bridge._preview_profile_from_payload({
                        "profile_name": "My Clone",
                        "provider": "qwen-character",
                        "voice_id": "Ryan",
                        "qwen_mode": "clone",
                    }, {})

    def test_preview_without_saved_profile_or_installed_voice_fails_clearly(self):
        with (
            patch("app.ui.premium_v2_host.ensure_roots"),
            patch.object(PremiumV2Bridge, "_load_durable_jobs"),
        ):
            bridge = PremiumV2Bridge()
            with patch.object(bridge, "_find_profile", return_value=None):
                self.assertIsNone(bridge._preview_profile_from_payload({"profile_name": "Missing"}, {}))


class VoiceProfileCatalogueRegressionTests(unittest.TestCase):
    def test_saved_alias_of_builtin_voice_survives_catalogue_reload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "voices"
            builtin = VoiceProfile(
                name="Offline Neural • Amy", provider="piper",
                voice_id="en_US-amy-medium", model_id="piper", authorized=True,
            )
            alias = VoiceProfile(
                name="My Story Narrator", provider="piper",
                voice_id="en_US-amy-medium", model_id="piper", authorized=True,
            )
            with (
                patch("app.tts.voice_profile.voices_root", return_value=root),
                patch("app.tts.voice_profile.builtin_voice_profiles", return_value=[builtin]),
            ):
                save_profiles([alias])
                loaded = load_profiles()
            self.assertIn("My Story Narrator", [item.name for item in loaded])
            self.assertTrue((root / "voices.json").is_file())

    def test_one_invalid_legacy_row_does_not_hide_other_saved_profiles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "voices"
            root.mkdir()
            (root / "voices.json").write_text(json.dumps([
                {"name": "Valid Existing Profile", "provider": "piper",
                 "voice_id": "en_US-amy-medium", "model_id": "piper"},
                {"name": "Broken Legacy Record", "provider": "piper"},
            ]), encoding="utf-8")
            with (
                patch("app.tts.voice_profile.voices_root", return_value=root),
                patch("app.tts.voice_profile.builtin_voice_profiles", return_value=[]),
            ):
                loaded = load_profiles()
            self.assertEqual([item.name for item in loaded], ["Valid Existing Profile"])


class VoiceProfileRenameTests(unittest.TestCase):
    def test_renaming_a_saved_reference_profile_replaces_the_original_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sample = root / "reference.wav"
            sample.write_bytes(b"reference-placeholder")
            voices = root / "voices"
            with (
                patch("app.ui.premium_v2_host.ensure_roots"),
                patch.object(PremiumV2Bridge, "_load_durable_jobs"),
                patch("app.tts.voice_profile.voices_root", return_value=voices),
                patch("app.tts.voice_profile.builtin_voice_profiles", return_value=[]),
            ):
                bridge = PremiumV2Bridge()
                bridge._voice_save({
                    "name": "Old Reference Name", "provider": "chatterbox",
                    "voice_id": "reference-id", "sample_path": str(sample),
                    "authorized": True, "qwen_mode": "clone",
                })
                result = bridge._voice_save({
                    "name": "Renamed Reference Voice", "original_name": "Old Reference Name",
                    "provider": "chatterbox", "voice_id": "reference-id",
                    "authorized": True,
                })
                saved = load_profiles()
            named = [profile.name for profile in saved if profile.provider == "chatterbox"]
            self.assertEqual(named, ["Renamed Reference Voice"])
            self.assertEqual(result["name"], "Renamed Reference Voice")
            self.assertEqual(saved[0].sample_path, str(sample.resolve()))


    def test_renaming_saved_voice_updates_all_project_cast_and_narrator_references(self):
        from types import SimpleNamespace
        from app.core.state import load_state, save_state

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sample = root / "reference.wav"
            sample.write_bytes(b"reference-placeholder")
            voices = root / "voices"
            project_one = SimpleNamespace(folder=root / "project-one", title="Silver Moon Saga · Vol 1")
            project_two = SimpleNamespace(folder=root / "project-two", title="Silver Moon Saga · Vol 2")
            save_state(project_one.folder, {
                "voice_profile": "Old Reference Name",
                "narrator": "Old Reference Name",
                "voice_id": "reference-id",
                "backend": "automatic",
                "characters": [
                    {"name": "Mira", "series": "Silver Moon Saga", "voice_profile": "Old Reference Name"},
                    {"name": "Ren", "series": "Silver Moon Saga", "voice_profile": "Other Voice"},
                ],
            })
            save_state(project_two.folder, {
                "voice_profile": "Other Narrator",
                "narrator": "Other Narrator",
                "voice_id": "other-id",
                "backend": "automatic",
                "characters": [
                    {"name": "Mira", "series": "Silver Moon Saga", "voice_profile": "Old Reference Name"},
                ],
            })
            registry = [
                {"id": "registry-mira", "series": "Silver Moon Saga", "primary_name": "Mira", "voice_name": "Old Reference Name"},
                {"id": "registry-ren", "series": "Silver Moon Saga", "primary_name": "Ren", "voice_name": "Other Voice"},
            ]
            registry_updates = []

            def update_registry(record_id, changes):
                registry_updates.append((record_id, dict(changes)))

            with (
                patch("app.ui.premium_v2_host.ensure_roots"),
                patch.object(PremiumV2Bridge, "_load_durable_jobs"),
                patch("app.tts.voice_profile.voices_root", return_value=voices),
                patch("app.tts.voice_profile.builtin_voice_profiles", return_value=[]),
                patch("app.ui.premium_v2_host.list_projects", return_value=[project_one, project_two]),
                patch("app.ui.premium_v2_host.list_reusable_characters", return_value=registry),
                patch("app.ui.premium_v2_host.update_reusable_character", side_effect=update_registry),
            ):
                bridge = PremiumV2Bridge()
                bridge._voice_save({
                    "name": "Old Reference Name",
                    "provider": "chatterbox",
                    "voice_id": "reference-id",
                    "sample_path": str(sample),
                    "authorized": True,
                })
                result = bridge._voice_save({
                    "name": "Renamed Reference Voice",
                    "original_name": "Old Reference Name",
                    "provider": "chatterbox",
                    "voice_id": "reference-id",
                    "authorized": True,
                })

            first = load_state(project_one.folder)
            second = load_state(project_two.folder)
            self.assertEqual(result["name"], "Renamed Reference Voice")
            self.assertEqual(first["voice_profile"], "Renamed Reference Voice")
            self.assertEqual(first["narrator"], "Renamed Reference Voice")
            self.assertEqual(first["characters"][0]["voice_profile"], "Renamed Reference Voice")
            self.assertEqual(first["characters"][1]["voice_profile"], "Other Voice")
            self.assertEqual(second["voice_profile"], "Other Narrator")
            self.assertEqual(second["characters"][0]["voice_profile"], "Renamed Reference Voice")
            self.assertEqual(
                registry_updates,
                [("registry-mira", {"voice_name": "Renamed Reference Voice"})],
            )


if __name__ == "__main__":
    unittest.main()
