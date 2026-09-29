from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path

from app.core.paths import settings_root
from app.tts.base import TTSProvider

try:
    import edge_tts
except ImportError:  # Optional at import time for developer environments.
    edge_tts = None


VOICE_CACHE = settings_root() / "edge_tts_voices.json"


class OnlineTTSNetworkError(RuntimeError):
    """The online neural provider cannot currently reach its synthesis service."""


def _run(coro):
    return asyncio.run(coro)


class EdgeTTSProvider(TTSProvider):
    """Microsoft Edge neural TTS provider.

    This provider gives access to a large, changing catalog of multilingual
    neural voices. Synthesis requires an internet connection; the voice
    catalog is cached locally so the UI remains useful offline.
    """

    provider_id = "edge-tts"
    is_online_provider = True

    def __init__(self) -> None:
        if edge_tts is None:
            raise RuntimeError(
                "Microsoft Edge neural voices are not installed in this build."
            )

    @classmethod
    def available(cls) -> bool:
        return edge_tts is not None

    @classmethod
    def fetch_voice_metadata(cls, refresh: bool = False) -> list[dict]:
        settings_root().mkdir(parents=True, exist_ok=True)

        if not refresh and VOICE_CACHE.exists():
            try:
                data = json.loads(VOICE_CACHE.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    return data
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass

        if edge_tts is None:
            return []

        voices = _run(edge_tts.list_voices())
        cleaned = []
        for voice in voices:
            cleaned.append(
                {
                    "name": voice.get("ShortName", ""),
                    "locale": voice.get("Locale", ""),
                    "gender": voice.get("Gender", ""),
                    "friendly_name": voice.get("FriendlyName", ""),
                    "categories": voice.get("VoiceTag", {}).get("ContentCategories", []),
                    "personalities": voice.get("VoiceTag", {}).get("VoicePersonalities", []),
                }
            )

        VOICE_CACHE.write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return cleaned

    def voices(self) -> list[str]:
        return [item["name"] for item in self.fetch_voice_metadata() if item.get("name")]

    def synthesize(
        self,
        text: str,
        output_path: Path,
        voice: str | None = None,
    ) -> Path:
        if not voice:
            raise ValueError("An Edge neural voice must be selected.")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="ryu-edge-") as temp_dir:
            mp3_path = Path(temp_dir) / "speech.mp3"

            async def generate() -> None:
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(str(mp3_path))

            try:
                _run(asyncio.wait_for(generate(), timeout=120))
            except asyncio.TimeoutError as exc:
                raise RuntimeError(
                    "Online voice synthesis timed out after 120 seconds. "
                    "Check the internet connection or switch to an offline neural voice."
                ) from exc

            if not mp3_path.exists() or mp3_path.stat().st_size < 1024:
                raise RuntimeError("Edge TTS did not produce valid audio.")

            if output_path.suffix.lower() == ".mp3":
                mp3_path.replace(output_path)
                return output_path

            import imageio_ffmpeg

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(mp3_path),
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    str(output_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

        return output_path
