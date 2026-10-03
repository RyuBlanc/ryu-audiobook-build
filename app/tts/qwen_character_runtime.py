from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

from app.core.paths import models_root

RUNTIME_ROOT = models_root() / "qwen3-tts"
VENV_ROOT = RUNTIME_ROOT / "runtime"
PYTHON = VENV_ROOT / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
MARKER = RUNTIME_ROOT / "runtime.json"

MODEL_IDS = {
    "custom-0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    "custom-1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "design-1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "base-0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
}
MODEL_DIRS = {key: RUNTIME_ROOT / key for key in MODEL_IDS}
TOKENIZER_ID = "Qwen/Qwen3-TTS-Tokenizer-12Hz"

CUSTOM_SPEAKERS = (
    "Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric",
    "Ryan", "Aiden", "Ono_Anna", "Sohee",
)


def runtime_ready() -> bool:
    if not PYTHON.exists():
        return False
    if not MARKER.exists():
        return False
    try:
        data = json.loads(MARKER.read_text(encoding="utf-8"))
        return data.get("ready") is True
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def runtime_python() -> Path:
    return PYTHON


def model_path(kind: str) -> Path:
    return MODEL_DIRS[kind]


def model_installed(kind: str) -> bool:
    root = MODEL_DIRS[kind]
    return (root / "config.json").exists() and any(root.glob("*.safetensors"))


def best_custom_kind(vram_gb: float | None = None) -> str:
    if vram_gb is not None and vram_gb >= 7.0 and model_installed("custom-1.7b"):
        return "custom-1.7b"
    if model_installed("custom-0.6b"):
        return "custom-0.6b"
    if model_installed("custom-1.7b"):
        return "custom-1.7b"
    return "custom-0.6b"


def _run(command: list[str], progress=None, timeout: int = 3600) -> None:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    try:
        for line in iter(process.stdout.readline, ""):
            line = line.strip()
            if line and progress:
                progress(line[-500:])
        code = process.wait(timeout=timeout)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass
        raise
    if code != 0:
        raise RuntimeError(f"Qwen character runtime command failed with exit code {code}.")


def install_runtime(progress=None) -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    if runtime_ready():
        if progress:
            progress("Qwen3-TTS local runtime is already installed.")
        return
    import venv
    if progress:
        progress("Creating isolated Qwen3-TTS runtime…")
    venv.EnvBuilder(with_pip=True, clear=False, upgrade_deps=True).create(VENV_ROOT)
    _run(
        [
            str(PYTHON), "-m", "pip", "install", "--upgrade",
            "qwen-tts==0.1.1",
        ],
        progress,
        timeout=3600,
    )
    MARKER.write_text(
        json.dumps(
            {
                "ready": True,
                "package": "qwen-tts==0.1.1",
                "tokenizer": TOKENIZER_ID,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def install_model(kind: str, progress=None) -> Path:
    if kind not in MODEL_IDS:
        raise ValueError(f"Unknown Qwen model kind: {kind}")
    install_runtime(progress)
    target = MODEL_DIRS[kind]
    target.mkdir(parents=True, exist_ok=True)
    if model_installed(kind):
        if progress:
            progress(f"{MODEL_IDS[kind]} is already installed.")
        return target

    # Use the isolated runtime's huggingface_hub so application dependencies
    # are never replaced by the character-TTS stack.
    script = (
        "from huggingface_hub import snapshot_download; "
        "snapshot_download(repo_id=%r, local_dir=%r, local_dir_use_symlinks=False, "
        "allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.npz','*.bin','tokenizer*','vocab*'])"
        % (MODEL_IDS[kind], str(target))
    )
    if progress:
        progress(f"Downloading {MODEL_IDS[kind]}… This model stays on this PC.")
    _run([str(PYTHON), "-c", script], progress, timeout=7200)
    if not model_installed(kind):
        raise RuntimeError(f"Qwen model download finished, but {MODEL_IDS[kind]} is incomplete.")
    return target


def runtime_environment() -> dict[str, str]:
    env = os.environ.copy()
    env["HF_HOME"] = str(RUNTIME_ROOT / "huggingface")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["TRANSFORMERS_ATTENTION_IMPLEMENTATION"] = "sdpa"
    return env


def worker_script() -> Path:
    return Path(__file__).with_name("qwen_character_worker.py")
