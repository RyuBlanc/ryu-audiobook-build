# Screen-to-Function Map — Premium V2

**Audit snapshot:** 21 October 2026
**Current review checkpoint:** code checkpoint Run #775 (`7b8176ac`); command-parity regression added in commit `6fa61f0d` and is being validated by [Run #780](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39579474613). This map is a source audit, not manual runtime acceptance.
**Visual authority:** `assets/frontend/ryu_audiobook_premium_v2.html`
**User-supplied visual source fingerprint:** 1,436,954 bytes; SHA-256 `e70f630d99e75f07fdd704bb1931910dd972795390ae0af0d29b07b9118abf95`; Git blob SHA `0da8d4a60c69530325fff9af7e516d251dc442cd`, matching the file in the audited repository commit.

## Inventory and status language

The approved HTML contains 15 `section.page` screens, 15 unique navigation destinations, 384 form/button controls (291 buttons, 48 inputs, 40 selects, 5 textareas), 279 unique DOM IDs, and no duplicate IDs in the initial static DOM. The direct `data-go` navigation targets cover 14 destinations; the Help page itself is reachable through the navigation map. These are static inventory counts, not proof that every control works.

- **Connected in source:** a real adapter call and host handler exist. Runtime acceptance may still be outstanding.
- **Partial:** some data/actions are connected but required controls/state paths are missing or legacy demo handlers remain.
- **Unavailable / explicitly guarded:** the UI or capability map truthfully reports the operation as unsupported.
- **Prototype-only risk:** static demo content, timers, browser storage, or a legacy handler remains in the supplied HTML path.
- **Unverified:** not proven by target-Windows, real-book, real-audio end-to-end acceptance.

## Screen map

| Screen | Real backend/service path observed | Current status and required follow-up |
|---|---|---|
| Dashboard | `project.list`, `job.list`; `app/core/project.py`, `app/core/state.py`, job/generation services | **Partial.** Project/job refresh exists, but the source HTML still contains sample metrics, cards and job text. Verify every headline metric and Continue/View/Pause action is derived from the active project and real job ID. |
| Audiobook Library | `project.list`, `project.open`, `project.get_active`; `app/core/project.py` | **Partial.** Project cards/search/filter refresh from local records. Standalone create, duplicate, archive and delete project commands are absent; import is the supported project-creation path. Validate card actions and filter/sort semantics with multiple real projects. |
| Import Studio | `import.choose_file`, `import.start`; `app/documents/parser.py`, `app/chapters/detector.py` | **Connected in source; unverified.** File selection and background import are real. Verify file drag/drop, supported extension validation, extraction diagnostics, retry/cancel, metadata, duplicate import behavior and source preservation on Windows. |
| Chapter Studio | `chapter.list`, `chapter.update`, `chapter.dialogue.assign`, `chapter.review`, `chapter.skip`, `chapter.clean`, `chapter.add`, `chapter.delete`, `chapter.reorder`, `chapter.merge`, `chapter.split`; `app/chapters/*`, `app/documents/parser.py` | **Partial; bridge operations are present.** Add/delete/reorder/merge/split, review state, skip-for-generation and text cleanup have host operations. Automated contract checks cover selected routes, but real-book editing and persisted state still need Windows acceptance. Find/replace, undo/redo and safe re-detection that preserves edits remain open. |
| Voice Studio | `voice.list`, `voice.save`, `voice.delete`, `voice.import_reference`, `voice.select`, `voice.preview`; `app/tts/voice_profile.py`, `profile_provider.py`, `providers/*`, `preview.py` | **Partial.** Saved-profile and preview commands exist; preview accepts 10/20/30/45/60-second targets. Confirm the currently selected saved profile/provider/model/settings are the exact preview and generation inputs. Premium cloud candidate generation and secure credential entry remain unavailable. |
| Character Studio | `character.list`, `character.analyze`, `character.assign`, `character.update`, `character.delete`, `chapter.dialogue.assign`, `character_library.*`; `app/chapters/characters.py`, `dialogue.py` | **Partial.** Book-level cast analysis and saved-character/voice operations exist. Manual source-backed dialogue assignment has a bridge path that validates the source passage and persists speaker evidence/offsets. Automatic per-line AI speaker suggestions remain prototype-only/guarded. Verify assignment edit/removal, narrator fallback and actual synthesis on Windows. |
| Pronunciation Studio | `pronunciation.list`, `pronunciation.save`, `pronunciation.delete`, `pronunciation.analyze`, `voice.preview`; `app/tts/pronunciation_suggester.py`, narration/profile services | **Partial.** Book dictionary list/save/delete/analyze and single saved-profile preview are present. Test-selected/test-all voice matrix behavior, per-voice result persistence, import/export, conflict reporting and invalidation of previously generated audio are not complete backend operations. |
| Sound Design Studio | `sound.catalog`, `sound.import`, `sound.assign`, `sound.save_manifest`, `sound.cues.get/save/clear`, `sound.chapter_bgm.get/save`, `sound.preview_book`; `app/audio/sound_design.py`, `preview_mixer.py`, `story_events.py`, `assembler.py` | **Connected in source; runtime acceptance open.** Book/chapter cue state and chapter-BGM rules have bridge operations. A background full-book mix-preview job is registered and regression-tested, including saved narration and production sound-design assignments. Still verify real playback, licensing/source metadata, missing assets, loudness/fades/ducking, preview/final parity and final assembly against actual projects on Windows. |
| Production Studio | `production.preview`, `production.generate_book`, `job.list/pause/resume/cancel`; `app/tts/manager.py`, `generator.py`, `readiness.py`, `resume.py`, `app/audio/assembler.py` | **Partial.** Generation and preview workers are real, durable job rows exist, and cancellation/output-validity safeguards have regression coverage. Dedicated preflight/rebuild/retry, checkpoint recovery proof, interruption/resume acceptance and final M4B inspection remain open. Do not infer completion from a green build. |
| Audiobooks Player | `player.get_active`, `system.open_output`; browser `Audio` playback/seek/speed controls in the adapter | **Partial.** Active output metadata and output-folder opening exist. Verify real-file playback and main/mini-player synchronization. Durable playback-position/bookmark persistence and full chapter-marker navigation are not evidenced by the current bridge. |
| Generation History | `history.list` | **Partial.** History is currently projected from the same durable job dictionary/file, not a separate immutable audit table. It lacks complete dedicated get-log/retry/resume/export-output operations and must be tested independently from task-manager clearing. |
| Models Center | `models.list`, `models.install`; `app/tts/model_registry.py`, model runtimes | **Partial.** Local model inventory and Qwen install job are connected. Per-model update/verify/repair/uninstall/default selection/test-generation actions intentionally report unavailable rather than fake success. Check-update/queue actions need contract verification. |
| Performance Center | `performance.info` capability is `False`; `app/hardware/*`, `app/tts/benchmark.py` are existing backend candidates | **Unavailable/partial.** The screen must not invent CPU/GPU/VRAM. The HTML still contains a timer-style benchmark demo path; ensure it cannot report a fake benchmark completion. Real telemetry and benchmark wiring remain open. |
| Settings | `settings.get`, `settings.save`, `diagnostics.check`, `diagnostics.export_logs` | **Partial.** Theme/effects/settings fields and a real save-dialog log export exist. Custom storage roots and secure provider-specific credentials are not connected; map each settings field to durable backend state and ensure unsupported actions explain why. |
| Help & Guide | Static HTML guide and `data-go` navigation | **Navigation connected; behavior content is static.** The guide should reflect actual available features and clearly distinguish unavailable functionality. Quick-start/action prompts need smoke testing. |

## Global shell and cross-screen actions

| Feature | Observed behavior | Acceptance requirement |
|---|---|---|
| Navigation and workflow strip | HTML navigation uses `data-page`/`data-go`; 15 page sections are present | Exercise every destination and repeat navigation with an open project; no unsaved editor state may be lost. |
| Backend adapter | `assets/frontend/premium_v2_backend_adapter.js` wraps the allow-listed `window.ryuBackend.invoke` bridge and uses null-safe DOM access | Build a complete control-to-call inventory, not just a screen list; ensure legacy target/bubble click handlers cannot also fire and simulate success. |
| Background Jobs popover | `job.list` refresh is scheduled at 1.5-second intervals; pause/resume/cancel/clear-completed handlers exist | Confirm state comes from worker/job records; test actual job controls, errors, restart recovery and count updates. Polling is not equivalent to event streaming. |
| Diagnostics export | `diagnostics.export_logs` uses a save dialog, bounded log inclusion, atomic report writing and best-effort redaction | Verify Windows behavior and inspect exports for leakage; redaction is not a complete security guarantee. |

## Known static mismatch

`app/ui/premium_v2_host.py` registers `chapter.split` and the adapter invokes it, but the capability map did not advertise it. Stage 1 includes the correction and regression assertion so the UI capability contract agrees with the actual handler.

## Acceptance boundary

This map is a source inspection result. It does not certify all screens or actions as manually accepted. The current known CI result is Run #731 for commit `eca9cf1a8330e2dcfce697f66233a73740e25ae0`: 308 automated tests passed and Windows installer/portable packaging completed. Target-Windows interactive acceptance remains pending.