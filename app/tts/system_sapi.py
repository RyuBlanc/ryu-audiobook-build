from __future__ import annotations

from pathlib import Path

import pyttsx3

from .base import TTSProvider


class SystemSAPIProvider(TTSProvider):
    """Offline Windows SAPI/pyttsx3 provider for the first working build."""

    def __init__(self) -> None:
        self._engine = pyttsx3.init()

    def voices(self) -> list[str]:
        return [voice.id for voice in self._engine.getProperty("voices")]

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if voice:
            self._engine.setProperty("voice", voice)
        self._engine.save_to_file(text, str(output_path))
        self._engine.runAndWait()
        return output_path
