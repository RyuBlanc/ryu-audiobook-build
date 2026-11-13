# Dragon Studio — 1.2.0 Bug-Fix Register

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
| DS-QWEN-004 | Qwen Voice Studio | Saved Qwen profiles and CustomVoice/VoiceDesign/Clone paths must load, preview the selected identity, save and reload consistently, and not fail inside the isolated external runtime. | Older issue; release-blocking regression risk | Provider #414 passed real 0.6B and 1.7B CustomVoice generation, saved-profile reload and audio decode; hosted 1.7B VoiceDesign CPU preview and expression/Japanese diagnostics passed. The saved-profile identity-locked Base/VoiceDesign-to-M4B production job was still running at the latest ledger snapshot. **Still open:** installed-app target-PC save/reload/audition and selected-voice playback across CustomVoice, VoiceDesign and Clone. |
| DS-QWEN-005 | Qwen performance / hardware | 30-second preview target is under 60 seconds on supported NVIDIA hardware; CPU/AMD/Intel performance and backend reporting must be accurate and evidence-backed. | Older unmet performance goal | Provider #414 recorded a real hosted CPU VoiceDesign preview of 30.000s audio in 372.782s warmed time (cold-start plus warm-up 59.650s). This misses the preview performance target on CPU and is not NVIDIA timing. Stage 7 Piper is a separate CPU ONNX benchmark; do not interpret it as Qwen speed. Hardware workflows #22 (NVIDIA) and #30 (AMD/Intel) remain pending with no assigned jobs. **Open:** physical NVIDIA CUDA, supported AMD ROCm and Intel XPU acceptance, plus under-60-second 30s saved-profile preview on supported NVIDIA hardware. |
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
| DS-QWEN-004 | External runtime import/GPU-selection contract and saved-profile routing are covered by tests; the M4B Piper profile round-trip passed. | Audition and save/reload CustomVoice, VoiceDesign and Clone profiles using the actual installed Qwen runtime on the target PC. |
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

Provider Runtime Smoke #414 on `500d97a` passed accelerator discovery/installer tests, expression protocol, the hosted CPU 1.7B VoiceDesign audio path, warm/angry expression output, Japanese pronunciation diagnostic, and 0.6B/1.7B CustomVoice saved-profile reload/audio decode. The CPU 30-second preview took 372.782 seconds warmed; this is not an NVIDIA timing result. The final Qwen Base Clone + saved VoiceDesign + character-to-M4B job was still in progress at this snapshot.

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
