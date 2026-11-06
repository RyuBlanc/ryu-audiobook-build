from __future__ import annotations

from pathlib import Path
import sys
import wave

from ..base import TTSProvider
from app.core.paths import models_root
from app.tts.pacing import pause_after_ms, sentence_units


class PiperProvider(TTSProvider):
    provider_id = "piper"

    def __init__(self, model_path: Path | None = None, backend: str = "automatic"):
        self.model_path = model_path
        self.backend = backend
        self._voice = None
        self._loaded_path: Path | None = None
        self._execution_providers: tuple[str, ...] = ()
        self._execution_backend = "unverified"
        self._narration_speed = 1.0
        self._pacing_profile = "natural"

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
        session = getattr(self._voice, "session", None)
        if session is None:
            session = getattr(self._voice, "_session", None)
        get_providers = getattr(session, "get_providers", None)
        if callable(get_providers):
            try:
                self._execution_providers = tuple(str(item) for item in get_providers())
            except Exception:
                self._execution_providers = ()
        if "CUDAExecutionProvider" in self._execution_providers:
            self._execution_backend = "cuda"
        elif "DmlExecutionProvider" in self._execution_providers:
            self._execution_backend = "directml"
        elif "CPUExecutionProvider" in self._execution_providers:
            self._execution_backend = "cpu"
        elif self._execution_providers:
            self._execution_backend = "other"

    @property
    def execution_providers(self) -> tuple[str, ...]:
        return self._execution_providers

    @property
    def execution_backend(self) -> str:
        return self._execution_backend

    @property
    def execution_backend_verified(self) -> bool:
        return bool(self._execution_providers)

    def configure_narration(self, speed: float = 1.0, pacing_profile: str = "natural") -> None:
        """Configure native Piper pacing so speed changes happen during synthesis."""
        self._narration_speed = max(0.5, min(1.5, float(speed)))
        self._pacing_profile = str(pacing_profile or "natural")

    @property
    def handles_narration_controls(self) -> bool:
        return True

    @staticmethod
    def _length_scale_for_speed(speed: float) -> float:
        speed = max(0.5, min(1.5, float(speed)))
        return 1.0 / speed

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> Path:
        path = self._resolve_model(voice)
        self._load(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            from piper import SynthesisConfig
            syn_config = SynthesisConfig(
                length_scale=self._length_scale_for_speed(self._narration_speed),
                normalize_audio=False,
            )
        except (ImportError, TypeError):
            syn_config = None

        units = sentence_units(text)
        silence_cache: dict[int, bytes] = {}

        with wave.open(str(output_path), "wb") as wav_file:
            first_chunk = True
            chunks = (
                self._voice.synthesize(text, syn_config=syn_config)
                if syn_config is not None
                else self._voice.synthesize(text)
            )
            for index, audio_chunk in enumerate(chunks):
                if first_chunk:
                    wav_file.setframerate(audio_chunk.sample_rate)
                    wav_file.setsampwidth(audio_chunk.sample_width)
                    wav_file.setnchannels(audio_chunk.sample_channels)
                    first_chunk = False

                wav_file.writeframes(audio_chunk.audio_int16_bytes)

                sentence_text = units[min(index, len(units) - 1)] if units else text
                pause_ms = pause_after_ms(sentence_text, self._pacing_profile)
                if pause_ms > 0:
                    key = round(audio_chunk.sample_rate * pause_ms / 1000.0)
                    silence = silence_cache.get(key)
                    if silence is None:
                        silence = (
                            b"\x00"
                            * key
                            * audio_chunk.sample_width
                            * audio_chunk.sample_channels
                        )
                        silence_cache[key] = silence
                    wav_file.writeframes(silence)

        return output_path
