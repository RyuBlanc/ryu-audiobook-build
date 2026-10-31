from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LiveCharacterStudioContracts(unittest.TestCase):
    def test_character_studio_starts_without_fabricated_demo_cast(self):
        html = (ROOT / "assets/frontend/ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        start = html.index('<section class="page" id="characters">')
        end = html.index('<section class="page" id="pronunciation"', start)
        section = html[start:end]

        for fake_value in (
            'id="charFoundMetric">23',
            'id="charAssignedMetric">20',
            'id="charReviewMetric">3',
            'id="charReadyMetric">87%',
            'id="assignedCountBadge">5 voices',
            'Rimuru Tempest',
            'Anime Hero',
            'data-ai-line="ai1"',
            '18 of 23 reviewed',
        ):
            self.assertNotIn(fake_value, section)

        self.assertIn('id="manualChapterList"', section)
        self.assertIn("Loading chapter data", section)
        self.assertIn("Loading chapter text", section)
        self.assertIn("Character Studio is rendered and persisted by premium_v2_backend_adapter.js", html)

    def test_source_backed_suggestions_and_exact_span_assignment_are_persisted(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        for command in (
            '"character.dialogue.suggestions.list": self._character_dialogue_suggestions_list',
            '"character.dialogue.suggestion.skip": self._character_dialogue_suggestion_skip',
            '"character.create": self._character_create',
        ):
            self.assertIn(command, host)
        self.assertIn('state["character_dialogue_suggestions"] = suggestions', host)
        worker_start = host.index("    def _character_worker(self, job_id: str, project) -> None:")
        worker_end = host.index("\n    def ", worker_start + 1)
        worker = host[worker_start:worker_end]
        self.assertIn('previous_dialogue_suggestions = state.get("character_dialogue_suggestions") or []', worker)
        self.assertIn('previous_dialogue_skips = state.get("character_dialogue_skips") or []', worker)
        self.assertIn('state["character_dialogue_skips"] = retain_current_dialogue_skips(', worker)
        self.assertNotIn('state["character_dialogue_skips"] = []', worker)
        self.assertIn("if exact_text != dialogue_text", host)
        self.assertIn('item["start"] < end and item["end"] > start', host)
        self.assertIn('"series": series', host)
        self.assertIn('"saved": True, "series": series', host)
        self.assertIn("grouped.setdefault(series, []).append(normalized)", host)

    def test_character_studio_uses_live_chapters_series_profiles_and_real_ai_review(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        for token in (
            "function renderCharacterStudioLive()",
            "async function refreshCharacterDialogueSuggestions()",
            "function characterDialogueRowsForChapter(chapter)",
            "function characterVoiceAssignments(name, series)",
            "function ensureAssignedAudioProfileControls()",
            "data-live-profile=",
            "async function saveManualCharacterAndAssign()",
            "async function testSelectedCharacterVoice()",
            "function renderAiChapterDocument()",
            "async function openAiCharacterReview(item)",
            "async function acceptHighConfidenceDialogues()",
            "async function skipCurrentDialogueSuggestion()",
            "if (changedProject)",
            "character.dialogue.suggestions.list",
            "character.dialogue.suggestion.skip",
            "Preview shorter than requested",
            "performance_target_met",
        ):
            self.assertIn(token, adapter)
        self.assertIn("No Characters Found", adapter)
        self.assertIn("const candidateSeries = String(linked?.series || hintedSeries || activeCharacterProjectSeries());", adapter)
        self.assertIn("Saved / manually created characters", adapter)
        self.assertIn(".ai-sentence.unassigned", adapter)
        self.assertIn(".ai-sentence.review", adapter)
        self.assertIn(".ai-sentence.confirmed", adapter)


    def test_assigned_cast_statistics_use_saved_provenance_and_distinct_chapters(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        html = (ROOT / "assets/frontend/ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        self.assertIn("aiAssigned / dialogueLines", adapter)
        self.assertIn("sourceKind === 'ai'", adapter)
        self.assertIn("const chapterSet = new Set()", adapter)
        self.assertIn("characterVoiceAssignments(selected.name, seriesValue)", adapter)
        self.assertIn("aiAssignedNode.textContent = String(assignments.aiAssignedPercent)", adapter)
        self.assertIn('<b id="assignedConfidence">—</b><span>AI Assigned</span>', html)
        self.assertNotIn('<span>Confidence</span>', html)

    def test_assignment_popup_preserves_full_source_passage_and_repositions_after_live_choices(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("function positionCharacterAssignmentPopover(popover, x, y)", adapter)
        self.assertIn("positionCharacterAssignmentPopover(popover, x, y);", adapter)
        self.assertIn("if ($('selectedTextPreview')) $('selectedTextPreview').textContent = String(passage.text);", adapter)
        self.assertNotIn("String(passage.text).slice(0, 120)", adapter)
        self.assertIn("#characterAssignPopover .popover-head b{display:block", adapter)
        self.assertIn("overflow-wrap:anywhere", adapter)

    def test_series_identity_flows_through_analysis_ui_assignment_and_learning(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        learning = (ROOT / "app/chapters/character_learning.py").read_text(encoding="utf-8")
        self.assertIn('learning_examples.extend(load_learning_examples(learning_series))', host)
        self.assertIn('last_speaker_series=continuity_series', host)
        self.assertIn('last_speaker_series: str = ""', learning)
        self.assertIn('candidate_series = _series_key(str(item.get("series") or ""))', learning)
        self.assertIn('"series": str(item.get("series") or "")', learning)
        self.assertIn('series:characterSeries(character)', adapter)
        self.assertIn('const hintedSeries = String(candidate.series || \'\').trim();', adapter)
        self.assertIn("row.name.toLowerCase() + '::' + row.series.toLowerCase()", adapter)
        self.assertIn('candidateSeries.toLowerCase() === String(item.assignmentSeries).toLowerCase()', adapter)
        self.assertIn('const ambiguousSeriesMatch = (row.suggestions || []).slice(1).some(other => {', adapter)
        self.assertIn('if (ambiguousSeriesMatch) { skipped++; continue; }', adapter)

    def test_qwen_design_preview_uses_design_model_without_production_anchor_setup(self):
        provider = (ROOT / "app/tts/providers/qwen_character.py").read_text(encoding="utf-8")
        worker = (ROOT / "app/tts/qwen_character_worker.py").read_text(encoding="utf-8")
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")

        self.assertIn('if self.qwen_mode in {"design", "design-preview"}:', provider)
        self.assertIn("self.model_kind = best_voice_design_kind()", provider)
        self.assertIn('elif active_task == "design-preview" and model is None:', worker)
        self.assertIn('elif active_task == "design-preview":', worker)
        self.assertIn("_generate_design_preview(model, request, output)", worker)
        self.assertIn('_generate_design_locked(model, locked_clone_prompts, request, output)', worker)
        self.assertIn('preview_profile.qwen_mode = "design-preview"', host)
        self.assertIn('"provider_setup_seconds": provider_setup_seconds', host)
        self.assertIn('"synthesis_seconds": synthesis_seconds', host)
        self.assertIn('"total_seconds": total_seconds', host)
        self.assertIn('"real_time_factor": real_time_factor', host)


if __name__ == "__main__":
    unittest.main()
