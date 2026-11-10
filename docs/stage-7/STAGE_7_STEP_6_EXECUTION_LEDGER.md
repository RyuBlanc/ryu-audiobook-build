# Stage 7 Step 6 — Hardware Optimization, Qwen Runtime and 30-Second Preview Performance

**Target:** Version 1.2.0  
**Branch:** `stage-7/step-6-safe-auto-fallback`  
**Latest code baseline:** `0fc9d8189311419414746ffb23d89df9c65d116c`

## Scope

Choose Qwen runtime from actual device/runtime capability, preserve model preference, report the backend actually used, and measure a warmed real 30-second VoiceDesign preview against the under-60-second target without sacrificing voice quality.

## Implemented and automated evidence

- Qwen 0.6B/1.7B preference and model identity are tracked independently.
- Accelerator selection distinguishes detected hardware from active CUDA/ROCm/XPU runtime.
- Backend telemetry reports the verified inference provider; CPU fallback is not relabelled GPU.
- Runtime safety tests cover CUDA/ROCm/XPU priority, AMD support mappings, Intel XPU candidates, shared memory versus VRAM, official wheel selection and rejection of inactive runtimes.
- Qwen preview performance policy and actual inference telemetry have regression coverage.
- Real accelerator scripts: `tests/smoke_qwen_gpu_preview.py` and `tests/smoke_qwen_amd_intel_preview.py`.
- Scripts require actual 1.7B VoiceDesign inference, 27–33 seconds of audio, active expected backend, no CPU fallback and elapsed synthesis under 60 seconds.
- Source workflow CI #2626 and #2627 each passed 1,258 tests; matching-head #2628 passed regression and Windows package acceptance.

## Physical accelerator status

| Target | Workflow | Result |
|---|---|---|
| NVIDIA CUDA | [Run #1](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42236144535) | QUEUED |
| AMD ROCm | [Run #9](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42236126768) | QUEUED |
| Intel XPU | AMD/Intel runner workflow #9 | QUEUED |

Both workflows use self-hosted runner labels `NVIDIA` and `AMD-INTEL`. Queued means the test has not started; it is not a pass. No GPU timing or voice-quality pass is claimed until real audio and benchmark artifacts are uploaded and inspected.

## Acceptance

- [x] Model preference and runtime safety policy regression.
- [x] Actual-backend telemetry and CPU-fallback truthfulness tests.
- [x] Real GPU smoke scripts and Stage 7 branch workflow triggers.
- [x] Matching-head regression and Windows packaged acceptance (#2628).
- [ ] NVIDIA real 30-second preview under 60 seconds.
- [ ] AMD ROCm real 30-second preview under 60 seconds where supported.
- [ ] Intel XPU real 30-second preview under 60 seconds where supported.
- [ ] Inspect benchmark JSON/audio, output duration, backend and voice quality.

Earlier hosted Qwen 1.7B CPU preview measurements were approximately 298–305 seconds for 30 seconds of output. That does not meet the target. A 4GB NVIDIA device is not assumed to pass the current 1.7B high-memory gate (7 GiB VRAM); evaluate lower-memory model mode separately without weakening the 1.7B test.

**Status: SOFTWARE IMPLEMENTATION AND REGRESSION PASS; PHYSICAL GPU PERFORMANCE ACCEPTANCE BLOCKED BY QUEUED SELF-HOSTED RUNNERS.**

## 2026-11-06 — exact matching-head package closeout #2641

- Candidate commit: `b1da6a8d4aee39e83ca9f781e22b92d26bb4859f`.
- GitHub Actions #2641 completed successfully: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42248725120
- Full Windows regression: **1,258 tests passed** (66.317 seconds).
- Focused Stage 6 History/Task Manager preflight and isolated native Qt lifecycle regression passed.
- Frontend and installer JavaScript syntax checks passed.
- Frozen application verification, bundled voice/critical module checks and the packaged Sound Design/Music Library acceptance (including Stage 5.3 generation UI and responsive viewport suite) passed.
- Inno Setup installer and functional HTML installer packaging passed.
- SHA-256 manifest generation and Microsoft Defender scan passed.
- Installer, portable package and real Piper benchmark JSON artifacts uploaded successfully.
- Artifacts: installer #2641 (884,310,710 bytes); portable #2641 (1,368,242,573 bytes); SHA-256 manifest (777 bytes); Piper benchmark evidence (806 bytes).
- Publish verified installer release step was skipped by workflow policy; uploaded verified artifacts remain available from the Actions run.
- User-directed physical installation checks remain WAIVED / NOT RUN. No claim is made of manual install or post-install destructive model checks.

**Disposition:** EXACT-HEAD REGRESSION AND PACKAGED WINDOWS ACCEPTANCE PASS on #2641. Step 7 software/package gate is current through #2641; physical accelerator acceptance remains separate and open.

## Matching-head acceptance update — 6 November 2026

- Final responsive acceptance correction is included in candidate `b1da6a8d4aee39e83ca9f781e22b92d26bb4859f`.
- Build Windows App #2641 passed both jobs: 1,258 regression tests, focused Stage 6 responsive preflight, Qt lifecycle regression, frozen app verification, packaged Sound Design/Music Library acceptance, installer and portable package creation, SHA-256 manifest, Microsoft Defender scan and artifact upload.
- Exact run: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42248725120
- Manual installed-Windows acceptance remains user-waived/not run.
- Real GPU acceptance remains pending: NVIDIA run #1 and AMD/Intel run #9 have not started because their self-hosted jobs are queued. No GPU target or under-60-second Qwen performance result is claimed.


## Hosted real Qwen acceptance — 7 November 2026

- Workflow: [Stage 7 Qwen Real CPU Preview and Accelerator Contract Acceptance](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42301856102), commit `97e6bb4240d51def6d4a5d1fc7d86c070c522a21`.
- Hosted Windows CPU run completed successfully and uploaded artifact `Ryu-Stage7-Qwen-Real-CPU-Preview-1` (artifact ID `13544458572`, 1,566,779 bytes).
- Real Qwen model: `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`.
- Warmed 30-second preview: **30.000 seconds output**, **268.184 seconds synthesis elapsed**, 5 segments, same persistent worker reused. The under-60-second target is **NOT MET on hosted CPU**.
- Cold start + warmup sample: 56.588 seconds (4.400-second sample); this is reported separately and is not the preview latency.
- Real warm and angry expression audio generated successfully.
- Japanese pronunciation preview generated: 1.040 seconds; normalized source matched `リムルが来た。`; saved Rimuru rule applied exactly once.
- Actual WAV inspection: preview is valid mono 24 kHz PCM with 720,000 frames = 30.000 seconds. The warmup, warm/angry expression and Japanese WAVs are non-empty and have valid headers.
- CPU artifact is genuine end-to-end Qwen inference. It validates worker reuse, duration control, expression output and pronunciation integration; it does not prove GPU speed, GPU backend selection or target-device voice quality.
- Companion source/regression run [#2662](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42301856057) passed: focused 38 tests and full 1,258-test suite. Build job was skipped because this was not an artifact-checkpoint commit.
- Real NVIDIA and AMD/Intel smoke workflows remain queued on their self-hosted runner labels. The real under-60-second GPU requirement remains an open hardware-only acceptance gate.


## User decision — physical accelerator testing deferred (7 November 2026)

The user does not currently have access to the required GPU hardware and has directed that hardware testing be completed later when hardware is available. This is **DEFERRED / NOT RUN**, not a pass and not a deletion of the acceptance criteria.

| Target | Status | Later acceptance evidence required |
|---|---|---|
| NVIDIA CUDA Qwen 1.7B | DEFERRED — hardware unavailable | Real 27–33s preview, active CUDA proof, warmed synthesis under 60s, audio/benchmark artifact and quality review |
| AMD ROCm Qwen 1.7B | DEFERRED — hardware unavailable | Real 27–33s preview, active ROCm proof, warmed synthesis under 60s, audio/benchmark artifact and quality review |
| Intel XPU Qwen 1.7B | DEFERRED — hardware unavailable | Real 27–33s preview, active XPU proof, warmed synthesis under 60s, audio/benchmark artifact and quality review |

The hosted Windows CPU run remains genuine end-to-end inference evidence: 30.000s output in 268.184s warmed synthesis. It confirms that the CPU path works but misses the under-60s target and proves no GPU performance. Keep all accelerator scripts and gates intact for later execution; do not convert queued jobs to passes.

**Step 6 disposition:** software runtime-selection, fallback, telemetry and test implementation are complete; physical accelerator performance acceptance is deferred and remains open for later hardware access.
