from __future__ import annotations

"""Local, deterministic soundtrack recipes for Ryu's Audiobook.

The catalogue is recipe-based, not 1,000 bundled recordings: combinations of
six story moods, eight sound textures, seven tempos and three harmonic arcs
produce 1,008 repeatable music variations. Tracks are generated only when
needed and require neither a network connection nor a GPU.
"""

from array import array
import hashlib
import math
import random
from pathlib import Path
import re
import sys
import wave


SAMPLE_RATE = 22050
PAGE_TURN_SECONDS = 0.62
ENDING_SECONDS = 2.65
TRANSITION_SECONDS = PAGE_TURN_SECONDS  # compatibility alias

THEMES: dict[str, dict[str, object]] = {
    "fantasy": {"root": 50, "scale": (0, 2, 4, 5, 7, 9, 11), "melody": (0, 2, 4, 2, 5, 4, 2, 1, 0, 2, 4, 6, 5, 4, 2, 0)},
    "mystery": {"root": 45, "scale": (0, 2, 3, 5, 7, 8, 10), "melody": (0, 2, 5, 4, 2, 1, 3, 2, 0, 3, 5, 4, 1, 2, 0, 0)},
    "romance": {"root": 48, "scale": (0, 2, 4, 5, 7, 9, 11), "melody": (0, 2, 4, 6, 5, 4, 2, 1, 0, 2, 4, 5, 4, 2, 1, 0)},
    "dark": {"root": 38, "scale": (0, 2, 3, 5, 7, 8, 10), "melody": (0, 3, 5, 4, 2, 3, 1, 0, 0, 2, 4, 3, 1, 2, 0, 0)},
    "action": {"root": 43, "scale": (0, 2, 4, 5, 7, 9, 10), "melody": (0, 4, 2, 5, 4, 6, 5, 2, 0, 2, 4, 6, 5, 4, 2, 0)},
    "calm": {"root": 48, "scale": (0, 2, 4, 5, 7, 9, 11), "melody": (0, 2, 4, 2, 1, 2, 4, 5, 4, 2, 1, 0, 2, 4, 2, 0)},
}

STYLE_ALIASES = {
    "auto": "auto", "automatic": "auto",
    "fantasy": "fantasy", "fantasy / adventure": "fantasy", "fantasy adventure": "fantasy",
    "mystery": "mystery", "mystery / suspense": "mystery", "mystery suspense": "mystery",
    "romance": "romance", "romance / warm": "romance", "romance warm": "romance",
    "dark": "dark", "dark / horror": "dark", "dark horror": "dark",
    "action": "action", "action / adventure": "action", "action adventure": "action",
    "calm": "calm", "calm / reflective": "calm", "calm reflective": "calm",
}

# Eight deliberately distinct timbral envelopes/partials, seven tempo choices,
# and three related chord progressions per story mood.
TEXTURES: tuple[dict[str, object], ...] = (
    {"name": "Warm cinematic pad", "harmonics": (1.0, 0.24, 0.08, 0.025), "envelope": "pad", "pad": 0.13, "lead": 0.030},
    {"name": "Soft plucked strings", "harmonics": (1.0, 0.48, 0.22, 0.08), "envelope": "pluck", "pad": 0.085, "lead": 0.050},
    {"name": "Glass bells", "harmonics": (1.0, 0.72, 0.42, 0.20, 0.08), "envelope": "bell", "pad": 0.070, "lead": 0.042},
    {"name": "Cinematic strings", "harmonics": (1.0, 0.32, 0.19, 0.11, 0.06), "envelope": "bow", "pad": 0.12, "lead": 0.034},
    {"name": "Harp-like arpeggio", "harmonics": (1.0, 0.54, 0.26, 0.10), "envelope": "pluck", "pad": 0.075, "lead": 0.047},
    {"name": "Soft piano tone", "harmonics": (1.0, 0.38, 0.20, 0.095, 0.035), "envelope": "piano", "pad": 0.095, "lead": 0.041},
    {"name": "Warm organ", "harmonics": (1.0, 0.47, 0.23, 0.12, 0.06), "envelope": "organ", "pad": 0.12, "lead": 0.031},
    {"name": "Airy atmospheric tone", "harmonics": (1.0, 0.16, 0.06, 0.02), "envelope": "air", "pad": 0.13, "lead": 0.028},
)
TEMPOS = (54, 60, 66, 72, 78, 84, 90)
PROGRESSIONS = ((0, 4, 5, 3), (0, 5, 3, 4), (0, 3, 4, 0))
VARIATIONS_PER_MOOD = len(TEXTURES) * len(TEMPOS) * len(PROGRESSIONS)
MUSIC_CATALOGUE_SIZE = len(THEMES) * VARIATIONS_PER_MOOD  # exactly 1,008
MOOD_ORDER = tuple(THEMES)


def normalize_music_style(style: str | None) -> str:
    value = re.sub(r"\s+", " ", str(style or "auto").strip().casefold())
    return STYLE_ALIASES.get(value, "auto")


def detect_chapter_mood(title: str, text: str, selected_style: str = "auto") -> str:
    """Select a coherent, stable music mood from strong story-language cues."""
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


def select_music_variation(title: str, text: str, mood: str) -> int:
    """Choose a reproducible variation within the selected mood, never randomly."""
    chosen = normalize_music_style(mood)
    if chosen == "auto":
        chosen = detect_chapter_mood(title, text)
    seed_text = f"{chosen}\0{title.strip()}\0{str(text or '')[:4096]}".encode("utf-8", errors="replace")
    digest = hashlib.blake2b(seed_text, digest_size=8).digest()
    return int.from_bytes(digest, "big") % VARIATIONS_PER_MOOD


def music_variation_info(mood: str, variation_index: int) -> dict[str, object]:
    """Describe one of 1,008 deterministic, locally generated recipes."""
    chosen = normalize_music_style(mood)
    if chosen == "auto":
        chosen = "fantasy"
    local_index = int(variation_index) % VARIATIONS_PER_MOOD
    texture_index = local_index % len(TEXTURES)
    tempo_index = (local_index // len(TEXTURES)) % len(TEMPOS)
    progression_index = (local_index // (len(TEXTURES) * len(TEMPOS))) % len(PROGRESSIONS)
    global_id = MOOD_ORDER.index(chosen) * VARIATIONS_PER_MOOD + local_index + 1
    return {
        "id": global_id,
        "mood": chosen,
        "variation_index": local_index,
        "texture": TEXTURES[texture_index]["name"],
        "tempo_bpm": TEMPOS[tempo_index],
        "harmony": progression_index + 1,
        "catalogue_size": MUSIC_CATALOGUE_SIZE,
    }


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


def _midi_hz(midi_note: int) -> float:
    return 440.0 * (2.0 ** ((float(midi_note) - 69.0) / 12.0))


def _scale_note(root: int, scale: tuple[int, ...], degree: int) -> int:
    octave, index = divmod(int(degree), len(scale))
    return root + scale[index] + octave * 12


def _pad_value(t: float, frequencies: tuple[float, ...]) -> float:
    # Four quiet chord tones with fixed weights; no random note selection.
    return (
        0.43 * math.sin(2.0 * math.pi * frequencies[0] * t)
        + 0.27 * math.sin(2.0 * math.pi * frequencies[1] * t)
        + 0.20 * math.sin(2.0 * math.pi * frequencies[2] * t)
        + 0.10 * math.sin(2.0 * math.pi * frequencies[3] * t)
    )


def synthesize_music_bed(
    path: Path | str,
    mood: str = "fantasy",
    variation_index: int = 0,
) -> Path:
    """Create a looping, mood-matched BGM from a deterministic catalogue recipe.

    The same mood/index always produces the same theme. There are 168 recipes
    in each of six mood families: 8 timbres × 7 tempos × 3 harmonic arcs.
    """
    target = Path(path)
    chosen = normalize_music_style(mood)
    if chosen == "auto":
        chosen = "fantasy"
    theme = THEMES[chosen]
    local_index = int(variation_index) % VARIATIONS_PER_MOOD
    texture_index = local_index % len(TEXTURES)
    tempo_index = (local_index // len(TEXTURES)) % len(TEMPOS)
    progression_index = (local_index // (len(TEXTURES) * len(TEMPOS))) % len(PROGRESSIONS)
    texture = TEXTURES[texture_index]
    scale = theme["scale"]
    root = int(theme["root"])
    motif = theme["melody"]
    progression = PROGRESSIONS[progression_index]
    tempo = TEMPOS[tempo_index]
    frames_per_beat = max(1, round(SAMPLE_RATE * 60.0 / tempo))
    frames_per_bar = frames_per_beat * 4
    frame_count = frames_per_beat * 16
    duration = frame_count / SAMPLE_RATE
    harmonics = tuple(float(x) for x in texture["harmonics"])

    chord_notes: list[tuple[float, float, float, float]] = []
    melody_frequencies: list[float] = []
    for bar in range(4):
        degree = progression[bar]
        chord_root = _scale_note(root, scale, degree)
        third = _scale_note(root, scale, degree + 2)
        fifth = _scale_note(root, scale, degree + 4)
        chord_notes.append((
            _midi_hz(chord_root - 12),
            _midi_hz(chord_root),
            _midi_hz(third),
            _midi_hz(fifth),
        ))
    for beat in range(16):
        bar = beat // 4
        degree = progression[bar] + motif[beat]
        melody_frequencies.append(_midi_hz(_scale_note(root + 24, scale, degree)))

    samples = array("h")
    sample_scale = 32767.0
    for index in range(frame_count):
        t = index / SAMPLE_RATE
        beat_index = (index // frames_per_beat) % 16
        bar_index = beat_index // 4
        local_beat = (index % frames_per_beat) / frames_per_beat
        current_chord = chord_notes[bar_index]
        current_pad = _pad_value(t, current_chord)
        detuned_chord = tuple(freq * 1.003 for freq in current_chord)
        current_pad = current_pad * 0.82 + _pad_value(t, detuned_chord) * 0.18

        # Blend the first ~140 ms of a new bar with the previous chord to
        # avoid hard harmonic edges. This is deterministic and cheap.
        bar_frame = index % frames_per_bar
        blend_frames = max(1, int(SAMPLE_RATE * 0.14))
        if bar_frame < blend_frames:
            previous_bar = (bar_index - 1) % 4
            alpha = bar_frame / blend_frames
            previous_chord = chord_notes[previous_bar]
            previous_pad = (
                _pad_value(t, previous_chord) * 0.82
                + _pad_value(t, tuple(freq * 1.003 for freq in previous_chord)) * 0.18
            )
            pad = previous_pad * (1.0 - alpha) + current_pad * alpha
        else:
            pad = current_pad

        lead_frequency = melody_frequencies[beat_index]
        lead = 0.0
        for harmonic_number, weight in enumerate(harmonics, start=1):
            if weight > 0.003:
                lead += weight * math.sin(2.0 * math.pi * lead_frequency * harmonic_number * t)
        envelope = str(texture["envelope"])
        attack = min(1.0, local_beat / (0.09 if envelope in {"pad", "bow", "organ", "air"} else 0.025))
        release = min(1.0, (1.0 - local_beat) / (0.20 if envelope in {"pad", "bow", "organ", "air"} else 0.13))
        if envelope == "pluck":
            sustain = math.exp(-3.2 * local_beat)
        elif envelope == "bell":
            sustain = math.exp(-2.6 * local_beat)
        elif envelope == "piano":
            sustain = 0.36 + 0.64 * math.exp(-2.0 * local_beat)
        elif envelope == "bow":
            sustain = 0.45 + 0.55 * min(1.0, local_beat / 0.22)
        elif envelope == "air":
            sustain = 0.88 + 0.12 * math.sin(math.pi * local_beat)
        else:
            sustain = 1.0
        lead *= attack * release * sustain

        arp_patterns = (
            (0, 2, 4, 2), (0, 3, 4, 1), (0, 2, 5, 3), (0, 4, 2, 5),
        )
        arp_degree = progression[bar_index] + arp_patterns[texture_index % len(arp_patterns)][beat_index % 4]
        arp_frequency = _midi_hz(_scale_note(root + 12, scale, arp_degree))
        arp_envelope = math.exp(-4.3 * local_beat) * min(1.0, local_beat / 0.018 if local_beat else 0.0)
        arp = math.sin(2.0 * math.pi * arp_frequency * t) * arp_envelope
        bass_frequency = current_chord[0]
        bass_pulse = math.sin(2.0 * math.pi * bass_frequency * t) * (0.78 + 0.22 * math.sin(2.0 * math.pi * t / 3.2))
        arp_gain = (0.060, 0.095, 0.052, 0.040, 0.100, 0.074, 0.035, 0.024)[texture_index]
        value = (
            pad * float(texture["pad"]) * 1.48
            + lead * float(texture["lead"]) * 1.45
            + arp * arp_gain
            + bass_pulse * 0.038
        )
        # Soft master ceiling leaves headroom for narration and SFX in the mix.
        left = max(-0.72, min(0.72, value))
        right = max(-0.72, min(0.72, value * 0.985))
        samples.append(int(left * sample_scale))
        samples.append(int(right * sample_scale))

    # Tiny edge fades guard against a click at a loop boundary without adding
    # a noticeable silence each time the short bed is repeated by FFmpeg.
    fade_frames = min(int(SAMPLE_RATE * 0.025), frame_count // 8)
    for frame in range(fade_frames):
        gain_in = frame / max(1, fade_frames)
        gain_out = (fade_frames - frame - 1) / max(1, fade_frames)
        samples[frame * 2] = int(samples[frame * 2] * gain_in)
        samples[frame * 2 + 1] = int(samples[frame * 2 + 1] * gain_in)
        out_index = (frame_count - fade_frames + frame) * 2
        samples[out_index] = int(samples[out_index] * gain_out)
        samples[out_index + 1] = int(samples[out_index + 1] * gain_out)

    return _write_stereo_pcm(target, samples)


def synthesize_chapter_transition(
    path: Path | str,
    mood: str = "fantasy",
    duration_seconds: float = TRANSITION_SECONDS,
    variation_index: int = 0,
) -> Path:
    """Create a short, quiet, mood-matched chapter transition chime."""
    target = Path(path)
    chosen = normalize_music_style(mood)
    if chosen == "auto":
        chosen = "fantasy"
    theme = THEMES[chosen]
    scale = theme["scale"]
    root = int(theme["root"])
    local_index = int(variation_index) % VARIATIONS_PER_MOOD
    progression_index = (local_index // (len(TEXTURES) * len(TEMPOS))) % len(PROGRESSIONS)
    progression = PROGRESSIONS[progression_index]
    texture_index = local_index % len(TEXTURES)
    texture = TEXTURES[texture_index]
    base = _midi_hz(_scale_note(root + 24, scale, progression[0]))
    upper = _midi_hz(_scale_note(root + 24, scale, progression[0] + 2))
    duration = max(0.45, min(2.0, float(duration_seconds)))
    frame_count = int(SAMPLE_RATE * duration)
    samples = array("h")
    for index in range(frame_count):
        t = index / SAMPLE_RATE
        progress = min(0.999999, t / duration)
        attack = min(1.0, t / 0.025)
        release = min(1.0, max(0.0, (duration - t) / 0.12))
        decay = math.exp(-4.8 * progress)
        fundamental = base + (upper - base) * progress
        tone = (
            math.sin(2.0 * math.pi * fundamental * t)
            + 0.32 * math.sin(2.0 * math.pi * fundamental * 2.0 * t)
            + 0.12 * math.sin(2.0 * math.pi * fundamental * 3.0 * t)
        )
        value = tone * attack * release * decay * 0.105
        samples.append(int(max(-0.5, min(0.5, value)) * 32767))
        samples.append(int(max(-0.5, min(0.5, value * 0.98)) * 32767))
    return _write_stereo_pcm(target, samples)



def synthesize_page_turn(path: Path | str, variation_index: int = 0) -> Path:
    """Generate a short, soft paper-flutter/page-turn cue for chapter boundaries."""
    target = Path(path)
    duration = PAGE_TURN_SECONDS
    frame_count = max(1, int(SAMPLE_RATE * duration))
    rng = random.Random(f"ryu-page-turn:{int(variation_index) % 168}")
    samples = array("h")
    low_noise = 0.0
    mid_noise = 0.0
    for index in range(frame_count):
        t = index / SAMPLE_RATE
        pos = t / duration
        noise = rng.uniform(-1.0, 1.0)
        low_noise = low_noise * 0.91 + noise * 0.09
        mid_noise = mid_noise * 0.58 + noise * 0.42
        sweep = max(0.0, math.sin(math.pi * pos)) ** 0.82
        flutter = 0.58 + 0.22 * math.sin(2.0 * math.pi * (13.0 + (variation_index % 5)) * t)
        grain = noise * (0.018 if index % 997 < 3 else 0.0)
        value = sweep * flutter * (low_noise * 0.48 + mid_noise * 0.16) + grain
        value *= min(1.0, t / 0.045) * min(1.0, max(0.0, (duration - t) / 0.09)) * 0.30
        value = max(-0.35, min(0.35, value))
        sample = int(value * 32767.0)
        samples.append(sample)
        samples.append(int(sample * 0.94))
    return _write_stereo_pcm(target, samples)


def synthesize_audiobook_ending(
    path: Path | str,
    mood: str = "fantasy",
    variation_index: int = 0,
    duration_seconds: float = ENDING_SECONDS,
) -> Path:
    """Generate a resolving end cue; unlike a chapter turn, it closes the book."""
    target = Path(path)
    chosen = normalize_music_style(mood)
    if chosen == "auto":
        chosen = "fantasy"
    theme = THEMES[chosen]
    scale = theme["scale"]
    root = int(theme["root"])
    local = int(variation_index) % VARIATIONS_PER_MOOD
    duration = max(1.8, min(4.0, float(duration_seconds)))
    frame_count = max(1, int(SAMPLE_RATE * duration))
    notes = (
        _midi_hz(_scale_note(root + 12, scale, 0)),
        _midi_hz(_scale_note(root + 12, scale, 4)),
        _midi_hz(_scale_note(root + 24, scale, 0)),
    )
    boundaries = (0.0, 0.38, 0.63, 1.0)
    samples = array("h")
    phase_shift = (local % 7) * 0.006
    for index in range(frame_count):
        t = index / SAMPLE_RATE
        pos = t / duration
        segment = 0 if pos < boundaries[1] else 1 if pos < boundaries[2] else 2
        segment_end = boundaries[segment + 1] * duration
        local_t = max(0.0, t - boundaries[segment] * duration)
        note = notes[segment]
        attack = min(1.0, local_t / (0.10 if segment < 2 else 0.18))
        release_window = 0.48 if segment == 2 else 0.12
        envelope = attack * min(1.0, max(0.0, (segment_end - t) / release_window))
        if segment == 2:
            envelope = attack * min(1.0, max(0.0, (duration - t) / 0.48))
        fade = min(1.0, t / 0.04) * min(1.0, max(0.0, (duration - t) / 0.48))
        fundamental = math.sin(2.0 * math.pi * note * (t + phase_shift))
        octave = math.sin(2.0 * math.pi * note * 2.0 * (t + phase_shift)) * 0.22
        fifth_harmonic = math.sin(2.0 * math.pi * note * 1.5 * (t + phase_shift)) * 0.07
        shimmer = math.sin(2.0 * math.pi * (note * 2.01) * t) * 0.025 * (1.0 - pos)
        value = (fundamental * 0.48 + octave + fifth_harmonic + shimmer) * envelope * fade * 0.13
        value = max(-0.40, min(0.40, value))
        sample = int(value * 32767.0)
        samples.append(sample)
        samples.append(int(sample * 0.97))
    return _write_stereo_pcm(target, samples)
