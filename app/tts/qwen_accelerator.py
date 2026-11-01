from __future__ import annotations

"""Qwen3-TTS accelerator discovery and runtime installation policy."""

import json
import os
from dataclasses import dataclass
from functools import lru_cache
import subprocess
import sys


@dataclass(frozen=True)
class Accelerator:
    backend: str
    device: str
    name: str
    memory_gb: float
    supported: bool
    reason: str


def _run(command: list[str], timeout: float = 4.0) -> str:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if os.name == "nt" else 0,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _windows_host_identity() -> tuple[str, str]:
    """Return Windows OS caption and processor model without treating RAM as VRAM."""
    if os.name != "nt":
        return "", ""
    script = (
        "$os=Get-CimInstance Win32_OperatingSystem; "
        "$cpu=Get-CimInstance Win32_Processor | Select-Object -First 1; "
        "[pscustomobject]@{OSCaption=$os.Caption; CPUName=$cpu.Name} | "
        "ConvertTo-Json -Compress"
    )
    raw = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])
    if not raw:
        return "", ""
    try:
        value = json.loads(raw)
        return str(value.get("OSCaption") or ""), str(value.get("CPUName") or "")
    except (ValueError, TypeError, AttributeError):
        return "", ""


_AMD_WINDOWS_GPU_MODELS = (
    "rx 9070", "rx 9070 xt", "rx 9060 xt", "rx 7900 xtx",
    "ai pro r9700", "pro w7900",
)
_AMD_WINDOWS_APU_MODELS = (
    "ryzen ai max+ 395", "ryzen ai max 390", "ryzen ai max 385",
    "ryzen ai 9 hx 375", "ryzen ai 9 hx 370", "ryzen ai 9 365",
    "ryzen ai 9 hx 475", "ryzen ai 9 hx 470", "ryzen ai 9 465",
)


def is_supported_amd_windows_device(adapter_name: str, cpu_name: str, os_caption: str) -> bool:
    """Match only AMD's published Windows PyTorch/ROCm 7.2.1 hardware list."""
    if "windows 11" not in str(os_caption).casefold():
        return False
    adapter = str(adapter_name).casefold()
    cpu = str(cpu_name).casefold()
    return (
        any(model in adapter for model in _AMD_WINDOWS_GPU_MODELS)
        or any(model in cpu for model in _AMD_WINDOWS_APU_MODELS)
    )


def is_supported_intel_windows_device(adapter_name: str, cpu_name: str, os_caption: str) -> bool:
    """Match Intel Arc A/B GPUs and supported Core Ultra Arc iGPU families."""
    if "windows 11" not in str(os_caption).casefold():
        return False
    adapter = str(adapter_name).casefold()
    cpu = str(cpu_name).casefold()
    if "arc" not in adapter:
        return False
    # Discrete Arc A/B products are validated independently of processor brand.
    if any(model in adapter for model in (
        "arc a", "arc b", "a380", "a580", "a750", "a770",
        "b570", "b580", "b60",
    )):
        return True
    # Integrated Arc graphics are validated on Core Ultra mobile H/V families.
    return "core ultra" in cpu and any(
        token in cpu for token in ("h processor", "v processor", " 1", " 2", " 3")
    )


def _windows_video_controllers() -> list[tuple[str, float]]:
    if os.name != "nt":
        return []
    script = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object -Property Name,AdapterRAM | ConvertTo-Json -Compress"
    )
    raw = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])
    if not raw:
        return []
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            payload = [payload]
        adapters = []
        for item in payload:
            name = str(item.get("Name") or "").strip()
            try:
                memory = max(0, int(item.get("AdapterRAM") or 0)) / (1024 ** 3)
            except (TypeError, ValueError):
                memory = 0.0
            if name:
                adapters.append((name, memory))
        return adapters
    except (ValueError, TypeError):
        return []


@lru_cache(maxsize=1)
def detect_accelerators() -> tuple[Accelerator, ...]:
    """Detect working accelerators and report installed-but-uncertified GPU candidates."""
    found: list[Accelerator] = []
    try:
        import torch
    except Exception:
        torch = None

    if torch is not None:
        if bool(getattr(torch, "cuda", None) and torch.cuda.is_available()):
            try:
                hip = bool(getattr(torch.version, "hip", None))
                name = str(torch.cuda.get_device_name(0))
                memory = float(torch.cuda.get_device_properties(0).total_memory) / (1024 ** 3)
                backend = "rocm" if hip else "cuda"
                reason = "AMD ROCm PyTorch is active" if hip else "NVIDIA CUDA PyTorch is active"
                found.append(Accelerator(backend, "cuda:0", name, memory, True, reason))
            except Exception:
                backend = "rocm" if bool(getattr(torch.version, "hip", None)) else "cuda"
                found.append(Accelerator(
                    backend, "cuda:0", backend.upper(), 0.0, True,
                    "PyTorch reports CUDA-compatible GPU runtime active",
                ))

        xpu = getattr(torch, "xpu", None)
        try:
            if xpu is not None and xpu.is_available():
                for index in range(max(1, int(xpu.device_count()))):
                    try:
                        props = xpu.get_device_properties(index)
                        name = str(getattr(props, "name", f"Intel XPU {index}"))
                        memory = float(getattr(props, "total_memory", 0) or 0) / (1024 ** 3)
                    except Exception:
                        name, memory = f"Intel XPU {index}", 0.0
                    found.append(Accelerator(
                        "xpu", f"xpu:{index}", name, memory, True,
                        "Intel PyTorch XPU runtime is active",
                    ))
        except Exception:
            pass

    if os.name == "nt":
        os_caption, cpu_name = _windows_host_identity()
        for name, memory in _windows_video_controllers():
            lowered = name.casefold()
            if ("amd" in lowered or "radeon" in lowered) and not any(
                item.backend in {"rocm", "cuda"} and item.supported for item in found
            ):
                if is_supported_amd_windows_device(name, cpu_name, os_caption):
                    backend = "rocm-candidate"
                    reason = (
                        "AMD device is listed for ROCm 7.2.1 on Windows 11. "
                        "The app will verify HIP activation after installing the runtime."
                    )
                else:
                    backend = "rocm-unsupported"
                    reason = (
                        "AMD adapter detected but not listed in AMD's supported Windows "
                        "PyTorch/ROCm device matrix. Qwen uses CPU on this device."
                    )
                found.append(Accelerator(backend, "cpu", name, 0.0, False, reason))
            elif ("intel" in lowered or "arc" in lowered) and not any(
                item.backend == "xpu" and item.supported for item in found
            ):
                if is_supported_intel_windows_device(name, cpu_name, os_caption):
                    backend = "xpu-candidate"
                    reason = (
                        "Intel Arc/Core Ultra Arc device is listed for Windows XPU. "
                        "The app will verify torch.xpu activation after installing."
                    )
                else:
                    backend = "xpu-unsupported"
                    reason = (
                        "Intel adapter is not in the supported Windows XPU hardware "
                        "matrix. Qwen uses CPU on this device."
                    )
                found.append(Accelerator(backend, "cpu", name, 0.0, False, reason))

    return tuple(found)


def best_accelerator() -> Accelerator:
    devices = detect_accelerators()
    for backend in ("cuda", "rocm", "xpu"):
        match = next((item for item in devices if item.backend == backend and item.supported), None)
        if match:
            return match
    experimental = next((item for item in devices if item.backend in {"directml", "intel-runtime-missing"}), None)
    if experimental:
        return Accelerator(
            backend=experimental.backend,
            device="cpu",
            name=experimental.name,
            memory_gb=experimental.memory_gb,
            supported=False,
            reason=experimental.reason,
        )
    return Accelerator(
        "cpu", "cpu", "CPU", 0.0, True,
        "No supported Qwen GPU backend detected",
    )


def accelerator_report() -> str:
    devices = detect_accelerators()
    if not devices:
        return "Qwen accelerator: CPU (no supported GPU backend detected)."
    return "Qwen accelerators: " + "; ".join(
        f"{item.name} [{item.backend}, {item.memory_gb:.1f} GiB, "
        f"{'supported' if item.supported else 'not certified'}] — {item.reason}"
        for item in devices
    )


def model_selection_memory_gb() -> float:
    """Memory hint for model selection; does not treat shared system RAM as VRAM."""
    device = best_accelerator()
    if device.backend in {"cuda", "xpu", "rocm"}:
        return device.memory_gb
    return 0.0
