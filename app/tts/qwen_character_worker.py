from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from pathlib import Path
import gc
import hashlib
import json
import sys

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
from app.tts.qwen_accelerator import best_accelerator

EXPRESSION_BANK_VERSION = "v8-emotion-range-anchor"
ANCHOR_STYLES = ("neutral",)
ANCHOR_TEXTS = {"neutral": DEFAULT_VOICE_DESIGN_ANCHOR_TEXT}

MODEL_IDS = {
    "custom-0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    "custom-1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "design-1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "base-0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "base-1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
}


def _load_model(kind: str, backend: str, root: Path):
    import torch
    from qwen_tts import Qwen3TTSModel

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
        device = selected.device if selected.supported else "cpu"
    elif requested == "cuda" and torch.cuda.is_available():
        device = "cuda:0"
    elif requested == "xpu" and getattr(torch, "xpu", None) is not None and torch.xpu.is_available():
        device = "xpu:0"
    elif requested == "rocm" and torch.cuda.is_available() and "rocm" in str(torch.version.hip or "").casefold():
        device = "cuda:0"
    else:
        raise RuntimeError(
            f"Requested Qwen backend '{requested}' is unavailable or not certified. "
            f"Detected: {selected.backend} ({selected.name}). {selected.reason}"
        )

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
    elif device.startswith("xpu"):
        try:
            torch.set_float32_matmul_precision("high")
        except Exception:
            pass

    kwargs = {
        "device_map": device,
        "dtype": dtype,
        "attn_implementation": "sdpa",
    }
    with redirect_stdout(sys.stderr):
        model = Qwen3TTSModel.from_pretrained(str(model_path), **kwargs)
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
    if not str(device).startswith("cuda"):
        return torch.float32
    try:
        supports_bf16 = bool(torch.cuda.is_bf16_supported())
    except Exception:
        supports_bf16 = False
    return torch.bfloat16 if supports_bf16 else torch.float16


def _xpu_inference_dtype(torch, device: str):
    try:
        supports_bf16 = bool(torch.xpu.is_bf16_supported())
    except Exception:
        supports_bf16 = False
    return torch.bfloat16 if supports_bf16 else torch.float16


def _is_cuda_oom(exc: BaseException) -> bool:
    message = str(exc).casefold()
    return ("out of memory" in message or "outofmemory" in message) and any(
        token in message for token in ("cuda", "cublas", "xpu", "hip", "rocm")
    )


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
        "do_sample": True, "top_k": 50, "top_p": 1.0, "temperature": 0.9,
        "repetition_penalty": 1.05, "subtalker_dosample": True,
        "subtalker_top_k": 50, "subtalker_top_p": 1.0,
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
    return ("Hello. This is a short voice identity sample for Ryu's Audiobook. "
            "The character speaks clearly, naturally, and with a steady identity from one sentence to the next.")


def _anchor_path(root: Path, request: dict, style: str = "neutral") -> Path:
    explicit = str(request.get("anchor_path") or "").strip()
    if explicit and style == "neutral":
        return Path(explicit)
    identity = "|".join([
        EXPRESSION_BANK_VERSION, str(request.get("speaker") or request.get("voice_id") or "voice"),
        str(request.get("language") or "English"), str(request.get("instruct") or ""),
        str(request.get("seed") or ""), str(request.get("anchor_text") or ""),
        str(request.get("profile_id") or ""), style,
    ])
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return root / "voice_anchors" / f"qwen-design-{style}-{digest}.wav"


def _generate_custom(model, request: dict, output: Path) -> None:
    import soundfile as sf
    speaker = str(request.get("speaker") or "").strip()
    if not speaker:
        raise RuntimeError("A Qwen CustomVoice speaker is required.")
    _set_seed(request.get("seed"))
    wavs, sr = model.generate_custom_voice(
        text=str(request.get("text") or ""), language=str(request.get("language") or "English"),
        speaker=speaker, instruct=str(request.get("instruct") or "").strip(),
        **_generation_kwargs(request),
    )
    if not wavs:
        raise RuntimeError("Qwen CustomVoice did not return audio.")
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), wavs[0], sr)


def _generate_design(model, request: dict, output: Path) -> None:
    import soundfile as sf
    _set_seed(request.get("seed"))
    wavs, sr = model.generate_voice_design(
        text=str(request.get("text") or ""), language=str(request.get("language") or "English"),
        instruct=_voice_design_instruct(request), **_generation_kwargs(request),
    )
    if not wavs:
        raise RuntimeError("Qwen VoiceDesign did not return narration audio.")
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), wavs[0], sr)


def _generate_design_preview(model, request: dict, output: Path) -> None:
    import soundfile as sf
    _set_seed(request.get("seed"))
    wavs, sr = model.generate_voice_design(
        text=str(request.get("text") or ""), language=str(request.get("language") or "English"),
        instruct=_voice_design_instruct(request),
        **_generation_kwargs({**request, "max_new_tokens": min(
            _recommended_max_new_tokens(str(request.get("text") or "")), 1024)}),
    )
    if not wavs:
        raise RuntimeError("Qwen VoiceDesign did not return preview audio.")
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), wavs[0], sr)


def _generate_design_anchor(model, request: dict, anchor: Path) -> str:
    import soundfile as sf
    language = str(request.get("language") or "English")
    anchor_text = (str(request.get("anchor_text") or "").strip()
                   or "Hello. This is a short, natural voice sample. I speak clearly and comfortably.")
    _set_seed(request.get("seed"))
    wavs, sr = model.generate_voice_design(
        text=anchor_text, language=language, instruct=_voice_design_instruct(request),
        **_generation_kwargs({**request, "max_new_tokens": min(
            int(request.get("max_new_tokens", 768)), 768)}),
    )
    if not wavs:
        raise RuntimeError("Qwen VoiceDesign did not return a reusable voice anchor.")
    anchor.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(anchor), wavs[0], sr)
    return anchor_text


def _expression_anchor_text(request: dict, style: str) -> str:
    if style == "neutral":
        requested = str(request.get("anchor_text") or "").strip()
        if requested:
            return requested
    return ANCHOR_TEXTS.get(style, ANCHOR_TEXTS["neutral"])


def _create_expression_anchors(model, request: dict, root: Path) -> dict[str, Path]:
    import soundfile as sf
    language = str(request.get("language") or "English")
    paths = {style: _anchor_path(root, request, style) for style in ANCHOR_STYLES}
    missing = [style for style, path in paths.items()
               if not path.exists() or path.stat().st_size < 1024]
    if not missing:
        return paths
    explicit_anchor = str(request.get("anchor_path") or "").strip()
    if explicit_anchor and "neutral" in missing:
        raise RuntimeError("The selected saved voice anchor is missing. Re-select or rebuild the voice profile.")
    for ordinal, style in enumerate(missing, start=1):
        path = paths[style]
        anchor_text = _expression_anchor_text(request, style)
        temperature = 0.88
        print(json.dumps({"progress": (
            f"Building the saved character identity • {ordinal}/{len(missing)} • first use for this profile"
        )}), flush=True)
        _set_seed(request.get("seed"))
        anchor_request = {**request, "text": anchor_text, "max_new_tokens": 384,
                          "temperature": temperature, "subtalker_temperature": temperature}
        base_description = str(request.get("instruct") or "")
        instruct = (voice_design_anchor_instruction(base_description)
                    if style == "neutral" else expression_instruction(base_description, style))
        wavs, sr = model.generate_voice_design(
            text=anchor_text, language=language, instruct=instruct,
            **_generation_kwargs(anchor_request),
        )
        if not wavs:
            raise RuntimeError(f"Qwen VoiceDesign did not return the '{style}' character reference.")
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
    device = best_accelerator().device
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
    requested_clone_kind = args.clone_kind
    try:
        clone_model, clone_device = _load_model(requested_clone_kind, args.backend, root)
    except Exception as exc:
        if _is_cuda_oom(exc) and str(requested_clone_kind) == "base-1.7b":
            fallback_kind = "base-0.6b"
            if (root / fallback_kind).exists():
                print(json.dumps({"progress": "Base 1.7B exceeded available accelerator memory • switching to Base 0.6B"}), flush=True)
                clone_model, clone_device = _load_model(fallback_kind, args.backend, root)
                args.clone_kind = fallback_kind
            else:
                raise
        else:
            raise
    explicit_anchor = bool(str(request.get("anchor_path") or "").strip())
    prompts = {}
    for style, path in paths.items():
        transcript = _expression_anchor_text(request, style)
        use_xvector_only = explicit_anchor and style == "neutral" and not str(request.get("anchor_text") or "").strip()
        prompts[style] = clone_model.create_voice_clone_prompt(
            ref_audio=str(path), ref_text=None if use_xvector_only else transcript,
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
    request = {**request, "temperature": temperature,
               "subtalker_temperature": temperature, "expression_style": style}
    _set_seed(request.get("seed"))
    wavs, sr = model.generate_voice_clone(
        text=str(request.get("text") or ""), language=str(request.get("language") or "English"),
        voice_clone_prompt=prompt, **_generation_kwargs(request),
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
    wavs, sr = model.generate_voice_clone(
        text=str(request.get("text") or ""), language=str(request.get("language") or "English"),
        ref_audio=str(ref_audio), ref_text=ref_text or None,
        x_vector_only_mode=x_vector_only, **_generation_kwargs(request),
    )
    if not wavs:
        raise RuntimeError("Qwen Base voice cloning did not return audio.")
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), wavs[0], sr)


def server(args) -> int:
    root = Path(args.models_root).resolve()
    model = None
    device = "pending"
    active_task = args.task
    active_kind = args.kind
    locked_clone_prompts = None
    locked_anchors = None

    def load_model(kind: str, *, allow_cpu_fallback: bool = True) -> None:
        nonlocal model, device, active_kind
        try:
            print(json.dumps({"progress": f"Loading Qwen model • {kind}"}), flush=True)
            model, device = _load_model(kind, args.backend, root)
        except Exception as exc:
            if allow_cpu_fallback and _is_cuda_oom(exc) and args.backend != "cpu":
                print(json.dumps({"progress": f"{kind} did not fit accelerator memory • switching to CPU compatibility mode…"}), flush=True)
                model, device = _load_model(kind, "cpu", root)
            else:
                raise
        active_kind = kind
        print(json.dumps({"progress": f"Qwen model loaded • {device}"}), flush=True)

    def anchor_bank_paths(request: dict) -> dict[str, Path]:
        return {style: _anchor_path(root, request, style) for style in ANCHOR_STYLES}

    def lock_design_identity(request: dict) -> None:
        nonlocal model, device, locked_clone_prompts, locked_anchors, active_kind
        if locked_clone_prompts is not None:
            return
        paths = anchor_bank_paths(request)
        ready = all(path.exists() and path.stat().st_size >= 1024 for path in paths.values())
        if not ready:
            if model is None or active_kind != "design-1.7b":
                if model is not None:
                    del model
                    gc.collect()
                load_model("design-1.7b")
            paths = _create_expression_anchors(model, request, root)
        else:
            paths = {style: path for style, path in paths.items()}
        print(json.dumps({"progress": "Expression references ready • loading Base clone engine…"}), flush=True)
        if model is not None:
            del model
            model = None
            gc.collect()
        try:
            clone_model, clone_device = _load_model(args.clone_kind, args.backend, root)
        except Exception as exc:
            if _is_cuda_oom(exc) and args.backend != "cpu":
                print(json.dumps({"progress": "Base model exceeded accelerator memory • retrying on CPU…"}), flush=True)
                clone_model, clone_device = _load_model(args.clone_kind, "cpu", root)
            else:
                raise
        prompts = {}
        for style, path in paths.items():
            transcript = _expression_anchor_text(request, style)
            prompts[style] = clone_model.create_voice_clone_prompt(
                ref_audio=str(path), ref_text=transcript, x_vector_only_mode=False)
        model, device, active_kind = clone_model, clone_device, args.clone_kind
        locked_clone_prompts, locked_anchors = prompts, paths

    load_model(args.kind)

    print(json.dumps({"ready": True, "device": device, "kind": active_kind}), flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            if isinstance(request.get("texts"), list):
                texts = [str(value).strip() for value in request["texts"]]
                outputs = [Path(value) for value in request.get("outputs", [])]
                if len(texts) != len(outputs):
                    raise RuntimeError("Qwen batch request has mismatched texts and outputs.")
                if any(not text for text in texts):
                    raise RuntimeError("Qwen batch contains empty narration text.")
                active_request = {**request, "text": " ".join(texts)}
                if args.task == "design-preview":
                    wavs, sample_rate = model.generate_voice_design(
                        text=active_request["text"], language=str(request.get("language") or "English"),
                        instruct=_voice_design_instruct(active_request), **_generation_kwargs(active_request))
                    if len(wavs) != len(outputs):
                        raise RuntimeError(f"Qwen VoiceDesign returned {len(wavs)} outputs for {len(outputs)} preview chunks.")
                    import soundfile as sf
                    for wav, output in zip(wavs, outputs):
                        output.parent.mkdir(parents=True, exist_ok=True)
                        sf.write(str(output), wav, sample_rate)
                elif args.task == "design":
                    lock_design_identity(request)
                    by_style = {}
                    for index, (text_value, output, style) in enumerate(zip(texts, outputs, request.get("styles", []))):
                        by_style.setdefault(reference_style(style), []).append((index, text_value, output))
                    for style, items in by_style.items():
                        prompt = locked_clone_prompts.get(style) or locked_clone_prompts.get("neutral")
                        if prompt is None:
                            raise RuntimeError(f"No Qwen expression prompt is available for style '{style}'.")
                        wavs, sample_rate = model.generate_voice_clone(
                            text=[item[1] for item in items], language=str(request.get("language") or "English"),
                            voice_clone_prompt=prompt,
                            **_generation_kwargs({**request, "text": " ".join(item[1] for item in items)}))
                        if len(wavs) != len(items):
                            raise RuntimeError(f"Qwen returned {len(wavs)} outputs for {len(items)} {style} batch items.")
                        import soundfile as sf
                        for item, wav in zip(items, wavs):
                            item[2].parent.mkdir(parents=True, exist_ok=True)
                            sf.write(str(item[2]), wav, sample_rate)
                else:
                    raise RuntimeError("Batch synthesis is supported only for VoiceDesign tasks.")
                print(json.dumps({"ok": True, "outputs": [str(path) for path in outputs],
                                  "device": device, "kind": active_kind}), flush=True)
                continue

            text_value = str(request.get("text") or "").strip()
            output = Path(str(request.get("output") or ""))
            if not text_value or not str(output):
                raise RuntimeError("Qwen character text/output is empty.")
            if args.task == "custom":
                _generate_custom(model, request, output)
            elif args.task == "design-preview":
                _generate_design_preview(model, request, output)
            elif args.task == "design":
                if request.get("longform"):
                    lock_design_identity(request)
                    _generate_design_locked(model, locked_clone_prompts, request, output)
                else:
                    _generate_design(model, request, output)
            elif args.task == "clone":
                _generate_clone(model, request, output)
            else:
                raise RuntimeError(f"Unsupported Qwen task: {args.task}")
            print(json.dumps({"ok": True, "output": str(output), "device": device,
                              "kind": active_kind, "task": active_task}), flush=True)
        except Exception as exc:
            if _is_cuda_oom(exc) and device.startswith(("cuda", "xpu")) and isinstance(request.get("texts"), list):
                try:
                    import torch
                    if device.startswith("cuda"):
                        torch.cuda.empty_cache()
                    else:
                        torch.xpu.empty_cache()
                    raise RuntimeError("Qwen batch exceeded accelerator memory.")
                except Exception as retry_exc:
                    exc = retry_exc
            if _is_cuda_oom(exc) and device.startswith(("cuda", "xpu")):
                try:
                    import torch
                    print(json.dumps({"progress": "GPU memory exhausted • switching this request to CPU…"}), flush=True)
                    if device.startswith("cuda"):
                        torch.cuda.empty_cache()
                    else:
                        torch.xpu.empty_cache()
                    if args.task == "design" and locked_clone_prompts:
                        model, device, locked_clone_prompts, locked_anchors = _prepare_design_clone(
                            model, request, args)
                    elif args.task == "design" and args.kind == "design-1.7b":
                        model, device = _load_model(str(args.clone_kind), "cpu", root)
                    elif args.task == "design-preview" and args.kind == "design-1.7b":
                        model, device = _load_model("design-1.7b", "cpu", root)
                    else:
                        model, device = _load_model(active_kind, "cpu", root)
                    active_kind = args.kind if args.task == "design-preview" else active_kind
                    if args.task == "custom":
                        _generate_custom(model, request, output)
                    elif args.task == "clone":
                        _generate_clone(model, request, output)
                    elif args.task == "design-preview":
                        _generate_design_preview(model, request, output)
                    else:
                        _generate_design(model, request, output)
                    print(json.dumps({"ok": True, "output": str(output), "device": device,
                                      "kind": active_kind, "task": active_task}), flush=True)
                    continue
                except Exception as retry_exc:
                    exc = retry_exc
            print(json.dumps({"ok": False, "error": str(exc), "device": device,
                              "kind": active_kind, "task": active_task}), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--kind", required=True, choices=sorted(MODEL_IDS))
    parser.add_argument("--clone-kind", default="base-0.6b", choices=["base-0.6b", "base-1.7b"])
    parser.add_argument("--anchor-path", default="")
    parser.add_argument("--anchor-text", default="")
    parser.add_argument("--task", choices=["custom", "design", "design-preview", "clone"], default="custom")
    parser.add_argument("--backend", default="automatic")
    parser.add_argument("--models-root", required=True)
    args = parser.parse_args()
    if args.server:
        return server(args)
    raise SystemExit("Use --server.")


if __name__ == "__main__":
    raise SystemExit(main())
