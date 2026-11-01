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
        found.append(Accelerator("cuda", "cuda:0", fields[0], memory, True,
                                 "NVIDIA CUDA device detected"))

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
                "rocm", "cuda:0", name, 0.0, True,
                "ROCm runtime detected; requires a compatible ROCm PyTorch build",
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
                    memory = float(getattr(props, "total_memory", 0) or 0) / (1024 ** 3)
                except Exception:
                    name, memory = f"Intel XPU {index}", 0.0
                found.append(Accelerator(
                    "xpu", f"xpu:{index}", name, memory, True,
                    "Installed PyTorch build exposes Intel XPU",
                ))
    except Exception:
        pass

    for name, memory in _windows_video_controllers():
        lowered = name.casefold()
        if ("amd" in lowered or "radeon" in lowered) and not any(x.backend == "cuda" for x in found):
            found.append(Accelerator(
                "directml", "directml", name, memory, False,
                "AMD adapter detected, but Qwen3-TTS DirectML transformer compatibility "
                "is not certified. CPU is used until real-device acceptance passes.",
            ))
        elif ("intel" in lowered or "arc" in lowered) and not any(x.backend == "xpu" for x in found):
            found.append(Accelerator(
                "intel-runtime-missing", "cpu", name, memory, False,
                "Intel adapter detected, but no Intel XPU PyTorch runtime is available. "
                "Install a matching Intel XPU PyTorch build to enable acceleration.",
            ))

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
            backend="cpu",
            device="cpu",
            name=f"CPU fallback ({experimental.name})",
            memory_gb=0.0,
            supported=True,
            reason=experimental.reason,
        )
    return Accelerator("cpu", "cpu", "CPU", 0.0, True,
                       "No supported Qwen GPU backend detected")


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
