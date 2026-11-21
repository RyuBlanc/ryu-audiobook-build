# Stage F — Final Physical and Manual Acceptance

**Stage:** F — final physical/manual acceptance and release-readiness evidence  
**Repository:** RyuBlanc/ryu-audiobook-build  
**Branch:** dragon-studio/stage-f-multilingual-context-aware-tts-2026-11-21  
**Engineering baseline:** Stage A–E hosted/source engineering and Stage F UI-reliability follow-up package Build #3497 / [run 44795887496](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/44795887496), commit cee26183af700ad9bafb17c7fcaea887207d4a72.  
**Status:** ACTIVE — Build #3533 exact-head regression passed; a new Windows artifact checkpoint is being created. F1 is deferred by product decision, F2 is hardware-constrained, and F3–F5 include user-reported outcomes recorded separately from independently verified evidence.

## 1. Purpose and boundary

Stage F consolidates the physical checks deliberately deferred from Stages B, C and D, plus the remaining installed-app, full-book, UI, installer and user-review checks. It is not permission to rebuild or repeat accepted Stage A–E work. Its purpose is to verify that the accepted code and exact Windows package behave correctly on the actual target machines and with real saved profiles, models, audio and displays.

The user explicitly requested that physical tests requiring their participation be deferred until engineering stages were complete. Stages A–E have now reached their hosted engineering/package exit criteria. Stage F is therefore the active handoff, but no physical test has been performed or marked passed by this document.

## 2. F0 — Non-physical engineering preparation

**Disposition:** source/docs/tooling preparation only. No physical PC, GPU, two-PC transfer, audio audition or visual acceptance is performed by this preparation.

The following assets are part of the Stage F preparation checkpoint:

- `scripts/stage_f_capture_environment.ps1` records privacy-minimized Windows environment metadata and SHA-256/size evidence for explicitly supplied files. It still pins the historical Build #3497 application, HTML installer and core installer hashes; **do not use it to validate a newer package until its baseline hashes are updated from that package's manifest**.
- `tests/test_stage_f_acceptance_tools.py` protects the pinned baseline, privacy exclusions, the rule that device discovery is not inference evidence, and the distinction between the legacy quote-span count and the canonical source-position passage index. Its Windows PowerShell integration test runs in the hosted Windows regression suite.
- [STAGE-F-USER-CHECKLIST.md](STAGE-F-USER-CHECKLIST.md) gives the physical sequence and the commands for collecting PC-A/PC-B evidence.

The capture tool does not capture or upload audio contents, profile names, filenames, absolute paths, account names, machine identifiers, serial numbers or network identifiers. For supplied files it records only their role, byte size and SHA-256. GPU utility presence and WMI adapter information are inventory only; neither is evidence of the backend selected by a synthesis worker.

### Historical Stage B failure diagnosis

The original Build Windows App failures #3198, #3199 and #3200 have now been traced to their exact Actions logs. All three remain historical failures: each ran 1,489 tests and ended with **4 failures and 1 error**. The shared causes were a progress test harness missing the production clock method `_now()` (which caused the two pause/resume assertions to cascade), a stale narration-versus-packaging progress expectation, and a source assertion that still expected the removed `Loading voice model` stage literal. The import-worker fixture also logged a `record_latest_import` ValueError while its test itself passed; that warning was not one of the five suite failures. Later Stage B and integrated checkpoints supersede these failures; this diagnosis does not relabel them as passed.

### DS-AI-012 passage-count reconciliation boundary

The historic 1,175-versus-1,196 figures cannot be reconciled from the repository alone because the original source book/export and the exact source revision used for both totals are not retained in the acceptance record. The implementation has two different measures: the legacy character analyzer's `dialogue_total` counts quote/dash spans, while the canonical passage index counts all non-narration source segments, including saved assignments and exact-source AI review spans. The new deterministic test demonstrates why those totals are not interchangeable. This is a metric-definition/source-evidence issue, not proof that either historical total is correct. Stage F must use the same source book/revision and report both metric definitions before comparing counts.

## 3. Historical hosted baseline — Build #3470 (superseded)

- Exact commit: fc3a0f8e1d64790b1a61024f8d883653b2dad51c.
- Actions: [Build Windows App #3470](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43714021829), run ID 43714021829.
- Jobs: tests = success; build = success.
- Regression: **1,692/1,692**.
- Installer artifact: Ryu-Audiobook-Installer-3470, ID 14162537175, 847,380,138 bytes.
- Portable artifact: Ryu-Audiobook-Portable-3470, ID 14163025967, 1,191,837,669 bytes.
- SHA-256 manifest: Ryu-Audiobook-Release-SHA256-3470, ID 14162528273, 3,049 bytes.
- Real two-chapter M4B evidence: ID 14162070795, 9,033,841 bytes.
- Stage 7 Piper benchmark evidence: ID 14162867421, 805 bytes.
- Artifacts are retained until **15 December 2026** according to the Actions API. Download and preserve the installer, portable package and manifest before expiry.

Build #3470 passed frozen-app verification, bundled voice assets/modules, real bundled-Piper multi-chapter M4B and FFmpeg decode, packaged Sound Design/Production acceptance, Stage D5 three-profile export/preflight/import and fresh-process reload, narrator-only full-book generation, retry/restart recovery, chaptered M4B playback/seek, installer creation/startup, install/launch/upgrade/uninstall, logo/hash checks, size reporting, Defender scans and artifact uploads. Defender reported no threats for the app, HTML installer or core installer. Public release publication was skipped by design.

This is hosted package evidence, not physical PC, GPU or acoustic sign-off.

## 3B. Current speech-integrity source checkpoint — Build #3533

- **Exact source commit:** `350ec3d9c91aa95220c7d1cce890fff7c97f6ec1`.
- **Branch:** `dragon-studio/stage-f-multilingual-context-aware-tts-2026-11-21`.
- **Actions:** [Build Windows App #3533](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/44903985035), run ID 44903985035; **tests SUCCESS**.
- **Regression result:** **1,746/1,746 passed**; all 25 workflow steps in the test job completed successfully. The Windows `build` job was skipped because this source commit was not an artifact checkpoint.
- **Speech-integrity implementation in this source:** single-output Qwen CustomVoice, VoiceDesign, one-pass VoiceDesign preview, direct Base Clone, saved VoiceDesign/Base production, reusable anchors and silent members of batch requests now get a one-time retry with the same selected model, speaker/profile identity, voice prompt and delivery style. Only the seed changes. A second silent result fails closed. Silent saved identity anchors are not reused from cache. Preview and audiobook chunk validation also reject entirely silent Qwen WAVs.
- **Pacing and expression:** the previous #3530 source already preserves the `yes.. then what` hesitation as a separate unit with a 540 ms pause and adds explicit joyful/suspicious delivery labels without changing the single saved acoustic identity anchor. Joyful sampling remains below the existing 0.80 CustomVoice bound.
- **Resolved intermediate CI attempts:** #3527 failed on a missing Python function-signature colon; #3528/#3529 exposed the shared-anchor test expectation and the 0.80 sampling boundary. #3530 passed 1,744 tests after those corrections. #3531 later found a lightweight test requiring an unavailable PyTorch import; the seed setter was isolated in the test. The separate hosted-CPU protocol smoke also rejected a deliberately silent fake waveform; that fixture now supplies non-zero synthetic audio, while the production silence guard remains enabled.
- **Hosted CPU comparison:** [Stage 7 Qwen Real CPU Preview #54](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/44903985064) is running against this exact source head. Its actual 30-second CPU preview has not yet been recorded as passed at the time of this checkpoint. This comparison is not NVIDIA/AMD/Intel physical-hardware evidence.
- **Package disposition:** no installer or portable artifact has been produced from #3533. This checkpoint is intended to run the exact-head Windows package workflow; after it completes, record the resulting installer/portable artifact IDs and verify the release hash manifest before changing the capture script baseline.

**Acceptance boundary:** the signal-level guard detects an entirely silent/near-silent Qwen segment or batch item. It does not prove that every word in an otherwise audible multi-sentence segment was spoken. The remaining acoustic check must listen to the user's saved VoiceDesign profile and a representative book, paying particular attention to missing sentences, pronunciation, natural hesitations and emotional delivery. No ASR/forced-alignment gate is claimed here.

## 3A. Current exact-head follow-up package — Build #3497

- Exact source commit: `cee26183af700ad9bafb17c7fcaea887207d4a72` (artifact-checkpoint commit; application source tree is the tested #3496 tree).
- Branch: `dragon-studio/stage-f-ui-reliability-followup-2026-11-20`.
- Actions: [Build Windows App #3497](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/44795887496), run ID 44795887496; overall conclusion SUCCESS.
- Test job: SUCCESS. Frontend JavaScript syntax, native Qt lifecycle, focused Stage B–D regressions, Stage E1–E4 acceptance and the full regression suite all passed. Full suite: **1,718/1,718**.
- Build job: SUCCESS. Frozen app verification, bundled voice assets/modules, real bundled-Piper multi-chapter M4B acceptance, packaged Sound Design/Production acceptance, functional installer startup, install/launch/upgrade/uninstall, logo/hash checks, Microsoft Defender scan step and artifact uploads all passed.
- Installer artifact: [Ryu-Audiobook-Installer-3497](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/44795887496/artifacts/14659354996), artifact ID 14659354996; 847,661,430 bytes (Actions artifact ZIP).
- Portable artifact: [Ryu-Audiobook-Portable-3497](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/44795887496/artifacts/14661421253), artifact ID 14661421253; 1,191,901,157 bytes (Actions artifact ZIP).
- SHA-256 manifest and package-size report: [Ryu-Audiobook-Release-SHA256-3497](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/44795887496/artifacts/14661900012), artifact ID 14661900012.
- Real multi-chapter M4B evidence: [artifact 14659122243](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/44795887496/artifacts/14659122243).
- Stage 7 Piper benchmark evidence: [artifact 14661475891](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/44795887496/artifacts/14661475891).
- Artifacts expire **20 December 2026** according to the Actions API. Download and preserve the installer, portable package, manifest and M4B evidence before expiry.
- Binary SHA-256 values pinned by the PC capture tool: app `c82a61fbf3927f334fcab0eb033aca5ce7c0fa7394a97a63994393259bcb574d`; HTML installer `5626423f680fc45a06a6c8ccbdc41867cd3758b59851b081c7738994a470c48a`; core installer `98f9adf51e24421561b741a85d2ea7c1aa7748bad04f2abf313db22e01f9ce66`.

Build #3497 replaced #3470 as the package baseline at the time of its checkpoint; it is now a historical package, not the current source head. The #3533 source regression checkpoint is newer, but it has not yet produced its own Windows package. User-reported F3/F4/F5 outcomes and the F1/F2 scope decisions are recorded in Sections 5–9 below. The public release publication step was skipped by design; Actions artifacts are not a published stable release.

## 4. Stage A–F status at handoff

| Stage | Engineering disposition | Physical disposition |
|---|---|---|
| A — baseline/reconciliation | Complete | Relevant real-device checks consolidated into F |
| B — truthful progress/ETA/duration | Hosted source, regression and package work complete | User reports current audiobook generation works; the long-book quality/listening check remains distinct |
| C — Qwen identity/lifecycle/accelerator/multilingual | C1–C4 hosted engineering/provider gates complete; speech-integrity retry hardening passes #3533 regression | CPU comparison #54 running; other-vendor GPU hardware unavailable per user; current saved-profile acoustic audition remains open |
| D — Voice Library/profile portability | D0–D5 hosted engineering/package complete | D6 profile transfer deferred to the next Voice Studio version because the current version has no import option |
| E — character intelligence/cast/Production/Help | E0–E5 hosted source/test gates complete | User reports the application UI is working; latest custom cursor is user-confirmed working |
| F — physical/manual acceptance | Active; exact-head package checkpoint pending | F3 generation, F4 UI and F5 installation are user-reported outcomes; exact #3533 package installation and saved-profile listening remain outstanding |

## 5. F1 — Real two-PC profile transfer (D6)

**Status: DEFERRED — next Voice Studio version (user decision, 21 November 2026).** The current shipped UI does not expose the required profile import flow. Do not treat two-PC import/transfer as a current-version defect or ask the user to perform an unavailable workflow. Keep [STAGE-D6-TWO-PC-TRANSFER-ACCEPTANCE.md](STAGE-D6-TWO-PC-TRANSFER-ACCEPTANCE.md) as future-version acceptance criteria. When the next Voice Studio version implements import, re-open D6 and execute the full two-PC transfer and fresh-process reload. The future criteria require:

1. PC-A and PC-B to be two separate physical Windows PCs using the same accepted Build #3497 artifact/source SHA where possible.
2. Real saved CustomVoice, VoiceDesign and authorized Clone profiles selected on PC-A; export one .ryuvoice bundle without altering the source catalogue.
3. Matching PC-A/PC-B bundle SHA-256, compatible-model preflight, exact stable profile IDs and voice-defining configuration parity.
4. SHA-256 verification for each VoiceDesign anchor and Clone reference asset; additive import without overwriting destination profiles.
5. A real close/relaunch on PC-B and fresh-process identity/asset reload.
6. Controlled CustomVoice, VoiceDesign and Clone audition on both PCs using matched text, profile/model settings and recorded actual backends.

A same-PC second process or CI fixture cannot pass D6. A missing model on PC-B must be reported honestly; do not remove a working model simply to manufacture a negative test.

## 6. F2 — Qwen device selection, real inference and performance

**Status: HARDWARE-CONSTRAINED — not passed in this checkpoint.** The user reports no AMD/Intel GPU hardware is available for those tests. Do not simulate or label hosted CPU as accelerator proof. The formal matrix remains in [STAGE-C3-QWEN-ACCELERATOR-ACCEPTANCE.md](STAGE-C3-QWEN-ACCELERATOR-ACCEPTANCE.md). The hosted CPU comparison #54 is running separately and only supplies CPU timing/functional evidence; any available NVIDIA saved-profile test must still record actual worker backend/device telemetry.

| Device/workload | Required physical proof | Target/disposition |
|---|---|---|
| NVIDIA CUDA with 7 GiB+ usable VRAM | Actual CUDA-enabled runtime plus worker-reported CUDA device during warmed VoiceDesign 1.7B + exact Base pairing | 30-second decoded preview in under 60 seconds; no CPU fallback |
| Lower-memory NVIDIA tier, including 4 GiB where loadable | Real 0.6B CustomVoice saved-profile preview and backend telemetry | 30-second preview under 60 seconds where supported; report exact limits if it cannot load |
| AMD ROCm | HIP-enabled runtime and actual worker telemetry on supported AMD hardware | Test only if supported runtime/hardware is present; never label CPU output as ROCm |
| Intel XPU | XPU-enabled runtime and actual worker telemetry on supported Intel hardware | Test only if supported runtime/hardware is present |
| CPU | Functional comparison, accurate backend identity and timing | CPU functional pass does not satisfy the GPU speed target |

For each available device test the 0.6B/1.7B selector and the applicable CustomVoice, VoiceDesign and Clone paths, including saved profile preview, save/reload, restart and production use. Record cold start and warmed inference separately, requested/decoded duration, elapsed synthesis time, model revision, driver/runtime versions, actual backend/device and memory use. User timing targets: approximately 10 seconds of preview within 20 seconds and 30 seconds of preview in under 60 seconds on supported accelerated hardware. A detection result or model download is not inference acceptance.

The exact-head CPU evidence from Provider Runtime Smoke #448 produced 30-second VoiceDesign previews in 187.318 and 336.607 seconds. The log explicitly marked the CPU under-60-second goal NOT MET. These CPU timings must not be rewritten as GPU evidence or used to claim the target has passed.

## 7. F3 — Installed-app voice identity and full-book production

**Status: PARTIALLY USER-REPORTED — audiobook generation is working.** This records the user's report, not an independently measured full-book listening result. The saved VoiceDesign speech-quality follow-up remains open until the exact packaged candidate is auditioned with the user's existing profile and a representative book. In particular, listen for missing sentences inside otherwise audible chunks, pronunciation, hesitation pauses and emotional delivery. CI's silent-segment checks do not prove word-level coverage.

- Install and launch the exact #3497 candidate; record version/SHA and target environment. Verify saved Qwen models/profile identity after restart and after model install/repair actions where applicable.
- Exercise CustomVoice, VoiceDesign and authorized Clone previews and ensure the selected profile/model/voice reaches the actual synthesis worker. Record the actual backend; no silent CPU/model substitution during GPU acceptance.
- Analyse a representative Japanese/Korean/Indian-language/English book as applicable. Review source-grounded character names, aliases and dialogue assignments across the full chapter set; check false positives and later-chapter coverage.
- Verify narrator-only is a real explicit setting with default OFF when cast selection is available; verify the valid saved narrator fallback for a book with no valid character voice profiles; verify series-scoped same-name characters and global Unassigned Character routing.
- Generate a representative multi-chapter/full-book audiobook. Record total input chapters/passages, eligible/skipped chapters, generated audio duration, elapsed time, progress, ETA revisions, validated chunks, model/provider/backend and errors.
- During a controlled run, test pause/resume, cancel, retry, process interruption/restart and recovery. Confirm the correct job owns the output, valid completed chunks are reused, stale output is never attached, and cancellation stops the intended work promptly.
- Validate the final M4B in an independent supported player: chapter titles/order/markers, duration, metadata, author, cover, audio decode, seek, playback and main/mini-player state. Listen for narrator/character identity continuity, pronunciation, missing/duplicated text, clipping, silence and sound-design transitions.

## 8. F4 — UI responsiveness, stability and display matrix

**Status: USER-REPORTED WORKING (21 November 2026).** The user confirms the current application UI is working and the custom cursor issue is sorted. Do not reopen dropdown, layout or cursor fixes without a reproduced regression. This user confirmation is separate from a complete independently captured 41-viewport/multi-monitor physical report; retain that matrix as a separate evidence item if formal display sign-off is required.

Inspect all 15 application destinations with the installed app, including rapid module switching and repeated open/close. Record launch time, navigation delay, stalls, unresponsive controls, rendering flicker, crashes and diagnostic logs. Confirm progress/ETA remain truthful during long-running generation and the cancel action responds promptly.

Run the responsive matrix across these aspect ratios: 4:3, 5:4, 3:2, 16:10, 16:9, 21:9, 32:9 and portrait. Include at least 1280×720, common laptop/desktop sizes, restored/maximized/minimized, split-screen, ultrawide, portrait, mixed-monitor arrangements and 100%, 125%, 150% and 200% display scaling. Check clipped text, overlapping controls, inaccessible actions, excessive/nested scrolling, scroll jumps and dialogs that extend beyond the viewport. Retain the agreed 41-viewport automated matrix as a separate CI result, not as a substitute for these observations.

## 9. F5 — Windows installer, shell identity and Help & Guide

**Status: USER-REPORTED INSTALLATION COMPLETED.** The user has completed an installation walkthrough on an earlier candidate. The #3533 exact-head source has not yet produced an installer; after the new artifact checkpoint, install and verify that exact package before marking the new package's F5 acceptance passed. #3497's previous installer/startup/install/upgrade/uninstall and Defender checks remain historical evidence only.

- Install the exact candidate on a clean or controlled target Windows environment; verify first launch, app shortcut, taskbar identity, multi-size icon and transparent logo edges/corners.
- Inspect the actual installer wizard at the target display size/scaling: full footer, Next/Back controls, details, progress, window centering, no cropped content and no unwanted black center bar/frame.
- Verify upgrades preserve user projects, models, profiles and saved output. Verify uninstall behaviour preserves user data where specified.
- Open Help & Guide in the installed application; follow import, chapter, voice/profile, character, pronunciation, Sound Design, generation/recovery, playback, model and troubleshooting instructions. Confirm wording matches the actual controls and clearly labels unsupported/deferred features.

## 10. Failure handling and release gate

If any physical item fails, record the exact build SHA, machine label, reproducible steps, expected/actual result, logs/screenshots/audio evidence and affected stable bug ID. Do not relabel it as a successful test. Reopen only the specific affected implementation; preserve completed unrelated Stage A–E work. The correction must receive focused tests, full regression and an exact-head Windows package before the affected physical check is repeated.

Stage F closes only when every applicable physical row is either PASS with evidence or explicitly approved as a documented exception. Unsupported device/backend combinations remain NOT SUPPORTED/NOT RUN, not passed. Version 1.2.0 publication and final release sign-off are separate and require explicit owner approval after this ledger is complete.

## 11. Evidence capture and handling

Run `scripts/stage_f_capture_environment.ps1` on PC-A and PC-B before the matching physical tasks. The tool's JSON is a supporting environment/hash record only. For a backend-specific Qwen PASS, retain the application's real synthesis worker diagnostic showing the resolved device/backend during the actual preview. Record audio durations and elapsed time separately.

Keep the source `.ryuvoice` bundle, imported-asset hashes, local listening notes and any private audio evidence under the user's control. Public GitHub records should contain only the non-sensitive machine labels (PC-A/PC-B), build SHA, test state, model/backend details as appropriate, timings and hashes. Do not publish recordings, account names, machine identifiers or local file paths.

The step-by-step user sequence is in [STAGE-F-USER-CHECKLIST.md](STAGE-F-USER-CHECKLIST.md).

## 12. Current checklist

| Check | Status |
|---|---|
| Historical Build #3470 hosted baseline | SUPERSEDED |
| Historical Build #3497 exact-head Windows package | PASS — historical installer/portable artifacts; 1,718/1,718 regressions |
| Build #3533 exact-head source regression | PASS — 1,746/1,746; Windows package job skipped |
| New #3533 exact-head Windows installer/portable package | CHECKPOINT REQUESTED — artifact IDs and hashes pending |
| D6 PC-A → PC-B real transfer | DEFERRED — next Voice Studio version; current import option is unavailable |
| Other-vendor AMD ROCm / Intel XPU physical testing | NOT AVAILABLE — user reports no corresponding hardware |
| NVIDIA saved-profile inference/performance | NOT RE-VERIFIED in this checkpoint; require actual worker telemetry |
| Hosted CPU 1.7B VoiceDesign comparison | IN PROGRESS — run #54; not GPU evidence |
| User's saved VoiceDesign acoustic audition | OPEN — listen for omissions, pauses, pronunciation and emotion |
| Representative full-book generation/listening | USER REPORT: generation works; acoustic/listening evidence still open |
| Physical pause/resume/cancel/recovery | NOT independently evidenced in this checkpoint |
| Real progress/ETA/duration observation | User reports current generation works; separate long-duration observation remains open |
| Physical responsive/flicker/freeze/multi-monitor matrix | USER REPORT: UI working; full display matrix not independently captured |
| Installed shortcut/taskbar/logo transparency on new package | PENDING new exact-head package install |
| Actual installer geometry/navigation on new package | PENDING new exact-head package install |
| Installed-app Help & Guide walkthrough on new package | PENDING new exact-head package install |
| Stage F speech-integrity source/test contracts | PASS — Build #3533, 1,746/1,746 |
| Final owner release approval | NOT RUN |
