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

## 6. CI wiring issue to resolve before the first Step 1 checkpoint

The Stage 6 baseline workflow `.github/workflows/build-windows.yml` has push filters for `stage-6/**`, but does not yet include `stage-7/**`. It supports `workflow_dispatch`. Ensure Stage 7 has a reliable CI trigger before treating any Step 1 commit as verified. Do not alter the default branch or start an unrelated main-branch package build just to work around this.

## 7. Current status

**Step 1: IN PROGRESS — source audit completed; implementation and verification not yet completed.**

No Step 1 source code changes or Step 1 test runs are recorded in this ledger. Do not mark Step 1 complete until the unified implementation, regression tests, matching-commit CI, and required packaged/runtime acceptance evidence are recorded.

## 8. Next action

Implement the authoritative registry/scanner and integrate the Premium V2 bridge and Voice Studio selectors. Add focused tests first, then run the focused model lifecycle/inventory tests, the full regression suite, and a matching-head Windows build/package checkpoint. Investigate and fix root causes of any failures before proceeding to Step 2.


## 9. CI validation branch alias

The repository's default-branch Actions workflow currently has a `stage-6/**` push filter but not a `stage-7/**` filter. To obtain matching-commit CI without changing the default branch or triggering an unrelated main package build, `stage-6/stage-7-step-1-ci-validation` mirrors the Stage 7 working branch for CI events. The canonical Stage 7 branch must be advanced to the exact tested commit SHA after each validation checkpoint. This alias is only a workflow-trigger compatibility measure; Stage 7 scope and acceptance remain unchanged.


## 2026-11-05 — CI failure audit update

- Run #2390 failed on one stale Stage 4 provider-health source assertion. Updated the regression to assert the Stage 7 truthful status mapping (Missing, Not configured, Partially installed, Unhealthy, Unsupported, Location unavailable, Installed pending functional verification, Ready) instead of the retired generic Setup required label.
- The file-inventory pagination failure seen in #2386 was corrected in the subsequent safe-runtime-path implementation; the full #2390 regression run reports only the provider-health assertion as a failure.
- Successful checks retained: #2387 safe runtime path discovery; #2388 storage accounting and Voice Studio mapping; #2389 Voice Studio registry synchronization and exact runtime paths.
- CI workflow deliberately skips Windows packaging on ordinary feature-branch commits. A final commit carrying [artifact-checkpoint] is required to run the Windows packaging job after tests pass.
- Latest source commit before this checkpoint: b4923aec15370066a08d199d191e487778a46759.
- Stage 7 Step 1 remains OPEN pending matching-head full regression and Windows packaging success.
