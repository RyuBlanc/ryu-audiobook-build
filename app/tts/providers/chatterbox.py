from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import queue
import threading
import time

from ..base import TTSProvider
from ..chatterbox_runtime import runtime_ready, runtime_python, runtime_environment, worker_script


class ChatterboxProvider(TTSProvider):
    """Local Chatterbox adapter with reference-audio voice cloning."""

    provider_id = "chatterbox"
    # Chatterbox Turbo becomes unstable on long utterances in practice.
    # Keep voice-cloning requests short enough for clean narration.
    recommended_chunk_chars = 300
    recommended_chunk_sentences = 1

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
        self._worker_log = None
        self._stdout_queue: queue.Queue[str | None] | None = None
        self._stdout_thread: threading.Thread | None = None

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
        log_path = Path.home() / "Ryu's Audiobook" / "Settings" / "chatterbox_worker.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        command = [
            str(python), str(worker_script()),
            "--server",
            "--backend", self.backend,
            "--language", self.language or "en",
            "--variant", requested_variant,
        ]
        if self.multilingual:
            command.append("--multilingual")

        # Never pipe stderr without draining it. Chatterbox writes model
        # loading/progress diagnostics there; an undrained pipe can fill and
        # deadlock the worker, which previously made the app appear frozen.
        self._worker_log = log_path.open("a", encoding="utf-8", errors="replace")
        self._worker = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._worker_log,
            text=True,
            bufsize=1,
            env=runtime_environment(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if sys.platform == "win32" else 0,
        )
        self._stdout_queue = queue.Queue()
        self._stdout_thread = threading.Thread(
            target=self._drain_worker_stdout,
            name="RyuChatterboxStdout",
            daemon=True,
        )
        self._stdout_thread.start()

        ready, detail = self._read_worker_response(timeout=900.0)
        if ready:
            return

        paging_error = (
            "1455" in detail
            or "paging file is too small" in detail.lower()
            or "os error 1455" in detail.lower()
            or "winerror 1455" in detail.lower()
        )
        self.close()

        if paging_error and not self.multilingual and requested_variant != "nano":
            # Relaunch once in explicit low-memory mode. The worker chooses
            # the Nano Chatterbox model without loading the larger base model.
            self._start_external_worker("nano")
            return

        raise RuntimeError(
            "The custom voice worker could not become ready. "
            + (detail or "Check Settings\\chatterbox_worker.log for details.")
        )

    def _drain_worker_stdout(self) -> None:
        stdout = self._worker.stdout if self._worker is not None else None
        q = self._stdout_queue
        if stdout is None or q is None:
            return
        try:
            for line in iter(stdout.readline, ""):
                q.put(line.rstrip("\r\n"))
        finally:
            q.put(None)

    def _read_worker_response(self, timeout: float) -> tuple[dict, str]:
        q = self._stdout_queue
        worker = self._worker
        if q is None:
            return {}, "Custom voice worker output channel was not initialized."
        try:
            line = q.get(timeout=timeout)
        except queue.Empty:
            return {}, "Timed out waiting for the custom voice worker."
        if line is None:
            detail = ""
            if worker is not None:
                code = worker.poll()
                detail = f"Worker exited with code {code}."
            log_path = Path.home() / "Ryu's Audiobook" / "Settings" / "chatterbox_worker.log"
            try:
                if log_path.exists():
                    tail = log_path.read_text(encoding="utf-8", errors="replace")[-6000:].strip()
                    if tail:
                        detail += f"\n\nCustom voice engine log:\n{tail}"
            except OSError:
                pass
            return {}, detail
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                if value.get("ready") or value.get("ok"):
                    return value, ""
                return {}, str(value.get("error") or "The custom voice worker returned an error.")
            return {}, "The custom voice worker returned an invalid response."
        except json.JSONDecodeError:
            # Libraries sometimes emit harmless startup diagnostics on stdout.
            # Ignore those lines while waiting for the worker's JSON handshake.
            # If the process dies, the EOF branch above reports the real log.
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    line = q.get(timeout=min(1.0, max(0.01, deadline - time.monotonic())))
                except queue.Empty:
                    return {}, "Timed out waiting for the custom voice worker."
                if line is None:
                    detail = "Worker exited before sending its ready response."
                    log_path = Path.home() / "Ryu's Audiobook" / "Settings" / "chatterbox_worker.log"
                    try:
                        if log_path.exists():
                            tail = log_path.read_text(encoding="utf-8", errors="replace")[-6000:].strip()
                            if tail:
                                detail += f"\n\nCustom voice engine log:\n{tail}"
                    except OSError:
                        pass
                    return {}, detail
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    if value.get("ready") or value.get("ok"):
                        return value, ""
                    return {}, str(value.get("error") or "The custom voice worker returned an error.")
            return {}, "Timed out waiting for a usable response from the custom voice worker."

    def _synthesize_external(self, text: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.reference_audio:
            raise RuntimeError("A reference voice sample is required for Chatterbox voice cloning.")
        reference = self.reference_audio.resolve()
        if not reference.is_file():
            raise RuntimeError(f"Reference voice file is missing: {reference}")

        self._start_external_worker()
        if not self._worker or not self._worker.stdin:
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
            response, detail = self._read_worker_response(timeout=300.0)
            if not response.get("ok"):
                raise RuntimeError(
                    "Custom voice generation failed. "
                    + (detail or "The Chatterbox worker returned no usable audio.")
                )
        except (BrokenPipeError, OSError) as exc:
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
        worker = self._worker
        self._worker = None
        self._stdout_queue = None
        self._stdout_thread = None
        if worker is not None:
            try:
                if worker.stdin:
                    worker.stdin.close()
            except OSError:
                pass
            try:
                if worker.poll() is None:
                    worker.terminate()
                    worker.wait(timeout=5)
            except Exception:
                try:
                    worker.kill()
                except Exception:
                    pass
            try:
                if worker.stdout:
                    worker.stdout.close()
            except OSError:
                pass
        if self._worker_log is not None:
            try:
                self._worker_log.flush()
                self._worker_log.close()
            except OSError:
                pass
            self._worker_log = None
