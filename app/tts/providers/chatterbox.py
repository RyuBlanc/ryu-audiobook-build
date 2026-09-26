from pathlib import Path
import os
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
        self._conditioned_reference: str | None = None
        self._conditioned_exaggeration: float | None = None

    def voices(self) -> list[str]:
        return [self.reference_audio.stem] if self.reference_audio and self.reference_audio.exists() else []

    def _load(self):
        if self._model is not None:
            return

        # Chatterbox currently has transformer attention paths that may require
        # eager attention when reference conditioning is used.
        os.environ.setdefault("TRANSFORMERS_ATTN_IMPLEMENTATION", "eager")
        try:
            from chatterbox.tts import ChatterboxTTS
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        except ImportError as exc:
            raise RuntimeError(
                "Chatterbox is not installed. Install the optional Chatterbox runtime first."
            ) from exc

        if self.backend == "cuda":
            device = "cuda"
        elif self.backend == "cpu":
            device = "cpu"
        else:
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
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

        reference = str(self.reference_audio.resolve())
        if not self.reference_audio.is_file():
            raise RuntimeError(f"Reference voice file is missing: {self.reference_audio}")

        # Chatterbox officially accepts the reference directly through
        # audio_prompt_path. This is more robust across Chatterbox releases
        # than relying on an internal cached-conditionals API.
        kwargs = {
            "audio_prompt_path": reference,
            "exaggeration": self.exaggeration,
            "cfg_weight": self.cfg_weight,
        }
        if self.multilingual:
            kwargs["language_id"] = self.language or "en"

        wav = self._model.generate(text, **kwargs)

        try:
            import torchaudio as ta
            ta.save(str(output_path), wav, self._model.sr)
        except Exception as ta_exc:
            try:
                import soundfile as sf
                data = wav.detach().cpu().squeeze().numpy() if hasattr(wav, "detach") else wav
                sf.write(str(output_path), data, self._model.sr)
            except Exception as sf_exc:
                raise RuntimeError(
                    "Chatterbox generated audio, but it could not be saved as WAV. "
                    f"torchaudio: {ta_exc}; soundfile: {sf_exc}"
                ) from sf_exc

        if not output_path.exists() or output_path.stat().st_size < 1024:
            raise RuntimeError("Chatterbox did not produce a valid WAV output.")
        return output_path
