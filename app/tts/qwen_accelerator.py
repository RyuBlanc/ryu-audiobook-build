from __future__ import annotations

"""Qwen3-TTS accelerator discovery and runtime installation policy.

Supported auto paths:
- NVIDIA CUDA: official PyTorch CUDA wheels on Windows/Linux.
- AMD ROCm: only on Linux, where official ROCm PyTorch wheels are supported.
- Intel XPU: only when an Intel XPU-enabled PyTorch build is already installed.
- Windows AMD/Intel: DirectML is reported as experimental/unavailable for Qwen
  transformer inference until the Qwen3-TTS operator stack passes real-device
  acceptance. We do not install torch-directml alongside arbitrary CUDA/CPU
  wheels because that combination is not a validated production runtime.
"""

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


def _windows_video_controllers() -> list[tuple[str, float]]:
    """Return visible Windows display adapters and dedicated memory in GiB."""
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
        import json
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
    found: list[Accelerator] = []

    nvidia = _run([
        "nvidia-smi", "--query-gpu=name,memory.total",
        "--format=csv,noheader,nounits",
    ])
    for line in nvidia.splitlines():
        fields = [part.strip() for part in line.split(",")]
        if not fields:
            continue
        try:
            memory = float(fields[1]) / 1024.0 if len(fields) > 1 else 0.0
        except ValueError:
            memory = 0.0
        found.append(Accelerator(
            backend="cuda", device="cuda:0", name=fields[0],
            memory_gb=memory, supported=True,
            reason="NVIDIA CUDA device detected",
        ))

    if sys.platform.startswith("linux"):
        rocm = _run(["rocminfo"], timeout=8.0)
        if rocm:
            names = [
                line.split(":", 1)[-1].strip()
                for line in rocm.splitlines()
                if "Marketing Name:" in line or "Name:" in line
            ]
            name = next((v for v in names if v), "AMD ROCm device")
            found.append(Accelerator(
                backend="rocm", device="cuda:0", name=name,
                memory_gb=0.0, supported=True,
                reason="ROCm runtime detected; PyTorch ROCm wheel still required",
            ))

    try:
        import torch
        xpu = getattr(torch, "xpu", None)
        if xpu is not None and bool(xpu.is_available()):
            count = int(xpu.device_count())
            for index in range(max(1, count)):
                try:
                    props = xpu.get_device_properties(index)
                    name = str(getattr(props, "name", f"Intel XPU {index}"))
                    memory = float(getattr(props, " total_memory", 0) or getattr(props, "total_memory", 0)) / (1024 ** 3)
                except Exception:
                    name, memory = f"Intel XPU {index}", 0.0
                found.append(Accelerator(
                    backend="xpu", device=f"xpu:{index}", name=name,
                    memory_gb=memory, supported=True,
                    reason="Installed PyTorch build exposes Intel XPU",
                ))
    except Exception:
        pass

    adapters = _windows_video_controllers()
    for name, memory in adapters:
        lowered = name.casefold()
        if "amd" in lowered or "radeon" in lowered:
            backend = "directml"
            supported = False
            reason = (
                "AMD display adapter detected. DirectML is not enabled for "
                "Qwen3-TTS until transformer operator compatibility is verified."
            )
        elif "intel" in lowered or "arc" in lowered:
            backend = "directml"
            supported = False
            reason = (
                "Intel display adapter detected. Install a validated Intel XPU "
                "PyTorch build for acceleration; Windows DirectML Qwen execution "
                "is not yet certified."
            )
        else:
            continue
        if not any(item.backend == "cuda" for item in found):
            found.append(Accelerator(
                backend=backend, device="directml", name=name,
                memory_gb=memory, supported=supported, reason=reason,
            ))

    return tuple(found)


def best_accelerator() -> Accelerator:
    devices = detect_accelerators()
    for backend in ("cuda", "rocm", "xpu"):
        match = next((item for item in devices if item.backend == backend and item.supported), None)
        if match:
            return match
    experimental = next((item for item in devices if item.backend == "directml"), None)
    if experimental:
        return experimental
    return Accelerator(
        backend="cpu", device="cpu", name="CPU", memory_gb=0.0,
        supported=True, reason="No supported Qwen GPU backend detected",
    )


def accelerator_report() -> str:
    devices = detect_accelerators()
    if not devices:
        return "Qwen accelerator: CPU (no supported GPU backend detected)."
    return "Qwen accelerators: " + "; ".join(
        f"{item.name} [{item.backend}, {item.memory_gb:.1f} GiB, "
        f"{'supported' if item.supported else 'not certified'}]"
        for item in devices
    )


def model_selection_memory_gb() -> float:
    """Memory hint for model size selection; never mistakes iGPU shared RAM as VRAM."""
    device = best_accelerator()
    if device.backend in {"cuda", "xpu", "rocm"}:
        return device.memory_gb
    return 0.0
