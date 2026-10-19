# Database Schema — Premium V2

**Status:** Target schema for the local-first shared state. The existing app currently persists project JSON and state JSON; this schema is not yet migrated into runtime.

## Persistence strategy

Use SQLite as the authoritative index and transactional metadata store, while keeping large source/audio/model assets in managed filesystem directories. Migrations must be versioned and backed up before destructive changes. Preserve existing project folders and import their JSON metadata without deleting or rewriting source book files. All writes should use transactions and atomic file replacement.

## Core tables

- `schema_migrations(version, applied_at, checksum)`
- `projects(id, title, author, cover_path, language, source_path, status, active_stage, output_dir, created_at, modified_at, archived_at, source_checksum)`
- `chapters(id, project_id, position, title, text_path_or_text, word_count, review_state, generation_state, audio_path, audio_duration, modified_at)`
- `voice_profiles(id, provider, model_id, display_name, language_json, parameters_json, reference_path, authorization_json, installed_state, created_at, modified_at)`
- `characters(id, project_id, canonical_name, aliases_json, description, dialogue_count, appearances_json, voice_profile_id, speaking_style_json, review_state, modified_at)`
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

## Required constraints and indexes

- Foreign keys enabled; child rows cascade only where data deletion semantics are explicitly approved.
- Unique `schema_migrations.version`, `background_jobs.id`, `projects.id`, and `voice_profiles.id`.
- Index jobs by state/priority/queued time; history by project and completion time; chapters by project/order; pronunciation by scope/language/written form.
- A job's task-manager entry may be cleared without deleting its history record.
- Model uninstall cannot delete an active job's required model; referenced profiles remain and report missing model.
- Final output writes use a temporary path followed by atomic replacement and output validation.
- Project export/import is versioned JSON; secrets are excluded.
- Database integrity checks run against the actual SQLite file and report failures without destructive auto-repair.
