from __future__ import annotations

import threading
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock

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



def test_running_character_analysis_job_can_be_cancelled_from_task_manager():
    event = threading.Event()
    job = {"job_id": "analysis-1", "type": "character-analysis", "state": "running"}
    update = Mock(side_effect=lambda job_id, **changes: {**job, **changes})
    bridge = SimpleNamespace(
        _jobs_lock=RLock(),
        _jobs={"analysis-1": job},
        _generators={},
        _analysis_cancel_events={"analysis-1": event},
        _preview_cancel_events={},
        _import_cancel_events={},
        _job_update=update,
    )

    result = __import__("app.ui.premium_v2_host", fromlist=["PremiumV2Bridge"]).PremiumV2Bridge._job_cancel(
        bridge, {"job_id": "analysis-1"}
    )

    assert event.is_set()
    assert result["state"] == "cancel_requested"
    update.assert_called_once()
    assert update.call_args.kwargs["stage"] == "Cancellation requested"


def test_task_manager_offers_cancel_for_character_analysis_jobs():
    adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
    start = adapter.index("function backgroundGenerationJobActions(")
    end = adapter.index("let backendJobFilter", start)
    section = adapter[start:end]
    assert "const canCancelAnalysis = String(job.type || '').toLowerCase() === 'character-analysis';" in section
    assert "(canCancelAnalysis && ['queued','running'].includes(state))" in section
    assert "!canCancelAnalysis" in section
