"""Run the complete unittest suite except the isolated native Qt lifecycle case.

That Qt case runs in its own Python process in the Windows workflow so it cannot
inherit or corrupt Qt global state created by unrelated tests. It is not skipped:
the workflow executes it as a separate required step before this runner.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
ISOLATED_TEST_IDS = {
    "test_regressions.RegressionTests."
    "test_voice_preview_invalidation_ignores_deleted_qt_status_widget",
    "tests.test_regressions.RegressionTests."
    "test_voice_preview_invalidation_ignores_deleted_qt_status_widget",
}


def _cases(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _cases(item)
        else:
            yield item


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    loader = unittest.TestLoader()
    discovered = loader.discover(
        start_dir=str(TESTS),
        pattern="test_*.py",
        top_level_dir=str(ROOT),
    )
    remaining = [
        case for case in _cases(discovered)
        if case.id() not in ISOLATED_TEST_IDS
    ]
    suite = unittest.TestSuite(remaining)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
