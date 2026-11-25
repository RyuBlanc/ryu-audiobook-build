from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.chapters.detector import Chapter
from app.chapters.passage_index import (
    INDEX_FILENAME,
    INDEX_SCHEMA_VERSION,
    chapter_index_summary,
    load_or_build_passage_index,
    passages_for_chapter,
)


class DialoguePassageIndexTests(unittest.TestCase):
    def make_project_folder(self, temporary: str) -> Path:
        folder = Path(temporary) / "book"
        folder.mkdir()
        return folder

    def test_index_persists_exact_source_offsets_and_reuses_matching_revision(self):
        chapter = Chapter(
            1,
            "Opening",
            "Narration before.\n\n“Mira spoke.”\n\nNarration after.",
        )
        with tempfile.TemporaryDirectory() as temporary:
            folder = self.make_project_folder(temporary)
            with patch(
                "app.chapters.passage_index.segment_chapter_speakers",
                wraps=__import__(
                    "app.chapters.speaker_segmentation",
                    fromlist=["segment_chapter_speakers"],
                ).segment_chapter_speakers,
            ) as segmenter:
                first = load_or_build_passage_index(folder, [chapter])
                first_calls = segmenter.call_count
                second = load_or_build_passage_index(folder, [chapter])

            self.assertEqual(segmenter.call_count, first_calls)
            self.assertEqual(second["index_revision"], first["index_revision"])
            self.assertEqual(second["source_revision"], first["source_revision"])
            self.assertEqual(second["assignment_revision"], first["assignment_revision"])
            self.assertTrue((folder / INDEX_FILENAME).is_file())

            dialogue = next(row for row in second["passages"] if row["dialogue"])
            self.assertEqual(chapter.text[dialogue["start"]:dialogue["end"]], dialogue["text"])
            self.assertEqual(dialogue["kind"], "needs_speaker_review")
            self.assertEqual(dialogue["assignment_state"], "pending")
            self.assertTrue(dialogue["passage_id"].startswith("ps_"))

            loaded = json.loads((folder / INDEX_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual(loaded["source_revision"], first["source_revision"])
            self.assertEqual(loaded["passages"], first["passages"])

    def test_assignment_revision_and_counts_change_without_changing_source_revision(self):
        text = (
            "Narration one.\n\n"
            "“Mira here.”\n\n"
            "Narration two.\n\n"
            "“Ren here.”\n\n"
            "Narration three.\n\n"
            "“Who is this?”"
        )
        chapter = Chapter(1, "Scene", text)
        mira = "“Mira here.”"
        ren = "“Ren here.”"
        conflict = "“Who is this?”"
        chapter.dialogue_assignments = [
            {
                "start": text.index(mira), "end": text.index(mira) + len(mira),
                "text": mira, "speaker": "Mira", "source": "manual",
            },
            {
                "start": text.index(ren), "end": text.index(ren) + len(ren),
                "text": ren, "speaker": "Ren", "source": "ai", "confidence": 0.91,
            },
            {
                "start": text.index(conflict), "end": text.index(conflict) + len(conflict),
                "text": conflict, "speaker": "Tara", "source": "manual",
            },
            {
                "start": text.index(conflict), "end": text.index(conflict) + len(conflict),
                "text": conflict, "speaker": "Uma", "source": "manual",
            },
        ]

        with tempfile.TemporaryDirectory() as temporary:
            index = load_or_build_passage_index(self.make_project_folder(temporary), [chapter])
            counts = index["counts"]
            self.assertEqual(counts["dialogue_passage_count"], 3)
            self.assertEqual(counts["narration_passage_count"], 3)
            self.assertEqual(counts["assigned_dialogue_count"], 2)
            self.assertEqual(counts["manual_assigned_dialogue_count"], 1)
            self.assertEqual(counts["ai_assigned_dialogue_count"], 1)
            self.assertEqual(counts["conflicting_dialogue_count"], 1)
            self.assertEqual(counts["unassigned_dialogue_count"], 1)

            rows = [row for row in index["passages"] if row["dialogue"]]
            self.assertEqual(
                {row["assignment_state"] for row in rows},
                {"assigned", "conflict"},
            )
            summary = chapter_index_summary(index, 1)
            self.assertIsNotNone(summary)
            self.assertEqual(summary["counts"], counts)
            self.assertEqual(
                passages_for_chapter(index, chapter.chapter_id),
                index["passages"],
            )

    def test_passage_id_hash_uses_the_legacy_separator_for_existing_workbook_compatibility(self):
        from hashlib import sha256

        dialogue = "“A stable passage.”"
        chapter = Chapter(1, "Scene", dialogue)
        with tempfile.TemporaryDirectory() as temporary:
            folder = self.make_project_folder(temporary)
            index = load_or_build_passage_index(folder, [chapter])
            row = next(item for item in index["passages"] if item["text"] == dialogue)
            text_hash = sha256(dialogue.encode("utf-8")).hexdigest()
            stable_identity = (
                f"{row['chapter_id']}\\0dialogue\\0{text_hash}\\00"
            )
            expected = "ps_" + sha256(stable_identity.encode("utf-8")).hexdigest()[:32]
            self.assertEqual(row["passage_id"], expected)

    def test_passage_ids_survive_unrelated_prefix_edits_while_offsets_reconcile(self):
        dialogue = "“A stable passage.”"
        chapter = Chapter(1, "Scene", f"Opening paragraph.\n\n{dialogue}\n\nClosing paragraph.")
        with tempfile.TemporaryDirectory() as temporary:
            folder = self.make_project_folder(temporary)
            before = load_or_build_passage_index(folder, [chapter])
            before_row = next(row for row in before["passages"] if row["text"] == dialogue)

            chapter.text = "An inserted opening paragraph.\n\n" + chapter.text
            after = load_or_build_passage_index(folder, [chapter])
            after_row = next(row for row in after["passages"] if row["text"] == dialogue)

            self.assertNotEqual(before["source_revision"], after["source_revision"])
            self.assertEqual(before_row["passage_id"], after_row["passage_id"])
            self.assertGreater(after_row["start"], before_row["start"])
            self.assertEqual(chapter.text[after_row["start"]:after_row["end"]], dialogue)

    def test_quoted_term_inside_narration_is_not_indexed_as_spoken_dialogue(self):
        from app.chapters.speaker_segmentation import segment_chapter_speakers

        source = (
            'She causes these sorts of “accidents” and keeps walking. '
            'Kousuke said, “We should leave now.”'
        )
        chapter = Chapter(1, "Inline quotation", source)
        segments = segment_chapter_speakers(chapter)

        dialogue = [row for row in segments if row.kind != "narration"]
        narration = [row for row in segments if row.kind == "narration"]
        self.assertEqual(len(dialogue), 1)
        self.assertEqual(dialogue[0].text, '“We should leave now.”')
        self.assertTrue(any('“accidents”' in row.text for row in narration))

    def test_inline_speech_tag_remains_dialogue_after_embedded_quote_filter(self):
        from app.chapters.characters import _all_dialogue_spans

        source = 'After a pause, Kousuke said, “I am ready.” Then he left.'
        spans = _all_dialogue_spans(source)
        self.assertEqual(len(spans), 1)
        self.assertEqual(source[spans[0][0]:spans[0][1]], '“I am ready.”')

    def test_embedded_quoted_term_ignores_stale_machine_assignment_but_keeps_manual_conflict(self):
        from app.chapters.speaker_segmentation import segment_chapter_speakers

        source = 'She causes these sorts of “accidents” and keeps walking.'
        start = source.index('“accidents”')
        end = start + len('“accidents”')
        quote = source[start:end]

        for assignment_source in ("ai", "outsourced"):
            chapter = Chapter(1, "Quoted term", source)
            chapter.dialogue_assignments = [{
                "start": start, "end": end, "text": quote,
                "speaker": "Legacy AI speaker", "source": assignment_source,
            }]
            segments = segment_chapter_speakers(chapter)
            embedded = next(row for row in segments if row.text == quote)
            self.assertEqual(embedded.kind, "narration")
            self.assertEqual(embedded.source, "automatic_embedded_quote")
            self.assertFalse(embedded.needs_review)

        manual = Chapter(1, "Quoted term", source)
        manual.dialogue_assignments = [{
            "start": start, "end": end, "text": quote,
            "speaker": "User Confirmed Speaker", "source": "manual",
        }]
        manual_segments = segment_chapter_speakers(manual)
        protected = next(row for row in manual_segments if row.start <= start < row.end)
        self.assertEqual(protected.kind, "needs_speaker_review")
        self.assertTrue(protected.needs_review)

    def test_legacy_cached_index_rebuilds_after_dialogue_segmentation_contract_changes(self):
        chapter = Chapter(1, "Scene", "She called it an “accident” and left.")
        with tempfile.TemporaryDirectory() as temporary:
            folder = self.make_project_folder(temporary)
            current = load_or_build_passage_index(folder, [chapter])
            path = folder / INDEX_FILENAME
            saved = json.loads(path.read_text(encoding="utf-8"))
            saved["schema_version"] = 1
            path.write_text(json.dumps(saved), encoding="utf-8")

            rebuilt = load_or_build_passage_index(folder, [chapter])
            self.assertEqual(INDEX_SCHEMA_VERSION, 3)
            self.assertEqual(rebuilt["schema_version"], 3)
            self.assertTrue(any(
                row["text"] == "“accident”"
                and row["kind"] == "narration"
                and row["source"] == "automatic_embedded_quote"
                for row in rebuilt["passages"]
            ))

    def test_quoted_term_at_sentence_start_is_narration_when_prose_continues(self):
        from app.chapters.speaker_segmentation import segment_chapter_speakers

        source = '“Accidents” were common in that dungeon.'
        segments = segment_chapter_speakers(Chapter(1, "Quoted term", source))
        self.assertTrue(any(
            row.kind == "narration" and row.source == "automatic_embedded_quote"
            and row.text == "“Accidents”"
            for row in segments
        ))

    def test_reopened_quote_mark_splits_malformed_multi_turn_dialogue(self):
        from app.chapters.speaker_segmentation import segment_chapter_speakers

        source = '“Pumped?\n“Yeah, see, I’m so ridiculously hyped.”'
        chapter = Chapter(1, "Two turns", source)
        segments = segment_chapter_speakers(chapter)
        dialogue = [row for row in segments if row.kind != "narration"]

        self.assertEqual(len(dialogue), 2)
        self.assertEqual(dialogue[0].text, "“Pumped?")
        self.assertEqual(dialogue[1].text, "“Yeah, see, I’m so ridiculously hyped.”")
        self.assertEqual(dialogue[0].end, dialogue[1].start - 1)

    def test_saved_index_with_wrong_source_slice_is_rebuilt_not_trusted(self):
        chapter = Chapter(1, "Scene", "Narration.\n\n“Check source.”")
        with tempfile.TemporaryDirectory() as temporary:
            folder = self.make_project_folder(temporary)
            first = load_or_build_passage_index(folder, [chapter])
            path = folder / INDEX_FILENAME
            saved = json.loads(path.read_text(encoding="utf-8"))
            saved["passages"][0]["text"] = "not the saved source"
            path.write_text(json.dumps(saved), encoding="utf-8")

            rebuilt = load_or_build_passage_index(folder, [chapter])
            self.assertEqual(rebuilt["index_revision"], first["index_revision"])
            for row in rebuilt["passages"]:
                self.assertEqual(chapter.text[row["start"]:row["end"]], row["text"])



    def test_sentence_final_quoted_phrase_inside_unfinished_narration_is_not_dialogue(self):
        from app.chapters.speaker_segmentation import segment_chapter_speakers

        source = (
            'The protagonist was going to cause an event that would go far beyond '
            '“some issues.” and put everyone in danger.'
        )
        segments = segment_chapter_speakers(Chapter(1, "Inline phrase", source))
        quote_start = source.index('“some issues.”')
        quote = next(row for row in segments if row.start <= quote_start < row.end)
        self.assertEqual(quote.kind, "narration")
        self.assertEqual(quote.source, "automatic_embedded_quote")

    def test_narrative_proverb_introduction_is_not_a_speaker_label(self):
        from app.chapters.speaker_segmentation import segment_chapter_speakers

        source = (
            'There was a proverb I found when researching the labyrinths: '
            '“To consider the nature of dungeons is like questioning death.”'
        )
        segments = segment_chapter_speakers(Chapter(1, "Proverb", source))
        self.assertTrue(any(
            row.kind == "narration" and row.source == "automatic_embedded_quote"
            and "nature of dungeons" in row.text
            for row in segments
        ))

    def test_reported_speech_introduction_keeps_the_quoted_words_as_dialogue(self):
        from app.chapters.speaker_segmentation import segment_chapter_speakers

        source = 'She disclosed that “Everything I said back then was a front…”'
        segments = segment_chapter_speakers(Chapter(1, "Reported speech", source))
        self.assertTrue(any(
            row.kind == "needs_speaker_review" and "Everything I said" in row.text
            for row in segments
        ))

    def test_dash_narration_and_perspective_headings_are_not_spoken_turns(self):
        from app.chapters.speaker_segmentation import segment_chapter_speakers

        source = (
            'I was about to answer.\n'
            '—gave my reply.\n\n'
            '—Yukine’s Perspective— How is she for real?\n\n'
            '—our teacher told us to take our seats. My savior!\n\n'
            '—nope, no chance at all.\n'
            '“Yes, I understand.”'
        )
        segments = segment_chapter_speakers(Chapter(1, "Dash boundaries", source))
        dash_rows = [row for row in segments if row.text.startswith("—")]
        self.assertTrue(dash_rows)
        self.assertTrue(all(row.kind == "narration" for row in dash_rows))
        self.assertTrue(any(
            row.kind == "needs_speaker_review" and row.text == '“Yes, I understand.”'
            for row in segments
        ))

    def test_uppercase_dash_spoken_turn_remains_reviewable_dialogue(self):
        from app.chapters.speaker_segmentation import segment_chapter_speakers

        source = '—Yes, I heard you.'
        segments = segment_chapter_speakers(Chapter(1, "Dash speech", source))
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].kind, "needs_speaker_review")



    def test_reported_speech_after_explains_and_states_remains_dialogue(self):
        from app.chapters.characters import is_embedded_quotation_reference

        examples = [
            'she explains that “Everything I said back then was a front…”',
            'she states, “But now things are different, because I have you…”',
            'she says that “I was left behind in the dungeon.”',
        ]
        for source in examples:
            start = source.index("“")
            end = source.index("”", start) + 1
            with self.subTest(source=source):
                self.assertFalse(is_embedded_quotation_reference(source, start, end))

if __name__ == "__main__":
    unittest.main()
