from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import shutil
import subprocess

import imageio_ffmpeg

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
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(source)

    # Keep the original reference recording, and create a normalized WAV copy
    # for local voice engines so MP3/M4A/FLAC/etc. can be used reliably.
    original = target_dir / source.name
    shutil.copy2(source, original)

    target = target_dir / "reference.wav"
    if source.suffix.lower() == ".wav":
        shutil.copy2(source, target)
    else:
        result = subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-y",
                "-i", str(source),
                "-vn",
                "-ac", "1",
                "-ar", "24000",
                "-c:a", "pcm_s16le",
                str(target),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not target.exists() or target.stat().st_size < 1024:
            raise RuntimeError(
                "The selected audio could not be converted to a local WAV reference. "
                + (result.stderr[-1200:] if result.stderr else "")
            )
    return target
