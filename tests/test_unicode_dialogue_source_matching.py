from app.ui.premium_v2_host import PremiumV2Bridge


def _normalizer_source():
    import inspect
    return inspect.getsource(PremiumV2Bridge._character_worker)


def test_ai_dialogue_matching_uses_unicode_aware_letters_and_digits():
    source = _normalizer_source()
    assert 'unicodedata.normalize("NFKC", str(value or "")).casefold()' in source
    assert "character.isalnum()" in source
    assert 're.sub(r"[^0-9a-z]+"' not in source


def test_nfkc_casefold_normalization_preserves_non_latin_quote_text():
    import unicodedata

    def normalize(value):
        normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
        return "".join(character for character in normalized if character.isalnum())

    assert normalize("「こんにちは！」") == "こんにちは"
    assert normalize("你好，Ren！") == "你好ren"
    assert normalize("안녕하세요, 미라!") == "안녕하세요미라"
    assert normalize("“Hello, RÉN!”") == "hellorén"
