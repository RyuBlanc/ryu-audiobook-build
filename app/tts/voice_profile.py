from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import shutil

from app.core.paths import voices_root


@dataclass
class VoiceProfile:
    name: str
    provider: str
    voice_id: str
    sample_path: str | None = None
    model_id: str | None = None
    backend: str = "automatic"
    language: str | None = None
    notes: str = ""
    authorized: bool = False


def profiles_file() -> Path:
    return voices_root() / "voices.json"


def load_profiles() -> list[VoiceProfile]:
    path = profiles_file()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [VoiceProfile(**item) for item in data]
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return []


def save_profiles(profiles: list[VoiceProfile]) -> None:
    voices_root().mkdir(parents=True, exist_ok=True)
    profiles_file().write_text(
        json.dumps([asdict(profile) for profile in profiles], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def import_reference_audio(source: Path, profile_name: str) -> Path:
    voices_root().mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in profile_name).strip() or "voice"
    target_dir = voices_root() / safe
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    shutil.copy2(source, target)
    return target
