# Backend API Map — Premium V2

**Audit snapshot:** 20 October 2026
**Audited source commit:** `eca9cf1a8330e2dcfce697f66233a73740e25ae0`
**Host:** PySide6/Qt WebEngine + QWebChannel, `app/ui/premium_v2_host.py`
**Adapter:** `assets/frontend/premium_v2_backend_adapter.js`

## Current bridge contract

The dispatcher accepts an allow-listed command name and JSON object payload. Successful calls return `{success: true, data: ...}`; failures return `{success: false, error: {code, message}}`. Unknown commands log a warning and return `not_connected`. The renderer does not receive an arbitrary shell-execution command.

The current host registers **61 command handlers**. Static adapter inspection found **54 distinct literal `call('command.name')` names**; other actions use delegated handlers/bootstrap or are not yet mapped. These counts are inventories, not acceptance counts.

### Registered command inventory

| Domain | Registered commands and current status |
|---|---|
| Application | `app.get_info` → `_app_info` (connected); `app.get_capabilities` → `_capabilities` (connected). |
| Project/library | `project.list`, `project.open`, `project.get_active`, `project.rename` have handlers. `project.create` is explicitly unavailable and is not registered; the supported creation path is import. Duplicate/archive/delete/export/backup-restore are not implemented as bridge commands. |
| Import | `import.choose_file`, `import.start` have real handlers; source parsing/chapter detection use existing Python services. Dedicated validate/report/retry commands are not registered. |
| Chapters | `chapter.list`, `chapter.update`, `chapter.clean`, `chapter.add`, `chapter.delete`, `chapter.reorder`, `chapter.split` have handlers. `chapter.split` is now explicitly present in the capability map. Merge/re-detect/review-state/skip/undo/redo/find-replace/preview commands are not registered as separate operations. |
| Voices | `voice.list`, `voice.save`, `voice.delete`, `voice.import_reference`, `voice.select`, `voice.preview` have handlers. Provider readiness, secure credential management and Premium cloud candidate-generation commands are absent/unavailable. |
| Character cast/library | `character.list`, `character.analyze`, `character.assign`, `character.update`, `character.delete`, `character_library.list`, `character_library.save`, `character_library.delete`, `character_library.import` have handlers. Per-line speaker assignments and the test/merge/validation operations in the full specification are not persisted by this bridge. |
| Pronunciation | `pronunciation.list`, `pronunciation.save`, `pronunciation.delete`, `pronunciation.analyze` have handlers. There are no registered bulk voice-test matrix, per-profile test-result persistence, import/export or conflict/invalidation commands. |
| Production/preview | `production.generate_book`, `production.preview`, `sound.preview_book` have handlers. There are no separate registered `production.preflight`, chapter-only generation, package-only rebuild or chapter retry commands in this bridge surface. |
| Jobs | `job.list`, `job.pause`, `job.resume`, `job.cancel`, `job.clear_completed` have handlers. Retry, set priority, pause all, resume all and dependency-management commands are not registered as independent bridge commands. |
| History/player | `history.list`, `player.get_active`, `system.open_output` have handlers. History log-detail/export/retry/resume operations and backend playback-position/bookmark commands are not registered. HTML audio controls handle transport, but durable position persistence is not evidenced. |
| Models/performance | `models.list`, `models.install` are registered; unsupported per-model update/verify/repair/uninstall actions are guarded in the adapter. `performance.info` has a handler but is truthfully advertised with capability `False`; live telemetry remains unavailable. |
| Settings/diagnostics | `settings.get`, `settings.save`, `diagnostics.check`, `diagnostics.export_logs` have handlers. Custom storage-root selection and secure provider credential actions are not connected. Diagnostic export redaction is best-effort. |
| Sound design | `sound.catalog`, `sound.import`, `sound.assign`, `sound.save_manifest`, `sound.cues.get`, `sound.cues.save`, `sound.cues.clear`, `sound.chapter_bgm.get`, `sound.chapter_bgm.save` have handlers. Runtime mix/output checks remain acceptance work. |

## Capability map

| Command | Capability state | Evidence / action |
|---|---|---|
| `project.create` | `False` | No dispatcher handler; create/open through the import flow instead. |
| `performance.info` | `False` | Handler exists to return unavailable/unmeasured telemetry; no fake CPU/GPU/VRAM values should be surfaced. |
| `chapter.split` | `True` after Stage 1 correction | Dispatcher handler and adapter call already existed; missing capability flag is corrected and covered by a contract assertion. |
| Most other registered commands in `_capabilities` | `True` | Means the host advertises the operation as implemented, not that every related UI control or Windows runtime path has passed acceptance. |

## State and persistence observed in source

- Project records and chapter content are managed through `app/core/project.py`; editor saves update the project and its state JSON.
- Active project selection is held in `QSettings` under `project/active_folder`.
- User settings are read/written by the settings bridge and `QSettings`; do not assume every visible field is wired until mapped individually.
- Premium V2 job records are stored in `settings_root()/premium_v2_jobs.json` using temporary-file replacement. On startup, jobs recorded as queued/running/pause-requested/cancel-requested/retrying are changed to a recoverable interrupted/failed state. The worker does not simply continue running after process restart.
- `history.list` currently returns the same in-memory/durable job rows used by the job manager. Clearing completed manager entries marks them hidden, so the history screen is not yet an independently persisted audit subsystem.
- The repository documents SQLite as a target schema; this audit did not find a deployed SQLite migration/store for Premium V2 project, job and history state.
- The adapter polls backend jobs every 1.5 seconds. This is backend polling, not a durable event stream.

## Error and safety requirements

1. Validate payload types, lengths and file paths in Python; never trust imported book text as executable content.
2. Keep secrets out of JavaScript, project JSON and ordinary settings. Secure provider-specific credential storage remains unimplemented.
3. Report missing providers/models and unsupported actions without simulated success.
4. Report progress only from backend generation/job data; validate output before showing final completion.
5. Keep capability flags synchronized with dispatcher handlers and add an integration assertion for command/capability parity.
6. Keep task-manager clearing separate from durable history retention as a dedicated history service is implemented.
7. Add request IDs/idempotency, complete schema/error contracts and state-change events where the architecture needs them; these are not complete in the current bridge.

## Immediate implementation order

1. Finish the stage-one screen/control/handler matrix and remove capability drift.
2. Eliminate legacy demo code paths that can still report success or overwrite backend-fed areas.
3. Close Stage 2 import/cleanup/chapter operations and persist review/skip state.
4. Complete Stage 3 speaker assignments and Stage 4 profile/preview consistency.
5. Complete shared job recovery/history, model actions, player state and settings persistence in the relevant roadmap stages.
6. Add an explicit integration test for each connected control and manual acceptance for operations that cannot be covered by unit tests.