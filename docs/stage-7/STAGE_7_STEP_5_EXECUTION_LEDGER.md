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
