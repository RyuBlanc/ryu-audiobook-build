from __future__ import annotations

import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

from ..base import TTSProvider
from ..qwen_character_runtime import (
    RUNTIME_ROOT,
    best_clone_kind,
    best_custom_kind,
    best_voice_design_kind,
    model_installed,
    runtime_environment,
    runtime_python,
    runtime_ready,
    worker_script,
)


class QwenCharacterProvider(TTSProvider):
    """Offline Qwen3-TTS character voices with no API key or cloud service."""

    provider_id = "qwen-character"
    # Qwen can safely handle substantially larger sentence-aware units. The
    # previous 360-char/2-sentence setting created thousands of tiny generation
    # jobs on long novels and made GPU utilization/ETA unnecessarily poor.
    recommended_chunk_chars = 1800
    recommended_chunk_sentences = 8
    handles_narration_controls = False

    def __init__(
        self,
        voice_id: str,
        language: str = "English",
        instruct: str = "",
        backend: str = "automatic",
        model_kind: str = "auto",
        reference_audio: Path | None = None,
        reference_text: str = "",
        qwen_mode: str = "custom",
        qwen_seed: int | None = None,
        qwen_anchor_path: Path | None = None,
        qwen_anchor_text: str = "",
    ):
        self.voice_id = voice_id
        self.language = language or "English"
        self.instruct = instruct or ""
        self.backend = backend
        self.qwen_mode = (qwen_mode or "custom").casefold()
        self.qwen_seed = qwen_seed
        self.qwen_anchor_path = qwen_anchor_path
        self.qwen_anchor_text = qwen_anchor_text or ""
        self.status_callback = None
        self.model_kind = self._resolve_kind(model_kind)
        self.reference_audio = reference_audio
        self.reference_text = reference_text
        self._worker: subprocess.Popen | None = None
        self._stdout_queue: queue.Queue[str | None] | None = None
        self._stdout_thread: threading.Thread | None = None
        self._worker_log = None

    def _resolve_kind(self, requested: str) -> str:
        requested = (requested or "auto").lower()
        if self.qwen_mode == "design":
            return requested if requested == "design-1.7b" else best_voice_design_kind()
        if self.qwen_mode == "clone":
            if requested in {"base-0.6b", "base-1.7b"}:
                return requested
            return best_clone_kind()
        if self.qwen_mode in {"design", "design-preview"}:
            return requested if requested == "design-1.7b" else best_voice_design_kind()
        if requested in {"custom-0.6b", "custom-1.7b"}:
            return requested
        return best_custom_kind()

    def voices(self) -> list[str]:
        return [self.voice_id]

    def set_status_callback(self, callback) -> None:
        self.status_callback = callback

    def _status(self, message: str) -> None:
        callback = self.status_callback
        if callable(callback):
            try:
                callback(str(message))
            except Exception:
                pass

    def _start_worker(self) -> None:
        if self._worker is not None and self._worker.poll() is None:
            return
        if not runtime_ready():
            raise RuntimeError(
                "Offline Character Voices are not installed. Open Models and choose "
                "Download Offline Character Voices first."
            )
        if not model_installed(self.model_kind):
            phase = {"design": "VoiceDesign", "clone": "Voice Clone (Base)"}.get(
                self.qwen_mode, "CustomVoice"
            )
            raise RuntimeError(
                f"The selected Qwen {phase} model ({self.model_kind}) is not installed. "
                "Open Models and install the corresponding Qwen3-TTS phase."
            )
        if self.qwen_mode == "design":
            clone_kind = best_clone_kind()
            if not model_installed(clone_kind):
                raise RuntimeError(
                    f"Qwen VoiceDesign also needs the {clone_kind} Base model to lock the "
                    "designed voice identity for consistent long-form narration. "
                    "Open Models → Full Qwen Voice Studio."
                )

        log_path = Path.home() / "Ryu's Audiobook" / "Settings" / "qwen_character_worker.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._worker_log = log_path.open("a", encoding="utf-8", errors="replace")
        clone_kind = best_clone_kind()
        command = [
            str(runtime_python()),
            str(worker_script()),
            "--server",
            "--kind", self.model_kind,
            "--task", self.qwen_mode,
            "--backend", self.backend,
            "--models-root", str(RUNTIME_ROOT),
            "--clone-kind", clone_kind,
        ]
        if self.qwen_anchor_path:
            command.extend(["--anchor-path", str(self.qwen_anchor_path.resolve())])
        if self.qwen_anchor_text:
            command.extend(["--anchor-text", self.qwen_anchor_text])
        self._worker = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._worker_log,
            text=True,
            encoding="utf-8",
            errors="strict",
            bufsize=1,
            env=runtime_environment(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if sys.platform == "win32" else 0,
        )
        self._stdout_queue = queue.Queue()
        self._stdout_thread = threading.Thread(
            target=self._drain_stdout,
            name="RyuQwenCharacterStdout",
            daemon=True,
        )
        self._stdout_thread.start()
        self._status(
            "Loading Qwen3-TTS "
            + ("VoiceDesign preview" if self.qwen_mode == "design-preview" else "voice engine")
            + f" • {self.model_kind}"
        )
        response = self._read_response(timeout=600.0)
        if response.get("ready"):
            return
        detail = response.get("error") or "The offline character worker did not become ready."
        self.close()
        raise RuntimeError(str(detail))

    def _drain_stdout(self) -> None:
        if self._worker is None or self._worker.stdout is None or self._stdout_queue is None:
            return
        try:
            for line in iter(self._worker.stdout.readline, ""):
                self._stdout_queue.put(line.rstrip("\r\n"))
        finally:
            self._stdout_queue.put(None)

    def _read_response(self, timeout: float) -> dict:
        q = self._stdout_queue
        if q is None:
            raise RuntimeError("Offline character worker output is unavailable.")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = q.get(timeout=min(1.0, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if line is None:
                raise RuntimeError("Offline character worker exited before returning a response.")
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                progress = value.get("progress")
                if progress:
                    self._status(str(progress))
                    continue
                return value
        raise RuntimeError("Timed out waiting for the offline character worker.")

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> Path:
        self._start_worker()
        if not self._worker or not self._worker.stdin:
            raise RuntimeError("Offline character worker is unavailable.")
        request = {
            "text": text,
            "output": str(output_path.resolve()),
            "speaker": self.voice_id,
            "language": self.language,
            "instruct": self.instruct,
            "seed": self.qwen_seed,
            "allow_instruct": self.model_kind == "custom-1.7b",
            "anchor_path": str(self.qwen_anchor_path.resolve()) if self.qwen_anchor_path else "",
            "anchor_text": self.qwen_anchor_text,
            "longform": self.qwen_mode != "design-preview",
        }
        if self.qwen_mode == "clone":
            if not self.reference_audio:
                raise RuntimeError("Qwen Base voice cloning requires a reference audio recording.")
            request["reference"] = str(self.reference_audio.resolve())
            request["ref_text"] = self.reference_text
            request["x_vector_only_mode"] = not bool(self.reference_text.strip())
        self._status(
            "Generating preview…" if "preview" in self.qwen_mode else "Generating narration…"
        )
        self._worker.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        self._worker.stdin.flush()
        if response := self._read_response(timeout=300.0):
            if response.get("device"):
                self._status(
                    f"Qwen ready • {response.get('kind', self.model_kind)} • {response.get('device')}"
                )
        else:
            response = {}
        if not response.get("ok"):
            raise RuntimeError(
                "Qwen3-TTS generation failed. "
                + str(response.get("error") or "Unknown Qwen error.")
            )
        if not output_path.exists() or output_path.stat().st_size < 1024:
            raise RuntimeError("Qwen generated an invalid or empty audio file.")
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
