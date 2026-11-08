from app.chapters.characters import is_likely_character_name


def test_common_capitalized_prose_and_description_phrases_are_not_cast_members():
    assert not is_likely_character_name("SILVER HAIRED")
    assert not is_likely_character_name("Silver-Haired")
    assert not is_likely_character_name("Letting")
    assert not is_likely_character_name("Hearing Tobio's")
    assert not is_likely_character_name("Astonished Tobio")
    assert not is_likely_character_name("The School")


def test_valid_names_and_explicit_user_or_speaker_evidence_are_preserved():
    assert is_likely_character_name("Ikuse Tobio")
    assert is_likely_character_name("Tobio")
    assert is_likely_character_name("Ono Anna")
    assert is_likely_character_name("Hearing", explicit=True)
    assert is_likely_character_name("Silver-Haired", trusted=True)
