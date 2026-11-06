# Stage 7 Step 4 — Hardware Detection and Runtime Compatibility

Updated: 6 November 2026

## Scope and implementation

- Live host CPU utilization and total/available RAM are read from psutil, with a Windows CIM fallback when psutil telemetry is unavailable.
- Accelerator inventory is sourced from the Qwen accelerator detector. It distinguishes an active PyTorch CUDA/ROCm/XPU runtime from a detected-but-not-active candidate and from an unsupported device. A detected adapter is never labelled as an active acceleration runtime merely because its driver or device name exists.
- NVIDIA candidates can be discovered through `nvidia-smi`; active CUDA devices and VRAM are read from PyTorch / NVIDIA telemetry.
- AMD Windows support is restricted to the published ROCm/PyTorch device and Windows release matrix. Unsupported adapters remain CPU fallback candidates rather than being assigned an invented GPU runtime.
- Intel Arc / supported Core Ultra Arc devices are reported as XPU candidates until the PyTorch XPU runtime is actually available. Active XPU status is taken from PyTorch.
- The Performance Center uses `performance.info(refresh:false)` for a lightweight display refresh and `performance.info(refresh:true)` only for an explicit hardware rescan. The rescan action refreshes the detector cache and reports current telemetry/candidate status.
- The displayed generation-time field remains **Not tested** until a real synthesis benchmark supplies a measured duration. Hardware discovery is not represented as a TTS benchmark.

## Regression and CI evidence

- Full regression on source commit `0179f63a69c2f2709a6f30acb1ae5ff714507e3`: **1,243 tests passed**.
- Workflow #2604: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42217262698
- Frontend JavaScript syntax validation, isolated native Qt lifecycle regression, focused Stage 6 History/Task Manager preflight and full regression all passed.
- Existing automated matrix coverage in `tests/test_qwen_runtime_safety.py` includes CUDA/ROCm/XPU priority, AMD ROCm 10.1 and legacy 7.2.1 GPU/APU mappings, unsupported AMD devices, Intel Arc/Core Ultra candidate detection, shared-memory versus VRAM distinction, official wheel selection, and rejection when HIP/XPU runtime activation is not verified.
- Smoke scripts exist for real Qwen GPU and AMD/Intel preview acceptance; the hosted Windows runner does not provide the user's target AMD/Intel hardware.

## Explicit limits and remaining acceptance

- Automated detection and runtime-policy regression is green. Physical validation on representative NVIDIA, AMD discrete, AMD iGPU/APU and Intel Arc/Core Ultra hardware remains a device-lab/manual acceptance item; CI cannot claim those devices were physically exercised.
- Performance Center's hardware scan is a telemetry refresh, not a synthesis benchmark. A real measured TTS benchmark must remain a separate Step 5 acceptance gate.
- Do not infer that an installed GPU runtime is active until the provider's real runtime and synthesis check passes.

**Step 4 disposition:** automated implementation and regression PASS; physical device-matrix acceptance remains explicitly open. Continue to Step 5 without representing the manual device matrix as passed.

## 2026-11-06 — latest combined-head CI and accelerator workflow status

- Matching-head Actions #2628 on `0fc9d8189311419414746ffb23d89df9c65d116c` passed full regression: **1,258 tests**, and Windows build/package acceptance passed.
- Stage 7 Qwen accelerator workflows were wired to the canonical `stage-7/**` branch:
  - NVIDIA source CI #2627 passed; real GPU run #1 is queued.
  - AMD/Intel source CI #2626 passed; real ROCm/XPU run #9 is queued.
- Queued self-hosted jobs are not physical hardware results. No NVIDIA, AMD ROCm, or Intel XPU performance pass is claimed from those jobs until they execute and upload real inference evidence.

**Current disposition:** software detection/runtime policy regression PASS; physical NVIDIA/AMD/Intel device matrix remains pending or unavailable. The target 30-second Qwen preview performance gate is tracked separately in Step 6.
