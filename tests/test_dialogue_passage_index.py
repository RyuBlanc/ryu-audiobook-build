from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.chapters.detector import Chapter
from app.chapters.passage_index import (
    INDEX_FILENAME,
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


if __name__ == "__main__":
    unittest.main()
