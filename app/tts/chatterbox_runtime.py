from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Callable

from app.core.paths import models_root

RUNTIME_DIR = models_root() / "chatterbox-runtime"
MARKER = RUNTIME_DIR / "runtime.json"

def _venv_python() -> Path:
    return RUNTIME_DIR / "Scripts" / "python.exe"

def runtime_python() -> Path | None:
    path = _venv_python()
    return path if path.exists() else None

def runtime_ready() -> bool:
    path = runtime_python()
    if not path or not MARKER.exists():
        return False
    try:
        data = json.loads(MARKER.read_text(encoding="utf-8"))
        return bool(data.get("provider") == "chatterbox" and data.get("ready"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False

def _resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / relative

def worker_script() -> Path:
    path = _resource_path("app/tts/chatterbox_worker.py")
    if not path.exists():
        raise RuntimeError(f"Chatterbox worker is missing from this build: {path}")
    return path

def _system_python() -> list[str] | None:
    for command in (["py", "-3.11"], ["py", "-3"], ["python"]):
        try:
            result = subprocess.run(command + ["-c", "import sys; print(sys.version_info[:2])"],
                                    capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                return command
        except (OSError, subprocess.SubprocessError):
            continue
    return None

def install_runtime(progress: Callable[[str], None] | None = None) -> None:
    system_python = _system_python()
    if not system_python:
        raise RuntimeError(
            "Python is required for the optional custom voice engine. "
            "Install Python 3.11 (64-bit) and make sure the 'py' launcher is available, then retry."
        )
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    python = _venv_python()
    if progress:
        progress("Creating isolated custom voice environment…")
    if not python.exists():
        result = subprocess.run(system_python + ["-m", "venv", str(RUNTIME_DIR)],
                                capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError("Could not create the custom voice environment. " +
                               (result.stderr or result.stdout).strip()[-2500:])
    if progress:
        progress("Installing Chatterbox and audio dependencies…")
    requirements = _resource_path("requirements-voice-cloning.txt")
    if not requirements.exists():
        raise RuntimeError(f"Voice-cloning requirements are missing from this build: {requirements}")
    for command in (
        [str(python), "-m", "pip", "install", "--upgrade", "pip"],
        [str(python), "-m", "pip", "install", "-r", str(requirements)],
    ):
        result = subprocess.run(command, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            raise RuntimeError("Custom voice runtime installation failed. " +
                               (result.stderr or result.stdout).strip()[-4000:])
    verify = subprocess.run(
        [str(python), "-c", "import chatterbox, torch, torchaudio; print(torch.__version__)"],
        capture_output=True, text=True, timeout=180,
    )
    if verify.returncode != 0:
        raise RuntimeError("The custom voice runtime installed but could not be imported. " +
                           (verify.stderr or verify.stdout).strip()[-3000:])
    MARKER.write_text(json.dumps({
        "provider": "chatterbox", "ready": True,
        "python": str(python), "torch": (verify.stdout or "").strip(),
    }, indent=2), encoding="utf-8")
    if progress:
        progress("Custom voice engine is ready.")

def runtime_status() -> str:
    if runtime_ready():
        return "Installed"
    if RUNTIME_DIR.exists():
        return "Incomplete"
    return "Not installed"

def remove_runtime() -> None:
    if RUNTIME_DIR.exists():
        shutil.rmtree(RUNTIME_DIR, ignore_errors=True)

def runtime_environment() -> dict[str, str]:
    env = os.environ.copy()
    hf_home = models_root() / "huggingface"
    hf_home.mkdir(parents=True, exist_ok=True)
    env["HF_HOME"] = str(hf_home)
    env.setdefault("TRANSFORMERS_ATTN_IMPLEMENTATION", "eager")
    return env
