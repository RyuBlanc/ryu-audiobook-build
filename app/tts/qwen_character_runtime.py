from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from functools import lru_cache

from app.core.paths import models_root
from app.version import APP_VERSION
from app.tts.qwen_accelerator import (
    accelerator_report,
    best_accelerator,
    detect_accelerators,
    model_selection_memory_gb,
)

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
    "base-1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
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
BOOTSTRAP_VERSION = 7


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
            headers={"User-Agent": f"Ryu-Audiobook-QwenRuntime/{APP_VERSION}"},
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
        size = temp.stat().st_size if temp.is_file() else 0
        if total > 0 and received != total:
            raise RuntimeError(
                "The downloaded Python runtime installer is incomplete: "
                f"received {received:,} of {total:,} expected bytes."
            )
        if size < 5_000_000:
            raise RuntimeError(
                "The downloaded Python runtime installer is incomplete: "
                f"received only {size:,} bytes."
            )
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


def _install_runtime_packages(python: Path, progress=None) -> str:
    """Install the best compatible Qwen runtime and return its verified backend.

    NVIDIA CUDA may fall back to CPU if neither CUDA wheel is installable. AMD
    ROCm and Intel XPU candidates must pass their own backend checks; they are
    never marked accelerated merely because a display adapter was detected.
    """
    if progress:
        progress("Installing PyTorch for the local character engine…")

    code, detail = _run_capture(
        [str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        timeout=900,
    )
    if code != 0:
        raise RuntimeError(f"Qwen runtime pip bootstrap failed: {detail[-2500:]}")

    adapters = detect_accelerators()
    amd_candidate = next(
        (item for item in adapters if item.backend == "rocm-candidate"), None
    )
    intel_candidate = next(
        (item for item in adapters if item.backend == "xpu-candidate"), None
    )
    active = best_accelerator()

    cpu_plan = (
        "CPU",
        [
            "--index-url", "https://download.pytorch.org/whl/cpu",
            f"torch=={TORCH_VERSION}", f"torchaudio=={TORCHAUDIO_VERSION}",
        ],
        "cpu",
    )
    install_plan: list[tuple[str, list[str], str]] = []

    if _has_nvidia_gpu() or active.backend == "cuda":
        install_plan.extend([
            (
                "CUDA 12.8",
                [
                    "--index-url", "https://download.pytorch.org/whl/cu128",
                    f"torch=={TORCH_VERSION}", f"torchaudio=={TORCHAUDIO_VERSION}",
                ],
                "cuda",
            ),
            (
                "CUDA 12.6",
                [
                    "--index-url", "https://download.pytorch.org/whl/cu126",
                    f"torch=={TORCH_VERSION}", f"torchaudio=={TORCHAUDIO_VERSION}",
                ],
                "cuda",
            ),
        ])
    elif amd_candidate is not None and os.name == "nt":
        # AMD's published Windows bundle is Python 3.12 / ROCm 7.2.1.
        rocm_root = "https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1"
        packages = [
            f"{rocm_root}/rocm_sdk_core-7.2.1-py3-none-win_amd64.whl",
            f"{rocm_root}/rocm_sdk_devel-7.2.1-py3-none-win_amd64.whl",
            f"{rocm_root}/rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl",
            f"{rocm_root}/rocm-7.2.1.tar.gz",
            f"{rocm_root}/torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl",
            f"{rocm_root}/torchaudio-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl",
        ]
        install_plan.append(("AMD ROCm 7.2.1 (Windows)", packages, "rocm"))
    elif intel_candidate is not None and os.name == "nt":
        install_plan.append((
            "Intel XPU (Windows)",
            [
                "--index-url", "https://download.pytorch.org/whl/xpu",
                "torch", "torchaudio",
            ],
            "xpu",
        ))
    elif active.backend == "rocm" and sys.platform.startswith("linux"):
        install_plan.append((
            "AMD ROCm",
            [
                "--index-url", "https://download.pytorch.org/whl/rocm6.4",
                f"torch=={TORCH_VERSION}", f"torchaudio=={TORCHAUDIO_VERSION}",
            ],
            "rocm",
        ))
    elif active.backend == "xpu":
        install_plan.append((
            "Intel XPU",
            [
                "--index-url", "https://download.pytorch.org/whl/xpu",
                "torch", "torchaudio",
            ],
            "xpu",
        ))
    else:
        install_plan.append(cpu_plan)

    install_error = ""
    selected_backend = ""
    selected_label = ""
    for label, package_args, expected_backend in install_plan:
        if progress:
            progress(f"Installing PyTorch {TORCH_VERSION} ({label})…")
        code, detail = _run_capture(
            [
                str(python), "-m", "pip", "install", "--upgrade",
                "--no-cache-dir", *package_args,
            ],
            timeout=3600,
        )
        if code == 0:
            selected_backend = expected_backend
            selected_label = label
            break
        install_error = detail

    # CUDA wheels are allowed to fall back to CPU to keep NVIDIA installations
    # usable if their local driver is too old. AMD/Intel candidates do not
    # silently fall back: the user must see that their GPU runtime did not work.
    if not selected_backend and (_has_nvidia_gpu() or active.backend == "cuda"):
        if progress:
            progress("CUDA wheels were unavailable • installing CPU compatibility runtime…")
        code, detail = _run_capture(
            [
                str(python), "-m", "pip", "install", "--upgrade",
                "--no-cache-dir", *cpu_plan[1],
            ],
            timeout=3600,
        )
        if code == 0:
            selected_backend = "cpu"
            selected_label = cpu_plan[0]
        else:
            install_error = detail

    if not selected_backend:
        hardware = (
            f"{amd_candidate.name} (AMD ROCm)"
            if amd_candidate is not None
            else f"{intel_candidate.name} (Intel XPU)"
            if intel_candidate is not None
            else f"{active.name} ({active.backend})"
        )
        raise RuntimeError(
            f"Could not install the selected Qwen accelerator runtime for {hardware}. "
            "No CPU downgrade was applied to a detected AMD/Intel GPU. "
            f"Last installer error: {install_error[-3000:]}"
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
        progress("Verifying the installed Qwen runtime and accelerator…")
    check = (
        "import sys, torch, torchaudio, qwen_tts; "
        "print('python=' + sys.version.split()[0]); "
        "print('torch=' + torch.__version__); "
        "print('torchaudio=' + torchaudio.__version__); "
        "print('qwen_tts=' + getattr(qwen_tts, '__version__', 'unknown')); "
        "print('cuda=' + str(torch.cuda.is_available())); "
        "print('hip=' + str(getattr(torch.version, 'hip', None))); "
        "xpu=getattr(torch, 'xpu', None); "
        "print('xpu=' + str(bool(xpu is not None and xpu.is_available())))"
    )
    code, detail = _run_capture([str(python), "-c", check], timeout=240)
    if code != 0:
        raise RuntimeError(
            f"Qwen3-TTS runtime self-test failed: {detail[-3500:]}"
        )

    normalized = detail.replace(" ", "")
    backend_ok = (
        (selected_backend == "cpu")
        or (selected_backend == "cuda" and "cuda=True" in normalized and "hip=None" in normalized)
        or (selected_backend == "rocm" and "hip=None" not in normalized and "cuda=True" in normalized)
        or (selected_backend == "xpu" and "xpu=True" in normalized)
    )
    if not backend_ok:
        if selected_backend == "rocm":
            reason = "AMD ROCm packages installed but PyTorch did not activate HIP"
        elif selected_backend == "xpu":
            reason = "Intel XPU packages installed but torch.xpu.is_available() is false"
        else:
            reason = f"PyTorch did not activate the selected {selected_backend} backend"
        raise RuntimeError(f"{reason}. Qwen runtime is not marked ready. {detail[-2500:]}")

    if progress:
        progress(f"Qwen runtime ready • {selected_label}. {detail[-700:]}")
    return selected_backend


def _runtime_self_test(python: Path) -> tuple[bool, str]:
    check = (
        "import sys, torch, torchaudio, qwen_tts; "
        "print('python=' + sys.version.split()[0]); "
        "print('torch=' + torch.__version__); "
        "print('torchaudio=' + torchaudio.__version__); "
        "print('qwen_tts=' + getattr(qwen_tts, '__version__', 'unknown')); "
        "print('cuda=' + str(torch.cuda.is_available())); "
        "print('hip=' + str(getattr(torch.version, 'hip', None))); "
        "xpu=getattr(torch, 'xpu', None); "
        "print('xpu=' + str(bool(xpu is not None and xpu.is_available())))"
    )
    returncode, detail = _run_capture([str(python), "-c", check], timeout=180)
    return returncode == 0, detail[-5000:]


def verify_runtime(progress=None) -> str:
    if not VENV_PYTHON.exists():
        raise RuntimeError("Qwen private Python runtime is missing.")
    ok, detail = _runtime_self_test(VENV_PYTHON)
    if not ok:
        raise RuntimeError(
            "Qwen3-TTS runtime is not healthy. Use 'Repair Qwen3-TTS Runtime'. "
            f"Diagnostic: {detail}"
        )
    worker = worker_script()
    if not worker.exists():
        raise RuntimeError(f"Qwen worker script is missing: {worker}")
    check = (
        "import ast, pathlib; "
        "ast.parse(pathlib.Path(r%r).read_text(encoding='utf-8')); "
        "ast.parse(pathlib.Path(r%r).read_text(encoding='utf-8'))"
    ) % (str(worker), str(Path(__file__).with_name("qwen_accelerator.py")))
    code, detail = _run_capture([str(VENV_PYTHON), "-c", check], timeout=120)
    if code != 0:
        raise RuntimeError(
            "Qwen worker script failed its Python syntax self-check. "
            f"Diagnostic: {detail[-3500:]}"
        )
    if progress:
        progress(f"Qwen runtime healthy • {detail}")
    return detail


def _runtime_version_is_current() -> bool:
    try:
        data = json.loads(MARKER.read_text(encoding="utf-8"))
        if (
            data.get("ready") is not True
            or data.get("bootstrap_version") != BOOTSTRAP_VERSION
            or data.get("qwen_tts") != QWEN_TTS_VERSION
            or not _python_works(VENV_PYTHON)
        ):
            return False

        ok, detail = _runtime_self_test(VENV_PYTHON)
        if not ok:
            return False
        runtime_backend = str(data.get("accelerator") or "cpu").casefold()
        normalized = detail.replace(" ", "")
        if runtime_backend == "cuda":
            return "cuda=True" in normalized and "hip=None" in normalized
        if runtime_backend == "rocm":
            return "cuda=True" in normalized and "hip=None" not in normalized
        if runtime_backend == "xpu":
            return "xpu=True" in normalized
        return runtime_backend == "cpu"
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def install_runtime(progress=None, force_repair: bool = False) -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)

    if force_repair:
        if progress:
            progress("Repairing Qwen3-TTS isolated runtime • model files will be kept…")
        MARKER.unlink(missing_ok=True)
        if VENV_ROOT.exists():
            shutil.rmtree(VENV_ROOT, ignore_errors=True)

    if _runtime_version_is_current() and not force_repair:
        if progress:
            progress(accelerator_report())
            progress("Qwen3-TTS local runtime is already installed.")
        return

    python = _install_portable_python(progress)
    python = _create_or_repair_venv(progress)
    selected_backend = _install_runtime_packages(python, progress)

    MARKER.write_text(
        json.dumps(
            {
                "ready": True,
                "bootstrap_version": BOOTSTRAP_VERSION,
                "python": PYTHON_VERSION,
                "qwen_tts": QWEN_TTS_VERSION,
                "torch": TORCH_VERSION,
                "torchaudio": TORCHAUDIO_VERSION,
                "tokenizer": TOKENIZER_ID,
                "accelerator": selected_backend,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def repair_runtime(progress=None) -> str:
    install_runtime(progress, force_repair=True)
    return verify_runtime(progress)


def reset_voice_cache(progress=None) -> int:
    """Remove generated Qwen voice-reference caches while preserving models/runtime."""
    anchors = RUNTIME_ROOT / "voice_anchors"
    removed = 0
    if anchors.exists():
        for path in anchors.glob("qwen-design-*.wav"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    if progress:
        progress(f"Removed {removed} generated Qwen voice-reference cache file(s).")
    return removed


def install_model(kind: str, progress=None, force_repair: bool = False) -> Path:
    """Install or repair one Qwen model in its dedicated, app-managed folder.

    force_repair redownloads the model files even when the manifest looks valid;
    it never removes the saved voice profiles or another model's folder.
    """
    if kind not in MODEL_IDS:
        raise ValueError(f"Unknown Qwen model kind: {kind}")
    install_runtime(progress)
    target = MODEL_DIRS[kind]
    target.mkdir(parents=True, exist_ok=True)
    if model_installed(kind) and not force_repair:
        if progress:
            progress(f"{MODEL_IDS[kind]} is already installed and passed the file check.")
        return target

    script = (
        "from huggingface_hub import snapshot_download; "
        "snapshot_download(repo_id=%r, local_dir=%r, "
        "allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.npz','*.bin','tokenizer*','vocab*'], "
        "force_download=%r)"
        % (MODEL_IDS[kind], str(target), bool(force_repair))
    )
    if progress:
        action = "Repairing" if force_repair else "Downloading"
        progress(f"{action} {MODEL_IDS[kind]}… This model stays on this PC.")
    _run([str(VENV_PYTHON), "-c", script], progress, timeout=7200)
    if not model_installed(kind):
        raise RuntimeError(f"Qwen model download finished, but {MODEL_IDS[kind]} is incomplete.")
    return target


def runtime_environment() -> dict[str, str]:
    env = os.environ.copy()
    # The Qwen worker is launched as a standalone Python script from the
    # frozen _internal/app/tts directory. Explicitly expose the frozen app
    # root so "from app.tts..." imports work regardless of the process cwd
    # or the Python script-path rules on Windows.
    app_root = Path(__file__).resolve().parents[2]
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(app_root)
        if not existing_pythonpath
        else str(app_root) + os.pathsep + existing_pythonpath
    )
    env["HF_HOME"] = str(RUNTIME_ROOT / "huggingface")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["TRANSFORMERS_ATTENTION_IMPLEMENTATION"] = "sdpa"
    env["TOKENIZERS_PARALLELISM"] = "false"
    env.setdefault("OMP_NUM_THREADS", "2")
    env.setdefault("MKL_NUM_THREADS", "2")
    env.setdefault("OPENBLAS_NUM_THREADS", "2")
    env["PYTHONUNBUFFERED"] = "1"
    return env


def worker_script() -> Path:
    return Path(__file__).with_name("qwen_character_worker.py")
