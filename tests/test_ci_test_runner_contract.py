"""Regression guards for Windows-safe CI evidence output."""
from pathlib import Path
import unittest


class CiTestRunnerContractTests(unittest.TestCase):
    def test_ci_runner_reconfigures_unicode_report_streams(self):
        runner = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "run_ci_tests.py"
        source = runner.read_text(encoding="utf-8")
        self.assertIn("for _stream in (sys.stdout, sys.stderr):", source)
        self.assertIn('_stream.reconfigure(encoding="utf-8", errors="replace")', source)
        self.assertIn("return 0 if successful else 1", source)


if __name__ == "__main__":
    unittest.main()
