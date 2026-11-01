from dataclasses import dataclass
from pathlib import Path
import json

from app.core.paths import models_root, settings_root


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    display_name: str
    provider: str
    voice_cloning: bool
    multilingual: bool
    preferred_backends: tuple[str, ...]
    notes: str = ""


BUILTIN_CATALOG = (
    ModelSpec(
        "piper",
        "Piper",
        "piper",
        False,
        True,
        ("cpu", "cuda"),
        "Fast local neural TTS. Individual voice models are downloaded separately."
    ),
    ModelSpec(
        "kokoro",
        "Kokoro 82M",
        "kokoro",
        False,
        True,
        ("cuda", "directml", "cpu"),
        "Natural offline TTS with a broad voice catalogue. Model and voice pack are downloaded separately."
    ),
    ModelSpec(
        "chatterbox",
        "Chatterbox",
        "chatterbox",
        True,
        False,
        ("cuda", "cpu"),
        "English voice cloning from a reference recording."
    ),
    ModelSpec(
        "chatterbox-multilingual",
        "Chatterbox Multilingual",
        "chatterbox",
        True,
        True,
        ("cuda", "cpu"),
        "Multilingual zero-shot voice cloning from a reference recording."
    ),
)


def _manifest_path() -> Path:
    return settings_root() / "models.json"


def installed_model_ids() -> set[str]:
    path = _manifest_path()
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(x) for x in data.get("installed", [])}
    except (OSError, ValueError, TypeError):
        return set()


def _has_kokoro_assets() -> bool:
    root = models_root() / "kokoro"
    model = any((root / name).exists() for name in ("kokoro-v1.0.onnx", "model.onnx", "model_q8f16.onnx", "model_quantized.onnx"))
    voices = any((root / name).exists() for name in ("voices-v1.0.bin", "voices.bin"))
    return model and voices


def installed_models() -> list[ModelSpec]:
    ids = installed_model_ids()
    result = [m for m in BUILTIN_CATALOG if m.model_id in ids]
    if (models_root() / "piper").exists() and any((models_root() / "piper").rglob("*.onnx")):
        if not any(m.model_id == "piper" for m in result):
            result.append(get_model("piper"))
    if _has_kokoro_assets() and not any(m.model_id == "kokoro" for m in result):
        result.append(get_model("kokoro"))
    return [m for m in result if m is not None]


def get_model(model_id: str) -> ModelSpec | None:
    return next((m for m in BUILTIN_CATALOG if m.model_id == model_id), None)


def mark_installed(model_id: str, installed: bool = True) -> None:
    if get_model(model_id) is None:
        raise ValueError(f"Unknown TTS model: {model_id}")

    path = _manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    ids = installed_model_ids()
    if installed:
        ids.add(model_id)
    else:
        ids.discard(model_id)
    path.write_text(json.dumps({"installed": sorted(ids)}, indent=2), encoding="utf-8")
