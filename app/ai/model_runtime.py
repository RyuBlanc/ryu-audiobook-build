from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.request
import zipfile

from app.core.paths import models_root

try:
    import certifi
except ImportError:
    certifi = None


LLAMA_RELEASE = "b11193"
LLAMA_CUDA12_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_RELEASE}/llama-b11193-bin-win-cuda-12.4-x64.zip"
LLAMA_CPU_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_RELEASE}/llama-b11193-bin-win-cpu-x64.zip"

MODEL_1_7B_URL = "https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/4102b64b54bf3f0ddb9408d83f42d5091e0a7b64/Qwen3-1.7B-Q5_K_M.gguf"
MODEL_4B_URL = "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf"


class BrainRuntimeError(RuntimeError):
    pass


def brain_root() -> Path:
    root = models_root() / "audiobook-ai"
    root.mkdir(parents=True, exist_ok=True)
    return root


def detect_nvidia_vram_gb() -> float:
    command = shutil.which("nvidia-smi")
    if not command:
        return 0.0
    try:
        result = subprocess.run(
            [command, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        values = [float(x.strip()) for x in result.stdout.splitlines() if x.strip()]
        return max(values, default=0.0) / 1024.0
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0.0


def recommended_model() -> tuple[str, str, int]:
    vram = detect_nvidia_vram_gb()
    if vram >= 7.0:
        return "qwen3-4b-q4", "Qwen3-4B-Q4_K_M.gguf", 2_500_000_000
    return "qwen3-1.7b-q5", "Qwen3-1.7B-Q5_K_M.gguf", 1_260_000_000


def model_path(model_id: str | None = None) -> Path:
    model_id = model_id or recommended_model()[0]
    filename = "Qwen3-4B-Q4_K_M.gguf" if model_id == "qwen3-4b-q4" else "Qwen3-1.7B-Q5_K_M.gguf"
    return brain_root() / filename


def server_path() -> Path | None:
    exe = brain_root() / "llama-server.exe"
    return exe if exe.exists() else None


def installed() -> bool:
    model_id, _, _ = recommended_model()
    return server_path() is not None and model_path(model_id).exists()


def _ssl_context() -> ssl.SSLContext:
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def download(url: str, target: Path, label: str = "file", progress=None) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Ryu-Audiobook/1.0", "Accept": "application/octet-stream"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120, context=_ssl_context()) as response, temp.open("wb") as handle:
            total = int(response.headers.get("Content-Length", "0") or 0)
            received = 0
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                handle.write(block)
                received += len(block)
                if progress and total:
                    progress(f"Downloading {label}… {received * 100 // total}%")
        if not temp.exists() or temp.stat().st_size < 1024:
            raise BrainRuntimeError(f"{label} download is incomplete.")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


def install_runtime(progress=None) -> Path:
    root = brain_root()
    server = root / "llama-server.exe"
    if not server.exists():
        vram = detect_nvidia_vram_gb()
        url = LLAMA_CUDA12_URL if vram > 0 else LLAMA_CPU_URL
        with tempfile.TemporaryDirectory(prefix="ryu-llama-") as temp_dir:
            archive = Path(temp_dir) / "llama.zip"
            if progress:
                progress("Downloading local AI runtime…")
            download(url, archive, "llama.cpp runtime", progress)
            with zipfile.ZipFile(archive) as zf:
                candidates = [n for n in zf.namelist() if n.lower().endswith("/llama-server.exe") or n.lower() == "llama-server.exe"]
                if not candidates:
                    raise BrainRuntimeError("The llama.cpp runtime did not contain llama-server.exe.")
                selected = candidates[0]
                extracted = Path(temp_dir) / "extracted"
                zf.extractall(extracted)
                src = extracted / selected
                if not src.exists():
                    src = next(extracted.rglob("llama-server.exe"))
                shutil.copy2(src, server)
                for dll in extracted.rglob("*.dll"):
                    destination = root / dll.name
                    if not destination.exists():
                        shutil.copy2(dll, destination)

    model_id, filename, _size = recommended_model()
    target = root / filename
    if not target.exists():
        if progress:
            progress(f"Downloading Audiobook AI model: {filename}…")
        url = MODEL_4B_URL if model_id == "qwen3-4b-q4" else MODEL_1_7B_URL
        download(url, target, filename, progress)

    return target


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class LocalLLM:
    def __init__(self, model: Path | None = None):
        self.model = model or model_path()
        self.server = server_path()
        if self.server is None:
            raise BrainRuntimeError("Audiobook AI runtime is not installed.")
        if not self.model.exists():
            raise BrainRuntimeError("Audiobook AI model is not installed.")
        self.process: subprocess.Popen | None = None
        self.port: int | None = None
        self.log_path = brain_root() / "llama-server.log"

    def start(self) -> None:
        if self.process and self.process.poll() is None:
            return
        self.port = _free_port()
        vram = detect_nvidia_vram_gb()
        args = [
            str(self.server), "-m", str(self.model),
            "--host", "127.0.0.1", "--port", str(self.port),
            "--ctx-size", "16384", "--batch-size", "512",
            "--ubatch-size", "256", "--no-webui",
            "--reasoning", "auto", "--reasoning-format", "none",
            "--chat-template-kwargs", "{\"enable_thinking\":false}",
        ]
        if vram >= 4.0:
            args += ["--n-gpu-layers", "99"]
        log_handle = self.log_path.open("a", encoding="utf-8", errors="replace")
        self.process = subprocess.Popen(
            args,
            stdout=log_handle,
            stderr=log_handle,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise BrainRuntimeError(f"Local AI server exited early. See {self.log_path}.")
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{self.port}/health")
                with urllib.request.urlopen(req, timeout=1) as response:
                    if response.status == 200:
                        return
            except Exception:
                time.sleep(0.5)
        raise BrainRuntimeError("Local Audiobook AI server did not become ready in 90 seconds.")

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 1200,
        temperature: float = 0.15,
        response_schema: dict | None = None,
    ) -> str:
        self.start()
        body = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "top_p": 0.9,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if response_schema:
            body["response_format"] = {
                "type": "json_object",
                "schema": response_schema,
            }
        # Qwen3 supports a per-request non-thinking switch; keep the server
        # itself in reasoning-off mode as the primary guard, and also pass the
        # template hint for older compatible llama.cpp builds.
        body["chat_template_kwargs"] = {"enable_thinking": False}
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            log_tail = ""
            try:
                if self.log_path.exists():
                    log_tail = self.log_path.read_text(encoding="utf-8", errors="replace")[-6000:]
            except OSError:
                pass
            raise BrainRuntimeError(
                f"Local Audiobook AI request failed: {exc}"
                + (f"\n\nllama-server log:\n{log_tail}" if log_tail else "")
            ) from exc
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, TypeError, IndexError) as exc:
            raise BrainRuntimeError(f"Local AI returned an unexpected response: {data}") from exc

    def close(self) -> None:
        process = self.process
        self.process = None
        self.port = None
        if process is not None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass


def self_test() -> str:
    """Run a real local inference and return a short JSON response."""
    from json import JSONDecoder
    llm = LocalLLM()
    try:
        schema = {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "message": {"type": "string"},
            },
            "required": ["ok", "message"],
            "additionalProperties": False,
        }
        raw = llm.complete(
            "You are the Ryu's Audiobook AI self-test. Return only JSON.",
            'Return {"ok":true,"message":"ready"}. Do not add any other text.',
            max_tokens=80,
            temperature=0.0,
            response_schema=schema,
        )
        start = raw.find("{")
        if start < 0:
            raise BrainRuntimeError("Audiobook AI self-test returned no JSON object.")
        value, _ = JSONDecoder().raw_decode(raw[start:])
        if value.get("ok") is not True:
            raise BrainRuntimeError(f"Audiobook AI self-test returned: {value}")
        return str(value.get("message") or "ready")
    finally:
        llm.close()
