"""Run the complete unittest suite except the isolated native Qt lifecycle case.

That case runs in its own Python process in the Windows workflow so it cannot
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


def _shutdown_qt_runtime() -> None:
    """Destroy the test QApplication while PySide/Qt DLLs are still loaded.

    The Windows runner can report all tests as OK and then terminate with
    STATUS_STACK_BUFFER_OVERRUN while the interpreter unloads a still-live
    QApplication at process shutdown. Explicitly close test widgets, flush
    deferred deletes, stop the event loop, and destroy the C++ application
    before Python begins unloading extension modules.
    """
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    import shiboken6

    app = QApplication.instance()
    if app is None:
        return

    app.closeAllWindows()
    app.processEvents()
    for widget in QApplication.allWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    app.quit()

    if shiboken6.isValid(app):
        shiboken6.delete(app)
    if shiboken6.isValid(app):
        raise RuntimeError("The regression runner could not destroy its QApplication cleanly.")


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
    # TestCase cleanups have run. Now tear Qt down explicitly while its native
    # libraries are still loaded; gc.collect alone does not destroy the global
    # QApplication before Python unloads PySide6 during process shutdown.
    import gc
    gc.collect()
    try:
        _shutdown_qt_runtime()
    except Exception as exc:
        print(f"Qt test-runtime shutdown failed: {exc!r}", file=sys.stderr)
        return 1
    gc.collect()
    sys.stdout.flush()
    sys.stderr.flush()
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
