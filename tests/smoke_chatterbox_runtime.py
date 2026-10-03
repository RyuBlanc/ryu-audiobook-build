from __future__ import annotations

import math
from pathlib import Path
from tempfile import TemporaryDirectory
import wave

from app.tts.chatterbox_worker import _generate, _load_model


def _make_reference(path: Path) -> None:
    # A deterministic short audio reference keeps this smoke test self-contained.
    # The goal is to exercise model loading, conditioning, synthesis and WAV output.
    rate = 24000
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        # Chatterbox-Nano/Turbo requires a reference longer than 5 seconds.
    # Use a deterministic 6-second reference so the smoke test exercises the
    # actual model constraint instead of failing on an invalid fixture.
    for i in range(rate * 6):
            sample = int(0.06 * 32767 * math.sin(2 * math.pi * 220 * i / rate))
            frames.extend(int(sample).to_bytes(2, "little", signed=True))
        handle.writeframes(frames)


def main() -> None:
    with TemporaryDirectory(prefix="ryu-chatterbox-smoke-") as temp:
        root = Path(temp)
        reference = root / "reference.wav"
        output = root / "output.wav"
        _make_reference(reference)

        model, device, variant = _load_model("cpu", False, "nano")
        _generate(
            model,
            "This is a short Ryu's Audiobook custom voice runtime test.",
            output,
            reference,
            "en",
            False,
            0.5,
            0.35,
        )

        if not output.is_file() or output.stat().st_size < 1024:
            raise RuntimeError(f"Chatterbox produced invalid output: {output}")
        print(f"CHATTERBOX_RUNTIME_SYNTHESIS=PASS device={device} variant={variant} bytes={output.stat().st_size}")


if __name__ == "__main__":
    main()
