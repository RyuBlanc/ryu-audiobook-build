"""End-to-end narrator and character voice routing through chapter generation.

The TTS engines are deterministic WAV writers and the M4B muxer is replaced with
a validating test double. This exercises the same saved-profile routing,
GenerationManager and chapter chunk generation used by production without
requiring network access or heavyweight local voice models in CI.
"""

import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.chapters.detector import Chapter
from app.core.character_identity import character_identity_key
from app.tts.cast_provider import CastAwareProvider
from app.tts.manager import GenerationManager
from app.tts.profile_provider import ProfileBoundProvider
from app.tts.voice_profile import VoiceProfile
from app.ui.premium_v2_host import PremiumV2Bridge


class RecordingWavProvider:
    def __init__(self, label):
        self.label = label
        self.calls = []

    def voices(self):
        return [self.label]

    def synthesize(self, text, output_path, voice=None):
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        self.calls.append((str(text), voice))
        # A valid, non-empty PCM WAV is sufficient for the real chunk validator.
        with wave.open(str(output), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"\\x00\\x00" * 8192)
        return output

    def close(self):
        return None


def assigned_quote(chapter_text, dialogue, speaker):
    start = chapter_text.index(dialogue)
    return {
        "start": start,
        "end": start + len(dialogue),
        "text": dialogue,
        "speaker": speaker,
        "series": "The Series",
        "source": "manual",
    }


class Stage3NarratorMultiChapterIntegrationTests(unittest.TestCase):
    def test_two_chapter_generation_routes_narrator_gaps_and_saved_character_voices(self):
        chapter_one_text = (
            "The lantern flickered. Mira said, “Stay close.” "
            "The tunnel narrowed."
        )
        chapter_two_text = (
            "Rain covered the road. Ren answered, “I can guide us.” "
            "The village was near."
        )
        chapters = [
            Chapter(
                1,
                "The Tunnel",
                chapter_one_text,
                dialogue_assignments=[assigned_quote(chapter_one_text, "Stay close.", "Mira")],
                review_status="ready",
            ),
            Chapter(
                2,
                "The Road",
                chapter_two_text,
                dialogue_assignments=[assigned_quote(chapter_two_text, "I can guide us.", "Ren")],
                review_status="ready",
            ),
        ]

        narrator_profile = VoiceProfile(
            name="Series Narrator",
            provider="piper",
            voice_id="narrator-id",
            backend="automatic",
        )
        mira_profile = VoiceProfile(
            name="Mira Voice",
            provider="piper",
            voice_id="mira-id",
            backend="automatic",
        )
        ren_profile = VoiceProfile(
            name="Ren Voice",
            provider="piper",
            voice_id="ren-id",
            backend="automatic",
        )
        other_mira_profile = VoiceProfile(
            name="Other Series Mira Voice",
            provider="piper",
            voice_id="other-mira-id",
            backend="automatic",
        )

        # Production preflight resolves the same saved series narrator used to
        # build the provider and rejects unresolved dialogue before generation.
        bridge = PremiumV2Bridge.__new__(PremiumV2Bridge)
        project = SimpleNamespace(chapters=chapters)
        bridge._project_series_name = lambda _project, _state: "The Series"
        bridge._narrator_series_default_read = lambda *_args: {
            "effective_profile_name": "Series Narrator",
            "profile_name": "Series Narrator",
            "source": "series_default",
            "profile_available": True,
        }
        bridge._find_profile = lambda name: narrator_profile if name == narrator_profile.name else None
        resolved_narrator, selection = bridge._resolve_narrator_for_generation(
            project, {"series": "The Series"}, chapters
        )
        self.assertIs(resolved_narrator, narrator_profile)
        self.assertEqual(selection["source"], "series_default")

        narrator_engine = RecordingWavProvider("Narrator engine")
        narrator_provider = ProfileBoundProvider(narrator_engine, narrator_profile)
        character_engines = {
            "Mira Voice": RecordingWavProvider("Mira engine"),
            "Ren Voice": RecordingWavProvider("Ren engine"),
            "Other Series Mira Voice": RecordingWavProvider("Other Series Mira engine"),
        }
        character_profiles = {
            "Mira Voice": mira_profile,
            "Ren Voice": ren_profile,
            "Other Series Mira Voice": other_mira_profile,
        }
        # The legacy name-only map deliberately points Mira to the other series.
        # The source-backed series identity must win for this book's assignment.
        cast_assignments = {"Mira": "Other Series Mira Voice", "Ren": "Ren Voice"}
        identity_assignments = {
            character_identity_key("Mira", "The Series"): "Mira Voice",
            character_identity_key("Mira", "Other Series"): "Other Series Mira Voice",
            character_identity_key("Ren", "The Series"): "Ren Voice",
        }
        provider = CastAwareProvider(
            narrator_provider,
            narrator_profile.voice_id,
            character_profiles,
            cast_assignments,
            narrator_profile=narrator_profile,
            identity_assignments=identity_assignments,
        )

        def provider_for_saved_profile(profile):
            return character_engines[profile.name], profile.voice_id

        completed_summaries = []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output_path = root / "The Series.m4b"

            def validate_and_package(chapter_dirs, target, title, author, cover, chapter_titles, **kwargs):
                self.assertEqual(len(chapter_dirs), 2)
                self.assertEqual(chapter_titles, ["The Tunnel", "The Road"])
                for chapter_dir in chapter_dirs:
                    manifest = chapter_dir / "chunk_manifest.json"
                    self.assertTrue(manifest.is_file())
                    chunk_files = sorted((chapter_dir / "chunks").glob("*.wav"))
                    self.assertTrue(chunk_files, f"No generated WAV chunks for {chapter_dir.name}")
                    for chunk_file in chunk_files:
                        with wave.open(str(chunk_file), "rb") as audio:
                            self.assertGreater(audio.getnframes(), 0)
                            self.assertEqual(audio.getframerate(), 16000)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"validated-test-m4b")
                return target

            with patch(
                "app.tts.cast_provider.provider_from_profile",
                side_effect=provider_for_saved_profile,
            ):
                manager = GenerationManager(
                    provider=provider,
                    voice=narrator_profile.voice_id,
                    chapters=chapters,
                    project_audio_root=root / "working_audio",
                    on_finished=completed_summaries.append,
                    narration_speed=1.0,
                )
                with patch("app.tts.manager.assemble_m4b", side_effect=validate_and_package):
                    manager._run_body(
                        output_path,
                        "The Series",
                        "Test Author",
                        None,
                        {"title": "The Series", "narrator": narrator_profile.name},
                    )

            self.assertTrue(output_path.is_file())
            self.assertEqual(len(completed_summaries), 1)
            summary = completed_summaries[0]
            self.assertEqual(summary.chapters_total, 2)
            self.assertEqual(summary.chapters_completed, 2)
            self.assertEqual(summary.chapters_failed, [])
            self.assertEqual(summary.output_path, output_path)

        narrator_text = [text for text, voice in narrator_engine.calls if voice == "narrator-id"]
        mira_text = [text for text, voice in character_engines["Mira Voice"].calls if voice == "mira-id"]
        ren_text = [text for text, voice in character_engines["Ren Voice"].calls if voice == "ren-id"]

        self.assertTrue(any("The lantern flickered." in item for item in narrator_text))
        self.assertTrue(any("The tunnel narrowed." in item for item in narrator_text))
        self.assertTrue(any("Rain covered the road." in item for item in narrator_text))
        self.assertTrue(any("The village was near." in item for item in narrator_text))
        self.assertTrue(any("Stay close." in item for item in mira_text))
        self.assertTrue(any("I can guide us." in item for item in ren_text))
        self.assertFalse(character_engines["Other Series Mira Voice"].calls)
        # No character dialogue may leak to the narrator provider.
        self.assertFalse(any("Stay close." in item or "I can guide us." in item for item in narrator_text))


if __name__ == "__main__":
    unittest.main()
