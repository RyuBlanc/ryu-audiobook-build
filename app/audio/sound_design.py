from __future__ import annotations

"""Small, offline procedural music beds and chapter transition cues.

These sounds are synthesized from simple oscillators; the app ships no music
recordings and requires no network/GPU. They are deliberately low-key beds,
not a replacement for a licensed cinematic score. Users can still choose
their own tracks in Manual mode.
"""

from array import array
import math
from pathlib import Path
import re
import sys
import wave


SAMPLE_RATE = 22050
BED_SECONDS = 16.0
TRANSITION_SECONDS = 0.92

# Integer-Hz notes keep the oscillator phases periodic across a loop. The
# gentle pad and slow four-note motif distinguish themes without fighting
# narration. Frequencies are approximate musical pitches by design.
THEMES: dict[str, dict[str, tuple[int, ...]]] = {
    "fantasy": {
        "pad": (110, 147, 175, 220, 262),
        "melody": (330, 392, 440, 392),
    },
    "mystery": {
        "pad": (98, 123, 147, 185, 220),
        "melody": (247, 294, 220, 247),
    },
    "romance": {
        "pad": (110, 139, 165, 220, 277),
        "melody": (330, 370, 330, 294),
    },
    "dark": {
        "pad": (82, 98, 123, 147, 196),
        "melody": (220, 247, 196, 185),
    },
    "action": {
        "pad": (98, 147, 196, 247, 294),
        "melody": (392, 330, 392, 494),
    },
    "calm": {
        "pad": (130, 164, 196, 246, 294),
        "melody": (330, 294, 246, 294),
    },
}

STYLE_ALIASES = {
    "auto": "auto",
    "automatic": "auto",
    "fantasy": "fantasy",
    "fantasy / adventure": "fantasy",
    "fantasy adventure": "fantasy",
    "mystery": "mystery",
    "mystery / suspense": "mystery",
    "mystery suspense": "mystery",
    "romance": "romance",
    "romance / warm": "romance",
    "romance warm": "romance",
    "dark": "dark",
    "dark / horror": "dark",
    "dark horror": "dark",
    "action": "action",
    "action / adventure": "action",
    "action adventure": "action",
    "calm": "calm",
    "calm / reflective": "calm",
    "calm reflective": "calm",
}


def normalize_music_style(style: str | None) -> str:
    value = re.sub(r"\s+", " ", str(style or "auto").strip().casefold())
    return STYLE_ALIASES.get(value, "auto")


def detect_chapter_mood(title: str, text: str, selected_style: str = "auto") -> str:
    """Choose a stable music bed from a manual style or chapter's story cues."""
    requested = normalize_music_style(selected_style)
    if requested != "auto":
        return requested

    sample = f"{title}\n{str(text or '')[:16000]}".casefold()
    rules = (
        ("dark", r"\b(horror|terr(or|ified)|nightmare|blood|corpse|death|murder|scream|demon|curse|cursed|evil|dread|fear|haunt(ed|ing)?)\b"),
        ("action", r"\b(battle|fight|attacked?|attack|sword|warrior|explosion|charge|combat|chase|pursuit|weapon|strike|enemy|enemies)\b"),
        ("mystery", r"\b(mystery|secret|hidden|suspicious|clue|investigat(e|ion)|unknown|strange|shadow|conspiracy|uncover|reveal)\b"),
        ("romance", r"\b(romance|love|lover|kiss|blush|heart|embrace|tender|affection|date|confess(ed|ion)?|beloved)\b"),
        ("calm", r"\b(peaceful|quiet|silence|resting|rested|sleep|dream|moonlight|gentle|serene|reflect(ed|ion)|memory|memories)\b"),
        ("fantasy", r"\b(magic|magical|spell|dragon|kingdom|wizard|witch|summon(ed|ing)?|dungeon|quest|fairy|fantasy|enchant(ed|ment)?)\b"),
    )
    for mood, pattern in rules:
        if re.search(pattern, sample):
            return mood
    return "fantasy"


def _write_stereo_pcm(path: Path, samples: array) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(samples.tobytes())
    return path


def synthesize_music_bed(path: Path | str, mood: str = "fantasy") -> Path:
    """Write a quiet, loopable 16-second ambient music bed as a local WAV."""
    target = Path(path)
    chosen = normalize_music_style(mood)
    if chosen == "auto":
        chosen = "fantasy"
    theme = THEMES[chosen]
    pads = theme["pad"]
    melody = theme["melody"]
    frame_count = int(SAMPLE_RATE * BED_SECONDS)
    frames_per_note = frame_count // len(melody)
    samples = array("h")

    for index in range(frame_count):
        t = index / SAMPLE_RATE
        note_index = min(len(melody) - 1, index // frames_per_note)
        within_note = (index % frames_per_note) / SAMPLE_RATE
        note_duration = frames_per_note / SAMPLE_RATE
        attack = min(1.0, within_note / 0.45)
        release = min(1.0, max(0.0, (note_duration - within_note) / 0.70))
        note_envelope = attack * release

        # Slow modulation periods divide the complete loop, so the end joins
        # the beginning smoothly when FFmpeg repeats the bed.
        breathe = 0.78 + 0.12 * math.sin(2.0 * math.pi * t / 8.0)
        pulse = 0.91 + 0.05 * math.sin(2.0 * math.pi * t / 4.0)
        pad = sum(
            math.sin(2.0 * math.pi * frequency * t) / (1.0 + slot * 0.55)
            for slot, frequency in enumerate(pads)
        ) / 3.1
        lead_frequency = melody[note_index]
        lead = (
            math.sin(2.0 * math.pi * lead_frequency * t)
            + 0.22 * math.sin(2.0 * math.pi * (lead_frequency * 2) * t)
        ) * note_envelope
        # Quiet by default: users control the final background bed level in UI.
        value = (pad * breathe * pulse * 0.055) + (lead * 0.018)
        left = max(-0.90, min(0.90, value))
        right = max(-0.90, min(0.90, value * 0.96))
        samples.append(int(left * 32767))
        samples.append(int(right * 32767))

    return _write_stereo_pcm(target, samples)


def synthesize_chapter_transition(
    path: Path | str,
    mood: str = "fantasy",
    duration_seconds: float = TRANSITION_SECONDS,
) -> Path:
    """Write a soft, short rising chime to separate chapters."""
    target = Path(path)
    chosen = normalize_music_style(mood)
    if chosen == "auto":
        chosen = "fantasy"
    melody = THEMES[chosen]["melody"]
    duration = max(0.45, min(2.0, float(duration_seconds)))
    frame_count = int(SAMPLE_RATE * duration)
    samples = array("h")

    for index in range(frame_count):
        t = index / SAMPLE_RATE
        progress = min(0.999999, t / duration)
        attack = min(1.0, t / 0.025)
        release = min(1.0, max(0.0, (duration - t) / 0.12))
        decay = math.exp(-4.8 * progress)
        fundamental = melody[0] + (melody[2] - melody[0]) * progress
        tone = (
            math.sin(2.0 * math.pi * fundamental * t)
            + 0.38 * math.sin(2.0 * math.pi * (fundamental * 1.5) * t)
            + 0.16 * math.sin(2.0 * math.pi * (fundamental * 2.0) * t)
        )
        value = tone * attack * release * decay * 0.12
        value = max(-0.6, min(0.6, value))
        samples.append(int(value * 32767))
        samples.append(int(value * 0.98 * 32767))

    return _write_stereo_pcm(target, samples)
