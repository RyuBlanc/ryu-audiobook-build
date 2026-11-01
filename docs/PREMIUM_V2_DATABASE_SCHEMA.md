# Database Schema — Premium V2

**Status as of 2026-10-20:** target architecture only. The current Premium V2 integration has not migrated its authoritative project/job/history storage to SQLite.
**Audited commit:** `eca9cf1a8330e2dcfce697f66233a73740e25ae0`.

## Current persistence found in source

- Existing project and chapter content continue to use the project's current filesystem/model persistence through `app/core/project.py`.
- Additional project state uses state JSON via `app/core/state.py`.
- The active project folder uses `QSettings` key `project/active_folder`.
- Premium V2 jobs are stored in `settings_root()/premium_v2_jobs.json`, written using a temporary file and replacement.
- `history.list` reads the same job rows. Clearing completed rows hides manager entries instead of deleting the underlying record, but this is not yet a separate immutable history store.
- The host marks queued/running/requested/cancel-pending/retrying jobs interrupted and recoverable on restart; this does not keep the original worker process alive.

Do not claim SQLite migrations, atomic transactions across project data, separate history retention or complete restart recovery are implemented until tests and code prove them.

## Target migration strategy

Use SQLite as the transactional metadata/index store and keep large source/audio/model assets in managed filesystem folders. Migration must be versioned and backed up before destructive changes. Preserve current project folders and original imported sources; import their existing metadata without deleting or rewriting source books. Writes should use transactions and atomic file replacement where supported.

## Target core tables

- `schema_migrations(version, applied_at, checksum)`
- `projects(id, title, author, cover_path, language, source_path, status, active_stage, output_dir, created_at, modified_at, archived_at, source_checksum)`
- `chapters(id, project_id, position, title, text_path_or_text, word_count, review_state, generation_state, audio_path, audio_duration, modified_at)`
- `voice_profiles(id, provider, model_id, display_name, language_json, parameters_json, reference_path, authorization_json, installed_state, created_at, modified_at)`
- `characters(id, project_id, canonical_name, aliases_json, description, dialogue_count, appearances_json, voice_profile_id, speaking_style_json, review_state, modified_at)`
- `dialogue_assignments(id, project_id, chapter_id, line_key, character_id, confidence, confirmation_state, modified_at)`
- `pronunciation_entries(id, written_form, spoken_form, language, handling_mode, scope_type, scope_id, enabled, conflict_state, created_at, modified_at)`
- `pronunciation_tests(id, entry_id, voice_profile_id, result_state, output_path, details_json, tested_at)`
- `sound_assets(id, asset_type, source_path, checksum, duration, sample_rate, loudness_lufs, true_peak_db, license_metadata_json, created_at)`
- `sound_manifests(id, project_id, chapter_id, manifest_json, validation_state, modified_at)`
- `model_packages(id, provider, capability, version, install_state, file_path, size_bytes, checksum, compatibility_state, updated_at)`
- `background_jobs(id, project_id, chapter_id, job_type, title, description, state, percentage, stage, priority, queued_at, started_at, updated_at, completed_at, estimated_seconds_remaining, retry_count, error_code, error_details_json, checkpoint_json, output_refs_json, settings_snapshot_json, model_snapshot_json)`
- `history_records(id, job_id, project_id, chapter_id, started_at, completed_at, duration_seconds, final_state, output_location, error_details_json, retry_count, provider, model_id, settings_snapshot_json, log_path, created_at)`
- `application_settings(key, value_json, modified_at)`
- `playback_state(project_id, output_path, chapter_index, position_seconds, volume, speed, bookmark_json, modified_at)`
- `application_events(id, event_type, entity_type, entity_id, request_id, timestamp, severity, details_json)`

## Constraints and migration acceptance

- Enable foreign keys; cascade deletion only where user-visible deletion semantics are explicit and tested.
- Uniquely key project IDs, chapter identities/ordering within project, voice-profile IDs, migration versions and job IDs.
- Index jobs by state/priority/queued time, history by project/completion time, chapters by project/order and pronunciation by scope/language/written form.
- Clearing task-manager entries must not clear `history_records`.
- Block model removal while active jobs depend on it; preserve profiles and mark missing models when appropriate.
- Write final outputs to a temporary path, validate streams/metadata/chapters, then replace the intended output atomically.
- Export/import versioned project JSON without secrets.
- Integrity checks must report corruption and offer backup/recovery rather than destructive automatic repair.
- Add close/reopen tests for project edits, chapter order/review/skip state, voice profiles, assignments, pronunciation rules, sound manifests, settings, jobs/history and playback position.