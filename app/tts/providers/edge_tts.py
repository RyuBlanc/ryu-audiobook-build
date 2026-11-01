from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
import time
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
    stop_on_failure = True
    request_timeout_seconds = 60
    transient_retry_attempts = 5

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

    @classmethod
    def _is_transient_service_error(cls, detail: str) -> bool:
        lowered = detail.casefold()
        markers = (
            "getaddrinfo failed",
            "cannot connect to host",
            "temporary failure in name resolution",
            "name or service not known",
            "connection refused",
            "connection reset",
            "timed out",
            "no audio was received",
            "noaudioreceived",
            "websocket",
            "server disconnected",
        )
        return any(marker in lowered for marker in markers)

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

            last_error: Exception | None = None
            attempts = self.transient_retry_attempts
            for attempt in range(attempts):
                mp3_path.unlink(missing_ok=True)
                try:
                    _run(asyncio.wait_for(generate(), timeout=self.request_timeout_seconds))
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    detail = str(exc)
                    transient = self._is_transient_service_error(detail)
                    if attempt < attempts - 1 and transient:
                        # Give transient Microsoft/WebSocket failures time to
                        # recover. Each attempt creates a fresh Communicate
                        # object and therefore a fresh WebSocket session.
                        time.sleep(min(10.0, 1.5 * (attempt + 1)))
                    elif attempt < 2 and not transient:
                        time.sleep(1.5 * (attempt + 1))
                    else:
                        break

            if last_error is not None:
                detail = str(last_error)
                if self._is_transient_service_error(detail):
                    raise OnlineTTSNetworkError(
                        "Microsoft's online voice service returned no usable audio "
                        f"after {attempts} attempts. This can happen even with a "
                        "working internet connection when the Edge TTS service or "
                        "WebSocket session is temporarily refusing/closing synthesis. "
                        "No M4B packaging was attempted, and completed offline/online "
                        "chunks remain available for resume.\n"
                        f"Details: {detail}"
                    ) from last_error
                raise RuntimeError(
                    "Online voice synthesis failed after 3 attempts. "
                    f"Details: {detail}"
                ) from last_error

            if not mp3_path.exists() or mp3_path.stat().st_size < 1024:
                raise OnlineTTSNetworkError(
                    "Microsoft's online voice service returned no usable audio "
                    f"after {attempts} attempts."
                )

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
