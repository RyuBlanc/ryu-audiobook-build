from pathlib import Path

from ..base import TTSProvider


class PiperProvider(TTSProvider):
    """Adapter placeholder for the optional Piper ONNX runtime.

    Keeping Piper behind TTSProvider lets the rest of the audiobook pipeline
    work without knowing which local TTS engine is installed.
    """

    provider_id = "piper"

    def __init__(self, model_path: Path | None = None, backend: str = "automatic"):
        self.model_path = model_path
        self.backend = backend

    def voices(self) -> list[str]:
        if self.model_path and self.model_path.exists():
            return [self.model_path.stem]
        return []

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> Path:
        raise RuntimeError(
            "Piper is not installed yet. Install a Piper voice/model from the app's Models page first."
        )
