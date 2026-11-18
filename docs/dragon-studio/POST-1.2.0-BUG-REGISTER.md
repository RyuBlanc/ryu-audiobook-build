| DS-CAST-008 | Narrator / character assignment | Narrator-only mode, saved narrator identity, character-cast routing and Unassigned Character handling must agree across readiness, preview and final generation. | Existing behaviour; regression risk | Provider Runtime Smoke #448 on exact C4 SHA passed saved Japanese and nine-language VoiceDesign identity reloads and assigned two-chapter Qwen character dialogue-to-M4B. **Still open:** validate narrator-only default-off/no-character fallback, Unassigned Character handling, saved narrator identity and Qwen narrator/character consistency on the installed target PC and a representative book. |

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
| DS-ETA-001 | Production Studio ETA | Remaining-time estimate increased over time while elapsed time increased normally; screenshots showed 15% progress with remaining estimate moving from 22:28:45 to 22:31:01 over about 23 seconds. | Existing defect; Stage B automated checkpoint; physical acceptance remains open | The measured synthesis-call estimator, warm-up exclusion, rolling median/smoothing, timestamped countdown, native-page parity and pause/resume clock reset are covered by the accepted Stage B/full-regression gates. Historical #3198–#3200 logs are now diagnosed: missing `_now()` test-double method, cascading pause/resume assertions, one stale progress expectation and one obsolete Qwen-stage source contract. Those runs remain failures. **Still open:** target-PC long multi-chapter Qwen/Piper acceptance across warm-up, slow chunks, pause/resume and final duration. |
| DS-PROG-002 | Production Studio progress | Ring stayed at 15% during long-running synthesis; percentage, active chapter, total workload and validated chunk progress need to be truthful and readable. | Existing defect; Stage B automated checkpoint; physical acceptance remains open | The completed-normalized-text workload, active chapter/segment, validated chunk count, true 1:1 ring and separate narration/M4B packaging progress are covered by accepted #3369 and later integrated regressions, including #3470. **Still open:** observe genuine long-running Qwen/Piper generation on the target PC and confirm useful movement through slow chunks and chapter transitions. |
| DS-DURATION-003 | Production Studio duration | Show expected audiobook listening length before completion, measured audio duration as chapters complete, and authoritative full M4B duration after validation. | Existing missing capability / accuracy issue; Stage B automated checkpoint | Regression/package contracts cover the approximate text-based listening estimate, completed-chapter projection, measured chapter audio, final M4B duration and separate narration/package progress. **Still open:** compare all three against a representative full-book target-PC output and verify the final M4B duration in an independent player. |
| DS-QWEN-004 | Qwen Voice Studio | Saved Qwen profiles and CustomVoice/VoiceDesign/Clone paths must load, preview the selected identity, save and reload consistently, and not fail inside the isolated external runtime. | Older issue; hosted/provider/package gates passed; physical acceptance remains open | Provider Runtime Smoke #448 and the exact-head C4 package #3414 passed real CPU CustomVoice 0.6B/1.7B, authorized Base Clone, multilingual saved VoiceDesign reload and two-chapter Qwen character-to-M4B; D5 packaged profile round-trip and fresh-process reload also passed in #3457/#3458. **Still open:** installed target-PC save/reload, restart and real CustomVoice/VoiceDesign/Clone audition-to-generation. |
| DS-QWEN-005 | Qwen performance / hardware | 30-second preview target is under 60 seconds on supported NVIDIA hardware; CPU/AMD/Intel performance and backend reporting must be accurate and evidence-backed. | Older unmet performance goal | Runtime policy and fail-closed backend contracts are hosted-tested. Provider #448 measured 30-second CPU VoiceDesign previews in 187.318s and 336.607s; CPU did not meet the under-60-second target. **Still open:** actual NVIDIA CUDA, supported AMD ROCm and Intel XPU inference with verified synthesis-worker telemetry and no CPU fallback; 30-second saved-profile preview under 60 seconds on each supported GPU workload claimed. |
| DS-QWEN-006 | Qwen Models Center install/repair lifecycle | Install mode-specific model sets, preserve the previous working isolated runtime when repair fails, refuse destructive repair during active synthesis, retain user profiles/anchors/models on uninstall, and reload saved identities after application restart. | Hosted lifecycle/package acceptance complete; physical acceptance remains open | Build #3382 passed focused C2 lifecycle/restart 9/9, full regression 1,563/1,563 and Windows package/Defender/artifact gates. **Still open:** installed target-PC model install/repair/remove and saved-profile restart/audition across applicable modes. |
| DS-JOBS-006 | Generation job lifecycle | Pause, resume, cancel, retry, interruption, durable recovery and history must refer to the correct job and preserve valid chapter checkpoints. | Hosted regression and packaged acceptance complete; physical acceptance remains open | Build #3369 and later integrated #3470 packaged tests cover pause/resume/cancel, retry, restart/recovery, checkpoint reuse and History/project/job/output identity. **Still open:** run a long real target-PC job, interrupt/restart/recover/retry and verify ownership, no stale output and prompt cancellation. |
| DS-M4B-007 | Full-book output | Multi-chapter generation must retain all eligible text, produce a valid chaptered M4B, validate duration/metadata and play correctly. | Hosted multi-chapter package smoke passed; representative full-novel physical acceptance remains open | #3470 packaged generation/retry/recovery, chapter markers, playback/seek and two-chapter M4B/FFmpeg decode passed; Provider #448 passed two-chapter Qwen character-to-M4B. **Still open:** representative full novel on the user's selected provider/cast, complete listening, metadata/cover/duration/chapter navigation and independent playback/seek. |
| DS-CAST-008 | Narrator / character assignment | Narrator-only mode, saved narrator identity, character-cast routing and Unassigned Character handling must agree across readiness, preview and final generation. | Existing behaviour; regression risk | Revalidate explicit narrator-only toggle, default-off behaviour, no-character fallback and saved voice identity. |
| DS-UI-009 | Production Studio layout | Organize the Production Studio controls and cards; prevent cover art from being permanently watermarked/embedded into the artwork; use the selected cover as artwork only. | Source/test and hosted package acceptance complete; physical visual acceptance remains open | E3 focused layout/progress/cover-art tests passed 41/41; #3470 packaged acceptance passed. **Still open:** inspect the installed app at target sizes and verify selected user cover art is never overlaid with app watermark; confirm information hierarchy and controls remain usable. |
| DS-BRAND-010 | Logo / Windows shell | Remove opaque white/black corner backgrounds from the logo where transparency is required; ensure taskbar, shortcut and installed-app icons use the intended transparent brand asset. | Hosted source/build/hash/installer checks passed; physical shell inspection remains open | #3470 generated and hash-checked shell/logo assets and passed install/launch/upgrade/uninstall plus Defender. **Still open:** inspect actual installed shortcut/taskbar/app icon on target Windows display for opaque corner artefacts and correct identity. |
| DS-INSTALL-011 | Installer layout | Installer content was cropped at the bottom; Next/Back and details were not fully visible; unwanted black center bar/frame appeared. | Hosted installer build/startup/install checks passed; physical geometry review remains open | #3470 passed HTML/core installer creation/startup, install/launch/upgrade/uninstall, size/hash and Defender gates. **Still open:** visually inspect the actual wizard at target resolution/scaling for footer, navigation, details, centering, cropping and black frame/bar. |
| DS-AI-012 | Multilingual novel analysis | Character/dialogue analysis must handle Japanese, Chinese, Korean, accented Latin and Indian scripts without losing names or quote evidence; English stopwords must not become characters. | E1 hosted source/test/package gate complete; representative-book and historical-count reconciliation remain open | E1 passed focused multilingual/full-book coverage gates, including 150 dialogue passages across three synthetic chapters, source-grounded fallback and Unicode combining marks; #3470 passed the 1,692-test exact-head package. **Still open:** compare analysis with a representative real source book, and reconcile historic 1,175/1,196 only from the original book/revision using the same metric definitions. The legacy quote-span counter and canonical saved-passage index are distinct measures. |
| DS-RESP-013 | Responsive UI | Verify Generate and application layouts at 1280×720 and the agreed 41-viewport matrix, including mixed display scaling, ultrawide and portrait. | Hosted CSS/DOM/overlap checks passed; physical responsiveness remains open | Historical automated 41-viewport and window/scale emulation passed at #3291; later E3/#3470 integrated layout and packaged gates passed. **Still open:** physical no-flicker/no-freeze inspection, 1280×720, minimized/restored/maximized, mixed monitors, ultrawide/portrait and 100/125/150/200% DPI. |
| DS-HELP-014 | Help & Guide | Help & Guide content must describe shipped features, controls, recovery paths and actual limitations accurately. | E4 hosted accuracy/package gate complete; installed-app walkthrough remains open | E4 focused Help & Guide accuracy tests passed 8/8 and #3470 packaged Help/Guide acceptance passed with the detailed seven-stage guide preserved. **Still open:** follow the actual installed app workflows and report any mismatch between instructions and shipped controls. |


## Stage A reconciliation and Stage B continuation — 13 November 2026

### Active roadmap boundary

The active implementation plan is **A → B → C → D → E → F**. Earlier Stage 1–8 ledgers and closeouts are historical implementation/test evidence only; they are not a roadmap to restart. Preserve their accepted work and only carry forward requirements still marked open by evidence.

### Exact-head baseline reviewed

- PR #35 is open and draft on `dragon-studio/1.2.0-post-release-bugfixes`.
- Baseline HEAD: `cbb557e8c249d336bb10bc7265e2e75d1257b63c`.
- Build Windows App #3369 ([run 43268213294](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43268213294)) passed on that exact HEAD. The tests job ran **1,543 tests; OK**. The Windows package job passed the frozen-app, real two-chapter M4B, packaged Sound Design/Production, installer, install/launch/upgrade/uninstall, logo transparency/hash, package-size and Defender steps.
- Build #3367 ([run 43266926128](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43266926128)) ran 1,543 tests and failed one assertion in `test_global_background_job_heartbeat_is_adaptive_and_keeps_active_progress_fast`: the test expected a literal `BACKEND_JOB_POLL_ACTIVE_MS = 1500` assignment although the implementation exposed a derived adaptive-delay function. The failure was a stale source-contract assertion, not a runtime polling timeout.
- Build #3368 ([run 43267602787](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43267602787)) passed all 1,543 tests, then failed packaged restart acceptance at “Task Manager repairs a mismatched View action in place”. The preceding restart, recovery, playback, music/cue persistence and real M4B markers had passed. Build #3369 on the corrected exact head passed both jobs. #3367 and #3368 remain recorded failures; neither is relabelled as a pass.
- The original #3198–#3200 logs have now been retrieved by exact Actions run ID and diagnosed on 18 November 2026. All three are preserved as failures (1,489 tests; 4 failures and 1 error each). The shared failures were a missing `_now()` method in `GenerationProgressDispatchHarness` (plus two pause/resume assertions cascading from that exception), a stale narration-versus-package progress expectation, and a source contract expecting the removed `Loading voice model` stage literal. Later accepted Stage B/full-package checkpoints supersede these failures; none is relabelled as passed.

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

Exact test-job logs are now available: #3198 / [run 42981592624](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42981592624), #3199 / [run 42981608441](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42981608441), and #3200 / [run 42981638144](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42981638144). Each test job reported 1,489 tests with 4 failures and 1 error; each build job was skipped because the tests job failed. The failing error was `test_generation_progress_maps_plan_chunks_and_m4b_stages_monotonically`: the `GenerationProgressDispatchHarness` test double lacked `_now()`. The pause/resume assertions then observed incomplete chapter/checkpoint work (0 != 1 and 1 != 2). `test_generation_progress_keeps_narration_and_package_percent_separate` failed because its fixture expected a missing narration-progress field, and `test_qwen_preview_starts_at_zero_and_progress_is_completed_segment_based` asserted an obsolete source literal for `Loading voice model`. The import-worker test's `record_latest_import` ValueError was logged inside a test that still reported `ok`; it was not a suite failure. Preserve these original failed results. The later Stage B baseline #3369 and integrated #3470 package demonstrate the accepted follow-on regression state; they do not change the historical conclusions.

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

The #3198–#3200 push-run logs are now individually diagnosed as recorded in the Stage F handoff above. Their four failures and one error remain historical; the later accepted Stage B and integrated package checkpoints supersede them without rewriting those results.

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
| DS-ETA-001 | The measured timing/countdown implementation is in the tested head; full regression and packaged UI gates passed. | #3198–#3200 are diagnosed historical failures (missing `_now()` in the progress harness, cascading pause/resume assertions, stale progress expectation and obsolete Qwen-stage source contract). They remain failures; later #3369/#3470 accepted regressions supersede them. A long real generation on the target PC must still confirm the estimate remains monotonic/stable and useful during warm-up, pause, resume and slow Qwen chunks. |
| DS-PROG-002 | Exact-head UI tests and packaged 41-viewport/overlap acceptance passed. | Long-running real Qwen/Piper generation on the target PC must show truthful movement, active stage/chapter, elapsed time and validated-work progress throughout the job. |
| DS-DURATION-003 | Listening-time estimate, chapter projection and final-output measurement paths are covered by regression/package contracts; actual M4B was produced in two CI smoke paths. | Compare estimated, accumulated chapter and final measured durations against a full-book target-PC output; ensure labels do not conflate listening duration with synthesis time. |
| DS-QWEN-004 | Provider Runtime Smoke #448 passed exact-head real CustomVoice 0.6B/1.7B, authorized Base Clone, Japanese plus nine-language saved VoiceDesign reload/identity checks with unchanged anchor SHA, and two-chapter Qwen character-to-M4B. | Pass the exact-head Windows artifact checkpoint, then audition and save/reload CustomVoice, VoiceDesign and Clone in the installed app on the target PC. |
| DS-QWEN-005 | Runtime selection and hardware fallback contracts are regression-tested; dedicated real-device acceptance workflows exist. Provider #448 measured 30s CPU VoiceDesign previews at 336.607s and 187.318s on separate paths. | Not closed. CPU misses the 60s target. Need real NVIDIA CUDA, supported AMD ROCm and Intel XPU hardware evidence with actual worker telemetry and no CPU/simulated substitution. |
| DS-JOBS-006 | Pause/resume/cancel-at-checkpoint, restart recovery, retry project ownership, checkpoint integrity and terminal job/history consistency have regression coverage. | Exercise a long real packaged job, force application/OS interruption, restart, recover/retry and verify no stale output or duplicate synthesis on the target PC. |
| DS-M4B-007 | Two-chapter real Piper output passed; Provider #448 also passed real Qwen character-to-M4B with two Qwen calls, four chapter markers and FFmpeg decode. | A representative full novel using the selected target-PC provider/cast must be generated and auditioned end-to-end. Verify all expected chapters, metadata, cover, duration and playback/seek/chapter navigation. |
| DS-CAST-008 | CI real Piper cast smoke passed saved-profile round-trip, narrator vs Mira/Ren routing, same-identity reuse and no cross-series character routing. Provider #448 additionally passed exact-head saved Japanese + nine-language Qwen VoiceDesign identity reload and two-chapter Qwen character-to-M4B. | Revalidate narrator-only default-off/no-character fallback, Unassigned Character handling, saved narrator identity and Qwen narrator/character consistency on the target PC with a representative book. |
| DS-UI-009 | Packaged overlap checks and 41 viewport CSS/DOM matrix passed. | Visually inspect Production Studio information hierarchy and user-supplied cover art in the installed app; confirm no app watermark is baked into the chosen artwork. |
| DS-BRAND-010 | Build #3291 validated transparent logo alpha/corners, generated icon/installer assets, and completed install/uninstall. | Inspect actual shortcut/taskbar/installed shell icon on the target PC and confirm no opaque white/black square appears. |
| DS-INSTALL-011 | Installer window geometry tests and #3291 HTML/core installer, startup, install, upgrade and uninstall steps passed. | Inspect the actual wizard visually at the target PC's display scaling/resolution; verify footer, Next/Back, details and frame have no cropping/black center bar. |
| DS-AI-012 | Unicode NFKC/casefold source matching and English false-positive/stopword regression tests passed in the exact-head suite. | Analyze representative Japanese, Chinese and Korean novels and an accented Latin sample; compare detected names, exact quote evidence, false positives and passage counts against the source. The historic 1,175-vs-1,196 reconciliation remains OPEN: the original source book/export and exact source revision are not present in the acceptance evidence. The code has two non-equivalent metrics (`analyze_book().dialogue_total` counts quote/dash spans; the canonical passage index counts all non-narration source segments, including saved assignments and AI review spans). A Stage F synthetic regression now documents this semantic difference; it does not retroactively reconcile the original book. Recalculate both metrics from the same original book/revision before closing. |
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


## Stage C4 — Qwen multilingual voice identity and expressive continuity (exact-head CPU real acceptance passed; Windows package pending)

- Candidate branch: dragon-studio/candidate-c4-voice-identity-continuity-2026-11-13. Latest application/test head before the documentation/revalidation push: 45a0d5ee66363f3c258e1512e28347e457212027 (Build Windows App #3405).
- C4 scope: language-matched VoiceDesign identity anchors for English, Japanese, Korean, Chinese, German, French, Russian, Portuguese, Spanish and Italian; preserve a saved language instead of inferring a different one from mixed/native-script text; preserve one canonical acoustic anchor across neutral and emotional synthesis and profile reload; invalidate resumable Qwen Design chunks when the expression pipeline changes without invalidating unrelated CustomVoice chunks; maintain native-language emotion/whisper cues; exercise the real saved-profile and CastAwareProvider production routes.
- Earlier failed runs remain historical failures: #3390 exposed an obsolete regression assertion requiring ANCHOR_TEXTS although the worker had moved to a single canonical neutral anchor; #3394 exposed missing multilingual emotion forms (including German panic, French boredom, Spanish/Portuguese panic and curiosity/surprise, Italian panic and Russian anger); #3397 exposed a stale source assertion for the old v8-emotion-range-anchor after the worker had moved to v9-language-matched-anchor-direction. The #3394 cue gaps were corrected in #3395. The #3397 test contract was corrected in #3398 to assert the versioned localized cache identity rather than the obsolete version literal.
- #3399 / Provider Runtime Smoke #441 proved real CPU Japanese saved-profile VoiceDesign after reload: neutral and angry audio, explicit Japanese, Design 1.7B + Base 0.6B, actual CPU telemetry and unchanged anchor SHA. #441 also passed real CustomVoice 0.6B/1.7B, Base Clone and two-chapter Qwen character-to-M4B acceptance. The 30-second VoiceDesign preview took 229.539 seconds on CPU; this is not a performance pass.
- #3401 added expression-pipeline versioning to the Qwen Design provider/resume signatures; custom voice signatures remain unchanged. #3402 and Provider Runtime Smoke #444 then passed real neutral/angry saved-profile VoiceDesign synthesis, reload and unchanged anchor SHA for nine additional languages (English, Korean, Chinese, German, French, Russian, Portuguese, Spanish, Italian), as well as Base Clone and two-chapter Qwen character M4B. #444's 30-second preview took 241.443 seconds on CPU.
- #3403 / [run 43461070567](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43461070567) failed the focused C4 suite because the broad Portuguese trem stem classified the neutral sentence "Hoje vou de trem até o centro da cidade." as concerned. The other focused preflights passed; full regression and Windows package were correctly skipped. #3404 narrowed the pattern to Portuguese trembling verb forms; #3405 added tremor and tremedeira coverage while retaining the train-noun negative case.
- Latest Build Windows App #3410 / [run 43499302199](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43499302199) passed on exact head `6348eb0`: Stage B **16/16**, Stage 6 **48/48**, C1 **10/10**, C2 **9/9**, C3 **8/8**, C4 **37/37**, full regression **1,595/1,595**. Windows packaging was skipped because this commit did not carry [artifact-checkpoint].
- Provider Runtime Smoke #448 / [run 43499302368](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43499302368) completed successfully on the same exact SHA. It passed real CPU VoiceDesign, CustomVoice 0.6B/1.7B, Base Clone, Japanese saved identity, nine additional saved languages and two-chapter Qwen character-to-M4B; three evidence archives were uploaded.
- Exact-head CPU functional/identity acceptance is passed. The 30-second VoiceDesign preview paths took **336.607s** and **187.318s** on CPU; the <60-second target remains unmet and requires actual supported GPU evidence.
- **#3411/#3412 diagnosis:** both full test jobs passed, but Windows packaging failed at the late HTML Python restore with `Command failed: pip cache dir`. CI commit #3386 had enabled pip cache on the third setup-python call; the preceding successful #3385 restore had no cache. The correction removes cache only from that late restore and adds a source-contract regression test. #3411/#3412 remain historical failures.
- C4 hosted closure boundary: the exact-head real CPU provider gate is passed at #448; C4 remains open until the Windows artifact checkpoint on the accumulated candidate passes the full regression, frozen-app, installer, install/launch/upgrade/uninstall, user-data, transparency/hash, package-size, Defender and artifact-upload gates. Installed-app/target-PC auditions, physical GPU acceptance and representative full-novel generation remain separate open requirements. Do not infer a full-novel result from the two-chapter fixture.

- **Next:** validate the workflow correction on the exact candidate head with the complete regression suite and full Windows package gates. Do not accept success until HTML-installer build/startup, install/launch/upgrade/uninstall, logo/hash, package-size, Defender and all expected artifacts pass. Keep installed-PC, physical GPU and representative full-novel acceptance open.


## Stage C hosted closeout update — Build Windows App #3413/#3414 (14 November 2026)

- **Corrected Windows package acceptance is now passed.** #3413 / run 43567790011 passed on workflow-fix commit 88b1c55bed87a7adc77cf7e4d2769cd90811e2f7; #3414 / run 43567794677 passed on exact candidate commit 1ab7c27ead88e55df644f703c339bc608bfef897. Both tests and build jobs completed successfully.
- On #3414: Stage B 16/16, Stage 6 48/48, C1 10/10, C2 9/9, C3 8/8, C4 37/37, and full regression 1,596/1,596. The added guard against restoring pip cache on the late HTML-installer Python setup passed.
- #3414 package gates passed through frozen-app verification, real bundled-Piper multi-chapter M4B, packaged Sound Design/Music Library, core and HTML installers, HTML UI startup, hosted install/launch/upgrade/uninstall, logo transparency/hash, package-size, Defender and artifact uploads. Installer artifact 14103528384 (847,025,536 bytes); portable 14103967421 (1,190,866,285 bytes); SHA/package manifest 14103383915; M4B 14102583924.
- PR #35 tracking branch dragon-studio/1.2.0-post-release-bugfixes was fast-forwarded from expected old HEAD 65adc53da81e8faeca09bc50cf4f21f663cc5138 to 1ab7c27ead88e55df644f703c339bc608bfef897. Compare verified the new candidate was 39 commits ahead / 0 behind before promotion. PR #35 remains open and draft, not merged or release-published.
- **Stage C is not fully closed.** C1/C2 hosted gates are passed but installed target-PC profile audition/repair/restart checks remain. C3 physical NVIDIA CUDA / AMD ROCm / Intel XPU inference and the relevant under-60-second 30-second preview targets remain open. C4 installed-app voice identity/narrator-cast checks and representative full-novel Qwen generation/playback remain open. Long real-generation progress/ETA/duration, interruption recovery, physical DPI/multi-monitor, shell icon/installer visual and final Help & Guide checks also remain open.
- The #3414 package checkpoint is not a final Stage 8 sign-off or a release publication. Do not start Stage D until the outstanding Stage C manual/hardware/full-book acceptance is recorded with evidence. No CPU fallback, hosted CI result or two-chapter fixture closes those requirements.



## Stage D engineering closeout and Stage E handoff — 15 November 2026

### Exact hosted/package evidence

- **Build #3457** / [run 43696836352](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43696836352), exact SHA `fbed26a0beadd5ebe845173f8e2e059668248d8c`: tests and Windows build passed; D3 21/21, D4 22/22, D5 contract 3/3, path security 10/10, full regression 1,681/1,681; packaged CustomVoice/VoiceDesign/Clone export → preflight → transactional import, two asset hashes and fresh-process reload passed.
- **Build #3458** / [run 43699897254](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43699897254), same exact SHA `fbed26a0beadd5ebe845173f8e2e059668248d8c`: both tests and Windows package passed again; installer, portable, SHA manifest, M4B and Piper benchmark artifacts uploaded.
- **Build #3459** / [run 43700613272](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43700613272), documentation commit `e3dd1259453f04d3d9dc9f19062cbbe6cc8b66f8`: tests and full regression **1,681/1,681** passed; build skipped because the change was documentation-only.
- **Build #3460** / [run 43700894123](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43700894123), documentation commit `6d970bf70911848c90bcb178b1a166a10bf8305d`: tests and full regression **1,681/1,681** passed; build skipped because the change was documentation-only.

### Stage D disposition

**D0–D5 hosted engineering/package acceptance is complete. D6 physical acceptance is NOT PASSED and is deferred to Stage F by user direction.** Stage D is closed as the current engineering workstream; physical acceptance remains an explicit final gate.

### Stage E scope

- Active branch: `dragon-studio/stage-e-character-intelligence-cast-production-ux-2026-11-15`.
- Base SHA: `6d970bf70911848c90bcb178b1a166a10bf8305d`.
- Charter: [STAGE-E-CHARACTER-INTELLIGENCE-AND-PRODUCTION-UX-PLAN.md](STAGE-E-CHARACTER-INTELLIGENCE-AND-PRODUCTION-UX-PLAN.md).
- Included IDs: DS-AI-012, DS-CAST-008, DS-UI-009 and DS-HELP-014.
- First audit gap: Indian-script speaker labels with combining marks are not represented in the existing multilingual fixtures; `SPEAKER_NAME_TOKEN` uses Python `\w`, which excludes Unicode mark categories. Add the regression first and validate the full analyzer before selecting the narrowest correction.
- Preserve Stage C/D accepted behavior. Hardware, installed-app and real-listening checks remain open for Stage F.

### Stage F disposition

Stage F will consolidate D6 two-PC transfer/audition, saved Qwen profile/device acceptance, real long-book generation/playback/recovery, physical display/DPI/flicker, shell icon and installer visual checks, and final Help & Guide user review. These checks must run after engineering stages are complete and cannot be replaced by CI simulation.
 
## Stage E1–E4 source/test gates and E5 package handoff — 15 November 2026

- Active branch: dragon-studio/stage-e-character-intelligence-cast-production-ux-2026-11-15.
- Exact tested head before the package checkpoint: a99786938d98004ceb1df91d603d31d05babd858.
- **E1 — 40/40** focused character analysis; multilingual Indian-script names with combining marks, source-grounded fallback, full-book coverage (150 passages / three chapters) and cancellation-before-commit contracts passed.
- **E2 — 181/181** focused Production-preview/cast-routing tests; same-name characters remain series-scoped, exact saved chapter dialogue assignments are forwarded, and unresolved dialogue uses the global Unassigned Character profile.
- **E3 — 41/41** focused Production layout/progress/cover-art tests passed; real selected cover and empty placeholder branding remain separate.
- **E4 — 8/8** Help & Guide accuracy tests passed; the original detailed seven-stage guide remains preserved.
- **Build #3469** / [run 43710739978](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43710739978), head a99786938d98004ceb1df91d603d31d05babd858: full regression 1,692/1,692 and all E1–E4 focused gates passed. Build job was skipped because it was not an explicit artifact checkpoint.
- **Historical failures preserved:** #3465 / run 43709432289 and #3466 / run 43709542835 failed full regression while preview-routing test fixtures/contracts were stale after the shared-router change. #3467 / run 43709935729 failed the E2 focused step due a Python syntax error in an escaped test literal. #3468 / run 43710004680 corrected those literals; #3469 passed the complete E1–E4 test gate. The failures remain failures in Actions history.
- **E5 is COMPLETE:** Build #3470 / [run 43714021829](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43714021829), exact head `fc3a0f8`, passed the full 1,692-test regression and both Windows package jobs, including frozen app, D5 round-trip, installer/portable, install/launch/upgrade/uninstall, Defender and SHA-256/artifact upload.
- **Stage F is now ACTIVE:** all physical/user-dependent checks remain NOT RUN until performed on the actual Windows systems. The non-physical tooling/documentation tests do not mark any physical F1–F5 item passed.


## Stage A–E engineering closeout and Stage F handoff — 15 November 2026

### Stage F non-physical preparation and historical evidence update — 18 November 2026

- The Stage F branch now includes `scripts/stage_f_capture_environment.ps1`, `tests/test_stage_f_acceptance_tools.py`, and `docs/dragon-studio/STAGE-F-USER-CHECKLIST.md` alongside the controlling Stage F plan.
- The capture tool is privacy-minimized: it records OS/CPU/GPU/memory/display inventory and SHA-256/byte-size for files explicitly supplied by the user, but omits account/machine/network identifiers, paths, file names and audio contents. Its output explicitly says hardware inventory is not inference/backend proof.
- The new test documents that `analyze_book().dialogue_total` counts quote/dash spans, whereas the canonical passage index counts all non-narration source segments including saved dialogue assignments. This explains why raw 1,175/1,196 totals cannot be compared without the same original book, revision and metric definition; the original source book/export is not retained in the current record, so the historical discrepancy remains open.
- Historical Stage B runs #3198–#3200 are now individually diagnosed from their test-job logs. They remain failed in Actions history; later accepted Stage B and #3470 package checkpoints supersede their implementation/test state without rewriting those failures.
- Stage F is a user-device acceptance stage. The non-physical tooling/documentation tests do not mark any physical F1–F5 item passed.

This section is the current A–F status overlay. It does not erase or rewrite the historical Build/PR failures recorded above, and it does not restart the earlier Stage 1–8 implementation history.

| Stage | Hosted/source engineering status | Physical acceptance disposition |
|---|---|---|
| A — baseline and scope reconciliation | COMPLETE. The A/B continuation preserved the accepted Stage 1–8 history and established one A→F bug-fix sequence. | No separate A-only physical gate; related real-device checks are consolidated into F. |
| B — measured generation progress, ETA and duration | COMPLETE as hosted/source/package engineering. Build #3369 passed 1,543 tests and the Windows package; later exact-head pipelines continue to exercise its regression gates. | Long real multi-chapter Qwen/Piper timing, progress movement, ETA countdown and final duration comparison remain Stage F. |
| C — Qwen identity, lifecycle, accelerator policy and multilingual continuity | COMPLETE as hosted/source/provider/package engineering. Stage C main accepted the integrated hosted baseline at Build #3420; C1–C4 gates and the #3414 exact-head package are recorded in the C ledgers. Provider Runtime Smoke #448 proves CPU functional identity paths only. | Real NVIDIA CUDA, AMD ROCm, Intel XPU and target-PC save/reload/audition/performance remain Stage F. The CPU 30-second VoiceDesign runs (187.318s and 336.607s) did not meet the under-60s target and are not GPU evidence. |
| D — portable Qwen Voice Library | D0–D5 COMPLETE as hosted engineering/package work. D5 exact-head package #3457 on fbed26a passed, and #3458 repeated the package checkpoint. #3459/#3460 documentation validations passed. | D6 two-physical-PC transfer, compatibility, fresh restart and CustomVoice/VoiceDesign/Clone auditions remain deferred to F and NOT PASSED. |
| E — multilingual Character Studio, cast parity, Production UX, Help & Guide | E0–E5 COMPLETE. Build #3469 passed E1 40/40, E2 181/181, E3 41/41, E4 8/8 and 1,692/1,692; exact-head Build #3470 on fc3a0f8 passed 1,692/1,692 and both Windows package jobs. | Physical UI smoothness, representative real-book quality, target-device voice continuity and Help & Guide walkthrough are Stage F. |
| F — final physical/manual acceptance | ACTIVE — plan and evidence baseline established on dragon-studio/stage-f-physical-final-acceptance-2026-11-15. | All physical checklist rows begin as NOT RUN. Close only with evidence from the actual target devices. |

### Build #3470 exact-head evidence

- Run: [Build Windows App #3470](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43714021829); run ID 43714021829; exact head fc3a0f8e1d64790b1a61024f8d883653b2dad51c.
- Both workflow jobs passed. The full regression reported **1,692 tests, OK**. The Stage B, Stage 6, C1–C4, D3/D4/D5 and E1/E2/E3/E4 focused workflow steps all completed successfully.
- Packaged evidence included the real two-chapter Piper M4B/FFmpeg decode, Stage 5.4 generation/retry/restart recovery, Stage D5 CustomVoice/VoiceDesign/Clone bundle round-trip with fresh-process reload, narrator-only full-book generation, embedded M4B chapters and player seek/restart.
- Windows installer and portable package creation, install/launch/upgrade/uninstall, shell/logo/hash checks, package-size report and three Microsoft Defender scans passed. Defender reported no threats for the application, HTML installer and core installer. Candidate release publication was intentionally skipped.
- Artifacts: installer 14162537175; portable 14163025967; SHA-256 manifest 14162528273; real multi-chapter M4B 14162070795; Piper benchmark 14162867421. GitHub retention expiry is 15 December 2026. Candidate release publication was intentionally skipped.

### Stage F guardrails

1. Do not rerun or reopen completed Stage A–E implementation without a reproducible regression. A physical check that fails creates a targeted follow-up defect; it does not invalidate unrelated accepted stages.
2. Never represent hosted CPU, mocked hardware, viewport emulation or a second process on one PC as physical GPU, multi-monitor or two-PC acceptance.
3. Record exact app build/SHA, machine label, OS, CPU/GPU/RAM/VRAM, model/runtime versions, resolved inference backend, input/output duration, timings and hashes as applicable. Do not include personal account names, serial numbers or private voice recordings in public evidence.
4. A requested GPU result passes only when synthesis telemetry proves the actual backend; silent CPU fallback is a failure of that backend-specific test.
5. Preserve every failed attempt and root cause. After a code correction, run focused tests, full regression and an exact-head Windows package before repeating the affected physical gate.
6. Stage F completion and Version 1.2.0 publication are separate decisions. Do not publish or claim final release acceptance without explicit owner approval.

The controlling documents are [STAGE-F-PHYSICAL-FINAL-ACCEPTANCE-PLAN.md](STAGE-F-PHYSICAL-FINAL-ACCEPTANCE-PLAN.md), [STAGE-F-USER-CHECKLIST.md](STAGE-F-USER-CHECKLIST.md) and [STAGE-D6-TWO-PC-TRANSFER-ACCEPTANCE.md](STAGE-D6-TWO-PC-TRANSFER-ACCEPTANCE.md). D6 remains NOT RUN and must be completed only on two separate physical PCs.
