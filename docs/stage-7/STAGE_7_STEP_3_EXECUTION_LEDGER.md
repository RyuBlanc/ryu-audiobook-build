# Stage 7 Step 3 — Model Lifecycle and Safe Uninstallation

Updated: 2026-11-06

## Scope and acceptance contract

Step 3 completes the Models Center lifecycle controls for app-managed local models and provider runtimes. It does not permit deleting user-owned books, generated audiobooks, saved voice profiles, character assignments, projects, settings, or shared model caches as a side effect of removing a runtime.

### Lifecycle commands and UI

- Models Center exposes install, repair, uninstall, verify, and inventory actions through the Premium V2 backend bridge.
- Uninstall UI performs a read-only preflight before confirmation and shows exact removal targets, file count, total bytes, installed dependents, and explicitly preserved data.
- A dependency conflict blocks the operation before confirmation; a stale preview is not an authorization. The background worker repeats preflight immediately before deletion.
- Destructive actions require the explicit "Confirm exact uninstall" action.
- Install/repair/uninstall operations run as background jobs, reject concurrent model lifecycle work, and block while preview, import, analysis, or generation jobs are active.
- Completion refreshes Models Center inventory, voice catalogs, and affected provider catalogs. Progress and failures are visible in Background Jobs.

### Ownership and preservation rules

- **Piper:** only the selected user-installed ONNX voice and its JSON sidecar may be removed. Other voices and bundled voices remain.
- **Kokoro:** only the app-managed Models/Kokoro directory may be removed; bundled assets remain.
- **Chatterbox:** the provider runtime is stored under the configured Provider Runtime root. Removal is blocked while installed components depend on that shared runtime. The Hugging Face model cache is not removed.
- **Qwen individual model:** only the exact selected model folder under Models/qwen3-tts is removed. The shared runtime and sibling model folders remain.
- **Qwen runtime:** only its private Python/venv/bootstrap marker/installer/log paths under the Provider Runtime root are removed. Downloaded Qwen weights under Models/qwen3-tts remain and become usable again after runtime reinstall.
- **Audiobook AI:** only its app-managed local runtime/model directory is targeted.
- All deletion paths reject symbolic-link targets, symbolic-link component roots, and nested symbolic links, and must remain within the selected component's owned directory.
- Saved voice profiles, voice references, character assignments, projects, source books, generated audiobooks, user settings, and unrelated cached model assets remain untouched.

## Root-cause fixes recorded during Step 3

- Rebuilt the corrupted uninstall execution method after repeated edits left a duplicated Chatterbox conditional and orphaned code that caused Python `IndentationError` before tests could import the bridge.
- Corrected Chatterbox runtime ownership: its target is under Provider Runtime, not assumed to be inside Models.
- Preserved raw target paths during preflight so symlink targets are not hidden by resolving paths too early.
- Compared dependency paths by filesystem identity to handle Windows 8.3 short paths versus long paths.
- Fixed the uninstall preview's one-shot generator being consumed by the symlink scan before file sizes were counted. The preview now materializes one list, validates it, and reports the same complete set.
- Aligned the Qwen model ownership check and test fixture with the actual Models/qwen3-tts component layout.
- Kept dependency preflight fail-closed and rechecked it immediately before removal.

## Automated verification

### Final regression checkpoint

- Workflow run: **#2591**
- Commit: `e20b5f6b0b5008e2c0cc3c0856bd513e0a1c0b71`
- Result: **SUCCESS**
- Full regression suite: **1,232 tests passed** in 56.239 seconds.
- Isolated native Qt lifecycle regression: passed.
- Frontend JavaScript syntax validation: passed.
- Focused Stage 6 History / Task Manager preflight: passed.
- Added UI contract test verifies exact-target preflight, byte/file counts, dependency and preservation display, explicit confirmation, async uninstall command, Background Jobs tracking, and post-operation refresh of Models, Voices, and provider catalogs.
- Added preservation tests verify Chatterbox and Qwen runtime removal leave voice profile files, character assignments, projects, and cached/model weight files intact.
- Additional lifecycle tests cover shared-runtime dependency blocks, exact component ownership, Qwen runtime versus weight separation, active-job guards, and symbolic-link rejection.

Historical failed runs #2576–#2588 are retained in GitHub Actions history. The syntax, ownership, path alias, preview iterator, dependency and fixture defects identified by those runs were corrected in later commits. They are not accepted as passing runs; the final current-head regression checkpoint above is the green evidence.

## Remaining acceptance before Step 3 closure

- Run the matching-head Windows packaged acceptance checkpoint, including frozen application verification, packaged UI acceptance, installer/portable generation, SHA-256 manifest, Defender scans, and artifact uploads.
- Confirm no regressions against the already accepted Step 2 storage baseline.

Do not mark Step 3 closed until the matching-head package checkpoint succeeds.
