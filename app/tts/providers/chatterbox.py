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
        # Chatterbox re-encodes the reference speaker when audio_prompt_path is
        # passed to every generate() call. Cache those conditionals once per
        # profile/reference so long books do not repeatedly pay the same cost.
        if (
            self._conditioned_reference != reference
            or self._conditioned_exaggeration != self.exaggeration
            or getattr(self._model, "conds", None) is None
        ):
            if not hasattr(self._model, "prepare_conditionals"):
                raise RuntimeError("This Chatterbox runtime does not expose reference-voice conditioning.")
            self._model.prepare_conditionals(
                reference,
                exaggeration=self.exaggeration,
            )
            self._conditioned_reference = reference
            self._conditioned_exaggeration = self.exaggeration

        if self.multilingual:
            wav = self._model.generate(
                text,
                language_id=self.language,
                audio_prompt_path=None,
                exaggeration=self.exaggeration,
                cfg_weight=self.cfg_weight,
            )
        else:
            wav = self._model.generate(
                text,
                audio_prompt_path=None,
                exaggeration=self.exaggeration,
                cfg_weight=self.cfg_weight,
            )

        try:
            import torchaudio as ta
            ta.save(str(output_path), wav, self._model.sr)
        except ImportError as exc:
            raise RuntimeError("torchaudio is required by the Chatterbox provider.") from exc

        return output_path
