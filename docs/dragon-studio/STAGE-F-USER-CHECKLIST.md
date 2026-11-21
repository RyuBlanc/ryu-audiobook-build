# Stage F — User Physical Acceptance Checklist

**Purpose:** Run only after the Stage F engineering-preparation checkpoint has passed. This checklist is for the real Windows PC checks that cannot be completed by hosted CI.

**Accepted application baseline:** Ryu Audiobook Build #3539, source commit `4b77e693f1f6799dabd41d52ad436319ce593604`.  
**Reference package:** [Build #3539 artifacts](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/44906128357).  
**Installer artifact:** ID `14708683167`; **portable artifact:** ID `14708428872`; **SHA-256 manifest:** ID `14708473846`. The manifest is the authority for the exact application/installer hashes. Download and preserve the installer, portable package and manifest while the Actions artifacts remain available.

## Before testing

- [ ] Download the Build #3539 installer, portable package and SHA-256 manifest.
- [ ] Keep the installer, portable package and manifest together in a safe local folder.
- [ ] Install the same accepted application build on each PC that will participate in a test.
- [ ] Do not delete existing projects, profiles, models or assets to create a test condition.
- [ ] Keep the original real voice bundle and source profile assets unchanged.
- [ ] Use the capture script below to record environment and SHA-256 evidence. It records metadata and hashes only; it does not upload files or audio.

### Capture a PC environment report

Open PowerShell in the repository/checkpoint tools folder. Run once on the source PC:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\stage_f_capture_environment.ps1 `
  -Role PC-A `
  -OutputPath .\StageF-PC-A-environment.json `
  -ApplicationExePath "C:\Path\To\Ryu's Audiobook.exe" `
  -InstallerExePath "C:\Path\To\Ryu's Audiobook Setup.exe"
```

Run the equivalent command on the destination PC with `-Role PC-B` and output name `StageF-PC-B-environment.json`.

For the Voice Library transfer, add the relevant file arguments to the command on each PC:

```powershell
-BundlePath "D:\D6\selected-profiles.ryuvoice" `
-ProfileAssetPaths @("D:\D6\voice-design-anchor.wav", "D:\D6\clone-reference.wav")
```

For `-ProfileAssetPaths`, use the actual profile-owned asset paths reported by Voice Library. The resulting JSON records file sizes and SHA-256 values but deliberately omits the supplied file names and paths. A mismatch against the pinned Build #3539 application/installer/core-installer hash is reported as an error and returns exit code `2`; preserve that report instead of ignoring the mismatch. The capture script now pins Build #3539's manifest SHA-256 values.

The script's hardware inventory is **not** proof that Qwen used CUDA, ROCm, XPU or any other backend. For that, capture the synthesis worker's actual backend/device telemetry during inference.

## F1 — D6: two-PC Voice Library transfer

**DEFERRED — do not run against Build #3539.** The current Voice Studio version does not expose the required user-facing profile import option. This is a product-scope decision for the next Voice Studio version, not an open defect in the current app. Keep the detailed acceptance criteria in [STAGE-D6-TWO-PC-TRANSFER-ACCEPTANCE.md](STAGE-D6-TWO-PC-TRANSFER-ACCEPTANCE.md), and reopen them only after the next Voice Studio version implements import.


## F2 — Qwen hardware and preview performance

Test only hardware/backends that are actually available and supported. Do not present a CPU fallback or the synthetic CI CUDA-selection probe as a GPU result. User reports no AMD/Intel GPU hardware is available. Hosted CPU run #54 passed functional synthesis but took 321.939 seconds to produce 30.000 seconds of warm VoiceDesign audio; the under-60-second target was not met on CPU.

- [ ] Record the exact GPU model, usable VRAM, driver/runtime and Qwen model revision.
- [ ] Run a saved-profile CustomVoice preview with the model size recorded.
- [ ] Run the applicable VoiceDesign 1.7B + exact Base model pairing.
- [ ] Run an authorized Clone preview where a suitable profile exists.
- [ ] Capture cold-start and warmed inference separately.
- [ ] Confirm worker telemetry reports the actual backend/device during synthesis.
- [ ] Record decoded audio duration and elapsed generation time.

Performance targets: approximately 10 seconds of preview audio within 20 seconds; 30 seconds of preview audio in under 60 seconds on supported accelerated hardware. A missing/supported-device limitation must be recorded honestly, not changed to PASS.

## F3 — Installed-app voice identity and representative audiobook

- [ ] Confirm saved CustomVoice, VoiceDesign and Clone profiles persist after app close/relaunch.
- [ ] Confirm model installation/repair/remove paths preserve saved user profiles/assets according to the lifecycle rules.
- [ ] Analyse a representative book; compare detected characters and dialogue with the actual source text across the whole book.
- [ ] Verify narrator-only is off by default when a global Third Person profile exists; ordinary narration stays on the narrator and unassigned character dialogue uses Third Person. Explicit per-book Narrator-only remains an override.
- [ ] Verify Third Person and narrator profiles remain separate; individually assigned character profiles keep their own voices.
- [ ] Generate a representative multi-chapter/full-book audiobook.
- [ ] Record chapter count, eligible/skipped chapters, audio duration, elapsed time, progress, ETA and validated chunk count.
- [ ] Test pause, resume, cancel, retry and a controlled process interruption/restart/recovery.
- [ ] Validate the final M4B in an independent player: chapter markers, titles/order, duration, metadata, cover, decode, seek and playback.
- [ ] Listen for missing/duplicated text, incorrect speaker identity, pronunciation, clipping, silence and sound-design transitions.

For the historical 1,175-vs-1,196 dialogue/passage discrepancy, use the same imported source book and source revision for both measurements and state exactly which count is being compared. The legacy quote-span counter and canonical saved-passage index count different categories; do not treat their raw totals as interchangeable.

## F4 — UI, responsiveness and stability

**Already reported working by the user on 21 November 2026:** current UI and custom cursor. #3539 also passed automated regressions for dropdowns, Production progress-label clipping/tooltips, cursor switching, Settings storage responsiveness, Third Person, chorus routing and responsive-layout contracts. Do not reopen those specific fixes without a reproduced regression.

- [ ] Inspect every application destination, rapid navigation and repeated open/close.
- [ ] Open and operate every dropdown in Voice Studio, Character Studio, Production, Sound Design, Performance and Settings; verify click, keyboard navigation and selection work.
- [ ] In Production, verify the percentage, stage, chapter, elapsed time and ETA stay within their assigned areas; long labels end with an ellipsis and reveal the complete text in a floating hover/focus tooltip.
- [ ] In Settings > Icon Pack, select Drake, Fang and Aether; verify the cursor changes inside the app only and is restored after restart.
- [ ] Import a custom icon image; verify its preview appears in the Custom tile, select it, restart the app and verify the pointer is applied inside the application.
- [ ] Move between Appearance, Storage & library, Speech & AI, Production and Diagnostics; confirm each pane stays responsive without a Windows Not Responding pause.
- [ ] Click dropdowns to open them, select with the mouse, then repeat using keyboard navigation and Space; the popup must not immediately close.
- [ ] In Voice Studio, verify the Third Person global selector is visible beside the narrator controls and remains separate from the narrator.
- [ ] In Character Studio, assign three or more characters to one dialogue passage and confirm simultaneous voice blending without the assignment popover moving out of position.
- [ ] Check for flicker, freeze, delayed response, inaccessible controls, crashes and excessive scroll nesting.
- [ ] Test 1280×720 and the agreed responsive matrix.
- [ ] Test aspect ratios 4:3, 5:4, 3:2, 16:10, 16:9, 21:9, 32:9 and portrait.
- [ ] Test 100%, 125%, 150% and 200% Windows display scaling.
- [ ] Test minimized/restored/maximized, split-screen, ultrawide, portrait and mixed-monitor use.
- [ ] During long generation, verify progress moves truthfully, ETA behaves as a countdown, and cancel responds promptly.

## F5 — Installer, Windows shell and Help & Guide

**Hosted CI:** Build #3539 passed HTML installer startup, install/launch/upgrade/uninstall, user-data preservation, logo checks and Microsoft Defender scans. The exact package still needs target-PC confirmation.

- [ ] Install and launch the Build #3539 package on the target Windows PC.
- [ ] Inspect shortcut/taskbar/app icon transparency; confirm no unwanted white/black square at icon corners.
- [ ] Inspect installer wizard geometry at the target display scaling: footer, Next/Back, details, progress, centering and no black center bar or cropping.
- [ ] Verify upgrade preserves projects, models, profiles and output.
- [ ] Verify uninstall preserves user data as specified.
- [ ] Open Help & Guide and follow the real workflows for import, voice profiles, character analysis, pronunciation, Sound Design, generation/recovery, playback, model management and troubleshooting.
- [ ] Record any instruction that does not match the installed application.

## How to record outcomes

Use only these states:

- **PASS** — the check was actually completed and evidence supports it.
- **FAIL** — it was run and the expected outcome did not occur.
- **BLOCKED** — it could not be run because a required device/model/setup was unavailable.
- **NOT RUN** — it has not been attempted.
- **NOT SUPPORTED** — the device/backend/workload is not supported; do not convert this to PASS.

For a failure, record the exact build/source SHA, test ID, steps, expected/actual result and useful logs. Keep screenshots/audio locally where appropriate. Do not upload private voice recordings, account names, machine serial numbers, computer names, MAC addresses or full local file paths to public GitHub records. Environment JSON reports from the capture script omit those identifiers and include only file hashes/sizes for supplied artifacts.

## Final release gate

- [ ] All applicable F1–F5 checks have evidence.
- [ ] Each unsupported or unavailable device/backend case is labelled NOT SUPPORTED or BLOCKED.
- [ ] All failures have a specific defect record and targeted correction plan.
- [ ] No Stage A–E work has been reopened without a reproducible regression.
- [ ] Final owner review and release approval are recorded separately from CI success.

Physical acceptance remains **NOT RUN** until these boxes are completed on the actual target devices.
