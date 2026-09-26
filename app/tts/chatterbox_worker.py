from __future__ import annotations

import argparse
from pathlib import Path
import sys

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--backend", default="automatic")
    parser.add_argument("--language", default="en")
    parser.add_argument("--multilingual", action="store_true")
    parser.add_argument("--exaggeration", type=float, default=0.5)
    parser.add_argument("--cfg-weight", type=float, default=0.5)
    args = parser.parse_args()

    text = Path(args.text_file).read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError("The custom voice text chunk is empty.")
    reference = Path(args.reference)
    if not reference.exists():
        raise RuntimeError(f"Reference voice file was not found: {reference}")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    import torch
    import torchaudio as ta
    from chatterbox.tts import ChatterboxTTS
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    if args.backend == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested, but the custom voice runtime cannot access an NVIDIA GPU.")
        device = "cuda"
    elif args.backend == "cpu":
        device = "cpu"
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    model = (ChatterboxMultilingualTTS if args.multilingual else ChatterboxTTS).from_pretrained(device=device)
    kwargs = {
        "audio_prompt_path": str(reference.resolve()),
        "exaggeration": args.exaggeration,
        "cfg_weight": args.cfg_weight,
    }
    if args.multilingual:
        kwargs["language_id"] = args.language or "en"
    wav = model.generate(text, **kwargs)
    ta.save(str(output), wav, model.sr)
    if not output.exists() or output.stat().st_size < 1024:
        raise RuntimeError("Chatterbox did not produce a valid WAV file.")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"RYU_CHATTERBOX_ERROR: {exc}", file=sys.stderr)
        raise
