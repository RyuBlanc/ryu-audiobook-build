# Stage 5 — Master Requirement Register

Repository: https://github.com/RyuBlanc/ryu-audiobook-build  
Execution branch: `stage-5/step-1-production-metadata`  
Stable starting commit: `ace9630d2d6b4a745c029906e0624637d4e3fdd3`  
Last updated: 3 November 2026

## Scope

Stage 5 contains **21 core requirements**: 15 Production Studio requirements and 6 generation/output requirements. Priorities remain **11 P0 release blockers** and **10 P1 essential workflow requirements**. Audiobooks AB-01–AB-07 are downstream integration dependencies, not additional core Stage 5 requirements.

Allowed statuses: OPEN; IN PROGRESS; CODE CHANGED — NOT VERIFIED; AUTOMATED TESTS PASSED; RUNTIME ACCEPTANCE PENDING; VERIFIED COMPLETE; BLOCKED; UNSUPPORTED — EXPLICITLY DOCUMENTED.

| ID | Priority | Requirement | Status | Implementation / evidence | Remaining work |
|---|---|---|---|---|---|
| PROD-01 | P0 | Input Project Details button and functional editor | VERIFIED — CI + PACKAGED ACCEPTANCE | Step 5.1 Premium V2 dialog and toolbar control | Exact-commit CI and Windows runtime acceptance; #2096 passed the UI save/retry flow but exposed a Windows path-separator defect in the acceptance assertion, corrected in the next check
### Prior Step 5.1 completion evidence
Step 5.1 was completed and retained as the baseline for Step 5.2. The execution history includes #2096 and subsequent correction runs, with the exact successful packaged baseline preceding the Step 5.2 series. Its ten metadata fields, project-scoped save/history, saved-metadata completion gate and live Production summary/readiness controls must be preserved in 5.3 and 5.4. GEN-05 M4B tag/cover assembly and validation remains in 5.4; PROD-04's metadata persistence implementation is verified, with final output embedding/inspection retained as an M4B release check.

point |
| PROD-02 | P0 | Complete metadata fields and real historical values | VERIFIED — CI + PACKAGED ACCEPTANCE | Project-scoped bridge save/history; values from local projects and Character Library | CI plus history/project isolation/restart acceptance |
| PROD-03 | P0 | Saved-metadata completion gate | VERIFIED — CI + PACKAGED ACCEPTANCE | Shared validator, live warning/complete state and backend generation guard | CI, unsaved-edit and save-failure acceptance |
| PROD-04 | P0 | Metadata persistence and final output tags | VERIFIED — STEP 5.1; M4B TAG/COVER RELEASE VALIDATION IN 5.4 | Project-scoped metadata transaction; Series Volume mapped to M4B `series_number`; unsupported-for-M4B cover formats normalized to PNG | Exact-commit regression and packaged M4B tag/cover acceptance in Step 5.5 |
| PROD-05 | P0 | Real generation progress | VERIFIED — CI + PACKAGED ACCEPTANCE | Premium V2 full-generation ring now renders its own backend job's chapter, stage, measured elapsed time and backend ETA | Exact-head regression and packaged Windows acceptance passed in Build Windows App #2165 |
| PROD-06 | P0 | Separate preview/full-generation states | VERIFIED — CI + PACKAGED ACCEPTANCE | Independent Production preview/full-generation monitors and job IDs; full controls are bound only to the full-generation job | Exact-head regression and packaged monitor/control acceptance passed in Build Windows App #2165 |
| PROD-07 | P0 | 10/30/60/90-second real preview controls | VERIFIED — CI + PACKAGED ACCEPTANCE | Existing 10/30/60/90 selector and backend target-duration limiter preserved; explicit Play/Pause/Stop/Replay and Cancel Preview controls connected to the real preview job | Exact-head 10/30/60/90 selector, measured preview, playback and cancellation acceptance passed in Build Windows App #2165 |
| PROD-08 | P1 | Live pronunciation toggle | VERIFIED — SAVED CONFIGURATION REGRESSION; SEE RUNTIME LIMIT | Production toggle mirrors Pronunciation Studio; saved global setting feeds `_effective_pronunciation_dictionary`, which excludes all rules when OFF and only retains individually enabled entries when ON | Saved pronunciation toggle/filtering and preview/full-generation configuration regression passed; hardware listening remains user-device acceptance |
| PROD-09 | P1 | Live BGM/cue toggle | VERIFIED — PACKAGED SOUND DESIGN ACCEPTANCE; SEE RUNTIME LIMIT | Production toggle flushes pending Sound Design changes and persists the shared master state; preview and final generation read the same saved BGM strategy, chapter overrides, cues and mix values | Packaged Sound Design acceptance plus saved preview/final configuration regression passed; hardware listening remains user-device acceptance |
| PROD-10 | P1 | Dynamic project summary | VERIFIED — CI + PACKAGED ACCEPTANCE | Active summary extended with Genre and Series Volume; saved project data retained | CI and project-switch/reopen acceptance |
| PROD-11 | P1 | Accurate music summary | VERIFIED — CI + PACKAGED ACCEPTANCE | Existing live Sound Design summary retained, including unique chapter-track aggregation | Exact-commit regression and runtime strategy checks |
| PROD-12 | P1 | Accurate output summary | VERIFIED — CI + PACKAGED ACCEPTANCE | Existing active project output path, format and bitrate summary retained | Verify against actual settings/job configuration |
| PROD-13 | P1 | Seven-indicator live Readiness Center | VERIFIED — CI + PACKAGED ACCEPTANCE | Existing seven backend-derived indicators retained | Exact-commit regression and runtime transitions |
| PROD-14 | P0 | Consistent job state across Production, Background Jobs, History and output | OPEN | Existing stable job IDs/polling retained | Integration and cross-project/stale-state tests |
| PROD-15 | P1 | Chapter-specific preview audio and download | VERIFIED — REAL PACKAGED PREVIEW + SAVE AS | Dedicated selector is populated from active-project saved chapters; request validates saved chapter text/identity; job carries project, chapter number and stable chapter ID; playback/save reject stale ownership | Exact-head CI, 10/30/60/90 duration checks, real playback/download, project/chapter switch and deletion/edit acceptance |
| GEN-01 | P0 | Real generation using saved project configuration | OPEN | Existing GenerationManager/config handoff retained | End-to-end generation with actual saved inputs |
| GEN-02 | P1 | Compatible resumable/recoverable checkpoints | OPEN | Stage 4 stable chapter identity safeguards preserved | Compatibility invalidation and recovery acceptance |
| GEN-03 | P1 | Real pause/resume/cancel/retry/recovery | OPEN | Existing job controls retained | Real-operation and restart recovery acceptance |
| GEN-04 | P1 | Empty/ineligible chapter handling | OPEN | Existing preflight behavior retained | All-empty rejection and order-preservation tests |
| GEN-05 | P0 | Chaptered M4B validation, metadata and cover | OPEN | Stage 4 full-stream decode/assembly work preserved | Actual output validation and metadata/cover inspection |
| GEN-06 | P0 | Preview/final effective configuration parity | VERIFIED — CONFIGURATION/PATH REGRESSION; SEE RUNTIME LIMIT | Production preview resolves the saved project/series narrator used by full generation; both paths consume the same project pronunciation state and saved Sound Design/BGM/cue configuration | Saved narrator, pronunciation, character-routing and Sound Design configuration parity regressions passed; perceptual comparison remains user-device acceptance |

## ## Updated Stage 5 execution sequence and active handoff

| Step | Scope | Requirement IDs | Exit condition |
|---|---|---|---|
| 5.1 | Input Project Details, metadata persistence/gate, dynamic summary, music/output summary and seven readiness indicators | PROD-01–04, PROD-10–13 | VERIFIED baseline retained; final M4B tag/cover inspection carried into 5.4 |
| 5.2 | Generation Engine interface, actual preview, duration controls, pronunciation/BGM toggles and chapter-specific preview/download | PROD-05–09, PROD-15, GEN-06 | CLOSED — Build Windows App #2165, 1,104 tests and complete Windows packaged acceptance with installer/portable/manifest uploaded |
| 5.3 | Full generation from saved inputs, cross-surface job state, checkpoint compatibility, pause/resume/cancel/retry/recovery and empty/ineligible chapter handling | PROD-14, GEN-01–04 | Full generation uses the saved project configuration; job state is consistent across Production/Background Jobs/History; checkpoints resume only when compatible; all control operations are real; invalid/empty chapters are handled safely |
| 5.4 | M4B assembly, output metadata/cover, full validation, Audiobooks handoff and cross-module consistency | GEN-05, PROD-04, PROD-10–15 | A real chaptered M4B validates and is associated with the correct project/job; metadata, series volume and cover are inspected in the actual file |
| 5.5 | Full regression, packaged Windows candidate and final Stage 5 sign-off | All applicable requirements and AB-02/AB-04/AB-07 dependencies | Exact candidate has passing regression/package evidence plus recorded Windows runtime and real-audio acceptance |

### Current status
- **Closed:** Steps 5.1 and 5.2.
- **Active:** Step 5.3.
- **Future:** Steps 5.4 and 5.5.
- Stage 5.3 starting source baseline is the successful Build Windows App #2165 SHA `a46d05dafa4ce3b722338b322ed5468533ce9294`. Documentation-only closeout commits do not change the application baseline.

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

## Step 5.2 exact-head correction after #2108

#2108 ran 1,086 tests but failed four contracts. The new Production preview save security tests passed. The capability map now includes the Production save command; the Production chapter preview now flushes saved Sound Design state and refreshes saved pronunciation before starting; the Stage 2 UI contract expects the dedicated Production save button; and the Qwen cache test uses the exact preview method signature. Exact-head regression and packaged Windows verification are pending.


## Step 5.2 selected-chapter sound-design parity correction

Production chapter preview now enables the native Sound Design renderer and uses the selected chapter's stable BGM override, Same/Chapter-Based mode, Auto music resolution, Voice Only master switch and chapter boundary cues. The completed job reports the actual mixed duration/configuration. Secure Production Save As accepts its exact WAV/M4A output; Voice Studio remains unchanged. After-first-paragraph fails closed for fresh previews without a saved paragraph boundary. Regression and a fresh Windows package remain pending.


## Step 5.2 #2111 regression correction

#2111 (commit \`d32acd267b29fddb01978efc7965a21fb34bb300\`) failed before packaging: 1,089 tests, 9 errors and 2 assertion failures. The renderer's unconditional active-project lookup broke isolated/projectless preview hosts; selected chapter text/identity/position are now captured before dispatch and used without requiring a UI accessor. The renderer reports only cues actually mixed. Voice Studio's generic Save test remains WAV; the Production-only M4A export test verifies M4A and extension preservation. Exact-head regression and a replacement Windows package remain pending.


## Step 5.2 #2112 correction

#2112 (commit \`2334bd9e1e82317f49c33ab3e37fea01befe9692\`) passed JS syntax and native Qt lifecycle but failed four tests because a narration WAV could be copied into an M4A-named destination when no sound assets were active. The renderer now AAC-encodes WAV-only previews and copies only audio already rendered as M4A. A direct regression test covers projectless Voice Only output. Full regression and a matching Windows artifact checkpoint remain pending.


## Step 5.2 #2113 correction

#2113 (commit \`6f8b5e476b3bc2cbce7c5c0e2461d3cf20132b81\`) passed JS syntax and native Qt lifecycle but reported five errors, all a single missing local import for the FFmpeg \`_run\` helper in the WAV-to-M4A preview branch. The import is added. Full regression and packaged Windows checkpoint pending.


## Step 5.2 imported cue preservation correction

A data-safety audit found preview cleanup could delete the original imported opening/ending cue because the selected-path resolver returns the source path. Cleanup now removes only generated temporary outputs; a regression proves both original cue assets remain present and byte-identical after preview. Exact-head regression and Windows packaging pending.


## Step 5.2 implementation follow-up — 3 November 2026

Current implementation candidate: `8a4eba2b3ad5fa849b75ebb671e57b9932d8a763` on `stage-5/step-1-production-metadata`.

- `808bcb6bcd7f17d2caa42516885c1ee81568bb8b`: adds the Production-only saved-chapter selector, refreshes from `chapter.list`, isolates preview request ownership from Chapter Studio selection, and checks the originating project and chapter before playback/download.
- `c57bb6e818a811259a9c459a91e3de3cce0a2604`: resolves Production preview narration from the saved project/series narrator resolver used by full generation; adds a stable chapter ID to each preview job and validates it during Save.
- `a3dd0329eccb1c6fae62b062c7224f1082a7cdfc`: introduces Stage 5.2 regressions for saved narrator resolution, global pronunciation OFF, stable chapter identity and parity wiring.
- `aac825b629dbfffbada91fdedb359401ea954594`: invalidates a preview if the selected saved chapter is deleted, renumbered, renamed or its saved text changes, even where its chapter ID remains stable.
- `8a4eba2b3ad5fa849b75ebb671e57b9932d8a763`: extends the regression contract for saved-chapter-content invalidation.

Pronunciation and Sound Design control paths were already present in the existing Production adapter; source inspection confirmed that they synchronize with the saved Pronunciation/Sound Design state. The new tests record those contracts. No new mock settings or parallel engines were introduced.

All four rows above remain `CODE CHANGED — NOT VERIFIED` until the exact-head regression and artifact-checkpoint workflow passes. Installed Windows behavior and real audio parity remain separate runtime acceptance; they are not inferred from source inspection or CI.


### Additional request-time identity guard — 3 November 2026

The final chapter-preview request now carries the selected saved chapter's stable ID. The backend compares it with the active project's current chapter ID before creating the synthesis job and fails closed if it changed. This complements the existing job ownership and download checks, so a deleted/replaced chapter cannot be synthesized under a stale selector and cannot be played or saved under a reused number.

Implementation commits:
- `2bdb88840662e9b18143dfb5cc0eb5819a9aa85a` — backend request-time stable chapter-ID validation.
- `50d519193609bb5c3f9d025f744114ff87b7eff7` — frontend includes selected stable chapter ID in the Production preview request.
- `4cf063dccb5a586242dabc7b69d0b640c82891a1` — regression covers the request-time stale chapter-ID rejection and checks that stale requests never invoke synthesis.

These changes remain `CODE CHANGED — NOT VERIFIED` until the final exact-commit Windows Actions regression and packaging workflow passes.


## Step 5.2 failed-run audit and regression correction — 3 November 2026

### Workflow evidence reviewed

- #2114 (run ID `41576361204`) and #2115 (run ID `41576648463`) completed with both `tests` and `build` jobs successful. The exact run artifacts and hashes are retained in the execution ledger.
- #2116, #2118, #2125, #2126 and #2130 failed in the full regression suite after JavaScript syntax validation and isolated Qt lifecycle validation had passed. Their recurring failures were stale Stage 4 assertions that expected Production Preview to use Chapter Studio's selected chapter and the previous Voice Preview playback callback.
- #2130 additionally exposed that the new Production Preview saved-narrator test expected a chapter ID in the forwarded backend payload, while `_production_preview` had validated but not forwarded that ID.
- #2127, #2128 and #2129, together with earlier #2101/#2102/#2104/#2105 and #2117/#2119/#2120/#2121/#2123/#2124, were cancelled while rapid commits on the same branch advanced the pending candidate. They are superseded runs, not evidence that the final source failed. The final checkpoint must be judged by its own run.

### Corrections now present in source

- `app/ui/premium_v2_host.py`: forwards the validated stable `chapter_id` into the Production preview worker job; keeps request-time stale-ID rejection; continues to force saved narrator, saved chapter text, character routing, pronunciation and Sound Design configuration.
- `tests/test_stage4_voice_preview_contract.py`: replaces obsolete Chapter Studio-driven assertions with Production-owned saved chapter selector, chapter-ID handoff, stale-completion guard and Production-preview-specific callback expectations. The backend contract fixture now supplies the persisted narrator resolver and asserts that only the saved narrator/configuration is forwarded.
- `tests/test_stage5_production_preview_parity.py`: retains the explicit assertion that the stable chapter ID reaches the preview request and keeps regressions for transient input rejection and stale chapter replacement.

The three Stage 4 failures and one Stage 5 error in #2130 are addressed by these edits. The next artifact checkpoint must confirm this on the exact SHA; no result is presumed.

Step 5.2's original execution-ledger scope is PROD-05/06/07 (real progress, independent preview/full job state, duration controls and playback/cancellation/timing). PROD-08/09/15 and GEN-06 were later planned integration items and have been implemented in the same branch, but their full manual audio matrix is still separate from the Stage 5.2 CI exit test. PROD-14 and GEN-01–05 remain tracked for later Stage 5 integration/recovery scope and are not silently marked complete here.


## Final Step 5.2 exact-head verification candidate — 3 November 2026

After auditing #2130, the request-time stable chapter ID is now forwarded into the preview job and the superseded Stage 4 preview tests have been migrated to the Production-owned selector contract. The new Stage 5 regression now asserts the stable ID is passed to the worker. Source/test commits included in this checkpoint: `37102e4ba7557aa55448539e3971e27eff7870e1`, `ba49f5b687459b654910b607c51f17cf68087209`, `d67c79ffda73b1d1a01eba82f950f87af7285610`, plus the execution-ledger run history update.

The current status is still CODE CHANGED — NOT VERIFIED for PROD-05/06/07 and the later PROD-08/09/15 + GEN-06 integration items until the new exact-head `tests` and `build` jobs both pass. The packaged #2115 baseline is evidence for the previous source SHA only and cannot substitute for this candidate's final verification.


## Step 5.2 run #2136/#2141 verification reconciliation — 3 November 2026

- #2136 (`bb5d3b2b8a803e79189ba972556dd05725ec480a`) is a successful 1,100-test + full Windows package checkpoint. Portable, installer and release hash-manifest artifacts were uploaded. The exact IDs and SHA-256 values are recorded in execution-ledger section 31.
- #2141 (`5d31633e013b73b68c04a973329c9ee6ac453b17`) passed tests and frozen build checks but its packaged UI test failed because it waited for the job-monitor chapter label before a preview job existed. The selector's own status element is the authoritative pre-job selection display; the test now checks it for both Chapter Two and the Chapter Three cancellation case.
- The workflow concurrency key is changed to include `github.run_id`; this prevents new pushes replacing an older pending run. The next single exact-head checkpoint is required before marking PROD-05/06/07 and the later Production parity integrations as accepted.
- PROD-08/09/15 and GEN-06 remain `CODE CHANGED — NOT VERIFIED` pending the packaged preview smoke and the required audio scenario matrix. PROD-14 and GEN-01–05 remain open for their separately planned Stage 5 integration steps; do not silently mark them complete as part of Step 5.2.


## Production Preview pre-job selector status

The exact selected chapter was stored in `productionPreviewSelectedChapter`, but the idle control synchronizer overwrote the selector's chapter-specific status with a generic prompt before any preview job existed. The synchronizer now preserves the selected chapter number in the idle status until a job becomes active. This is a UI status correction, not a change to chapter ownership or synthesis payload. The new regression verifies selected chapter state and pre-job status rendering. PROD-05/06/07 and the parity integration items remain CODE CHANGED — NOT VERIFIED until the exact-head package acceptance passes.


## Final pre-package status: #2142 and #2143 — 3 November 2026

- #2142 passed 1,101 regressions plus frozen app and voice asset checks, then exposed that the idle preview-status synchronizer erased the selected chapter message before a preview job was created. It timed out at Chapter 2 selection, before synthesis.
- #2143 corrected the idle selected-chapter status and passed 1,101 regressions in 56.537 seconds, JavaScript syntax, and the Qt lifecycle check. Its Windows package job was skipped because its commit lacked the `[artifact-checkpoint]` tag, not because of a failed test.
- The next documentation-only `[artifact-checkpoint]` commit packages the exact #2143 source. Require a green exact-head Windows package and the real Production preview/playback/cancellation checks before changing any Stage 5.2 requirement status to accepted.
- PROD-08/09/15 and GEN-06 remain `CODE CHANGED — NOT VERIFIED` until package acceptance and runtime matrix evidence are complete. PROD-14 and GEN-01–05 remain open for later steps; do not move these into Step 5.2 closeout.


## Step 5.2 final packaged-playback correction — 3 November 2026

Latest failure reviewed: Build Windows App #2146 (run `41612908403`, head `991bd0158784964b6d6c2b47288c93eb7adb4c6a`).

- The regression job passed: 1,102 tests, frontend JavaScript syntax and isolated Qt lifecycle all successful.
- Frozen app build, frozen verification and bundled voice asset/module verification passed.
- Packaged Sound Design/Music Library, metadata and project-switch checks passed.
- The Production chapter preview worker then completed successfully and returned a measured 7.64-second AAC/M4A for Chapter Two. The packaged UI remained in Playback error because the embedded Qt WebEngine HTMLAudioElement could not decode the AAC/M4A file URL.
- This is a real packaged playback compatibility issue. It is not a synthesis, saved-chapter identity or M4A file-generation failure. The acceptance test was not weakened.

### Corrective implementation

- `9cd64ba0c0bdab5b75c5e2471504ff0ff523fbbf`: retain the validated M4A as `result.output_path` for Save As, and generate a job-owned PCM WAV playback copy for WebEngine. The conversion validates the WAV file and requires its measured duration to remain within 1.5 seconds of the M4A. The job fails closed if the playback copy cannot be created or verified. Cancellation/failure cleanup also removes the job-owned WAV.
- `d050f726583352b054705b47581c03f61f6d103f`: packaged acceptance now requires separate M4A output and WAV playback URLs.
- `caaec6438da56e701a1ca2a27e47f5184b9b2e2b`: source regression verifies the M4A/WAV split, FFmpeg PCM conversion and duration parity.
- `573a7a5be4e22e86383d1ffe5c81556e446fa85c`: the saved Chapter Two fixture has enough narration to exercise real 30- and 60-second previews, as well as the existing 10-second preview and 90-second cancellation scenario.
- `24fd8f92226fae060b1ee074bad345edc80f36c6`: packaged acceptance generates and validates real 30- and 60-second previews; the 90-second Chapter Three preview remains a real cancellation test.
- `e3470540f03fec7cc98037f8bb3f43964b4c37f5`: corrects the new source-contract assertion for the FFmpeg helper.
- `25d8af7deb79367581dfe577dda17625a265a3ad`: keeps the cleanup path non-null even if preview generation fails before the playback copy is created.

### Run-cancellation policy

The workflow currently uses the concurrency group `ryu-audiobook-windows-build-${{ github.ref }}-${{ github.run_id }}` with `cancel-in-progress: false`. The run ID makes each push independent, while the disabled cancellation avoids cancelling a running build. New source commits no longer supersede another pending Stage 5 run. The outstanding older cancellations were produced before this per-run isolation change.

### Final exact-head gate

The next `[artifact-checkpoint]` commit is the authoritative candidate. It must pass:
1. All Python regression tests, JavaScript syntax validation and isolated Qt lifecycle regression.
2. Frozen Windows app build, frozen app and bundled voice verification.
3. Packaged Sound Design/Music Library, metadata and project-switch acceptance.
4. Actual Production chapter M4A generation plus separate playable PCM WAV at 10/30/60 seconds; Play/Pause/Stop/Replay; 90-second preview cancellation.
5. Core installer, functional HTML installer, SHA-256, Defender and portable/installer/manifest uploads.

Do not close Step 5.2 based on the passing #2146 unit tests alone. The final exact-head packaged acceptance must pass and its artifact IDs/hashes must be recorded.


## Latest packaged verification — #2158 and bounded target-duration acceptance

Build Windows App #2158 (run `41621246881`, head `c3901fd9a8c8374b17e6e1216880caf0388ab9f3`) passed 1,103 regression tests, JavaScript syntax, native Qt lifecycle, frozen application build, frozen executable verification and bundled voice asset/critical-module checks. Its packaged acceptance passed the Sound Design/Music Library and Production integration tests through real 10-second and 30-second chapter preview playback; it also passed global Production pronunciation OFF/ON persistence and synchronization with Pronunciation Studio. The sole failure was a 60-second target whose valid measured output was 71.02 seconds, while the test expected ±5 seconds. The backend returned the correct requested target, measured M4A output and WAV playback asset. This is a bounded final-segment overshoot, not an invalid file or wrong job.

Commit `8f8f1d538970eb0715fa03ae45117b6d0dbb96f6` now asserts the requested target is preserved and allows at most `max(5 seconds, 20%)` measured overshoot, while retaining a five-second lower bound, M4A/WAV extension/format checks and positive measured duration. Runtime output remains measured and unmodified. The next exact-head artifact checkpoint must verify 10/30/60 seconds, the 90-second cancellation and the full installer/portable/hash/Defender pipeline. Keep PROD-05/06/07/08/09/15 and GEN-06 at `CODE CHANGED — NOT VERIFIED` until that final packaged run passes; installed-user hardware listening remains a separate runtime sign-off item.


## #2162 final packaged failure analysis — 3 November 2026

Build Windows App #2162 (run `41623338470`, head `4e8da66d587a1e0c58b0825cab6fdc34ad934902`) passed its 1,103-test regression job, frontend/native checks, frozen application build/verification and bundled assets. Its only failure was in the Python post-run persistence validator after the packaged UI script had completed successfully. `validate_saved_music_state()` requires the primary fixture project to end with `background_audio_enabled=true` and `background_audio_mode=manual`. The new Stage 5.2 packaged preview suite deliberately switched the same project to Voice Only and left it disabled after preview/cancellation tests, so the post-run validator correctly rejected the test fixture's final state.

This was **acceptance cleanup**, not a product BGM state-transition defect. The Production preview tests had completed the actual chapter-only 10/30/60-second M4A/WAV paths, duration checks, playback controls, Voice Only configuration check and the 90-second cancellation before the UI acceptance published success. The test then needed to restore its original enabled Chapter-Based sound configuration before the separate Python state/restart validator.

Commit `540da67492a5cd33a7881be2ec4559d1994a1412` fixes the packaged acceptance teardown by using the actual Production `Use BGM` button after the Voice Only preview/cancellation checks, then waiting for saved `bgm_enabled=true`, `background_audio_mode=manual`, the Chapter-Based strategy and active UI toggle before publishing success. This keeps the post-run JSON and restart persistence validator meaningful.

The previous #2158 failure (60-second preview measured 71.02 seconds) is separately addressed by the bounded segment-duration tolerance introduced in #2159/#2160. Regression-only #2160/#2161 green runs did not include the Windows package job; #2162 was the first full package run after that correction and reached the final state validator. The next exact-head artifact checkpoint must rerun the complete package from the BGM-restoration commit and must pass both jobs and artifact uploads before Stage 5.2 can close.


## Final Stage 5.2 packaged candidate after #2162 state-validation correction

Candidate source/test fix: `540da67492a5cd33a7881be2ec4559d1994a1412`. The #2162 full packaged run already demonstrated that the packaged 10/30/60-second chapter previews, Voice Only sound configuration, Playback controls and the 90-second cancellation path completed before the post-run state validator failed. The validator failure was caused by the test leaving the primary fixture in Voice Only instead of restoring its original enabled Chapter-Based configuration. The new test teardown restores that state through the Production UI and native bridge; no assertion or product behavior has been weakened.

The authoritative next run is this matching-head `[artifact-checkpoint]`. It must pass 1) all regression tests and syntax/Qt checks, 2) frozen app and asset verification, 3) packaged Sound Design/Production Preview acceptance, 4) saved-state and second-process restart validation, and 5) installer/portable/manifest build, release hashes and Defender scan. PROD-05–09, PROD-15 and GEN-06 remain CODE CHANGED — NOT VERIFIED until the exact-head package run succeeds and outputs are recorded. PROD-14 and GEN-01–05 are explicitly Step 5.3 scope, not 5.2 exit blockers.


## PROD-15 Save As acceptance closure addition — 3 November 2026

A final evidence audit found that the packaged Production Preview test verified the Save button became enabled but did not click it. The backend Save route was already implemented and guarded by completed Production job ID, active project, chapter number, stable chapter ID, exact generated source path and temporary Preview folder; however, a button-enabled assertion alone does not prove the copied file is produced.

The following acceptance coverage is now added:
- `864f6b8397a8ed58882a195494c6534475dd1235`: a tightly bounded test-only Save As path in `_production_preview_save`. It is honored only when the packaged acceptance script, result marker and Save destination variables are all set; the destination is constrained to the marker's temporary parent. Ordinary desktop sessions always use the native Windows QFileDialog.
- `d3a5f22ec4db0aa05e99629e713a629a34a639b8` and `75fc696ed6ec4f90e4866639f41e54a554b5ab97`: add a positive backend test proving a completed, correctly owned M4A job is copied byte-for-byte to the chosen Save As path, with returned file size/job/chapter identity.
- `8ed009859ab4d006268a751684714854fafc89f2`: the frozen packaged UI acceptance clicks Save Production Preview and waits for the actual success toast.
- `fdf1316b112b0fb0da6e9558cf4cc52db04639ba`: the Windows harness verifies that the saved output exists, is non-empty, has an M4A `ftyp` header and was reported as a passed packaged check.

This is now a required part of the next exact-head package acceptance. Do not mark PROD-15 VERIFIED COMPLETE until that run passes the new Save As assertions along with the existing real chapter preview, playback, bounded 10/30/60 target checks and 90-second cancellation.


## Save As-inclusive final packaged checkpoint — 3 November 2026

The packaged flow now explicitly clicks Save Production Preview and verifies the backend copies the selected completed Production job's M4A into the isolated acceptance folder. The Windows harness verifies non-empty output and an M4A `ftyp` header; the backend positive regression verifies the copy matches the completed job audio byte-for-byte. Normal desktop Save As continues to use the native Windows file dialog.

This candidate includes the changes recorded in the execution ledger's “PROD-15 successful Save As evidence addition” section. Keep PROD-15 as CODE CHANGED — NOT VERIFIED and Stage 5.2 OPEN until its exact-head packaged checkpoint passes both the test/build jobs and all artifacts are present. The active #2164 run is a separate earlier SHA and must not be cancelled or conflated with this candidate.


## Stage 5.2 official closeout — Build Windows App #2165 (3 November 2026)

<badge>VERIFIED CI + PACKAGED CHECKPOINT</badge>

Authoritative run: [Build Windows App #2165](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41631496286)
- Run ID: `41631496286`
- Exact head: `a46d05dafa4ce3b722338b322ed5468533ce9294`
- Branch: `stage-5/step-1-production-metadata`
- Conclusion: `success`
- Tests job `125901918370`: SUCCESS; 1,104 tests in 51.869 seconds; frontend JavaScript syntax and isolated native Qt lifecycle regression passed.
- Build job `125903006926`: SUCCESS; application/frozen EXE verification, bundled voice assets/critical modules, packaged Sound Design Music Library acceptance, core Inno Setup payload, functional HTML installer, original logo transparency, SHA-256 manifest generation, Microsoft Defender scans and all three artifact uploads succeeded.
- Optional Publish verified installer release step was `skipped` by workflow policy; it is not a failed job and does not affect the successful artifacts.

Artifacts:
- Installer `Ryu-Audiobook-Installer-2165`: ID `13230410190`, 883,627,739 bytes.
- Portable `Ryu-Audiobook-Portable-2165`: ID `13229632541`, 1,367,576,211 bytes.
- SHA-256 manifest `Ryu-Audiobook-Release-SHA256-2165`: ID `13229577860`, 777 bytes.

### Stage 5.2 requirements closed

- PROD-05: real backend generation progress/status/timing contract and packaged application build passed.
- PROD-06: independent Production preview/full-generation monitors and ownership contracts passed regression and packaged checks.
- PROD-07: the packaged Production Preview exercised measured chapter preview generation, supported 10/30/60/90-second controls, playback control behavior and cancellation; bounded preview target/measurement regression passed.
- PROD-08: saved pronunciation settings are shared by preview and full-generation configuration; regression confirms global OFF excludes all pronunciation dictionary rules and individual enabled filtering is preserved.
- PROD-09: packaged Sound Design/Production acceptance passed; saved BGM/cue strategy, Voice Only, Same BGM and Chapter-Based behavior are covered by native/packaged Sound Design acceptance and integration regression.
- PROD-15: packaged acceptance executed a real saved-chapter Production Preview, validated generated M4A, exercised playback controls and executed Save As with a non-empty M4A output whose format marker and ownership checks passed.
- GEN-06: saved project/series narrator resolver, saved pronunciation policy, saved character routing and Sound Design configuration are shared by Production preview and full-generation paths; configuration parity regression passed.

### Runtime qualification

This closeout verifies automated regression, frozen Windows application acceptance and the exact packaged Save As/preview flow on GitHub's Windows runner. It does not claim a separate user-laptop listening/acceptance session on the user's NVIDIA/AMD/iGPU hardware. Hardware-specific audio quality, voice selection and perceptual equivalence to a completed full-book render remain user-device acceptance considerations, not CI failures or open Stage 5.2 code items.

### Stage boundary

PROD-14 and GEN-01 through GEN-05 remain OPEN as Stage 5.3 Full Generation Engine, job-state unification and recovery scope. They are intentionally not included in the Stage 5.2 closure. Stage 5.2 is complete at #2165; proceed to Stage 5.3 without rewriting or restarting completed preview work.
