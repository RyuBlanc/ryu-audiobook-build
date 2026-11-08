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


if __name__ == "__main__":
    unittest.main()
