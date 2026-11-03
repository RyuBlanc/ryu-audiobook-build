# Stage 5.4 — Full Generation Engine & Job Management

## Baseline and candidate

- Accepted Stage 5.3 branch: `stage-5/step-1-production-metadata`
- Accepted Stage 5.3 commit: `18dc29585ebb0c72e346a9694166d65db27757b8`
- Accepted Stage 5.3 Windows workflow: [#2211](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41689204000)
- Stage 5.4 working branch: `stage-5/step-4-generation-engine`
- Stage 5.4 implementation candidate: `25a0d1832b5753d483b0b17501874c660282618e`
- Matching-head regression workflow: [#2225](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41742660649)
- Regression result: **1,138 tests passed**; frontend JavaScript syntax validation passed; isolated native Qt lifecycle regression passed.
- Workflow #2225's Windows build job was skipped by the workflow's release-safety condition (build runs on `main`, a commit containing `[artifact-checkpoint]`, or `workflow_dispatch`). This status update intentionally uses the workflow's `[artifact-checkpoint]` trigger on the Stage 5.4 branch to obtain matching-head Windows packaging evidence. No merge to `main` is required.

## Historical Stage 5.4 workflow reconciliation

| Run | SHA / candidate | Result | Reconciliation |
|---|---|---|---|
| #2211 | `18dc2958…` | Success | Accepted Stage 5.3 baseline; preserved unchanged |
| #2212 | `18dc2958…` | Ran on baseline | Not Stage 5.4 implementation evidence |
| #2213 | `9e7b0e48…` | Failed | Early candidate tree omitted existing Stage 5.3 files; superseded, not accepted |
| #2214 | `da2d7110…` | Failed | Candidate had full tree but carried an older 19 KB workflow from `main` instead of the 59 KB Stage 5.3 workflow; workflow-contract checks failed, alongside stale test harness/fixture assertions; corrected |
| #2215–#2218 | Early candidate SHAs | Cancelled | Automatically superseded during early branch updates while old concurrency settings were in effect; none was manually cancelled; final workflow now uses a run-specific concurrency group and `cancel-in-progress: false` |
| #2219 | `bdd9ceb4…` | Failed | Earlier candidate/workflow state; not used as acceptance evidence |
| #2220 | `c9e01390…` | Failed | Two stale test contracts: old import-cancel bridge expression and resume fixture without stable chapter identity; corrected |
| #2221 | `59ddbefd…` | Failed | Same pre-correction fixture/contract failures; superseded |
| #2222 | `637eab41…` | Failed | Same two stale fixtures plus changed-text fixture recreated a chapter with a new ID; corrected to retain the original chapter ID for an edit |
| #2223 | `83c6e8e1…` | Failed | Only the changed-text fixture remained; corrected |
| #2224 | `a715fcd9…` | Failed | Only the changed-text fixture remained; corrected |
| #2225 | `25a0d183…` | Success | Full regression suite passed: 1,138 tests; exact implementation candidate verified |

No Stage 5.3 accepted branch or its uploaded artifacts were rewritten. Superseded/failed candidate runs are retained as history and are not counted as acceptance evidence.

## Formal scope and current status

| Requirement | Priority | Acceptance focus | Automated status |
|---|---|---|---|
| GEN-01 | P0 | Full generation consumes the active project's saved narrator, character assignments, pronunciation, BGM/cues, metadata and output settings | **AUTOMATED TESTS PASSED** on #2225; Windows packaged verification pending |
| GEN-02 | P1 | Reuse only compatible chapter/chunk checkpoints; detect missing/corrupt/incompatible audio; preserve valid unaffected work | **AUTOMATED TESTS PASSED** on #2225; Windows packaged verification pending |
| GEN-03 | P1 | Actual pause/resume/cancel/retry/recovery; safe checkpoint boundaries; backend-confirmed states | **AUTOMATED TESTS PASSED** on #2225; installed-app interaction acceptance pending |
| GEN-04 | P1 | Skip empty/excluded chapters in saved order; reject all-ineligible projects | **AUTOMATED TESTS PASSED** on #2225 |
| PROD-14 | P0 | One project/job identity and consistent terminal state across Production, Readiness, Background Jobs, History and output | **AUTOMATED TESTS PASSED** on #2225; installed-app consistency acceptance pending |

## Implementation retained and hardened

### GEN-01 — Real saved configuration
- Preserved the existing Production Studio generation path.
- The backend resolves the active or explicitly selected saved project.
- Uses the selected saved narrator profile and wraps the provider with the saved profile identity for checkpoint compatibility.
- Builds actual character-to-profile mappings from saved Character Studio assignments and uses the existing cast-aware provider.
- Applies the effective saved pronunciation dictionary.
- Loads the persisted Sound Design strategy, book/chapter BGM assignments, cues, volumes, fades and output settings.
- Uses saved Input Project Details metadata and the configured output folder/bitrate.
- No parallel or mock generation configuration was introduced.

### GEN-02 — Checkpoint integrity and stable chapter identity
- Added `is_valid_wav_chunk` to validate PCM WAV header values and read the complete declared sample payload.
- Cached and newly synthesized chunks are validated before reuse/completion.
- Resume inspection requires stable chapter identity where present, a generation signature, the full expected chunk-index set and readable WAV payloads before marking a chapter complete.
- Resume inspection locates checkpoints by stable `chapter_id` even after chapter numbering/title changes.
- A new chapter identity cannot adopt an existing same-number/title folder belonging to another chapter; it receives an identity-scoped folder, preserving the previous chapter's checkpoint.
- Editing the same chapter while retaining its stable ID updates that chapter's checkpoint and invalidates stale text/audio as required.
- Added regression coverage for truncated files with intact headers, chapter renumbering, identity collision and stale changed-text cache invalidation.

### GEN-03 — Real job control and recovery
- `GenerationManager` now checks pause/cancel requests after each persisted valid chunk or complete synthesis batch.
- A pause does not interrupt an active synthesis chunk; it pauses at the next saved chunk/batch boundary.
- Cancellation exits through the manager's actual cancelled path, preserving valid completed checkpoints.
- Pause/resume/cancel handlers recheck worker and terminal state after invoking the manager, preventing late requests from overwriting completed/failed/cancelled results.
- Added real `job.retry` and `job.recover` backend commands and Background Jobs actions.
- Retry is available for eligible failed/cancelled generation jobs; Recover is restricted to jobs marked interrupted by application restart.
- Retry/recovery targets the original saved project folder, not the current UI selection.
- A newer job that owns the project blocks retry/recovery of an older attempt.
- New attempts are linked to their source with `retry_of_job_id` / `recovery_of_job_id` and incremented retry count.

### GEN-04 — Eligible chapters
- Preserved existing rules: whitespace/empty chapters and explicitly excluded chapters are skipped.
- Eligible chapters preserve saved project order.
- Entirely empty/ineligible projects are rejected before a generation job is created with an actionable repair message.

### PROD-14 — Unified job ownership
- Preserved existing single job ID across Generation Engine, Background Jobs, History, project state and resulting output association.
- Added early and atomic pre-creation checks to prevent duplicate active audiobook-generation jobs for the same project, including simultaneous Generate/Retry requests.
- Preserved stale-callback and project-switch guards so older jobs cannot overwrite newer project ownership or attach outputs to another project.
- Reused existing polling and job-state mechanisms; no separate progress timer/state model was added.

## Regression coverage added or updated

- Truncated WAV with intact header is rejected and regenerated.
- Resume inspector does not mark an invalid or incomplete checkpoint complete.
- Stable chapter identity survives renumbering/title changes.
- New chapter identity does not adopt another chapter's same-number/title audio.
- Editing existing chapter text with the same ID invalidates stale chunks and assembled cache.
- Pause/resume works inside one chapter at a persisted chunk boundary.
- Retry targets the original project after project selection changes.
- Recover is restricted to interrupted/recoverable generation jobs.
- Retry is rejected for nonrecoverable failures or when a newer job owns the project.
- Late pause/resume/cancel cannot overwrite a terminal job result.
- Background Jobs exposes and routes actual Retry/Recover commands.
- Existing preflight, saved character voice, durable restart recovery, stale callback, project ownership and History/terminal identity tests remain in the suite.

## Remaining Stage 5.4 verification

1. Obtain Windows build, frozen application, packaged acceptance, installer/portable package and SHA-256 artifact evidence on the exact Stage 5.4 checkpoint commit.
2. Confirm packaged full generation consumes the saved narrator, saved cast, pronunciation, Sound Design and metadata configuration.
3. Verify an actual multi-chapter generation scenario, including eligible chapter order and empty/excluded chapter skips.
4. Exercise pause/resume within a chapter, cancel at a saved checkpoint, retry after failed/cancelled generation, and interrupted-job recovery after app restart.
5. Confirm Production Studio, Readiness, Background Jobs and History display the same project/job/terminal state and that output remains attached to the original project.
6. Record installed Windows/manual acceptance separately from automated CI. Source-level tests and a successful package build alone do not establish all user-facing control flows as runtime-verified.

## Stage 5.4 exit decision

**OPEN — NOT YET CLOSED.**

Automated regression acceptance passed on #2225. Stage 5.4 cannot receive formal closure until the matching-head Windows build/packaged evidence and applicable installed-app generation/control/ownership acceptance are recorded. Stage 5.5 final M4B metadata/chapter-marker validation and Audiobooks handoff remain subsequent work. Version 1.2.0 must not be tagged/published at this point.
