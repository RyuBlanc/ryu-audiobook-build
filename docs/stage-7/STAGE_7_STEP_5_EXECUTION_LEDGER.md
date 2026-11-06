# Stage 7 Step 5 — Performance Center, Real Benchmarks and PC Comparison

**Target:** Version 1.2.0  
**Branch:** `stage-7/step-6-safe-auto-fallback`  
**Latest matching-head evidence:** #2628, `0fc9d8189311419414746ffb23d89df9c65d116c`

## Scope and implementation evidence

- Persistent benchmark records are separate from the transient latest-result display.
- Benchmark records include resource snapshots and support repeat/export workflows.
- PC benchmark import and comparison were implemented; legacy report import is covered by #2624 and packaged #2625.
- Hardware rescan is separate from synthesis measurement; generation time remains Not tested until real synthesis supplies a measurement.
- Backend reporting uses verified inference-provider telemetry; unverified/CPU fallback must not be labelled GPU.
- Relevant regression coverage includes `tests/test_qwen_preview_performance_policy.py`, `tests/test_p0_hardware_fallback.py` and benchmark tests in the full regression suite.
- #2624 passed PC comparison/import CI; #2625 passed the packaged Performance Center/PC comparison checkpoint; #2628 passed the combined 1,258-test regression and Windows package acceptance.

## Acceptance

- [x] Persistent benchmark records and regression coverage.
- [x] Resource snapshots and measured-result data model coverage.
- [x] PC benchmark import/comparison and regression evidence.
- [x] Matching-head packaged acceptance includes Performance Center changes.
- [x] Hardware scan is not represented as a synthesis benchmark.
- [ ] Hands-on interactive acceptance after app restart, repeat/export, import and comparison (actual user-machine installation excluded by this request).
- [ ] Physical GPU benchmark evidence is tracked under Step 6.

Evidence: [#2624](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42231216994), [#2625](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42231677314), [#2628](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42236851623).

**Status: SOFTWARE IMPLEMENTATION, REGRESSION AND PACKAGED ACCEPTANCE PASS.** Actual installed-app interaction is waived/not run; physical GPU performance is tracked separately.
