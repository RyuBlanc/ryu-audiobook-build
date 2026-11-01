from __future__ import annotations

"""Original offline cinematic/anime-style soundtrack and book-cue synthesizer.

Music is procedurally composed from rhythmic motifs, ostinato patterns, bass,
hybrid percussion, sustained strings and bright lead layers. It does not copy
existing anime, film, or audio-drama scores. Every track renders locally and
deterministically; no network, cloud service, GPU, or external music pack is
required.
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
OPENING_SECONDS = 1.18
PAGE_TURN_SECONDS = 0.62
ENDING_SECONDS = 2.65
TRANSITION_SECONDS = PAGE_TURN_SECONDS  # compatibility alias


THEMES: dict[str, dict[str, object]] = {
    "fantasy": {
        "label": "Epic Anime Fantasy",
        "root": 50, "scale": (0, 2, 4, 5, 7, 9, 11),
        "motif": (0, 4, 2, 5, 4, 2, 6, 5, 4, 2, 0, 3, 5, 4, 2, 7),
        "bass": (0, 0, 3, 4),
    },
    "mystery": {
        "label": "Cinematic Mystery / Suspense",
        "root": 45, "scale": (0, 2, 3, 5, 7, 8, 10),
        "motif": (0, 3, 5, 4, 2, 1, 3, 6, 5, 3, 2, 0, 3, 5, 1, 0),
        "bass": (0, 0, 5, 3),
    },
    "romance": {
        "label": "Emotional Cinematic Drama",
        "root": 48, "scale": (0, 2, 4, 5, 7, 9, 11),
        "motif": (0, 2, 4, 6, 5, 4, 2, 1, 0, 2, 4, 5, 7, 5, 4, 2),
        "bass": (0, 4, 5, 3),
    },
    "dark": {
        "label": "Dark Supernatural Tension",
        "root": 38, "scale": (0, 2, 3, 5, 7, 8, 10),
        "motif": (0, 3, 5, 2, 1, 4, 3, 0, 2, 6, 5, 3, 1, 0, 5, 2),
        "bass": (0, 0, 1, 5),
    },
    "action": {
        "label": "Heroic Anime Battle",
        "root": 43, "scale": (0, 2, 4, 5, 7, 9, 10),
        "motif": (0, 4, 2, 5, 4, 6, 5, 2, 0, 2, 4, 6, 5, 4, 2, 7),
        "bass": (0, 0, 4, 5),
    },
    "calm": {
        "label": "Adventure Journey / Exploration",
        "root": 48, "scale": (0, 2, 4, 7, 9),
        "motif": (0, 2, 4, 2, 1, 2, 4, 5, 4, 2, 1, 0, 2, 4, 2, 0),
        "bass": (0, 0, 4, 2),
    },
    "anime-rock": {
        "label": "High-Energy Anime Rock",
        "root": 45, "scale": (0, 2, 3, 5, 7, 9, 10),
        "motif": (0, 0, 3, 5, 7, 5, 3, 2, 0, 3, 5, 8, 7, 5, 3, 2),
        "bass": (0, 0, 5, 3),
    },
    "sci-fi": {
        "label": "Futuristic Sword-Fantasy / Sci-Fi",
        "root": 42, "scale": (0, 1, 5, 7, 8, 10),
        "motif": (0, 3, 5, 2, 4, 1, 5, 3, 0, 4, 2, 5, 3, 1, 4, 0),
        "bass": (0, 0, 5, 1),
    },
}

STYLE_ALIASES = {
    "auto": "auto", "automatic": "auto",
    "fantasy": "fantasy", "fantasy / adventure": "fantasy", "epic anime fantasy": "fantasy",
    "mystery": "mystery", "mystery / suspense": "mystery", "cinematic mystery / suspense": "mystery",
    "romance": "romance", "romance / warm": "romance", "emotional cinematic drama": "romance",
    "dark": "dark", "dark / horror": "dark", "dark supernatural tension": "dark",
    "action": "action", "action / adventure": "action", "heroic anime battle": "action",
    "calm": "calm", "calm / reflective": "calm", "adventure journey / exploration": "calm",
    "anime-rock": "anime-rock", "anime rock": "anime-rock", "high-energy anime rock": "anime-rock",
    "sci-fi": "sci-fi", "sci fi": "sci-fi", "futuristic sword-fantasy / sci-fi": "sci-fi",
}

# The catalogue varies rhythmic arrangement, instrumental envelope, tempo and
# motif rotation. There are no user-facing chord-progression/harmony recipes.
TEXTURES: tuple[dict[str, object], ...] = (
    {"name": "Epic String Ostinato + Taiko", "lead": 0.15, "strings": 0.22, "bass": 0.15, "drums": 0.29, "arp": 0.09, "pad": 0.07, "sustain": 0.50},
    {"name": "Heroic Brass + Trailer Hits", "lead": 0.25, "strings": 0.12, "bass": 0.18, "drums": 0.34, "arp": 0.04, "pad": 0.04, "sustain": 0.24},
    {"name": "Anime Rock Pulse", "lead": 0.20, "strings": 0.09, "bass": 0.25, "drums": 0.32, "arp": 0.12, "pad": 0.03, "sustain": 0.18},
    {"name": "Hybrid Orchestral Drive", "lead": 0.17, "strings": 0.17, "bass": 0.20, "drums": 0.32, "arp": 0.07, "pad": 0.06, "sustain": 0.30},
    {"name": "Magic Arpeggio + Drums", "lead": 0.15, "strings": 0.10, "bass": 0.11, "drums": 0.22, "arp": 0.26, "pad": 0.12, "sustain": 0.15},
    {"name": "Emotional Strings + Piano", "lead": 0.17, "strings": 0.27, "bass": 0.11, "drums": 0.13, "arp": 0.12, "pad": 0.16, "sustain": 0.78},
    {"name": "Cinematic Synth Sequence", "lead": 0.19, "strings": 0.08, "bass": 0.19, "drums": 0.24, "arp": 0.22, "pad": 0.07, "sustain": 0.20},
    {"name": "Dark Low Drums + Strings", "lead": 0.12, "strings": 0.18, "bass": 0.24, "drums": 0.30, "arp": 0.04, "pad": 0.12, "sustain": 0.44},
)
TEMPOS = (84, 96, 108, 120, 132, 144, 156)
ARRANGEMENTS: tuple[dict[str, object], ...] = (
    {"name": "Driving Cinematic Pulse", "kick": (0, 4), "snare": (2, 6), "extra": (3, 7)},
    {"name": "Rolling Double-Time", "kick": (0, 2, 4, 6), "snare": (2, 6), "extra": (1, 3, 5, 7)},
    {"name": "Syncopated Battle Drive", "kick": (0, 3, 4, 7), "snare": (2, 5), "extra": (1, 6)},
)
VARIATIONS_PER_MOOD = len(TEXTURES) * len(TEMPOS) * len(ARRANGEMENTS)
MUSIC_CATALOGUE_SIZE = len(THEMES) * VARIATIONS_PER_MOOD  # 1,344
MOOD_ORDER = tuple(THEMES)

CUE_STYLE_LABELS = {
    "classic-book": "Classic Hardcover • opening / page flip / close",
    "magical-tome": "Magical Tome • paper / shimmer / close",
    "cinematic-whoosh": "Cinematic Whoosh • sweep / impact / resolve",
    "soft-pages": "Soft Pages • subtle paper sounds",
    "custom": "Custom Audio Set • use my own three sounds",
}
GENERATED_CUE_STYLES = ("classic-book", "magical-tome", "cinematic-whoosh", "soft-pages")


def normalize_music_style(style: str | None) -> str:
    value = re.sub(r"\s+", " ", str(style or "auto").strip().casefold())
    return STYLE_ALIASES.get(value, "auto")


def normalize_cue_style(style: str | None) -> str:
    value = str(style or "classic-book").strip().casefold()
    return value if value in CUE_STYLE_LABELS else "classic-book"


def detect_chapter_mood(title: str, text: str, selected_style: str = "auto") -> str:
    """Map story cues to an original soundtrack family, not an existing score."""
    requested = normalize_music_style(selected_style)
    if requested != "auto":
        return requested
    sample = f"{title}\n{str(text or '')[:16000]}".casefold()
    rules = (
        ("sci-fi", r"\b(space|spaceship|starship|android|cyber|quantum|hologram|laser|galaxy|system|terminal|technology|futuristic|digital|mecha)\b"),
        ("dark", r"\b(horror|terr(or|ified)|nightmare|blood|corpse|death|murder|scream|demon|curse|cursed|evil|dread|fear|haunt(ed|ing)?)\b"),
        ("anime-rock", r"\b(opening theme|run faster|rebellion|rival|resolve|training|awakening|limit break|power up|surpass|determination)\b"),
        ("action", r"\b(battle|fight|attacked?|attack|sword|warrior|explosion|charge|combat|chase|pursuit|weapon|strike|enemy|enemies|duel)\b"),
        ("mystery", r"\b(mystery|secret|hidden|suspicious|clue|investigat(e|ion)|unknown|strange|shadow|conspiracy|uncover|reveal)\b"),
        ("romance", r"\b(romance|love|lover|kiss|blush|heart|embrace|tender|affection|date|confess(ed|ion)?|beloved|farewell|longing)\b"),
        ("calm", r"\b(peaceful|quiet|silence|resting|rested|sleep|dream|moonlight|gentle|serene|reflect(ed|ion)|memory|memories|journey|landscape)\b"),
        ("fantasy", r"\b(magic|magical|spell|dragon|kingdom|wizard|witch|summon(ed|ing)?|dungeon|quest|fairy|fantasy|enchant(ed|ment)?|reincarnat(ed|ion))\b"),
    )
    for mood, pattern in rules:
        if re.search(pattern, sample):
            return mood
    return "fantasy"


def select_music_variation(title: str, text: str, mood: str) -> int:
    """Select a repeatable arrangement index from the chosen cinematic family."""
    chosen = normalize_music_style(mood)
    if chosen == "auto":
        chosen = detect_chapter_mood(title, text)
    seed_text = f"{chosen}\0{title.strip()}\0{str(text or '')[:4096]}".encode("utf-8", errors="replace")
    digest = hashlib.blake2b(seed_text, digest_size=8).digest()
    return int.from_bytes(digest, "big") % VARIATIONS_PER_MOOD


def music_variation_info(mood: str, variation_index: int) -> dict[str, object]:
    """Describe one local cinematic soundtrack arrangement."""
    chosen = normalize_music_style(mood)
    if chosen == "auto":
        chosen = "fantasy"
    local_index = int(variation_index) % VARIATIONS_PER_MOOD
    texture_index = local_index % len(TEXTURES)
    tempo_index = (local_index // len(TEXTURES)) % len(TEMPOS)
    arrangement_index = (local_index // (len(TEXTURES) * len(TEMPOS))) % len(ARRANGEMENTS)
    global_id = MOOD_ORDER.index(chosen) * VARIATIONS_PER_MOOD + local_index + 1
    return {
        "id": global_id,
        "mood": chosen,
        "style": THEMES[chosen]["label"],
        "variation_index": local_index,
        "texture": TEXTURES[texture_index]["name"],
        "tempo_bpm": TEMPOS[tempo_index],
        "arrangement": ARRANGEMENTS[arrangement_index]["name"],
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


def _tone_with_partials(freq: float, t: float, richness: float = 0.45) -> float:
    """A bright, mildly saw-like synthetic lead that sits above narration."""
    return (
        math.sin(2.0 * math.pi * freq * t)
        + richness * math.sin(2.0 * math.pi * freq * 2.0 * t)
        + richness * 0.45 * math.sin(2.0 * math.pi * freq * 3.0 * t)
        + richness * 0.20 * math.sin(2.0 * math.pi * freq * 4.0 * t)
    )


def synthesize_music_bed(path: Path | str, mood: str = "fantasy", variation_index: int = 0) -> Path:
    """Render an original rhythmic cinematic/anime-style music loop locally.

    The arrangement uses faster ostinati, a clear bass line, hybrid kick/snare/
    tom accents, brighter melodic leads, rising transitions and sustained
    strings. It deliberately replaces the older quiet harmony/pad recipe.
    """
    target = Path(path)
    chosen = normalize_music_style(mood)
    if chosen == "auto":
        chosen = "fantasy"
    theme = THEMES[chosen]
    local_index = int(variation_index) % VARIATIONS_PER_MOOD
    texture_index = local_index % len(TEXTURES)
    tempo_index = (local_index // len(TEXTURES)) % len(TEMPOS)
    arrangement_index = (local_index // (len(TEXTURES) * len(TEMPOS))) % len(ARRANGEMENTS)
    texture = TEXTURES[texture_index]
    arrangement = ARRANGEMENTS[arrangement_index]
    scale = tuple(int(x) for x in theme["scale"])
    root = int(theme["root"])
    motif = tuple(int(x) for x in theme["motif"])
    bass_pattern = tuple(int(x) for x in theme["bass"])
    tempo = TEMPOS[tempo_index]
    seconds_per_beat = 60.0 / tempo
    frames_per_beat = max(1, round(SAMPLE_RATE * seconds_per_beat))
    frames_per_eighth = max(1, frames_per_beat // 2)
    frame_count = frames_per_beat * 16
    duration = frame_count / SAMPLE_RATE

    seed_text = f"ryu-cinematic|{chosen}|{local_index}".encode("utf-8")
    seed = int.from_bytes(hashlib.blake2b(seed_text, digest_size=8).digest(), "big")
    rng = random.Random(seed)
    noise = [rng.uniform(-1.0, 1.0) for _ in range(frame_count)]
    scale_multiplier = 32767.0
    samples = array("h")
    rotation = (local_index * 3 + arrangement_index * 2) % len(motif)
    lead_gain = float(texture["lead"])
    strings_gain = float(texture["strings"])
    bass_gain = float(texture["bass"])
    drum_gain = float(texture["drums"])
    arp_gain = float(texture["arp"])
    pad_gain = float(texture["pad"])
    sustain = float(texture["sustain"])
    drone_freq = _midi_hz(_scale_note(root - 12, scale, 0))
    fifth_freq = _midi_hz(_scale_note(root, scale, 4))
    kick_hits = set(int(x) for x in arrangement["kick"])
    snare_hits = set(int(x) for x in arrangement["snare"])
    extra_hits = set(int(x) for x in arrangement["extra"])
    previous_noise = 0.0

    for frame in range(frame_count):
        t = frame / SAMPLE_RATE
        beat = frame // frames_per_beat
        beat_phase = (frame % frames_per_beat) / frames_per_beat
        eighth = frame // frames_per_eighth
        eighth_phase = (frame % frames_per_eighth) / frames_per_eighth
        beat_in_bar = beat % 4
        beat_in_two_bars = beat % 8
        bar = (beat // 4) % 4
        sample_noise = noise[frame]
        high_noise = sample_noise - previous_noise * 0.86
        previous_noise = sample_noise

        # A short, percussive melodic ostinato with a slight variation each bar.
        degree = motif[(eighth + rotation + bar * 2) % len(motif)]
        lead_freq = _midi_hz(_scale_note(root + 19, scale, degree))
        lead_env = min(1.0, eighth_phase / 0.035) * math.exp(-2.7 * eighth_phase)
        if sustain > 0.55:
            lead_env = min(1.0, eighth_phase / 0.08) * (0.25 + 0.75 * math.exp(-1.2 * eighth_phase))
        vibrato = 1.0 + 0.0022 * math.sin(2.0 * math.pi * 5.1 * t)
        lead = _tone_with_partials(lead_freq * vibrato, t, 0.38 + texture_index * 0.012) * lead_env

        # A sustained octave/fifth string layer; detuning and slow vibrato avoid
        # the hollow, static sine-wave sound of the previous generator.
        string_degree = motif[(beat // 2 + rotation + 4) % len(motif)]
        string_freq = _midi_hz(_scale_note(root + 12, scale, string_degree))
        string_vibrato = 1.0 + 0.0030 * math.sin(2.0 * math.pi * (4.2 + texture_index * 0.15) * t)
        string_env = 0.32 + 0.68 * min(1.0, beat_phase / 0.12)
        string_wave = (
            0.65 * math.sin(2.0 * math.pi * string_freq * string_vibrato * t)
            + 0.35 * math.sin(2.0 * math.pi * string_freq * 1.006 * t)
            + 0.14 * math.sin(2.0 * math.pi * string_freq * 2.0 * t)
        ) * string_env

        # Repeating bass movement gives the piece a score-like forward drive.
        bass_note = _midi_hz(_scale_note(root - 12, scale, bass_pattern[bar]))
        bass_gate = math.exp(-3.8 * beat_phase)
        bass = (
            0.72 * math.sin(2.0 * math.pi * bass_note * t)
            + 0.22 * math.sin(2.0 * math.pi * bass_note * 2.0 * t)
        ) * bass_gate

        # Deterministic kick, snare/tom and noise cymbal hits. These are not
        # placed on top as random effects: the rhythm is aligned to the tempo.
        drum = 0.0
        if beat_in_two_bars in kick_hits and beat_phase < 0.55:
            dt = beat_phase * seconds_per_beat
            kick_freq = max(38.0, 78.0 - 220.0 * dt)
            kick = math.sin(2.0 * math.pi * (kick_freq * dt - 8.0 * dt * dt))
            drum += kick * math.exp(-20.0 * dt) * 0.82
        if beat_in_two_bars in snare_hits and beat_phase < 0.34:
            drum += (0.75 * high_noise + 0.25 * sample_noise) * math.exp(-17.0 * beat_phase) * 0.68
        if beat_in_two_bars in extra_hits and beat_phase < 0.26:
            dt = beat_phase * seconds_per_beat
            tom = math.sin(2.0 * math.pi * 66.0 * dt) * math.exp(-15.0 * dt)
            drum += tom * 0.42 + high_noise * math.exp(-19.0 * beat_phase) * 0.22
        if beat_in_bar == 0 and beat_phase < 0.20:
            impact = math.sin(2.0 * math.pi * 48.0 * beat_phase * seconds_per_beat)
            drum += impact * math.exp(-19.0 * beat_phase) * (0.18 if texture_index in (0, 4, 5) else 0.34)

        # Fast eighth-note plucks or synth-sequence pulses.
        arp_freq = _midi_hz(_scale_note(root + 7, scale, motif[(eighth * 3 + rotation + 2) % len(motif)]))
        arp_env = min(1.0, eighth_phase / 0.018) * math.exp(-5.3 * eighth_phase)
        arp = _tone_with_partials(arp_freq, t, 0.25) * arp_env

        # Quiet root/fifth air layer supports the score without replacing its
        # rhythmic foreground with a sustained chord progression.
        slow_pulse = 0.72 + 0.28 * math.sin(2.0 * math.pi * t / max(1.5, duration * 0.58))
        pad = (
            math.sin(2.0 * math.pi * drone_freq * t)
            + 0.48 * math.sin(2.0 * math.pi * fifth_freq * t)
        ) * slow_pulse

        # Small tension rise before each new bar: filter-like noise swell.
        riser = 0.0
        if beat_in_bar == 3 and beat_phase > 0.60:
            rise = (beat_phase - 0.60) / 0.40
            riser = high_noise * rise * 0.16

        value = (
            lead * lead_gain * 0.66
            + string_wave * strings_gain * 0.58
            + bass * bass_gain * 0.66
            + drum * drum_gain * 0.72
            + arp * arp_gain * 0.52
            + pad * pad_gain * 0.17
            + riser * max(0.65, drum_gain)
        )
        # Soft saturation keeps the hybrid score full without digital clipping.
        value = math.tanh(value * 1.65) / math.tanh(1.65)
        pan_l = 0.94 + 0.06 * math.sin(2.0 * math.pi * 0.13 * t)
        pan_r = 0.94 + 0.06 * math.sin(2.0 * math.pi * 0.13 * t + 1.1)
        samples.append(int(max(-0.90, min(0.90, value * pan_l)) * scale_multiplier))
        samples.append(int(max(-0.90, min(0.90, value * pan_r)) * scale_multiplier))

    # Short edge fades are long enough to avoid clicks but do not leave a gap
    # when FFmpeg loops this bed beneath a multi-minute narration.
    fade_frames = min(int(SAMPLE_RATE * 0.045), frame_count // 8)
    for frame in range(fade_frames):
        gain_in = frame / max(1, fade_frames)
        gain_out = (fade_frames - frame - 1) / max(1, fade_frames)
        samples[frame * 2] = int(samples[frame * 2] * gain_in)
        samples[frame * 2 + 1] = int(samples[frame * 2 + 1] * gain_in)
        out_index = (frame_count - fade_frames + frame) * 2
        samples[out_index] = int(samples[out_index] * gain_out)
        samples[out_index + 1] = int(samples[out_index + 1] * gain_out)
    return _write_stereo_pcm(target, samples)


def _cue_style(cue_style: str | None) -> str:
    chosen = normalize_cue_style(cue_style)
    return "classic-book" if chosen == "custom" else chosen


def _cue_noise(seed_text: str, count: int) -> list[float]:
    seed = int.from_bytes(hashlib.blake2b(seed_text.encode("utf-8"), digest_size=8).digest(), "big")
    rng = random.Random(seed)
    return [rng.uniform(-1.0, 1.0) for _ in range(count)]


def synthesize_opening_cue(
    path: Path | str,
    variation_index: int = 0,
    cue_style: str = "classic-book",
    duration_seconds: float = OPENING_SECONDS,
) -> Path:
    """Create a locally generated book-opening cue for the selected cue set."""
    target = Path(path)
    style = _cue_style(cue_style)
    duration = max(0.70, min(2.4, float(duration_seconds)))
    frame_count = max(1, int(SAMPLE_RATE * duration))
    noise = _cue_noise(f"ryu-book-open:{style}:{int(variation_index) % 168}", frame_count)
    samples = array("h")
    low = 0.0
    for i in range(frame_count):
        t = i / SAMPLE_RATE
        pos = t / duration
        n = noise[i]
        low = low * 0.90 + n * 0.10
        mid = n - low * 0.68
        # Cover lift at the beginning, two small page flutters, then a fade.
        flutter = 0.0
        for centre, width, weight in ((0.13, 0.10, 0.75), (0.34, 0.12, 0.55), (0.62, 0.15, 0.36)):
            flutter += math.exp(-((t - centre * duration) / max(0.025, width * duration)) ** 2) * weight
        paper = (0.70 * mid + 0.30 * low) * flutter
        thump_dt = t - 0.055
        thump = 0.0
        if thump_dt >= 0:
            thump = math.sin(2.0 * math.pi * (76.0 * thump_dt - 20.0 * thump_dt * thump_dt)) * math.exp(-15.0 * thump_dt)
        if style == "magical-tome":
            shimmer = math.sin(2.0 * math.pi * (710.0 + 540.0 * pos) * t) * math.exp(-3.0 * pos) * 0.14
            paper += shimmer
        elif style == "cinematic-whoosh":
            whoosh = (0.2 * n + 0.8 * mid) * (pos ** 1.8) * max(0.0, 1.0 - pos)
            paper += whoosh * 1.7
        elif style == "soft-pages":
            paper *= 0.55
            thump *= 0.42
        value = (paper * 0.42 + thump * 0.30) * min(1.0, t / 0.018) * min(1.0, max(0.0, (duration - t) / 0.10))
        sample = int(max(-0.65, min(0.65, value)) * 32767.0)
        samples.append(sample)
        samples.append(int(sample * 0.93))
    return _write_stereo_pcm(target, samples)


def synthesize_chapter_transition(
    path: Path | str,
    mood: str = "fantasy",
    duration_seconds: float = TRANSITION_SECONDS,
    variation_index: int = 0,
    cue_style: str = "classic-book",
) -> Path:
    """Compatibility wrapper; chapter transitions are page turns, not chimes."""
    return synthesize_page_turn(
        path,
        variation_index=variation_index,
        cue_style=cue_style,
        duration_seconds=duration_seconds,
    )


def synthesize_page_turn(
    path: Path | str,
    variation_index: int = 0,
    cue_style: str = "classic-book",
    duration_seconds: float = PAGE_TURN_SECONDS,
) -> Path:
    """Create a papery page turn; optional style adds magical or cinematic character."""
    target = Path(path)
    style = _cue_style(cue_style)
    duration = max(0.35, min(1.8, float(duration_seconds)))
    frame_count = max(1, int(SAMPLE_RATE * duration))
    noise = _cue_noise(f"ryu-page-turn:{style}:{int(variation_index) % 168}", frame_count)
    samples = array("h")
    low_noise = 0.0
    mid_noise = 0.0
    for index in range(frame_count):
        t = index / SAMPLE_RATE
        pos = t / duration
        n = noise[index]
        low_noise = low_noise * 0.90 + n * 0.10
        mid_noise = mid_noise * 0.56 + n * 0.44
        sweep = max(0.0, math.sin(math.pi * pos)) ** 0.80
        flutter = 0.62 + 0.22 * math.sin(2.0 * math.pi * (12.0 + (variation_index % 7)) * t)
        grain = n * (0.14 if 0.07 < pos < 0.20 else 0.0)
        paper = sweep * flutter * (low_noise * 0.42 + mid_noise * 0.24) + grain
        impact = 0.0
        if style == "magical-tome":
            impact = math.sin(2.0 * math.pi * (860.0 + 520.0 * pos) * t) * math.exp(-5.0 * pos) * 0.10
        elif style == "cinematic-whoosh":
            dt = max(0.0, t - 0.035)
            impact = math.sin(2.0 * math.pi * (65.0 - 15.0 * pos) * dt) * math.exp(-18.0 * dt) * 0.21
            paper += (n - low_noise) * max(0.0, math.sin(math.pi * pos)) * 0.22
        elif style == "soft-pages":
            paper *= 0.54
        value = (paper + impact) * min(1.0, t / 0.025) * min(1.0, max(0.0, (duration - t) / 0.075)) * 0.48
        sample = int(max(-0.55, min(0.55, value)) * 32767.0)
        samples.append(sample)
        samples.append(int(sample * 0.94))
    return _write_stereo_pcm(target, samples)


def synthesize_audiobook_ending(
    path: Path | str,
    mood: str = "fantasy",
    variation_index: int = 0,
    duration_seconds: float = ENDING_SECONDS,
    cue_style: str = "classic-book",
) -> Path:
    """Make a distinct closing-cover cue rather than reusing the chapter flip."""
    target = Path(path)
    style = _cue_style(cue_style)
    duration = max(1.8, min(4.0, float(duration_seconds)))
    frame_count = max(1, int(SAMPLE_RATE * duration))
    noise = _cue_noise(f"ryu-book-close:{style}:{int(variation_index) % 168}", frame_count)
    samples = array("h")
    low = 0.0
    for i in range(frame_count):
        t = i / SAMPLE_RATE
        n = noise[i]
        low = low * 0.93 + n * 0.07
        high = n - low
        # A cover settles with a soft body thump, a short flutter and a long
        # quiet tail. It deliberately has no pitched "ending jingle".
        close_dt = t - 0.48
        thump = 0.0
        if close_dt >= 0:
            thump = math.sin(2.0 * math.pi * (88.0 * close_dt - 16.0 * close_dt * close_dt)) * math.exp(-9.0 * close_dt)
        flutter = math.exp(-((t - 0.33) / 0.24) ** 2) * (0.70 * high + 0.30 * low)
        tail = max(0.0, 1.0 - max(0.0, t - 0.65) / max(0.15, duration - 0.65))
        if style == "magical-tome":
            shimmer = math.sin(2.0 * math.pi * (590.0 - 270.0 * min(1.0, t / duration)) * t)
            flutter += shimmer * math.exp(-2.7 * t) * 0.12
        elif style == "cinematic-whoosh":
            flutter += high * min(1.0, t / 0.28) * math.exp(-1.5 * t) * 0.50
            thump *= 1.5
        elif style == "soft-pages":
            flutter *= 0.50
            thump *= 0.42
        value = (flutter * 0.28 + thump * 0.37) * min(1.0, t / 0.025) * tail
        # A smooth end fade lets the cue sit beneath the final narration tail.
        value *= min(1.0, max(0.0, (duration - t) / 0.42))
        sample = int(max(-0.65, min(0.65, value)) * 32767.0)
        samples.append(sample)
        samples.append(int(sample * 0.96))
    return _write_stereo_pcm(target, samples)
