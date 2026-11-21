from __future__ import annotations

import math
import struct
import wave
from pathlib import Path


def wav_has_audible_content(path: Path, *, minimum_peak: float = 0.00005, minimum_rms: float = 0.00001) -> bool:
    """Reject digital/near-digital silence while preserving quiet speech."""
    try:
        with wave.open(str(Path(path)), "rb") as source:
            channels, width = int(source.getnchannels()), int(source.getsampwidth())
            rate, frames = int(source.getframerate()), int(source.getnframes())
            if source.getcomptype() != "NONE" or channels <= 0 or rate <= 0 or frames <= 0 or width not in {1,2,3,4}:
                return False
            maximum = 128.0 if width == 1 else float(1 << (width * 8 - 1))
            peak = sum_squares = 0.0
            count = 0
            while True:
                payload = source.readframes(max(1, rate // 2))
                if not payload:
                    break
                stride = channels * width
                payload = payload[:len(payload) - (len(payload) % stride)]
                if width == 1:
                    samples = (v - 128 for v in payload)
                elif width == 2:
                    samples = (v[0] for v in struct.iter_unpack("<h", payload))
                elif width == 3:
                    def unpack_24(data):
                        for i in range(0, len(data), 3):
                            value = data[i] | (data[i+1] << 8) | (data[i+2] << 16)
                            yield value - 0x1000000 if value & 0x800000 else value
                    samples = unpack_24(payload)
                else:
                    samples = (v[0] for v in struct.iter_unpack("<i", payload))
                for sample in samples:
                    value = float(sample) / maximum
                    peak = max(peak, abs(value))
                    sum_squares += value * value
                    count += 1
            if not count:
                return False
            return peak >= minimum_peak and math.sqrt(sum_squares / count) >= minimum_rms
    except (OSError, EOFError, ValueError, wave.Error, OverflowError, struct.error):
        return False


def provider_uses_qwen_voice(provider, voice: str | None = None) -> bool:
    if str(getattr(provider, "provider_id", "") or "").casefold() == "qwen-character":
        return True
    checker = getattr(provider, "is_qwen_voice", None)
    if callable(checker):
        try:
            return checker(voice) is True
        except Exception:
            return False
    return False
