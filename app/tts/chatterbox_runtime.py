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
    # Chatterbox is most reliable on Python 3.11. Prefer it over the host
    # Python used by the frozen application and reject known-incompatible 3.12
    # environments rather than installing a broken runtime.
    candidates = (
        ["py", "-3.11"],
        [sys.executable] if sys.version_info[:2] == (3, 11) else None,
        ["python3.11"],
        ["python"],
    )
    for command in candidates:
        if not command:
            continue
        try:
            result = subprocess.run(
                command + ["-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                version = (result.stdout or "").strip()
                if version.startswith("3.11"):
                    return command
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def _has_nvidia() -> bool:
    command = shutil.which("nvidia-smi")
    if not command:
        return False
    try:
        return subprocess.run(
            [command, "-L"], capture_output=True, text=True, timeout=5
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def install_runtime(progress: Callable[[str], None] | None = None) -> None:
    system_python = _system_python()
    if not system_python:
        raise RuntimeError(
            "Python 3.11 (64-bit) is required for the optional custom voice engine. "
            "Install Python 3.11 from python.org, then retry the installation."
        )

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    python = _venv_python()
    if progress:
        progress("Creating isolated custom voice environment…")
    if not python.exists():
        result = subprocess.run(
            system_python + ["-m", "venv", str(RUNTIME_DIR)],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Could not create the custom voice environment. "
                + (result.stderr or result.stdout).strip()[-2500:]
            )

    if progress:
        progress("Installing Chatterbox and audio dependencies…")
    requirements = _resource_path("requirements-voice-cloning.txt")
    if not requirements.exists():
        raise RuntimeError(f"Voice-cloning requirements are missing from this build: {requirements}")

    commands = [
        [str(python), "-m", "pip", "install", "--upgrade", "pip"],
        [str(python), "-m", "pip", "install", "-r", str(requirements)],
    ]
    if _has_nvidia():
        # Chatterbox 0.1.7 pins torch 2.6.0. Replace the default CPU wheel
        # with the official CUDA 12.4 wheels used by RTX 20/30/40-class GPUs.
        # Automatic mode still falls back to CPU if CUDA cannot be used.
        commands.append([
            str(python), "-m", "pip", "install", "--upgrade", "--force-reinstall",
            "torch==2.6.0", "torchaudio==2.6.0",
            "--index-url", "https://download.pytorch.org/whl/cu124",
        ])

    for command in commands:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Custom voice runtime installation failed. "
                + (result.stderr or result.stdout).strip()[-5000:]
            )

    verify = subprocess.run(
        [
            str(python), "-c",
            "import chatterbox, torch, torchaudio; "
            "print(f'torch={torch.__version__}'); "
            "print(f'cuda={torch.cuda.is_available()}'); "
            "print('gpu=' + (torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'))",
        ],
        capture_output=True, text=True, timeout=180,
    )
    if verify.returncode != 0:
        raise RuntimeError(
            "The custom voice runtime installed but could not be imported. "
            + (verify.stderr or verify.stdout).strip()[-3000:]
        )

    MARKER.write_text(json.dumps({
        "provider": "chatterbox",
        "ready": True,
        "python": str(python),
        "runtime": (verify.stdout or "").strip(),
        "gpu_acceleration": _has_nvidia(),
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
