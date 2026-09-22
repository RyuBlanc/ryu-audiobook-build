from pathlib import Path

from ..base import TTSProvider


class KokoroProvider(TTSProvider):
    """Adapter boundary for the optional Kokoro runtime.

    The model is deliberately not bundled with the application. Once the
    runtime is installed, this provider can be connected without changing
    chapter generation, M4B assembly, or the UI.
    """

    provider_id = "kokoro"

    def __init__(self, model_path: Path | None = None, backend: str = "automatic"):
        self.model_path = model_path
        self.backend = backend

    def voices(self) -> list[str]:
        return []

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> Path:
        raise RuntimeError(
            "Kokoro runtime is not installed yet. Install a Kokoro model from the app's Models page first."
        )
