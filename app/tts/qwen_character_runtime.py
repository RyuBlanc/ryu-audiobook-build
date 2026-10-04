from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

from app.core.paths import models_root

# Qwen3-TTS currently publishes a stable Python 3.12 package/runtime path.
# The official qwen-tts package is 0.1.1 and supports Python 3.12. We keep this
# runtime completely separate from the frozen Ryu's Audiobook interpreter so
# PyInstaller cannot accidentally become the "python.exe" for venv creation.
PYTHON_VERSION = "3.12.10"
PYTHON_INSTALLER_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
    f"python-{PYTHON_VERSION}-amd64.exe"
)

RUNTIME_ROOT = models_root() / "qwen3-tts"
PYTHON_ROOT = RUNTIME_ROOT / "python312"
PYTHON = PYTHON_ROOT / "python.exe"
VENV_ROOT = RUNTIME_ROOT / "runtime"
VENV_PYTHON = VENV_ROOT / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
MARKER = RUNTIME_ROOT / "runtime.json"
INSTALLER_PATH = RUNTIME_ROOT / f"python-{PYTHON_VERSION}-amd64.exe"
INSTALLER_LOG = RUNTIME_ROOT / "python-install.log"

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

TORCH_VERSION = "2.9.1"
TORCHAUDIO_VERSION = "2.9.1"
QWEN_TTS_VERSION = "0.1.1"


def _python_works(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        result = subprocess.run(
            [str(path), "-c", "import sys; print(sys.version_info[:2])"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _run_capture(command: list[str], timeout: int = 120) -> tuple[int, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        return result.returncode, (result.stdout or result.stderr or "").strip()
    except subprocess.TimeoutExpired as exc:
        return 124, str(exc)
    except OSError as exc:
        return 1, str(exc)


def _has_nvidia_gpu() -> bool:
    code, output = _run_capture(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        timeout=10,
    )
    return code == 0 and bool(output.strip())


def _download_file(url: str, target: Path, progress=None) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".part")
    try:
        if progress:
            progress("Downloading the private Qwen runtime's Python 3.12 bootstrap…")
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Ryu-Audiobook-QwenRuntime/0.3.7"},
        )
        with urllib.request.urlopen(request, timeout=120) as response, temp.open("wb") as handle:
            total = int(response.headers.get("Content-Length", "0") or 0)
            received = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                received += len(chunk)
                if progress and total:
                    progress(
                        f"Downloading Python runtime… {received * 100 // total}%"
                    )
        if not temp.exists() or temp.stat().st_size < 5_000_000:
            raise RuntimeError("The downloaded Python runtime installer is incomplete.")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


def _install_portable_python(progress=None) -> Path:
    if _python_works(PYTHON):
        return PYTHON

    # A previous release could have created the venv from the frozen
    # Ryu's Audiobook.exe interpreter. That produces the exact
    # "_internal\\python312.dll not found" error seen by users. Remove the
    # broken interpreter/venv so the next install starts from a real CPython.
    if PYTHON_ROOT.exists():
        if progress:
            progress("Repairing the offline character Python runtime…")
        shutil.rmtree(PYTHON_ROOT, ignore_errors=True)

    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    _download_file(PYTHON_INSTALLER_URL, INSTALLER_PATH, progress)

    if progress:
        progress("Installing the private Python 3.12 runtime…")

    command = [
        str(INSTALLER_PATH),
        "/quiet",
        "/passive",
        "InstallAllUsers=0",
        "Include_launcher=0",
        "Include_test=0",
        "PrependPath=0",
        "Shortcuts=0",
        f"TargetDir={PYTHON_ROOT}",
        f"/log={INSTALLER_LOG}",
    ]
    code, detail = _run_capture(command, timeout=900)
    if code not in {0, 3010} or not _python_works(PYTHON):
        tail = ""
        try:
            if INSTALLER_LOG.exists():
                tail = INSTALLER_LOG.read_text(encoding="utf-8", errors="replace")[-5000:]
        except OSError:
            pass
        raise RuntimeError(
            "Ryu could not install its private Python 3.12 runtime. "
            f"Installer exit code: {code}. {detail[-1000:]} {tail[-2500:]}"
        )
    return PYTHON


def _create_or_repair_venv(progress=None) -> Path:
    if _python_works(VENV_PYTHON):
        return VENV_PYTHON

    if VENV_ROOT.exists():
        shutil.rmtree(VENV_ROOT, ignore_errors=True)

    if progress:
        progress("Creating the isolated Qwen3-TTS environment…")

    code, detail = _run_capture(
        [str(PYTHON), "-m", "venv", str(VENV_ROOT)],
        timeout=180,
    )
    if code != 0 or not _python_works(VENV_PYTHON):
        raise RuntimeError(
            "The isolated Qwen3-TTS environment could not be created. "
            f"Exit code: {code}. {detail[-3000:]}"
        )
    return VENV_PYTHON


def _install_runtime_packages(python: Path, progress=None) -> None:
    if progress:
        progress("Installing PyTorch for the local character engine…")

    code, detail = _run_capture(
        [str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        timeout=900,
    )
    if code != 0:
        raise RuntimeError(f"Qwen runtime pip bootstrap failed: {detail[-2500:]}")

    if _has_nvidia_gpu():
        torch_indexes = (
            "https://download.pytorch.org/whl/cu128",
            "https://download.pytorch.org/whl/cu126",
        )
    else:
        torch_indexes = ("https://download.pytorch.org/whl/cpu",)

    torch_error = ""
    for index_url in torch_indexes:
        if progress:
            label = "CUDA 12.8" if "cu128" in index_url else (
                "CUDA 12.6" if "cu126" in index_url else "CPU"
            )
            progress(f"Installing PyTorch {TORCH_VERSION} ({label})…")
        code, detail = _run_capture(
            [
                str(python), "-m", "pip", "install", "--upgrade",
                f"torch=={TORCH_VERSION}",
                f"torchaudio=={TORCHAUDIO_VERSION}",
                "--index-url", index_url,
            ],
            timeout=2400,
        )
        if code == 0:
            torch_error = ""
            break
        torch_error = detail

    if torch_error:
        raise RuntimeError(
            "PyTorch installation failed for the offline character engine. "
            f"Last error: {torch_error[-3500:]}"
        )

    if progress:
        progress("Installing the official Qwen3-TTS Python package…")
    code, detail = _run_capture(
        [
            str(python), "-m", "pip", "install", "--upgrade",
            f"qwen-tts=={QWEN_TTS_VERSION}",
        ],
        timeout=2400,
    )
    if code != 0:
        raise RuntimeError(
            f"Qwen3-TTS package installation failed: {detail[-3500:]}"
        )

    if progress:
        progress("Testing the offline character Python runtime…")
    check = (
        "import torch, torchaudio, qwen_tts; "
        "print('torch=' + torch.__version__); "
        "print('cuda=' + str(torch.cuda.is_available()))"
    )
    code, detail = _run_capture([str(python), "-c", check], timeout=180)
    if code != 0:
        raise RuntimeError(
            f"Qwen3-TTS runtime self-test failed: {detail[-3500:]}"
        )

    if progress:
        progress(f"Offline character runtime ready. {detail[-700:]}")


def _runtime_version_is_current() -> bool:
    try:
        data = json.loads(MARKER.read_text(encoding="utf-8"))
        return (
            data.get("ready") is True
            and data.get("bootstrap_version") == 2
            and data.get("qwen_tts") == QWEN_TTS_VERSION
            and _python_works(VENV_PYTHON)
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def runtime_ready() -> bool:
    return _runtime_version_is_current()


def runtime_python() -> Path:
    return VENV_PYTHON


def model_path(kind: str) -> Path:
    return MODEL_DIRS[kind]


def model_installed(kind: str) -> bool:
    root = MODEL_DIRS[kind]
    return (root / "config.json").exists() and any(root.glob("*.safetensors"))


def _detected_vram_gb() -> float:
    """Return the largest NVIDIA VRAM size visible to this PC, or 0."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if result.returncode != 0:
            return 0.0
        values = []
        for line in result.stdout.splitlines():
            value = line.strip()
            try:
                values.append(float(value))
            except ValueError:
                continue
        return max(values, default=0.0) / 1024.0
    except (OSError, subprocess.SubprocessError):
        return 0.0


def best_custom_kind(vram_gb: float | None = None) -> str:
    # Qwen 1.7B is the quality path for 8GB-class GPUs; 0.6B is the
    # compatibility path for 4GB-class GPUs. Detect VRAM automatically when
    # the caller does not provide it so Voice Cast and generation make the
    # same hardware-aware choice as the Models installer.
    if vram_gb is None:
        vram_gb = _detected_vram_gb()
    if vram_gb >= 7.0 and model_installed("custom-1.7b"):
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

    if _runtime_version_is_current():
        if progress:
            progress("Qwen3-TTS local runtime is already installed.")
        return

    python = _install_portable_python(progress)
    python = _create_or_repair_venv(progress)
    _install_runtime_packages(python, progress)

    MARKER.write_text(
        json.dumps(
            {
                "ready": True,
                "bootstrap_version": 2,
                "python": PYTHON_VERSION,
                "qwen_tts": QWEN_TTS_VERSION,
                "torch": TORCH_VERSION,
                "torchaudio": TORCHAUDIO_VERSION,
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

    script = (
        "from huggingface_hub import snapshot_download; "
        "snapshot_download(repo_id=%r, local_dir=%r, "
        "allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.npz','*.bin','tokenizer*','vocab*'])"
        % (MODEL_IDS[kind], str(target))
    )
    if progress:
        progress(f"Downloading {MODEL_IDS[kind]}… This model stays on this PC.")
    _run([str(VENV_PYTHON), "-c", script], progress, timeout=7200)
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
