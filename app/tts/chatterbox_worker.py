from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys


def _load_model(backend: str, multilingual: bool):
    import torch
    from chatterbox.tts import ChatterboxTTS
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

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

    model_class = ChatterboxMultilingualTTS if multilingual else ChatterboxTTS
    # Chatterbox may print model-loading progress. Keep stdout reserved for the
    # JSON worker protocol so the parent process can reliably read responses.
    with redirect_stdout(sys.stderr):
        model = model_class.from_pretrained(device=device)
    return model, device


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
    model, device = _load_model(args.backend, args.multilingual)
    print(json.dumps({"ready": True, "device": device}), flush=True)
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
            print(json.dumps({"ok": False, "error": str(exc)}), flush=True)
    return 0


def one_shot(args) -> int:
    text = Path(args.text_file).read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError("The custom voice text chunk is empty.")
    reference = Path(args.reference)
    if not reference.exists():
        raise RuntimeError(f"Reference voice file was not found: {reference}")
    output = Path(args.output)
    model, _device = _load_model(args.backend, args.multilingual)
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
        print(f"RYU_CHATTERBOX_ERROR: {exc}", file=sys.stderr)
        raise
