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
}



def _load_model(kind: str, backend: str, root: Path):
    import torch
    from qwen_tts import Qwen3TTSModel

    model_path = root / kind
    if not model_path.exists():
        raise RuntimeError(f"Qwen model is not installed: {MODEL_IDS[kind]}")

    if backend == "cpu":
        device = "cpu"
    else:
        device = "cuda:0" if torch.cuda.is_available() else "cpu"

    dtype = torch.float16 if device.startswith("cuda") else torch.float32
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
    return "out of memory" in message and ("cuda" in message or "cublas" in message)


def _generate_custom(model, request: dict, output: Path) -> None:
    import soundfile as sf

    speaker = str(request.get("speaker") or "").strip()
    if not speaker:
        raise RuntimeError("A Qwen custom voice speaker is required.")
    wavs, sr = model.generate_custom_voice(
        text=str(request.get("text") or ""),
        language=str(request.get("language") or "English"),
        speaker=speaker,
        instruct=str(request.get("instruct") or ""),
    )
    if not wavs:
        raise RuntimeError("Qwen did not return audio.")
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), wavs[0], sr)


def _generate_clone(model, request: dict, output: Path) -> None:
    import soundfile as sf

    ref_audio = Path(str(request.get("reference") or ""))
    if not ref_audio.is_file():
        raise RuntimeError(f"Qwen reference audio was not found: {ref_audio}")
    ref_text = str(request.get("ref_text") or "").strip()
    kwargs = {
        "text": str(request.get("text") or ""),
        "language": str(request.get("language") or "English"),
        "ref_audio": str(ref_audio),
    }
    if ref_text:
        kwargs["ref_text"] = ref_text
    else:
        kwargs["x_vector_only_mode"] = True
    wavs, sr = model.generate_voice_clone(**kwargs)
    if not wavs:
        raise RuntimeError("Qwen did not return cloned audio.")
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
    print(json.dumps({"ready": True, "device": device, "model": MODEL_IDS[args.kind]}), flush=True)
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
                elif args.task == "clone":
                    _generate_clone(model, request, output)
                else:
                    raise RuntimeError(f"Unsupported Qwen task: {args.task}")
            except Exception as exc:
                if _is_cuda_oom(exc) and device.startswith("cuda"):
                    # 4GB-class GPUs can occasionally run out of memory because
                    # Windows desktop apps consume VRAM. Reload the same model
                    # on CPU rather than failing the audiobook generation.
                    import gc
                    gc.collect()
                    model, device = _load_model(args.kind, "cpu", root)
                    if args.task == "custom":
                        _generate_custom(model, request, output)
                    else:
                        _generate_clone(model, request, output)
                else:
                    raise
            print(json.dumps({"ok": True, "output": str(output), "device": device}), flush=True)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": str(exc), "device": device}), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--kind", required=True)
    parser.add_argument("--task", choices=["custom", "clone"], default="custom")
    parser.add_argument("--backend", default="automatic")
    parser.add_argument("--models-root", required=True)
    args = parser.parse_args()
    if args.server:
        return server(args)
    raise SystemExit("Use --server.")


if __name__ == "__main__":
    raise SystemExit(main())
