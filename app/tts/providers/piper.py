from __future__ import annotations

from pathlib import Path
import sys
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
    def _bundled_root() -> Path | None:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            path = Path(meipass) / "bundled_models" / "piper"
            if path.exists():
                return path

        # Source/dev runs can also use a local bundled_models directory.
        path = Path(__file__).resolve().parents[3] / "bundled_models" / "piper"
        return path if path.exists() else None

    @classmethod
    def model_paths(cls) -> list[Path]:
        paths: list[Path] = []
        user_root = models_root() / "piper"
        if user_root.exists():
            paths.extend(user_root.rglob("*.onnx"))
        bundled = cls._bundled_root()
        if bundled:
            paths.extend(bundled.rglob("*.onnx"))

        unique: dict[str, Path] = {}
        for path in paths:
            unique.setdefault(path.stem.casefold(), path)
        return sorted(unique.values(), key=lambda p: p.stem.casefold())

    def voices(self) -> list[str]:
        return [path.stem for path in self.model_paths()]

    def _resolve_model(self, voice: str | None) -> Path:
        if self.model_path and self.model_path.exists():
            return self.model_path

        paths = self.model_paths()
        if not paths:
            raise RuntimeError(
                "No offline neural voice model is installed. Reinstall Ryu's Audiobook "
                "or open Models to install a local voice."
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
                "The offline Piper neural runtime is missing from this installation."
            ) from exc

        use_cuda = self.backend == "cuda"
        if self.backend == "automatic":
            try:
                import onnxruntime as ort
                use_cuda = "CUDAExecutionProvider" in ort.get_available_providers()
            except Exception:
                use_cuda = False

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
