from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from app.tts.providers.kokoro import KokoroProvider


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "bundled_models" / "kokoro" / "kokoro-v1.0.fp16.onnx"
VOICES = ROOT / "bundled_models" / "kokoro" / "voices-v1.0.bin"

VOICES_TO_TEST = ("af_heart", "am_michael", "bf_emma", "bm_george", "jf_alpha")


def main() -> None:
    if not MODEL.is_file() or not VOICES.is_file():
        raise RuntimeError(f"Kokoro assets are missing: {MODEL} / {VOICES}")

    provider = KokoroProvider(model_path=MODEL, voices_path=VOICES)
    print(f"Kokoro model={MODEL} size={MODEL.stat().st_size}")
    print(f"Kokoro voices={VOICES} size={VOICES.stat().st_size}")

    with TemporaryDirectory(prefix="ryu-kokoro-smoke-") as tmp:
        root = Path(tmp)
        for voice in VOICES_TO_TEST:
            output = root / f"{voice}.wav"
            provider.synthesize(
                "This is a short Ryu's Audiobook natural voice test.",
                output,
                voice=voice,
            )
            if not output.is_file() or output.stat().st_size < 1024:
                raise RuntimeError(f"Kokoro produced invalid output for {voice}: {output}")
            print(f"Kokoro {voice}: PASS ({output.stat().st_size} bytes)")

    print("Kokoro runtime synthesis smoke test PASSED.")


if __name__ == "__main__":
    sys.exit(main())
