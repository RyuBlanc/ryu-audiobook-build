from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Stage3NarratorSegmentationContracts(unittest.TestCase):
    def test_backend_exposes_source_backed_narrator_segmentation(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn('"character.narration.segments.list": self._character_narration_segments_list', host)
        self.assertIn("def _character_narration_segments_list(", host)
        self.assertIn("segment_chapter_speakers(chapter)", host)
        self.assertIn('chapter.narrator_passages = [', host)
        self.assertIn('"automatic": True', host)

    def test_character_studio_displays_narration_as_a_dedicated_speaker_role(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        for token in (
            "async function refreshCharacterNarrationSegments()",
            "character.narration.segments.list",
            "function characterNarrationSegmentsForChapter(chapter)",
            "Narrator · Auto",
            "Needs speaker",
            "kind === 'needs_speaker_review'",
            "review-' + Number(chapter.number)",
            "ryu-narrator-passage",
        ):
            self.assertIn(token, adapter)


    def test_series_narrator_default_backend_commands_and_project_precedence(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        for token in (
            '"narrator.series.default.get": self._narrator_series_default_get',
            '"narrator.series.default.save": self._narrator_series_default_save',
            '"narrator.series.default.apply": self._narrator_series_default_apply',
            'def _narrator_series_default_get(',
            'def _narrator_series_default_save(',
            'def _narrator_series_default_apply(',
            '"narrator_profile_source": "project_override"',
            'effective = project_profile or default_profile',
        ):
            self.assertIn(token, host)
        for token in ("Series Narrator Default", "Save Series Default", "Reset to Series Default",
                      "narrator.series.default.save", "narrator.project.reset"):
            self.assertIn(token, adapter)
        self.assertNotIn("Apply to This Book", adapter)

    def test_series_narrator_defaults_are_migrated_and_protected_from_deletion(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn('series_defaults_root = Path(settings_root()) / "series-narrators"', host)
        self.assertIn('attempted_series_defaults.append((path, original_text))', host)
        self.assertIn("The profile is the saved narrator default for series", host)
        self.assertIn("Change that series narrator default before deleting this profile.", host)

    def test_production_cast_series_scope_fallback_uses_tested_series_parser(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("def _character_series_for_voice_assignment(", host)
        self.assertIn('re.match(r"(?i)^series\\s*[·:-]\\s*(.+)$", scope)', host)
        self.assertIn("self._character_series_for_voice_assignment(", host)

    def test_production_cast_routing_uses_series_scoped_character_identity(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("from app.core.character_identity import character_identity_key", host)
        self.assertIn("cast_identity_assignments: dict[str, str] = {}", host)
        self.assertIn("character_identity_key(character_name, character_series)", host)
        self.assertIn("identity_assignments=cast_identity_assignments", host)

    def test_generation_uses_effective_narrator_and_blocks_unresolved_dialogue(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("def _resolve_narrator_for_generation(", host)
        self.assertIn("self._narrator_series_default_read(project, state, series)", host)
        self.assertIn("segment.needs_review", host)
        self.assertIn("self._resolve_narrator_for_generation(project, state, chapters)", host)
        self.assertIn('"narrator_profile_source": str(narrator_selection.get("source") or "none")', host)

    def test_create_series_preview_uses_the_existing_voice_preview_job_worker(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn('if not payload.get("allow_projectless_preview")', host)
        self.assertIn('"allow_projectless_preview": True', host)
        self.assertIn("threading.Thread(", host)
        self.assertIn("self._preview_worker", host)

    def test_narrator_preview_requires_source_backed_narration_and_reuses_voice_preview(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn('"narrator.preview": self._narrator_preview', host)
        self.assertIn('def _narrator_preview(', host)
        self.assertIn('segment_chapter_speakers(chapter)', host)
        self.assertIn('segment.kind != "narration"', host)
        self.assertIn('"route_character_cast": False', host)
        self.assertIn('id="previewProjectNarrator"', adapter)
        self.assertIn("call('narrator.preview'", adapter)

    def test_new_series_creation_supports_narrator_setup_or_explicit_incomplete_draft(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        for token in (
            "ryuCreateSeriesNarratorSetup",
            "ryuCreateSeriesNarratorProfile",
            "ryuCreateSeriesNarratorSample",
            "Preview Narrator",
            "Play Narrator Preview",
            "Save Draft Without Narrator",
            "narratorDraftWithoutVoice",
            "narrator.preview",
            "narrator.series.default.save",
            "Incomplete narration setup",
            "narratorPanel.hidden=!createSeries",
            "characterSavedProfileLabel(savedProfile)",
        ):
            self.assertIn(token, adapter)

    def test_series_default_resolution_is_file_backed_and_does_not_use_project_cache(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn('settings_root() / "series-narrators"', host)
        self.assertIn("def _narrator_series_default_read(self, project, state: dict[str, Any], series: str)", host)
        self.assertIn('stored_source in {"series_default", "none"}', host)
        self.assertIn("default_profile = str(record.get(\"profile_name\") or \"\").strip()", host)

    def test_storage_cleanup_only_runs_after_successful_stage_3_step_11_9_checkpoint(self):
        build = (ROOT / ".github/workflows/build-windows.yml").read_text(encoding="utf-8")
        cleanup = (ROOT / ".github/workflows/actions-storage-cleanup.yml").read_text(encoding="utf-8")
        self.assertNotIn("Clean old Actions runs and storage after verified Windows build", build)
        self.assertNotIn("name: Clean stale Actions runs and storage", build)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", cleanup)
        self.assertIn("contains(github.event.workflow_run.head_commit.message, '[artifact-checkpoint]')", cleanup)
        self.assertIn("contains(github.event.workflow_run.head_commit.message, '[Stage 3][Step 11.9]')", cleanup)
        self.assertIn(r"/\\[Stage 3\\]\\[Step 11\\.9\\]/.test", cleanup)
        self.assertIn("if (!packageAnchor)", cleanup)

    def test_series_narrator_summary_reader_does_not_require_active_project(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        start = host.index("    def _narrator_series_default_read(")
        end = host.index("    def _narrator_series_default_get(", start)
        reader = host[start:end]
        self.assertNotIn("self._active_project()", reader)
        self.assertIn("_narrator_series_default_read(project, state,", host)
