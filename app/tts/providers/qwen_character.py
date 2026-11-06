from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
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
    _detected_vram_gb,
    ensure_best_runtime_for_gpu,
    register_qwen_worker,
    unregister_qwen_worker,
)
from ..expression import DEFAULT_VOICE_DESIGN_ANCHOR_TEXT, classify_expression
from app.core.paths import settings_root


class QwenCharacterProvider(TTSProvider):
    """Offline Qwen3-TTS character voices with no API key or cloud service."""

    provider_id = "qwen-character"
    # Long-form audiobook narration uses the original high-throughput bounds.
    # Larger sentence-aware units reduce per-request overhead while retaining
    # expression-based boundaries. Short previews intentionally stay smaller.
    recommended_chunk_chars = 2400
    recommended_chunk_sentences = 10
    # Preserve efficient long units in calm narration, but cut at real shifts
    # between neutral, thoughtful, warm and concerned styles so each unit can
    # use the matching stable-identity expression reference.
    split_on_expression_change = True
    # Preview requests use the same bounded sentence-aware units as production
    # narration. This reduces per-request model overhead without changing the
    # selected model, prompt, sampling, pronunciation or voice identity.
    recommended_preview_chunk_chars = 800
    recommended_preview_chunk_sentences = 4
    split_preview_on_expression_change = True
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
        long_form_model_kind: str | None = None,
        low_memory: bool = False,
    ):
        self.voice_id = voice_id
        self.language = language or "English"
        self.instruct = instruct or ""
        self.backend = backend
        self.low_memory = bool(low_memory)
        self.last_execution_context: dict = {}
        self.qwen_mode = (qwen_mode or "custom").casefold()
        self.qwen_seed = qwen_seed
        self.qwen_anchor_path = qwen_anchor_path
        self.qwen_anchor_text = (
            qwen_anchor_text
            or (DEFAULT_VOICE_DESIGN_ANCHOR_TEXT if self.qwen_mode == "design" else "")
        )
        self.qwen_profile_id = qwen_profile_id or ""
        self.long_form_model_kind = (
            long_form_model_kind
            if long_form_model_kind in {"base-0.6b", "base-1.7b"}
            else None
        )
        self.status_callback = None
        requested_kind = (model_kind or "auto").lower()
        self._auto_select_model = (
            requested_kind == "auto" and self.qwen_mode in {"custom", "clone"}
        )
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
            return best_clone_kind(vram_gb=0.0)
        if self.qwen_mode in {"design", "design-preview"}:
            return requested if requested == "design-1.7b" else best_voice_design_kind()
        if requested in {"custom-0.6b", "custom-1.7b"}:
            return requested
        return best_custom_kind(vram_gb=0.0)

    def _ensure_model_kind(self) -> None:
        """Resolve automatic model/GPU choices outside the Qt main thread."""
        if not self._auto_select_model:
            return
        if self.qwen_mode in {"design", "design-preview"}:
            self.model_kind = best_voice_design_kind()
        elif self.qwen_mode == "clone":
            self.model_kind = best_clone_kind()
        else:
            self.model_kind = best_custom_kind()
        self._auto_select_model = False

    @property
    def recommended_batch_size(self) -> int:
        """Use conservative two-chunk batches only with ample GPU memory.

        The production worker already supports same-voice Qwen VoiceDesign
        batches. CPU, low-memory devices and providers that cannot batch keep
        the serial path; the generator falls back to serial on an explicit
        accelerator OOM, preserving checkpoint and recovery behavior.
        """
        if self.qwen_mode != "design":
            return 1
        try:
            return 2 if _detected_vram_gb() >= 12.0 else 1
        except Exception:
            return 1

    @property
    def recommended_preview_batch_size(self) -> int:
        """Batch short VoiceDesign previews only on GPUs with comfortable VRAM."""
        if self.qwen_mode != "design-preview":
            return 1
        try:
            # VoiceDesign is a 1.7B model. Prefer serial inference on 4 GB
            # GPUs / CPU; two sentences can share a call on 8 GB-class GPUs.
            # The preview caller falls back if the device reports CUDA OOM.
            return 2 if _detected_vram_gb() >= 7.0 else 1
        except Exception:
            return 1

    def _request_timeout(self, text_chars: int) -> float:
        # One 2.4k-character Qwen chunk can legitimately take many minutes on
        # laptop GPUs. Keep a generous watchdog so slow inference is not
        # mistaken for a dead worker.
        return max(1800.0, min(7200.0, 900.0 + float(text_chars) * 0.8))

    def voices(self) -> list[str]:
        return [self.voice_id]

    def generation_signature(self) -> str:
        self._ensure_model_kind()
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
                str(self.backend or "automatic"),
                str(self.low_memory),
                (
                    self.long_form_model_kind or best_long_form_clone_kind()
                    if self.qwen_mode == "design"
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

    @property
    def execution_backend(self) -> str:
        return str(self.last_execution_context.get("backend") or "unverified")

    @property
    def execution_backend_verified(self) -> bool:
        return self.last_execution_context.get("verified_inference") is True

    @property
    def execution_providers(self) -> tuple[str, ...]:
        return tuple(self.last_execution_context.get("execution_providers") or ())

    def _record_execution_context(self, response: dict) -> None:
        if not isinstance(response, dict) or response.get("ok") is not True:
            return
        device = str(response.get("device") or "").strip()
        kind = str(response.get("kind") or self.model_kind).strip()
        if not device or device.casefold() in {"pending", "unknown"}:
            return
        reported_backend = str(response.get("backend") or "").strip().casefold()
        backend = (
            reported_backend if reported_backend in {"cuda", "rocm", "xpu", "cpu"}
            else "cuda" if device.casefold().startswith("cuda")
            else "xpu" if device.casefold().startswith("xpu")
            else "cpu" if device.casefold() == "cpu"
            else "other"
        )
        record = {
            "device": device,
            "backend": backend,
            "model_kind": kind,
            "task": str(response.get("task") or self.qwen_mode),
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "source": "qwen-worker-response",
            "verified_inference": True,
        }
        self.last_execution_context = record
        try:
            path = settings_root() / "qwen_last_inference.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".tmp")
            temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(path)
        except Exception as exc:
            self._status(f"Could not persist last Qwen inference telemetry: {exc}")

    def _start_worker(self) -> None:
        if self._worker is not None and self._worker.poll() is None:
            return
        self._ensure_model_kind()
        if str(self.backend or "automatic").casefold() in {"automatic", "auto"} and runtime_ready():
            ensure_best_runtime_for_gpu(self._status)
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
        # A VoiceDesign preview is deliberately a one-pass audition using the
        # same VoiceDesign model and profile prompt. It must not generate the
        # long-form anchor bank or require a separate Qwen Base model merely to
        # audition a profile. Production narration remains on the stable
        # VoiceDesign/Base identity-lock path.
        if self.qwen_mode == "design":
            clone_kind = self.long_form_model_kind or best_long_form_clone_kind()
            if not model_installed(clone_kind):
                raise RuntimeError(
                    f"VoiceDesign stable identity needs the local Qwen Base model ({clone_kind}) selected by the global preference. "
                    "Open Models and install the selected global model size, or change the global preference in Models & Voice Engines."
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
        if self.low_memory:
            command.append("--low-memory")
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
        register_qwen_worker(self._worker.pid)
        stdout_queue = queue.Queue()
        self._stdout_queue = stdout_queue
        worker = self._worker
        self._stdout_thread = threading.Thread(
            target=self._drain_stdout,
            args=(worker, stdout_queue),
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
            self._record_execution_context(response)
            self._status(
                f"Qwen engine ready • {response.get('kind', self.model_kind)} • "
                f"{response.get('device', 'unknown device')}"
            )
            return
        detail = response.get("error") or "The offline character worker did not become ready."
        self.close()
        raise RuntimeError(str(detail))

    def _drain_stdout(self, worker, output_queue: queue.Queue[str | None]) -> None:
        """Drain one worker into its captured queue, even while close() clears shared state."""
        stdout = getattr(worker, "stdout", None)
        if stdout is None:
            output_queue.put(None)
            return
        try:
            for line in iter(stdout.readline, ""):
                output_queue.put(line.rstrip("\r\n"))
        except (OSError, ValueError):
            # close() intentionally closes the pipe to stop the worker. The
            # queue is owned by this thread and remains valid until its sentinel.
            pass
        finally:
            output_queue.put(None)

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
        request_language = self.language
        # Qwen supports automatic language selection. Use it when an English
        # narration chunk visibly contains Japanese/Chinese/Korean text so
        # names and short foreign-language phrases are not forced through the
        # English phoneme path.
        if any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" or "\uac00" <= ch <= "\ud7af" for ch in text):
            request_language = "Auto"
        request = {
            "text": text,
            "output": str(output_path.resolve()),
            "speaker": self.voice_id,
            "language": request_language,
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
            self._record_execution_context(response)
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
        voice: str | None = None,
    ) -> list[Path]:
        """Generate several same-voice chunks in one Qwen request.

        The worker reuses the locked VoiceDesign/Base prompt for every item.
        """
        if not items:
            return []
        if self.qwen_mode not in {"design", "design-preview"}:
            return [self.synthesize(text, output) for text, output in items]
        self._start_worker()
        if not self._worker or not self._worker.stdin:
            raise RuntimeError("Offline character worker is unavailable.")

        texts = [str(text).strip() for text, _output in items]
        outputs = [str(Path(output).resolve()) for _text, output in items]
        if any(not text for text in texts):
            raise ValueError("Qwen batch contains empty narration text.")

        batch_language = self.language
        if any(
            any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" or "\uac00" <= ch <= "\ud7af" for ch in text)
            for text in texts
        ):
            batch_language = "Auto"
        request = {
            "texts": texts,
            "outputs": outputs,
            "styles": [classify_expression(text) for text in texts],
            "speaker": self.voice_id,
            "language": batch_language,
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

        self._record_execution_context(response)
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

    def request_cancel(self) -> None:
        """Terminate an active Qwen subprocess without waiting on the calling thread."""
        worker = self._worker
        if worker is None or worker.poll() is not None:
            return
        try:
            # Popen.terminate() maps to TerminateProcess on Windows. Do not
            # wait here: Stop/Cancel is invoked from the main Qt thread.
            worker.terminate()
        except (OSError, ProcessLookupError):
            pass

    def close(self) -> None:
        worker = self._worker
        self._worker = None
        self._stdout_queue = None
        self._stdout_thread = None
        if worker is not None:
            worker_pid = getattr(worker, "pid", None)
            if worker_pid is not None:
                unregister_qwen_worker(worker_pid)
            try:
                if worker.stdin:
                    worker.stdin.close()
            except (OSError, ValueError):
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
            except (OSError, ValueError):
                pass
        if self._worker_log is not None:
            try:
                self._worker_log.flush()
                self._worker_log.close()
            except (OSError, ValueError):
                pass
            self._worker_log = None
