# Dragon Studio — 1.2.0 Bug-Fix Register

**Tracking branch:** `dragon-studio/1.2.0-post-release-bugfixes`  
**Baseline:** current Stage 5 functional branch plus the measured-ETA repair candidate  
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
| DS-ETA-001 | Production Studio ETA | Remaining-time estimate increased over time while elapsed time increased normally; screenshots showed 15% progress with remaining estimate moving from 22:28:45 to 22:31:01 over about 23 seconds. | Existing defect; pre-release blocker until verified | Candidate repair committed: actual synthesis-call timing, rolling median/smoothing, timestamped frontend countdown and native-page parity. **Not accepted: Builds #3198, #3199 and #3200 are failed. Root cause of those CI failures still needs exact job logs.** |
| DS-PROG-002 | Production Studio progress | Ring stayed at 15% during long-running synthesis; percentage, active chapter, total workload and validated chunk progress need to be truthful and readable. | Existing defect; pre-release blocker until verified | Validated-chunk counter and workload details implemented in candidate. **Packaged visual/runtime acceptance pending.** |
| DS-DURATION-003 | Production Studio duration | Show expected audiobook listening length before completion, measured audio duration as chapters complete, and authoritative full M4B duration after validation. | Existing missing capability / accuracy issue | Text-based estimate and completed-chapter projection implemented. Must remain clearly labelled approximate until final M4B is measured. **Not runtime-accepted.** |
| DS-QWEN-004 | Qwen Voice Studio | Saved Qwen profiles and CustomVoice/VoiceDesign/Clone paths must load, preview the selected identity, save and reload consistently, and not fail inside the isolated external runtime. | Older issue; release-blocking regression risk | Build #3333 passed new one-pass VoiceDesign preview OOM-retry and explicit CUDA/ROCm/XPU fail-closed regression coverage; Qwen workflow #33 produced real 30-second CPU VoiceDesign audio and passed expression/Japanese diagnostics. **Still open:** physical installed-app save/reload/audition for CustomVoice, VoiceDesign and Clone, correct selected-voice playback and profile persistence on target PC. |
| DS-QWEN-005 | Qwen performance / hardware | 30-second preview target is under 60 seconds on supported NVIDIA hardware; CPU/AMD/Intel performance and backend reporting must be accurate and evidence-backed. | Older unmet performance goal | Real hosted CPU VoiceDesign previews: #29 = 30.000s audio / 320.118s warm; #33 = 30.000s / 342.812s warm. Both miss the <60s target. NVIDIA #20 and AMD/Intel #28 remain pending without assigned self-hosted hardware jobs. Stage 7 Piper benchmark is separately verified CPU ONNX and does not validate Qwen GPU acceleration. Physical NVIDIA, supported AMD ROCm and Intel XPU acceptance remain mandatory. |
| DS-JOBS-006 | Generation job lifecycle | Pause, resume, cancel, retry, interruption, durable recovery and history must refer to the correct job and preserve valid chapter checkpoints. | Existing P0 acceptance | Preserve Stage 5.4/5.5 work; run packaged interruption/recovery acceptance against current candidate. **Not closed by ETA changes.** |
| DS-M4B-007 | Full-book output | Multi-chapter generation must retain all eligible text, produce a valid chaptered M4B, validate duration/metadata and play correctly. | Existing P0 acceptance | Must pass packaged full-book generation, FFmpeg/M4B chapter validation and actual playback. **Not closed by ETA changes.** |
| DS-CAST-008 | Narrator / character assignment | Narrator-only mode, saved narrator identity, character-cast routing and Unassigned Character handling must agree across readiness, preview and final generation. | Existing behaviour; regression risk | Revalidate explicit narrator-only toggle, default-off behaviour, no-character fallback and saved voice identity. |
| DS-UI-009 | Production Studio layout | Organize the Production Studio controls and cards; prevent cover art from being permanently watermarked/embedded into the artwork; use the selected cover as artwork only. | Older user-reported UX defect | Requires source review and packaged visual acceptance at supported sizes. Keep artwork asset and app branding separate. |
| DS-BRAND-010 | Logo / Windows shell | Remove opaque white/black corner backgrounds from the logo where transparency is required; ensure taskbar, shortcut and installed-app icons use the intended transparent brand asset. | Older user-reported release defect | Re-run alpha/transparency and frozen Windows shell icon acceptance on the final installer. |
| DS-INSTALL-011 | Installer layout | Installer content was cropped at the bottom; Next/Back and details were not fully visible; unwanted black center bar/frame appeared. | Older user-reported release defect | Re-run installer window geometry tests and actual install/upgrade/uninstall on Windows. |
| DS-AI-012 | Multilingual novel analysis | Character/dialogue analysis must handle Japanese, Chinese, Korean and accented Latin text without losing names or quote evidence; English stopwords must not become characters. | Older functional defect / regression risk | Re-run Unicode-aware analysis and source-backed dialogue assignment tests on representative books. |
| DS-RESP-013 | Responsive UI | Verify Generate page and application layouts at 1280×720 and the agreed 41-viewport matrix, including mixed display scaling, ultrawide and portrait layouts. | Existing release acceptance | Keep the known Generate-page overflow and responsive regression gates. **Not closed by ETA changes.** |
| DS-HELP-014 | Help & Guide | Help and Guide content must describe the shipped features, controls, recovery paths and real limitations accurately. | Existing release acceptance | Review after the release-scope bug fixes so the guide matches the actual packaged build. |

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
