from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from pathlib import Path
import gc
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
    # These values mirror Qwen's official 12Hz examples and give the audiobook
    # engine expressive but stable speech rather than flat greedy decoding.
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


def _generate_custom(model, request: dict, output: Path) -> None:
    import soundfile as sf

    speaker = str(request.get("speaker") or "").strip()
    if not speaker:
        raise RuntimeError("A Qwen CustomVoice speaker is required.")
    language = str(request.get("language") or "English")
    instruct = str(request.get("instruct") or "").strip()

    kwargs = _generation_kwargs(request)
    # Qwen's 0.6B CustomVoice model is the lightweight fallback and does not
    # provide the same instruction-control surface as 1.7B.
    if request.get("allow_instruct", True) is False:
        instruct = ""

    wavs, sr = model.generate_custom_voice(
        text=str(request.get("text") or ""),
        language=language,
        speaker=speaker,
        instruct=instruct,
        **kwargs,
    )
    if not wavs:
        raise RuntimeError("Qwen CustomVoice did not return audio.")
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), wavs[0], sr)


def _generate_design(model, request: dict, output: Path) -> None:
    import soundfile as sf

    instruct = str(request.get("instruct") or "").strip()
    if not instruct:
        raise RuntimeError(
            "VoiceDesign needs a voice description such as age, timbre, accent, "
            "energy, emotion and speaking style."
        )
    _set_seed(request.get("seed"))
    wavs, sr = model.generate_voice_design(
        text=str(request.get("text") or ""),
        language=str(request.get("language") or "English"),
        instruct=instruct,
        **_generation_kwargs(request),
    )
    if not wavs:
        raise RuntimeError("Qwen VoiceDesign did not return audio.")
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), wavs[0], sr)


def _generate_clone(model, request: dict, output: Path) -> None:
    import soundfile as sf

    ref_audio = Path(str(request.get("reference") or ""))
    if not ref_audio.is_file():
        raise RuntimeError(f"Qwen reference audio was not found: {ref_audio}")
    ref_text = str(request.get("ref_text") or "").strip()
    x_vector_only = bool(request.get("x_vector_only_mode", not bool(ref_text)))

    # Qwen Base supports both x-vector-only cloning and higher-fidelity ICL
    # cloning when an exact reference transcript is supplied.
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
            try:
                if args.task == "custom":
                    _generate_custom(model, request, output)
                elif args.task == "design":
                    _generate_design(model, request, output)
                elif args.task == "clone":
                    _generate_clone(model, request, output)
                else:
                    raise RuntimeError(f"Unsupported Qwen task: {args.task}")
            except Exception as exc:
                if _is_cuda_oom(exc) and device.startswith("cuda"):
                    gc.collect()
                    try:
                        import torch
                        torch.cuda.empty_cache()
                    except Exception:
                        pass
                    model, device = _load_model(args.kind, "cpu", root)
                    if args.task == "custom":
                        _generate_custom(model, request, output)
                    elif args.task == "design":
                        _generate_design(model, request, output)
                    else:
                        _generate_clone(model, request, output)
                else:
                    raise
            print(
                json.dumps(
                    {
                        "ok": True,
                        "output": str(output),
                        "device": device,
                        "kind": args.kind,
                        "task": args.task,
                    }
                ),
                flush=True,
            )
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": str(exc),
                        "device": device,
                        "kind": args.kind,
                        "task": args.task,
                    }
                ),
                flush=True,
            )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--kind", required=True, choices=sorted(MODEL_IDS))
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
