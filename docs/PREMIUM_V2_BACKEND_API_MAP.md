# Backend API Map — Premium V2

**Status:** Audit contract, Phase 1. Commands below describe the intended typed bridge; they are not represented as already implemented. All mutations must validate inputs and persist before returning success.

## Bridge contract

Use the existing PySide6/Python runtime and embed the supplied HTML in the desktop process (Qt WebEngine + QWebChannel or an equivalent supported local bridge). The renderer must not invoke arbitrary shell commands. Bridge methods should return structured results and emit real job/state events. Keep custom HTML dialogs and controls; native OS dialogs are permitted only when the HTML has no equivalent and the design spec allows them.

Common response shape:
- success: boolean
- data: object or array
- error: stable code, user-safe message, optional retryable flag
- request_id: correlation ID

Common events:
- `state.changed`
- `job.created`, `job.updated`, `job.completed`, `job.failed`
- `project.opened`, `project.updated`
- `playback.updated`
- `diagnostics.updated`

## Command inventory

| Domain | Commands to expose | Existing implementation candidates |
|---|---|---|
| App / shell | `app.get_info`, `app.get_capabilities`, `app.navigate`, `app.get_update_log` | `app/main.py`, `app/version.py`, `app/ui/workflow.py` |
| Project | `project.list`, `project.create`, `project.open`, `project.update_metadata`, `project.duplicate`, `project.archive`, `project.delete`, `project.export`, `project.import_backup`, `project.get_active` | `app/core/project.py`, `app/core/paths.py`, `app/core/state.py`, `app/ui/library.py` |
| Import | `import.validate`, `import.start`, `import.get_report`, `import.retry` | `app/ui/import_page.py`, `app/documents/parser.py`, `app/documents/importer.py`, `app/chapters/detector.py` |
| Chapters | `chapter.list`, `chapter.update`, `chapter.rename`, `chapter.reorder`, `chapter.add`, `chapter.split`, `chapter.merge`, `chapter.delete`, `chapter.scan_dialogue`, `chapter.clean_text`, `chapter.preview` | `app/chapters/*`, `app/ui/chapter_editor.py` |
| Voices | `voice.list_profiles`, `voice.list_available`, `voice.save_profile`, `voice.delete_profile`, `voice.preview`, `voice.assign_narrator`, `voice.provider_status`, `voice.get_model_status` | `app/tts/voice_profile.py`, `app/tts/profile_provider.py`, `app/tts/providers/*`, `app/ui/voice_page.py` |
| Characters | `character.analyze`, `character.list`, `character.save`, `character.merge`, `character.assign_voice`, `character.validate_assignments`, `character.preview_dialogue` | `app/chapters/characters.py`, `app/chapters/dialogue.py`, `app/ui/character_review.py`, `app/ui/dialogue_assignment.py`, `app/ui/dialogue_manager.py` |
| Pronunciation | `pronunciation.list`, `pronunciation.add`, `pronunciation.update`, `pronunciation.delete`, `pronunciation.analyze`, `pronunciation.test_voice`, `pronunciation.test_selected_voices`, `pronunciation.test_all_saved_voices`, `pronunciation.import`, `pronunciation.export` | `app/tts/pronunciation_suggester.py`, narration/profile modules |
| Sound | `sound.assets.list`, `sound.assets.import`, `sound.assets.delete`, `sound.manifest.get`, `sound.manifest.save`, `sound.validate`, `sound.preview_mix`, `sound.analyze_loudness` | `app/audio/sound_design.py`, `app/audio/preview_mixer.py`, `app/audio/story_events.py` |
| Production/jobs | `production.preflight`, `production.preview`, `production.generate_chapter`, `production.generate_book`, `production.rebuild_package`, `job.list`, `job.pause`, `job.resume`, `job.cancel`, `job.retry`, `job.set_priority`, `job.pause_all`, `job.resume_all` | `app/tts/manager.py`, `app/tts/generator.py`, `app/tts/readiness.py`, `app/tts/resume.py`, `app/audio/assembler.py` |
| Player | `player.open_output`, `player.play`, `player.pause`, `player.seek`, `player.next_chapter`, `player.previous_chapter`, `player.set_volume`, `player.set_speed`, `player.bookmark`, `player.get_position` | `app/ui/audiobooks_page.py`, audio assembly metadata |
| History | `history.list`, `history.get`, `history.open_log`, `history.retry`, `history.resume`, `history.open_output`, `history.export_diagnostics` | `app/ui/history_page.py`, job service and logs |
| Models | `model.list`, `model.install`, `model.pause_install`, `model.resume_install`, `model.verify`, `model.repair`, `model.uninstall`, `model.set_default`, `model.test` | `app/tts/model_registry.py`, model/runtime modules, `app/ui/models_page.py` |
| Performance | `performance.snapshot`, `performance.benchmark`, `performance.set_device`, `performance.set_limits`, `performance.clear_cache`, `performance.clear_temp_audio`, `diagnostics.export` | `app/hardware/*`, `app/tts/benchmark.py`, `app/ui/hardware_page.py` |
| Settings | `settings.get`, `settings.update`, `settings.choose_folder`, `settings.export_logs`, `diagnostics.workflow_integrity`, `diagnostics.database_integrity`, `diagnostics.model_integrity` | `app/ui/settings_page.py`, `app/core/paths.py`, `app/core/state.py` |
| Help | `help.get_topic`, `help.open_workflow`, `help.run_integrity_check` | Must be added or mapped to actual help content. |

## Bridge safety rules

1. File paths are selected/validated in Python; renderer-supplied paths are normalized and checked against allowed roots.
2. Imported text is data only and never executed as code or commands.
3. Voice cloning/design actions require explicit authorization acknowledgement and record the consent metadata required by the existing backend.
4. Provider commands are exposed only when the actual runtime reports the provider available.
5. Job progress is emitted from real backend callbacks/checkpoints; no front-end timer may claim percentage completion.
6. The UI receives errors, unsupported capabilities, missing models and offline provider status honestly.
7. Secrets are never returned to JavaScript or written to project JSON.
8. Mutating commands are idempotent where possible and use request IDs to avoid duplicate work.
9. Renderer/backend version and command schema are checked at startup; incompatible bridge versions fail visibly rather than silently.
10. No command is marked complete until a backend implementation and integration test exist.
