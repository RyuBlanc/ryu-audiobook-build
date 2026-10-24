# Known Limitations — Ryu's Audiobook Dragon Studio

**Audited:** 24 October 2026 (Models Center/job-monitor follow-up)
**Current code baseline:** `eca9cf1a8330e2dcfce697f66233a73740e25ae0` on `fix/import-qa-speaker-hover-hardware`
**Open PR:** [#15](https://github.com/RyuBlanc/ryu-audiobook-build/pull/15), open and unmerged.

This document records actual source-level limitations. A supported bridge handler does not imply all related UI controls have passed runtime acceptance.

## Application and integration limitations

| Area | Current behavior | Acceptance implication |
|---|---|---|
| Project creation | `project.create` is advertised as unavailable and has no dispatcher handler. The supported path is importing source material, which creates/opens a local project. | Do not describe a standalone New Project action as connected. |
| Hardware telemetry | `performance.info` is marked unavailable. Do not invent CPU, GPU, VRAM or benchmark values. Legacy HTML benchmark behavior still requires protection from fake-success paths. | Live telemetry and benchmarking remain unaccepted. |
| Secure provider credentials | ElevenLabs API-key setup is connected and stores the key in app-owned local settings (`elevenlabs.json`) or reads `ELEVENLABS_API_KEY` from the environment. A Windows secure provider-specific credential store is not integrated, so the key is not stored in the Windows Credential Manager or another OS-backed secret vault. | The key persists locally, but users should protect their Windows account and app data; do not describe this as OS-vault-backed secret storage. |
| Premium cloud candidate generation | ElevenLabs Voice Design candidate generation and creation use real provider endpoints when a valid API key and online access are available. This is a provider-specific integration, not a universal cloud voice-design API; local Qwen VoiceDesign uses the installed Qwen runtime. | Show provider-specific setup/error status and never invent candidates when the provider is unavailable. Online calls may consume provider quota. |
| Chapter review and generation inclusion | Review status is persisted in `chapters.json`; older chapter records default to `needs_review`. A separate `skip_for_generation` flag defaults to false and is persisted per chapter. The Review filter uses review state; the contextual chapter action can toggle review or skip state. Generation excludes flagged chapters while preserving their text. Project state, job result data and progress messages distinguish empty chapters from intentionally excluded chapters. | Backend plumbing and regression contract are in place; interactive Windows save/reload and generated-output acceptance remain pending. Review status never implicitly skips a chapter. |
| Automatic per-line AI speaker suggestions | Automatic per-line AI speaker suggestions remain prototype-only; confidence labels and bulk acceptance are not treated as verified evidence. | Do not treat an AI suggestion as a confirmed speaker assignment. |
| Manual dialogue-line speaker assignment | Manual source-backed dialogue speaker assignments are persisted after exact passage validation against saved chapter text. | Assignments require an unambiguous source passage and saved character; synthesis integration and interactive Windows acceptance remain to be verified. |
| Custom storage roots | Custom project-library and audio-assets root selection is not implemented. | Current roots remain the configured local storage locations. |
| Per-model actions | Inventory, install, verify, repair and uninstall are connected for supported app-managed local components. Install/repair/uninstall use real background jobs and refresh model/voice catalogues at completion. Remote model update checks, universal default-selection and model test-generation are not established as connected; the Check Updates button only refreshes the local catalogue. | Do not show remote-update success or fake test-generation; complete actual Windows model/voice/narration acceptance. |
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

## Models Center status update — 24 October 2026

- The current branch implements `models.list/install/verify/repair/uninstall` for supported managed components. Lifecycle operations run as background jobs, prevent conflicting model/audio operations, and refresh the inventory and relevant Voice Studio catalogues when they finish.
- Storage accounting now includes nested Chatterbox files and the Qwen isolated Python runtime/metadata while keeping each Qwen model-weight directory separately counted. Build #1162 passed 530 automated tests for this change; its package job was superseded by the follow-up job-monitor fix, so its artifact is not the final acceptance candidate.
- A regression guard was added for the race where a background job is already terminal during the first poll. The current branch workflow must validate this follow-up before that latest package can be considered passed.
- Still unsupported: true live CPU/GPU/VRAM telemetry. Still requiring target-PC acceptance: install/repair/remove models; provider selector refresh; real preview, audiobook narration and playback; installer and portable first-run.


## 2026-10-24 validation boundary

Build #1164 previously passed 531 tests and produced installer/portable/SHA-256 artifacts for its older commit; that artifact does not certify this newer source. Use the workflow run whose head SHA matches the current branch. Packaged Windows visual, crash, real-provider and audio acceptance remains separate from CI.
