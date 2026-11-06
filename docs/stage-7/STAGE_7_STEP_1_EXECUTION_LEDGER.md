# Stage 7 — Step 1 Execution Ledger
## Unified Model Registry and Actual Inventory

**Project:** Ryu's Audiobook — Dragon Studio Edition  
**Target:** Version 1.2.0  
**Stage 6 accepted baseline:** Build #2368  
**Baseline branch:** `stage-6/baseline-audit`  
**Baseline commit:** `1c5e5774c43448260b10990f24f9303250589c39`  
**Stage 7 working branch:** `stage-7/step-1-model-registry-inventory`  
**Audit date:** 5 November 2026

## 1. Baseline verification

- Build #2368: successful.
- Run: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42050864498
- Tests job: success.
- Windows build/package job: success.
- Installer artifact: `Ryu-Audiobook-Installer-2368`, present and unexpired at audit.
- Portable artifact: `Ryu-Audiobook-Portable-2368`, present and unexpired at audit.
- SHA-256 artifact: `Ryu-Audiobook-Release-SHA256-2368`, present and unexpired at audit.
- Build #2367 failed packaged acceptance because the Task Manager did not repair a missing View action in place. The subsequent #2368 packaged acceptance passed; do not redo this fix absent a regression.
- The latest observed `main` HEAD is `356b536499be8d3679d96496f24f3836864cb47e`. It is maintenance-only relative to the accepted Stage 6 line and is highly diverged from the Stage 6 baseline. Do not use `main` as the Stage 7 implementation base.

## 2. Existing implementation inspected

Files inspected at the exact Stage 6 baseline:

- `app/tts/model_registry.py`
- `app/ui/models_page.py`
- `app/ui/premium_v2_host.py`
- `app/tts/qwen_character_runtime.py`
- `app/tts/chatterbox_runtime.py`
- `app/ai/model_runtime.py`
- `app/core/paths.py`
- `app/hardware/detect.py`
- `app/hardware/backend.py`
- `app/ui/hardware_page.py`
- `assets/frontend/premium_v2_backend_adapter.js`
- `tests/test_models_center_lifecycle.py`

Existing functionality is substantial and must be preserved. The Stage 6 baseline already has provider-specific installers, Qwen variant recognition, runtime checks, lifecycle bridge actions, background jobs, and model inventory regression tests. Step 1 must consolidate these sources, not replace the installers or redesign Premium V2.

## 3. Confirmed inventory gaps and risks

1. **Split inventory authorities.** `app/tts/model_registry.py` has a small manifest/catalog, while `PremiumV2Bridge._models_list` separately constructs a larger hard-coded inventory. The legacy Models page has another refresh implementation. These can disagree.
2. **Incomplete catalog coverage.** The registry catalog does not represent the complete set of Qwen variants, Audiobook AI, system providers, online providers, and separate runtime components.
3. **Manifest is not a complete registry.** `models.json` stores only installed IDs; it does not persist actual paths, file lists, versions, checksums, dependencies, health evidence, active references, or verification timestamps.
4. **No file-level inventory in the Premium V2 response.** The bridge reports some aggregate sizes and selected directory paths, but does not return a complete actual file list with per-file sizes.
5. **Model/runtime separation is inconsistent.** Qwen is partly separated; Chatterbox runtime and first-use model cache are described as shared, but not exposed as distinct inventory ownership.
6. **Ready-state classification is unsafe.** The frontend's `modelNeedsAttention` uses a status-text regex. Statuses such as `Installed · model files present` and `Installed and file-verified` can be counted as ready even though the specification reserves Ready for verified usable components.
7. **Audiobook AI readiness is presence-based.** Inventory/verify paths can treat the presence of `llama-server.exe` and a GGUF file as sufficient without a current functional runtime/inference check or robust file validation.
8. **Piper ownership needs normalization.** The bridge's verified list is based on provider-discovered paths, while the removable local list is restricted to the app Models root. Bundled and user-managed voices must remain distinct in the unified inventory.
9. **Storage scan error semantics are incomplete.** Some inaccessible paths collapse to zero bytes or an incomplete state. A missing directory and an inaccessible/disconnected configured location must not be conflated.
10. **Voice selector synchronization is indirect.** Premium V2 refreshes the model inventory and voice catalogue separately. Qwen selection/readiness checks also exist in Voice Studio provider-specific code. The unified status must become the shared source of truth without removing saved profiles or assignments.
11. **No consistent version/dependency/compatibility fields.** The inventory response does not consistently expose actual versions, dependencies, supported devices, health evidence, or last verification time.
12. **No storage ownership contract.** Shared runtimes and model weights need stable ownership IDs so aggregate storage totals cannot double-count files.

## 4. Step 1 implementation scope

- One authoritative persistent registry and inventory scanner.
- Actual, independently identifiable model variants and runtime components.
- Explicit component type: model, runtime, system provider, or online provider.
- Normalized statuses: Ready, Installed, Missing, Not configured, Partially installed, Unhealthy, Unsupported, and Location unavailable.
- Ready only after required files and runtime dependencies pass their defined checks; file presence alone is not readiness.
- Actual model and runtime paths, file records, sizes, version/dependency metadata where available, storage ownership, health result, and verification timestamp.
- Shared runtimes counted once; model weights remain separately attributable.
- Premium V2 Models Center and Voice Studio selectors consume the same authoritative inventory.
- Preserve existing installer, repair, background-job, saved-profile, project, and assignment behaviour.
- Preserve Premium V2 visual design; no UI rewrite.

Read-only path/file detail is part of the first inventory contract. Storage-root migration, cache relocation, and storage-management operations remain Step 2.

## 5. Required regression coverage

- Manifest absent, malformed, stale, and legacy migration.
- Each provider/model variant independently detected.
- Bundled versus user-managed assets.
- Model present but runtime missing.
- Runtime present but model missing.
- Partial and corrupt files.
- Functional verification failure must not be Ready.
- Qwen VoiceDesign Base dependency.
- Shared runtime storage counted once.
- Actual file sizes and exact paths.
- Inaccessible/disconnected storage reported as Location unavailable, not Missing.
- Provider/system/online components never represented as downloaded local models.
- Voice Studio selectors use the same status and never offer incompatible/unusable local models.
- Refresh is stable, non-blocking, and does not destroy selection or saved profiles.

## 6. CI wiring — current state

The workflow `.github/workflows/build-windows.yml` now includes the `stage-7/**` push filter and retains `workflow_dispatch`. This was verified directly in the workflow at checkpoint `ec8a15c0dbb26beda183720012eeb7843a5f0334` (workflow blob `72be0c5073726d66d0961225292c10ecf0aa57ec`). The earlier statement that the filter was absent is historical and stale; it must not be used to justify routing future canonical Stage 7 commits through the Stage 6 alias.

A push to the canonical Stage 7 branch is now the intended CI trigger. A matching-head test/package result must still be checked before acceptance.

## 7. Current status

**Step 1: IN PROGRESS — unified inventory implementation is present; matching-head CI and installed-app acceptance remain open.**

The source implementation and initial regression coverage are committed. The latest candidate is recorded in Section 10. Do not mark Step 1 complete until the candidate's full regression run, Windows packaging, and required installed-app acceptance evidence are recorded.

## 8. Next action

Run the full regression suite and Windows packaging checkpoint on the latest canonical candidate recorded in Section 10. Investigate any failures at their root cause, preserve existing working functionality, and rerun on the corrected head. Then perform actual installed-Windows-app Models Center acceptance for model/runtime paths, file inventory and sizes, individual model removal, shared-runtime removal with model weights retained, and post-removal refresh. Do not begin Step 2 until those closure checks are accepted.


## 9. CI validation branch alias

This alias was used historically because the earlier workflow did not include a `stage-7/**` push filter. The filter is now present, so the canonical Stage 7 branch is the authoritative CI branch. At checkpoint `ec8a15c0dbb26beda183720012eeb7843a5f0334`, the alias and canonical branch were identical. Subsequent regression-test commits were added only to the canonical branch; the alias is now behind and must not be treated as the latest candidate.


## 2026-11-05 — CI failure audit update

- Run #2390 failed on one stale Stage 4 provider-health source assertion. Updated the regression to assert the Stage 7 truthful status mapping (Missing, Not configured, Partially installed, Unhealthy, Unsupported, Location unavailable, Installed pending functional verification, Ready) instead of the retired generic Setup required label.
- The file-inventory pagination failure seen in #2386 was corrected in the subsequent safe-runtime-path implementation; the full #2390 regression run reports only the provider-health assertion as a failure.
- Successful checks retained: #2387 safe runtime path discovery; #2388 storage accounting and Voice Studio mapping; #2389 Voice Studio registry synchronization and exact runtime paths.
- CI workflow deliberately skips Windows packaging on ordinary feature-branch commits. A final commit carrying [artifact-checkpoint] is required to run the Windows packaging job after tests pass.
- Latest source commit before this checkpoint: b4923aec15370066a08d199d191e487778a46759.
- Stage 7 Step 1 remains OPEN pending matching-head full regression and Windows packaging success.


## 2026-11-05 — Production preview selector regression

- Packaged checkpoint #2393 built and verified the frozen executable and bundled assets, but its packaged SD/Music acceptance timed out waiting for Production-owned Chapter 2 selection.
- The older packaged checkpoint #2392 subsequently passed the same packaged SD/Music acceptance, confirming the timeout was not deterministic.
- Hardened the Production preview chapter selector to reconcile the visible chapter number with the stable chapter ID and content signature even when the number is unchanged. A valid preview is invalidated only when the actual chapter identity changes.
- Added dedicated selector identity reconciliation coverage and updated the existing integration contract to assert the new behavior.
- Latest regression checkpoint #2395: 1,196 tests passed; isolated Qt lifecycle regression passed; Stage 6 preflight passed (37 tests); frontend JavaScript syntax passed.
- New matching-head packaged acceptance and Windows installer verification are still required before Step 1 closure.
- Current source commit before package checkpoint: 089a2613dab94686b1f32395a794f7ee748e5217.


## 10. 2026-11-06 — canonical fast-forward, regression additions and closure status

### Canonical branch

- Canonical branch: `stage-7/step-1-model-registry-inventory`.
- The canonical branch was safely fast-forwarded from `6edd3be6c6e61705141630583d2e01ad564888c7` to tested checkpoint `ec8a15c0dbb26beda183720012eeb7843a5f0334` (23 commits ahead, 0 behind; no divergence; non-forced fast-forward).
- The CI alias `stage-6/stage-7-step-1-ci-validation` was identical to `ec8a15c0dbb26beda183720012eeb7843a5f0334` at that point.
- Additional Step 1 acceptance regressions were then committed to the canonical branch: `6492b2f4da07bd100649eee7775a099129dfbe3d` and fixture-isolation correction `d153751c7763e409cc84192b9b470f8b0faae379`.
- Latest canonical candidate before this ledger checkpoint: `d153751c7763e409cc84192b9b470f8b0faae379`. It is two commits ahead of the alias. The alias is not the latest tested candidate.

### Implementation verified by source inspection

- `app/tts/model_registry.py` provides the unified live `build_inventory()`, exact component paths, paginated `component_file_inventory()`, file sizes, status normalization, persisted inventory snapshot and Voice Studio availability projection.
- `app/ui/premium_v2_host.py` delegates Models Center inventory and file requests to the registry; model lifecycle operations refresh the inventory after completion and include the refreshed rows in the Background Job result.
- Premium V2 displays model/runtime/Python locations and exposes paginated file details with per-file sizes. The existing approved Premium V2 visual structure is retained.
- Existing lifecycle code uses component-owned path checks and blocks removal during active preview/generation/analysis or model lifecycle jobs.
- Source inspection is not a substitute for installed-Windows-app acceptance.

### Failure audit and prior CI evidence

- #2386: file-inventory pagination failure was corrected in the subsequent safe-runtime-path implementation.
- #2387: safe runtime path discovery — recorded successful.
- #2388: storage accounting and Voice Studio mapping — recorded successful.
- #2389: Voice Studio registry synchronization and exact runtime paths — recorded successful.
- #2390: failed on a stale Stage 4 provider-health source assertion. The assertion was updated to the current Stage 7 truthful status taxonomy rather than restoring the retired generic label. The full #2390 run reported this as its remaining failure.
- #2392 packaged SD/Music acceptance passed.
- #2393 packaged SD/Music acceptance timed out waiting for Production-owned Chapter 2 selection. This was not deterministic because #2392 passed the same acceptance.
- The selector identity reconciliation fix was committed as `089a2613dab94686b1f32395a794f7ee748e5217`.
- #2395: 1,196 regression tests passed; isolated Qt lifecycle regression passed; Stage 6 preflight passed (37 tests); frontend JavaScript syntax passed. This evidence is for source commit `089a2613dab94686b1f32395a794f7ee748e5217`, not the latest candidate. A new matching-head result is required.

### New acceptance regressions added to the canonical candidate

- Existing tests already cover individual Qwen model removal preserving sibling model folders, removal path containment, active-job protection and actual paginated file inventory sizes.
- `6492b2f4da07bd100649eee7775a099129dfbe3d` adds controlled temporary-directory tests for Qwen shared-runtime removal preserving all Qwen model weights and project data, Chatterbox shared-runtime removal preserving cached model assets, and inventory refresh reporting an individually removed Qwen model as `Missing` while retaining another model.
- `d153751c7763e409cc84192b9b470f8b0faae379` isolates the Chatterbox test's registry mutation so the test does not touch the real user settings manifest.
- These newly added tests have not yet been confirmed by a matching-head CI result. They use temporary fixtures; no real installed model files were used or removed.

### Closure assessment after Run #2400

The exact candidate `89ce5762a1194d8860e72d1cf4fb3b3b586d1ccc` completed successfully in [Actions run #2400](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42146555980). The run completed both CI jobs successfully, executed 1,199 regression tests with `OK`, and built the Windows application and release artifacts. All three uploaded artifacts are attached to that exact HEAD SHA and remain unexpired.

**The automated regression and matching-head package gates are PASSED.** Do not rerun or reopen those gates absent a new regression or code change.

The remaining Step 1 gate is actual installed-Windows-app Models Center acceptance. Verify actual model/runtime/Python paths, per-file and aggregate inventory sizes, an individual model uninstall, a shared-runtime uninstall while preserving model weights/cache, post-removal inventory refresh, and preservation of saved voice profiles, character assignments and project data.

**Current status: AUTOMATED CI + PACKAGE PASSED / INSTALLED-APP MODEL LIFECYCLE ACCEPTANCE PENDING. Do not proceed to Step 2 until this final gate is accepted.**
## 11. 2026-11-06 — Run #2400 matching-head regression and package acceptance

**Workflow:** [#2400 — Stage 7 Step 1 artifact checkpoint](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42146555980)  
**Run ID:** `42146555980`  
**Event:** `push`  
**Branch:** `stage-7/step-1-model-registry-inventory`  
**Run conclusion:** `success`  
**Exact HEAD:** `89ce5762a1194d8860e72d1cf4fb3b3b586d1ccc`  
**Run completion:** 6 November 2026, 02:16:31 UTC

The run's `head_sha` exactly matches the canonical candidate SHA. Both required jobs completed successfully.

### Regression job

- Job `tests` — success (job ID `127659321815`).
- Frontend JavaScript syntax validation — passed.
- Isolated native Qt lifecycle regression — passed.
- Stage 6 History/Task Manager preflight — passed.
- Full regression suite — **1,199 tests ran; OK**.
- No failed test/job is recorded in this run.

### Windows build and package job

- Job `build` — success (job ID `127660114384`).
- Installer JavaScript validation — passed.
- Prepare, validate and build application — passed.
- Frozen application verification — passed.
- Bundled voice assets and critical module verification — passed.
- Packaged Sound Design / Music Library acceptance (including Stage 5.3 generation UI) — passed.
- Core installer payload and functional HTML installer — built successfully.
- Original logo transparency and release hash generation — passed.
- Microsoft Defender executable scan — passed.
- Installer, SHA-256 manifest and portable application artifact uploads — all passed.
- Publish verified installer release — skipped by workflow policy; this run uploaded artifacts but did not publish a GitHub release.

### Artifacts uploaded by #2400

All three artifacts are unexpired at the audit time and are attached to this exact branch and HEAD SHA.

| Artifact | Artifact ID | Size |
|---|---:|---:|
| `Ryu-Audiobook-Installer-2400` | `13471707043` | 884,098,912 bytes |
| `Ryu-Audiobook-Portable-2400` | `13471781855` | 1,368,032,093 bytes |
| `Ryu-Audiobook-Release-SHA256-2400` | `13471632308` | 775 bytes |

Artifact ZIP digests reported by GitHub:

- Installer ZIP: `sha256:1c1d8b678db857bfccd7258501c23ae931fb1fec2ac0c96544283d1a827468d8`
- Portable ZIP: `sha256:73dfb899e8effb5ff3937bcd38688f8aafc30bebf7eb25c706d68533c67f85a1`
- SHA manifest ZIP: `sha256:d1e3f260a196f263f2145965d80a8c669f7e5e22f2ff7a6d070401495bd09e65`

The SHA-256 manifest ZIP was downloaded and its JSON content inspected. It contains nine file records, including both installer executables, the portable app executable and packaged logo/installer assets. The connector rejected direct download of the installer and portable artifact ZIPs because each exceeds its 512 MB file limit; their artifact metadata, run attachment, digests and upload log remain available. The manifest's two setup executable records are:

- `Ryu's Audiobook Setup.exe` — 884,098,748 bytes — SHA-256 `5b7d0a3d4c77fe029f154397d9d373535f0852ef76ea0d5a1cd43d731510df72`
- `Ryu's Audiobook Core Setup.exe` — 657,206,062 bytes — SHA-256 `7065e96a2a7b65a9b3755db2063c9aa327f3e2613ddd28e3c89f02667716f172`

Portable app executable — `Ryu's Audiobook.exe` — 12,082,466 bytes — SHA-256 `ba33c64d1bc3a4dd2addb7c87c687e0d4444c31a613e82bc971f03e3361ef9a5`.

### Updated Step 1 closure assessment

The following two formal gates are now satisfied:

1. Full automated regression suite passes on the exact candidate SHA, including the newly added Qwen/Chatterbox shared-runtime preservation and model-refresh tests.
2. Frozen Windows build/package and artifact/hash generation pass on that same exact candidate SHA.

**Remaining Step 1 gate: actual installed-Windows-app Models Center acceptance.** The CI packaged Sound Design/Music Library test does not prove actual user-machine model lifecycle behaviour. The following still need to be exercised in the installed/portable app:

- Verify real model/runtime/Python paths and actual paginated file records and sizes.
- Remove one individual model and confirm unrelated model weights remain.
- Remove one shared runtime and confirm its model weights/cache ownership is preserved.
- Refresh the inventory and confirm the removed component's actual status.
- Confirm saved voice profiles, character assignments and project data remain intact.

**Status: AUTOMATED CI AND PACKAGE ACCEPTANCE PASSED; STEP 1 REMAINS OPEN ONLY FOR INSTALLED-APP MODEL INVENTORY/LIFECYCLE ACCEPTANCE. Do not proceed to Step 2 until this final gate is accepted.**


## 12. 2026-11-06 — Step 1 formal closure and manual-acceptance waiver

**Decision:** Step 1 is formally ACCEPTED for progression to Stage 7 Step 2, at the user's explicit direction, with the installed-app manual acceptance gate waived for this stage.

### Accepted evidence

- Matching-head Run #2400 (89ce5762a1194d8860e72d1cf4fb3b3b586d1ccc) passed both required CI jobs.
- Full regression suite: 1,199 tests passed; frontend JavaScript syntax, isolated native Qt lifecycle regression, and Stage 6 History/Task Manager preflight passed.
- Frozen Windows application verification, bundled asset/critical module checks, packaged Sound Design/Music Library acceptance, installer build, functional HTML installer, Defender scan, release hash generation, and installer/portable/manifest uploads passed.
- All three artifacts were attached to the exact tested HEAD and were unexpired at the recorded audit.
- The three new controlled lifecycle regressions for Qwen shared-runtime preservation, Chatterbox cache preservation, and inventory refresh after individual model removal were included in the 1,199-test run.

### Explicitly waived / not claimed as passed

The user has chosen to proceed without the separate installed-Windows-app manual acceptance. Therefore, actual on-device confirmation of model/runtime/Python paths, file inventory and sizes, individual model uninstall, shared-runtime uninstall with model weights/cache retained, post-removal refresh, and preservation of saved profiles/assignments/projects is **WAIVED for Step 1 progression**. These behaviours are covered by source inspection and automated regression evidence to the extent recorded above, but are not represented as manually verified on the user's machine. Any issues discovered during later use remain actionable and must be fixed without reopening already-passed CI gates unless a regression or source change requires it.

### Final disposition

**STEP 1: ACCEPTED / CLOSED FOR STAGE PROGRESSION.** Automated regression and matching-head package gates: PASSED. Installed-app manual gate: USER-WAIVED, NOT RUN.

**Stage 7 Step 2 is authorized to begin on the canonical Stage 7 working line.** Preserve the Step 1 implementation and do not rerun its completed gates absent a relevant regression or code change.

## 2026-11-06 — latest combined-head confirmation

- The latest combined Stage 7 candidate is commit `0fc9d8189311419414746ffb23d89df9c65d116c`.
- Matching-head Windows Actions #2628 passed the full 1,258-test regression suite and the Windows build/package job.
- Frozen-app verification, packaged Sound Design/Music Library acceptance, installer/portable generation, SHA-256 manifest, Defender checks and artifact uploads passed on that exact commit.
- This later checkpoint includes the accumulated Step 1 inventory and Step 3 lifecycle source and regression coverage. It does not replace the explicit user waiver below.

**Current disposition:** STEP 1 ACCEPTED / CLOSED FOR STAGE PROGRESSION. Automated regression and packaged acceptance are current through #2628. Actual installed-app inventory and destructive lifecycle checks remain USER-WAIVED / NOT RUN, not manually passed.

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
