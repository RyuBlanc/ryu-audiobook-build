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

from app.core.paths import models_root, runtimes_root, model_cache_root
from app.version import APP_VERSION
from app.tts.qwen_accelerator import (
    accelerator_report,
    detect_accelerators,
    best_accelerator,
    model_selection_memory_gb,
    amd_windows_runtime_spec,
    windows_host_identity,
    gpu_runtime_candidates,
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

RUNTIME_ROOT = runtimes_root() / "qwen3-tts"
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
MODEL_DIRS = {key: models_root() / "qwen3-tts" / key for key in MODEL_IDS}
TOKENIZER_ID = "Qwen/Qwen3-TTS-Tokenizer-12Hz"

CUSTOM_SPEAKERS = (
    "Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric",
    "Ryan", "Aiden", "Ono_Anna", "Sohee",
)

TORCH_VERSION = "2.9.1"
TORCHAUDIO_VERSION = "2.9.1"
QWEN_TTS_VERSION = "0.1.1"
BOOTSTRAP_VERSION = 9


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


def _install_runtime_packages(python: Path, progress=None) -> tuple[str, str, str]:
    """Install the best compatible Qwen runtime and return backend + installed package versions."""
    if progress:
        progress("Installing PyTorch for the local character engine…")
    code, detail = _run_capture(
        [str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        timeout=900,
    )
    if code != 0:
        raise RuntimeError(f"Qwen runtime pip bootstrap failed: {detail[-2500:]}")

    adapters = detect_accelerators()
    amd_candidate = next((item for item in adapters if item.backend == "rocm-candidate"), None)
    intel_candidate = next((item for item in adapters if item.backend == "xpu-candidate"), None)
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
        os_caption, display_version, cpu_name = windows_host_identity()
        spec = amd_windows_runtime_spec(
            amd_candidate.name, cpu_name, os_caption, display_version
        )
        if spec is None:
            raise RuntimeError(
                f"AMD adapter {amd_candidate.name} is not listed for this Windows release. "
                "Qwen will not install an unverified ROCm runtime or downgrade this GPU "
                "to a misleading accelerated state."
            )
        if spec["rocm"] == "10.1.0":
            label = f"AMD ROCm 10.1.0 ({spec['arch']}, Windows 11 25H2)"
            package_args = [
                "--index-url", "https://stable.repo.amd.com/rocm/whl-next/",
                f"torch[device-{spec['arch']}]=={spec['torch']}",
                f"torchaudio=={spec['torchaudio']}",
            ]
        else:
            rocm_root = "https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1"
            package_args = [
                f"{rocm_root}/rocm_sdk_core-7.2.1-py3-none-win_amd64.whl",
                f"{rocm_root}/rocm_sdk_devel-7.2.1-py3-none-win_amd64.whl",
                f"{rocm_root}/rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl",
                f"{rocm_root}/rocm-7.2.1.tar.gz",
                f"{rocm_root}/torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl",
                f"{rocm_root}/torchaudio-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl",
            ]
            label = "AMD ROCm 7.2.1 (legacy Windows 11 support)"
        install_plan.append((label, package_args, "rocm"))
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
            progress(f"Installing PyTorch ({label})…")
        code, detail = _run_capture(
            [
                str(python), "-m", "pip", "install", "--upgrade",
                "--no-cache-dir", *package_args,
            ],
            timeout=3600,
        )
        if code == 0:
            selected_backend, selected_label = expected_backend, label
            break
        install_error = detail

    # Never silently replace a detected GPU runtime with CPU PyTorch. A
    # user may explicitly select CPU, but Auto must either activate the
    # compatible GPU backend or report why it could not.
    if not selected_backend:
        hardware = (
            f"{amd_candidate.name} (AMD ROCm)" if amd_candidate is not None
            else f"{intel_candidate.name} (Intel XPU)" if intel_candidate is not None
            else f"{active.name} ({active.backend})"
        )
        raise RuntimeError(
            f"Could not activate the selected Qwen GPU runtime for {hardware}. "
            "CPU fallback was not installed automatically because it would hide "
            "a GPU performance failure. Check driver/runtime compatibility and "
            f"use explicit CPU selection only when intended. Last error: {install_error[-3000:]}"
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
        raise RuntimeError(f"Qwen3-TTS package installation failed: {detail[-3500:]}")

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
        raise RuntimeError(f"Qwen3-TTS runtime self-test failed: {detail[-3500:]}")

    normalized = detail.replace(" ", "")
    backend_ok = (
        selected_backend == "cpu"
        or (selected_backend == "cuda" and "cuda=True" in normalized and "hip=None" in normalized)
        or (selected_backend == "rocm" and "cuda=True" in normalized and "hip=None" not in normalized)
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

    def output_value(key: str) -> str:
        prefix = key + "="
        for line in detail.splitlines():
            if line.strip().startswith(prefix):
                return line.strip()[len(prefix):].strip()
        return ""

    installed_torch = output_value("torch")
    installed_torchaudio = output_value("torchaudio")
    if not installed_torch or not installed_torchaudio:
        raise RuntimeError(
            "Qwen runtime self-test did not report installed PyTorch and torchaudio versions."
        )
    if progress:
        progress(f"Qwen runtime ready • {selected_label}. {detail[-700:]}")
    return selected_backend, installed_torch, installed_torchaudio


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
        "ast.parse(pathlib.Path(r%r).read_text(encoding='utf-8'))"
    ) % str(worker)
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

        def output_value(key: str) -> str:
            prefix = key + "="
            for line in detail.splitlines():
                if line.strip().startswith(prefix):
                    return line.strip()[len(prefix):].strip()
            return ""

        if (
            data.get("torch") != output_value("torch")
            or data.get("torchaudio") != output_value("torchaudio")
        ):
            return False
        backend = str(data.get("accelerator") or "cpu").casefold()
        normalized = detail.replace(" ", "")
        if backend == "cuda":
            return "cuda=True" in normalized and "hip=None" in normalized
        if backend == "rocm":
            return "cuda=True" in normalized and "hip=None" not in normalized
        if backend == "xpu":
            return "xpu=True" in normalized
        return backend == "cpu"
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def runtime_ready() -> bool:
    """Cheap UI-safe readiness gate.

    The previous implementation imported torch, torchaudio and qwen_tts in a
    subprocess every time a voice-selection callback queried readiness. On
    some Windows/GPU setups that import can take several seconds and makes
    Qt report the application as not responding. This fast gate only checks
    local marker/filesystem state. The worker process remains responsible for
    real model/runtime initialization, and verify_runtime() remains the full
    diagnostic used by repair/installation workflows.
    """
    try:
        if not MARKER.is_file() or not VENV_PYTHON.is_file() or not worker_script().is_file():
            return False
        data = json.loads(MARKER.read_text(encoding="utf-8"))
        return (
            data.get("ready") is True
            and data.get("bootstrap_version") == BOOTSTRAP_VERSION
            and data.get("qwen_tts") == QWEN_TTS_VERSION
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def runtime_python() -> Path:
    return VENV_PYTHON


def model_path(kind: str) -> Path:
    return MODEL_DIRS[kind]


def _model_weight_file_ready(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size >= 1024
    except OSError:
        return False


def model_installed(kind: str) -> bool:
    """Return true only when the local model's config and required weights are present."""
    root = MODEL_DIRS[kind]
    config_path = root / "config.json"
    try:
        if not config_path.is_file():
            return False
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            return False
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False

    index_path = root / "model.safetensors.index.json"
    if index_path.is_file():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            weight_map = index.get("weight_map")
            if not isinstance(weight_map, dict) or not weight_map:
                return False
            names = list(weight_map.values())
            if any(not isinstance(name, str) or not name or Path(name).name != name for name in names):
                return False
            shards = {root / name for name in names}
            if not all(_model_weight_file_ready(path) for path in shards):
                return False

            # A sharded download may leave all filenames in place but only
            # partially write the last file. Compare the aggregate byte count
            # with the index's declared tensor size when that metadata exists.
            metadata = index.get("metadata")
            expected_size = metadata.get("total_size", 0) if isinstance(metadata, dict) else 0
            try:
                expected_size = int(expected_size or 0)
            except (TypeError, ValueError):
                expected_size = 0
            actual_size = sum(path.stat().st_size for path in shards)
            # SafeTensors headers add bytes beyond tensor payload size, so a
            # complete set should meet or exceed the index's declared tensor
            # payload size. Do not accept a percentage tolerance: it can label
            # a truncated shard as ready when the missing bytes are a small
            # fraction of a large model.
            if expected_size > 0 and actual_size < expected_size:
                return False
            return True
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False

    # Without an index, a sharded naming convention is not safe to accept:
    # a missing index can itself be the result of an interrupted download.
    weights = list(root.glob("*.safetensors"))
    if not weights or any("-of-" in path.name for path in weights):
        return False
    return all(_model_weight_file_ready(path) for path in weights)


@lru_cache(maxsize=1)
@lru_cache(maxsize=1)
def _detected_vram_gb() -> float:
    """Return dedicated GPU memory in GiB where the driver exposes it."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2,
        )
        if result.returncode == 0:
            values = []
            for line in result.stdout.splitlines():
                try:
                    values.append(float(line.strip()))
                except ValueError:
                    pass
            if values:
                return max(values) / 1024.0
    except (OSError, subprocess.SubprocessError):
        pass
    # Non-NVIDIA memory is read from the active backend only; WMI's shared
    # AdapterRAM is intentionally not treated as dedicated VRAM.
    try:
        return max(0.0, float(model_selection_memory_gb()))
    except Exception:
        return 0.0



def best_custom_kind(vram_gb: float | None = None) -> str:
    # Qwen 1.7B CustomVoice is the quality path for 8GB-class GPUs; 0.6B is
    # the compatibility path for 4GB-class GPUs. Detect VRAM automatically
    # when the caller does not provide it.
    if vram_gb is None:
        vram_gb = _detected_vram_gb()
    if vram_gb >= 7.0 and model_installed("custom-1.7b"):
        return "custom-1.7b"
    if model_installed("custom-0.6b"):
        return "custom-0.6b"
    if model_installed("custom-1.7b"):
        return "custom-1.7b"
    return "custom-0.6b"


def best_clone_kind(vram_gb: float | None = None) -> str:
    # Voice cloning uses Qwen Base, not CustomVoice. The 1.7B Base model is
    # the higher-quality path for 8GB-class GPUs; 0.6B is the lighter option.
    if vram_gb is None:
        vram_gb = _detected_vram_gb()
    # Keep the default long-form path compatible with 4 GB and 8 GB GPUs.
    # The 1.7B Base remains selectable explicitly for high-memory systems.
    if vram_gb >= 10.0 and model_installed("base-1.7b"):
        return "base-1.7b"
    if model_installed("base-0.6b"):
        return "base-0.6b"
    if model_installed("base-1.7b"):
        return "base-1.7b"
    return "base-0.6b"


def best_voice_design_kind() -> str:
    # Qwen's official VoiceDesign API is provided by the 1.7B VoiceDesign model.
    return "design-1.7b"


def best_long_form_clone_kind(vram_gb: float | None = None) -> str:
    """Choose a stable Base clone model for reusable VoiceDesign identities.

    8GB-class GPUs get the higher-quality 1.7B Base when it is installed.
    4GB-class GPUs prefer the lighter 0.6B Base to avoid memory pressure.
    """
    if vram_gb is None:
        vram_gb = _detected_vram_gb()
    if vram_gb >= 7.0 and model_installed("base-1.7b"):
        return "base-1.7b"
    if model_installed("base-0.6b"):
        return "base-0.6b"
    if model_installed("base-1.7b"):
        return "base-1.7b"
    return "base-0.6b"



def required_models_for_profile(profile) -> tuple[str, ...]:
    """Return the exact local model kinds required by a saved Qwen voice profile.

    Selection mirrors QwenCharacterProvider: explicit model IDs win; automatic
    CustomVoice/Clone profiles use the same installed-model preference helpers.
    VoiceDesign additionally requires a Base model to preserve identity during
    long-form generation.
    """
    mode = str(getattr(profile, "qwen_mode", "custom") or "custom").casefold()
    requested = str(getattr(profile, "model_id", "auto") or "auto").casefold()
    if mode in {"design", "design-preview"}:
        return (best_voice_design_kind(), best_long_form_clone_kind())
    if mode == "clone":
        kind = requested if requested in {"base-0.6b", "base-1.7b"} else best_clone_kind()
        return (kind,)
    kind = requested if requested in {"custom-0.6b", "custom-1.7b"} else best_custom_kind()
    return (kind,)


def profile_model_readiness(profile) -> tuple[bool, str]:
    """Check model files required by a Qwen profile without importing ML runtimes."""
    required = required_models_for_profile(profile)
    missing = [kind for kind in required if not model_installed(kind)]
    if not missing:
        return True, "Required local Qwen model files are present: " + ", ".join(required) + "."
    labels = [f"{kind} ({MODEL_IDS.get(kind, kind)})" for kind in missing]
    phase = str(getattr(profile, "qwen_mode", "custom") or "custom").casefold()
    action = {
        "design": "Install Qwen VoiceDesign and its required Base model",
        "design-preview": "Install Qwen VoiceDesign and its required Base model",
        "clone": "Install the matching Qwen Base model",
    }.get(phase, "Install the matching Qwen CustomVoice model")
    return False, "Missing or incomplete model files: " + "; ".join(labels) + f". {action} in Models."

def _run(command: list[str], progress=None, timeout: int = 3600) -> None:
    """Run a child command with streaming progress and an enforceable wall-clock timeout.

    Reading stdout directly on the controlling thread can block forever when a
    subprocess stalls without emitting a newline. A daemon reader thread feeds
    a queue so this function can enforce the deadline even during silent stalls.
    """
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
    output: queue.Queue[object] = queue.Queue()
    finished = object()
    deadline = time.monotonic() + max(0.0, float(timeout))

    def drain_stdout() -> None:
        try:
            if process.stdout is not None:
                for line in iter(process.stdout.readline, ""):
                    output.put(line)
        except Exception as exc:
            output.put(exc)
        finally:
            output.put(finished)

    reader = threading.Thread(target=drain_stdout, name="QwenCommandOutput", daemon=True)
    reader.start()

    try:
        stream_finished = False
        while not stream_finished:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                item = output.get(timeout=min(0.2, remaining))
            except queue.Empty:
                continue

            if item is finished:
                stream_finished = True
            elif isinstance(item, BaseException):
                raise item
            elif isinstance(item, str):
                line = item.strip()
                if line and progress:
                    progress(line[-500:])

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, timeout)
        code = process.wait(timeout=remaining)
    except subprocess.TimeoutExpired as exc:
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass
        reader.join(timeout=1)
        raise RuntimeError(
            f"Qwen character runtime command timed out after {timeout} seconds."
        ) from exc
    except Exception:
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass
        reader.join(timeout=1)
        raise
    finally:
        if process.stdout is not None:
            try:
                process.stdout.close()
            except OSError:
                pass

    if code != 0:
        raise RuntimeError(f"Qwen character runtime command failed with exit code {code}.")


_ACTIVE_QWEN_WORKERS: set[int] = set()
_ACTIVE_QWEN_WORKERS_LOCK = threading.RLock()
_GPU_RUNTIME_UPGRADE_LOCK = threading.RLock()


def register_qwen_worker(pid: int | None) -> None:
    if pid:
        with _ACTIVE_QWEN_WORKERS_LOCK:
            _ACTIVE_QWEN_WORKERS.add(int(pid))


def unregister_qwen_worker(pid: int | None) -> None:
    if pid:
        with _ACTIVE_QWEN_WORKERS_LOCK:
            _ACTIVE_QWEN_WORKERS.discard(int(pid))


def _active_qwen_worker_pids() -> list[int]:
    active: list[int] = []
    with _ACTIVE_QWEN_WORKERS_LOCK:
        for pid in list(_ACTIVE_QWEN_WORKERS):
            try:
                os.kill(pid, 0)
                active.append(pid)
            except ProcessLookupError:
                _ACTIVE_QWEN_WORKERS.discard(pid)
            except (PermissionError, OSError):
                active.append(pid)
    return active


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
            progress("Qwen3-TTS local runtime is already installed.")
        return

    python = _install_portable_python(progress)
    python = _create_or_repair_venv(progress)
    selected_backend, installed_torch, installed_torchaudio = _install_runtime_packages(python, progress)

    MARKER.write_text(
        json.dumps(
            {
                "ready": True,
                "bootstrap_version": BOOTSTRAP_VERSION,
                "python": PYTHON_VERSION,
                "qwen_tts": QWEN_TTS_VERSION,
                "torch": installed_torch,
                "torchaudio": installed_torchaudio,
                "tokenizer": TOKENIZER_ID,
                "accelerator": selected_backend,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def ensure_best_runtime_for_gpu(progress=None) -> str | None:
    """Safely replace a CPU-only Qwen venv with the best verified GPU runtime.

    The existing CPU runtime is kept until the GPU venv passes its self-test.
    Upgrades are refused while this app has active Qwen workers, so a running
    audiobook is never interrupted by replacing its Python environment.
    """
    if not runtime_ready():
        return None

    with _GPU_RUNTIME_UPGRADE_LOCK:
        try:
            current = json.loads(MARKER.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        current_backend = str(current.get("accelerator") or "cpu").casefold()
        if current_backend in {"cuda", "rocm", "xpu"}:
            return current_backend

        candidates = gpu_runtime_candidates(refresh=True)
        if not candidates:
            return None

        active = best_accelerator()
        if active.supported and active.backend in {"cuda", "rocm", "xpu"}:
            return active.backend

        active_pids = _active_qwen_worker_pids()
        if active_pids:
            raise RuntimeError(
                "A supported GPU was detected, but the CPU Qwen runtime cannot "
                "be upgraded while another Qwen synthesis worker is running. "
                "Finish or cancel that job, then retry GPU selection."
            )

        backup_venv = RUNTIME_ROOT / "runtime-cpu-backup"
        backup_marker = RUNTIME_ROOT / "runtime.json.cpu-backup"
        if backup_venv.exists():
            shutil.rmtree(backup_venv, ignore_errors=True)
        backup_marker.unlink(missing_ok=True)
        marker_bytes = MARKER.read_bytes()
        if not VENV_ROOT.exists():
            raise RuntimeError("The current Qwen CPU runtime folder is missing; use Models → Repair.")
        VENV_ROOT.replace(backup_venv)
        MARKER.unlink(missing_ok=True)
        try:
            if progress:
                progress(
                    f"Supported GPU detected • upgrading Qwen from CPU to {active.name} "
                    f"({active.backend}) without changing model quality…"
                )
            install_runtime(progress, force_repair=False)
            detail = verify_runtime(progress)
            installed = json.loads(MARKER.read_text(encoding="utf-8"))
            selected_backend = str(installed.get("accelerator") or "cpu").casefold()
            refreshed = best_accelerator()
            if (
                selected_backend not in {"cuda", "rocm", "xpu"}
                or not refreshed.supported
                or refreshed.backend != selected_backend
            ):
                raise RuntimeError(
                    "GPU PyTorch installed but is not active. "
                    f"Installed={selected_backend}; detected={refreshed.backend} "
                    f"({refreshed.name}). {detail[-1200:]}"
                )
            shutil.rmtree(backup_venv, ignore_errors=True)
            backup_marker.unlink(missing_ok=True)
            if progress:
                progress(
                    f"Qwen GPU runtime active • {refreshed.name} • "
                    f"{selected_backend.upper()} • {installed.get('torch', 'PyTorch')}"
                )
            return selected_backend
        except Exception as exc:
            if VENV_ROOT.exists():
                shutil.rmtree(VENV_ROOT, ignore_errors=True)
            if backup_venv.exists():
                backup_venv.replace(VENV_ROOT)
            MARKER.write_bytes(marker_bytes)
            raise RuntimeError(
                "Automatic Qwen GPU activation failed. The previous CPU runtime "
                "was restored intact; no model, profile or audio data was changed. "
                f"Reason: {exc}"
            ) from exc


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
    cache_root = model_cache_root()\n    cache_root.mkdir(parents=True, exist_ok=True)\n    env["HF_HOME"] = str(cache_root)
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
