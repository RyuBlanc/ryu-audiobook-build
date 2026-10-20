# Known Limitations — Ryu's Audiobook Dragon Studio

**Audited:** 20 October 2026
**Current code baseline:** `eca9cf1a8330e2dcfce697f66233a73740e25ae0` on `fix/import-qa-speaker-hover-hardware`
**Open PR:** [#15](https://github.com/RyuBlanc/ryu-audiobook-build/pull/15), open and unmerged.

This document records actual source-level limitations. A supported bridge handler does not imply all related UI controls have passed runtime acceptance.

## Application and integration limitations

| Area | Current behavior | Acceptance implication |
|---|---|---|
| Project creation | `project.create` is advertised as unavailable and has no dispatcher handler. The supported path is importing source material, which creates/opens a local project. | Do not describe a standalone New Project action as connected. |
| Hardware telemetry | `performance.info` is marked unavailable. Do not invent CPU, GPU, VRAM or benchmark values. Legacy HTML benchmark behavior still requires protection from fake-success paths. | Live telemetry and benchmarking remain unaccepted. |
| Secure provider credentials | Credential management is not connected to a secure provider-specific credential store. | Do not enter or expect API keys to persist through these controls. |
| Premium cloud voice candidates | Premium cloud candidate generation is not connected to a provider endpoint. Guarded actions must not generate mock candidates. | Use only providers/profiles whose backend path is actually configured. |
| Chapter review status | Review status is not yet supplied by the chapter backend. | Review filtering cannot be relied on until review state is persisted. |
| Per-line AI speaker suggestions | Per-line AI speaker suggestions are still prototype-only. | Do not treat line suggestions as confirmed or saved speaker assignments. |
| Dialogue-line speaker assignment | Dialogue-line speaker assignment is not persisted by the current backend. | Saved cast voice assignments are distinct from assigning a speaker to each dialogue line. |
| Custom storage roots | Custom project-library and audio-assets root selection is not implemented. | Current roots remain the configured local storage locations. |
| Per-model actions | The model screen's per-model update/verify/repair/uninstall/default-selection/test actions are not all connected to backend operations. Qwen install/repair uses the real `models.install` job; unsupported actions must remain guarded. | Do not treat unsupported model actions as successful. |
| SQLite | `docs/PREMIUM_V2_DATABASE_SCHEMA.md` describes a target schema, not a deployed migration. Project data/state and Premium V2 job records currently use existing project/state files, QSettings and `premium_v2_jobs.json`. | Do not claim SQLite persistence or migrations are complete. |
| Durable jobs/history | Job rows persist and unfinished rows are marked recoverable/failed on restart. `history.list` currently reads the same job rows, not a separate immutable history store. | Restart recovery, checkpoint reuse and history independence still require test coverage. |
| Player state | Browser audio transport can operate on the selected output, but durable playback position/bookmarks and complete chapter-position recovery are not evidenced. | Verify seek, duration, chapter navigation and restart resume with real generated output. |
| Prototype leftovers | The approved HTML still contains static example content, legacy demo renderers/timers and some `localStorage` usage. The adapter guards selected operations, not proof that all legacy code paths are gone. | Continue control-by-control mapping and regression tests; never report prototype state as production success. |
| Sanitized log export | The implementation has a save dialog, bounded log collection, recent-job summary, atomic writing and best-effort redaction of common token/key/email/home-path patterns. | Redaction is not a complete security guarantee. Review actual export files before sharing them. |

## CI evidence as of this audit

- GitHub Actions [Run #731](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39397963882) completed successfully for commit `eca9cf1a8330e2dcfce697f66233a73740e25ae0`.
- The run log reports **308 tests passed** (`Ran 308 tests in 34.431s`) and the Windows installer and portable artifacts uploaded successfully.
- Installer artifact: [Ryu-Audiobook-Installer-731](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39397963882/artifacts/12253986738).
- Portable artifact: [Ryu-Audiobook-Portable-731](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39397963882/artifacts/12254815829).
- The installer release-publication step was not run; no GitHub Release is claimed.

## Windows acceptance still pending

CI does not replace interactive Windows acceptance. The following remain pending until performed on the target machine and recorded:

- Install and launch both installer and portable builds.
- Visit all 15 destinations and exercise real project import/edit, voice preview, character assignment, pronunciation, sound design, production, player, history, models, performance, settings and help actions.
- Verify a real preview uses the selected saved profile and exact requested duration.
- Generate a short real audiobook; validate chapter order, actual duration, output path, metadata/cover and playback.
- Exercise pause, resume, cancel, retry and restart recovery with real jobs and installed/offline providers.
- Verify project/settings/job state after restart and inspect diagnostics exports for data leakage.
- Compare visual layout at 1920×1080, 1366×768, 1280×720 and resized/narrow supported windows.

**Release gate:** Do not describe Stage 8.2.11 as fully accepted. The current source still requires the Windows manual acceptance above and the remaining items in `docs/STAGE_1_GAP_REGISTER.md`.