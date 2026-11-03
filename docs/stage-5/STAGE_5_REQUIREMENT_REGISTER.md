# Stage 5 — Master Requirement Register

Repository: https://github.com/RyuBlanc/ryu-audiobook-build  
Execution branch: `stage-5/step-1-production-metadata`  
Stable starting commit: `ace9630d2d6b4a745c029906e0624637d4e3fdd3`  
Last updated: 2 November 2026

## Scope

Stage 5 contains **21 core requirements**: 15 Production Studio requirements and 6 generation/output requirements. Priorities remain **11 P0 release blockers** and **10 P1 essential workflow requirements**. Audiobooks AB-01–AB-07 are downstream integration dependencies, not additional core Stage 5 requirements.

Allowed statuses: OPEN; IN PROGRESS; CODE CHANGED — NOT VERIFIED; AUTOMATED TESTS PASSED; RUNTIME ACCEPTANCE PENDING; VERIFIED COMPLETE; BLOCKED; UNSUPPORTED — EXPLICITLY DOCUMENTED.

| ID | Priority | Requirement | Status | Implementation / evidence | Remaining work |
|---|---|---|---|---|---|
| PROD-01 | P0 | Input Project Details button and functional editor | CODE CHANGED — NOT VERIFIED | Step 5.1 Premium V2 dialog and toolbar control | Exact-commit CI and Windows runtime acceptance; #2096 passed the UI save/retry flow but exposed a Windows path-separator defect in the acceptance assertion, corrected in the next checkpoint |
| PROD-02 | P0 | Complete metadata fields and real historical values | CODE CHANGED — NOT VERIFIED | Project-scoped bridge save/history; values from local projects and Character Library | CI plus history/project isolation/restart acceptance |
| PROD-03 | P0 | Saved-metadata completion gate | CODE CHANGED — NOT VERIFIED | Shared validator, live warning/complete state and backend generation guard | CI, unsaved-edit and save-failure acceptance |
| PROD-04 | P0 | Metadata persistence and final output tags | CODE CHANGED — NOT VERIFIED | Project-scoped metadata transaction; Series Volume mapped to M4B `series_number`; unsupported-for-M4B cover formats normalized to PNG | Exact-commit regression and packaged M4B tag/cover acceptance in Step 5.5 |
| PROD-05 | P0 | Real generation progress | CODE CHANGED — NOT VERIFIED | Premium V2 full-generation ring now renders its own backend job's chapter, stage, measured elapsed time and backend ETA | Exact-commit regression and packaged Windows runtime acceptance pending |
| PROD-06 | P0 | Separate preview/full-generation states | CODE CHANGED — NOT VERIFIED | Independent Production preview/full-generation monitors and job IDs; full controls are bound only to the full-generation job | Exact-commit concurrency/isolation and runtime acceptance pending |
| PROD-07 | P0 | 10/30/60/90-second real preview controls | CODE CHANGED — NOT VERIFIED | Existing 10/30/60/90 selector and backend target-duration limiter preserved; explicit Play/Pause/Stop/Replay and Cancel Preview controls connected to the real preview job | Exact-commit duration matrix, audio validation, playback and cancellation acceptance pending |
| PROD-08 | P1 | Live pronunciation toggle | OPEN | Existing Pronunciation integration retained | Test global Off and individually enabled rules |
| PROD-09 | P1 | Live BGM/cue toggle | OPEN | Existing Sound Design integration retained | Test Same BGM, Chapter-Based BGM, Voice Only and cues |
| PROD-10 | P1 | Dynamic project summary | CODE CHANGED — NOT VERIFIED | Active summary extended with Genre and Series Volume; saved project data retained | CI and project-switch/reopen acceptance |
| PROD-11 | P1 | Accurate music summary | CODE CHANGED — NOT VERIFIED | Existing live Sound Design summary retained, including unique chapter-track aggregation | Exact-commit regression and runtime strategy checks |
| PROD-12 | P1 | Accurate output summary | CODE CHANGED — NOT VERIFIED | Existing active project output path, format and bitrate summary retained | Verify against actual settings/job configuration |
| PROD-13 | P1 | Seven-indicator live Readiness Center | CODE CHANGED — NOT VERIFIED | Existing seven backend-derived indicators retained | Exact-commit regression and runtime transitions |
| PROD-14 | P0 | Consistent job state across Production, Background Jobs, History and output | OPEN | Existing stable job IDs/polling retained | Integration and cross-project/stale-state tests |
| PROD-15 | P1 | Chapter-specific preview audio and download | OPEN | Existing preview bridge identified | Chapter-only synthesis, ownership, playback/download acceptance |
| GEN-01 | P0 | Real generation using saved project configuration | OPEN | Existing GenerationManager/config handoff retained | End-to-end generation with actual saved inputs |
| GEN-02 | P1 | Compatible resumable/recoverable checkpoints | OPEN | Stage 4 stable chapter identity safeguards preserved | Compatibility invalidation and recovery acceptance |
| GEN-03 | P1 | Real pause/resume/cancel/retry/recovery | OPEN | Existing job controls retained | Real-operation and restart recovery acceptance |
| GEN-04 | P1 | Empty/ineligible chapter handling | OPEN | Existing preflight behavior retained | All-empty rejection and order-preservation tests |
| GEN-05 | P0 | Chaptered M4B validation, metadata and cover | OPEN | Stage 4 full-stream decode/assembly work preserved | Actual output validation and metadata/cover inspection |
| GEN-06 | P0 | Preview/final effective configuration parity | OPEN | Stage 4 parity regression foundation preserved | Complete scenario matrix and real audio validation |

## Five-step execution sequence

| Step | Scope | Requirement IDs | Exit condition |
|---|---|---|---|
| 5.1 | Input Project Details, metadata persistence/gate, dynamic summary, music/output summary, seven readiness indicators | PROD-01–04, PROD-10–13 | Active saved project data is accurate; incomplete/unsaved metadata blocks full generation; exact-commit tests pass |
| 5.2 | Generation Engine interface, actual preview, duration controls, pronunciation/BGM toggles, chapter-specific preview/download | PROD-05–09, PROD-15, GEN-06 | Both preview workflows use real configuration and protect project/chapter ownership |
| 5.3 | Full generation, saved inputs, checkpoint compatibility, pause/resume/cancel/retry/recovery and empty-chapter handling | PROD-14, GEN-01–04 | Generation safely resumes from compatible chunks; control operations are real; all-empty books are rejected |
| 5.4 | M4B assembly, output metadata/cover, validation, Audiobooks handoff and cross-module consistency | GEN-05–06, PROD-10–15 | A real chaptered M4B validates and is associated with the correct project/job |
| 5.5 | Full regression, packaged Windows candidate and final Stage 5 sign-off | All applicable requirements and AB-02/AB-04/AB-07 dependencies | Exact candidate has passing regression/package evidence plus recorded Windows runtime and real-audio acceptance |

## Step 5.1 required-field policy

The supplied Step 5.1.1 block labels all ten fields as **Required metadata fields**. The completion gate therefore requires **Book Title, Author, actual selected Narrator profile, Publisher, Series, Series Volume, Language, Release Year, Genre and a valid project-local Cover Image**. A missing, unsupported, empty or unavailable cover does not pass. The UI identifies every missing field and preview remains available while full-book generation is blocked.

## Evidence rules

A button, static assertion, job submission, file existence or build alone does not prove completion. Record implementation commit, named tests/results, Actions run number/URL, runtime evidence where required, artifact identity where relevant and remaining limitations for every requirement. No core requirement may be removed or reprioritized.


## Step 5.1 interpretation correction

The first implementation gated only Title, Author, Narrator, Language and Genre. On re-reading the supplied Step 5.1.1 list, all ten entries are under the heading "Required metadata fields"; the gate and tests now cover all ten, including Publisher, Series, Series Volume, Release Year and a real M4B-compatible project cover. No field has been downgraded to optional.

## Step 5.1 narrator acceptance test isolation

The packaged acceptance fixture names the deterministic built-in narrator profile `Offline Character • Anime Hero` without importing the heavyweight TTS provider module into the harness interpreter. The frozen application still performs real catalogue resolution and persistence through `voice.select`; an unknown or unavailable profile will fail the packaged test.


## Step 5.2 implementation status

Source audit and implementation checkpoint: branch stage-5/step-1-production-metadata; baseline commit d8e52ea894282c282c0785da867585d246ee4470. The implementation commit and matching GitHub Actions result will be appended to the execution ledger after this checkpoint is pushed and verified.

- 5.2.1 source audit: COMPLETE.
- 5.2.2 real idle/generating state: CODE CHANGED — NOT VERIFIED.
- 5.2.3 independent preview/full job state: CODE CHANGED — NOT VERIFIED.
- 5.2.4 preview duration controls: existing real duration pipeline preserved; exact-commit verification pending.
- 5.2.5 preview playback and cancellation: CODE CHANGED — NOT VERIFIED.
- 5.2.6 actual progress, elapsed time, ETA and failure handling: CODE CHANGED — NOT VERIFIED.
- 5.2.7 matching-head regression and packaged Windows acceptance: PENDING.

Do not mark PROD-05/06/07 AUTOMATED TESTS PASSED until the exact implementation commit's regression workflow completes successfully. Do not mark runtime acceptance complete from CI alone.



## Step 5.2.2 clarification

The Generation Engine must show Idle rather than 0% when no job exists. A percentage is displayed only when it comes from an actual job or a verified completed output. The chapter-preview monitor shows the selected chapter number/title from the backend job record; it must not infer a chapter from a static UI label. Failed full-generation status displays the backend error message.

Run #2106 passed the consolidated regression suite on commit 97a4d3094dac80827bfc8ce1f0df0b12141d46e6 (1,082 tests, frontend syntax and native Qt lifecycle). The current follow-up includes additional idle/chapter status assertions and remains pending its own exact-head artifact checkpoint.



## Step 5.2 packaged checkpoint #2107

Run #2107 on commit `6ef7dea5c028ba477d86511b353ad03583dfe44b` passed 1,083 regression tests, frontend syntax, native Qt lifecycle, frozen app verification, bundled voice asset/critical-module checks, packaged Sound Design/Music Library acceptance, installer creation, hashes, and Defender scan. Installer, portable app and SHA-256 manifest uploaded; publication was skipped by workflow policy.

The follow-up gives Production Preview its own Save command, checking completed job, project, chapter and generated WAV identity. Voice Studio retains its existing save route. Additional tests guard the persisted pronunciation and Sound Design settings used by preview/full generation. The follow-up is pending exact-head tests and another Windows packaged checkpoint. Installed-app real audio acceptance remains separate.
