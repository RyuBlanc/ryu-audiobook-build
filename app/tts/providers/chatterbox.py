from pathlib import Path

from ..base import TTSProvider


class ChatterboxProvider(TTSProvider):
    """Adapter boundary for local Chatterbox voice cloning.

    A reference sample is passed to the provider; the rest of the audiobook
    pipeline does not need to know which cloning model is active.
    """

    provider_id = "chatterbox"

    def __init__(
        self,
        model_path: Path | None = None,
        reference_audio: Path | None = None,
        backend: str = "automatic",
        language: str | None = None,
    ):
        self.model_path = model_path
        self.reference_audio = reference_audio
        self.backend = backend
        self.language = language

    def voices(self) -> list[str]:
        return [self.reference_audio.stem] if self.reference_audio and self.reference_audio.exists() else []

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> Path:
        raise RuntimeError(
            "Chatterbox runtime is not installed yet. Install a compatible local model from the app's Models page first."
        )
