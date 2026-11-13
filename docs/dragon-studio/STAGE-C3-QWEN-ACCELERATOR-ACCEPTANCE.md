# Stage C3 — Qwen accelerator and performance acceptance

**Status:** Candidate implementation and hosted policy regressions in progress. Physical accelerator closeout has not been claimed.

**Baseline:** Stage C2 exact-head Build Windows App #3382, commit `05a15fac65305e428752f194b8852884c40c7c5d`, branch `dragon-studio/candidate-c2-profile-lifecycle-2026-11-13`.

## C3 objectives

1. Detect an accelerator only when the operating system/device and actual Qwen PyTorch runtime agree.
2. Distinguish an installed/active runtime from a hardware candidate that still needs a driver or runtime.
3. Keep explicit CUDA/ROCm/XPU selections fail-closed; never silently produce CPU audio and report it as GPU.
4. Keep Automatic on a verified supported GPU by default. CPU may win only with recent, paired, device-verified 30-second measurements for the same model and same host, with CPU at least 5% faster.
5. Ignore missing, malformed, unverified, stale, wrong-machine, wrong-model and materially future-dated benchmark records.
6. Measure real saved-profile audio, not a worker handshake, protocol-ready message, synthetic WAV or Piper ONNX result.

## Automated hosted regression

- `tests.test_qwen_accelerator_acceptance` exercises active NVIDIA CUDA, AMD ROCm (HIP-enabled PyTorch), Intel XPU, NVIDIA detection when CUDA PyTorch is not active, Windows AMD device/version matching, Windows Intel Arc/Core Ultra predicates, and rejection of future-dated paired benchmark evidence.
- `tests.test_qwen_runtime_safety`, `tests.test_qwen_preview_performance_policy` and `tests.test_qwen_global_model_preference` remain in the hosted Qwen contract suite.
- The focused C3 tests run in the main Windows regression job and the hosted CPU contract workflow.
- CPU preview remains comparison-only. Qwen CPU run #38 generated 30.000s of actual saved-profile VoiceDesign audio in 255.415s, explicitly not meeting the 60-second target.

## Physical hardware acceptance matrix

| Hardware | Runtime proof | Workload | Acceptance |
|---|---|---|---|
| NVIDIA CUDA, 7 GiB+ VRAM | CUDA-enabled PyTorch, exact GPU/driver via `nvidia-smi`, actual worker telemetry `cuda` | Saved VoiceDesign reload; 1.7B VoiceDesign + 1.7B Base identity path; warmed 30s preview | 27–33s decoded audio, under 60s elapsed, CUDA verified, no CPU fallback |
| NVIDIA CUDA, lower-memory tier (including 4 GiB where loadable) | CUDA-enabled PyTorch and actual worker telemetry `cuda` | Saved-profile CustomVoice 0.6B; real 30s preview | 27–33s decoded audio, under 60s, CUDA verified; retain exact VRAM and error evidence if it cannot load, never convert failure into CPU pass |
| AMD ROCm | Active HIP-enabled PyTorch; backend reported `rocm`, not merely WMI candidate | Saved VoiceDesign 1.7B + Base preview and real production chapters; saved CustomVoice 0.6B preview | Actual backend `rocm`, 27–33s preview, under 60s, production chunks decode; retain adapter/driver/ROCm/PyTorch versions |
| Intel XPU | `torch.xpu.is_available()`, active `xpu` runtime and device telemetry | Saved VoiceDesign 1.7B + Base preview and real production chapters; saved CustomVoice 0.6B preview | Actual backend `xpu`, 27–33s preview, under 60s, production chunks decode; retain adapter/driver/oneAPI/PyTorch versions |

A hardware candidate is not an active runtime. Device name, WMI result, VRAM size, model download, worker handshake or CUDA availability alone is not inference acceptance. The provider must report the same backend/device during measured synthesis.

The 1.7B NVIDIA VoiceDesign workflow intentionally requires at least 7 GiB VRAM. The separate 0.6B CustomVoice path allows lower-memory NVIDIA hardware to be evaluated without weakening that gate. A 4 GiB card that cannot load this model/workload must be recorded as unsupported for that workload; do not count CPU fallback.

## Workflow controls

- `.github/workflows/qwen-nvidia-preview-acceptance.yml`: existing 1.7B VoiceDesign CUDA gate, self-hosted Windows NVIDIA, manual dispatch or explicit hardware tag.
- `.github/workflows/qwen-nvidia-customvoice-acceptance.yml`: new 0.6B CustomVoice CUDA gate, self-hosted Windows NVIDIA, manual dispatch or explicit hardware tag.
- `.github/workflows/qwen-amd-intel-preview-acceptance.yml`: real ROCm/XPU VoiceDesign preview and long-form throughput, extended with saved-profile CustomVoice 0.6B preview.
- `.github/workflows/qwen-cpu-contract-acceptance.yml`: hosted CPU comparison and software contract tests; never GPU proof.

Hardware workflows are not triggered by an ordinary source checkpoint. They remain manually dispatchable. Do not wait for or infer a result from an unassigned runner.

## Upstream Windows support matrices

- AMD ROCm support is version-, OS- and device-specific. The official ROCm matrix lists Windows 11 25H2 and validated PyTorch 2.14.0 support for the corresponding device set: https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html
- Intel's current PyTorch XPU client matrix lists Windows 11 support for Arc A-Series, Arc B-Series and Core Ultra Arc graphics families including Meteor Lake-H, Arrow Lake-H, Lunar Lake and Panther Lake: https://docs.pytorch.org/docs/2.15/notes/get_start_xpu.html
- Device allow-lists are not inferred from marketing names alone; update them only against current upstream matrix entries and keep positive and negative regression cases.

## C3 exit criteria

C3 can close only after the exact candidate SHA:
- passes the new focused C3 suite, the full regression suite and exact-head Windows package checkpoint;
- produces real decoded preview audio and device-verified timing evidence on each backend claimed as supported;
- passes the relevant under-60-second target without CPU fallback;
- preserves backend/device/model/VRAM/driver/runtime metadata and uploads benchmark artifacts;
- records unsupported hardware/workloads transparently rather than disguising a fallback as a pass.

C1/C2 installed-PC checks, representative full-novel Qwen acceptance and Stage C4 narrator/character consistency remain separate work. C3 does not close them.