# Stage 7 Step 2 — Installation Locations, Storage and Model File Management

**Scope:** MOD-01–MOD-04, focused on installation locations, storage management and model-file management.  
**Branch:** `stage-7/step-2-storage-management`  
**Baseline:** Step 1 closure commit `b361ac0fc191592e2988f7977587ee82d917774e`.  
**Status:** IN PROGRESS — baseline audit recorded; implementation and acceptance gates not yet complete.

## 1. Step 2 outcome

Give the user reliable control and visibility over where model weights, provider runtimes, model caches and temporary working files live. Show actual paths and actual disk usage, and make relocation recoverable. Do not break the Step 1 unified registry, installed-model discovery, provider selectors, saved voice profiles, character assignments, projects or generated user assets.

This step is storage/location management. The full uninstall/lifecycle closure remains Step 3; Step 2 must nevertheless prevent migration/cleanup from damaging active jobs or user-owned data.

## 2. Required functional behaviour

### MOD-01 — Authoritative installation locations and file inventory

- Every installed or partially installed component must report its actual model, runtime, Python executable, cache and temporary locations where applicable; do not infer a path from a default if the real path is known.
- Keep model weights, shared runtime, Python runtime, provider cache and temporary/download staging as distinct component roles. A shared runtime must not be represented as a model-weight folder.
- Reuse Step 1's live inventory and paginated file inventory. Each file row must include full path, filename, role, exact byte size and modification time; aggregate file count and bytes must agree with the enumerated files.
- Count physical files once when roots overlap. Do not follow symlinks or traverse outside the selected managed roots.
- Preserve truthful states including Installed, Ready, Missing, Partially installed, Unhealthy and Location unavailable. A disconnected drive must not turn a previously registered model into an uninstalled model.

### MOD-02 — Storage location selectors and capacity

- Provide independently configurable locations for the managed Models root, provider/runtime storage, model download/cache storage and temporary/staging files. Existing Project Library and Audio Assets selectors must continue to work unchanged.
- Show the exact active path, whether it is currently available/readable/writable, total capacity, used capacity and free capacity from the actual filesystem. Show component/model bytes separately from filesystem capacity; never label one as the other.
- Provide Choose/Browse, Use default, Open Folder and Copy Path actions where the path is applicable. Refresh must re-read the filesystem and registry, not display stale cached values.
- Validate absolute paths, existing destination/parent, read/write access, free space and destination/source overlap before applying a new root.
- Preserve current default locations and discover existing installations without forcing users to download them again.
- Keep the existing Premium V2 visual language and Settings layout; add controls without redesigning unrelated screens.

### MOD-03 — Safe relocation / migration

- A location change for a non-empty managed root is a migration, not merely a settings-string update.
- Preflight must calculate required bytes, destination free space plus a safety reserve, source accessibility, destination writability, active jobs, duplicate/overlapping paths and any existing target data.
- Block migration while model downloads/installs/repairs/uninstalls, inference, previews or other jobs are using affected paths. Explain which job prevents migration.
- Copy into a unique staging directory on the destination filesystem. Never move/delete the source first.
- Verify the staged copy before switching: file count, total bytes, relative paths and per-file content hashes for files copied. Reject incomplete or changed source files.
- Switch the configured root only after verification succeeds. Use an atomic same-volume rename/switch where supported; otherwise use an explicit recoverable journal/marker and never expose a half-copied root as active.
- Keep the original source intact until the new root has been reopened and a fresh inventory/health scan confirms the expected components. Only then may the user explicitly confirm source cleanup.
- On any copy, hash, disk, settings-write, switch or post-switch verification failure, restore the previous active root and leave the original data intact. A retry must detect/reuse or safely discard only its own staging directory.
- Prevent duplicate downloads when a model already exists at the configured or previously registered location. Reconcile inventory before scheduling a download.
- Persist migration state so interrupted migrations can be recovered after application restart. Report source, destination, progress, verified bytes/files, failure reason and recovery action.

### MOD-04 — External-drive recovery and safe cleanup

- If a configured drive is disconnected, show Location unavailable with the preserved configured path and last-known inventory metadata. Do not silently fall back to an empty default, mark models Missing, overwrite the setting or initiate duplicate downloads.
- On reconnect, refresh and reconcile the same path; restore Installed/Ready only after live files and runtime checks are confirmed.
- Cache/temp cleanup must use explicit app-owned allowlisted directories and safe age/state rules. It must never remove model weights, runtime environments, source books, original imports, completed audiobook exports, saved previews, voice-reference recordings, profiles, character assignments, project files, active downloads, active job workspaces or resumable checkpoints.
- Show a dry-run estimate (files and bytes) and exact target paths before cleanup. Cleanup must be cancellable and report what was actually removed; no broad recursive deletion of a parent shared with user data.

## 3. UI requirements

### Settings → Local storage
- Keep current Project Library and Audio Assets rows.
- Add Models, Provider Runtime, Model Cache/Downloads and Temporary/Staging rows with current path, availability, filesystem total/used/free and actions.
- Make it clear whether changing a root will simply change the destination for future downloads or migrate existing content. For non-empty roots, require the migration flow.
- Show a concise warning for external/removable drives and a restart requirement if runtime modules capture configured paths at process startup.

### Models Center
- Keep Step 1 model cards/table and expanded per-file inventory.
- Show model path separately from runtime/Python/cache path.
- Add per-component Open Folder and Copy Path; show path unavailable distinctly from component missing.
- Add storage summary and a refresh/reconcile action. Migration progress and errors must be visible and truthful; do not block the UI thread.

### Migration confirmation / recovery
- Show source and destination, estimated bytes, free space, affected components and active-job blockers.
- Show staging/copy/verification/switch/rollback phases and current file/byte progress.
- Never show success until settings persistence and a post-switch inventory verification both succeed.

## 4. Baseline audit (Step 2 branch)

- `app/core/paths.py`: Project Library and Audio Assets are configurable; `models_root()` remains fixed at `app_root()/Models`. Voices, Settings, Soundtracks, Audio Library and default temp-like locations remain under the app profile.
- `app/tts/qwen_character_runtime.py`: Qwen runtime, private Python and all model directories are module-level constants rooted under `models_root()`; download/install functions write directly into those constants.
- `app/tts/chatterbox_runtime.py`: Chatterbox runtime is rooted under `models_root()`; Hugging Face cache is also rooted under `models_root()/huggingface`; some Python bootstrap temp data is under Windows LocalAppData.
- `app/tts/model_registry.py`: Step 1 provides live component paths, per-file inventory and aggregate storage bytes. It currently resolves model roots through `models_root()`; preserve this single inventory source.
- `app/ui/settings_page.py`: existing folder selector validates a harmless write probe and displays free/total capacity for Project Library and Audio Assets only. It does not migrate non-empty folders.
- `tests/test_storage_root_selection.py`: existing tests cover absolute configured roots, legacy project visibility, routing new imports/exports, actual filesystem capacity and writable-folder validation. Extend rather than replace these tests.
- `app/ui/premium_v2_host.py`: Models Center inventory and lifecycle are already wired. Do not duplicate the registry or disturb Step 1 lifecycle protections.

## 5. Test-first implementation order

1. **Storage-root contract:** tests for configurable Models/runtime/cache/temp roots, defaults, absolute-path validation, disconnected paths and backwards compatibility of all existing roots.
2. **Storage accounting:** tests for actual filesystem total/used/free, component bytes vs disk capacity, overlapping roots/no double count, inaccessible paths and accurate per-file totals.
3. **Migration engine:** isolated temporary-directory tests for preflight, low space, read-only/missing drive, source/destination overlap, active-job blocking, staged copy, hash mismatch, settings-write failure, atomic switch, interrupted migration recovery and rollback.
4. **Runtime integration:** route Qwen model/runtime/Python, Chatterbox runtime/HF cache and other model providers through the configured roots; prove new installs land there and existing installations remain discoverable without redownload.
5. **UI integration:** selectors, open/copy path, availability and capacity refresh, migration confirmation/progress/recovery; preserve current Premium V2 style.
6. **External-drive and cleanup protection:** disconnect/reconnect, duplicate-download prevention, dry-run cleanup, and preservation tests for all protected user data and active work.
7. **Regression and package acceptance:** run focused storage/model tests first, then full regression suite and frozen Windows build/package only after source changes stabilize. Reuse Step 1 gates unless a relevant regression or code change requires them.

## 6. Acceptance matrix

| ID | Scenario | Required result |
|---|---|---|
| S2-01 | Default install / upgrade | Existing model/runtime paths discovered; no forced redownload |
| S2-02 | Select each managed root | Absolute path persisted and displayed accurately |
| S2-03 | Filesystem capacity | Total/used/free match actual filesystem; component bytes separate |
| S2-04 | File inventory | Per-file bytes sum to aggregate; overlaps counted once |
| S2-05 | Destination unavailable/read-only | Change rejected; active setting and source untouched |
| S2-06 | Insufficient free space | Migration blocked before copying; actionable estimate |
| S2-07 | Successful migration | Staged copy verified; root switched; fresh inventory confirms components |
| S2-08 | Copy/hash/settings/switch failure | Previous root remains active; source intact; recovery state recorded |
| S2-09 | Interrupted migration/restart | Resume or rollback safely; no ambiguous active root |
| S2-10 | Active download/inference/preview | Migration blocked until affected job is terminal |
| S2-11 | External drive disconnect | Location unavailable; metadata preserved; no fallback or duplicate download |
| S2-12 | External drive reconnect | Same installation rediscovered and verified |
| S2-13 | Existing model at old path | Inventory reconciliation prevents duplicate download |
| S2-14 | Cache/temp cleanup dry run | Exact allowlisted targets and bytes shown; no deletion |
| S2-15 | Cache/temp cleanup execution | Only eligible app-owned cache/temp files removed |
| S2-16 | Protected user data | Models, runtimes, books, exports, previews, references, profiles, assignments, projects and checkpoints preserved |
| S2-17 | UI responsiveness | Inventory/migration runs in background; progress truthful; UI remains responsive |
| S2-18 | Existing storage settings | Project Library and Audio Assets behavior and legacy project discovery unchanged |

## 7. Closure rules

Step 2 is not complete until all acceptance-matrix items are either passed with test evidence or explicitly documented as a user-approved waiver. A passing unit test alone does not prove installed-Windows behavior. Do not mark a migration successful before post-switch inventory verification. Do not begin Step 3 uninstall-safety work until Step 2 storage and relocation gates are closed.

**Current disposition:** Step 2 branch established; baseline audit and acceptance contract documented. Implementation has not yet begun; all Step 2 acceptance items remain open.


## 8. Implementation progress — 2026-11-06

### Completed in the initial implementation slice

- Added independent configured roots for model weights, provider runtimes, model cache/downloads and temporary/staging files while retaining the legacy default layout.
- Routed Qwen model weights separately from its configurable runtime/Python root; default paths remain the existing `Models/qwen3-tts` layout.
- Routed Chatterbox runtime and Hugging Face cache through the managed runtime/cache roots; default paths remain compatible with existing installations.
- Added Settings → Local storage rows for Models, Provider Runtime, Model Cache / Downloads and Temporary / Staging, including Choose, Use default, Open, Copy Path and actual used/free/total filesystem capacity.
- Added a safety guard: changing a non-empty managed root or replacing an unavailable configured root is refused until the verified migration workflow exists. This prevents a settings-only path change from making installed models appear missing. Project Library and Audio Assets selection remain unchanged.
- Added regression coverage for independent root configuration, legacy defaults, relative-path fallback, capacity reporting, and refusal to orphan data or silently replace an unavailable root.

### Remaining before Step 2 closure

- Implement the verified staging-copy, content-hash verification, atomic switch, journal/recovery and rollback migration engine.
- Integrate all model/runtime/cache/temp writers and readers, including temporary download/bootstrap staging, without moving user-owned previews or source/output files.
- Add active-job/download/inference guards, external-drive disconnect/reconnect reconciliation and duplicate-download prevention.
- Implement safe cache/temp cleanup dry-run and protected-data tests.
- Complete Models Center storage summary/relocation UI and responsive background progress/recovery.
- Run focused storage/migration tests, full regression and matching-head packaged acceptance; audit and fix every failure.

**Current status: INITIAL ROOT-CONFIGURATION SLICE IMPLEMENTED; MIGRATION AND FULL ACCEPTANCE OPEN. Do not treat Step 2 as complete or proceed to Step 3.**


### Verified migration engine implementation — 2026-11-06

- Added `app/core/storage_migration.py` with path-overlap checks, source/destination validation, active-job callback gate, destination free-space reserve, app-owned staging directory, per-file SHA-256 verification, source-stability re-verification before switching, journal state updates, settings callback, post-switch validation and rollback callback.
- The source tree is retained after successful migration. A failed post-switch validation restores the configured source root and removes only the destination copy created by that migration; source data is not deleted.
- Added `tests/test_storage_migration.py` covering successful copy/source retention, non-empty destination and overlap rejection, active-job and low-space rejection, post-switch validation rollback and symlink rejection.
- This is the engine/test slice only. It is **not yet wired into the Settings or Models Center UI**, and journal restart recovery, all-provider writer routing, full job-path conflict detection, removable-drive reconciliation and safe cleanup remain open.
- CI for the exact wording correction is running as #2420; migration engine/test commits are running as #2421–#2424. Do not infer pass status until each matching-head run completes.

**Updated disposition:** migration engine and initial safety tests added; UI/runtime integration and end-to-end acceptance remain open. Step 2 remains IN PROGRESS.
