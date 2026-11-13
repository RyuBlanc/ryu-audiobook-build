| DS-CAST-008 | Narrator / character assignment | Narrator-only mode, saved narrator identity, character-cast routing and Unassigned Character handling must agree across readiness, preview and final generation. | Existing behaviour; regression risk | Hosted Qwen Base/VoiceDesign and CastAwareProvider smoke produced the assigned two-chapter character-dialogue M4B with two Qwen dialogue calls; saved multilingual profiles also retained the same canonical identity anchor after reload. **Still open:** validate narrator-only default-off/no-character fallback, Unassigned Character handling, saved narrator identity and Qwen narrator/character consistency on the installed target PC and a representative book. |

**Tracking branch:** `dragon-studio/1.2.0-post-release-bugfixes`  
**Verified baseline before the A/B continuation push:** PR #35, branch `dragon-studio/1.2.0-post-release-bugfixes`, HEAD `cbb557e8c249d336bb10bc7265e2e75d1257b63c`; Build Windows App #3369 passed 1,543 tests and the Windows package.  
**Purpose:** maintain one durable register for release blockers and old/new regressions found after the 1.2.0 release.

> This branch name establishes the long-lived bug-fix workstream. It does not claim that version 1.2.0 has already shipped or that any unverified bug is fixed. The 1.2.0 release tag and packaged artifact remain the boundary between pre-release blockers and post-release regressions.

## Working rules

1. Keep the completed Stage 1–8 implementation history intact. Do not restart completed stages or replace their accepted work.
2. Every bug gets a stable ID, exact reproduction, affected version/build, root cause, code change, focused regression test, packaged checkpoint and acceptance evidence.
3. A passing unit test does not close a UI, installer, hardware, playback or packaged-EXE defect.
4. Failed workflows remain failed until their actual failure step is understood and a corrected exact-head run passes. Do not call a failed or unavailable run green.
5. Keep fixes grouped by a small related bug set. Do not combine unrelated UI, Qwen, installer and generation changes merely to reduce run count.
6. Record whether a defect is a regression from the 1.2.0 release or an older issue that remains open. Never silently relabel an older issue as newly introduced.
7. Keep the original failed run numbers, commit hashes and logs linked to each repair. Preserve superseded PRs as closed historical records rather than deleting their history.

## Current verification queue

| ID | Area | Reported defect / acceptance | Classification | Current status |
|---|---|---|---|---|
| DS-ETA-001 | Production Studio ETA | Remaining-time estimate increased over time while elapsed time increased normally; screenshots showed 15% progress with remaining estimate moving from 22:28:45 to 22:31:01 over about 23 seconds. | Existing defect; Stage B automated checkpoint; physical acceptance remains open | The measured synthesis-call estimator, warm-up exclusion, rolling median/smoothing, timestamped countdown, native-page parity and pause/resume clock reset are present. Exact previous baseline #3369 passed 1,543 tests and the Windows package. The A/B continuation adds a direct long-pause regression and runs this test module before the full suite. **Still open:** long real multi-chapter Qwen/Piper acceptance on the target PC. Original push runs #3198–#3200 remain individually undiagnosed because their run logs were unavailable. |
| DS-PROG-002 | Production Studio progress | Ring stayed at 15% during long-running synthesis; percentage, active chapter, total workload and validated chunk progress need to be truthful and readable. | Existing defect; Stage B automated checkpoint; physical acceptance remains open | The current contract uses completed normalized text workload (not invented token progress), retains active chapter/segment and validated chunk counts, and keeps narration percentage separate from M4B packaging percentage. The true 1:1 ring and completed-work basis tests passed at #3369; the same exact-head package passed. **Still open:** observe real long-running generation on the target PC to confirm useful movement throughout slow Qwen chunks and chapter transitions. |
| DS-DURATION-003 | Production Studio duration | Show expected audiobook listening length before completion, measured audio duration as chapters complete, and authoritative full M4B duration after validation. | Existing missing capability / accuracy issue; Stage B automated checkpoint | Regression contracts cover the text-based listening estimate, completed-chapter runtime projection, measured chapter audio, final M4B duration validation and separation of narration vs packaging progress. Build #3369 also passed packaged generation/M4B gates. **Still open:** compare all three duration values against a representative full-book target-PC output; estimated listening time must remain explicitly approximate until final M4B measurement. |
| DS-QWEN-004 | Qwen Voice Studio | Saved Qwen profiles and CustomVoice/VoiceDesign/Clone paths must load, preview the selected identity, save and reload consistently, and not fail inside the isolated external runtime. | Older issue; Stage C1 automated acceptance passed, installed-app acceptance remains open | Provider Runtime Smoke #414 passed CPU CustomVoice 0.6B/1.7B, authorized Base Clone, saved VoiceDesign with matching anchor SHA, and Qwen character-to-M4B output. The Stage C1 saved VoiceDesign audition and series-scoped identity/assignment corrections passed focused tests and the exact-head Windows package in #3380 (1,554 full regression tests). **Still open:** installed-app target-PC audition and save/reload/production identity verification across all modes. |
| DS-QWEN-005 | Qwen performance / hardware | 30-second preview target is under 60 seconds on supported NVIDIA hardware; CPU/AMD/Intel performance and backend reporting must be accurate and evidence-backed. | Older unmet performance goal | Provider #414 recorded a real hosted CPU VoiceDesign preview of 30.000s audio in 372.782s warmed time (cold-start plus warm-up 59.650s). Latest hosted CPU comparison, Qwen CPU contract run #38 / [43400140577](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43400140577), generated exactly 30.000s of saved-profile VoiceDesign audio but took **255.415s**; it explicitly reported `QWEN_VS01_CPU_60S_TARGET=NOT_MET_ON_HOSTED_CPU`. This is CPU-only comparison evidence, not GPU performance. Piper is separate ONNX evidence, not Qwen speed. **Open:** physical NVIDIA CUDA, supported AMD ROCm and Intel XPU acceptance; 30s saved-profile preview under 60s on supported GPU with verified actual inference device and no CPU fallback. |
| DS-QWEN-006 | Qwen Models Center install/repair lifecycle | Install mode-specific model sets, preserve the previous working isolated runtime when repair fails, refuse destructive repair during active synthesis, retain user profiles/anchors/models on uninstall, and reload saved identities after application restart. | Existing lifecycle reliability gap; Stage C2 hosted acceptance complete | Exact-head Build Windows App #3382 / [run 43400140506](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43400140506), commit `05a15fac65305e428752f194b8852884c40c7c5d`, passed focused C2 lifecycle/restart **9/9**, full regression **1,563/1,563**, and all Windows package/installer/Defender/artifact gates. Transactional repair rollback, active-worker protection, interrupted-repair recovery, safe model/runtime removal and fresh-process saved-profile reload are covered. **Still open:** installed target-PC repair/restart, model install/remove, and actual CustomVoice/VoiceDesign/Clone audition-to-generation. No physical GPU claim is implied. |
| DS-JOBS-006 | Generation job lifecycle | Pause, resume, cancel, retry, interruption, durable recovery and history must refer to the correct job and preserve valid chapter checkpoints. | Existing P0 acceptance | Build #3369 passed the packaged restart/recovery acceptance, cross-module job/project/History/output identity, and Task Manager in-place action repair. The new Stage B regression separately protects the paused ETA clock. **Still open:** repeat long real generation and interruption/recovery on the target PC; do not infer physical-device recovery from hosted CI. |
| DS-M4B-007 | Full-book output | Multi-chapter generation must retain all eligible text, produce a valid chaptered M4B, validate duration/metadata and play correctly. | Existing P0 acceptance | Build #3369 passed the packaged real two-chapter Piper M4B generation/decode/chapter-marker path. This is a smoke fixture, not a full-novel acceptance. **Still open:** Qwen Base/VoiceDesign production acceptance and representative full-novel target-PC generation, metadata/cover/final duration, chapter navigation and playback. |
| DS-CAST-008 | Narrator / character assignment | Narrator-only mode, saved narrator identity, character-cast routing and Unassigned Character handling must agree across readiness, preview and final generation. | Existing behaviour; regression risk | Revalidate explicit narrator-only toggle, default-off behaviour, no-character fallback and saved voice identity. |
| DS-UI-009 | Production Studio layout | Organize the Production Studio controls and cards; prevent cover art from being permanently watermarked/embedded into the artwork; use the selected cover as artwork only. | Older user-reported UX defect | Requires source review and packaged visual acceptance at supported sizes. Keep artwork asset and app branding separate. |
| DS-BRAND-010 | Logo / Windows shell | Remove opaque white/black corner backgrounds from the logo where transparency is required; ensure taskbar, shortcut and installed-app icons use the intended transparent brand asset. | Older user-reported release defect | Build #3363 validated source logo transparency/corners, generated icon/installer assets and Windows install/launch/upgrade/uninstall. **Still open:** inspect the actual installed shortcut/taskbar icon on the target PC for opaque white/black corner artefacts. |
| DS-INSTALL-011 | Installer layout | Installer content was cropped at the bottom; Next/Back and details were not fully visible; unwanted black center bar/frame appeared. | Older user-reported release defect | Build #3363 passed HTML/core installer UI startup, install/launch/upgrade/uninstall and Defender checks. **Still open:** visually inspect the actual wizard at the target PC's display scaling/resolution for footer, navigation buttons, details and frame cropping. |
| DS-AI-012 | Multilingual novel analysis | Character/dialogue analysis must handle Japanese, Chinese, Korean and accented Latin text without losing names or quote evidence; English stopwords must not become characters. | Older functional defect / regression risk | Re-run Unicode-aware analysis and source-backed dialogue assignment tests on representative books. |
| DS-RESP-013 | Responsive UI | Verify Generate page and application layouts at 1280×720 and the agreed 41-viewport matrix, including mixed display scaling, ultrawide and portrait layouts. | Existing release acceptance | Build #3369 passed the full regression suite and Windows package after the #3367 and #3368 corrections. The package passed its packaged Sound Design/Production and Windows install/launch/upgrade/uninstall gates. Earlier 41-viewport and emulated scale evidence remains historical acceptance, not a substitute for a final physical target-PC test. **Still open:** physical no-flicker/no-freeze responsiveness, 1280×720 hands-on acceptance, the agreed final-head viewport matrix and mixed-DPI/multi-monitor checks. |
| DS-HELP-014 | Help & Guide | Help and Guide content must describe the shipped features, controls, recovery paths and real limitations accurately. | Existing release acceptance | Review after the release-scope bug fixes so the guide matches the actual packaged build. |


## Stage A reconciliation and Stage B continuation — 13 November 2026

### Active roadmap boundary

The active implementation plan is **A → B → C → D → E → F**. Earlier Stage 1–8 ledgers and closeouts are historical implementation/test evidence only; they are not a roadmap to restart. Preserve their accepted work and only carry forward requirements still marked open by evidence.

### Exact-head baseline reviewed

- PR #35 is open and draft on `dragon-studio/1.2.0-post-release-bugfixes`.
- Baseline HEAD: `cbb557e8c249d336bb10bc7265e2e75d1257b63c`.
- Build Windows App #3369 ([run 43268213294](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43268213294)) passed on that exact HEAD. The tests job ran **1,543 tests; OK**. The Windows package job passed the frozen-app, real two-chapter M4B, packaged Sound Design/Production, installer, install/launch/upgrade/uninstall, logo transparency/hash, package-size and Defender steps.
- Build #3367 ([run 43266926128](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43266926128)) ran 1,543 tests and failed one assertion in `test_global_background_job_heartbeat_is_adaptive_and_keeps_active_progress_fast`: the test expected a literal `BACKEND_JOB_POLL_ACTIVE_MS = 1500` assignment although the implementation exposed a derived adaptive-delay function. The failure was a stale source-contract assertion, not a runtime polling timeout.
- Build #3368 ([run 43267602787](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43267602787)) passed all 1,543 tests, then failed packaged restart acceptance at “Task Manager repairs a mismatched View action in place”. The preceding restart, recovery, playback, music/cue persistence and real M4B markers had passed. Build #3369 on the corrected exact head passed both jobs. #3367 and #3368 remain recorded failures; neither is relabelled as a pass.
- The original #3198–#3200 push failures remain individually undiagnosed; their exact job logs were not available in the connected Actions lookup. Do not claim they were diagnosed from commit subjects.

### Stage B continuation added in the same push

- Keep the production estimator based on actual synthesis-call timing; do not introduce time-based fake percentage or Qwen token progress.
- Add a focused regression for a paused job retaining its measured remainder, clearing its countdown timestamp, and resuming with both wall-clock and monotonic ETA clocks restarted. A 10,000-second pause must not consume the saved estimate; the first 10 seconds of active synthesis after resume should reduce 60 seconds to 50 seconds.
- Add a dedicated focused Stage B test step before the full regression suite. The packaged Windows job remains downstream of a successful tests job.
- The exact-head A/B checkpoint is only accepted when the focused Stage B module, complete regression suite and Windows package all pass on the same pushed SHA.

### Remaining acceptance boundary

The new hosted checkpoint cannot close physical target-PC listening acceptance. A long multi-chapter Qwen/Piper run must still demonstrate live elapsed time, truthful completed-work percentage, active chapter, ETA countdown/revision across pause/resume, projected listening duration and final measured M4B duration. Physical NVIDIA/AMD/Intel hardware checks remain Stage C, not a Stage B claim.

## Workflow failures requiring diagnosis

The current screenshot shows these failed Build Windows App push runs on the former Stage 5 branch:

| Run | Commit | Commit purpose | Status |
|---|---|---|---|
| #3198 | `6466eb6a53d9286db88ffa1aa6eb9a5047012146` | Expose validated synthesis chunk progress in Production Studio | Failed |
| #3199 | `db043b67cefc1a1a447db67b8877324db5b22040` | Verify Production Studio shows validated chunk progress | Failed |
| #3200 | `ea6710d4e5f08193b1f38301c86b44fef103c44d` | Final measured ETA and chunk-progress artifact checkpoint | Failed |

These three runs are not considered diagnosed merely because their commit subjects are known. The exact failing job/step logs must be obtained before choosing a correction. The available connected Actions lookup in the current session cannot resolve these push-triggered runs by run number; #3200 is not the internal Actions run ID.

## Verified test correction — Builds Windows App #3251–#3264

The first correction attempt failed (#3251–#3258) for two independently observed test defects: a case-sensitive lowercase timeout assertion, and a minimal process double missing the stream attributes touched during provider cleanup. The CPU Qwen workflow consequently stopped before real model execution.

The next correction fixed the test assertion, provided a realistic exited-process object, limited cleanup to the diagnostic log handle in these focused tests, and normalized PowerShell path separators in the CPU Qwen log collector.

**Validation evidence:**
- Earlier intermediate PR run [#3261](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43020576268), commit `86f64fa309d754a3104039c25dab5e97e81b76c8`: all 1,498 regression tests passed; package job is not yet complete for the final PR head.
- Current PR run [#3267](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43021199482), exact current PR head `17868d6afe1230f4d1cfb57326f260a4239af8e4`: dependency installation, frontend syntax, native Qt lifecycle, and Stage 6 preflight passed; full regression suite passed (1,498 tests, `OK`). Windows build job `130525480144` is still in `Prepare, validate and build application`; package/install/portable artifacts are not yet available.
- Prior PR #3264 / run `43020594973` on `5bac4b58cd80bbaf5a3e528857fe3acf196fcee0` also passed 1,498 tests, but its package result is not being substituted for the latest-head gate.
- CPU Qwen run [#12](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43020566273), commit `b7006e4cadbb36170909ed384773754f0c722916`: runtime installation, focused 56-test group, and expression protocol smoke passed; real 30-second Qwen 1.7B VoiceDesign CPU preview is still in progress. Worker stderr collection and artifact upload have not executed yet.
- NVIDIA run #13 and AMD/Intel run #20 have not yet supplied verified physical-device results.
- NVIDIA run #13 and AMD/Intel run #20 have not yet supplied verified physical-device results.

The worker log collection step must still be verified after the real preview executes. The real CPU preview and hardware acceptance gates remain open; no Qwen runtime or performance bug is closed by the passing regression suite alone.

## Diagnosed Qwen diagnostic-test regression — Builds Windows App #3245–#3250

Affected head: `b29d9e162a32e149b5e51c16a172e30d46ded4aa`.

Failed runs: [#3245](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43014810959), [#3246](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43014816798), [#3247](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43014817131), [#3248](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43014820763), [#3249](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43014823323), [#3250](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43014829590). Build #3244 / commit `f9457470293cbd0213efd2d558f65b679e504d5a` is the passing predecessor.

The suite ran 1,498 tests and failed with one error in `test_worker_timeout_reports_live_state_and_captured_stderr_log`. The test patched `time.monotonic` with a finite iterable, but `_read_response` performs more clock reads per wait loop than the fixture anticipated. The mock raised `StopIteration` before the timeout assertion. Since the log handle was closed only after that assertion, Windows temporary-directory cleanup then raised a secondary `PermissionError [WinError 32]`.

The correction is limited to deterministic test timing/cleanup, safe closing of the stderr log after its diagnostic tail has been assembled, and robust artifact collection using an explicit `if: always()` PowerShell copy to `qwen-cpu-acceptance/`. It does not increase timeouts, weaken acceptance conditions, or hide the Qwen failure.

## Diagnosed regression-suite failure — Build Windows App #3202

The first pull-request validation on the initial Dragon Studio head (commit `b86ee65`, PR #35) completed installation, JavaScript syntax validation, the isolated Qt lifecycle test and the focused Stage 6 preflight successfully. The full regression suite ran 1,489 tests and failed with **4 failures and 1 error**.

Exact findings from the log:

1. **Error — `test_generation_progress_maps_plan_chunks_and_m4b_stages_monotonically`:** the test double `GenerationProgressDispatchHarness` did not expose the production bridge clock method `_now()`. The final chunk timing callback reached the completed-work branch and raised `AttributeError`. Test harness now delegates `_now` to `PremiumV2Bridge._now`.
2. **Failure — `test_bridge_pause_and_resume_control_real_generation_manager`:** the control-test bridge double also lacked `_now()`. Final-chunk ETA anchoring raised inside the progress callback, so the test observed one completed chapter instead of two. Test harness now exposes the bridge clock.
3. **Failure — `test_bridge_pause_and_resume_at_saved_chunk_boundary_inside_a_chapter`:** same missing clock method in the test bridge double; the final chunk callback aborted before the chapter completion checkpoint. Covered by the same harness repair.
4. **Failure — `test_generation_progress_keeps_narration_and_package_percent_separate`:** this functional test still expected the previous callback-spacing throughput estimator. It now emits measured `chunk-timing` events, excludes warm-up, and expects the new measured median estimate.
5. **Failure — `test_qwen_preview_starts_at_zero_and_progress_is_completed_segment_based`:** a source-contract assertion expected the old chapter-start loading expression and ETA reset. The implementation intentionally uses the warm-up state and preserves a valid measured ETA across chapter starts; the assertion now checks that new contract.

The three test-double/expectation repairs are committed on the Dragon Studio branch. These are confirmed causes from #3202; they are not a substitute for the original push-run logs from #3198–#3200, which remain undiagnosed individually.

The new CI rule runs the Windows package job for pull requests whose head branch starts with `dragon-studio/`, after the tests job succeeds. This closes the gap where the earlier pull-request validation ran tests but skipped artifact packaging.

## Closure checklist for every bug

- [ ] Reproduction recorded with source version/build and exact steps.
- [ ] Failing source path and root cause confirmed from code or logs.
- [ ] Focused regression test added and observed failing before the fix where practical.
- [ ] Fix committed on this tracking branch with a bug ID in the commit/PR description.
- [ ] Focused tests pass on the exact commit.
- [ ] Full regression suite passes on the exact commit.
- [ ] Windows packaged artifact checkpoint passes on the exact commit.
- [ ] Real Windows UI/installer/audio/hardware acceptance completed where applicable.
- [ ] Evidence (run URL, artifact, logs, screenshot or playback result) attached to the bug record.
- [ ] Help & Guide updated if the user-visible workflow or limitation changed.

## Release boundary

Before the 1.2.0 tag, release-blocking rows stay in the release candidate checklist. After the exact 1.2.0 artifact is tagged and distributed, every newly discovered issue is marked either **post-release regression** or **older issue still open**, with the affected released version and first known bad build recorded. The branch remains the shared fix queue; it is not a reason to reopen or redo already accepted stages.

## Exact-head packaged acceptance — Build Windows App #3291

**Exact commit:** `3cb6f0d8cda0257b3d7e8a89d8ca74e51bbb88ff`  
**PR:** [#35](https://github.com/RyuBlanc/ryu-audiobook-build/pull/35)  
**PR workflow:** [#3291](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43049805295) — success  
**Push workflow:** [#3290](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43049793518) — success

### Confirmed by the #3291 package logs

- Regression suite and Windows package jobs both completed successfully.
- The real Piper acceptance generated a two-chapter M4B, reloaded saved narrator/Mira/Ren profiles, routed the dialogue to the saved character voices, verified voice identity output, and passed FFmpeg audio decode plus two named chapter markers. Evidence: `REAL_MULTICHAPTER_M4B=PASS`, `REAL_M4B_FFMPEG_DECODE=PASS`, and `STAGE_3_REAL_PROVIDER_ACCEPTANCE=PASS`.
- The packaged UI acceptance generated a real narrator-only M4B for a zero-character-profile fixture, persisted narrator-only mode and saved narrator identity through project/job/History, and opened the generated output in Audiobooks playback. Evidence: `xapp08_packaged_narrator_only_full_book_generation`.
- All 41 responsive CSS/DOM viewport cases passed across all 15 active pages, player, Library, mini-player, History, Task Manager and job details. The responsive shell bounds also passed. The separate scale/window emulator covered restored, half, quarter, maximized, ultrawide, portrait and 100/125/150/200% effective-size cases.
- The packaged overlap scan passed on all 15 destinations. Help Guide search, empty-result and expand/collapse checks ran as part of the same packaged acceptance.
- The Windows install/launch/upgrade/uninstall, user-data preservation, installer startup, logo transparency/hash checks, and Defender scan steps succeeded.
- Artifacts uploaded: installer ZIP `Ryu-Audiobook-Installer-3291`, SHA-256/package report `Ryu-Audiobook-Release-SHA256-3291`, and real M4B evidence `Ryu-Stage3-Real-Multichapter-M4B-3291`.

### Updated classification of the verification queue

| ID | Exact-head evidence | Still required before closure |
|---|---|---|
| DS-ETA-001 | The measured timing/countdown implementation is in the tested head; full regression and packaged UI gates passed. | The old #3198–#3200 push failures remain individually undiagnosed because their logs are unavailable. A long real generation on the target PC must confirm the estimate remains monotonic/stable and useful during warm-up, pause, resume and slow Qwen chunks. |
| DS-PROG-002 | Exact-head UI tests and packaged 41-viewport/overlap acceptance passed. | Long-running real Qwen/Piper generation on the target PC must show truthful movement, active stage/chapter, elapsed time and validated-work progress throughout the job. |
| DS-DURATION-003 | Listening-time estimate, chapter projection and final-output measurement paths are covered by regression/package contracts; actual M4B was produced in two CI smoke paths. | Compare estimated, accumulated chapter and final measured durations against a full-book target-PC output; ensure labels do not conflate listening duration with synthesis time. |
| DS-QWEN-004 | Provider #414 passed real CustomVoice 0.6B/1.7B, authorized Base Clone, saved VoiceDesign profile reload with identical anchor SHA, and two-chapter Qwen character-to-M4B production. Stage C1 adds a regression for Native Character Studio's identity-locked VoiceDesign audition path. | Validate the Stage C1 correction on an exact-head packaged build, then audition and save/reload CustomVoice, VoiceDesign and Clone in the installed app on the target PC. |
| DS-QWEN-005 | Runtime selection and hardware fallback contracts are regression-tested; dedicated real-device acceptance workflows exist. | Not closed. CPU historical 30-second preview was ~298–355 seconds. NVIDIA run #15 and AMD/Intel run #23 have no assigned self-hosted runner jobs. Need real NVIDIA CUDA, AMD ROCm and Intel XPU hardware evidence; no CPU/simulated substitution. |
| DS-JOBS-006 | Pause/resume/cancel-at-checkpoint, restart recovery, retry project ownership, checkpoint integrity and terminal job/history consistency have regression coverage. | Exercise a long real packaged job, force application/OS interruption, restart, recover/retry and verify no stale output or duplicate synthesis on the target PC. |
| DS-M4B-007 | Two-chapter real Piper output passed FFmpeg decoding/chapter markers; packaged narrator-only full-book generation produced M4B and played the generated output in the packaged Audiobooks view. | A representative full novel using the selected target-PC provider/cast must be generated and auditioned end-to-end. Verify all expected chapters, metadata, cover, duration and playback/seek/chapter navigation. |
| DS-CAST-008 | CI real Piper cast smoke passed saved-profile round-trip, narrator vs Mira/Ren routing, same-identity reuse and no cross-series character routing. Narrator-only packaged generation also passed. | Revalidate Qwen saved identities and Unassigned Character/narrator fallback on the target PC with a representative book. |
| DS-UI-009 | Packaged overlap checks and 41 viewport CSS/DOM matrix passed. | Visually inspect Production Studio information hierarchy and user-supplied cover art in the installed app; confirm no app watermark is baked into the chosen artwork. |
| DS-BRAND-010 | Build #3291 validated transparent logo alpha/corners, generated icon/installer assets, and completed install/uninstall. | Inspect actual shortcut/taskbar/installed shell icon on the target PC and confirm no opaque white/black square appears. |
| DS-INSTALL-011 | Installer window geometry tests and #3291 HTML/core installer, startup, install, upgrade and uninstall steps passed. | Inspect the actual wizard visually at the target PC's display scaling/resolution; verify footer, Next/Back, details and frame have no cropping/black center bar. |
| DS-AI-012 | Unicode NFKC/casefold source matching and English false-positive/stopword regression tests passed in the exact-head suite. | Analyze representative Japanese, Chinese and Korean novels and an accented Latin sample; compare detected names, exact quote evidence, false positives and passage counts against the source. The historic 1,175-vs-1,196 passage reconciliation remains open. |
| DS-RESP-013 | **Automated 41-viewport CSS/DOM matrix passed** on all 15 pages at #3291, including Generate 1280×720, portrait/ultrawide, player/Library/mini-player/History/Task Manager/job details. Window/scale emulation passed. | Physical minimized/restored, mixed-DPI, multiple-monitor and extended-monitor checks still require Windows hardware; the emulated scale matrix is not a physical DPI test. |
| DS-HELP-014 | Help Guide content contracts and packaged search, empty-result, expand and collapse interactions passed at #3291. | Final wording parity review against every user-visible feature after any remaining product changes; verify guide on target PC. |

### Current artifact boundary and next required build

The #3291 PR run uploaded the installer, release SHA-256/package report and the M4B evidence. Its portable upload was **skipped by the workflow condition for all pull requests**; this is a delivery-policy gap, not a successful portable artifact.

The workflow is being adjusted so only PRs whose head starts with `dragon-studio/` also upload the portable application. Release publication remains restricted to a push on `main`. A new exact-head PR package run must pass before a portable artifact is claimed.

**Hardware/manual boundary:** automated acceptance is not a substitute for real target-PC multi-monitor/DPI, shell icon, installer visuals, Qwen profiles, long-book generation and playback. NVIDIA/AMD/Intel Qwen accelerator gates remain blocked until matching self-hosted runners are online. Do not close those rows without their evidence.

## Exact-head package acceptance — Build Windows App #3323

- **Run:** [#3323 / 43139856426](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43139856426)
- **PR:** [#35](https://github.com/RyuBlanc/ryu-audiobook-build/pull/35)
- **Exact head:** `1c235746646a4a3ba0263178cb1bba045ebffd93`
- **Result:** Tests and Windows package jobs both completed successfully. Full regression suite: **1,523 tests, OK** in 67.393 seconds.
- **Test correction:** Replaced the stale exact-source assertion for inline prompt construction with AST-level checks of `create_locked_clone_prompts` and the saved-anchor call path. Added a runtime-shaped Automatic CUDA OOM recovery regression for `base-1.7b`, verifying that the selected model kind, saved anchor path/transcript, profile identity and seed are preserved and the identity prompt is rebuilt on CPU. Existing Automatic CUDA/XPU and explicit-CUDA no-fallback tests also passed.
- **Windows package acceptance:** Application preparation/build, frozen-app verification, bundled voice assets/critical modules, real bundled-Piper multi-chapter M4B, packaged Sound Design/Music Library acceptance, Inno Setup, core installer, HTML installer, installer UI startup, install/launch/upgrade/uninstall, logo transparency/hash, package-size report, Microsoft Defender, and artifact uploads all passed.
- **Artifacts:**
  - Installer: `Ryu-Audiobook-Installer-3323` — 846,232,402 bytes.
  - Portable: `Ryu-Audiobook-Portable-3323` — 1,183,868,011 bytes.
  - SHA/package manifest: `Ryu-Audiobook-Release-SHA256-3323` — 3,043 bytes.
  - Real multi-chapter M4B: `Ryu-Stage3-Real-Multichapter-M4B-3323` — 8,935,889 bytes.
- The optional Stage 7 real Piper benchmark upload and public release publication steps were skipped by workflow conditions; no release was published by this PR run.
- **Acceptance boundary:** This is a successful exact-head automated Windows package checkpoint. It does not close physical-target-PC Qwen profile audition/save/reload, real NVIDIA/AMD/Intel performance, a representative full novel with user-selected voices, physical display/DPI and installer visual checks, or long-running pause/resume/recovery acceptance. Do not mark these complete from simulated tests or the bundled Piper fixture.

### Remaining verification queue after #3323

- DS-ETA-001 / DS-PROG-002 / DS-DURATION-003: long real Qwen/Piper target-PC run to verify truthful chunk progress, 1:1 ring, elapsed time, monotonic measured ETA, audiobook listening-duration estimate, and authoritative final M4B duration across chapters, pauses and resumes.
- DS-QWEN-004: install/run and audition saved CustomVoice, VoiceDesign and Clone profiles; save/reload each and verify selected identity in the actual packaged runtime.
- DS-QWEN-005: real NVIDIA CUDA, AMD ROCm and Intel XPU acceptance on assigned physical runners; 30-second VoiceDesign preview target remains <60 seconds on supported NVIDIA hardware. Historical CPU timings do not satisfy this target.
- DS-JOBS-006: packaged pause, resume, cancel, retry, forced interruption, restart/recovery, durable job state and history.
- DS-M4B-007: representative full-novel chaptered M4B, metadata/cover/chapter/duration validation and actual playback/seek.
- DS-UI-009 / DS-BRAND-010 / DS-INSTALL-011 / DS-RESP-013: physical target-PC inspection of Production Studio cover-art separation/layout, shell icon alpha, installer geometry, real mixed-DPI/multi-monitor behaviour; automated 41-viewport checks are not physical DPI checks.
- DS-HELP-014: final Help & Guide audit against the actual shipped features and recovery paths.



## Exact-head Windows package checkpoint — Build #3327

- **PR:** [#35](https://github.com/RyuBlanc/ryu-audiobook-build/pull/35)
- **Run:** [Build Windows App #3327](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43159940335)
- **Exact head:** `4acba59fa8dcd0e52cba60bb28a401b8dc43f4c6`
- **Regression suite:** **1,523 passed**. JavaScript syntax, isolated native Qt lifecycle and Stage 6 History/Task Manager preflight passed.
- **Windows package:** success. Frozen application, bundled voice assets/modules, real bundled-Piper multi-chapter M4B, packaged Sound Design/Music acceptance, Inno Setup installer, functional HTML installer startup, install/launch/upgrade/uninstall, logo transparency/hashes, package size report and Microsoft Defender scan passed.
- **Artifacts:** installer `Ryu-Audiobook-Installer-3327` (846,171,638 bytes; artifact `13919385123`); portable `Ryu-Audiobook-Portable-3327` (1,183,868,011 bytes; `13918936894`); SHA manifest `Ryu-Audiobook-Release-SHA256-3327` (3,047 bytes; `13919370271`); multi-chapter M4B evidence `Ryu-Stage3-Real-Multichapter-M4B-3327` (8,997,510 bytes; `13917718510`).
- **Skipped by workflow condition:** optional Stage 7 real Piper benchmark upload and public release publication. No release was published.
- **PR state:** open and draft. This is an exact-head CI/package pass, not physical Qwen GPU or full-book target-PC acceptance.
- **Open acceptance:** physical Qwen profile save/reload/audition; CUDA/ROCm/XPU hardware runs and NVIDIA <60-second preview; long real-generation progress/ETA/duration; forced interruption/recovery; full novel M4B/playback; cast routing; cover-art/branding/installer visual checks; physical display/DPI; final Help & Guide review.

## Follow-up Qwen safety coverage

After #3327, focused regression tests were added for:
- one-pass VoiceDesign preview automatic OOM recovery: retain the same `design-1.7b` model and the full preview request, retry on CPU, and verify a real output file is written;
- explicit CUDA, ROCm and XPU VoiceDesign OOM: fail closed on the selected accelerator and prove no CPU model loader is called.

These tests are awaiting the next exact-head regression and Windows package run. They do not claim physical hardware validation.


## Updated exact-head acceptance — Builds #3333 and #3334

- [Build #3333](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43166950641), commit `8b48dc7dfcdb3472fd405a0f1d8c56d6045f373a`: 1,525 tests passed and full Windows package passed. This commit corrected only the explicit-backend Qwen OOM test double.
- [Build #3334](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43167024722), exact PR head at the time `2a1925673c5c9cedaf7cf8bbbcedf10d68e7d0a5`: 1,525 tests passed and full Windows package passed. This commit added only the failure/correction record to the push ledger.
- Stage 7 bundled Piper measurements were CPU ONNX: #3333 = 3.458s for 12.631s audio (RTF 0.274); #3334 = 2.837s for 12.701s audio (RTF 0.223). Both reported `CPUExecutionProvider`.
- [Qwen CPU workflow #33](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43166944780) passed 70 focused tests and real CPU 1.7B VoiceDesign preview (30.000s audio, 342.812s warm), plus warm/angry expression and Japanese pronunciation diagnostics.
- **No Qwen target-PC performance or profile persistence row is closed by these checks.** The CPU preview misses the target; NVIDIA/AMD/Intel runner jobs have not executed; physical save/reload/audition, full-book M4B and long-run generation acceptance remain open.


## Run failure diagnosis and exact-head correction — Builds #3335–#3339

- **#3335** — [run](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43173516940), commit `5a5be58665e642b632e11e7f7ec1fa730b8fa47a`: 1,525 tests ran; one failed. All setup/preflight checks passed. The single failure was `test_dragon_studio_pr_runs_packaged_acceptance_and_uploads_candidate_installer_and_manifest`: the PR artifact policy requires Stage 7 Piper evidence upload to remain disabled on pull_request, but the workflow had been changed to upload whenever the benchmark JSON existed.
- **#3336** — [run](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43173608205), commit `c2e4ffd3423842b8e6f6a597c6208e9a2cbfa3bc`: same single assertion failure; this was a status-register documentation commit and did not change the workflow condition.
- **#3337** — [run](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43173777908), commit `be60099becaeddb423a479080c51d69b41bbd30a`: 1,526 tests ran; the same single PR artifact-policy assertion failed. This commit added explicit-backend VoiceDesign preview OOM tests. Its separate [Qwen CPU workflow #34](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43173772666) passed 71 focused tests and produced actual 30.000s Qwen 1.7B VoiceDesign CPU audio; warm preview took 360.765s, so the performance target remains unmet.
- **#3338** — [run](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43173968701), commit `7248dbf5a2a334a53c077c78ec13279435306f47`: 1,526 tests ran; same single PR artifact-policy assertion failed. The commit fixed escaped GitHub Actions expression markers in the new run-summary environment variables.
- **#3339** — [run](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43174166569), exact head `39a68d21a312d58220aa5d035d98aed566ac2672`: restored `if: ${{ github.event_name != 'pull_request' }}` for the Piper JSON artifact upload. Result: **1,526 tests passed; full Windows package passed**. This closes the CI regression introduced by the #3335 workflow edit; the preceding four runs remain historically failed and are not relabelled green.
- The failures were **not app runtime regressions**: in each, the test setup and all other test cases passed; the build/package job was correctly skipped because the test job failed.
- The run-summary step now emits the exact commit, PR metadata, commit message/rationale and changed-file list. The Stage 7 measured benchmark metrics are appended separately. On PR runs the measured metrics remain in the job summary, while the raw Stage 7 JSON artifact upload stays disabled by the PR policy. Public release publication also remains skipped on PR runs.

### Build #3339 artifact evidence

- Installer `Ryu-Audiobook-Installer-3339`: 846,123,896 bytes; artifact ID `13925155689`.
- Portable `Ryu-Audiobook-Portable-3339`: 1,183,868,011 bytes; artifact ID `13924911356`.
- SHA-256 manifest `Ryu-Audiobook-Release-SHA256-3339`: 3,044 bytes; artifact ID `13925220599`.
- Real multi-chapter M4B evidence `Ryu-Stage3-Real-Multichapter-M4B-3339`: 8,967,241 bytes; artifact ID `13923457578`.
- Stage 7 real Piper benchmark: `en_US-amy-medium`, 2.635s synthesis, 12.724s generated audio, RTF 0.207; actual verified ONNX backend CPU / `CPUExecutionProvider`; post-synthesis process RSS 365,465,600 bytes; available system RAM 13,188,767,744 of 17,174,360,064 bytes. This is hosted Windows CPU Piper, not Qwen and not GPU validation.


## Dragon Studio correction chain and current acceptance — November 12, 2026

Builds #3358–#3362 were not six unrelated product regressions. The first direct-project resolver commit changed the production bridge to a safe cached folder loader; the failures that followed were incomplete fake bridge fixtures and one Windows path-key mismatch in tests. The later Qwen acceptance instrumentation introduced a missing `time` import, which was corrected in #3363. All preceding failures remain historically failed; #3363 is the exact-head green correction.

- **#3358**: five Stage 8 retry/recovery fixtures lacked `_load_library_project`.
- **#3359**: 15 test-double errors remained across player, Dashboard, Voice Preview, Stage 5 and Stage 8 fixtures.
- **#3360**: only the Dashboard requested-audiobook test failed because its mock path key was not normalized.
- **#3361**: Dashboard path issue plus missing stopwatch module import; Provider #412 separately reached the real production smoke and raised `NameError: time is not defined`.
- **#3362**: Dashboard issue corrected; one stopwatch import assertion remained.
- **#3363**: `time` import corrected; 1,541 tests and full Windows package passed.
- **#3364**: the test job confirmed the PR-topic step and passed all tests; Windows packaging was still running at this register snapshot.
- **#3365**: a native renderer-retry blank-frame defect is corrected in source and guarded by `test_renderer_retry_keeps_native_splash_visible_before_both_reload_paths`; Actions validation is queued.

### Current Qwen evidence boundary

Provider Runtime Smoke #414 on `500d97a` completed successfully. Accelerator discovery/installer tests, expression protocol, actual CPU 1.7B VoiceDesign preview, warm/angry expression audio, Japanese pronunciation, 0.6B/1.7B CustomVoice save/reload and decoded audio, authorized Base Clone save/reload, saved VoiceDesign reload with matching anchor SHA, and two-chapter Qwen character-to-M4B with FFmpeg decode all passed. The 30-second CPU VoiceDesign timings were 372.782 seconds for the one-pass diagnostic and 165.985 seconds for the saved identity-locked profile preview. Both exceed the 60-second target; neither is an NVIDIA result. The job and artifact uploads completed successfully (Clone/Design/M4B artifact ID `13965151425`).

NVIDIA workflow #22 and AMD/Intel workflow #30 remain pending with no assigned self-hosted runner jobs. They are not device acceptance. No GPU performance pass is claimed.

### Current responsiveness evidence boundary

The direct resolver is protected by AST and filesystem-boundary tests; known-folder actions avoid `list_projects()`. The bridge has seven remaining `list_projects()` calls, each serving a full-library operation (Dashboard/Library listing, duplicate-source check, series-wide update, profile-dependency check, first-time Character Library hydration or diagnostics). The Library list path caches parsed Project objects by project/chapter file fingerprints.

The frontend route wrapper refreshes project lists only for Dashboard and Library; other panels are not blocked by that scan. Startup loads required settings/project/voice/chapter data first and defers character, sound, history and model hydration until after the core workspace is ready.

These code and regression results demonstrate that repeated unrelated-project loads were removed from the identified known-folder paths. They do **not** prove zero UI stalls/flicker on the target PC or close physical DPI/multi-monitor acceptance. The native renderer-retry splash correction is pending #3365.


## Build #3370 — A/B test pass; packaged acceptance failure diagnosed (13 November 2026)

- Exact head: `f644d9af9d12fe0af03484a60173b3619c4d6811`; [Build Windows App #3370](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43347009057).
- **This was the complete PR #35 build**, triggered by a pull-request synchronize event after the A/B continuation commit. It built the cumulative PR application. The commit itself added the Stage A register reconciliation, Stage B pause/resume regression, focused Stage B workflow step and ETA checkpoint documentation; it did not change the application runtime source.
- Tests job passed: JavaScript syntax, isolated native Qt lifecycle, focused Stage B **16/16**, focused Stage 6 **48/48**, full regression **1,544/1,544**. The new pause/resume ETA test passed both in the focused module and full suite.
- Windows package step 6 (frozen application build), step 7 (frozen verification), step 8 (bundled voice assets/critical modules), step 9 (real two-chapter Piper M4B acceptance) and step 10 (M4B evidence upload) passed.
- The real multi-chapter evidence artifact **`Ryu-Stage3-Real-Multichapter-M4B-3370`**, artifact ID `14002562242`, was uploaded at 9,037,412 bytes. The run reported the two-chapter M4B and FFmpeg chapter-marker decode as passing.
- The only failed build step was step 11, packaged Sound Design / Music Library acceptance. Its restart/persistence, mix/cue, real recovery, cross-module identity, History and Task Manager missing-View repair checks had passed up to the final mismatched-View repair. The final error was `Timed out waiting for Task Manager repairs a mismatched View action in place`. Installer, release hash, Defender and installer artifact steps were skipped because the prerequisite package acceptance failed; no installer/release checkpoint was created.
- This is the same acceptance point that failed in #3368 and passed in #3369. The packaged acceptance script and adapter source were unchanged from the successful #3369 head; the A/B commit changed no application runtime files. This run therefore does **not** establish a new application regression.
- **Cause confirmed in the polling contract and acceptance timing:** active jobs poll at 1,500 ms; idle jobs poll at 10,000 ms; hidden idle pages back off to 30,000 ms. The acceptance had just completed its scripted generation/recovery jobs, corrupted a View action, then waited exactly 10,000 ms while its comment incorrectly assumed the active 1,500 ms interval. It did not request a refresh, making the check race the adaptive idle poll (and potentially exceed it when hidden). The adaptive idle policy is intentional and must not be weakened merely to satisfy this fixture.
- **Correction pushed in the next A/B validation commit:** after removing or mismatching the View action, the acceptance invokes the existing Task Manager button's normal immediate-refresh path. It still requires the original row object to remain connected, the View action to be repaired to the exact backend job ID, and no full-list rebuild to replace the row. The wait is now bounded to 5 seconds after that explicit refresh. A Python contract test protects both refresh triggers and same-row assertions.
- A/B package acceptance remains open until a new exact-head Windows package passes all required gates. The successful 1,544-test job and M4B evidence artifact do not convert #3370 into a successful Windows package checkpoint.


## Build Windows App #3371 — Stage A/B exact-head Windows package checkpoint passed (13 November 2026)

- PR #35 synchronize run: [#3371 / 43351171744](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43351171744).
- Exact tested HEAD: `550cccc0508d0341889e7c88bfe44bea9ff93da1`; this matches the current PR #35 head when checked.
- Test job passed every step: JavaScript syntax, isolated native Qt lifecycle, focused Stage B ETA/progress **16/16**, focused Stage 6 History/Task Manager preflight **48/48**, and full regression **1,544/1,544**. The pause/resume ETA regression passed in both the focused and full suite.
- Windows build job passed every required gate: frozen application build and verification; bundled voice assets and critical-module verification; real bundled-Piper two-chapter M4B generation and FFmpeg chapter-marker decode; packaged Sound Design/Music Library acceptance; Inno Setup/core payload; functional HTML installer startup; hosted Windows install/launch/upgrade/uninstall; logo transparency/hash generation; package-size report; and Microsoft Defender scans of the app, HTML installer and core installer with no detection.
- Packaged Task Manager acceptance explicitly passed both `stage6_task_manager_repairs_missing_view_action_in_place` and `stage6_task_manager_repairs_mismatched_view_action_in_place`. Both restored the identity-matched View action without replacing the existing native row. The test triggers the normal immediate refresh; adaptive production polling was not changed.
- Real M4B evidence: 2 chapters, 504,269-byte M4B fixture; FFmpeg decode and 2 chapter markers passed. Artifact `Ryu-Stage3-Real-Multichapter-M4B-3371`, ID `14005200121`, uploaded ZIP size 8,992,198 bytes.
- Preserved Windows artifacts (all uploaded by #3371 and unexpired at checkpoint time):
  - Installer `Ryu-Audiobook-Installer-3371`, ID `14005930515`, 845,998,580 bytes.
  - Portable `Ryu-Audiobook-Portable-3371`, ID `14004749158`, 1,183,885,216 bytes.
  - SHA-256 manifest `Ryu-Audiobook-Release-SHA256-3371`, ID `14005436978`, 3,040 bytes.
  - M4B evidence above.
- Package-size report: distribution 1,183,554,652 bytes across 1,739 files; HTML setup 845,998,416 bytes; core setup 619,168,828 bytes. Do not remove bundled assets merely to reduce package size without a separate compatibility/performance assessment.
- **Stage A:** exact baseline/run/result reconciliation is recorded. **Stage B:** automated accuracy and pause/resume regression plus hosted package gate are passed. The A/B hosted checkpoint is closed at this exact SHA.
- Scope boundary: PR #35 remains open and draft; the workflow's public-release publication step was skipped by PR policy. Hosted Windows install/upgrade tests do not replace hands-on target-PC testing. The two-chapter Piper fixture is not full-novel/Qwen acceptance.
- Still open after this checkpoint: real long-running Qwen/Piper progress, ETA and duration comparison on target PC; Qwen saved-profile identity and CustomVoice/VoiceDesign/Clone production acceptance; physical NVIDIA/AMD/Intel performance; representative full-book generation/recovery/playback; remaining Library/Character/Chapter/Production Studio defects; and physical display/DPI, shell-icon and installer-layout acceptance. Continue the active roadmap at **Stage C**, not historical Stages 1–8.

## Build Windows App #3372 — Stage A/B exact-head checkpoint reconfirmed (13 November 2026)

- Run: [#3372 / 43355282923](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43355282923). Exact tested HEAD: `65adc53da81e8faeca09bc50cf4f21f663cc5138`, matching PR #35 at the time.
- Focused Stage B: **16/16**; focused Stage 6: **48/48**; full regression: **1,544/1,544**. Every test-job step passed.
- Frozen app, bundled assets, real two-chapter Piper M4B/FFmpeg decode, packaged Sound Design/Music Library acceptance, installer startup, hosted install/launch/upgrade/uninstall, logo/hash, package-size and Defender gates all passed.
- Artifacts: installer ID `14007141961` (846,038,888 bytes); portable ID `14007426176` (1,183,885,216 bytes); SHA-256 manifest ID `14007535608` (3,041 bytes); two-chapter M4B evidence ID `14006256981` (8,981,117-byte ZIP).
- This is the verified Stage A/B starting point for Stage C. It did not perform the Native Character Studio identity audit described below.

## Stage C1 — Qwen VoiceDesign identity audit and candidate correction

- Source audit traced Voice Studio's native preview through `VoicePreviewWorker` → `provider_from_profile` → `QwenCharacterProvider`. For saved `design` profiles, that route preserves `qwen_profile_id` and uses the identity-locked VoiceDesign/Base anchor path also used for production.
- Confirmed defect: `NativeCharacterDialoguePanel.test_voice_profile` changed a selected saved Qwen VoiceDesign profile to `qwen_mode="design-preview"` and replaced its model ID with the standalone VoiceDesign model. That one-pass path can sound different from the selected saved profile used for audiobook production. It also checked the VoiceDesign model but not the required long-form Base model.
- Correction in this candidate: resolve the same VoiceDesign/Base model pair as Voice Studio using `qwen_model_kinds_for_preference`; in Auto mode use the same runtime helpers. Require both models to be installed, retain the original profile object/mode/profile ID, and send that unchanged profile through `VoicePreviewWorker`.
- Regression coverage: explicit 0.6B/1.7B model-size preference selection, Auto hardware-aware fallback, both model-readiness guards, and a source contract prohibiting the `design-preview` rewrite.
- The web Voice Studio profile-edit path was also audited: edits to VoiceDesign prompt/language/seed detach the prior saved profile before save, so no defect was confirmed there and that path is not changed.
- The #3375 candidate passed focused C1 7/7, Stage B 16/16, Stage 6 48/48, full regression 1,546/1,546 and all hosted Windows package gates.
- Additional confirmed production-routing gap: Voice Cast writes series-scoped voice identities, but Production's effective cast resolver did not read that map or the saved roster. Same-named characters across series could therefore lose their chosen voice in production; explicit unassigned values could be overridden by stale name-only assignments.
- This follow-on correction imports the roster, resolves exact Unicode-normalized (series, character) keys, preserves explicit empty assignments, and keeps legacy name-only mappings subordinate. Added focused tests route both same-named characters through CastAwareProvider to their selected profiles and verify explicit unassignment.
- This follow-on correction still needs focused, full-suite and exact-head packaged validation. Do not close C1 until those gates pass.

## Stage C acceptance boundary after #3372

- C2 hosted source/test/package acceptance is complete at Build #3382 on exact SHA `05a15fac65305e428752f194b8852884c40c7c5d`; installed target-PC repair/restart and voice audition remain physical acceptance items.
- C3 is active on the new exact C2-derived candidate branch: accelerator-discovery and benchmark-evidence regressions plus a saved-profile 0.6B CustomVoice preview gate. Physical NVIDIA CUDA, supported AMD ROCm and Intel XPU timing remain unproven until actual self-hosted hardware runs.
- C4 remains open: narrator/character identity consistency, emotional continuity, Japanese and other non-English pronunciation, and no voice drift on representative material.

### Stage C1 candidate workflow attempt #3373 — failed before the C1 tests ran

- Run: [#3373 / 43363581227](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43363581227), candidate SHA `188998bc55377d6e9e27d1ebae2b6349040647bd`.
- Passed before the failure: dependency setup, frontend JavaScript syntax, isolated Qt lifecycle (**1/1**), focused Stage B (**16/16**) and focused Stage 6 (**48/48**).
- Failure: the new `Run focused Stage C1 Qwen Character Studio identity regression` PowerShell step invoked `$pythonExe` without defining it in that step. GitHub Actions step processes do not share PowerShell variables; the interpreter command never ran. The C1 test module therefore has **no result** from #3373. Full regression and the build/package job were correctly skipped.
- Correction: resolve and validate `python.exe` inside the focused C1 step before invoking unittest. This is a workflow harness repair; it does not change the Qwen runtime or weaken the regression.
- #3373 remains a failed historical run. The corrected candidate requires a new push run, focused C1 result, full suite and exact-head package before PR promotion.

## Stage C1 follow-on — series-scoped Voice Cast production routing

- Exact-head source trace found that Voice Cast persists series-scoped assignments in voice_cast_identity_assignments using character_identity_key(name, series), but production's _effective_generation_character_rows did not consume the scoped map or voice_cast_character_roster. Same-named characters in separate series could display independent voices in Voice Cast while their selections were absent from the production cast.
- The resolver now imports the saved roster, applies each normalized (series, character) assignment, and treats an explicit empty value as the authoritative Unassigned choice. A stale name-only key cannot override a scoped record. Invalid/duplicate identity keys, duplicate matching rows, unresolved profile names and uncovered ambiguous legacy mappings remain strict-generation errors.
- Added regressions route the same character name in two series through CastAwareProvider using separate saved profiles, and verify an explicit empty scoped assignment overrides a stale legacy name-only mapping.
- The #3375 VoiceDesign preview correction remains independently validated. This follow-on production-router change has not yet been validated by Actions and requires a new exact-head package before Stage C1 can close.


## Stage C1 — Voice Studio assignment entry-point follow-on

- Candidate #3376 on exact SHA 54ff7e2da9d2d78ddbe27540f5f430ca0cbd2336 passed run 43372658193: Stage B 16/16, Stage 6 48/48, focused C1 7/7, full regression 1,548/1,548 and all hosted Windows package gates.
- Preserved #3376 artifacts: installer ID 14014730865; portable ID 14013769936; SHA-256 manifest ID 14014641192; real multi-chapter M4B evidence ID 14013926395; Piper benchmark ID 14014158132.
- Further C1 audit found Voice Studio Assign to Character used a name-only choice and wrote only the legacy voice_cast map. Same-named characters across series could collapse to one option and leave the newer scoped assignment map stale.
- Candidate fix builds choices by exact (series, character) identity, displays series for duplicate names, writes through VoiceCastPage._save_cast(update_voice=True), and uses a scoped-map fallback only when Voice Cast is unavailable. Legacy name-only values are written only when unambiguous.
- Production scoped-map preflight recognizes confirmed aliases as identity matches. Focused tests cover duplicate-name selection, both assignment persistence paths, and alias-keyed scoped assignment overriding stale legacy profile data.
- This follow-on requires focused C1, full regression and exact-head packaged Windows validation before C1 can close.

## Stage C1 candidate run #3377 — focused test fixture import failure

- Run [#3377 / 43382873285](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43382873285), exact candidate SHA 6424cc83ef0222603cabf39316c4941ac06dda6d.
- Passed before C1 failure: JavaScript syntax, isolated Qt lifecycle, Stage B 16/16, and Stage 6 48/48.
- Focused C1 executed 10 tests: the seven pre-existing C1 checks and the new same-name-choice helper passed; two new mocked assignment-flow tests errored at fixture setup because tempfile.TemporaryDirectory was used without importing tempfile. No application-code assertion failed. Full regression and package were correctly skipped.
- Correction: add the missing standard-library tempfile import. Do not remove either end-to-end mocked assignment test or reduce the focused suite.

## Build Windows App #3378 — one stale assignment contract

- Run [#3378 / 43383155116](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43383155116), candidate SHA `2e9d1e746efbc409352e7e96ba2c8c295b83120d`.
- Focused Stage C1 passed **10/10**, Stage B **16/16**, Stage 6 **48/48**. Full regression executed **1,552 tests** and had exactly one failure.
- The only failure was `test_native_voice_assignment_syncs_only_assigned_character_to_series_library`, whose static assertion expected the removed name-only `source_row` implementation. The new exact-series UI tests passed. The requirement to avoid changing unrelated Character Library voices is preserved.
- Follow-on correction uses `_save_cast(update_voice=False)` to persist the complete scoped Voice Cast state without bulk-overwriting Library voice records, then syncs exactly the selected `(series, character)` row with `update_voice=True`. The no-Voice-Cast fallback uses the same one-row operation.
- The two live assignment tests and the Stage 4 source contract now assert the exact selected series and single-row payload. Full regression and exact-head package remain open; #3378 stays recorded as failed.

## Build Windows App #3379 — Stage C1 tests green, packaged Production gate failed

- Run: [#3379 / 43384228609](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43384228609), exact candidate SHA `0533ecceed87dc56a684cb6ecca229ee45e7a294`.
- Test job passed: focused C1 **10/10**, Stage B **16/16**, Stage 6 **48/48**, full regression **1,552/1,552**.
- Build passed application preparation, frozen-app verification, bundled critical modules, three packaged Premium V2 startup launches, real Piper 10/30/60/90-second previews, two-chapter M4B generation and FFmpeg chapter-marker decode. M4B artifact ID `14018382062`, ZIP 8,998,989 bytes.
- Only failed package step: `Run packaged Sound Design Music Library acceptance (including Stage 5.3 generation UI)`. The Sound Design/Library interactions and real production preview/full-generation assertions completed, but the later Stage 5.4 job-control fixture timed out waiting for `#startGenerate` to become enabled. Its tooltip remained `Finish or cancel the active Production audio operation first.`
- The failure diagnostic showed the current Stage 5.4 project had saved metadata, a saved and available Offline Neural narrator, valid output configuration and dialogue readiness. All listed project audio jobs were terminal; the remaining visible Production lock came from a stale frontend `productionJobSnapshots` value that was not refreshed when navigating back to Generate after switching projects.
- Source audit found `bindMiniPlayerNavigation()` already contained the intended Production-navigation job refresh but **was never invoked from `wire()`**. Therefore a new Generate page could retain the previous project's active preview snapshot until a later poll.
- Correction: activate the existing navigation wrapper during adapter wiring, refresh the real project-filtered `job.list` on Generate/Production navigation, and retain the existing busy gate against the newly selected project's jobs. No active-job requirement is removed and no test waits are weakened.
- The packaged test's failure diagnostics also called unsupported prototype-only bridge actions `voice.select.get` and `production.readiness`. Those calls are replaced with the authoritative fields already returned by native `project.get_active`, eliminating misleading disconnected-command errors while preserving narrator/readiness diagnostics.
- Added focused contracts for navigation-triggered job refresh and for use of supported native readiness fields. The candidate must pass focused tests, full regression and an exact-head package before Stage C1 closes. Installer steps skipped after #3379's packaged gate failure; #3379 is not a package pass.


## Stage C1 automated closeout and Stage C2 implementation candidate — 13 November 2026

### Stage C1 exact-head result

- Build Windows App [#3380 / run 43387876985](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43387876985) passed on exact SHA e7ce7896d2bcb9ea93a47ab9dae9d5e5a502726c of the candidate-c1-voice-identity branch.
- Focused C1, Stage B and Stage 6 preflight steps passed; the complete regression suite passed **1,554 tests**.
- The Windows package passed frozen-app/asset verification, real multi-chapter Piper M4B and FFmpeg chapter-marker acceptance, packaged Sound Design/Production, restart/recovery, functional installer, hosted Windows install/launch/upgrade/uninstall, logo/hash, Defender and artifact-upload gates.
- The only #3379 packaged Production failure was fixed by wiring Generate navigation to refresh authoritative project-scoped job snapshots. The existing active-job guard was retained.
- **C1 automated/source/package acceptance is complete.** Manual audition of the installed saved CustomVoice, VoiceDesign and Clone profiles, restart, and final production identity on the target PC remain explicit physical acceptance requirements. They are not inferred from hosted CI.

### Stage C2 — profile restart and install/repair lifecycle

- Source audit confirmed that profile catalogue save/migration is already atomic and that real CPU provider acceptance has exercised save/reload. C2 therefore adds the missing fresh-process proof rather than replacing working profile persistence.
- Confirmed repair reliability defect: repair_runtime() previously removed the existing Qwen readiness marker and venv before creating the replacement. A failed repair could strand a previously working installation. The new implementation keeps the old private Python, venv and marker in a repair backup until the replacement runtime passes its self-check; failed repair restores the previous files. Repair/install refuses to replace a runtime while a Qwen worker is active.
- The C2 regression additions cover successful replacement, failure rollback, active-worker protection, recovery of an interrupted repair, CustomVoice/VoiceDesign/Clone model selection under 0.6B/1.7B/Auto, safe removal of one model/runtime without deleting profiles/anchors/other model weights, and profile reload from a separate Python interpreter.
- Build Windows App #3382 passed on exact commit `05a15fac65305e428752f194b8852884c40c7c5d`: C2 focused lifecycle/restart **9/9**; Stage B **16/16**; Stage 6 **48/48**; C1 **10/10**; full regression **1,563/1,563**. The exact-head Windows package, hosted install/launch/upgrade/uninstall, Defender, M4B/Piper evidence and artifact uploads all passed. This closes C2 hosted acceptance; target-PC hardware and installed-app checks remain separate. No physical GPU result is claimed.

## Stage C2 exact-head closeout and Stage C3 handoff — 13 November 2026

- C2 exact candidate branch: `dragon-studio/candidate-c2-profile-lifecycle-2026-11-13`.
- Exact C2 commit: `05a15fac65305e428752f194b8852884c40c7c5d`.
- Build Windows App #3382: [run 43400140506](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43400140506), completed successfully on that exact SHA.
- Test acceptance: C2 lifecycle/restart **9/9**; C1 preflight **10/10**; Stage B **16/16**; Stage 6 **48/48**; full regression **1,563/1,563**.
- Windows package acceptance: frozen application and bundled assets; real multi-chapter M4B/FFmpeg decode; packaged Production/Sound Design; installer startup; hosted Windows install/launch/upgrade/uninstall and user-data preservation; logo/hash and package-size checks; Defender scans and all artifact uploads passed.
- Preserved artifacts: installer ID `14026626426` (846,161,241 bytes); portable ID `14026367342` (1,183,914,174 bytes); SHA-256 manifest ID `14026132844`; M4B evidence ID `14024234780`; Piper benchmark ID `14026810708`.
- C2 hosted acceptance is complete. Target-PC repair/restart, saved-profile audition, physical GPU, full-novel Qwen and physical playback remain separate acceptance work.
- Parent C1 checkpoint #3381 also completed successfully on `e7ce7896d2bcb9ea93a47ab9dae9d5e5a502726c`.

## Stage C3 — Qwen accelerator detection and performance acceptance candidate

- Candidate branch: `dragon-studio/candidate-c3-qwen-accelerator-acceptance-2026-11-13`, branched from the exact #3382 SHA.
- Automatic benchmark history must reject materially future-dated (>5-minute skew) and stale (>30-day) data and compare timezone-aware timestamps as instants.
- Focused tests cover active NVIDIA CUDA, AMD ROCm and Intel XPU discovery; NVIDIA hardware visible without CUDA PyTorch remains a non-passing runtime candidate; Intel Arc/Core Ultra and AMD Windows ROCm device predicates; future-dated paired CPU/GPU history cannot displace a real active GPU.
- Existing 1.7B VoiceDesign CUDA gate remains unchanged: saved profile reload, VoiceDesign/Base identity lock, real 27–33s WAV, verified device `cuda`, no CPU substitution and warmed preview under 60s. A separate 0.6B CustomVoice gate covers the lower-memory NVIDIA path where the model actually loads.
- CPU contract run #38 / [43400140577](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43400140577) produced 30.000s of saved-profile VoiceDesign audio in 255.415s and explicitly marked the hosted CPU 60s target as not met. This is comparison-only, not GPU acceptance.
- C3 cannot close until an exact-head Windows package and actual device-verified self-hosted run(s) prove each claimed hardware backend, including saved-profile preview audio, timing JSON/logs, device/runtime metadata and uploaded evidence. Do not count a hosted CPU run or hardware candidate as accelerator acceptance.

### C3 first exact-head validation — Build Windows App #3384

- Run [43415226253](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43415226253) on `cf26fe3b60444d2e6c04147a306edbcd599e5c79` passed JavaScript syntax, native Qt lifecycle, Stage B **16/16**, Stage 6 **48/48**, C1 **10/10** and C2 **9/9**.
- The focused C3 suite ran seven tests; six passed. The only failure was a test-fixture contract mismatch: `_nvidia_smi_devices()` returns VRAM already normalized in GiB, but the mocked result supplied the raw `nvidia-smi` MiB value `4096` and expected `4.0`. The real parser divides the driver value by 1024.
- No application detector regression was proven by this run. Full regression and Windows packaging were correctly skipped after the focused test failed.
- Corrective test change supplies `4.0` GiB to the mocked detector and adds a separate parser regression proving raw `4096` MiB is normalized to `4.0` GiB. No test is removed or relaxed; the candidate must rerun at a new exact SHA.


## Stage C4 — Qwen multilingual voice identity and expressive continuity (candidate in progress)

- Candidate branch: dragon-studio/candidate-c4-voice-identity-continuity-2026-11-13. Latest application/test head before the documentation/revalidation push: 45a0d5ee66363f3c258e1512e28347e457212027 (Build Windows App #3405).
- C4 scope: language-matched VoiceDesign identity anchors for English, Japanese, Korean, Chinese, German, French, Russian, Portuguese, Spanish and Italian; preserve a saved language instead of inferring a different one from mixed/native-script text; preserve one canonical acoustic anchor across neutral and emotional synthesis and profile reload; invalidate resumable Qwen Design chunks when the expression pipeline changes without invalidating unrelated CustomVoice chunks; maintain native-language emotion/whisper cues; exercise the real saved-profile and CastAwareProvider production routes.
- Earlier failed runs remain historical failures: #3390 exposed an obsolete regression assertion requiring ANCHOR_TEXTS although the worker had moved to a single canonical neutral anchor; #3394 exposed missing multilingual emotion forms (including German panic, French boredom, Spanish/Portuguese panic and curiosity/surprise, Italian panic and Russian anger); #3397 exposed a stale source assertion for the old v8-emotion-range-anchor after the worker had moved to v9-language-matched-anchor-direction. The #3394 cue gaps were corrected in #3395. The #3397 test contract was corrected in #3398 to assert the versioned localized cache identity rather than the obsolete version literal.
- #3399 / Provider Runtime Smoke #441 proved real CPU Japanese saved-profile VoiceDesign after reload: neutral and angry audio, explicit Japanese, Design 1.7B + Base 0.6B, actual CPU telemetry and unchanged anchor SHA. #441 also passed real CustomVoice 0.6B/1.7B, Base Clone and two-chapter Qwen character-to-M4B acceptance. The 30-second VoiceDesign preview took 229.539 seconds on CPU; this is not a performance pass.
- #3401 added expression-pipeline versioning to the Qwen Design provider/resume signatures; custom voice signatures remain unchanged. #3402 and Provider Runtime Smoke #444 then passed real neutral/angry saved-profile VoiceDesign synthesis, reload and unchanged anchor SHA for nine additional languages (English, Korean, Chinese, German, French, Russian, Portuguese, Spanish, Italian), as well as Base Clone and two-chapter Qwen character M4B. #444's 30-second preview took 241.443 seconds on CPU.
- #3403 / [run 43461070567](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43461070567) failed the focused C4 suite because the broad Portuguese trem stem classified the neutral sentence "Hoje vou de trem até o centro da cidade." as concerned. The other focused preflights passed; full regression and Windows package were correctly skipped. #3404 narrowed the pattern to Portuguese trembling verb forms; #3405 added tremor and tremedeira coverage while retaining the train-noun negative case.
- Latest Build Windows App #3405 / [run 43462518581](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43462518581), exact SHA 45a0d5e: Stage B 16/16, Stage 6 48/48, C1 10/10, C2 9/9, C3 8/8, C4 focused suite passed, and full regression 1,595/1,595. Build/package was correctly skipped because this was an intermediate fix, not an artifact checkpoint. Provider Runtime Smoke #447 was skipped because the commit did not request [qwen-acceptance]; #3404's Provider Runtime Smoke #446 was cancelled and is not evidence.
- Next exact-head gate: a tagged documentation/ledger commit requests [qwen-acceptance] on top of #3405. This must rerun the complete real CPU Provider Runtime Smoke chain on the current head, including all ten language profiles, neutral/angry audio, reload/anchor hashes, CustomVoice, Base Clone and Qwen character-to-M4B. That run is a CPU functional/identity gate, not GPU performance evidence.
- C4 closure boundary: after current-head real smoke passes, run one exact-head Windows artifact checkpoint with all accumulated tests and existing package/install/Defender gates unchanged. Keep installed-app/target-PC auditions and Stage C3 physical GPU checks open until their own evidence exists. Do not infer a full-novel result from the two-chapter fixture.
