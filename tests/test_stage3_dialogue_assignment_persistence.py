"""Stage 3 tests for explicit, source-backed dialogue speaker assignments."""
from pathlib import Path
import unittest
from app.chapters.detector import Chapter
from app.chapters.assignment_utils import assign_dialogue_to_chapters


class DialogueAssignmentPersistenceTests(unittest.TestCase):
    def test_explicit_assignment_saves_original_offsets_and_manual_evidence(self):
        text = 'Narration first.\n\n“Rimuru, the eastern route is clear.”'
        chapter = Chapter(1, "Arrival", text)
        result = assign_dialogue_to_chapters([chapter], "“Rimuru, the eastern route is clear.”", ["Souei"])
        item = chapter.dialogue_assignments[0]
        self.assertTrue(result["saved"])
        self.assertEqual(result["chapter_number"], 1)
        self.assertEqual(text[item["start"]:item["end"]], item["text"])
        self.assertEqual(item["source"], "manual")
        self.assertEqual(item["confidence"], 1.0)
        self.assertEqual(item["speaker"], "Souei")
        self.assertEqual(item["speakers"], ["Souei"])

    def test_whitespace_wrapping_is_tolerated_without_corrupting_offsets(self):
        text = '“The eastern route is clear,\n but the river is rising.”'
        chapter = Chapter(1, "River", text)
        assign_dialogue_to_chapters([chapter], "“The eastern route is clear, but the river is rising.”", ["Souei"])
        item = chapter.dialogue_assignments[0]
        self.assertEqual(text[item["start"]:item["end"]], item["text"])
        self.assertEqual(item["text"], text)

    def test_stale_or_prototype_only_dialogue_is_rejected_without_mutation(self):
        chapter = Chapter(1, "Real", "This is the actual imported story.")
        with self.assertRaisesRegex(ValueError, "not found"):
            assign_dialogue_to_chapters([chapter], "“The eastern route is clear.”", ["Souei"])
        self.assertEqual(chapter.dialogue_assignments, [])

    def test_repeated_dialogue_requires_a_specific_chapter_or_unique_passage(self):
        chapters = [Chapter(1, "One", "“I understand.”"), Chapter(2, "Two", "Later, she said “I understand.”")]
        with self.assertRaisesRegex(ValueError, "appears more than once"):
            assign_dialogue_to_chapters(chapters, "“I understand.”", ["Rias"])
        self.assertEqual(chapters[0].dialogue_assignments, [])
        self.assertEqual(chapters[1].dialogue_assignments, [])
        result = assign_dialogue_to_chapters(chapters, "“I understand.”", ["Rias"], chapter_number=2)
        self.assertEqual(result["chapter_number"], 2)

    def test_reassignment_replaces_exact_span_but_rejects_overlaps(self):
        chapter = Chapter(1, "One", "“I understand.”")
        assign_dialogue_to_chapters([chapter], "“I understand.”", ["Rias"])
        assign_dialogue_to_chapters([chapter], "“I understand.”", ["Akeno"])
        self.assertEqual(len(chapter.dialogue_assignments), 1)
        self.assertEqual(chapter.dialogue_assignments[0]["speaker"], "Akeno")
        chapter.dialogue_assignments.append({"start": 1, "end": 5, "text": "I un", "speaker": "Rias", "source": "manual"})
        with self.assertRaisesRegex(ValueError, "overlaps"):
            assign_dialogue_to_chapters([chapter], "“I understand.”", ["Rias"])

    def test_multi_speaker_assignments_keep_legacy_and_new_fields(self):
        chapter = Chapter(1, "One", "“We stand together.”")
        assign_dialogue_to_chapters([chapter], "“We stand together.”", ["Rimuru", "Benimaru"], mode="chorus")
        item = chapter.dialogue_assignments[0]
        self.assertEqual(item["speaker"], "Rimuru")
        self.assertEqual(item["speakers"], ["Rimuru", "Benimaru"])
        self.assertEqual(item["multi_speaker_mode"], "chorus")



    def test_cast_router_does_not_apply_stale_offsets_to_a_different_quote(self):
        from app.tts.cast_provider import CastAwareProvider
        from app.tts.voice_profile import VoiceProfile

        class DummyProvider:
            recommended_chunk_chars = 1400
            recommended_chunk_sentences = 2

            def synthesize(self, text, output_path, voice=None):
                return output_path

        profile = VoiceProfile("Souei Voice", "piper", "souei")
        cast = CastAwareProvider(
            DummyProvider(), "Narrator",
            profiles={"Souei Voice": profile},
            assignments={"Souei": "Souei Voice"},
        )
        original = '“The eastern route is clear.”'
        transformed = '“The eastern route is blocked.”'
        saved = [{
            "start": 0, "end": len(original), "text": original,
            "speaker": "Souei", "speakers": ["Souei"], "source": "manual",
        }]
        parts = cast.split_for_cast(transformed, "Narrator", dialogue_assignments=saved)
        dialogue = next((voice for text, voice in parts if "eastern route" in text), None)
        self.assertEqual(dialogue, "Narrator")
        cast.close()

    def test_cast_router_uses_manual_assignment_to_select_saved_character_voice(self):
        from app.tts.cast_provider import CastAwareProvider
        from app.tts.voice_profile import VoiceProfile

        class DummyProvider:
            recommended_chunk_chars = 1400
            recommended_chunk_sentences = 2

            def synthesize(self, text, output_path, voice=None):
                return output_path

        source = 'Narration first. “Rimuru, the eastern route is clear.” Then silence.'
        start = source.index("“")
        end = source.index("”") + 1
        profile = VoiceProfile("Souei Voice", "piper", "souei")
        cast = CastAwareProvider(
            DummyProvider(), "Narrator",
            profiles={"Souei Voice": profile},
            assignments={"Souei": "Souei Voice"},
        )
        parts = cast.split_for_cast(source, "Narrator", dialogue_assignments=[{
            "start": start, "end": end, "text": source[start:end],
            "speaker": "Souei", "speakers": ["Souei"], "source": "manual",
        }])
        self.assertIn(("Rimuru, the eastern route is clear.", "Souei Voice"), parts)
        self.assertTrue(any("Narration first." in text and voice == "Narrator" for text, voice in parts))
        cast.close()

    def test_alternating_multi_speaker_assignment_rotates_voice_per_dialogue(self):
        from app.tts.cast_provider import CastAwareProvider
        from app.tts.voice_profile import VoiceProfile

        class DummyProvider:
            recommended_chunk_chars = 1400
            recommended_chunk_sentences = 2

            def synthesize(self, text, output_path, voice=None):
                return output_path

        source = '“First line.” Then narration. “Second line.”'
        first_start = source.index('“')
        first_end = source.index('”') + 1
        second_start = source.index('“', first_end)
        second_end = source.index('”', second_start) + 1
        cast = CastAwareProvider(
            DummyProvider(), "Narrator",
            profiles={
                "Rimuru Voice": VoiceProfile("Rimuru Voice", "piper", "rimuru"),
                "Benimaru Voice": VoiceProfile("Benimaru Voice", "piper", "benimaru"),
            },
            assignments={"Rimuru": "Rimuru Voice", "Benimaru": "Benimaru Voice"},
        )
        assignments = [
            {"start": first_start, "end": first_end, "text": source[first_start:first_end],
             "speakers": ["Rimuru", "Benimaru"], "speaker": "Rimuru", "multi_speaker_mode": "alternating"},
            {"start": second_start, "end": second_end, "text": source[second_start:second_end],
             "speakers": ["Rimuru", "Benimaru"], "speaker": "Rimuru", "multi_speaker_mode": "alternating"},
        ]
        parts = cast.split_for_cast(source, "Narrator", dialogue_assignments=assignments)
        dialogue_parts = [(text, voice) for text, voice in parts if "line." in text]
        self.assertEqual(dialogue_parts, [("First line.", "Rimuru Voice"), ("Second line.", "Benimaru Voice")])
        cast.close()

    def test_unassignment_removes_only_the_exact_saved_source_span(self):
        from app.chapters.assignment_utils import unassign_dialogue_from_chapters

        source = 'Narration. “First line.” Then “Second line.”'
        chapter = Chapter(1, "One", source)
        assign_dialogue_to_chapters([chapter], "“First line.”", ["Rimuru"])
        assign_dialogue_to_chapters([chapter], "“Second line.”", ["Benimaru"])
        start = source.index("“")
        end = source.index("”") + 1
        result = unassign_dialogue_from_chapters([chapter], 1, start, end, source[start:end])
        self.assertTrue(result["removed"])
        self.assertEqual(len(chapter.dialogue_assignments), 1)
        self.assertEqual(chapter.dialogue_assignments[0]["text"], "“Second line.”")

    def test_unassignment_rejects_stale_text_and_duplicate_records_without_mutation(self):
        from app.chapters.assignment_utils import unassign_dialogue_from_chapters

        source = '“The eastern route is clear.”'
        chapter = Chapter(1, "One", source)
        assign_dialogue_to_chapters([chapter], source, ["Souei"])
        saved = list(chapter.dialogue_assignments)
        with self.assertRaisesRegex(ValueError, "changed since"):
            unassign_dialogue_from_chapters([chapter], 1, 0, len(source), "“The eastern route is blocked.”")
        self.assertEqual(chapter.dialogue_assignments, saved)
        chapter.dialogue_assignments.append(dict(saved[0]))
        with self.assertRaisesRegex(ValueError, "No unique saved"):
            unassign_dialogue_from_chapters([chapter], 1, 0, len(source), source)
        self.assertEqual(len(chapter.dialogue_assignments), 2)

    def test_unassignment_bridge_and_ui_contract(self):
        root = Path(__file__).resolve().parents[1]
        host = (root / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (root / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn('"chapter.dialogue.unassign": self._chapter_dialogue_unassign', host)
        self.assertIn('"chapter.dialogue.unassign": True', host)
        self.assertIn("unassign_dialogue_from_chapters(", host)
        self.assertIn("chapter.dialogue.unassign", adapter)
        self.assertIn("removeAiCharacterAssignment", adapter)
        self.assertIn("!Number.isInteger(start) || !Number.isInteger(end)", adapter)
        self.assertIn("await call('chapter.dialogue.unassign'", adapter)
        self.assertNotIn("return normalize(item.text) === normalize(text)", adapter)

    def test_dialogue_review_uses_saved_chapter_passages_and_scopes_duplicate_quotes(self):
        adapter = (Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("function renderDialogueReview()", adapter)
        self.assertIn("const source = String(chapter.text || '')", adapter)
        self.assertIn("function characterAssignmentsFor(chapter)", adapter)
        self.assertIn("const start = Number(assignment?.start), end = Number(assignment?.end);", adapter)
        self.assertIn("data-chapter-number", adapter)
        self.assertIn("chapter_number:window.ryuPremiumPendingDialogueChapter", adapter)
        self.assertIn("dialogue passages assigned", adapter)
        self.assertIn("data-dialogue-id", adapter)
        self.assertIn("Analysis has not run for this project", adapter)
        html = (Path(__file__).resolve().parents[1] / "assets" / "frontend" / "ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        self.assertNotIn("The eastern route is clear…", html)  # no screenshot/example dialogue may substitute for project data
        self.assertIn("Loading the selected project", html)


if __name__ == "__main__":
    unittest.main()
