"""Stage 8.2.10 generation reliability regressions."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.chapters.detector import Chapter
from app.tts.manager import GenerationManager


class Stage8210GenerationReliabilityTests(unittest.TestCase):
    def test_cancel_requested_during_final_chapter_skips_book_packaging(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            chapter = Chapter(1, "Opening", "A short chapter for cancellation.")
            provider = SimpleNamespace()
            manager = GenerationManager(provider, "Narrator", [chapter], root / "working_audio")
            finished = []
            manager.on_finished = finished.append

            def complete_then_cancel(*args, **kwargs):
                output_dir = root / "working_audio" / "chapter-output"
                output_dir.mkdir(parents=True, exist_ok=True)
                manager.cancel_event.set()
                return SimpleNamespace(
                    chunks_completed=1,
                    chunks_total=1,
                    output_path=output_dir,
                )

            output = root / "Audiobook.m4b"
            with patch("app.tts.manager.generate_chapter", side_effect=complete_then_cancel), patch(
                "app.tts.manager.assemble_m4b"
            ) as assemble:
                manager._run(output, "Audiobook", "", None, {})

            self.assertEqual(len(finished), 1)
            self.assertTrue(finished[0].cancelled)
            self.assertIsNone(finished[0].output_path)
            assemble.assert_not_called()
            self.assertFalse(output.exists())

    def test_cancelled_or_failed_attempt_does_not_attach_stale_output_to_job(self):
        source = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn('output_path=str(actual) if valid and status != "cancelled"', source)
        self.assertIn("and not summary.packaging_failed and not summary.chapters_failed else None", source)

    def test_running_jobs_estimate_eta_only_after_progress_is_meaningful(self):
        source = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn('row["eta_seconds"] = (', source)
        self.assertIn("elapsed >= 5 and progress >= 5 and progress < 100", source)
        self.assertIn('row["eta_seconds"] = 0', source)

    def test_assigned_saved_character_profile_is_used_for_actual_synthesis(self):
        from unittest.mock import patch

        from app.tts.cast_provider import CastAwareProvider
        from app.tts.voice_profile import VoiceProfile

        class RecordingProvider:
            recommended_chunk_chars = 1400
            recommended_chunk_sentences = 2

            def __init__(self):
                self.calls = []

            def synthesize(self, text, output_path, voice=None):
                self.calls.append((text, voice))
                return output_path

        narrator = RecordingProvider()
        assigned = RecordingProvider()
        profile = VoiceProfile("Souei Voice", "piper", "souei")
        cast = CastAwareProvider(
            narrator,
            "Narrator",
            profiles={"Souei Voice": profile},
            assignments={"Souei": "Souei Voice"},
        )
        output = Path("dialogue.wav")
        try:
            with patch("app.tts.cast_provider.provider_from_profile", return_value=(assigned, "resolved-souei-voice")):
                result = cast.synthesize("The eastern route is clear.", output, "Souei Voice")
            self.assertEqual(result, output)
            self.assertEqual(assigned.calls, [("The eastern route is clear.", "resolved-souei-voice")])
            self.assertEqual(narrator.calls, [], "assigned character dialogue must not fall back to narrator synthesis")
        finally:
            cast.close()

    def test_last_chapter_cancel_is_checked_before_packaging(self):
        source = Path("app/tts/manager.py").read_text(encoding="utf-8")
        self.assertIn("if self.cancel_event.is_set():\n            cancelled = True\n        if not cancelled and self._wait_if_paused", source)
