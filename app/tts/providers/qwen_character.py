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
    best_long_form_clone_kind,
    best_custom_kind,
    best_voice_design_kind,
    model_installed,
    runtime_environment,
    runtime_python,
    runtime_ready,
    verify_runtime,
    worker_script,
)
from ..expression import classify_expression


class QwenCharacterProvider(TTSProvider):
    """Offline Qwen3-TTS character voices with no API key or cloud service."""

    provider_id = "qwen-character"
    # Qwen can safely handle substantially larger sentence-aware units. The
    # previous 360-char/2-sentence setting created thousands of tiny generation
    # jobs on long novels and made GPU utilization/ETA unnecessarily poor.
    recommended_chunk_chars = 800
    recommended_chunk_sentences = 4
    # Conservative startup estimate used only until real chunk timings are available.
    estimated_chars_per_minute = 180.0
    handles_narration_controls = False
    stop_on_failure = True

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
        qwen_profile_id: str = "",
    ):
        self.voice_id = voice_id
        self.language = language or "English"
        self.instruct = instruct or ""
        self.backend = backend
        self.qwen_mode = (qwen_mode or "custom").casefold()
        self.qwen_seed = qwen_seed
        self.qwen_anchor_path = qwen_anchor_path
        self.qwen_anchor_text = qwen_anchor_text or ""
        self.qwen_profile_id = qwen_profile_id or ""
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

    @property
    def recommended_batch_size(self) -> int:
        """Generate one Qwen segment at a time for responsive checkpoints."""
        return 1


    def _request_timeout(self, text_chars: int) -> float:
        # One 2.4k-character Qwen chunk can legitimately take many minutes on
        # laptop GPUs. Keep a generous watchdog so slow inference is not
        # mistaken for a dead worker.
        return max(1800.0, min(7200.0, 900.0 + float(text_chars) * 0.8))

    def voices(self) -> list[str]:
        return [self.voice_id]

    def generation_signature(self) -> str:
        reference = ""
        if self.reference_audio and Path(self.reference_audio).exists():
            try:
                stat = Path(self.reference_audio).stat()
                reference = f"{Path(self.reference_audio).resolve()}:{stat.st_size}:{stat.st_mtime_ns}"
            except OSError:
                reference = str(self.reference_audio)
        return "|".join(
            [
                self.provider_id,
                self.voice_id,
                self.language,
                self.qwen_mode,
                self.model_kind,
                (
                    best_long_form_clone_kind()
                    if self.qwen_mode in {"design", "design-preview"}
                    else ""
                ),
                self.instruct,
                str(self.qwen_seed),
                str(self.qwen_anchor_path or ""),
                self.qwen_anchor_text,
                self.qwen_profile_id,
                reference,
            ]
        )


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
            try:
                verify_runtime()
            except Exception as exc:
                raise RuntimeError(f"Qwen3-TTS runtime is not healthy: {exc}") from exc
            raise RuntimeError(
                "Offline Character Voices are not installed. Open Models and choose "
                "Install / Repair Qwen Voice Studio first."
            )
        if not model_installed(self.model_kind):
            phase = {"design": "VoiceDesign", "design-preview": "VoiceDesign", "clone": "Voice Clone (Base)"}.get(
                self.qwen_mode, "CustomVoice"
            )
            raise RuntimeError(
                f"The selected Qwen {phase} model ({self.model_kind}) is not installed. "
                "Open Models and install the corresponding Qwen3-TTS phase."
            )
        clone_kind = None
        if self.qwen_mode in {"design", "design-preview"}:
            clone_kind = best_long_form_clone_kind()
            if not model_installed(clone_kind):
                raise RuntimeError(
                    f"VoiceDesign stable identity needs the local Qwen Base model ({clone_kind}). "
                    "Open Models and install the matching Qwen Base phase."
                )
        log_path = Path.home() / "Ryu's Audiobook" / "Settings" / "qwen_character_worker.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._worker_log = log_path.open("a", encoding="utf-8", errors="replace")
        command = [
            str(runtime_python()),
            str(worker_script()),
            "--server",
            "--kind", self.model_kind,
            "--task", self.qwen_mode,
            "--backend", self.backend,
            "--models-root", str(RUNTIME_ROOT),
            "--clone-kind", clone_kind or best_clone_kind(),
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
        response = self._read_response(timeout=900.0, heartbeat="Loading Qwen model / character identity")
        if response.get("ready"):
            self._status(
                f"Qwen engine ready • {response.get('kind', self.model_kind)} • "
                f"{response.get('device', 'unknown device')}"
            )
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

    def _read_response(self, timeout: float, heartbeat: str = "") -> dict:
        q = self._stdout_queue
        if q is None:
            raise RuntimeError("Offline character worker output is unavailable.")
        deadline = time.monotonic() + timeout
        started = time.monotonic()
        last_heartbeat = started
        while time.monotonic() < deadline:
            try:
                line = q.get(timeout=min(1.0, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                now = time.monotonic()
                if heartbeat and now - last_heartbeat >= 2.0:
                    elapsed = int(now - started)
                    self._status(
                        f"{heartbeat} • elapsed {elapsed // 60}:{elapsed % 60:02d} • Qwen is still processing…"
                    )
                    last_heartbeat = now
                continue
            if line is None:
                exit_code = self._worker.poll() if self._worker is not None else None
                detail = ""
                try:
                    if self._worker_log is not None:
                        self._worker_log.flush()
                        log_path = Path(self._worker_log.name)
                        if log_path.exists():
                            detail = log_path.read_text(
                                encoding="utf-8", errors="replace"
                            )[-2400:].strip()
                except OSError:
                    pass
                suffix = f" Exit code: {exit_code}."
                if detail:
                    suffix += f" Worker log: {detail}"
                raise RuntimeError(
                    "Offline character worker exited before returning a response."
                    + suffix
                )
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
            "profile_id": self.qwen_profile_id,
            "longform": self.qwen_mode != "design-preview",
            "expression_style": classify_expression(text),
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
        # A Qwen request owns the single long-lived worker. If a synthesis
        # request times out or fails, do not queue another request behind a
        # possibly still-running model call.
        self._worker.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        self._worker.stdin.flush()
        try:
            response = self._read_response(
            timeout=self._request_timeout(len(text)),
            heartbeat="Generating preview…" if "preview" in self.qwen_mode else "Generating narration…",
        )
        except Exception:
            self.close()
            raise
        if response:
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

    def synthesize_batch(
        self,
        items: list[tuple[str, Path]],
    ) -> list[Path]:
        """Generate several same-voice chunks in one Qwen request.

        The worker reuses the locked VoiceDesign/Base prompt for every item.
        """
        if not items:
            return []
        self._start_worker()
        if not self._worker or not self._worker.stdin:
            raise RuntimeError("Offline character worker is unavailable.")

        texts = [str(text).strip() for text, _output in items]
        outputs = [str(Path(output).resolve()) for _text, output in items]
        if any(not text for text in texts):
            raise ValueError("Qwen batch contains empty narration text.")

        request = {
            "texts": texts,
            "outputs": outputs,
            "styles": [classify_expression(text) for text in texts],
            "speaker": self.voice_id,
            "language": self.language,
            "instruct": self.instruct,
            "seed": self.qwen_seed,
            "anchor_path": str(self.qwen_anchor_path.resolve()) if self.qwen_anchor_path else "",
            "anchor_text": self.qwen_anchor_text,
            "profile_id": self.qwen_profile_id,
            "styles": [classify_expression(text) for text in texts],
            "longform": True,
        }
        self._status(
            f"Generating {len(items)} Qwen narration segments together…"
        )
        self._worker.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        self._worker.stdin.flush()
        try:
            response = self._read_response(
                timeout=self._request_timeout(sum(len(text) for text in texts)),
                heartbeat=f"Generating {len(items)} Qwen segments…",
            )
        except Exception:
            self.close()
            raise

        if not response.get("ok"):
            # Batch memory pressure should not kill the whole audiobook. The
            # caller can retry these same items one at a time.
            if response.get("batch_oom"):
                raise RuntimeError("Qwen batch exceeded available GPU memory.")
            raise RuntimeError(
                "Qwen3-TTS batch generation failed. "
                + str(response.get("error") or "Unknown Qwen error.")
            )

        produced = response.get("outputs") or []
        if len(produced) != len(outputs):
            raise RuntimeError(
                f"Qwen returned {len(produced)} audio files for {len(outputs)} requested segments."
            )
        for output in outputs:
            path = Path(output)
            if not path.exists() or path.stat().st_size < 1024:
                raise RuntimeError(f"Qwen generated an invalid or empty audio file: {path.name}")
        return [Path(output) for output in outputs]

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
