from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import ctypes
import gc
import json
import os
from pathlib import Path
import sys


def _windows_memory_status() -> tuple[int, int, int, int] | None:
    if sys.platform != "win32":
        return None
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]
    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return (
        int(status.ullTotalPhys),
        int(status.ullAvailPhys),
        int(status.ullTotalPageFile),
        int(status.ullAvailPageFile),
    )


def _choose_variant(requested: str, multilingual: bool, device: str) -> str:
    requested = (requested or "auto").lower()
    if multilingual:
        return "base"
    if requested in {"nano", "base", "turbo"}:
        return requested
    # English custom voices can use the much smaller Nano model on
    # resource-constrained Windows systems. This is especially useful on
    # 4 GB GPUs and on machines with a small Windows commit/pagefile limit.
    status = _windows_memory_status()
    if status:
        total_phys, _avail_phys, _total_pagefile, avail_pagefile = status
        if total_phys <= 16 * 1024**3 or avail_pagefile < 8 * 1024**3:
            return "nano"
    if device == "cuda":
        try:
            import torch
            props = torch.cuda.get_device_properties(0)
            if int(props.total_memory) <= 5 * 1024**3:
                return "nano"
        except Exception:
            pass
    if device == "cpu":
        return "nano"
    return "turbo"


def _is_paging_file_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return (
        getattr(exc, "winerror", None) == 1455
        or "os error 1455" in message
        or "winerror 1455" in message
        or "paging file is too small" in message
    )


def _friendly_model_error(exc: BaseException) -> str:
    if _is_paging_file_error(exc):
        status = _windows_memory_status()
        detail = ""
        if status:
            _total_phys, _avail_phys, _total_pagefile, avail_pagefile = status
            detail = (
                f" Available Windows commit/pagefile space: {avail_pagefile / 1024**3:.1f} GB."
            )
        return (
            "Windows virtual memory is too small to load the custom voice model. "
            "Ryu's Audiobook uses a low-memory Chatterbox mode automatically when possible, "
            "but the current Windows commit limit is still insufficient."
            + detail
            + " Set the Windows pagefile to System managed size (or increase it), restart Windows, "
              "and try the custom voice preview again."
        )
    return str(exc)


def _load_model(backend: str, multilingual: bool, variant: str):
    import torch
    from chatterbox.tts import ChatterboxTTS
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    from chatterbox.tts_turbo import ChatterboxTurboTTS

    if backend == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA was requested, but the custom voice runtime cannot access an NVIDIA GPU."
            )
        device = "cuda"
    elif backend == "cpu":
        device = "cpu"
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    selected = _choose_variant(variant, multilingual, device)
    model_class = ChatterboxMultilingualTTS if multilingual else (
        ChatterboxTurboTTS if selected in {"nano", "turbo"} else ChatterboxTTS
    )
    with redirect_stdout(sys.stderr):
        if multilingual:
            model = model_class.from_pretrained(device=device)
        elif selected == "nano":
            model = model_class.from_pretrained(device=device, nano=True)
        else:
            model = model_class.from_pretrained(device=device)
    gc.collect()
    if device == "cuda":
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
    return model, device, selected


def _generate(model, text: str, output: Path, reference: Path, language: str, multilingual: bool,
              exaggeration: float, cfg_weight: float) -> None:
    import torchaudio as ta

    kwargs = {
        "audio_prompt_path": str(reference.resolve()),
        "exaggeration": exaggeration,
        "cfg_weight": cfg_weight,
    }
    if multilingual:
        kwargs["language_id"] = language or "en"
    with redirect_stdout(sys.stderr):
        wav = model.generate(text, **kwargs)
    output.parent.mkdir(parents=True, exist_ok=True)
    ta.save(str(output), wav, model.sr)
    if not output.exists() or output.stat().st_size < 1024:
        raise RuntimeError("Chatterbox did not produce a valid WAV file.")


def server(args) -> int:
    model, device, variant = _load_model(args.backend, args.multilingual, args.variant)
    print(json.dumps({"ready": True, "device": device, "variant": variant}), flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            text = str(request.get("text", "")).strip()
            output = Path(request["output"])
            reference = Path(request["reference"])
            if not text:
                raise RuntimeError("The custom voice text chunk is empty.")
            if not reference.is_file():
                raise RuntimeError(f"Reference voice file was not found: {reference}")
            _generate(
                model,
                text,
                output,
                reference,
                str(request.get("language") or "en"),
                bool(request.get("multilingual")),
                float(request.get("exaggeration", 0.5)),
                float(request.get("cfg_weight", 0.5)),
            )
            print(json.dumps({"ok": True, "output": str(output)}), flush=True)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": _friendly_model_error(exc)}), flush=True)
    return 0


def one_shot(args) -> int:
    text = Path(args.text_file).read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError("The custom voice text chunk is empty.")
    reference = Path(args.reference)
    if not reference.exists():
        raise RuntimeError(f"Reference voice file was not found: {reference}")
    output = Path(args.output)
    model, _device, _variant = _load_model(args.backend, args.multilingual, args.variant)
    _generate(
        model, text, output, reference, args.language or "en", args.multilingual,
        args.exaggeration, args.cfg_weight,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--text-file")
    parser.add_argument("--output")
    parser.add_argument("--reference")
    parser.add_argument("--backend", default="automatic")
    parser.add_argument("--language", default="en")
    parser.add_argument("--multilingual", action="store_true")
    parser.add_argument("--variant", default=os.environ.get("RYU_CHATTERBOX_VARIANT", "auto"))
    parser.add_argument("--exaggeration", type=float, default=0.5)
    parser.add_argument("--cfg-weight", type=float, default=0.5)
    args = parser.parse_args()

    if args.server:
        return server(args)
    return one_shot(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"RYU_CHATTERBOX_ERROR: {_friendly_model_error(exc)}", file=sys.stderr)
        raise
