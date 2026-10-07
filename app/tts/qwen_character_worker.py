from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from pathlib import Path
import gc
import hashlib
import json
import sys

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


def _generation_kwargs(request: dict) -> dict:
    return {
        "do_sample": bool(request.get("do_sample", True)),
        "top_k": int(request.get("top_k", 50)),
        "top_p": float(request.get("top_p", 1.0)),
        "temperature": float(request.get("temperature", 0.9)),
        "repetition_penalty": float(request.get("repetition_penalty", 1.05)),
        "subtalker_dosample": bool(request.get("subtalker_dosample", True)),
        "subtalker_top_k": int(request.get("subtalker_top_k", 50)),
        "subtalker_top_p": float(request.get("subtalker_top_p", 1.0)),
        "subtalker_temperature": float(request.get("subtalker_temperature", 0.9)),
        "max_new_tokens": int(request.get("max_new_tokens", 2048)),
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


def _anchor_path(root: Path, request: dict) -> Path:
    explicit = str(request.get("anchor_path") or "").strip()
    if explicit:
        return Path(explicit)
    identity = "|".join(
        [
            str(request.get("speaker") or request.get("voice_id") or "voice"),
            str(request.get("language") or "English"),
            str(request.get("instruct") or ""),
            str(request.get("seed") or ""),
        ]
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return root / "voice_anchors" / f"qwen-design-{digest}.wav"


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


def _generate_design_anchor(model, request: dict, anchor: Path) -> str:
    import soundfile as sf

    language = str(request.get("language") or "English")
    anchor_text = str(request.get("anchor_text") or "").strip() or _default_anchor_text(language)
    _set_seed(request.get("seed"))
    wavs, sr = model.generate_voice_design(
        text=anchor_text,
        language=language,
        instruct=str(request.get("instruct") or "").strip(),
        **_generation_kwargs(
            {
                **request,
                "max_new_tokens": min(int(request.get("max_new_tokens", 2048)), 768),
            }
        ),
    )
    if not wavs:
        raise RuntimeError("Qwen VoiceDesign did not return a reusable voice anchor.")
    anchor.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(anchor), wavs[0], sr)
    return anchor_text


def _prepare_design_clone(model, request: dict, args):
    # Build the reusable character voice identity once from VoiceDesign, then
    # switch to the Base model and reuse one VoiceClonePromptItem for every
    # narration chunk. This prevents per-chunk VoiceDesign timbre drift.
    import torch
    from qwen_tts import Qwen3TTSModel

    anchor = _anchor_path(Path(args.models_root).resolve(), request)
    anchor_text = str(request.get("anchor_text") or "").strip() or _default_anchor_text(
        str(request.get("language") or "English")
    )

    if not anchor.exists() or anchor.stat().st_size < 1024:
        anchor_text = _generate_design_anchor(model, request, anchor)

    del model
    gc.collect()
    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass

    clone_model, clone_device = _load_model(args.clone_kind, args.backend, Path(args.models_root).resolve())
    x_vector_only = False
    prompt = clone_model.create_voice_clone_prompt(
        ref_audio=str(anchor),
        ref_text=anchor_text,
        x_vector_only_mode=x_vector_only,
    )
    return clone_model, clone_device, prompt, anchor


def _generate_design_locked(model, prompt, request: dict, output: Path) -> None:
    import soundfile as sf

    _set_seed(request.get("seed"))
    wavs, sr = model.generate_voice_clone(
        text=str(request.get("text") or ""),
        language=str(request.get("language") or "English"),
        voice_clone_prompt=prompt,
        **_generation_kwargs(request),
    )
    if not wavs:
        raise RuntimeError("Qwen locked VoiceDesign/Base generation did not return audio.")
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
    try:
        model, device = _load_model(args.kind, args.backend, root)
    except Exception as exc:
        if _is_cuda_oom(exc) and args.backend != "cpu":
            model, device = _load_model(args.kind, "cpu", root)
        else:
            raise

    locked_prompt = None
    anchor_path = None
    active_task = args.task
    active_kind = args.kind

    if args.task == "design":
        # VoiceDesign itself creates the identity anchor only once. Generation
        # then continues through the Base model in the same worker process.
        pass

    print(
        json.dumps(
            {
                "ready": True,
                "device": device,
                "model": MODEL_IDS[args.kind],
                "kind": args.kind,
                "task": args.task,
            }
        ),
        flush=True,
    )

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            output = Path(request["output"])
            text = str(request.get("text") or "").strip()
            if not text:
                raise RuntimeError("Qwen character text is empty.")

            if active_task == "design" and locked_prompt is None:
                try:
                    model, device, locked_prompt, anchor_path = _prepare_design_clone(model, request, args)
                    active_task = "design-locked"
                    active_kind = args.clone_kind
                except Exception as exc:
                    if _is_cuda_oom(exc) and device.startswith("cuda"):
                        try:
                            import torch
                            torch.cuda.empty_cache()
                        except Exception:
                            pass
                        model, device = _load_model(args.kind, "cpu", root)
                        args.backend = "cpu"
                        model, device, locked_prompt, anchor_path = _prepare_design_clone(model, request, args)
                        active_task = "design-locked"
                        active_kind = args.clone_kind
                    else:
                        raise

            if active_task == "custom":
                _generate_custom(model, request, output)
            elif active_task == "design-locked":
                _generate_design_locked(model, locked_prompt, request, output)
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
                        "anchor": str(anchor_path) if anchor_path else None,
                    }
                ),
                flush=True,
            )
        except Exception as exc:
            # A CUDA OOM should not destroy a long audiobook. For Base clone
            # and CustomVoice we can reload on CPU. For a locked VoiceDesign
            # profile, the same policy applies after the anchor exists.
            if _is_cuda_oom(exc) and device.startswith("cuda"):
                try:
                    import torch
                    torch.cuda.empty_cache()
                except Exception:
                    pass
                try:
                    model, device = _load_model(
                        active_kind,
                        "cpu",
                        root,
                    )
                    if active_task == "design-locked":
                        # Prompt tensors remain device-specific in Qwen, so rebuild
                        # the Base prompt after switching devices.
                        if anchor_path and Path(anchor_path).exists():
                            anchor_text = str(request.get("anchor_text") or "").strip() or _default_anchor_text(
                                str(request.get("language") or "English")
                            )
                            locked_prompt = model.create_voice_clone_prompt(
                                ref_audio=str(anchor_path),
                                ref_text=anchor_text,
                                x_vector_only_mode=False,
                            )
                    device = "cpu"
                    if active_task == "custom":
                        _generate_custom(model, request, output)
                    elif active_task == "design-locked":
                        _generate_design_locked(model, locked_prompt, request, output)
                    else:
                        _generate_clone(model, request, output)
                    print(
                        json.dumps(
                            {
                                "ok": True,
                                "output": str(output),
                                "device": device,
                                "kind": active_kind,
                                "task": active_task,
                            }
                        ),
                        flush=True,
                    )
                    continue
                except Exception as retry_exc:
                    exc = retry_exc
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": str(exc),
                        "device": device,
                        "kind": active_kind,
                        "task": active_task,
                    }
                ),
                flush=True,
            )
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
        choices=["custom", "design", "clone"],
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
