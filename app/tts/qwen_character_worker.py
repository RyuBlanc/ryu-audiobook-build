from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from pathlib import Path
import gc
import os
import hashlib
import json
import sys
import time

# This worker is launched as a standalone Python script by the packaged
# Windows application. In that mode Python starts with app/tts on sys.path,
# not the PyInstaller _internal root, so explicitly add the application root
# before importing sibling application modules.
_APPLICATION_ROOT = Path(__file__).resolve().parents[2]
if str(_APPLICATION_ROOT) not in sys.path:
    sys.path.insert(0, str(_APPLICATION_ROOT))

from app.tts.expression import (
    DEFAULT_VOICE_DESIGN_ANCHOR_TEXT,
    EXPRESSION_STYLES,
    classify_expression,
    expression_instruction,
    expression_temperature,
    reference_style,
    voice_design_anchor_instruction,
)
from app.tts.qwen_accelerator import automatic_accelerator, best_accelerator

EXPRESSION_BANK_VERSION = "v8-emotion-range-anchor"

# The Base model locks speaker identity from one acoustic reference, but does
# not expose VoiceDesign's per-line natural-language instruction channel.
# Emotion changes therefore come from sentence-aware chunking, punctuation,
# pause design and controlled sampling variation, never a second voice anchor.
# Use one canonical acoustic reference per saved profile. Generating different
# VoiceDesign samples independently for each emotion can subtly change timbre
# or even gender presentation; emotion boundaries and sampling variation must
# not replace the saved character identity.
ANCHOR_STYLES = ("neutral",)
ANCHOR_TEXTS = {"neutral": DEFAULT_VOICE_DESIGN_ANCHOR_TEXT}


MODEL_IDS = {
    "custom-0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    "custom-1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "design-1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "base-0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "base-1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
}


_WORKER_STARTED_AT = time.monotonic()
_WORKER_DIAGNOSTIC_PREFIX = "[RYU_QWEN_WORKER] "


def _worker_diagnostic(event: str, **details) -> None:
    """Write one structured, flushed startup event to the worker stderr log."""
    payload = {
        "event": str(event),
        "pid": os.getpid(),
        "elapsed_seconds": round(max(0.0, time.monotonic() - _WORKER_STARTED_AT), 3),
        **details,
    }
    try:
        print(
            _WORKER_DIAGNOSTIC_PREFIX + json.dumps(payload, ensure_ascii=True, default=str),
            file=sys.stderr,
            flush=True,
        )
    except Exception:
        # Diagnostics must never make synthesis fail.
        pass


def _model_weight_bytes(model_path: Path) -> int:
    weight_suffixes = {".safetensors", ".bin", ".pt", ".pth"}
    total = 0
    try:
        for path in model_path.rglob("*"):
            if path.is_file() and path.suffix.casefold() in weight_suffixes:
                total += path.stat().st_size
    except OSError:
        return 0
    return total


def _preflight_device_memory(torch, device: str, model_path: Path, low_memory: bool) -> None:
    if not (str(device).startswith("cuda") or str(device).startswith("xpu")):
        return
    try:
        if str(device).startswith("cuda"):
            try:
                free_bytes, total_bytes = torch.cuda.mem_get_info(device)
            except TypeError:
                free_bytes, total_bytes = torch.cuda.mem_get_info()
        else:
            mem_get_info = getattr(torch.xpu, "mem_get_info", None)
            if not callable(mem_get_info):
                return
            try:
                free_bytes, total_bytes = mem_get_info(0)
            except TypeError:
                free_bytes, total_bytes = mem_get_info()
    except Exception:
        return
    weight_bytes = _model_weight_bytes(model_path)
    if weight_bytes <= 0:
        return
    # Low-memory loading reduces host-side pressure, not the model's GPU weight footprint.
    reserve_factor = 1.30
    required_bytes = int(weight_bytes * reserve_factor)
    if int(free_bytes) < required_bytes:
        raise RuntimeError(
            f"{device} out of memory: Qwen model weights require about "
            f"{weight_bytes / (1024 ** 3):.2f} GB plus a {int((reserve_factor - 1) * 100)}% "
            f"runtime reserve, but only {int(free_bytes) / (1024 ** 3):.2f} GB is free. "
            "The same selected model will be retried on CPU."
        )


def _load_model(kind: str, backend: str, root: Path, low_memory: bool = False):
    _worker_diagnostic(
        "model_load_begin",
        model_kind=kind,
        requested_backend=backend,
        low_memory=bool(low_memory),
    )
    import_started = time.monotonic()
    try:
        import torch
    except Exception as exc:
        _worker_diagnostic(
            "torch_import_failed",
            model_kind=kind,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise
    _worker_diagnostic(
        "torch_import_complete",
        model_kind=kind,
        elapsed_seconds=round(time.monotonic() - import_started, 3),
        torch_version=str(getattr(torch, "__version__", "unknown")),
    )

    qwen_import_started = time.monotonic()
    try:
        from qwen_tts import Qwen3TTSModel
    except Exception as exc:
        _worker_diagnostic(
            "qwen_tts_import_failed",
            model_kind=kind,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise
    _worker_diagnostic(
        "qwen_tts_import_complete",
        model_kind=kind,
        elapsed_seconds=round(time.monotonic() - qwen_import_started, 3),
    )

    if kind not in MODEL_IDS:
        raise RuntimeError(f"Unknown Qwen model kind: {kind}")
    model_path = root / kind
    if not model_path.exists():
        raise RuntimeError(f"Qwen model is not installed: {MODEL_IDS[kind]}")

    selected = best_accelerator()
    requested = (backend or "automatic").casefold()
    if requested == "cpu":
        device = "cpu"
    elif requested in {"automatic", "auto"}:
        selected, selection_reason = automatic_accelerator(kind)
        device = selected.device if selected.supported else "cpu"
        print(json.dumps({"progress": selection_reason}), flush=True)
    elif requested == "cuda" and torch.cuda.is_available() and not getattr(torch.version, "hip", None):
        device = "cuda:0"
    elif requested == "rocm" and torch.cuda.is_available() and getattr(torch.version, "hip", None):
        device = "cuda:0"
    elif requested == "xpu" and getattr(torch, "xpu", None) is not None and torch.xpu.is_available():
        device = "xpu:0"
    else:
        raise RuntimeError(
            f"Requested Qwen backend '{requested}' is unavailable or not certified. "
            f"Detected: {selected.backend} ({selected.name}). {selected.reason}"
        )

    if low_memory and device == "cpu":
        try:
            torch.set_num_threads(max(1, min(4, (os.cpu_count() or 4) // 2)))
        except Exception:
            pass
    gc.collect()
    if device.startswith("cuda"):
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
    elif device.startswith("xpu"):
        try:
            torch.xpu.empty_cache()
        except Exception:
            pass
    _preflight_device_memory(torch, device, model_path, low_memory)
    if device.startswith("cuda"):
        dtype = _inference_dtype(torch, device)
    elif device.startswith("xpu"):
        dtype = _xpu_inference_dtype(torch, device)
    else:
        dtype = torch.float32
    if device.startswith("cuda"):
        try:
            torch.set_float32_matmul_precision("high")
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
        except Exception:
            pass
    kwargs = {
        "device_map": device,
        "dtype": dtype,
        "attn_implementation": "sdpa",
    }
    if low_memory:
        kwargs["low_cpu_mem_usage"] = True
    weight_bytes = _model_weight_bytes(model_path)
    model_load_started = time.monotonic()
    _worker_diagnostic(
        "model_weights_load_begin",
        model_kind=kind,
        requested_backend=backend,
        selected_device=device,
        weight_bytes=weight_bytes,
        low_memory=bool(low_memory),
        dtype=str(dtype),
    )
    try:
        with redirect_stdout(sys.stderr):
            try:
                model = Qwen3TTSModel.from_pretrained(str(model_path), **kwargs)
            except TypeError as exc:
                if low_memory and "low_cpu_mem_usage" in str(exc):
                    kwargs.pop("low_cpu_mem_usage", None)
                    print(json.dumps({
                        "progress": (
                            "This Qwen runtime wrapper does not expose low_cpu_mem_usage; "
                            "continuing with single-job, CPU-thread and accelerator-memory safeguards."
                        )
                    }), flush=True)
                    model = Qwen3TTSModel.from_pretrained(str(model_path), **kwargs)
                else:
                    raise
    except Exception as exc:
        _worker_diagnostic(
            "model_weights_load_failed",
            model_kind=kind,
            selected_device=device,
            elapsed_seconds=round(time.monotonic() - model_load_started, 3),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise
    _worker_diagnostic(
        "model_weights_load_complete",
        model_kind=kind,
        selected_device=device,
        elapsed_seconds=round(time.monotonic() - model_load_started, 3),
    )
    gc.collect()
    if device.startswith("cuda"):
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
    elif device.startswith("xpu"):
        try:
            torch.xpu.empty_cache()
        except Exception:
            pass
    return model, device


def _inference_dtype(torch, device: str):
    """Choose a safe CUDA/ROCm inference dtype for the active device."""
    if not str(device).startswith("cuda"):
        return torch.float32
    try:
        return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    except Exception:
        return torch.float16


def _xpu_inference_dtype(torch, device: str):
    """Use BF16 on supported Intel XPU devices, otherwise FP16."""
    try:
        return torch.bfloat16 if torch.xpu.is_bf16_supported() else torch.float16
    except Exception:
        return torch.float16


def _is_cuda_oom(exc: BaseException) -> bool:
    message = str(exc).casefold()
    return ("out of memory" in message or "outofmemory" in message) and any(
        token in message for token in ("cuda", "cublas", "hip", "rocm", "xpu")
    )


def _is_accelerator_runtime_failure(exc: BaseException) -> bool:
    """Recognize device initialization/driver/kernel failures, not model/data errors."""
    message = f"{type(exc).__name__}: {exc}".casefold()
    accelerators = ("cuda", "cublas", "cudnn", "hip", "rocm", "xpu", "sycl", "oneapi", "gpu")
    failure_markers = (
        "out of memory", "outofmemory", "error", "failed", "failure",
        "initializ", "driver", "device-side", "no kernel", "invalid device",
        "not available", "not supported", "launch",
    )
    return any(token in message for token in accelerators) and any(
        token in message for token in failure_markers
    )


def _load_model_with_fallback(
    kind: str,
    backend: str,
    root: Path,
    low_memory: bool = False,
    *,
    progress=None,
    allow_cpu_fallback: bool = True,
):
    """Load one exact model; Automatic may retry device-runtime failures on CPU."""
    requested_backend = str(backend or "automatic").strip().casefold()
    try:
        return _load_model(kind, backend, root, low_memory=low_memory)
    except Exception as accelerator_error:
        # Explicit GPU choices are promises to use that device, not permission
        # to silently deliver a much slower CPU result.
        automatic = requested_backend in {"automatic", "auto"}
        if (
            not allow_cpu_fallback
            or not automatic
            or not _is_accelerator_runtime_failure(accelerator_error)
        ):
            raise
        message = (
            f"Automatic accelerator initialization failed for {kind}; "
            "retrying the same selected model on CPU without changing voice identity. "
            f"Device error: {accelerator_error}"
        )
        if callable(progress):
            progress(message)
        try:
            return _load_model(kind, "cpu", root, low_memory=low_memory)
        except Exception as cpu_error:
            raise RuntimeError(
                f"Automatic accelerator loading failed for {kind}, and its CPU fallback "
                f"also failed. Accelerator error: {accelerator_error}. CPU error: {cpu_error}"
            ) from cpu_error


def _actual_backend(device: str) -> str:
    selected = str(device or "").casefold()
    if selected.startswith("xpu"):
        return "xpu"
    if selected.startswith("cuda"):
        try:
            import torch
            return "rocm" if getattr(torch.version, "hip", None) else "cuda"
        except Exception:
            return "cuda"
    if selected == "cpu":
        return "cpu"
    return "other"


def _voice_design_instruct(request: dict, style: str | None = None) -> str:
    base = str(request.get("instruct") or "").strip()
    selected = style or classify_expression(str(request.get("text") or ""))
    return expression_instruction(base, selected)
def _recommended_max_new_tokens(text: str | None) -> int:
    chars = max(1, len(str(text or "")))
    estimated = int(chars * 1.10)
    return max(96, min(2048, estimated))

def _generation_kwargs(request: dict) -> dict:
    defaults = {
        "do_sample": True,
        "top_k": 50,
        "top_p": 1.0,
        "temperature": 0.9,
        "repetition_penalty": 1.05,
        "subtalker_dosample": True,
        "subtalker_top_k": 50,
        "subtalker_top_p": 1.0,
        "subtalker_temperature": 0.9,
    }
    text_value = request.get("text") or ""
    max_new_tokens = request.get("max_new_tokens")
    if max_new_tokens is None:
        max_new_tokens = _recommended_max_new_tokens(str(text_value))
    return {
        "do_sample": bool(request.get("do_sample", defaults["do_sample"])),
        "top_k": int(request.get("top_k", defaults["top_k"])),
        "top_p": float(request.get("top_p", defaults["top_p"])),
        "temperature": float(request.get("temperature", defaults["temperature"])),
        "repetition_penalty": float(request.get("repetition_penalty", defaults["repetition_penalty"])),
        "subtalker_dosample": bool(request.get("subtalker_dosample", defaults["subtalker_dosample"])),
        "subtalker_top_k": int(request.get("subtalker_top_k", defaults["subtalker_top_k"])),
        "subtalker_top_p": float(request.get("subtalker_top_p", defaults["subtalker_top_p"])),
        "subtalker_temperature": float(request.get("subtalker_temperature", defaults["subtalker_temperature"])),
        "max_new_tokens": int(max_new_tokens),
    }


def _set_seed(seed):
    if seed is None:
        return
    import torch
    seed = int(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        try:
            torch.cuda.manual_seed_all(seed)
        except Exception:
            pass


def _default_anchor_text(language: str) -> str:
    key = (language or "English").casefold()
    if key.startswith("japanese"):
        return "こんにちは。これは声のテストです。落ち着いて、自然に、はっきりと話します。"
    if key.startswith("korean"):
        return "안녕하세요. 이것은 자연스러운 목소리 테스트입니다. 차분하고 또렷하게 말합니다."
    if key.startswith("chinese"):
        return "你好。这是一段自然的声音测试。我会用清晰、稳定、富有表现力的方式说话。"
    return (
        "Hello. This is a short voice identity sample for Ryu's Audiobook. "
        "The character speaks clearly, naturally, and with a steady identity from one sentence to the next."
    )


def _anchor_path(root: Path, request: dict, style: str = "neutral") -> Path:
    explicit = str(request.get("anchor_path") or "").strip()
    if explicit and style == "neutral":
        return Path(explicit)
    identity = "|".join(
        [
            EXPRESSION_BANK_VERSION,
            str(request.get("speaker") or request.get("voice_id") or "voice"),
            str(request.get("language") or "English"),
            str(request.get("instruct") or ""),
            str(request.get("seed") or ""),
            str(request.get("anchor_text") or ""),
            str(request.get("profile_id") or ""),
            style,
        ]
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return root / "voice_anchors" / f"qwen-design-{style}-{digest}.wav"
def _generate_custom(model, request: dict, output: Path) -> None:
    import soundfile as sf

    speaker = str(request.get("speaker") or "").strip()
    if not speaker:
        raise RuntimeError("A Qwen CustomVoice speaker is required.")
    _set_seed(request.get("seed"))
    wavs, sr = model.generate_custom_voice(
        text=str(request.get("text") or ""),
        language=str(request.get("language") or "English"),
        speaker=speaker,
        instruct=str(request.get("instruct") or "").strip(),
        **_generation_kwargs(request),
    )
    if not wavs:
        raise RuntimeError("Qwen CustomVoice did not return audio.")
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), wavs[0], sr)


def _generate_design(model, request: dict, output: Path) -> None:
    """Generate narration with the same VoiceDesign engine used by the UI preview."""
    import soundfile as sf

    _set_seed(request.get("seed"))
    wavs, sr = model.generate_voice_design(
        text=str(request.get("text") or ""),
        language=str(request.get("language") or "English"),
        instruct=_voice_design_instruct(request),
        **_generation_kwargs(request),
    )
    if not wavs:
        raise RuntimeError("Qwen VoiceDesign did not return narration audio.")
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), wavs[0], sr)

def _generate_design_preview(model, request: dict, output: Path) -> None:
    import soundfile as sf

    _set_seed(request.get("seed"))
    wavs, sr = model.generate_voice_design(
        text=str(request.get("text") or ""),
        language=str(request.get("language") or "English"),
        instruct=_voice_design_instruct(request),
        **_generation_kwargs(
            {
                **request,
                "max_new_tokens": min(
                    _recommended_max_new_tokens(str(request.get("text") or "")),
                    1024,
                ),
            }
        ),
    )
    if not wavs:
        raise RuntimeError("Qwen VoiceDesign did not return preview audio.")
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), wavs[0], sr)


def _generate_design_anchor(model, request: dict, anchor: Path) -> str:
    import soundfile as sf

    language = str(request.get("language") or "English")
    anchor_text = (
        str(request.get("anchor_text") or "").strip()
        or "Hello. This is a short, natural voice sample. I speak clearly and comfortably."
    )
    _set_seed(request.get("seed"))
    wavs, sr = model.generate_voice_design(
        text=anchor_text,
        language=language,
        instruct=_voice_design_instruct(request),
        **_generation_kwargs(
            {
                **request,
                "max_new_tokens": min(int(request.get("max_new_tokens", 768)), 768),
            }
        ),
    )
    if not wavs:
        raise RuntimeError("Qwen VoiceDesign did not return a reusable voice anchor.")
    anchor.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(anchor), wavs[0], sr)
    return anchor_text


def _expression_anchor_text(request: dict, style: str) -> str:
    # An explicitly supplied neutral reference may have a user-provided exact
    # transcript; never pair it with a guessed transcript.
    if style == "neutral":
        requested = str(request.get("anchor_text") or "").strip()
        if requested:
            return requested
    return ANCHOR_TEXTS.get(style, ANCHOR_TEXTS["neutral"])


def _create_expression_anchors(model, request: dict, root: Path) -> dict[str, Path]:
    """Build/reuse a small expressive reference bank for one stable persona.

    Anchor creation happens in the Qwen worker, not the Qt thread. The bank is
    content-addressed and versioned, so a voice-description/pipeline change
    cannot silently reuse references generated by older rules.
    """
    import soundfile as sf

    language = str(request.get("language") or "English")
    paths = {style: _anchor_path(root, request, style) for style in ANCHOR_STYLES}
    missing = [
        style for style, path in paths.items()
        if not path.exists() or path.stat().st_size < 1024
    ]
    if not missing:
        return paths

    explicit_anchor = str(request.get("anchor_path") or "").strip()
    if explicit_anchor and "neutral" in missing:
        raise RuntimeError(
            "The selected saved voice anchor is missing. Re-select or rebuild the voice profile."
        )

    for ordinal, style in enumerate(missing, start=1):
        path = paths[style]
        anchor_text = _expression_anchor_text(request, style)
        # A slightly more expressive reference helps the locked Base voice
        # reproduce a natural range later without changing the chosen identity.
        temperature = 0.88
        print(
            json.dumps({
                "progress": (
                    f"Building the saved character identity • {ordinal}/{len(missing)} "
                    f"• first use for this profile"
                )
            }),
            flush=True,
        )
        _set_seed(request.get("seed"))
        anchor_request = {
            **request,
            "text": anchor_text,
            "max_new_tokens": 384,
            "temperature": temperature,
            "subtalker_temperature": temperature,
        }
        base_description = str(request.get("instruct") or "")
        instruct = (
            voice_design_anchor_instruction(base_description)
            if style == "neutral"
            else expression_instruction(base_description, style)
        )
        wavs, sr = model.generate_voice_design(
            text=anchor_text,
            language=language,
            instruct=instruct,
            **_generation_kwargs(anchor_request),
        )
        if not wavs:
            raise RuntimeError(
                f"Qwen VoiceDesign did not return the '{style}' character reference."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), wavs[0], sr)
        if not path.exists() or path.stat().st_size < 1024:
            raise RuntimeError(f"Qwen generated an invalid '{style}' character reference.")

    return paths


def _prepare_design_clone(model, request: dict, args):
    import torch

    root = Path(args.models_root).resolve()
    paths = _create_expression_anchors(model, request, root)
    print(json.dumps({"progress": "Expression references ready • loading Base clone engine…"}), flush=True)
    del model
    gc.collect()
    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass

    requested_clone_kind = args.clone_kind
    clone_model, clone_device = _load_model_with_fallback(
        requested_clone_kind,
        args.backend,
        root,
        low_memory=args.low_memory,
        progress=lambda message: print(json.dumps({"progress": message}), flush=True),
    )

    explicit_anchor = bool(str(request.get("anchor_path") or "").strip())
    prompts = {}
    for style, path in paths.items():
        transcript = _expression_anchor_text(request, style)
        use_xvector_only = explicit_anchor and style == "neutral" and not str(
            request.get("anchor_text") or ""
        ).strip()
        prompts[style] = clone_model.create_voice_clone_prompt(
            ref_audio=str(path),
            ref_text=None if use_xvector_only else transcript,
            x_vector_only_mode=use_xvector_only,
        )
    return clone_model, clone_device, prompts, paths


def _generate_design_locked(model, prompts, request: dict, output: Path) -> None:
    import soundfile as sf

    style = classify_expression(str(request.get("text") or ""))
    prompt = prompts.get(reference_style(style)) or prompts.get("neutral")
    if prompt is None:
        raise RuntimeError("The canonical Qwen voice identity is not available.")
    temperature = expression_temperature(style)
    request = {
        **request,
        "temperature": temperature,
        "subtalker_temperature": temperature,
        "expression_style": style,
    }
    _set_seed(request.get("seed"))
    wavs, sr = model.generate_voice_clone(
        text=str(request.get("text") or ""),
        language=str(request.get("language") or "English"),
        voice_clone_prompt=prompt,
        **_generation_kwargs(request),
    )
    if not wavs:
        raise RuntimeError("Qwen canonical VoiceDesign/Base generation returned no audio.")
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), wavs[0], sr)


def _generate_clone(model, request: dict, output: Path) -> None:
    import soundfile as sf

    ref_audio = Path(str(request.get("reference") or ""))
    if not ref_audio.is_file():
        raise RuntimeError(f"Qwen reference audio was not found: {ref_audio}")
    ref_text = str(request.get("ref_text") or "").strip()
    x_vector_only = bool(request.get("x_vector_only_mode", not bool(ref_text)))

    _set_seed(request.get("seed"))
    kwargs = {
        "text": str(request.get("text") or ""),
        "language": str(request.get("language") or "English"),
        "ref_audio": str(ref_audio),
        "ref_text": ref_text or None,
        "x_vector_only_mode": x_vector_only,
        **_generation_kwargs(request),
    }
    wavs, sr = model.generate_voice_clone(**kwargs)
    if not wavs:
        raise RuntimeError("Qwen Base voice cloning did not return audio.")
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), wavs[0], sr)


def server(args) -> int:
    root = Path(args.models_root).resolve()
    _worker_diagnostic(
        "worker_server_started",
        task=args.task,
        model_kind=args.kind,
        requested_backend=args.backend,
        models_root_exists=root.is_dir(),
    )

    # Design/preview workers are lazy-loaded. This prevents every new preview
    # from loading the 1.7B VoiceDesign model and immediately swapping it out
    # for Base just to synthesize a cached character voice.
    model = None
    device = "pending"
    active_task = args.task
    active_kind = args.kind
    locked_clone_prompts = None
    locked_anchors = None
    locked_profile_key: str | None = None
    design_identity_cache: dict[str, tuple[dict, dict, str]] = {}

    def load_model(kind: str, *, allow_cpu_fallback: bool = True) -> None:
        nonlocal model, device, active_kind
        _worker_diagnostic(
            "load_model_requested",
            task=active_task,
            model_kind=kind,
            requested_backend=args.backend,
        )
        print(json.dumps({"progress": f"Loading Qwen model • {kind}"}), flush=True)
        model, device = _load_model_with_fallback(
            kind,
            args.backend,
            root,
            low_memory=args.low_memory,
            progress=lambda message: print(json.dumps({"progress": message}), flush=True),
            allow_cpu_fallback=allow_cpu_fallback,
        )
        active_kind = kind
        _worker_diagnostic(
            "load_model_ready",
            task=active_task,
            model_kind=kind,
            selected_device=device,
            selected_backend=_actual_backend(device),
        )
        print(json.dumps({"progress": f"Qwen model loaded • {device}"}), flush=True)

    def anchor_bank_paths(request: dict) -> dict[str, Path]:
        return {
            style: _anchor_path(root, request, style)
            for style in ANCHOR_STYLES
        }

    def clear_model_cache(target_device: str) -> None:
        try:
            import torch
            if target_device.startswith("cuda"):
                torch.cuda.empty_cache()
            elif target_device.startswith("xpu"):
                torch.xpu.empty_cache()
        except Exception:
            pass

    def create_locked_clone_prompts(target_model, request: dict, paths: dict[str, Path]) -> dict:
        """Build identity-lock prompts on the device that owns the Base model."""
        explicit_anchor = bool(str(request.get("anchor_path") or "").strip())
        prompts = {}
        for style, path in paths.items():
            transcript = _expression_anchor_text(request, style)
            use_xvector_only = explicit_anchor and style == "neutral" and not str(
                request.get("anchor_text") or ""
            ).strip()
            prompts[style] = target_model.create_voice_clone_prompt(
                ref_audio=str(path),
                ref_text=None if use_xvector_only else transcript,
                x_vector_only_mode=use_xvector_only,
            )
        return prompts

    def lock_design_identity(request: dict) -> None:
        nonlocal model, device, locked_clone_prompts, locked_anchors, locked_profile_key, active_kind
        profile_key = str(request.get("profile_id") or "").strip()
        if not profile_key:
            profile_key = hashlib.sha256(
                json.dumps({
                    "speaker": request.get("speaker"),
                    "language": request.get("language"),
                    "instruct": request.get("instruct"),
                    "anchor_text": request.get("anchor_text"),
                    "seed": request.get("seed"),
                }, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()[:32]

        cached_identity = design_identity_cache.get(profile_key)
        if cached_identity is not None:
            locked_clone_prompts, locked_anchors, cached_kind = cached_identity
            locked_profile_key = profile_key
            if model is None or active_kind != cached_kind:
                if model is not None:
                    del model
                    model = None
                    gc.collect()
                    clear_model_cache(device)
                load_model(cached_kind)
                active_kind = cached_kind
            return

        paths = anchor_bank_paths(request)
        ready = all(
            path.exists() and path.stat().st_size >= 1024
            for path in paths.values()
        )
        clone_kind = str(args.clone_kind)

        if not ready:
            # Create a new character anchor only when this profile has none.
            # Release an already loaded Base model before loading VoiceDesign.
            if model is not None:
                del model
                model = None
                gc.collect()
                clear_model_cache(device)
            load_model(args.kind)
            print(
                json.dumps({
                    "progress": "Preparing this character's saved acoustic identity…"
                }),
                flush=True,
            )
            paths = _create_expression_anchors(model, request, root)
            del model
            model = None
            gc.collect()
            clear_model_cache(device)

        # Keep each saved canonical character identity cached per profile while
        # reusing one Base model instance across character profiles and creating
        # only profile-specific clone prompts. This preserves each character's
        # acoustic anchor without loading a separate 0.6B/1.7B model per cast member.
        if model is None or active_kind != clone_kind:
            if model is not None:
                del model
                model = None
                gc.collect()
                clear_model_cache(device)
            # Preserve the selected Base model kind across Automatic fallback;
            # never trade the requested 1.7B identity for a smaller model.
            load_model(clone_kind)
        active_kind = clone_kind

        locked_clone_prompts = create_locked_clone_prompts(model, request, paths)
        locked_anchors = paths
        locked_profile_key = profile_key
        design_identity_cache[profile_key] = (locked_clone_prompts, paths, clone_kind)

    # VoiceDesign loads lazily on the first request. A separate protocol
    # acknowledgement lets the parent send that request without claiming that
    # a model or compute device is already ready.
    if active_task in {"design", "design-preview"}:
        _worker_diagnostic(
            "worker_protocol_ready",
            task=active_task,
            model_kind=args.kind,
            lazy_model_load=True,
        )
        print(json.dumps({
            "worker_ready": True,
            "kind": args.kind,
            "task": args.task,
        }), flush=True)
    else:
        load_model(args.kind)
        ready_kind = active_kind or args.kind
        print(json.dumps({
            "ready": True,
            "device": device,
            "backend": _actual_backend(device),
            "model": MODEL_IDS.get(ready_kind, ready_kind),
            "kind": ready_kind,
            "task": args.task,
        }), flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        batch_texts = None
        try:
            request = json.loads(line)
            batch_texts = request.get("texts")
            batch_outputs = request.get("outputs")

            if active_task == "design":
                lock_design_identity(request)
            elif active_task == "design-preview" and model is None:
                # One-pass audition: load only VoiceDesign, without preparing
                # multiple anchor recordings or swapping to a Base model.
                load_model(args.kind)


            if isinstance(batch_texts, list):
                if not isinstance(batch_outputs, list) or len(batch_texts) != len(batch_outputs):
                    raise RuntimeError("Qwen batch request has mismatched texts and outputs.")
                texts = [str(value or "").strip() for value in batch_texts]
                if any(not value for value in texts):
                    raise RuntimeError("Qwen batch contains empty narration text.")

                requested_styles = request.get("styles") or [None] * len(texts)
                styles = [
                    str(style) if style else classify_expression(text)
                    for text, style in zip(texts, requested_styles)
                ]
                import soundfile as sf
                if active_task == "design-preview":
                    # Preview batches remain on the VoiceDesign model; do not
                    # swap to the production Base voice-clone identity workflow.
                    print(
                        json.dumps({"progress": f"Generating {len(texts)} VoiceDesign preview segments…"}),
                        flush=True,
                    )
                    for style in dict.fromkeys(styles):
                        indexes = [i for i, item_style in enumerate(styles) if item_style == style]
                        selected_texts = [texts[i] for i in indexes]
                        longest_text = max(selected_texts, key=len) if selected_texts else ""
                        batch_request = {
                            **request,
                            "text": longest_text,
                            "max_new_tokens": min(_recommended_max_new_tokens(longest_text), 1024),
                        }
                        design_instructions = [
                            _voice_design_instruct({**request, "text": texts[index]}, style)
                            for index in indexes
                        ]
                        _set_seed(request.get("seed"))
                        wavs, sr = model.generate_voice_design(
                            text=selected_texts,
                            language=[str(request.get("language") or "English")] * len(selected_texts),
                            instruct=design_instructions,
                            **_generation_kwargs(batch_request),
                        )
                        if len(wavs) != len(indexes):
                            raise RuntimeError(
                                f"Qwen VoiceDesign returned {len(wavs)} outputs for "
                                f"{len(indexes)} {style} preview items."
                            )
                        for index, wav in zip(indexes, wavs):
                            destination = Path(str(batch_outputs[index]))
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            sf.write(str(destination), wav, sr)
                else:
                    print(
                        json.dumps({"progress": f"Generating {len(texts)} Qwen segments with locked character expression…"}),
                        flush=True,
                    )
                    for style in dict.fromkeys(styles):
                        indexes = [i for i, item_style in enumerate(styles) if item_style == style]
                        selected_texts = [texts[i] for i in indexes]
                        temperature = expression_temperature(style)
                        batch_request = {
                            **request,
                            "text": max(selected_texts, key=len) if selected_texts else "",
                            "temperature": temperature,
                            "subtalker_temperature": temperature,
                        }
                        prompt_style = reference_style(style)
                        prompt = locked_clone_prompts.get(prompt_style) or locked_clone_prompts.get("neutral")
                        if prompt is None:
                            raise RuntimeError(f"No Qwen expression prompt is available for style '{style}'.")
                        wavs, sr = model.generate_voice_clone(
                            text=selected_texts,
                            language=[str(request.get("language") or "English")] * len(selected_texts),
                            voice_clone_prompt=prompt,
                            **_generation_kwargs(batch_request),
                        )
                        if len(wavs) != len(indexes):
                            raise RuntimeError(
                                f"Qwen returned {len(wavs)} outputs for {len(indexes)} {style} batch items."
                            )
                        for index, wav in zip(indexes, wavs):
                            destination = Path(str(batch_outputs[index]))
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            sf.write(str(destination), wav, sr)

                print(
                    json.dumps(
                        {
                            "ok": True,
                            "outputs": [str(Path(str(path)).resolve()) for path in batch_outputs],
                            "device": device, "backend": _actual_backend(device),
                            "kind": active_kind,
                            "task": active_task,
                            "voice_lock": bool(locked_clone_prompts is not None),
                        }
                    ),
                    flush=True,
                )
                continue

            output = Path(request["output"])
            text = str(request.get("text") or "").strip()
            if not text:
                raise RuntimeError("Qwen character text is empty.")

            if active_task == "custom":
                print(
                    json.dumps({"progress": "Generating Qwen CustomVoice speech…"}),
                    flush=True,
                )
                _generate_custom(model, request, output)
            elif active_task == "design":
                print(json.dumps({"progress": "Generating natural VoiceDesign narration…"}), flush=True)
                _generate_design_locked(model, locked_clone_prompts, request, output)
            elif active_task == "design-preview":
                print(json.dumps({"progress": "Generating one-pass VoiceDesign preview…"}), flush=True)
                _generate_design_preview(model, request, output)
            elif active_task == "clone":
                print(
                    json.dumps({"progress": "Generating Qwen Base clone speech…"}),
                    flush=True,
                )
                _generate_clone(model, request, output)
            else:
                raise RuntimeError(f"Unsupported Qwen task: {active_task}")

            print(
                json.dumps(
                    {
                        "ok": True,
                        "output": str(output),
                        "device": device, "backend": _actual_backend(device),
                        "kind": active_kind,
                        "task": active_task,
                        "anchor": (str(locked_anchors.get("neutral")) if locked_anchors else None),
                        "voice_lock": bool(locked_clone_prompts is not None),
                    }
                ),
                flush=True,
            )
        except Exception as exc:
            # A CUDA OOM should not destroy a long audiobook.
            if _is_cuda_oom(exc) and device.startswith(("cuda", "xpu")) and isinstance(batch_texts, list):
                try:
                    import torch
                    if device.startswith("cuda"):
                        torch.cuda.empty_cache()
                    else:
                        torch.xpu.empty_cache()
                except Exception:
                    pass
                print(json.dumps({
                    "ok": False,
                    "batch_oom": True,
                    "error": str(exc),
                    "device": device, "backend": _actual_backend(device),
                    "kind": active_kind,
                    "task": active_task,
                }), flush=True)
                continue

            requested_backend = str(args.backend or "automatic").strip().casefold()
            automatic_backend = requested_backend in {"automatic", "auto"}
            accelerator_device = str(device or "").casefold().startswith(("cuda", "xpu"))
            if _is_cuda_oom(exc) and automatic_backend and accelerator_device:
                # Automatic may retry the same selected model on CPU after an
                # accelerator OOM. Explicit CUDA/ROCm/XPU choices fail closed;
                # they must never silently become a slower CPU generation.
                clear_model_cache(device)
                try:
                    print(
                        json.dumps({
                            "progress": (
                                "Automatic accelerator synthesis ran out of memory; "
                                "retrying the same selected model on CPU without changing voice identity."
                            )
                        }),
                        flush=True,
                    )
                    if active_task == "design-preview":
                        # Preview stays on the same VoiceDesign model/prompt path.
                        model, device = _load_model(str(args.kind), "cpu", root, low_memory=args.low_memory)
                        active_kind = str(args.kind)
                        _generate_design_preview(model, request, Path(str(request.get("output"))))
                    elif active_task == "design":
                        # Rebuild the Base clone prompt on CPU from the exact same
                        # saved acoustic anchor. Prompt tensors/cache objects can
                        # be device-bound and must not be reused after a GPU->CPU
                        # model transition.
                        if not locked_anchors or not locked_profile_key or locked_clone_prompts is None:
                            raise RuntimeError(
                                "The stable VoiceDesign identity could not be restored after accelerator memory fallback."
                            )
                        model, device = _load_model(str(args.clone_kind), "cpu", root, low_memory=args.low_memory)
                        active_kind = str(args.clone_kind)
                        locked_clone_prompts = create_locked_clone_prompts(
                            model, request, locked_anchors
                        )
                        design_identity_cache[locked_profile_key] = (
                            locked_clone_prompts,
                            locked_anchors,
                            str(args.clone_kind),
                        )
                        _generate_design_locked(
                            model,
                            locked_clone_prompts,
                            request,
                            Path(str(request.get("output"))),
                        )
                    else:
                        model, device = _load_model(active_kind, "cpu", root, low_memory=args.low_memory)
                        if active_task == "custom":
                            _generate_custom(model, request, Path(str(request.get("output"))))
                        else:
                            _generate_clone(model, request, Path(str(request.get("output"))))
                    print(json.dumps({
                        "ok": True,
                        "output": str(request.get("output")),
                        "device": device, "backend": _actual_backend(device),
                        "kind": active_kind,
                        "task": active_task,
                        "anchor": (
                            str(locked_anchors.get("neutral"))
                            if active_task == "design" and locked_anchors else None
                        ),
                        "voice_lock": (
                            bool(locked_clone_prompts is not None)
                            if active_task == "design" else False
                        ),
                    }), flush=True)
                    continue
                except Exception as retry_exc:
                    exc = retry_exc

            print(json.dumps({
                "ok": False,
                "error": str(exc),
                "device": device, "backend": _actual_backend(device),
                "kind": active_kind,
                "task": active_task,
            }), flush=True)
    return 0

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--kind", required=True, choices=sorted(MODEL_IDS))
    parser.add_argument("--clone-kind", default="base-0.6b", choices=["base-0.6b", "base-1.7b"])
    parser.add_argument("--anchor-path", default="")
    parser.add_argument("--anchor-text", default="")
    parser.add_argument(
        "--task",
        choices=["custom", "design", "design-preview", "clone"],
        default="custom",
    )
    parser.add_argument("--backend", default="automatic")
    parser.add_argument("--low-memory", action="store_true")
    parser.add_argument("--models-root", required=True)
    args = parser.parse_args()
    if args.server:
        return server(args)
    raise SystemExit("Use --server.")


if __name__ == "__main__":
    raise SystemExit(main())

