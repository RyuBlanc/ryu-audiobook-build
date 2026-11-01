from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class HardwareInfo:
    cpu: str
    gpu_name: str | None
    vram_mb: int | None
    nvidia_available: bool


def detect_hardware() -> HardwareInfo:
    gpu_name = None
    vram_mb = None
    nvidia_available = False

    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            result = subprocess.run(
                [nvidia_smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            first = result.stdout.strip().splitlines()[0]
            name, memory = [part.strip() for part in first.split(",", 1)]
            gpu_name = name
            vram_mb = int(float(memory))
            nvidia_available = True
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            pass

    import platform
    return HardwareInfo(
        cpu=platform.processor() or platform.machine(),
        gpu_name=gpu_name,
        vram_mb=vram_mb,
        nvidia_available=nvidia_available,
    )


def recommended_mode(info: HardwareInfo) -> str:
    """Return a conservative initial mode; later TTS engines can refine this."""
    if not info.nvidia_available:
        return "CPU"
    if info.vram_mb is not None and info.vram_mb >= 7000:
        return "GPU — Quality"
    if info.vram_mb is not None and info.vram_mb >= 3500:
        return "GPU — Compatible"
    return "CPU"
