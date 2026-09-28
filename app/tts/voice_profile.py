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

    builtins = list(builtin_voice_profiles())
    combined = list(builtins)

    # A custom voice must never disappear merely because its display name
    # happens to match a bundled Piper voice. Keep saved profiles distinct
    # by provider/voice identity and prefer the saved custom profile when
    # the identity is genuinely the same.
    builtin_keys = {
        ("piper", p.voice_id.casefold(), "")
        for p in builtins
    }
    seen_names: set[str] = {p.name.casefold() for p in combined}
    # Process saved built-in Piper identities first so a custom profile that
    # reuses a bundled display name is still kept distinct even when the
    # bundled model files are not installed yet.
    ordered_saved = sorted(
        saved,
        key=lambda p: (0 if p.provider == "piper" else 1, p.name.casefold()),
    )
    for profile in ordered_saved:
        sample_key = str(profile.sample_path or "").casefold()
        identity = (profile.provider, profile.voice_id.casefold(), sample_key)

        if identity in builtin_keys and not sample_key:
            continue

        # Preserve a custom profile even if it shares a display name with a
        # bundled voice. The UI will make the provider visible where needed.
        if profile.name.casefold() in seen_names:
            if profile.provider != "piper":
                suffix = " • Custom"
                base = profile.name
                candidate = base + suffix
                n = 2
                while candidate.casefold() in seen_names:
                    candidate = f"{base}{suffix} {n}"
                    n += 1
                profile.name = candidate
        combined.append(profile)
        seen_names.add(profile.name.casefold())
    return combined


def save_profiles(profiles: list[VoiceProfile]) -> None:
    voices_root().mkdir(parents=True, exist_ok=True)
    builtins = {
        (p.provider, p.voice_id.casefold())
        for p in builtin_voice_profiles()
    }
    persistent = [
        p for p in profiles
        if (p.provider, p.voice_id.casefold()) not in builtins
        or p.sample_path
        or p.provider != "piper"
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
