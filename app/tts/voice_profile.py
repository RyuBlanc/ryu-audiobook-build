from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json

from app.core.paths import voices_root

@dataclass
class VoiceProfile:
    name: str
    provider: str
    voice_id: str
    sample_path: str | None = None
    notes: str = ""

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
    profiles_file().write_text(
        json.dumps([asdict(profile) for profile in profiles], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
