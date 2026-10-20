# Known Limitations — Ryu's Audiobook Dragon Studio

Last audited against branch `fix/import-qa-speaker-hover-hardware` at the Stage 8.2.11 / Run #724 candidate. This file describes actual gaps surfaced by the frontend adapter and backend capability map. It is not a claim that Windows manual acceptance has passed.

## Application and integration limitations

| Area | Current behavior | Acceptance implication |
|---|---|---|
| Project creation | The backend capability map reports `project.create` as unavailable. The supported workflow is to import a source book and create/open its local project through that path. | Do not advertise a standalone New Project action as connected until a real handler exists. |
| Hardware telemetry | `performance.info` is unavailable. The Performance screen reports CPU telemetry and GPU/VRAM telemetry as unavailable/not measured rather than inventing values. | Live CPU/GPU/VRAM measurements remain unaccepted. |
| Secure provider credentials | Credential management is not connected to a secure provider-specific credential store in this build. No API key is requested or saved by the guarded controls. | Do not enter or expect provider API keys to persist through these controls. |
| Premium cloud voice candidates | Premium cloud candidate generation is not connected to a provider endpoint in this build. The guarded action does not generate mock candidates. | Use supported saved voice profiles and Generate Preview. |
| Chapter review status | Review status is not yet supplied by the chapter backend. Selecting the Review filter reports this limitation and shows all chapters instead of inventing review flags. | Review-state filtering is not available until review state is persisted by the backend. |
| Per-line AI speaker suggestions | Per-line AI speaker suggestions are still prototype-only. The current supported workflow assigns a saved character's voice through Character Studio; chapter-line speaker assignment is not persisted by the current backend. | Do not treat per-line speaker assignments as saved or production-ready. |
| Custom storage roots | Custom project-library and audio-assets root selection is not implemented. | Projects and assets use the application's configured local storage roots. |
| Sanitized log export | Sanitized log export is not connected yet. | The UI must not claim a sanitized diagnostic export was created. |
| Per-model actions | The model screen's per-model actions are not all connected to backend operations. The local Qwen Voice Studio install/repair action is connected to the real `models.install` job; other unsupported per-model actions must report an unavailable operation. | Do not treat unsupported per-model install/update/remove actions as successful. |
| Review and capability reporting | The capability map marks supported bridge commands individually; unsupported commands return a truthful `not_connected` error. | A green build is not proof every visible action is available. |

## What CI has verified for Run #724

- The Windows build workflow passed and produced both installer and portable artifacts.
- The repository test suite reported 305 tests passing.
- The frozen executable's startup smoke and offline synthesis self-test passed.
- The live local Audiobook AI smoke test passed.
- Bundled voice assets and critical modules were checked by the workflow.

## Acceptance still required on a real Windows machine

CI does not replace interactive Windows acceptance. The following remain pending until performed on the target machine and recorded:

- Install and launch the installer build; separately launch the portable build.
- Visit all 15 destinations and check that no navigation destination is missing or blocked.
- Exercise import, chapter edit/split, voice preview, character assignment, pronunciation, sound design, generation, Player, History, Models, Performance, Settings, and Help.
- Verify a real preview's selected voice and requested duration; generate and play a short audiobook and verify chapter order, actual duration, and output path.
- Exercise pause, resume, cancel, retry, and recovery from a failed/offline provider.
- Restart the application and verify project data and settings persist.
- Record failures with screenshots/logs and rebuild only after fixing confirmed defects.

**Release rule:** Do not describe Stage 8.2.11 as fully accepted, or Stage 8.2.12 as complete, until these target-machine checks have actually passed.