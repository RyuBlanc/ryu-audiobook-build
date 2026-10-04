from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import shutil
import subprocess
import wave

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
    exaggeration: float = 0.5
    cfg_weight: float = 0.35
    style_preset: str = "Natural"
    # Qwen3-TTS phase/profile metadata. These fields are optional so older
    # voice profiles continue to load without migration.
    qwen_mode: str = "custom"
    qwen_prompt: str = ""
    qwen_seed: int | None = None
    reference_text: str = ""


def profiles_file() -> Path:
    return voices_root() / "voices.json"


def _qwen_runtime_available() -> bool:
    try:
        from app.tts.qwen_character_runtime import runtime_ready
        return runtime_ready()
    except Exception:
        return False


def builtin_voice_profiles() -> list[VoiceProfile]:
    """Return local neural voices available on this installation."""
    result: list[VoiceProfile] = []
    offline_fallbacks: list[VoiceProfile] = []

    try:
        from app.tts.providers.piper import PiperProvider
        paths = PiperProvider.model_paths()
    except Exception:
        paths = []

    metadata = {
        "en_US-amy-medium": ("en-US", "Female", "Amy", "Recommended offline fallback voice"),
        "en_US-lessac-medium": ("en-US", "Male", "Lessac", "Recommended offline fallback voice"),
        "en_US-ryan-high": ("en-US", "Male", "Ryan", "High-quality offline fallback voice"),
    }
    for path in paths:
        language, gender, friendly, note = metadata.get(
            path.stem,
            (path.stem.split("-", 1)[0], "Neutral", path.stem, "Built-in offline neural voice"),
        )
        offline_fallbacks.append(
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

    # Kokoro profiles are exposed only when its local model + voice pack are
    # actually present. This keeps the voice picker honest and avoids saving
    # profiles that cannot be previewed or generated on the current PC.
    try:
        from app.tts.providers.kokoro import KokoroProvider
        if KokoroProvider.assets_available():
            catalog = KokoroProvider().voices()
            for voice_id in catalog:
                language = KokoroProvider._language_for_voice(voice_id)
                region = {
                    "en-us": "English (US)",
                    "en-gb": "English (UK)",
                    "ja": "Japanese",
                    "cmn": "Chinese",
                    "es": "Spanish",
                    "fr-fr": "French",
                    "hi": "Hindi",
                }.get(language, language)
                result.append(
                    VoiceProfile(
                        name=f"Kokoro Natural • {voice_id}",
                        provider="kokoro",
                        voice_id=voice_id,
                        model_id="kokoro",
                        backend="automatic",
                        language=language,
                        notes=f"Offline natural voice • {region} • Kokoro voice catalogue",
                        authorized=True,
                    )
                )
    except Exception:
        pass

    # Qwen3-TTS offline character voices. Keep the catalogue visible even
    # before the model is installed so the user can choose a character first;
    # preview/generation will clearly request the local model when it is missing.
    # Native languages are respected: only Ryan/Aiden are native-English Qwen
    # speakers, while Vivian/Serena/Uncle_Fu/Dylan/Eric/Ono_Anna/Sohee retain
    # their documented native languages.
    qwen_profiles = [
        ("Anime Hero", "Ryan", "Dynamic English male character; confident anime-protagonist energy, crisp diction, expressive emotional lifts and cinematic pacing.", "English"),
        ("Anime Rival", "Ryan", "Cool English male rival; restrained confidence, teasing edge, controlled intensity and clean audiobook diction.", "English"),
        ("Anime Hero • Warm", "Aiden", "Sunny American English male character; warm young-protagonist energy, optimistic emotion and natural conversational delivery.", "English"),
        ("Anime Sidekick", "Aiden", "Playful American English male sidekick; bright comic timing, lively reactions and clear intelligible delivery.", "English"),
        ("Anime / Cartoon • Vivian", "Vivian", "Bright slightly edgy young female voice. Best quality is obtained in the speaker's native Chinese; style instructions can add animated energy.", "Chinese"),
        ("Anime / Cartoon • Serena", "Serena", "Warm gentle young female voice. Best quality is obtained in the speaker's native Chinese; style instructions can add soft anime warmth.", "Chinese"),
        ("Anime Villain • Uncle Fu", "Uncle_Fu", "Seasoned low mellow male voice. Best quality is obtained in native Chinese; strong theatrical villain delivery.", "Chinese"),
        ("Anime • Japanese Female", "Ono_Anna", "Playful Japanese female voice with a light nimble timbre; ideal for Japanese character dialogue.", "Japanese"),
        ("Anime • Korean Female", "Sohee", "Warm Korean female voice with rich emotion; ideal for Korean character dialogue.", "Korean"),
    ]
    for name, speaker, instruct, language in qwen_profiles:
        result.append(
            VoiceProfile(
                name=f"Offline Character • {name}",
                provider="qwen-character",
                voice_id=speaker,
                model_id="auto",
                backend="automatic",
                language=language,
                notes=(
                    f"{instruct} "
                    "Qwen3-TTS CustomVoice • use the speaker's native language for best quality."
                ),
                authorized=True,
                qwen_mode="custom",
                qwen_prompt=instruct,
            )
        )

    # Prefer Kokoro natural voices in the picker when installed; keep Piper
    # available as the lightweight fallback.
    return result + offline_fallbacks


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

    builtin_keys = {
        (p.provider, p.voice_id.casefold(), "")
        for p in builtins
    }
    seen_names: set[str] = {p.name.casefold() for p in combined}
    ordered_saved = sorted(
        saved,
        key=lambda p: (0 if p.provider in {"piper", "kokoro"} else 1, p.name.casefold()),
    )
    for profile in ordered_saved:
        sample_key = str(profile.sample_path or "").casefold()
        identity = (profile.provider, profile.voice_id.casefold(), sample_key)

        if identity in builtin_keys and not sample_key:
            continue

        if profile.name.casefold() in seen_names:
            if profile.provider not in {"piper", "kokoro"}:
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
        or p.provider not in {"piper", "kokoro"}
    ]
    profiles_file().write_text(
        json.dumps([asdict(profile) for profile in persistent], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def import_reference_audio(source: Path, profile_name: str, minimum_seconds: float = 6.0) -> Path:
    voices_root().mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in profile_name).strip() or "voice"
    target_dir = voices_root() / safe
    target_dir.mkdir(parents=True, exist_ok=True)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(source)

    original = target_dir / source.name
    shutil.copy2(source, original)
    target = target_dir / "reference.wav"

    # Always normalize the clone reference, including WAV files. This prevents
    # stereo/48 kHz/float input differences from changing Chatterbox conditioning.
    result = subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(source), "-vn",
            "-ac", "1", "-ar", "24000", "-sample_fmt", "s16",
            "-c:a", "pcm_s16le", str(target),
        ],
        check=False, capture_output=True, text=True,
    )
    if result.returncode != 0 or not target.exists() or target.stat().st_size < 1024:
        raise RuntimeError(
            "The selected audio could not be converted to a normalized Chatterbox reference. "
            + (result.stderr[-1600:] if result.stderr else "")
        )
    # Chatterbox reference conditioning requires audio longer than five seconds.
    # Validate imported references here so the user gets a clear error before
    # the model is loaded.
    try:
        with wave.open(str(target), "rb") as handle:
            duration = handle.getnframes() / max(1, handle.getframerate())
    except (OSError, wave.Error) as exc:
        raise RuntimeError(f"The reference audio could not be inspected: {exc}") from exc
    if duration < float(minimum_seconds):
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(
            f"The reference recording is only {duration:.1f} seconds long. "
            f"Premium cloning requires a clean reference of at least {float(minimum_seconds):.0f} seconds; "
            "around 10 seconds of clear single-speaker speech is recommended."
        )
    try:
        with wave.open(str(target), "rb") as handle:
            channels = handle.getnchannels()
            sample_rate = handle.getframerate()
            sample_width = handle.getsampwidth()
        if channels != 1 or sample_rate != 24000 or sample_width != 2:
            raise RuntimeError(
                f"Normalized reference format is {channels}ch/{sample_rate}Hz/{sample_width * 8}-bit; "
                "expected mono 24 kHz PCM16."
            )
    except (OSError, wave.Error) as exc:
        raise RuntimeError(f"The normalized reference could not be validated: {exc}") from exc
    return target
