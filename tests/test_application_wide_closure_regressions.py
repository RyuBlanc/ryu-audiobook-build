from __future__ import annotations

from app.tts.voice_profile import VoiceProfile
import app.tts.profile_provider as profile_provider
from app.tts.qwen_model_preference import normalize_qwen_backend_preference
from app.tts.providers.qwen_character import QwenCharacterProvider


def test_qwen_backend_normalizer_rejects_provider_identifier():
    assert normalize_qwen_backend_preference("qwen-character") == "automatic"
    assert normalize_qwen_backend_preference(" QWEN-CHARACTER ") == "automatic"
    assert normalize_qwen_backend_preference("cuda") == "cuda"
    assert normalize_qwen_backend_preference("cpu") == "cpu"


def test_saved_qwen_profile_with_provider_id_uses_global_automatic(monkeypatch):
    captured = {}

    class FakeQwenProvider:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(profile_provider, "QwenCharacterProvider", FakeQwenProvider)
    monkeypatch.setattr(profile_provider, "get_qwen_backend_preference", lambda: "automatic")
    monkeypatch.setattr(profile_provider, "get_qwen_model_preference", lambda: "0.6b")
    monkeypatch.setattr(
        profile_provider,
        "qwen_model_kinds_for_preference",
        lambda mode, preference: ("custom-0.6b", "base-0.6b"),
    )

    profile = VoiceProfile(
        name="Legacy Qwen Anime Hero",
        provider="qwen-character",
        voice_id="Ryan",
        backend="qwen-character",
        qwen_mode="custom",
    )
    provider, voice = profile_provider.provider_from_profile(profile)

    assert isinstance(provider, FakeQwenProvider)
    assert voice == "Ryan"
    assert captured["backend"] == "automatic"
    assert captured["model_kind"] == "custom-0.6b"


def test_qwen_provider_never_passes_provider_id_as_compute_backend():
    provider = QwenCharacterProvider(
        voice_id="Ryan",
        backend="qwen-character",
        model_kind="custom-0.6b",
    )
    assert provider.backend == "automatic"


def test_explicit_qwen_cpu_preference_is_preserved(monkeypatch):
    captured = {}

    class FakeQwenProvider:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(profile_provider, "QwenCharacterProvider", FakeQwenProvider)
    monkeypatch.setattr(profile_provider, "get_qwen_backend_preference", lambda: "automatic")
    monkeypatch.setattr(profile_provider, "get_qwen_model_preference", lambda: "0.6b")
    monkeypatch.setattr(
        profile_provider,
        "qwen_model_kinds_for_preference",
        lambda mode, preference: ("custom-0.6b", "base-0.6b"),
    )
    profile = VoiceProfile(
        name="Explicit CPU",
        provider="qwen-character",
        voice_id="Ryan",
        backend="cpu",
        qwen_mode="custom",
    )

    profile_provider.provider_from_profile(profile)
    assert captured["backend"] == "cpu"
