"""Stage 4 pronunciation-to-synthesis and checkpoint-safety regressions."""
import json
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace

from app.tts.generator import prepare_chapter_plan, save_state


class _OffsetAwareProvider:
    recommended_chunk_chars = 1400
    recommended_chunk_sentences = 2
    split_on_expression_change = False
    def __init__(self): self.cast_inputs = []
    def split_for_cast(self, text, voice, dialogue_assignments=None):
        self.cast_inputs.append((text, dialogue_assignments))
        return [(text, voice)]
    def generation_signature(self): return "fake-provider-v1"
    def configure_narration(self, speed, profile): pass


def _chapter(number, title, text, assignments=None):
    return SimpleNamespace(number=number, title=title, text=text, dialogue_assignments=assignments or [])


def _write_valid_wav(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x01\x00" * 1200)


class PronunciationSynthesisSafetyTests(unittest.TestCase):
    def test_cast_offsets_are_consumed_before_replacement_and_source_is_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            assignments = [{"start": 0, "end": 3, "character": "Narrator"}]
            chapter = _chapter(1, "One", "NYC is busy.", assignments)
            provider = _OffsetAwareProvider()
            plan = prepare_chapter_plan(chapter, provider, "Narrator", root,
                pronunciation_dictionary=[{"written_form": "NYC", "spoken_form": "New York City"}])
            self.assertEqual(provider.cast_inputs[0][0], "NYC is busy.")
            self.assertEqual(provider.cast_inputs[0][1], assignments)
            self.assertEqual(chapter.text, "NYC is busy.")
            self.assertEqual(chapter.dialogue_assignments, assignments)
            manifest = json.loads((plan.chapter_dir / "chunk_manifest.json").read_text(encoding="utf-8"))
            self.assertIn("New York City", " ".join(item["text"] for item in manifest["chunks"]))
            narration = json.loads((plan.chapter_dir / "narration.json").read_text(encoding="utf-8"))
            self.assertEqual(narration["narration_text"], "NYC is busy.")

    def test_changed_rule_invalidates_only_chapters_whose_synthesis_text_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            provider = _OffsetAwareProvider()
            affected, unrelated = _chapter(1, "One", "NYC is busy."), _chapter(2, "Two", "Boston is quiet.")
            rules = [{"written_form": "NYC", "spoken_form": "New York City"}]
            first_a = prepare_chapter_plan(affected, provider, "Narrator", root, rules)
            first_u = prepare_chapter_plan(unrelated, provider, "Narrator", root, rules)
            for plan in (first_a, first_u):
                _write_valid_wav(plan.chapter_dir / "chunks" / "00001.wav")
                save_state(plan.chapter_dir, {"completed": [0], "chunks_total": len(plan.chunks_with_voices),
                                              "generation_signature": plan.signature})
            changed = [{"written_form": "NYC", "spoken_form": "The Big Apple"}]
            second_a = prepare_chapter_plan(affected, provider, "Narrator", root, changed)
            second_u = prepare_chapter_plan(unrelated, provider, "Narrator", root, changed)
            self.assertNotEqual(first_a.signature, second_a.signature)
            self.assertEqual(second_a.completed, frozenset())
            self.assertFalse((second_a.chapter_dir / "chunks" / "00001.wav").exists())
            self.assertEqual(first_u.signature, second_u.signature)
            self.assertEqual(second_u.completed, frozenset({0}))
            self.assertTrue((second_u.chapter_dir / "chunks" / "00001.wav").exists())


if __name__ == "__main__":
    unittest.main()
