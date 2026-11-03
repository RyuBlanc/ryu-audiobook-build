# Stage 5.4 — Full Generation Engine & Job Management

## Baseline and working candidate

- Stage 5.3 accepted baseline: `18dc29585ebb0c72e346a9694166d65db27757b8`
- Stage 5.3 accepted workflow: [#2211](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41689204000)
- Stage 5.4 implementation branch: `stage-5/step-4-generation-engine`
- Implementation commit before this status record: `01c30d94974fa8b54e80127ad28c9919fb0d1542`
- This document records source-level changes only. No Stage 5.4 item is marked VERIFIED COMPLETE until matching-head automated and applicable runtime acceptance evidence is recorded.

## Formal scope

| Requirement | Priority | Acceptance focus | Current status |
|---|---|---|---|
| GEN-01 | P0 | Full generation consumes the selected project's saved narrator, cast, pronunciation, BGM/cue, metadata and output settings | Existing backend input path preserved; matching-head verification pending |
| GEN-02 | P1 | Reuse only compatible, complete chapter/chunk checkpoints; repair missing/corrupt/incompatible chunks | CODE CHANGED — NOT VERIFIED |
| GEN-03 | P1 | Actual pause, resume, cancel, retry and interrupted-job recovery | CODE CHANGED — NOT VERIFIED |
| GEN-04 | P1 | Skip empty/excluded chapters in order; reject all-ineligible projects | Existing preflight preserved; matching-head verification pending |
| PROD-14 | P0 | One project/job identity and truthful state across Production, Readiness, Background Jobs, History and output | Race guard and explicit retry/recovery ownership linkage added; matching-head verification pending |

## Work added on the Stage 5.3 baseline

### Checkpoint integrity
- Added `is_valid_wav_chunk` to validate the PCM WAV header and read the complete declared sample payload.
- Cached chunk reuse now rejects missing, truncated and invalid payloads even when the WAV header remains intact.
- Newly synthesized chunks are validated before their completion index is committed.
- Resume inspection now requires the stable chapter identity where available, a generation signature, all expected chunk indexes and valid payloads before classifying a chapter as complete.
- Invalid or incomplete checkpoint folders remain visible as partial/recoverable state so the generator can regenerate affected chunks.

### Safe pause/resume and cancellation
- `GenerationManager` now receives a checkpoint callback from the chapter generator.
- A pause request is honoured after a validated chunk or complete synthesis batch has been persisted.
- Cancellation detected at that checkpoint exits generation as cancelled rather than misclassifying an intentionally partial chapter as a generation failure.
- The existing chapter-boundary pause remains as an additional safe point.

### Job controls and ownership
- Added `job.retry` and `job.recover` bridge handlers and capability flags.
- Retry/recovery restarts generation for the original job's saved project folder, not whichever project happens to be selected in the UI.
- Retry is restricted to recoverable failed jobs and cancelled generation jobs. Recovery is restricted to jobs explicitly marked interrupted and recoverable.
- A newer generation job that owns the project prevents an older job from being retried over it.
- A second active full-generation job for the same project is rejected.
- New attempts are linked to the prior job with `retry_of_job_id`, `recovery_of_job_id` and an incremented retry count.
- Terminal job results are not overwritten by late pause/resume/cancel requests.
- Background Jobs now renders actual Retry/Recover actions for eligible failed/cancelled generation jobs.

## Regression coverage added/extended

- Truncated WAV payload with intact header is rejected and regenerated.
- Resume inspector does not classify truncated checkpoint audio as completed.
- Pause and resume can occur within one long chapter after a saved chunk boundary.
- Retry targets the original project after project selection changes.
- Recovery accepts only interrupted/recoverable generation jobs.
- Retry is rejected if a newer job owns the project or the failed job is not recoverable.
- Late pause/resume/cancel operations cannot overwrite a terminal completion.
- Background Jobs adapter contract includes real Retry/Recover command routing.

## Remaining Stage 5.4 verification

1. Run the full Windows regression suite on the exact Stage 5.4 candidate SHA and fix every failing test at root cause.
2. Confirm the packaged full-generation path still consumes the actual saved narrator, character assignments, pronunciation and sound settings.
3. Exercise pause/resume from a mid-chapter chunk checkpoint, cancellation at a checkpoint, retry after failed/cancelled generation and interrupted-job recovery after an application restart.
4. Verify empty/ineligible chapter handling, preserved order and all-empty rejection.
5. Verify the same project/job ID and terminal state across Production Studio, Readiness, Background Jobs, History and the registered output.
6. Perform installed Windows acceptance with a real multi-chapter project. Automated source tests alone do not satisfy this requirement.
7. Retain Stage 5.3 workflow #2211 and artifacts as the prior-stage baseline; do not rebuild Stage 5.3 independently.

## Stage 5.4 exit decision

**OPEN — NOT YET ACCEPTED.**

Exit only when GEN-01, GEN-02, GEN-03, GEN-04 and PROD-14 are verified on the same intended implementation commit, the full matching-head regression and Windows packaging checkpoints pass, and actual Windows generation/control/recovery acceptance is recorded. Final M4B metadata/chapter-output validation and Audiobooks handoff remain in the subsequent Stage 5.5 integration/assembly closeout where applicable.
