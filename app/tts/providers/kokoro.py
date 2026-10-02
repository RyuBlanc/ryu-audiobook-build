from __future__ import annotations

from pathlib import Path
import sys

from app.core.paths import models_root

from ..base import TTSProvider


KOKORO_VOICES = (
    # American English
    "af_heart", "af_bella", "af_nicole", "af_aoede", "af_kore", "af_sarah",
    "af_nova", "af_sky", "af_alloy", "af_jessica", "af_river",
    "am_michael", "am_fenrir", "am_puck", "am_echo", "am_eric", "am_liam",
    "am_onyx", "am_santa", "am_adam",
    # British English
    "bf_emma", "bf_isabella", "bf_alice", "bf_lily",
    "bm_george", "bm_fable", "bm_lewis", "bm_daniel",
    # Other currently published voice ids; exposed for future multilingual casting.
    "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
    "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
    "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
    "ef_dora", "em_alex", "em_santa", "ff_siwis",
    "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
)


class KokoroProvider(TTSProvider):
    """Offline Kokoro-ONNX provider.

    The runtime is imported lazily so Ryu's Audiobook can still start when a
    user has not installed/downloaded the optional Kokoro assets. The model
    and voice pack may live in the user's Models folder or in the frozen app's
    bundled_models/kokoro directory.
    """

    provider_id = "kokoro"
    sample_rate = 24000

    def __init__(self, model_path: Path | None = None, voices_path: Path | None = None, backend: str = "automatic"):
        self.model_path = model_path or self._find_model()
        self.voices_path = voices_path or self._find_voices()
        self.backend = backend
        self._runtime = None

    @staticmethod
    def _frozen_root() -> Path | None:
        root = getattr(sys, "_MEIPASS", None)
        return Path(root) if root else None

    @classmethod
    def _candidate_roots(cls) -> list[Path]:
        roots = [models_root() / "kokoro"]
        frozen = cls._frozen_root()
        if frozen:
            roots.insert(0, frozen / "bundled_models" / "kokoro")
        return roots

    @classmethod
    def _find_model(cls) -> Path | None:
        names = ("kokoro-v1.0.onnx", "model.onnx", "model_q8f16.onnx", "model_quantized.onnx")
        for root in cls._candidate_roots():
            for name in names:
                path = root / name
                if path.exists():
                    return path
        return None

    @classmethod
    def _find_voices(cls) -> Path | None:
        names = ("voices-v1.0.bin", "voices.bin")
        for root in cls._candidate_roots():
            for name in names:
                path = root / name
                if path.exists():
                    return path
        return None

    @classmethod
    def assets_available(cls) -> bool:
        return cls._find_model() is not None and cls._find_voices() is not None

    def voices(self) -> list[str]:
        return list(KOKORO_VOICES)

    def _load_runtime(self):
        if self._runtime is not None:
            return self._runtime
        if self.model_path is None or self.voices_path is None:
            raise RuntimeError(
                "Kokoro voice assets are not installed. Add kokoro-v1.0.onnx "
                "and voices-v1.0.bin to the app's Models\\kokoro folder."
            )
        try:
            from kokoro_onnx import EspeakConfig, Kokoro
        except ImportError as exc:
            raise RuntimeError(
                "Kokoro runtime is not installed. Install the application's optional Kokoro runtime first."
            ) from exc

        espeak_config = None
        try:
            import espeakng_loader
            data_path = Path(espeakng_loader.get_data_path())
            lib_path = Path(espeakng_loader.get_library_path())
            if not data_path.exists():
                raise RuntimeError(f"Kokoro eSpeak data is missing at {data_path}")
            if not lib_path.exists():
                raise RuntimeError(f"Kokoro eSpeak library is missing at {lib_path}")
            espeak_config = EspeakConfig(
                lib_path=str(lib_path),
                data_path=str(data_path),
            )
        except Exception as exc:
            raise RuntimeError(
                "Kokoro's offline phonemizer data is not installed correctly. "
                "Repair/reinstall Natural Voices and restart Ryu's Audiobook. "
                f"Details: {exc}"
            ) from exc

        self._runtime = Kokoro(
            str(self.model_path),
            str(self.voices_path),
            espeak_config=espeak_config,
        )
        return self._runtime

    @staticmethod
    def _language_for_voice(voice: str) -> str:
        if voice.startswith("b"):
            return "en-gb"
        if voice.startswith("a"):
            return "en-us"
        if voice.startswith("j"):
            return "ja"
        if voice.startswith("z"):
            return "cmn"
        if voice.startswith("e"):
            return "es"
        if voice.startswith("f"):
            return "fr-fr"
        if voice.startswith("h"):
            return "hi"
        return "en-us"

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> Path:
        voice = voice or "af_heart"
        if voice not in KOKORO_VOICES:
            raise ValueError(f"Unknown Kokoro voice: {voice}")
        if not text.strip():
            raise ValueError("Kokoro cannot synthesize empty text.")

        try:
            import soundfile as sf
        except ImportError as exc:
            raise RuntimeError("The soundfile runtime is required for Kokoro output.") from exc

        runtime = self._load_runtime()
        samples, sample_rate = runtime.create(
            text.strip(),
            voice=voice,
            speed=1.0,
            lang=self._language_for_voice(voice),
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), samples, sample_rate)
        return output_path
