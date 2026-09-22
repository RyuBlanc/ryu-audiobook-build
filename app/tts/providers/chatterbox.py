from pathlib import Path
import wave

from ..base import TTSProvider


class ChatterboxProvider(TTSProvider):
    """Local Chatterbox adapter with reference-audio voice cloning.

    Chatterbox supports conditioning generation on a reference audio file.
    The reference must be a voice the user is authorized to use.
    """

    provider_id = "chatterbox"

    def __init__(
        self,
        model_path: Path | None = None,
        reference_audio: Path | None = None,
        backend: str = "automatic",
        language: str | None = None,
        multilingual: bool = False,
        exaggeration: float = 0.5,
        cfg_weight: float = 0.5,
    ):
        self.model_path = model_path
        self.reference_audio = reference_audio
        self.backend = backend
        self.language = language or "en"
        self.multilingual = multilingual
        self.exaggeration = exaggeration
        self.cfg_weight = cfg_weight
        self._model = None
        self._device = None

    def voices(self) -> list[str]:
        return [self.reference_audio.stem] if self.reference_audio and self.reference_audio.exists() else []

    def _load(self):
        if self._model is not None:
            return

        try:
            from chatterbox.tts import ChatterboxTTS
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        except ImportError as exc:
            raise RuntimeError(
                "Chatterbox is not installed. Install the optional Chatterbox runtime first."
            ) from exc

        device = "cuda" if self.backend == "cuda" else "cpu"
        if self.multilingual:
            self._model = ChatterboxMultilingualTTS.from_pretrained(device=device)
        else:
            self._model = ChatterboxTTS.from_pretrained(device=device)
        self._device = device

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> Path:
        if not self.reference_audio or not self.reference_audio.exists():
            raise RuntimeError("A reference voice sample is required for Chatterbox voice cloning.")

        self._load()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if self.multilingual:
            wav = self._model.generate(
                text,
                language_id=self.language,
                audio_prompt_path=str(self.reference_audio),
                exaggeration=self.exaggeration,
                cfg_weight=self.cfg_weight,
            )
        else:
            wav = self._model.generate(
                text,
                audio_prompt_path=str(self.reference_audio),
                exaggeration=self.exaggeration,
                cfg_weight=self.cfg_weight,
            )

        try:
            import torchaudio as ta
            ta.save(str(output_path), wav, self._model.sr)
        except ImportError as exc:
            raise RuntimeError("torchaudio is required by the Chatterbox provider.") from exc

        return output_path
