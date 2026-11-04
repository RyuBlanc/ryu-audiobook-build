# Stage 5.4 — Full Generation Engine & Job Management

## Baseline and candidate

- Accepted Stage 5.3 branch: `stage-5/step-1-production-metadata`
- Accepted Stage 5.3 commit: `18dc29585ebb0c72e346a9694166d65db27757b8`
- Accepted Stage 5.3 Windows workflow: [#2211](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41689204000)
- Stage 5.4 working branch: `stage-5/step-4-generation-engine`
- Stage 5.4 final candidate/checkpoint: `8132097b6028a17d44ddc2f03c8f514d4cd88598`
- Final matching-head Windows artifact-checkpoint workflow: [#2235](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41755362901)
- Regression result on #2235: **1,138 tests passed**; frontend JavaScript syntax validation and isolated native Qt lifecycle regression passed.
- Windows frozen application build, frozen executable verification, bundled voice assets/critical modules and packaged Stage 5.4 runtime acceptance all passed on #2235.
- All eight Stage 5.4 packaged runtime markers passed, including real multi-chapter generation, empty/excluded skips, pause/resume/cancel, Retry, project/History/output ownership, Dashboard readiness, and process-termination/restart recovery.
- Installer, portable Windows package and SHA-256 manifest were all successfully built and uploaded on the same code candidate. Installer release publishing was intentionally skipped; no public release was created.
- Stage 5.4 engineering exit: **CLOSED** on candidate `8132097b...`, with a separate documentation closeout commit recording the evidence below.


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

## Recent failed Stage 5.4 candidate runs and fixes

| Run | Commit | Observed package failure | Root cause / disposition |
|---|---|---|---|
| #2226 | `7e5b9526…` | Background Jobs pause message assertion failed | Stale acceptance expected the former chapter-boundary wording; updated to the implemented saved chunk/batch boundary wording |
| #2227 | `b4397e28…` | Multi-chapter completed-job assertion failed | Completed job result omitted the eligible/empty/excluded counts; retained the counters in the final job result and project summary |
| #2228–#2231 | `9a71c7aa…`–`2ca809db…` | Failed / Cancelled filter was missing in the packaged UI test | The original modal only had Active/Completed/All; the dynamic Failed / Cancelled filter was added for retry/recovery |
| #2232 | `9bf6d3c1…` | Production-owned Chapter 2 selection timed out | The adapter had already auto-selected Chapter 2, so dispatching a change to the same value was a no-op; acceptance now selects another chapter first, then Chapter 2 |
| #2233 | `3763c222…` | Stage 5.4 control project absent from Dashboard recent cards | Dashboard shows only the three latest projects; acceptance now falls back to the full Library grid's normal Open project action |
| #2234 | `7d72008d…` | Dashboard running control timed out after Retry/Recover UI checks | The synthetic Background Jobs test left the filter on Failed / Cancelled; acceptance now restores Active before testing running/paused Dashboard states |

The six-second cue import exception in the earlier candidate runs is the intentional negative test confirming that cue clips longer than five seconds are rejected. It is not a product regression. Those earlier failures were superseded by #2235, which passed the frozen-app Stage 5.4 acceptance and cleared the installer, portable-package and SHA-256 upload gates.

## Formal scope and current status

| Requirement | Priority | Acceptance focus | Automated status |
|---|---|---|---|
| GEN-01 | P0 | Full generation consumes the active project's saved narrator, character assignments, pronunciation, BGM/cues, metadata and output settings | **PASSED** — regression suite + frozen Windows packaged generation on #2235 |
| GEN-02 | P1 | Reuse only compatible chapter/chunk checkpoints; detect missing/corrupt/incompatible audio; preserve valid unaffected work | **PASSED** — regression suite + packaged multi-chapter/checkpoint acceptance on #2235 |
| GEN-03 | P1 | Actual pause/resume/cancel/retry/recovery; safe checkpoint boundaries; backend-confirmed states | **PASSED** — real packaged UI controls and process-restart recovery on #2235 |
| GEN-04 | P1 | Skip empty/excluded chapters in saved order; reject all-ineligible projects | **PASSED** — two eligible chapters generated in saved order; empty and excluded chapters skipped on #2235 |
| PROD-14 | P0 | One project/job identity and consistent terminal state across Production, Readiness, Background Jobs, History and output | **PASSED** — GenerationManager, Background Jobs, History, Dashboard readiness and M4B output ownership reconciled on #2235 |

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

## Final Stage 5.4 verification — completed on #2235

| Exit check | Evidence | Result |
|---|---|---|
| Regression and frontend checks | 1,138 tests passed; frontend JavaScript syntax and isolated native Qt lifecycle checks passed | **PASS** |
| Windows package | Application build, frozen executable verification and bundled voice assets/critical modules | **PASS** |
| Saved-project generation | Frozen Windows app generated two eligible chapters in saved order using the saved bundled Offline Neural narrator | **PASS** |
| Empty/excluded handling | One empty and one excluded chapter were skipped; final job/project summary retained the skip counts | **PASS** |
| Actual generation controls | Background Jobs Pause, Resume and Cancel controlled a real GenerationManager job at persisted chunk checkpoints | **PASS** |
| Retry and ownership | Retry reused compatible checkpoints and preserved original project identity across job, History and output; Dashboard readiness reflected the same completed project | **PASS** |
| Restart recovery | A real paused generation job survived process termination as interrupted, was recovered via Background Jobs/native bridge in the next frozen-app process, reused checkpoints and completed with the same project/History/output identity | **PASS** |
| Release artifacts | Installer, portable Windows app and SHA-256 manifest built and uploaded successfully | **PASS** |

**Run:** [#2235 — Stage 5.4 artifact checkpoint](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41755362901)  
**Code candidate:** `8132097b6028a17d44ddc2f03c8f514d4cd88598`

Artifacts uploaded by #2235:
- [Windows installer](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41755362901/artifacts/13289020554) — artifact SHA-256 `30946b5ce10a371a55128b19a697d5c4c5a25855ec434474b5111aceaab9eb39`
- [Portable Windows app](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41755362901/artifacts/13289130038) — artifact SHA-256 `68f52ea14fc17ca9bd5c3abf82c832a3371c915489402d4c15a89e42d05803e0`
- [Release SHA-256 manifest](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41755362901/artifacts/13288497252) — artifact SHA-256 `30e7c153e809c99203bb149e779713d76a86e2e571d54d493dcdde75d4e419b6`

The Stage 5.4 CI acceptance exercised the frozen Windows application and real UI/native job commands, including a second process after termination. A separate hands-on installation and user-device smoke test is not represented by CI and remains a post-build operational check; it does not block the Stage 5.4 engineering exit recorded here. The verified installer release publishing step was intentionally skipped, so this closeout does not publish or tag version 1.2.0.

## Stage 5.4 exit decision

**CLOSED — ACCEPTED on 4 November 2026.**

All Stage 5.4 requirements GEN-01 through GEN-04 and PROD-14 passed their regression and frozen Windows packaged acceptance checkpoints on #2235. The historical failed candidate runs (#2226–#2234) have been reconciled by the final accepted build. Stage 5.5 final M4B assembly/metadata/chapter-marker validation and Audiobooks Library handoff remain subsequent work.
