# Final Closure Ledger — Ryu's Audiobook Premium V2

**Audit date:** 26 October 2026  
**Working branch:** `fix/native-ui-font-scale-learning-ai`  
**Source baseline:** successful Build Windows App #1423, commit `314afd4199e5dca7ef677b0aed313bc668692614`, plus follow-up commits listed below.  
**Purpose:** this file supersedes older status statements that describe the pre-follow-up source. It does not claim manual Windows acceptance.

## Most recent source changes

- `42c5931f23d247366dabef57248fefb3a1804e63` — job/history JSON persistence now writes to unique same-directory temporary files, flushes and fsyncs before replacing the last known-good file. Generation `narration.json` and `chunk_manifest.json` use the generator's atomic JSON writer. Regression tests simulate replacement failure and check that prior data survives and temporary files are removed.
- `a44f4367bdad9846ac1ffc0cf604dd0a128388d5` — audiobook generation now rejects `.m4a` and `.mp3` output targets because the current assembler emits a chaptered `.m4b`. This prevents silently saving a different file extension than requested. Regression test covers the backend/assembler contract.
- Successful packaging baseline #1423: 701 tests passed; installer, portable application and SHA-256 manifest uploaded. Release-publication step skipped. See https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40219817108.
- Follow-up CI for later commits must be assessed by matching its head SHA to the branch head; a source commit alone is not proof of build success.

## Source-level work already present

- Qwen CUDA failure fallback and CPU runtime fallback; safer llama.cpp CPU fallback/download validation.
- Performance screen does not preserve prototype sample metrics as measured CPU/GPU/VRAM or benchmark results when telemetry is unavailable.
- Terminal operation history has its own `premium_v2_history.json` store, separate from the active queue and retained across queue visibility cleanup.
- Generation state uses resumable per-chunk checkpoints tied to a signature of current narration/voice/settings; invalid or missing WAV chunks are regenerated; assembly refuses missing/corrupt manifest chunks and validates the final M4B audio stream and minimum bitrate.
- Generation preflight rejects empty/ineligible chapters, and terminal job state distinguishes completed, failed and cancelled work.
- Project import is staged, source-preserving and transactional; duplicate source files are detected before project/job creation. Chapter fixtures cover multiple source formats and heading patterns.
- Chapter add/rename/delete/reorder/merge/split/clean/find/replace/bounded undo-redo, review and generation-exclusion paths are connected at source level; save failure blocks chapter switching.
- Saved manual character/dialogue assignment is source-validated and integrated into the synthesis routing path; automatic bulk AI line-level acceptance remains guarded.
- Player position saving and restore on metadata load are implemented in source. This still needs real-app restart acceptance.
- Model inventory and supported install/verify/repair/uninstall work via guarded background jobs. Refresh is local catalogue refresh, not a remote updater.
- Configured project-library and audio-output roots are supported in the existing settings/root path; legacy library locations remain visible, and storage reporting uses actual filesystem capacity.
- Project Trash/restore/purge handlers exist. Project-file writing is transactional/atomic.
- UI hardening includes stale-response guards, serialized job polling, stable rendering for unchanged sections, and progress-panel flicker remediation. Application-wide visual stability cannot be certified by static tests.

## True remaining code/product limitations

These must not be described as completed unless a separate implementation and test closes them:

1. **Output formats:** generation exports chaptered `.m4b` only. M4A/MP3 audiobook export is not implemented and is now rejected explicitly.
2. **Standalone project lifecycle:** standalone blank-project creation is unavailable; richer duplicate/archive/export/backup-restore workflow is not complete. Import creates an initial project.
3. **Hardware metrics:** live CPU/GPU/VRAM telemetry and a real benchmark are not implemented; the honest state is unavailable/not measured.
4. **Scanned PDF OCR:** image-only/scanned PDF OCR is not built in.
5. **Model actions:** remote model-update checking, universal default selection, and generic model test-generation are not implemented.
6. **Character AI:** bulk automated speaker suggestion acceptance remains prototype-only/guarded; manual source-backed assignment is available.
7. **Pronunciation:** the full per-profile test-result matrix, dictionary import/export, conflict tracking, and invalidation of already-generated audio require more work.
8. **Storage and secrets:** project-library and audio-output root selection exist, but model/cache root customization and related external-drive recovery acceptance are incomplete. Provider credentials are app-local/environment-backed, not in Windows Credential Manager.
9. **Database:** SQLite is a target/documented schema, not a deployed migration; existing project/job data uses file storage, JSON and QSettings.
10. **Diagnostics:** log redaction is best-effort, not a security guarantee.

## Manual Windows acceptance still required

CI builds and static regression tests do not prove the app is flicker-free, crash-free, or working with live providers and real audio on the user's PC. Until the exact installer/portable artifact matching the latest successful head SHA is tested, keep these acceptance items open:

- Install, launch, close and relaunch both installer and portable package; verify first-run and preserve/remove data behavior.
- Exercise all 15 destinations at 1920×1080, 1366×768 and 1280×720; check clipped controls, stale selections, UI flicker, duplicate event handling, stalls, WebEngine/bridge errors and crash logs.
- Import representative TXT, EPUB, searchable PDF and DOCX files; compare source text, chapter order/count and representative passage content. Test cancellation, corrupt/unsupported files, duplicate imports and low-disk errors.
- Run a real saved voice preview at supported durations; verify provider, profile, model, voice ID, playback and settings after restart.
- Generate a multi-chapter audiobook with real voice output; test pause/cancel/retry/restart, checkpoint reuse, selected character voices, pronunciation, cover/metadata, chapter navigation, duration and playback.
- Validate sound-design source assets, file-missing behavior, preview/final mix parity and licensed asset provenance.
- Confirm History survives restart/queue cleanup; confirm Player resume position and main/mini-player synchronization; inspect actual diagnostic exports before sharing.

## Closure rule

Mark a source item closed when the handler and regression test are present and the matching-head CI run passes. Mark a runtime item accepted only after the packaged Windows test is performed and recorded. Keep unsupported capability explicitly unavailable rather than simulating success. Do not claim zero flicker/crashes without repeated target-machine testing.
