from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile

from ..base import TTSProvider
from ..chatterbox_runtime import runtime_ready, runtime_python, runtime_environment, worker_script


class ChatterboxProvider(TTSProvider):
    """Local Chatterbox adapter with reference-audio voice cloning."""

    provider_id = "chatterbox"

    def __init__(
        self,
        model_path: Path | None = None,
        reference_audio: Path | None = None,
        backend: str = "automatic",
        language: str | None = None,
        multilingual: bool = False,
        exaggeration: float = 0.5,
        cfg_weight: float = 0.35,
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
        self._worker: subprocess.Popen | None = None

    def voices(self) -> list[str]:
        return [self.reference_audio.stem] if self.reference_audio and self.reference_audio.exists() else []

    def _load(self):
        if self._model is not None:
            return
        os.environ.setdefault("TRANSFORMERS_ATTN_IMPLEMENTATION", "eager")
        try:
            from chatterbox.tts import ChatterboxTTS
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        except ImportError as exc:
            raise RuntimeError(
                "Chatterbox is not installed. Open Models → Install / Repair Custom Voice Engine first."
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

    def _start_external_worker(self, variant: str | None = None) -> None:
        if self._worker is not None and self._worker.poll() is None:
            return
        python = runtime_python()
        if not python or not runtime_ready():
            raise RuntimeError(
                "Custom voice engine is not installed. Open Models → Install / Repair Custom Voice Engine "
                "and complete the one-time runtime installation."
            )

        requested_variant = (variant or "auto").lower()

        def spawn(selected_variant: str):
            command = [
                str(python), str(worker_script()),
                "--server",
                "--backend", self.backend,
                "--language", self.language or "en",
                "--variant", selected_variant,
            ]
            if self.multilingual:
                command.append("--multilingual")
            self._worker = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=runtime_environment(),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if sys.platform == "win32" else 0,
            )

        def read_ready() -> tuple[dict, str]:
            try:
                ready_line = self._worker.stdout.readline() if self._worker and self._worker.stdout else ""
                if not ready_line:
                    raise RuntimeError("The custom voice worker stopped before becoming ready.")
                ready = json.loads(ready_line)
                if not ready.get("ready"):
                    raise RuntimeError("The custom voice worker did not report ready.")
                return ready, ""
            except Exception as exc:
                detail = ""
                try:
                    if self._worker and self._worker.stderr:
                        detail = self._worker.stderr.read().strip()[-3000:]
                except Exception:
                    pass
                return {}, detail or str(exc)

        spawn(requested_variant)
        ready, detail = read_ready()
        if ready:
            return

        self.close()
        paging_error = (
            "1455" in detail
            or "paging file is too small" in detail.lower()
            or "os error 1455" in detail.lower()
            or "winerror 1455" in detail.lower()
        )
        if paging_error and not self.multilingual and requested_variant != "nano":
            # The base model can exceed the Windows commit limit on small
            # RAM/pagefile systems. Relaunch from a clean process with the
            # official Chatterbox Nano voice-cloning model.
            spawn("nano")
            ready, nano_detail = read_ready()
            if ready:
                return
            self.close()
            detail = nano_detail or detail
            raise RuntimeError(
                "The custom voice worker could not start even in low-memory mode. "
                + detail
            )

        raise RuntimeError(f"The custom voice worker could not start. {detail}")

    def _synthesize_external(self, text: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.reference_audio:
            raise RuntimeError("A reference voice sample is required for Chatterbox voice cloning.")
        reference = self.reference_audio.resolve()
        if not reference.is_file():
            raise RuntimeError(f"Reference voice file is missing: {reference}")

        self._start_external_worker()
        if not self._worker or not self._worker.stdin or not self._worker.stdout:
            raise RuntimeError("The custom voice worker is unavailable.")
        request = {
            "text": text,
            "output": str(output_path.resolve()),
            "reference": str(reference),
            "backend": self.backend,
            "language": self.language or "en",
            "multilingual": self.multilingual,
            "exaggeration": self.exaggeration,
            "cfg_weight": self.cfg_weight,
        }
        try:
            self._worker.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            self._worker.stdin.flush()
            line = self._worker.stdout.readline()
            if not line:
                raise RuntimeError("The custom voice worker stopped during generation.")
            response = json.loads(line)
            if not response.get("ok"):
                raise RuntimeError(
                    "Custom voice generation failed. " +
                    str(response.get("error") or "The Chatterbox runtime returned an unknown error.")
                )
        except (BrokenPipeError, OSError, json.JSONDecodeError) as exc:
            self.close()
            raise RuntimeError(f"Custom voice worker communication failed: {exc}") from exc

        if not output_path.exists() or output_path.stat().st_size < 1024:
            raise RuntimeError("Custom voice engine did not produce a valid WAV output.")
        return output_path

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> Path:
        if not self.reference_audio or not self.reference_audio.exists():
            raise RuntimeError("A reference voice sample is required for Chatterbox voice cloning.")

        if getattr(sys, "frozen", False) or runtime_ready():
            return self._synthesize_external(text, output_path)

        self._load()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        reference = str(self.reference_audio.resolve())
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

    def close(self) -> None:
        if self._worker is not None:
            try:
                if self._worker.stdin:
                    self._worker.stdin.close()
            except OSError:
                pass
            try:
                self._worker.terminate()
                self._worker.wait(timeout=5)
            except Exception:
                try:
                    self._worker.kill()
                except Exception:
                    pass
            self._worker = None
