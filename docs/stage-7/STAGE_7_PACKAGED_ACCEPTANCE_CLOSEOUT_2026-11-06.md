# Stage 7 — Packaged Acceptance Closeout Candidate

**Audit date:** 6 November 2026  
**Baseline:** `d4b4c20cad02852480dcf4072841df07abe1f747`  
**Baseline branch:** `stage-7/step-2-storage-management`  
**Candidate branch:** `stage-7/packaged-acceptance-closeout-2608`

## Purpose

Run the Windows packaged acceptance gate against the latest source-test-green Stage 7 candidate. This checkpoint is specifically required because the latest ordinary push (#2608) skipped the Windows build/package job. No Stage 7 completion claim is made by this ledger entry.

## Failure audit

### #2605 — packaged Production Chapter 2 selection timeout

- Workflow run: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42218590672
- Failing job: `build` (job ID `127895699388`); regression job passed.
- The packaged UI acceptance completed the Sound Design/Music Library checks and then timed out in `selectProductionPreviewChapter(2)`, specifically `waitForSelection`.
- The picker assertion required the status label to contain the exact phrase `Chapter 2 selected.`. When a valid preview already existed for the selected chapter, the UI could render a Preview ready state instead. The test therefore coupled chapter selection to one presentation string and rejected a valid ready state.
- The fix is present in baseline commit `d4b4c20`: the Production Preview status now reports `Preview ready · Chapter N` only when the valid preview's recorded chapter number matches the currently selected chapter; the packaged selector assertion accepts either the selected state or the chapter-qualified Preview ready state.
- This addresses the observed status-contract mismatch, not by extending the timeout. Matching-head packaged acceptance is still required to prove the frozen application passes.

### #2606 — background TTS benchmark fixture failure

- Workflow run: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42219666871
- The full suite failed because `test_performance_benchmark_runs_in_background_and_reports_real_measurement` invoked the real installed-voice precondition without creating an isolated Piper model fixture.
- The failure was a test-fixture defect: `_performance_benchmark` correctly refuses to enqueue a real benchmark when no local Piper ONNX voice is installed.
- Correction is present in #2607 commit `643a52fa1bbcf418a7ef460cd9da3732c25710d3`: the test now creates a temporary `Models/piper/en_US-test-medium.onnx` fixture and isolates its paths.
- #2607 passed the full 1,246-test suite. #2608 then passed the updated 1,247-test suite.

## Existing CI evidence

| Run | Commit | Result | Evidence |
|---|---|---|---|
| #2605 | `e7065e933195dcb4141052ee690833fb73c3bd34` | Failed | Source tests passed; packaged acceptance timed out in Production Chapter 2 selection |
| #2606 | `9207ab8ceafb291c3299f55704f38cc4e3c49856` | Failed | Benchmark test lacked an isolated installed Piper fixture |
| #2607 | `643a52fa1bbcf418a7ef460cd9da3732c25710d3` | Passed | Isolated Piper fixture correction; 1,246 tests passed |
| #2608 | `d4b4c20cad02852480dcf4072841df07abe1f747` | Passed | Chapter-qualified preview readiness correction; 1,247 tests passed; Windows build skipped on ordinary push |

## Required checkpoint acceptance

This candidate must run both jobs on the exact same HEAD:

1. Full regression suite, including the isolated Piper benchmark fixture.
2. Frozen Windows application verification and packaged Sound Design/Music Library acceptance, including Production Chapter 2 selection.
3. Windows installer payload and portable application build.
4. Release SHA-256 manifest generation and artifact upload.

The packaged gate must explicitly pass the Production Chapter 2 selection and chapter-qualified preview-ready state in the frozen application. A green source-test job alone is not sufficient.

## Remaining Stage 7 work

This checkpoint does not close Steps 4–7. After packaged acceptance, continue hardware/runtime truthfulness and compatibility, Performance Center measurement/history, automatic hardware optimization and Qwen performance, cross-module integration, UI gap coverage, and final packaged release acceptance. Preserve the approved Premium V2 design and all previously accepted Stage 1–6 behavior.

**Status: checkpoint queued by commit; acceptance pending GitHub Actions result.**
