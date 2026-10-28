"""Stage 3 regression tests for voice cast analysis and dialogue assignment."""

import unittest
import tempfile
from pathlib import Path
from unittest import mock

from app.chapters.assignment_utils import (
    assignment_speakers,
    assign_dialogue_to_chapters,
    normalize_assignment,
    unassign_dialogue_from_chapters,
)
from app.chapters.characters import analyze_book, merge_character_analysis_record
from app.chapters.detector import Chapter
from app.tts.voice_profile import VoiceProfile, load_saved_profiles, save_profiles
from app.tts.cast_provider import CastAwareProvider



class QwenModelIntegrityTests(unittest.TestCase):
    def test_model_is_not_installed_when_any_indexed_shard_is_missing_or_truncated(self):
        import json
        from unittest.mock import patch
        from app.tts.qwen_character_runtime import model_installed

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "custom-0.6b"
            root.mkdir(parents=True)
            (root / "config.json").write_text("{}", encoding="utf-8")
            index = root / "model.safetensors.index.json"
            index.write_text(json.dumps({
                "metadata": {"total_size": 4096},
                "weight_map": {
                    "layer_a.weight": "model-00001-of-00002.safetensors",
                    "layer_b.weight": "model-00002-of-00002.safetensors",
                },
            }), encoding="utf-8")
            first = root / "model-00001-of-00002.safetensors"
            second = root / "model-00002-of-00002.safetensors"
            first.write_bytes(b"a" * 2048)

            with patch("app.tts.qwen_character_runtime.MODEL_DIRS", {"custom-0.6b": root}):
                self.assertFalse(model_installed("custom-0.6b"), "missing second shard must not be treated as installed")
                second.write_bytes(b"b" * 1024)
                self.assertFalse(model_installed("custom-0.6b"), "short aggregate weights must be treated as incomplete")
                second.write_bytes(b"b" * 2048)
                self.assertTrue(model_installed("custom-0.6b"))
                first.unlink()
                self.assertFalse(model_installed("custom-0.6b"))


class Stage3VoiceProfilePersistenceTests(unittest.TestCase):
    def test_custom_voice_profile_round_trips_unicode_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "voice catalogue"
            catalogue = root / "voices.json"
            profile = VoiceProfile(
                name="Mira • 夜",
                provider="chatterbox",
                voice_id="mira-reference",
                sample_path=str(root / "Mira • 夜" / "reference.wav"),
                notes="Character voice — warm, measured, and clear.",
                authorized=True,
            )

            with (
                mock.patch("app.tts.voice_profile.voices_root", return_value=root),
                mock.patch("app.tts.voice_profile.profiles_file", return_value=catalogue),
                mock.patch("app.tts.voice_profile.builtin_voice_profiles", return_value=[]),
            ):
                save_profiles([profile])
                loaded = load_saved_profiles()

            self.assertTrue(catalogue.is_file())
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].name, "Mira • 夜")
            self.assertEqual(loaded[0].sample_path, str(root / "Mira • 夜" / "reference.wav"))
            self.assertEqual(loaded[0].notes, "Character voice — warm, measured, and clear.")
            self.assertTrue(loaded[0].authorized)


class Stage3DialogueAssignmentTests(unittest.TestCase):
    def test_legacy_single_speaker_assignment_remains_readable(self):
        self.assertEqual(assignment_speakers({"speaker": "Mira"}), ["Mira"])
        self.assertEqual(assignment_speakers({"speakers": ["Mira", "Ren"], "speaker": "Mira"}),
                         ["Mira", "Ren"])

    def test_multi_speaker_assignment_persists_legacy_compatible_shape(self):
        chapter = Chapter(1, "Chapter 1", 'Mira said, “We should leave now.”')
        result = assign_dialogue_to_chapters(
            [chapter], "We should leave now.", ["Mira", "Ren"], chapter_number=1, mode="chorus"
        )

        self.assertTrue(result["saved"])
        self.assertEqual(result["speakers"], ["Mira", "Ren"])
        self.assertEqual(chapter.dialogue_assignments[0]["speaker"], "Mira")
        self.assertEqual(chapter.dialogue_assignments[0]["speakers"], ["Mira", "Ren"])
        self.assertEqual(chapter.dialogue_assignments[0]["multi_speaker_mode"], "chorus")
        self.assertEqual(chapter.dialogue_assignments[0]["confidence"], 1.0)

    def test_ambiguous_dialogue_is_rejected_without_mutating_assignments(self):
        chapter = Chapter(1, "Chapter 1", '“Come back.” Then she called, “Come back.”')
        before = list(chapter.dialogue_assignments)

        with self.assertRaisesRegex(ValueError, "appears more than once"):
            assign_dialogue_to_chapters([chapter], "Come back.", ["Mira"])

        self.assertEqual(chapter.dialogue_assignments, before)

    def test_stale_source_span_cannot_remove_a_saved_assignment(self):
        chapter = Chapter(1, "Chapter 1", "The saved text has changed.")
        chapter.dialogue_assignments = [
            {"start": 0, "end": 11, "text": "Wait for me.", "speaker": "Mira"}
        ]

        with self.assertRaisesRegex(ValueError, "chapter text changed"):
            unassign_dialogue_from_chapters(
                [chapter], 1, 0, 11, "Wait for me."
            )

        self.assertEqual(len(chapter.dialogue_assignments), 1)

    def test_exact_unassignment_removes_only_the_matching_assignment(self):
        text = "Mira said, “Wait here.” Ren answered, “I will.”"
        chapter = Chapter(1, "Chapter 1", text)
        first = text.index("Wait here.")
        chapter.dialogue_assignments = [
            {"start": first, "end": first + len("Wait here."), "text": "Wait here.", "speaker": "Mira"},
            {"start": text.index("I will."), "end": text.index("I will.") + len("I will."),
             "text": "I will.", "speaker": "Ren"},
        ]

        result = unassign_dialogue_from_chapters(
            [chapter], 1, first, first + len("Wait here."), "Wait here."
        )

        self.assertTrue(result["removed"])
        self.assertEqual(len(chapter.dialogue_assignments), 1)
        self.assertEqual(chapter.dialogue_assignments[0]["speaker"], "Ren")

    def test_normalizing_empty_speaker_list_removes_stale_assignment_fields(self):
        item = {"text": "Hello.", "speaker": "Old", "speakers": ["Old"], "multi_speaker_mode": "chorus"}
        normalized = normalize_assignment(item, [])

        self.assertEqual(normalized, {"text": "Hello."})
        self.assertEqual(item["speaker"], "Old", "normalization must not mutate its input")


class Stage3CharacterAnalysisTests(unittest.TestCase):

    def test_reanalysis_refreshes_evidence_but_preserves_user_cast_metadata(self):
        candidate = type("Candidate", (), {
            "name": "Mira",
            "role": "Supporting Character",
            "dialogue_count": 7,
            "examples": ["A newly detected line."],
            "confidence": 0.91,
            "aliases": ["Mira Vale"],
        })()
        prior = {
            "name": "Mira",
            "role": "Lead",
            "aliases": ["Captain Mira"],
            "voice_profile": "Warm Narrator",
            "short_description": "User-authored character description.",
            "notes": "Keep this note.",
            "scope": "Series-wide",
            "chapter_appearances": [1, 3, 8],
            "dialogue_count": 2,
            "examples": ["Stale example"],
        }

        merged = merge_character_analysis_record(candidate, prior)

        self.assertEqual(merged["dialogue_count"], 7)
        self.assertEqual(merged["examples"], ["A newly detected line."])
        self.assertEqual(merged["confidence"], 0.91)
        self.assertEqual(merged["role"], "Lead")
        self.assertEqual(merged["aliases"], ["Captain Mira", "Mira Vale"])
        self.assertEqual(merged["voice_profile"], "Warm Narrator")
        self.assertEqual(merged["short_description"], "User-authored character description.")
        self.assertEqual(merged["notes"], "Keep this note.")
        self.assertEqual(merged["scope"], "Series-wide")
        self.assertEqual(merged["chapter_appearances"], [1, 3, 8])


    def test_character_rename_preserves_previous_name_as_alias_for_voice_routing(self):
        host_source = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        update_method = host_source[
            host_source.index("def _character_update("):
            host_source.index("def _character_delete(")
        ]

        self.assertIn('saved_original_name = str(item.get("name") or original_name).strip()', update_method)
        self.assertIn("if saved_original_name.casefold() != name.casefold():", update_method)
        self.assertIn("aliases = [saved_original_name, *aliases]", update_method)
        self.assertIn("seen_alias_keys = {name.casefold()}", update_method)
        self.assertIn("if alias and alias_key not in seen_alias_keys:", update_method)

    def test_manual_assignments_remain_character_candidates_during_reanalysis(self):
        chapter = Chapter(
            1,
            "Chapter 1",
            '“Wait for me,” she said. “I am coming,” he replied.',
            dialogue_assignments=[
                {"start": 0, "end": 15, "text": "Wait for me.", "speaker": "Mira"},
                {"start": 16, "end": 35, "text": "I am coming.", "speakers": ["Ren", "Mira"]},
            ],
        )

        result = analyze_book([chapter])
        names = {character.name.casefold() for character in result.characters}

        self.assertIn("mira", names)
        self.assertIn("ren", names)
        self.assertGreaterEqual(result.dialogue_total, 2)


class _RecordingNarratorProvider:
    def __init__(self):
        self.calls = []

    def synthesize(self, text, output_path, voice=None):
        self.calls.append((text, voice))
        return Path(output_path)


class Stage3CastRoutingTests(unittest.TestCase):
    def test_dialogue_routes_to_assigned_cast_voice_and_narration_to_narrator(self):
        narrator = _RecordingNarratorProvider()
        profiles = {
            "Mira Voice": VoiceProfile(name="Mira Voice", provider="piper", voice_id="mira"),
            "Ren Voice": VoiceProfile(name="Ren Voice", provider="piper", voice_id="ren"),
        }
        provider = CastAwareProvider(
            narrator, "Narrator", profiles,
            {"Mira": "Mira Voice", "Ren": "Ren Voice"},
        )
        text = 'Mira said, “Wait here.” Ren answered, “I will.”'
        assignments = [
            {"start": text.index("Wait here."), "end": text.index("Wait here.") + len("Wait here."),
             "text": "Wait here.", "speaker": "Mira"},
            {"start": text.index("I will."), "end": text.index("I will.") + len("I will."),
             "text": "I will.", "speaker": "Ren"},
        ]

        parts = provider.split_for_cast(text, "Narrator", dialogue_assignments=assignments)

        self.assertTrue(any("Wait here." in spoken and voice == "Mira Voice" for spoken, voice in parts))
        self.assertTrue(any("I will." in spoken and voice == "Ren Voice" for spoken, voice in parts))
        self.assertTrue(any("Mira said" in spoken and voice == "Narrator" for spoken, voice in parts))
        self.assertTrue(any("Ren answered" in spoken and voice == "Narrator" for spoken, voice in parts))

    def test_missing_assigned_cast_profile_fails_instead_of_using_narrator(self):
        narrator = _RecordingNarratorProvider()
        provider = CastAwareProvider(
            narrator, "Narrator", {}, {"Mira": "Deleted Mira Voice"}
        )

        with self.assertRaisesRegex(RuntimeError, "assigned character voice profile.*unavailable"):
            provider.synthesize("Wait here.", Path("unused.wav"), "Deleted Mira Voice")

        self.assertEqual(narrator.calls, [])

    def test_unassigned_narration_still_uses_narrator_provider(self):
        narrator = _RecordingNarratorProvider()
        provider = CastAwareProvider(
            narrator, "Narrator", {}, {"Mira": "Mira Voice"}
        )

        result = provider.synthesize("Narration text.", Path("narration.wav"), "Narrator")

        self.assertEqual(result, Path("narration.wav"))
        self.assertEqual(narrator.calls, [("Narration text.", "Narrator")])



class Stage3HostSafetyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.host_source = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")

    def test_partial_character_update_preserves_omitted_metadata(self):
        start = self.host_source.index("def _character_update(")
        end = self.host_source.index("def _character_delete(", start)
        method = self.host_source[start:end]

        self.assertIn('payload.get("role") if "role" in payload else item.get("role", "Character")', method)
        self.assertIn('payload.get("short_description") if "short_description" in payload else item.get("short_description", "")', method)
        self.assertIn('payload.get("notes") if "notes" in payload else item.get("notes", "")', method)
        self.assertIn('payload.get("scope") if "scope" in payload else item.get("scope", "Current book only")', method)
        self.assertIn('payload.get("voice_profile") if "voice_profile" in payload else item.get("voice_profile")', method)

    def test_voice_profile_deletion_is_blocked_while_referenced(self):
        start = self.host_source.index("def _voice_delete(")
        end = self.host_source.index("def _voice_select(", start)
        method = self.host_source[start:end]

        self.assertIn("Built-in voices cannot be deleted", method)
        self.assertIn('state.get("voice_profile")', method)
        self.assertIn('item.get("voice_profile")', method)
        self.assertIn("Select another narrator before deleting it", method)
        self.assertIn("Reassign that character before deleting it", method)

    def test_custom_voice_clone_requires_reference_audio_and_permission(self):
        start = self.host_source.index("def _voice_save(")
        end = self.host_source.index("def _voice_list(", start)
        method = self.host_source[start:end]

        self.assertIn('if provider_name == "chatterbox" and not authorized:', method)
        self.assertIn('if provider_name == "chatterbox" and not sample_path:', method)
        self.assertIn('if not authorized:', method)
        self.assertIn('if not sample_path:', method)


if __name__ == "__main__":
    unittest.main()
