from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TTSProvider(ABC):
    """Interface shared by system and future local AI TTS engines."""

    @abstractmethod
    def voices(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> Path:
        raise NotImplementedError
