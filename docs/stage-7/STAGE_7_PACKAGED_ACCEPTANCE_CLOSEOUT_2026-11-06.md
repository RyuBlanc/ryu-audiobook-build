# Stage 7 — Packaged Acceptance Closeout Candidate

**Audit date:** 6 November 2026  
**Working branch:** `stage-7/step-6-safe-auto-fallback`  
**Candidate source head before this checkpoint record:** `7fba1b24718cbfaa775619b629cf584adc1bed0e`  
**Latest packaged feature checkpoint:** #2625, commit `544f0153d276d78c8f12d815e2ccbcf69c6ee049`

## Purpose

Record the exact latest Stage 7 candidate, its new Qwen hardware workflow wiring, and the remaining matching-head package and physical-device gates. This document does not claim Stage 7 completion.

## Previous packaged checkpoint

Run #2625 passed on commit `544f0153d276d78c8f12d815e2ccbcf69c6ee049`:

- Windows regression job passed.
- Windows application build/package job passed.
- Frozen-app and packaged Sound Design/Music Library acceptance passed, including Production Preview chapter selection.
- Installer, portable package, SHA-256 manifest, and Defender evidence were uploaded.
- Bundled Piper benchmark artifact reported 12.852 seconds of generated audio in 3.813 seconds, RTF 0.297x, using ONNX CPUExecutionProvider on the hosted Windows runner. This is a CPU benchmark, not GPU proof.

Run: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42231677314

## Qwen accelerator workflow correction

The Stage 7 audit found both accelerator acceptance workflows were not correctly integrated with the active Stage 7 branch:

- AMD/Intel workflow was still scoped to the Stage 3 branch.
- NVIDIA workflow was manual-only.

Both workflows have been corrected to run on relevant Qwen path changes under `stage-7/**`, while retaining manual dispatch.

- AMD/Intel workflow commit: `12a1e37db4583d2c241b85d2c93517707a078b9f`; test CI #2626 passed.
  - CI: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42236126629
  - Real AMD/Intel hardware run #9 remains queued: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42236126768
- NVIDIA workflow commit: `7fba1b24718cbfaa775619b629cf584adc1bed0e`; test CI #2627 passed.
  - CI: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42236144051
  - Real NVIDIA hardware run #1 remains queued: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42236144535

Both #2626 and #2627 ran the full regression suite: **1,258 tests passed** on each. Their Windows build jobs were skipped because these were ordinary workflow-wiring commits, not artifact-checkpoint commits. The real hardware jobs are queued; no accelerator timing or hardware pass is claimed until those jobs execute and upload evidence.

## Required matching-head checkpoint

This record is committed with an `[artifact-checkpoint]` message so the Windows build workflow runs both jobs against the same new HEAD:

1. Full Windows regression suite.
2. Frozen Windows application verification and packaged feature acceptance.
3. Installer and portable application packaging.
4. SHA-256 manifest, Defender scan, and artifact upload.

Do not reuse #2625 package artifacts as matching-head acceptance for the later workflow commits.

## Remaining Stage 7 acceptance

1. **Steps 1–3 — Model inventory, storage and lifecycle:** retain existing implementation and passing regression evidence; complete matching-head packaged acceptance and actual installed-Windows checks for individual Piper/Kokoro/Qwen removal, shared Chatterbox/Qwen runtime removal, preserved model weights, voice profiles, projects and user assets.
2. **Step 2 — Storage:** verify configurable roots, file inventory, migration, interrupted recovery, disconnected-drive handling and safe cleanup in the installed application. CI-only evidence is not a manual installed-app pass.
3. **Step 4 — Hardware detection:** automated runtime-policy regression is green. Physical NVIDIA, AMD discrete/APU/iGPU and Intel Arc/Core Ultra validation remains device-dependent and must be recorded only for devices actually tested.
4. **Step 5 — Performance Center:** verify persistent benchmark history, repeat/export, resource snapshots, PC-to-PC comparison/import, and truthful active backend/device reporting in the packaged app. Hardware scan must not be presented as a synthesis benchmark.
5. **Step 6 — Optimization/Qwen:** run real warmed 30-second Qwen 1.7B VoiceDesign acceptance on supported NVIDIA, AMD ROCm and Intel XPU hardware. Require actual successful inference, correct backend telemetry, audio artifact and measured time. Target is under 60 seconds without reducing voice quality. CPU fallback must be labelled CPU and must not count as GPU acceptance.
6. **Step 7 — Integration/release:** verify cross-module integration, Premium V2 UI behavior and no regressions to accepted Stage 1–6 workflows; update all execution records and the master register; run final installer/portable acceptance on the exact release commit.

## Acceptance rule

A green source regression run, a hosted CPU benchmark, a queued self-hosted job, or an earlier packaged checkpoint is not a substitute for the exact evidence required above.

**Status: IN PROGRESS — 1,258-test regression is green; Qwen hardware runs are queued; matching-head Windows packaging and installed-device acceptance remain open.**
