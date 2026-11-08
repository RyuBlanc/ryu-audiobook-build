from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_character_editor_profile_is_editable_and_persisted():
    adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
    start = adapter.index("function openCharacterEditorForSelected()")
    end = adapter.index("async function deleteSelectedProjectCharacter()", start)
    section = adapter[start:end]
    assert "$('editCharacterVoice').disabled = saved.length === 0;" in section
    assert "voice_profile:String($('editCharacterVoice')?.value ?? current.voice_profile ?? '')" in section
    assert "if (modal.classList.contains('show')) voice.disabled = true;" not in adapter


def test_ai_review_exposes_saved_voice_profiles_for_new_and_existing_characters():
    adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
    start = adapter.index("async function openAiCharacterReview(item)")
    end = adapter.index("function openCharacterEditorForSelected()", start)
    review = adapter[start:end]
    assert 'id="aiCharacterVoiceProfile"' in review
    assert "characterSavedProfiles()" in review
    assert "const selectedProfile = String($('aiCharacterVoiceProfile')?.value" in adapter
    assert "selectedProfile, assignmentSource, assignmentConfidence" in adapter


def test_ai_review_keeps_chapter_navigator_and_filters_queue_to_selected_chapter():
    adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
    start = adapter.index("function renderDialogueReview()")
    end = adapter.index("function renderAiChapterDocument()", start)
    review = adapter[start:end]
    assert "aiChapterNavigator" in review
    assert "data-ai-chapter-number" in review
    assert "Number(item.chapter_number) === Number(selectedChapter?.number)" in review
    assert "window.ryuPremiumAiChapterNumber = number" in review
    assert "renderAiChapterDocument();" in review
