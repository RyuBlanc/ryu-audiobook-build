# Stage 7.4.2 — Critical Workflow Verification

Status: **Automated regression verification complete; manual runtime acceptance remains explicitly out of scope for this substage.**

## Evidence

- Regression workflow: [Run #110](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/38951287776)
- Regression-test commit: `8772ca9a190a4a364f2631c7c189dac9cbc3dc19`
- Result: **154 tests passed** (`Ran 154 tests`; `OK` in the job log).
- Windows packaging workflow: [Build #484](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39152837325)
- Packaged source commit: `9ff9702fdaec0275cfe06c13d4f9e0b51cb8e500`
- Result: build, frozen-application checks, bundled voice-asset checks, installer packaging and portable packaging succeeded.

## Critical workflow coverage confirmed in the regression suite

| Workflow risk | Automated regression coverage |
|---|---|
| Saved custom/Qwen voice settings survive profile persistence | `test_qwen_custom_voice_profile_round_trip_preserves_generation_settings`, `test_qwen_voice_profiles_persist_phase_metadata`, `test_voice_profile_library_preserves_custom_voice_and_labels` |
| Preview and final synthesis share the saved voice identity | `test_qwen_voicedesign_preview_and_audiobook_share_stable_identity`, `test_qwen_design_preview_uses_stable_identity_base_model`, `test_cast_signature_changes_when_saved_qwen_identity_changes` |
| Character detection and voice assignment | Explicit speaker tags, Unicode/Japanese labels, short CJK names, light-novel dialogue, em-dash dialogue, multi-speaker cast routing, and saved cast assignment tests in `tests/test_regressions.py` and `tests/test_dialogue_assignment.py` |
| Preview target duration and responsive work | `test_timed_preview_uses_target_duration_and_live_progress`, `test_voice_preview_runs_in_a_worker_thread`, `test_generation_page_preview_uses_background_worker` |
| Empty chapter and recovery behavior | `test_detector_never_returns_empty_chapter`, `test_empty_chapter_repair_preserves_existing_edits_and_assignments`, `test_generation_readiness_allows_valid_chapters_and_nonblocking_empty_chapters`, `test_generation_readiness_blocks_when_every_chapter_is_empty` |
| Resume and stale-chunk invalidation | `test_generation_resume_reuses_completed_chunks_without_reopening_them`, `test_generation_resume_state_detects_completed_and_partial_chapters`, `test_qwen_resume_signature_tracks_exact_voice_configuration` |
| Generation cancellation/pause/recovery | `test_generation_cancel_closes_active_provider`, `test_generation_pause_resumes_at_safe_chapter_boundaries`, `test_qwen_failure_stops_cascading_chapter_errors` |

## Exit decision

The regression suite covers the critical Stage 7.4.2 risks and passed, and the latest Windows package build succeeded. Therefore **Stage 7.4.2 automated verification is complete** and work can advance to **Stage 7.4.3 — Audiobook Output Validation**.

This does **not** claim the app was manually launched or that custom-voice audio was heard in this environment. Manual Windows checks, real generated audio inspection, M4B playback/chapter-marker/metadata/cover/bitrate checks and long-book resume validation remain required under Stages 7.4.3–7.4.4. The passing regression workflow predates Build #484, while Build #484 packages the newer UI-test commit; do not represent the 154-test run as having executed on Build #484's exact SHA.
