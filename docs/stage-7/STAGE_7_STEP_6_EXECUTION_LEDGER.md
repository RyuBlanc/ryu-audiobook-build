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
