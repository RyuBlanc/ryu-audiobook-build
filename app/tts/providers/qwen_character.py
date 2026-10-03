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
    best_custom_kind,
    model_installed,
    runtime_environment,
    runtime_python,
    runtime_ready,
    worker_script,
)


class QwenCharacterProvider(TTSProvider):
    """Offline Qwen3-TTS character voices with no API key or cloud service."""

    provider_id = "qwen-character"
    recommended_chunk_chars = 360
    recommended_chunk_sentences = 2
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
    ):
        self.voice_id = voice_id
        self.language = language or "English"
        self.instruct = instruct or ""
        self.backend = backend
        self.model_kind = self._resolve_kind(model_kind)
        self.reference_audio = reference_audio
        self.reference_text = reference_text
        self._worker: subprocess.Popen | None = None
        self._stdout_queue: queue.Queue[str | None] | None = None
        self._stdout_thread: threading.Thread | None = None
        self._worker_log = None

    @staticmethod
    def _resolve_kind(requested: str) -> str:
        requested = (requested or "auto").lower()
        if requested in {"custom-0.6b", "custom-1.7b"}:
            return requested
        return best_custom_kind()

    def voices(self) -> list[str]:
        return [self.voice_id]

    def _start_worker(self) -> None:
        if self._worker is not None and self._worker.poll() is None:
            return
        if not runtime_ready():
            raise RuntimeError(
                "Offline Character Voices are not installed. Open Models and choose "
                "Download Offline Character Voices first."
            )
        if not model_installed(self.model_kind):
            raise RuntimeError(
                f"The selected offline character model ({self.model_kind}) is not installed. "
                "Open Models and download the compatible character voice model."
            )

        log_path = Path.home() / "Ryu's Audiobook" / "Settings" / "qwen_character_worker.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._worker_log = log_path.open("a", encoding="utf-8", errors="replace")
        command = [
            str(runtime_python()),
            str(worker_script()),
            "--server",
            "--kind", self.model_kind,
            "--task", "clone" if self.reference_audio else "custom",
            "--backend", self.backend,
        ]
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
        response = self._read_response(timeout=900.0)
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
        }
        if self.reference_audio:
            request["reference"] = str(self.reference_audio.resolve())
            request["ref_text"] = self.reference_text
        self._worker.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        self._worker.stdin.flush()
        response = self._read_response(timeout=300.0)
        if not response.get("ok"):
            raise RuntimeError(
                "Offline character generation failed. "
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
