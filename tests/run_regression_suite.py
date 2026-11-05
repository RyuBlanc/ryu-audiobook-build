"""Run the complete unittest suite except required isolated native Qt lifecycle cases.

Those cases run in their own Python processes in the Windows workflow so they cannot
inherit or corrupt Qt global state created by unrelated tests. They are not skipped:
the workflow executes each as a separate required step before this runner.
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
    "test_regressions.RegressionTests."
    "test_voice_preview_is_invalidated_when_target_settings_change",
    "tests.test_regressions.RegressionTests."
    "test_voice_preview_is_invalidated_when_target_settings_change",
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
    # Ensure Python finalizers execute while Qt and multimedia DLLs are still
    # loaded. On Windows the interpreter otherwise tears down PySide6 objects
    # after the Qt runtime has begun unloading, which can terminate the process
    # after unittest has correctly reported OK.
    import gc
    gc.collect()
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
