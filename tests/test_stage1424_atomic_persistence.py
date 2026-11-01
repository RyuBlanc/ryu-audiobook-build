"""Stage 1424 regressions for crash-safe job/history and generation checkpoint writes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.tts.generator import _atomic_write_json
from app.ui.premium_v2_host import PremiumV2Bridge


class Stage1424AtomicPersistenceTests(unittest.TestCase):
    def _assert_replace_failure_preserves_previous_file(self, writer, target: Path, new_value):
        original = '{"previous": "known-good"}\n'
        target.write_text(original, encoding="utf-8")

        with patch.object(Path, "replace", side_effect=OSError("simulated interrupted replacement")):
            with self.assertRaisesRegex(OSError, "simulated interrupted replacement"):
                writer(target, new_value)

        self.assertEqual(target.read_text(encoding="utf-8"), original)
        self.assertEqual(list(target.parent.glob(f".{target.name}.*.tmp")), [])

    def test_job_and_history_json_writes_preserve_last_good_file_on_replace_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "premium_v2_history.json"
            rows = [{"job_id": "task-1", "state": "completed"}]
            self._assert_replace_failure_preserves_previous_file(
                lambda path, payload: PremiumV2Bridge._persist_json_rows(object(), path, payload),
                target,
                rows,
            )

    def test_generation_state_writer_preserves_last_good_file_on_replace_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "generation.json"
            self._assert_replace_failure_preserves_previous_file(
                _atomic_write_json,
                target,
                {"completed": [0, 1], "chunks_total": 2},
            )

    def test_resume_metadata_and_chunk_manifest_use_atomic_json_writes(self):
        source = Path("app/tts/generator.py").read_text(encoding="utf-8")
        start = source.index("def prepare_chapter_plan(")
        end = source.index("\ndef generate_chapter(", start)
        preparation = source[start:end]
        self.assertIn('_atomic_write_json(\n        chapter_dir / "narration.json"', preparation)
        self.assertIn('_atomic_write_json(chapter_dir / "chunk_manifest.json", chunk_manifest)', preparation)
        self.assertNotIn('(chapter_dir / "narration.json").write_text(', preparation)
        self.assertNotIn('(chapter_dir / "chunk_manifest.json").write_text(', preparation)


if __name__ == "__main__":
    unittest.main()
