from __future__ import annotations

from pathlib import Path
import re
import wave


_CLOSERS = '"”»」』)]}’'
_PROFILE_EXTRA_PAUSE_MS = {
    "natural": 0,
    "relaxed": 110,
    "minimal": -70,
    "off": -999999,
}


def _sentence_units(text: str) -> list[str]:
    units: list[str] = []
    current: list[str] = []

    def flush() -> None:
        value = "".join(current).strip()
        if value:
            units.append(value)
        current.clear()

    i = 0
    while i < len(text):
        char = text[i]
        current.append(char)

        if char == "
":
            if i + 1 < len(text) and text[i + 1] == "
":
                current.pop()
                flush()
                i += 1
                continue

        if char in ".!?…":
            j = i + 1
            while j < len(text) and text[j] in _CLOSERS:
                current.append(text[j])
                j += 1
            if j >= len(text) or text[j].isspace():
                flush()
                i = j - 1

        i += 1

    flush()
    return units


def split_for_pacing(
    text: str,
    max_chars: int = 1400,
    max_sentences: int = 2,
) -> list[str]:
    """Split narration into natural TTS units without changing text."""
    text = text.strip()
    if not text:
        return []

    sentences = _sentence_units(text)
    if not sentences:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_chars = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        would_exceed = current and (
            current_chars + len(sentence) + 1 > max_chars
            or len(current) >= max_sentences
        )
        if would_exceed:
            chunks.append(" ".join(current).strip())
            current = []
            current_chars = 0

        if len(sentence) <= max_chars:
            current.append(sentence)
            current_chars += len(sentence) + (1 if current_chars else 0)
            continue

        remaining = sentence
        while len(remaining) > max_chars:
            cut = remaining.rfind(" ", 0, max_chars + 1)
            if cut < max_chars // 2:
                cut = max_chars
            chunks.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        if remaining:
            current.append(remaining)
            current_chars += len(remaining) + (1 if current_chars else 0)

    if current:
        chunks.append(" ".join(current).strip())

    return [chunk for chunk in chunks if chunk]


def pause_after_ms(text: str, profile: str = "natural") -> int:
    """Return a small, deterministic audiobook pause for a TTS unit."""
    profile = (profile or "natural").lower()
    if profile == "off":
        return 0

    stripped = text.strip()
    if not stripped:
        return 0

    end = stripped[-1]
    if end in "!?…":
        base = 360
    elif end == ".":
        base = 290
    elif end in ";:":
        base = 210
    elif end == ",":
        base = 110
    elif end in "—–-":
        base = 170
    else:
        base = 90

    if stripped.endswith(tuple(_CLOSERS)):
        without_closer = stripped.rstrip(_CLOSERS).rstrip()
        if without_closer.endswith(("?", "!", "…")):
            base = 360
        elif without_closer.endswith("."):
            base = 290

    if "

" in stripped:
        base += 140

    base += _PROFILE_EXTRA_PAUSE_MS.get(profile, 0)
    return max(50, base)


def append_silence(path: Path, duration_ms: int) -> None:
    """Append PCM silence to a generated WAV without changing its voice/pitch."""
    if duration_ms <= 0:
        return

    with wave.open(str(path), "rb") as source:
        params = source.getparams()
        frames = source.readframes(source.getnframes())

    if params.comptype != "NONE":
        raise RuntimeError(f"Cannot add narration pacing to compressed WAV: {path.name}")

    silence_frames = max(0, round(params.framerate * duration_ms / 1000.0))
    if silence_frames <= 0:
        return

    silence = b"\x00" * silence_frames * params.nchannels * params.sampwidth
    temp = path.with_suffix(".pacing.wav")
    with wave.open(str(temp), "wb") as target:
        target.setparams(params)
        target.writeframes(frames + silence)
    temp.replace(path)
