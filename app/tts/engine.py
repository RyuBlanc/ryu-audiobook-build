from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .base import TTSProvider
from .model_registry import ModelSpec, installed_models, get_model


@dataclass
class EngineSelection:
    model_id: str
    backend: str
    reason: str


class LocalTTSEngine:
    """Hardware-neutral TTS orchestration layer.

    Model implementations live behind providers. The engine decides which
    installed model/backend to use, while generation code remains unchanged.
    """

    def __init__(self, provider: TTSProvider | None = None):
        self.provider = provider

    def available_models(self) -> list[ModelSpec]:
        return installed_models()

    def select_model(self, model_id: str | None = None, backend: str = "automatic") -> EngineSelection:
        if model_id:
            spec = get_model(model_id)
            if spec is None:
                raise ValueError(f"Unknown TTS model: {model_id}")
            return EngineSelection(spec.model_id, backend, "User selected model")

        models = installed_models()
        if models:
            # Prefer a cloning-capable model when a user has installed one.
            cloning = [m for m in models if m.voice_cloning]
            chosen = cloning[0] if cloning else models[0]
            return EngineSelection(chosen.model_id, backend, "Best installed compatible model")

        return EngineSelection("system-sapi", "cpu", "No local AI model installed; using Windows SAPI fallback")

    def synthesize(
        self,
        text: str,
        output_path: Path,
        voice: str | None = None,
        progress: Callable[[float], None] | None = None,
    ) -> Path:
        if self.provider is None:
            raise RuntimeError("No TTS provider is configured.")
        return self.provider.synthesize(text, output_path, voice=voice)
