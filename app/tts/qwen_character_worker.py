from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from pathlib import Path
import gc
import hashlib
import json
import sys

# This worker is launched as a standalone Python script by the packaged
# Windows application. In that mode Python starts with app/tts on sys.path,
# not the PyInstaller _internal root, so explicitly add the application root
# before importing sibling application modules.
_APPLICATION_ROOT = Path(__file__).resolve().parents[2]
if str(_APPLICATION_ROOT) not in sys.path:
    sys.path.insert(0, str(_APPLICATION_ROOT))

from app.tts.expression import (
    EXPRESSION_STYLES,
    classify_expression,
    expression_instruction,
    expression_temperature,
    reference_style,
)

EXPRESSION_BANK_VERSION = "v7-single-anchor-stable-identity"

# The Base model can lock speaker identity from an acoustic reference, but does
# not provide VoiceDesign's per-line natural-language instruction channel.
# Prepare a tiny, versioned bank so the chosen reference itself carries a
# restrained delivery shape. These scripts are the exact transcripts supplied
# to create_voice_clone_prompt.
# Use one canonical acoustic reference per saved profile. Generating different
# VoiceDesign samples independently for each emotion can subtly change timbre
# or even gender presentation; emotion boundaries and sampling variation must
# not replace the saved character identity.
ANCHOR_STYLES = ("neutral",)
ANCHOR_TEXTS = {
    "neutral": (
        "Hello. I thought I understood what was happening. "
        "Oh, really? That's actually wonderful. "
        "Wait... something isn't right. Let's think for a moment."
    ),
}


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

    if backend == "cpu":
        device = "cpu"
    else:
        device = "cuda:0" if torch.cuda.is_available() else "cpu"

    dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32
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
    with redirect_stdout(sys.stderr):
        model = Qwen3TTSModel.from_pretrained(str(model_path), **kwargs)
    gc.collect()
    if device.startswith("cuda"):
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
    return model, device


def _is_cuda_oom(exc: BaseException) -> bool:
    message = str(exc).casefold()
    return "out of memory" in message and (
        "cuda" in message or "cublas" in message or "outofmemory" in message
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
        temperature = expression_temperature(style)
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
        instruct = expression_instruction(
            str(request.get("instruct") or ""),
            style,
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
    try:
        clone_model, clone_device = _load_model(requested_clone_kind, args.backend, root)
    except Exception as exc:
        if _is_cuda_oom(exc) and str(requested_clone_kind) == "base-1.7b":
            fallback_kind = "base-0.6b"
            if (root / fallback_kind).exists():
                print(json.dumps({"progress": "Base 1.7B exceeded available GPU memory • switching to Base 0.6B"}), flush=True)
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

    # Design/preview workers are lazy-loaded. This prevents every new preview
    # from loading the 1.7B VoiceDesign model and immediately swapping it out
    # for Base just to synthesize a cached character voice.
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
                print(json.dumps({"progress": f"{kind} did not fit GPU memory • switching to CPU compatibility mode…"}), flush=True)
                model, device = _load_model(kind, "cpu", root)
            else:
                raise
        active_kind = kind
        print(json.dumps({"progress": f"Qwen model loaded • {device}"}), flush=True)

    def anchor_bank_paths(request: dict) -> dict[str, Path]:
        return {
            style: _anchor_path(root, request, style)
            for style in ANCHOR_STYLES
        }

    def lock_design_identity(request: dict) -> None:
        nonlocal model, device, locked_clone_prompts, locked_anchors, active_kind
        if locked_clone_prompts is not None:
            return
        paths = anchor_bank_paths(request)
        ready = all(
            path.exists() and path.stat().st_size >= 1024
            for path in paths.values()
        )

        if ready:
            print(
                json.dumps({
                    "progress": (
                        "Loading cached canonical character identity • "
                        "reusing neutral/thoughtful/warm/concerned references…"
                    )
                }),
                flush=True,
            )
            clone_kind = args.clone_kind
            try:
                clone_model, clone_device = _load_model(clone_kind, args.backend, root)
            except Exception as exc:
                if _is_cuda_oom(exc) and args.backend != "cpu":
                    clone_kind = "base-0.6b"
                    args.clone_kind = clone_kind
                    clone_model, clone_device = _load_model(clone_kind, args.backend, root)
                else:
                    raise
            model = clone_model
            device = clone_device
            active_kind = clone_kind
            explicit_anchor = bool(str(request.get("anchor_path") or "").strip())
            locked_clone_prompts = {}
            for style, path in paths.items():
                transcript = _expression_anchor_text(request, style)
                use_xvector_only = explicit_anchor and style == "neutral" and not str(
                    request.get("anchor_text") or ""
                ).strip()
                locked_clone_prompts[style] = model.create_voice_clone_prompt(
                    ref_audio=str(path),
                    ref_text=None if use_xvector_only else transcript,
                    x_vector_only_mode=use_xvector_only,
                )
            locked_anchors = paths
            return

        load_model(args.kind)
        print(
            json.dumps({
                "progress": "Preparing the saved character identity • first use for this profile…"
            }),
            flush=True,
        )
        paths = _create_expression_anchors(model, request, root)
        del model
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

        clone_kind = str(args.clone_kind)
        try:
            model, device = _load_model(clone_kind, args.backend, root)
        except Exception as exc:
            if _is_cuda_oom(exc) and args.backend != "cpu":
                clone_kind = "base-0.6b"
                args.clone_kind = clone_kind
                model, device = _load_model(clone_kind, args.backend, root)
            else:
                raise
        active_kind = clone_kind
        explicit_anchor = bool(str(request.get("anchor_path") or "").strip())
        locked_clone_prompts = {}
        for style, path in paths.items():
            transcript = _expression_anchor_text(request, style)
            use_xvector_only = explicit_anchor and style == "neutral" and not str(
                request.get("anchor_text") or ""
            ).strip()
            locked_clone_prompts[style] = model.create_voice_clone_prompt(
                ref_audio=str(path),
                ref_text=None if use_xvector_only else transcript,
                x_vector_only_mode=use_xvector_only,
            )
        locked_anchors = paths

    print(
        json.dumps(
            {
                "ready": True,
                "device": "pending",
                "model": MODEL_IDS.get(args.clone_kind if args.task in {"design", "design-preview"} else args.kind, args.kind),
                "kind": args.clone_kind if args.task in {"design", "design-preview"} else args.kind,
                "task": args.task,
            }
        ),
        flush=True,
    )

    # Non-design providers still load immediately so the ready signal means
    # the actual model is warm. Design workers intentionally defer the heavy
    # load until the first request, as explained above.
    if active_task not in {"design", "design-preview"}:
        load_model(args.kind)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        batch_texts = None
        try:
            request = json.loads(line)
            batch_texts = request.get("texts")
            batch_outputs = request.get("outputs")

            if active_task in {"design", "design-preview"}:
                lock_design_identity(request)

            if isinstance(batch_texts, list):
                if not isinstance(batch_outputs, list) or len(batch_texts) != len(batch_outputs):
                    raise RuntimeError("Qwen batch request has mismatched texts and outputs.")
                texts = [str(value or "").strip() for value in batch_texts]
                if any(not value for value in texts):
                    raise RuntimeError("Qwen batch contains empty narration text.")

                print(json.dumps({"progress": f"Generating {len(texts)} Qwen segments with natural expression…"}), flush=True)
                requested_styles = request.get("styles") or [None] * len(texts)
                styles = [
                    str(style) if style else classify_expression(text)
                    for text, style in zip(texts, requested_styles)
                ]
                import soundfile as sf
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
                            "device": device,
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
                _generate_custom(model, request, output)
            elif active_task in {"design", "design-preview"}:
                print(
                    json.dumps(
                        {
                            "progress": (
                                "Generating natural VoiceDesign narration…"
                                if active_task == "design"
                                else "Generating natural VoiceDesign preview…"
                            )
                        }
                    ),
                    flush=True,
                )
                _generate_design_locked(model, locked_clone_prompts, request, output)
            elif active_task == "clone":
                _generate_clone(model, request, output)
            else:
                raise RuntimeError(f"Unsupported Qwen task: {active_task}")

            print(
                json.dumps(
                    {
                        "ok": True,
                        "output": str(output),
                        "device": device,
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
            if _is_cuda_oom(exc) and device.startswith("cuda") and isinstance(batch_texts, list):
                print(json.dumps({
                    "ok": False,
                    "batch_oom": True,
                    "error": str(exc),
                    "device": device,
                    "kind": active_kind,
                    "task": active_task,
                }), flush=True)
                continue

            if _is_cuda_oom(exc) and device.startswith("cuda"):
                try:
                    import torch
                    torch.cuda.empty_cache()
                except Exception:
                    pass
                try:
                    if active_task in {"design", "design-preview"}:
                        # The stable clone model is always the active model once
                        # identity is locked. Re-load it on CPU and reuse prompts.
                        model, device = _load_model(
                            str(args.clone_kind),
                            "cpu",
                            root,
                        )
                        active_kind = str(args.clone_kind)
                        if locked_clone_prompts is None:
                            raise RuntimeError("The stable VoiceDesign identity could not be restored after GPU memory fallback.")
                        _generate_design_locked(model, locked_clone_prompts, request, Path(str(request.get("output"))))
                    else:
                        model, device = _load_model(active_kind, "cpu", root)
                        if active_task == "custom":
                            _generate_custom(model, request, Path(str(request.get("output"))))
                        else:
                            _generate_clone(model, request, Path(str(request.get("output"))))
                    print(json.dumps({
                        "ok": True,
                        "output": str(request.get("output")),
                        "device": device,
                        "kind": active_kind,
                        "task": active_task,
                    }), flush=True)
                    continue
                except Exception as retry_exc:
                    exc = retry_exc

            print(json.dumps({
                "ok": False,
                "error": str(exc),
                "device": device,
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
    parser.add_argument("--models-root", required=True)
    args = parser.parse_args()
    if args.server:
        return server(args)
    raise SystemExit("Use --server.")


if __name__ == "__main__":
    raise SystemExit(main())
