from __future__ import annotations

"""Run the complete unittest suite and write a downloadable evidence bundle."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import time
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "test-evidence"
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("PYTHONPATH", str(ROOT))
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")


class EvidenceTextResult(unittest.TextTestResult):
    """Capture per-test status and duration without changing test semantics."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.case_records = []
        self._active = {}

    def startTest(self, test):
        record = {
            "test_id": test.id(),
            "status": "running",
            "duration_seconds": None,
        }
        self.case_records.append(record)
        self._active[test.id()] = record
        record["_start"] = time.perf_counter()
        super().startTest(test)

    def _finish(self, test, status, details=None):
        record = self._active.get(test.id())
        if record is None:
            return
        record["status"] = status
        record["duration_seconds"] = round(
            max(0.0, time.perf_counter() - record["_start"]), 6
        )
        record.pop("_start", None)
        if details:
            record["details"] = details

    def addSuccess(self, test):
        self._finish(test, "passed")
        super().addSuccess(test)

    def addFailure(self, test, err):
        self._finish(test, "failed", self._exc_info_to_string(err, test))
        super().addFailure(test, err)

    def addError(self, test, err):
        self._finish(test, "error", self._exc_info_to_string(err, test))
        super().addError(test, err)

    def addSkip(self, test, reason):
        self._finish(test, "skipped", str(reason))
        super().addSkip(test, reason)

    def addExpectedFailure(self, test, err):
        self._finish(test, "expected_failure", self._exc_info_to_string(err, test))
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self._finish(test, "unexpected_success", "Test unexpectedly passed.")
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self._finish(test, "failed", self._exc_info_to_string(err, test))
        super().addSubTest(test, subtest, err)

    def stopTest(self, test):
        record = self._active.get(test.id())
        if record and record["status"] == "running":
            self._finish(test, "unknown", "No terminal unittest result was recorded.")
        super().stopTest(test)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    stream = io.StringIO()
    captured = io.StringIO()
    suite = unittest.defaultTestLoader.discover(start_dir="tests")
    runner = unittest.TextTestRunner(
        stream=stream,
        verbosity=2,
        resultclass=EvidenceTextResult,
        failfast=False,
        buffer=False,
    )

    started_utc = datetime.now(timezone.utc)
    wall_start = time.perf_counter()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        result = runner.run(suite)
    elapsed = round(max(0.0, time.perf_counter() - wall_start), 3)
    finished_utc = datetime.now(timezone.utc)

    counts = {}
    for case in result.case_records:
        status = case.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
        case.pop("_start", None)

    evidence_complete = len(result.case_records) == result.testsRun and counts.get("unknown", 0) == 0
    successful = result.wasSuccessful() and evidence_complete
    summary = {
        "total": result.testsRun,
        "case_records": len(result.case_records),
        "passed": counts.get("passed", 0),
        "failed": counts.get("failed", 0),
        "errors": counts.get("error", 0),
        "skipped": counts.get("skipped", 0),
        "expected_failures": counts.get("expected_failure", 0),
        "unexpected_successes": counts.get("unexpected_success", 0),
        "unknown": counts.get("unknown", 0),
        "successful": successful,
        "evidence_complete": evidence_complete,
        "elapsed_seconds": elapsed,
    }
    metadata = {
        "title": "Ryu's Audiobook — Stage 1 Regression Test Evidence",
        "generated_at_utc": finished_utc.isoformat(),
        "started_at_utc": started_utc.isoformat(),
        "repository": os.environ.get("GITHUB_REPOSITORY", "RyuBlanc/ryu-audiobook-build"),
        "branch": os.environ.get("GITHUB_REF_NAME", "local"),
        "commit_sha": os.environ.get("GITHUB_SHA", "unknown"),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "workflow_run_number": os.environ.get("GITHUB_RUN_NUMBER", "local"),
        "python_version": sys.version,
    }
    payload = {
        "metadata": metadata,
        "summary": summary,
        "test_cases": result.case_records,
        "failures": [
            {"test_id": test.id(), "traceback": detail}
            for test, detail in result.failures
        ],
        "errors_detail": [
            {"test_id": test.id(), "traceback": detail}
            for test, detail in result.errors
        ],
    }

    result_json = OUTPUT / "stage1-test-results.json"
    result_json.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    run_url = (
        os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        + "/"
        + metadata["repository"]
        + "/actions/runs/"
        + str(metadata["workflow_run_id"])
    )
    summary_text = (
        f"{metadata['title']}\n"
        f"Generated UTC: {metadata['generated_at_utc']}\n"
        f"Repository: {metadata['repository']}\n"
        f"Branch: {metadata['branch']}\n"
        f"Commit: {metadata['commit_sha']}\n"
        f"Workflow run: {run_url}\n"
        f"Result: {'PASS' if summary['successful'] else 'FAIL'}\n"
        f"Cases run: {summary['total']}; per-case records: {summary['case_records']}; "
        f"passed: {summary['passed']}; failed: {summary['failed']}; "
        f"errors: {summary['errors']}; skipped: {summary['skipped']}; "
        f"expected failures: {summary['expected_failures']}; "
        f"unexpected successes: {summary['unexpected_successes']}; unknown: {summary['unknown']}\n"
        f"Elapsed: {summary['elapsed_seconds']} seconds\n\n"
        "=== unittest verbose result log ===\n"
        + stream.getvalue()
        + "\n=== stdout/stderr captured during tests ===\n"
        + captured.getvalue()
    )
    (OUTPUT / "stage1-test-results.txt").write_text(summary_text, encoding="utf-8")

    acceptance_matrix = f"""# Stage 1 — Acceptance Evidence Matrix

- **CI run:** [{metadata['workflow_run_id']}]({run_url})
- **Branch:** {metadata['branch']}
- **Commit:** {metadata['commit_sha']}
- **Full automated suite:** **{'PASS' if summary['successful'] else 'FAIL'}** — {summary['total']} cases, {summary['passed']} passed, {summary['failed']} failed, {summary['errors']} errors, {summary['skipped']} skipped.
- **Automated evidence:** stage1-test-results.json and stage1-test-results.txt in this artifact.

## Requirement status

| Requirement | Automated evidence | Status after CI | Runtime acceptance still required |
|---|---|---|---|
| UI-01 — Premium V2 default/startup | default-installed-interface and native-compatibility tests; packaged frontend checks | Automated pass | Launch the installed build; confirm first screen, persisted settings and no fallback UI |
| UI-02 — Overlap/readability | responsive shell/header/layout contracts; notification boundaries; compact-window style tests | Automated contracts pass | Inspect screens for overlap, clipped text, low contrast and doubled/ghosted text |
| UI-03 — Flicker with effects enabled | effect/blur caps; in-place job updates; stable refresh and stale-response regressions | Automated contracts pass | With Effects=High and Reduce Motion OFF, navigate repeatedly and observe for flicker/black flashes during idle and active synthesis |
| UI-04 — Desktop behaviour | native geometry, minimum size, saved text-scale/window-size settings and startup recovery contracts | Automated contracts pass | Minimize, maximize/restore, move/resize, collapse/scroll sidebar, restart to verify saved preferences and error recovery |
| UI-05 — Notifications/errors/empty states | toast/miniplayer bounds, failed-playback error preservation, backend handler and empty-state regressions | Automated contracts pass | Confirm live notifications do not cover controls/player and success appears only after the operation succeeds |
| UI-06 — Responsive acceptance | compact-width/responsive shell and merged resize-handler contracts | Automated contracts pass | Inspect 1920x1080, 1366x768 and 1280x720, plus narrow resize, menus, dialogs, selections and scrolling |
| UI-07 — Existing stability safeguards | in-place refresh, stale-response guards, chapter draft/scroll, autosave/state restoration and background-job tests | Automated contracts pass | Exercise multi-page navigation while synthesis/polling runs; verify no draft loss, scroll jumps or frozen UI |
| Production metadata gate | complete/missing fields, narrator lookup, legacy series-volume compatibility and invalid/corrupt/missing cover regressions | Automated gate tests pass | Verify incomplete saved metadata blocks full-book generation with guidance; preview remains separate |
| Playable output readiness | audio URL validation and playback-state/recovery regression tests | Automated contracts pass | Play a real generated output through completion; test replay and invalid/missing-file recovery |

## Important interpretation

This matrix separates source/contract tests from an interactive test of the packaged Windows executable. A successful CI run does not prove that visual overlap and flicker are absent on the user's desktop. Stage 1 should not be marked fully closed until runtime checks above are recorded against this build.

## Manual result recording

For each runtime row, record PASS, FAIL or BLOCKED, the screen/resolution, steps taken, and any screenshot/video or log reference. For UI-03, record the exact Effects and Reduce Motion settings; the acceptance target is smooth operation with effects enabled and without requiring Reduce Motion to be turned on.
"""
    (OUTPUT / "stage1-acceptance-matrix.md").write_text(acceptance_matrix, encoding="utf-8")

    print(summary_text)
    print(f"Machine-readable test evidence: {result_json}")
    print(f"Stage 1 acceptance matrix: {OUTPUT / 'stage1-acceptance-matrix.md'}")
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
