# Stage 7 Step 7 — Cross-Module Integration, Final Regression and Release Closeout

**Target:** Version 1.2.0  
**Branch:** `stage-7/step-6-safe-auto-fallback`  
**Latest packaged baseline:** #2628, `0fc9d8189311419414746ffb23d89df9c65d116c`

## Scope

Integrate Stage 7 without changing the approved Premium V2 design or regressing accepted Stage 1–6 behavior. Produce matching-commit Windows installer/portable artifacts and auditable release records.

## Integrated evidence

- Full Windows regression: **1,258 tests passed** on exact #2628 candidate.
- Frontend JavaScript syntax, isolated native Qt lifecycle and focused Stage 6 History/Task Manager preflight passed.
- Frozen Windows app verification and packaged Sound Design/Music Library acceptance passed.
- Installer and portable artifacts generated.
- SHA-256 manifest, Defender checks and artifact upload gates passed.
- All #2628 artifacts are attached to exact commit `0fc9d8189311419414746ffb23d89df9c65d116c`.
- Steps 1–4 ledgers reconciled with #2628 evidence; Steps 5–7 and master register are added in this documentation closeout.

## Final acceptance

- [x] Matching-head regression (#2628).
- [x] Matching-head frozen app/package acceptance (#2628).
- [x] Installer and portable artifacts (#2628).
- [x] SHA-256 manifest and Defender checks (#2628).
- [ ] Seven ledgers and master register committed on final candidate.
- [ ] Matching-head CI/package rerun after final documentation commit.
- [ ] Resolve queued hardware jobs or carry forward explicit runner/device limitation.
- [ ] Version 1.2.0 sign-off after non-waived gates are green.

## User-directed exclusion

The user asked to complete Stage 7 except physical installation. Hands-on installation, first launch, uninstall and migration interaction on the user's actual Windows machine are WAIVED / NOT RUN. They are not claimed as passed. Automated lifecycle regressions and packaged acceptance remain in scope.

**Status: AUTOMATED INTEGRATION AND PACKAGED ACCEPTANCE PASS ON #2628; FINAL DOCUMENTATION-HEAD ACCEPTANCE AND HARDWARE RUNNER DISPOSITION REMAIN.**

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

## Cross-step Qwen verification update — 7 November 2026

- Companion hosted Windows CPU Qwen acceptance workflow [run #1](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42301856102) passed its real inference flow and uploaded audio/diagnostics. Actual output was valid 30.000-second mono 24 kHz PCM; warmed synthesis took 268.184 seconds, so under-60-second target was not met on CPU.
- Source CI [#2662](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42301856057) passed 38 focused tests and 1,258 full regression tests.
- Real NVIDIA/AMD/Intel hardware acceptance remains queued and is not represented as passed. Physical installed-app checks remain user-waived/not run.


## User decision — hardware acceptance carry-forward (7 November 2026)

The user explicitly defers real GPU and installed-device checks until the required hardware is available. Record these as **DEFERRED / NOT RUN**, never as passed:

- NVIDIA CUDA, AMD ROCm and Intel XPU Qwen 1.7B performance acceptance (under-60-second warmed 30-second preview).
- Hands-on installed-Windows first-launch, uninstall and storage/migration interaction checks previously excluded by the user.

Automated source regression and Windows packaged acceptance remain independently verifiable. Final exact-head package run #2672 is currently in progress; its regression job passed, and its packaging job has passed frozen-app verification and packaged Sound Design/Music Library acceptance and is completing installer packaging/upload gates.

**Closeout rule:** Stage 7 software/package closeout can be signed off after #2672 succeeds. GPU performance and physical installed-app validation remain named carry-forward checks for the later hardware session. Stage 8 can proceed without falsely claiming those checks passed.
