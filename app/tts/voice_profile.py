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


def builtin_voice_profiles() -> list[VoiceProfile]:
    """Return neural voices shipped with the application, when present."""
    try:
        from app.tts.providers.piper import PiperProvider
        paths = PiperProvider.model_paths()
    except Exception:
        return []

    metadata = {
        "en_US-amy-medium": ("en-US", "Female", "Amy", "Recommended offline narrator voice"),
        "en_US-lessac-medium": ("en-US", "Male", "Lessac", "Recommended offline narrator voice"),
        "en_US-ryan-high": ("en-US", "Male", "Ryan", "High-quality offline narrator voice"),
    }
    result: list[VoiceProfile] = []
    for path in paths:
        language, gender, friendly, note = metadata.get(
            path.stem,
            (path.stem.split("-", 1)[0], "Neutral", path.stem, "Built-in offline neural voice"),
        )
        result.append(
            VoiceProfile(
                name=f"Offline Neural • {friendly}",
                provider="piper",
                voice_id=path.stem,
                model_id="piper",
                backend="automatic",
                language=language,
                notes=f"Built-in offline voice • {gender} • {note}",
                authorized=True,
            )
        )
    return result


def load_profiles() -> list[VoiceProfile]:
    path = profiles_file()
    saved: list[VoiceProfile] = []
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            saved = [VoiceProfile(**item) for item in data]
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            saved = []

    combined = list(builtin_voice_profiles())
    names = {p.name.casefold() for p in combined}
    for profile in saved:
        if profile.name.casefold() not in names:
            combined.append(profile)
            names.add(profile.name.casefold())
    return combined


def save_profiles(profiles: list[VoiceProfile]) -> None:
    voices_root().mkdir(parents=True, exist_ok=True)
    persistent = [
        p for p in profiles
        if not p.name.startswith("Offline Neural •")
        and not p.notes.lower().startswith("built-in offline")
    ]
    profiles_file().write_text(
        json.dumps([asdict(profile) for profile in persistent], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def import_reference_audio(source: Path, profile_name: str) -> Path:
    voices_root().mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in profile_name).strip() or "voice"
    target_dir = voices_root() / safe
    target_dir.mkdir(parents=True, exist_ok=True)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(source)

    original = target_dir / source.name
    shutil.copy2(source, original)
    target = target_dir / "reference.wav"
    if source.suffix.lower() == ".wav":
        shutil.copy2(source, target)
    else:
        result = subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(source), "-vn",
                "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(target),
            ],
            check=False, capture_output=True, text=True,
        )
        if result.returncode != 0 or not target.exists() or target.stat().st_size < 1024:
            raise RuntimeError(
                "The selected audio could not be converted to a local WAV reference. "
                + (result.stderr[-1200:] if result.stderr else "")
            )
    return target
