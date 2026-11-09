from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CharacterStudioUIContracts(unittest.TestCase):
    def test_character_editor_profile_is_editable_and_persisted(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        start = adapter.index("function openCharacterEditorForSelected()")
        end = adapter.index("async function deleteSelectedProjectCharacter()", start)
        section = adapter[start:end]
        self.assertIn("$('editCharacterVoice').disabled = saved.length === 0;", section)
        self.assertIn(
            "voice_profile:String($('editCharacterVoice')?.value ?? current.voice_profile ?? '')",
            section,
        )
        self.assertNotIn("if (modal.classList.contains('show')) voice.disabled = true;", adapter)

    def test_ai_review_exposes_saved_voice_profiles_for_new_and_existing_characters(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        start = adapter.index("async function openAiCharacterReview(item)")
        end = adapter.index("function openCharacterEditorForSelected()", start)
        review = adapter[start:end]
        self.assertIn('id="aiCharacterVoiceProfile"', review)
        self.assertIn("characterSavedProfiles()", review)
        self.assertIn("const selectedProfile = String($('aiCharacterVoiceProfile')?.value", adapter)
        self.assertIn("selectedProfile, assignmentSource, assignmentConfidence", adapter)

    def test_ai_review_keeps_chapter_navigator_and_filters_queue_to_selected_chapter(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        start = adapter.index("function renderDialogueReview()")
        end = adapter.index("function renderAiChapterDocument()", start)
        review = adapter[start:end]
        self.assertIn("aiChapterNavigator", review)
        self.assertIn("data-ai-chapter-number", review)
        self.assertIn("Number(item.chapter_number) === Number(selectedChapter?.number)", review)
        self.assertIn("window.ryuPremiumAiChapterNumber = number", review)
        self.assertIn("renderAiChapterDocument();", review)

    def test_ai_review_queue_exposes_all_pending_passages_in_bounded_batches(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        start = adapter.index("function renderDialogueReview()")
        end = adapter.index("function renderAiChapterDocument()", start)
        review = adapter[start:end]
        self.assertNotIn("pending.slice(0, 120)", review)
        self.assertIn("pendingQueue.slice(0, visibleCount)", review)
        self.assertIn("data-ai-load-more", review)
        self.assertIn("ryuPremiumDialogueReviewVisibleCount", review)
        self.assertIn("ryuPremiumDialogueReviewQueueSignature", review)
        self.assertIn("Show more passages", review)
        self.assertIn("Math.min(pendingQueue.length, visibleCount + 120)", adapter)


    def test_ai_chapter_navigator_reports_per_chapter_metrics_and_search_status_filters(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        start = adapter.index("function renderDialogueReview()")
        end = adapter.index("function renderAiChapterDocument()", start)
        review = adapter[start:end]
        self.assertIn("chapterPassages", review)
        self.assertIn("wordCount", review)
        self.assertIn("split(/\\s+/)", review)
        self.assertIn("assignedCount", review)
        self.assertIn("aiSuggestedCount", review)
        self.assertIn("skippedCount", review)
        self.assertIn("data-ai-chapter-search", review)
        self.assertIn("data-ai-chapter-status", review)
        self.assertIn("data-ai-chapter-filter", review)
        self.assertIn("data-ai-chapter-status-filter", review)
        self.assertIn("ryuPremiumAiChapterFilter", review)
        self.assertIn("ryuPremiumAiChapterStatusFilter", review)
        self.assertIn("Not analysed yet", review)
        self.assertIn("Needs review", review)
        self.assertIn("Review complete", review)
        self.assertIn("chapterNav.addEventListener('input'", review)
        self.assertIn("chapterNav.addEventListener('change'", review)


    def test_ai_chapter_metrics_include_manual_source_assignments_and_all_pending_passages(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        start = adapter.index("function renderDialogueReview()")
        end = adapter.index("function renderAiChapterDocument()", start)
        review = adapter[start:end]
        self.assertIn("chapterPassages.filter(item => item.assigned && !item.skipped)", review)
        self.assertIn("chapterPassages.filter(item => item.skipped)", review)
        self.assertIn("chapterPassages.filter(item => !item.assigned && !item.skipped)", review)


    def test_narrator_only_generation_auto_enables_for_zero_cast_and_can_be_overridden(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("id = 'narratorOnlyGeneration'", adapter)
        self.assertIn("input.checked = project?.narrator_only_generation === true", adapter)
        self.assertIn('"narrator_only_generation": narrator_only_eligible', host)
        self.assertIn('"narrator_only_generation_auto": narrator_only_automatic', host)
        self.assertIn('state.get("narrator_only_generation_user_opt_out", False) is True', host)
        self.assertIn("Automatically enabled because this book has no configured character voice profiles", adapter)
        self.assertIn("production.narrator_only.save", adapter)
        self.assertIn("narrator_only_generation:narratorOnly", adapter)
        self.assertIn('state["narrator_only_generation"] = enabled', host)
        self.assertIn('state["narrator_only_generation_user_opt_out"] = not enabled', host)
        self.assertIn('"route_character_cast": not narrator_only', host)


if __name__ == "__main__":
    unittest.main()
