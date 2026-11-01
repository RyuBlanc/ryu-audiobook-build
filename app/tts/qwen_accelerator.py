from __future__ import annotations

"""Qwen3-TTS accelerator discovery and runtime installation policy."""

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
import subprocess
import sys
import re


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


def windows_host_identity() -> tuple[str, str, str]:
    """Return Windows edition, DisplayVersion and processor model."""
    if os.name != "nt":
        return "", "", ""
    script = (
        "$os=Get-CimInstance Win32_OperatingSystem; "
        "$cpu=Get-CimInstance Win32_Processor | Select-Object -First 1; "
        "$version=Get-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion'; "
        "[pscustomobject]@{OSCaption=$os.Caption; DisplayVersion=$version.DisplayVersion; CPUName=$cpu.Name} | "
        "ConvertTo-Json -Compress"
    )
    raw = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])
    if not raw:
        return "", "", ""
    try:
        value = json.loads(raw)
        return (
            str(value.get("OSCaption") or ""),
            str(value.get("DisplayVersion") or ""),
            str(value.get("CPUName") or ""),
        )
    except (ValueError, TypeError, AttributeError):
        return "", "", ""


def _normalise_device_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


# AMD ROCm 10.1.0 / PyTorch 2.14.0 Windows 11 25H2 device targets.
# gfx1030 remains excluded here because AMD's 10.1 PyTorch Windows wheel
# selector does not publish a gfx1030 10.1.0 wheel.
_AMD_ROCM_101_GPU_TARGETS = (
    ("radeon ai pro r9700s", "gfx1201"),
    ("radeon ai pro r9700", "gfx1201"),
    ("radeon ai pro r9600d", "gfx1201"),
    ("radeon ai pro r9600", "gfx1201"),
    ("radeon rx 9070 xt", "gfx1201"),
    ("radeon rx 9070 gre", "gfx1201"),
    ("radeon rx 9070", "gfx1201"),
    ("radeon rx 9060 xt lp", "gfx1200"),
    ("radeon rx 9060 xt", "gfx1200"),
    ("radeon rx 9060", "gfx1200"),
    ("radeon rx 9050 4gb", "gfx1200"),
    ("radeon rx 9050", "gfx1200"),
    ("radeon pro w7900 dual slot", "gfx1100"),
    ("radeon pro w7900", "gfx1100"),
    ("radeon pro w7800 48gb", "gfx1100"),
    ("radeon pro w7800", "gfx1100"),
    ("radeon rx 7900 xtx", "gfx1100"),
    ("radeon rx 7900 xt", "gfx1100"),
    ("radeon rx 7900 gre", "gfx1100"),
    ("radeon pro w7700", "gfx1101"),
    ("radeon rx 7800 xt", "gfx1101"),
    ("radeon rx 7700 xt", "gfx1101"),
    ("radeon rx 7700", "gfx1101"),
    ("radeon pro v710", "gfx1101"),
    ("radeon rx 7600", "gfx1102"),
)

_AMD_ROCM_101_APU_TARGETS = (
    ("ryzen ai max pro 495", "gfx1151"),
    ("ryzen ai max pro 490", "gfx1151"),
    ("ryzen ai max pro 485", "gfx1151"),
    ("ryzen ai max pro 395", "gfx1151"),
    ("ryzen ai max pro 390", "gfx1151"),
    ("ryzen ai max pro 385", "gfx1151"),
    ("ryzen ai max pro 380", "gfx1151"),
    ("ryzen ai max 395", "gfx1151"),
    ("ryzen ai max 392", "gfx1151"),
    ("ryzen ai max 388", "gfx1151"),
    ("ryzen ai max 390", "gfx1151"),
    ("ryzen ai max 385", "gfx1151"),
    ("ryzen ai 9 hx pro 475", "gfx1150"),
    ("ryzen ai 9 hx pro 470", "gfx1150"),
    ("ryzen ai 9 pro 465", "gfx1150"),
    ("ryzen ai 7 pro 450", "gfx1152"),
    ("ryzen ai 5 pro 440", "gfx1152"),
    ("ryzen ai 5 pro 435", "gfx1153"),
    ("ryzen ai 9 hx 475", "gfx1150"),
    ("ryzen ai 9 hx 470", "gfx1150"),
    ("ryzen ai 9 465", "gfx1150"),
    ("ryzen ai 7 450", "gfx1152"),
    ("ryzen ai 5 435", "gfx1153"),
    ("ryzen ai 5 430", "gfx1153"),
    ("ryzen ai 7 445", "gfx1153"),
    ("ryzen ai 9 hx pro 375", "gfx1150"),
    ("ryzen ai 9 hx pro 370", "gfx1150"),
    ("ryzen ai 7 pro 350", "gfx1152"),
    ("ryzen ai 5 pro 340", "gfx1152"),
    ("ryzen ai 9 hx 375", "gfx1150"),
    ("ryzen ai 9 hx 370", "gfx1150"),
    ("ryzen ai 9 365", "gfx1150"),
    ("ryzen ai 7 350", "gfx1152"),
    ("ryzen ai 7 345", "gfx1152"),
    ("ryzen ai 5 340", "gfx1152"),
    ("ryzen ai 5 330", "gfx1152"),
    ("ryzen 7 pro 250", "gfx1103"),
    ("ryzen 5 pro 230", "gfx1103"),
    ("ryzen 5 pro 220", "gfx1103"),
    ("ryzen 5 pro 215", "gfx1103"),
    ("ryzen 3 pro 210", "gfx1103"),
    ("ryzen 9 270", "gfx1103"),
    ("ryzen 7 260", "gfx1103"),
    ("ryzen 7 250", "gfx1103"),
    ("ryzen 5 240", "gfx1103"),
    ("ryzen 5 230", "gfx1103"),
    ("ryzen 5 220", "gfx1103"),
    ("ryzen 3 210", "gfx1103"),
)

# Exact Windows 11 models in the older ROCm 7.2.1 PyTorch matrix.
_AMD_ROCM_721_GPU_TARGETS = (
    "radeon rx 9070",
    "radeon rx 9070 xt",
    "radeon ai pro r9700",
    "radeon rx 9060 xt",
    "radeon rx 7900 xtx",
    "radeon pro w7900",
    "radeon pro w7900 dual slot",
    "radeon rx 7700",
)
_AMD_ROCM_721_APU_TARGETS = (
    "ryzen ai max 395",
    "ryzen ai max 390",
    "ryzen ai max 385",
    "ryzen ai 9 hx 375",
    "ryzen ai 9 hx 370",
    "ryzen ai 9 365",
    "ryzen ai 9 hx 475",
    "ryzen ai 9 hx 470",
    "ryzen ai 9 465",
)


def amd_windows_runtime_spec(
    adapter_name: str, cpu_name: str, os_caption: str, display_version: str
) -> dict[str, str] | None:
    """Return an official Windows ROCm/PyTorch target for the detected AMD device."""
    if "windows 11" not in str(os_caption).casefold():
        return None
    adapter = _normalise_device_name(adapter_name)
    cpu = _normalise_device_name(cpu_name)

    if str(display_version).strip().casefold() == "25h2":
        arch = next(
            (target for model, target in _AMD_ROCM_101_GPU_TARGETS if model in adapter),
            None,
        )
        if arch is None:
            arch = next(
                (target for model, target in _AMD_ROCM_101_APU_TARGETS if model in cpu),
                None,
            )
        if arch is not None:
            return {
                "rocm": "10.1.0",
                "arch": arch,
                "torch": "2.14.0+rocm10.1.0",
                "torchaudio": "2.11.0.3+rocm10.1.0",
            }
        return None

    legacy_gpu_match = any(model in adapter for model in _AMD_ROCM_721_GPU_TARGETS)
    # Avoid prefix matches for models not listed in the legacy Windows matrix.
    if any(name in adapter for name in (
        "radeon rx 9070 gre", "radeon rx 7700 xt", "radeon rx 9060 xt lp",
        "radeon ai pro r9700s",
    )):
        legacy_gpu_match = False
    legacy_apu_match = (
        any(model in cpu for model in _AMD_ROCM_721_APU_TARGETS)
        and not re.search(r"\bpro\b", cpu)
    )
    if legacy_gpu_match or legacy_apu_match:
        return {
            "rocm": "7.2.1",
            "arch": "",
            "torch": "2.9.1+rocm7.2.1",
            "torchaudio": "2.9.1+rocm7.2.1",
        }
    return None


def is_supported_amd_windows_device(
    adapter_name: str, cpu_name: str, os_caption: str, display_version: str = ""
) -> bool:
    """Match only AMD devices for which an official Windows PyTorch/ROCm route exists."""
    return amd_windows_runtime_spec(
        adapter_name, cpu_name, os_caption, display_version
    ) is not None


def is_supported_intel_windows_device(adapter_name: str, cpu_name: str, os_caption: str) -> bool:
    """Match Intel Arc A/B and supported Core Ultra Arc iGPU families."""
    if "windows 11" not in str(os_caption).casefold():
        return False
    adapter = _normalise_device_name(adapter_name)
    cpu = _normalise_device_name(cpu_name)
    if "arc" not in adapter:
        return False
    if re.search(r"\barc\s+[ab]\d{3}\b", adapter):
        return True
    # Meteor Lake H, Lunar Lake, Arrow Lake H and Panther Lake mobile SKUs.
    # Windows WMI names can include "(R)" and "(TM)" between Core/Ultra tokens.
    return bool(
        re.search(r"\bcore\b.*\bultra\b", cpu)
        and re.search(r"\b\d{3}[hv]\b", cpu)
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


def _nvidia_smi_devices() -> list[tuple[str, float]]:
    """Discover NVIDIA adapters without requiring the Qwen PyTorch runtime."""
    raw = _run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
        timeout=6.0,
    )
    devices: list[tuple[str, float]] = []
    for line in raw.splitlines():
        parts = [part.strip() for part in line.split(",", 1)]
        if not parts or not parts[0]:
            continue
        memory_gb = 0.0
        if len(parts) > 1:
            try:
                memory_gb = max(0.0, float(parts[1])) / 1024.0
            except (TypeError, ValueError):
                memory_gb = 0.0
        devices.append((parts[0], memory_gb))
    return devices


@lru_cache(maxsize=1)
def _detect_accelerators_cached() -> tuple[Accelerator, ...]:
    """Scan all active PyTorch GPU devices and hardware candidates."""
    found: list[Accelerator] = []
    try:
        import torch
    except Exception:
        torch = None

    if torch is not None:
        cuda = getattr(torch, "cuda", None)
        try:
            if cuda is not None and cuda.is_available():
                hip = bool(getattr(torch.version, "hip", None))
                backend = "rocm" if hip else "cuda"
                count = max(1, int(cuda.device_count()))
                for index in range(count):
                    try:
                        props = cuda.get_device_properties(index)
                        name = str(getattr(props, "name", f"{backend.upper()} {index}"))
                        memory = float(getattr(props, "total_memory", 0) or 0) / (1024 ** 3)
                    except Exception:
                        try:
                            name = str(cuda.get_device_name(index))
                        except Exception:
                            name = f"{backend.upper()} {index}"
                        memory = 0.0
                    reason = (
                        "AMD ROCm PyTorch is active"
                        if hip else "NVIDIA CUDA PyTorch is active"
                    )
                    found.append(Accelerator(
                        backend, f"cuda:{index}", name, memory, True, reason
                    ))
        except Exception:
            pass

        xpu = getattr(torch, "xpu", None)
        try:
            if xpu is not None and xpu.is_available():
                count = max(1, int(xpu.device_count()))
                for index in range(count):
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

    # nvidia-smi can see a supported NVIDIA adapter even when the private
    # Qwen environment currently has CPU-only PyTorch. Report that state as a
    # candidate so Auto mode can repair/upgrade the runtime instead of silently
    # running a multi-minute CPU synthesis.
    if not any(item.backend == "cuda" for item in found):
        for name, memory in _nvidia_smi_devices():
            found.append(Accelerator(
                "cuda-candidate", "cpu", name, memory, False,
                "NVIDIA GPU detected, but CUDA PyTorch is not active. "
                "The Qwen runtime must install/verify CUDA before Auto can use it.",
            ))

    if os.name == "nt":
        os_caption, display_version, cpu_name = windows_host_identity()
        for name, _adapter_memory in _windows_video_controllers():
            lowered = name.casefold()
            if ("amd" in lowered or "radeon" in lowered) and not any(
                item.backend == "rocm" and item.supported for item in found
            ):
                spec = amd_windows_runtime_spec(name, cpu_name, os_caption, display_version)
                if spec:
                    backend = "rocm-candidate"
                    reason = (
                        f"AMD device matches official ROCm {spec['rocm']} Windows 11 "
                        f"PyTorch support ({spec['arch'] or 'legacy ROCm 7.2.1'}); "
                        "HIP activation is verified after installation."
                    )
                else:
                    backend = "rocm-unsupported"
                    reason = (
                        "AMD adapter/Windows release is not in the official Windows "
                        "PyTorch device matrix. Qwen uses CPU on this device."
                    )
                found.append(Accelerator(backend, "cpu", name, 0.0, False, reason))
            elif ("intel" in lowered or "arc" in lowered) and not any(
                item.backend == "xpu" and item.supported for item in found
            ):
                if is_supported_intel_windows_device(name, cpu_name, os_caption):
                    backend = "xpu-candidate"
                    reason = (
                        "Intel Arc/Core Ultra Arc device is listed for Windows 11 XPU; "
                        "XPU activation is verified after installing the PyTorch XPU runtime."
                    )
                else:
                    backend = "xpu-unsupported"
                    reason = (
                        "Intel adapter is not in the supported Windows XPU hardware "
                        "matrix. Qwen uses CPU on this device."
                    )
                found.append(Accelerator(backend, "cpu", name, 0.0, False, reason))

    return tuple(found)


def detect_accelerators(refresh: bool = False) -> tuple[Accelerator, ...]:
    """Return cached hardware discovery; refresh=True rescans after runtime changes."""
    if refresh:
        _detect_accelerators_cached.cache_clear()
    return _detect_accelerators_cached()


def gpu_runtime_candidates(refresh: bool = False) -> tuple[Accelerator, ...]:
    """Return GPUs with a known install path but no active PyTorch runtime yet."""
    return tuple(
        item for item in detect_accelerators(refresh=refresh)
        if item.backend in {"cuda-candidate", "rocm-candidate", "xpu-candidate"}
    )


def best_accelerator() -> Accelerator:
    devices = detect_accelerators()
    priority = {"cuda": 0, "rocm": 1, "xpu": 2}
    active = [item for item in devices if item.supported and item.backend in priority]
    if active:
        # Prefer backend family, then the adapter with the most reported VRAM
        # within that family (important on PCs with multiple same-vendor GPUs).
        return min(
            active,
            key=lambda item: (priority[item.backend], -item.memory_gb, item.device),
        )
    candidates = [
        item for item in devices
        if item.backend in {"cuda-candidate", "rocm-candidate", "xpu-candidate"}
    ]
    if candidates:
        candidate_priority = {
            "cuda-candidate": 0, "rocm-candidate": 1, "xpu-candidate": 2
        }
        return min(
            candidates,
            key=lambda item: (
                candidate_priority[item.backend], -item.memory_gb, item.name
            ),
        )
    experimental = next(
        (item for item in devices if item.backend in {"directml", "intel-runtime-missing"}),
        None,
    )
    if experimental:
        return Accelerator(
            backend=experimental.backend,
            device="cpu",
            name=experimental.name,
            memory_gb=experimental.memory_gb,
            supported=False,
            reason=experimental.reason,
        )
    unsupported = next(
        (item for item in devices if item.backend.endswith("-unsupported")),
        None,
    )
    if unsupported:
        return Accelerator(
            backend=unsupported.backend,
            device="cpu",
            name=unsupported.name,
            memory_gb=0.0,
            supported=False,
            reason=unsupported.reason,
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
