# Stage 7 Master Requirement, Bug and Change Register

**Target:** Version 1.2.0  
**Canonical branch:** `stage-7/step-6-safe-auto-fallback`  
**Evidence baseline:** #2640 regression pass, `5a0b87b0ad3c5f7007cf2775dd9cb2bb90606c60`; packaged baseline #2628  
**Audit date:** 6 November 2026

## Status conventions

PASS = automated regression/package evidence passed. OPEN = evidence outstanding. QUEUED = job has not started, not a pass. WAIVED / NOT RUN = user-excluded physical installation, not represented as success. Historical failures remain recorded.

## Master requirement register

| ID | Requirement | Evidence | Status |
|---|---|---|---|
| MOD-01 | Unified model registry and actual inventory | Step 1 ledger; #2628 | PASS — installed-app check waived |
| MOD-02 | Configurable storage roots and accurate accounting | Step 2 ledger; #2628 | PASS — installed-app check waived |
| MOD-03 | Safe migration, verification, rollback and recovery | `tests/test_storage_migration.py`; #2628 | PASS — physical drive check waived |
| MOD-04 | Unavailable-drive preservation and safe cleanup | Step 2 ledger; #2628 | PASS — physical drive check waived |
| LIF-01 | Individual Piper/Kokoro/Qwen/Audiobook AI removal | `tests/test_models_center_lifecycle.py`; #2628 | PASS — installed-app check waived |
| LIF-02 | Shared Chatterbox/Qwen runtime removal independent of weights/cache | Step 3 ledger; #2628 | PASS — installed-app check waived |
| LIF-03 | Ownership boundaries, symlink protection, active-job blocking and inventory refresh | Step 3 tests; #2628 | PASS |
| HW-01 | Truthful CPU/GPU detection and runtime compatibility | `tests/test_qwen_runtime_safety.py`; #2628 | PASS — physical matrix open |
| HW-02 | NVIDIA real Qwen 1.7B preview under 60 seconds | NVIDIA run #1 | QUEUED |
| HW-03 | AMD ROCm real Qwen 1.7B preview under 60 seconds | AMD/Intel run #9 | QUEUED |
| HW-04 | Intel XPU real Qwen 1.7B preview under 60 seconds | AMD/Intel run #9 | QUEUED |
| PERF-01 | Real benchmark records and verified backend reporting | Benchmark/runtime tests; #2628 | PASS |
| PERF-02 | Persistent history, repeat/export and resource snapshots | Performance Center regression; #2625/#2628 | PASS — installed-app interaction waived |
| PERF-03 | PC benchmark import and comparison | #2624/#2625 | PASS |
| QWEN-01 | Model preference, runtime selection and safe fallback | Qwen policy/runtime tests; #2626/#2627/#2628 | PASS |
| QWEN-02 | 30-second preview under 60 seconds without quality loss | Real GPU artifacts pending | OPEN |
| INT-01 | Cross-module regression and packaged acceptance | #2628, 1,258 tests | PASS |
| REL-01 | Installer, portable, SHA-256 and Defender evidence | #2628 exact HEAD artifacts | PASS |
| REL-02 | Seven ledgers and master register on final candidate | Documentation closeout | OPEN until matching-head CI/package |
| REL-03 | Actual installed Windows acceptance | Explicitly excluded by user | WAIVED / NOT RUN |

## Defect and change register

| Record | Root cause / correction | Evidence | Disposition |
|---|---|---|---|
| BUG-STEP3-ROOTS | Legacy Qwen/Chatterbox uninstall workers validated against wrong root after storage-root split | #2541–#2545; #2628 | Corrected |
| BUG-STEP3-FIXTURE | Lifecycle fixtures assumed shared Models/Runtime roots or patched wrong imported references | #2527–#2530 corrected by later tests | Corrected; failures retained |
| BUG-PACKAGED-2605 | Production Preview chapter selection assertion rejected valid chapter-qualified preview-ready state | Later package checkpoints #2622/#2625/#2628 | Corrected |
| BUG-BENCH-2606 | Benchmark test lacked isolated installed Piper fixture | #2607/#2608 and #2628 | Corrected |
| BUG-TASKMANAGER-2547 | Task Manager exceeded 600x800 viewport due to fixed width and overlay padding | #2548/#2549 and #2628 | Corrected |
| BUG-PC-COMPARE-2623 | PC comparison/import change initially failed CI | #2624/#2625/#2628 | Corrected |
| CI-QWEN-AMDI-BRANCH | AMD/Intel workflow targeted Stage 3 instead of Stage 7 | #2626 | Corrected; hardware run queued |
| CI-QWEN-NVIDIA-TRIGGER | NVIDIA workflow was dispatch-only | #2627 | Corrected; hardware run queued |
| CI-PACKAGED-2628 | Matching-head package checkpoint | #2628 | PASS |

## Current blockers

1. NVIDIA #1 and AMD/Intel #9 remain queued on self-hosted runner labels; verify runner availability or record the unavailable hardware limitation.
2. Qwen target requires real 27–33 second audio, warmed synthesis under 60 seconds, verified active backend and quality evidence.
3. The latest exact-head full regression passed in #2640 (1,258 tests); its build job was skipped because this was a test-only commit. A dedicated artifact-checkpoint commit and matching-head package run are still required.
4. Physical installation is user-waived / not run.

## Evidence links

- #2628: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42236851623
- #2627 NVIDIA workflow trigger CI: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42236144051
- NVIDIA hardware run #1: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42236144535
- #2626 AMD/Intel workflow trigger CI: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42236126629
- AMD/Intel hardware run #9: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42236126768
- #2625 Performance Center package: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42231677314
- #2624 PC benchmark comparison/import: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42231216994

**Disposition:** Matching-head full regression and Windows packaged acceptance PASSED on #2641 / `b1da6a8d4aee39e83ca9f781e22b92d26bb4859f`. Installer, portable, SHA-256, Defender and Piper benchmark artifacts uploaded. Hardware performance remains open pending real self-hosted runner evidence. Physical installation is waived, not passed.


## Final documentation-head checkpoint request — 6 November 2026

All seven execution ledgers and this master register are now present on the canonical Stage 7 branch. The final documentation candidate must be validated on its exact commit with the full regression and Windows package workflow. This checkpoint is deliberately marked as an artifact checkpoint so the build job is not skipped.

Physical installed-app acceptance remains user-waived/not run. Real NVIDIA/AMD/Intel inference remains dependent on the queued self-hosted jobs and cannot be converted into a pass by this documentation checkpoint.


## Subsequent responsive acceptance correction — 6 November 2026

- #2637 failed at the 600x800 responsive viewport check (Task Manager measured 780px wide in a 600px viewport).
- #2638 passed after adding synchronization for iframe CSS media-query recalculation.
- #2639 failed in the Python preflight because the new JavaScript `matchMedia` markers were mistakenly asserted in the Python launcher as well as the browser script. This was a test-contract ownership error.
- #2640 corrected the Python test to assert browser-only `matchMedia` markers in the JavaScript fixture, while retaining the original 41-resolution packaged acceptance. Full regression: 1,258 tests passed.
- #2640 is test-only; its build job was skipped. Do not treat it as a packaged acceptance pass. A dedicated artifact-checkpoint run must validate the frozen executable and installer on the exact candidate.

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

## Exact-head package evidence — #2641

- Run: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42248725120
- Commit: `b1da6a8d4aee39e83ca9f781e22b92d26bb4859f`.
- Tests: 1,258 passed; focused Stage 6 preflight and Qt lifecycle passed.
- Frozen app and responsive packaged Sound Design/Music Library acceptance passed.
- Installer, portable, SHA-256 and Defender gates passed; all four expected artifacts were uploaded.
- The 30-second Qwen hardware workflows are still queued, not passed.
- Installed-app manual checks are user-waived/not run.

## Matching-head acceptance update — 6 November 2026

- Final responsive acceptance correction is included in candidate `b1da6a8d4aee39e83ca9f781e22b92d26bb4859f`.
- Build Windows App #2641 passed both jobs: 1,258 regression tests, focused Stage 6 responsive preflight, Qt lifecycle regression, frozen app verification, packaged Sound Design/Music Library acceptance, installer and portable package creation, SHA-256 manifest, Microsoft Defender scan and artifact upload.
- Exact run: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42248725120
- Manual installed-Windows acceptance remains user-waived/not run.
- Real GPU acceptance remains pending: NVIDIA run #1 and AMD/Intel run #9 have not started because their self-hosted jobs are queued. No GPU target or under-60-second Qwen performance result is claimed.

## Real hosted Qwen CPU benchmark evidence — 7 November 2026

- Actual official Qwen 1.7B VoiceDesign model executed through the production provider/worker on GitHub-hosted Windows CPU in workflow [run #1](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42301856102), commit `97e6bb4240d51def6d4a5d1fc7d86c070c522a21`.
- Output verified as 30.000 seconds mono 24 kHz PCM; measured warmed preview latency **268.184 seconds** (5 segments, worker reused). Under-60-second target is not met on CPU.
- Real warm/angry expression audio and Japanese pronunciation pipeline passed; Japanese source `リムルが来た。` and single-rule application independently checked.
- Artifact: `Ryu-Stage7-Qwen-Real-CPU-Preview-1`, ID `13544458572`, 1,566,779 bytes.
- Source CI #2662 passed 38 focused Stage 6 tests and the full 1,258-test regression suite.
- NVIDIA / AMD ROCm / Intel XPU real GPU runs remain queued; this CPU result cannot substitute for those hardware checks.

**Updated QWEN-02 status:** OPEN / CPU target missed (268.184s). GPU target not yet measured. CPU result is now measured instead of inferred.

## Final Stage 7 CPU-side acceptance checkpoint — 7 November 2026

- #2662 source CI: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42301856057 — full regression **1,258 passed**; focused 38-test Stage 6 preflight passed. The Windows artifact job was skipped because #2662 was a normal test commit, not an artifact-checkpoint message.
- Real Qwen CPU workflow: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42301856102 — successful real Qwen 1.7B VoiceDesign inference; 30.000s WAV output; warmed preview took 268.184s; worker reused; warm/angry and Japanese pronunciation checks passed. The under-60s target is NOT MET on hosted CPU.
- Real inference evidence artifact: `Ryu-Stage7-Qwen-Real-CPU-Preview-1` (ID 13544458572).
- NVIDIA, AMD ROCm and Intel XPU GPU-specific workflows remain queued on self-hosted runners. Their benchmark targets are not met/verified until real GPU evidence exists.
- Actual installed-app / physical installation tests on the user's PC remain excluded and are to be completed by the user later.

## Latest-records package gate

This commit requests a fresh matching-head full regression and Windows installer/portable package checkpoint after the Qwen CPU benchmark result was reconciled into the Stage 7 records.
