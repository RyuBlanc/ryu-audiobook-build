from pathlib import Path
import wave

from ..base import TTSProvider
from app.core.paths import models_root


class PiperProvider(TTSProvider):
    provider_id = "piper"

    def __init__(self, model_path: Path | None = None, backend: str = "automatic"):
        self.model_path = model_path
        self.backend = backend
        self._voice = None
        self._loaded_path: Path | None = None

    @staticmethod
    def model_paths() -> list[Path]:
        root = models_root() / "piper"
        if not root.exists():
            return []
        return sorted(root.rglob("*.onnx"))

    def voices(self) -> list[str]:
        return [path.stem for path in self.model_paths()]

    def _resolve_model(self, voice: str | None) -> Path:
        if self.model_path and self.model_path.exists():
            return self.model_path

        paths = self.model_paths()
        if not paths:
            raise RuntimeError(
                "No Piper voice model is installed. Open Models and download a Piper voice first."
            )

        if voice:
            for path in paths:
                if path.stem == voice:
                    return path

        return paths[0]

    def _load(self, path: Path) -> None:
        if self._voice is not None and self._loaded_path == path:
            return

        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise RuntimeError(
                "Piper runtime is not installed. Reinstall Ryu's Audiobook with the Piper TTS component."
            ) from exc

        use_cuda = self.backend == "cuda"
        try:
            self._voice = PiperVoice.load(str(path), use_cuda=use_cuda)
        except TypeError:
            self._voice = PiperVoice.load(str(path))
        self._loaded_path = path

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> Path:
        path = self._resolve_model(voice)
        self._load(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with wave.open(str(output_path), "wb") as wav_file:
            self._voice.synthesize_wav(text, wav_file)

        return output_path
