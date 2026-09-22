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
    validated: bool = False
    reason: str = ""


@dataclass(frozen=True)
class HardwareProfile:
    cpu: str
    architecture: str
    backends: tuple[BackendInfo, ...]
    recommended: str


def _nvidia() -> BackendInfo:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return BackendInfo("NVIDIA CUDA", "NVIDIA GPU", False, reason="nvidia-smi not found")
    try:
        r = subprocess.run(
            [smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True
        )
        name, memory = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",", 1)]
        return BackendInfo(
            "NVIDIA CUDA", name, True, int(float(memory)),
            validated=False,
            reason="Hardware detected; TTS runtime still needs validation",
        )
    except Exception as exc:
        return BackendInfo("NVIDIA CUDA", "NVIDIA GPU", False, reason=str(exc))


def _directml() -> BackendInfo:
    if platform.system() != "Windows":
        return BackendInfo("DirectML", "Windows GPU", False, reason="Windows only")
    try:
        import onnxruntime  # type: ignore
        providers = onnxruntime.get_available_providers()
        ok = "DmlExecutionProvider" in providers
        return BackendInfo(
            "DirectML", "Windows GPU", ok,
            validated=False,
            reason="ONNX Runtime DirectML provider available" if ok else "DirectML provider unavailable",
        )
    except ImportError:
        return BackendInfo("DirectML", "Windows GPU", False, reason="onnxruntime not installed")


def detect_hardware() -> HardwareProfile:
    system = platform.system()
    arch = platform.machine()
    backends = [
        _nvidia(),
        _directml(),
        BackendInfo("CPU", platform.processor() or arch, True, validated=True, reason="Universal fallback"),
    ]

    # Recommendation is deliberately conservative: a detected GPU is not
    # treated as validated TTS acceleration until a model benchmark succeeds.
    recommended = "CPU"
    if any(b.available and b.name == "NVIDIA CUDA" for b in backends):
        recommended = "NVIDIA CUDA"
    elif any(b.available and b.name == "DirectML" for b in backends):
        recommended = "DirectML"

    return HardwareProfile(
        platform.processor() or arch,
        arch,
        tuple(backends),
        recommended,
    )
