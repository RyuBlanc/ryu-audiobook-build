from __future__ import annotations

from dataclasses import dataclass
import platform
import shutil
import subprocess

@dataclass(frozen=True)
class BackendInfo:
    name: str
    device: str
    available: bool
    memory_mb: int | None = None

@dataclass(frozen=True)
class HardwareProfile:
    cpu: str
    architecture: str
    backends: tuple[BackendInfo, ...]
    recommended: str

def _nvidia() -> BackendInfo:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return BackendInfo("NVIDIA CUDA", "NVIDIA GPU", False)
    try:
        r = subprocess.run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5, check=True)
        name, memory = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",", 1)]
        return BackendInfo("NVIDIA CUDA", name, True, int(float(memory)))
    except Exception:
        return BackendInfo("NVIDIA CUDA", "NVIDIA GPU", False)

def detect_hardware() -> HardwareProfile:
    system = platform.system()
    arch = platform.machine()
    backends = [_nvidia(), BackendInfo("DirectML", "Windows GPU", system == "Windows"), BackendInfo("CPU", platform.processor() or arch, True)]
    available = [b for b in backends if b.available]
    recommended = "CPU"
    nvidia = next((b for b in available if b.name == "NVIDIA CUDA"), None)
    directml = next((b for b in available if b.name == "DirectML"), None)
    if nvidia:
        recommended = "NVIDIA CUDA"
    elif directml:
        recommended = "DirectML"
    return HardwareProfile(platform.processor() or arch, arch, tuple(backends), recommended)
