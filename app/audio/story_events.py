from __future__ import annotations

"""Conservative offline story-event detection and procedural sound cues."""

from array import array
from dataclasses import dataclass
import math
from pathlib import Path
import random
import sys
import wave
import re

SAMPLE_RATE = 22050
MAX_EVENTS_PER_CHUNK = 3
MAX_EVENTS_PER_CHAPTER = 60


@dataclass(frozen=True)
class StoryEvent:
    kind: str
    char_start: int
    char_end: int
    confidence: float
    duration_seconds: float
    mix_gain: float
    category: str


@dataclass(frozen=True)
class EventProfile:
    duration: float
    gain: float
    category: str


EVENT_PROFILES = {
    "running_footsteps": EventProfile(2.15, 0.78, "action"),
    "walking_footsteps": EventProfile(1.75, 0.52, "action"),
    "door_open": EventProfile(1.20, 0.58, "action"),
    "door_slam": EventProfile(0.95, 0.48, "action"),
    "knock": EventProfile(0.90, 0.58, "action"),
    "rain": EventProfile(5.20, 0.35, "ambience"),
    "thunder": EventProfile(3.20, 0.42, "ambience"),
    "wind": EventProfile(4.50, 0.28, "ambience"),
    "birds": EventProfile(2.80, 0.34, "ambience"),
    "waves": EventProfile(4.60, 0.30, "ambience"),
    "fire": EventProfile(4.00, 0.28, "ambience"),
    "crowd": EventProfile(3.80, 0.24, "ambience"),
    "sword_clash": EventProfile(0.90, 0.54, "action"),
    "magic": EventProfile(1.80, 0.36, "fantasy"),
    "explosion": EventProfile(2.20, 0.50, "action"),
    "horse_hooves": EventProfile(2.05, 0.52, "action"),
    "heartbeat": EventProfile(2.30, 0.27, "body"),
    "gasp": EventProfile(0.95, 0.25, "body"),
    "glass_break": EventProfile(1.20, 0.50, "action"),
    "water_splash": EventProfile(1.55, 0.42, "action"),
}

# Require clear, audible actions rather than broad emotion words or loose keywords.
_RULES = (
    ("running_footsteps", 0.96, (
        r"\b(?:ran|running|sprinted|sprinting|dashed|bolted|raced)\s+(?:quickly\s+|straight\s+|back\s+|forward\s+)?(?:across|down|up|through|toward|towards|to|into|onto|past|along|around)\s+(?:the\s+|a\s+|an\s+|his\s+|her\s+|their\s+)?(?:hall(?:way)?|corridor|stairs?|street|road|path|field|forest|room|yard|garden|bridge|alley|passage|platform|courtyard|doorway|door|gate|entrance|exit|beach|ground|floor|tunnel)\b",
        r"\b(?:broke|burst)\s+into\s+a\s+run\b",
        r"\b(?:running|sprinting)\s+footsteps?\b",
        r"\bfootsteps?\s+(?:pounded|thudded|raced|sprinted|approached|receded)\b",
        r"\b(?:feet|footsteps?)\s+(?:were\s+)?(?:pounding|racing|thundering)\s+(?:down|along|across|through)\b",
    )),
    ("walking_footsteps", 0.86, (
        r"\bfootsteps?\s+(?:echoed|crunched|approached|receded|clicked|clattered)\b",
        r"\b(?:walked|strolled|paced|strode)\s+(?:slowly\s+|quietly\s+|carefully\s+)?(?:across|down|up|through|toward|towards|along|past)\s+(?:the\s+|a\s+|an\s+|his\s+|her\s+|their\s+)?(?:hall(?:way)?|corridor|stairs?|street|road|path|field|forest|room|yard|garden|bridge|alley|passage|platform|courtyard|doorway|beach|ground|floor|tunnel)\b",
        r"\b(?:steps|shoes)\s+(?:clicked|crunched|thudded)\s+(?:on|against|over)\s+(?:the\s+|a\s+)?(?:stone|gravel|wood|floor|ground|tiles?|path)\b",
    )),
    ("door_slam", 0.97, (
        r"\b(?:slammed|banged|shut)\s+(?:the\s+|his\s+|her\s+|their\s+)?door\b",
        r"\bthe\s+door\s+(?:slammed|banged|crashed|shut)\b",
        r"\bdoor\s+(?:slammed|banged)\s+shut\b",
    )),
    ("door_open", 0.91, (
        r"\b(?:opened|pushed open|pulled open|swung open|eased open)\s+(?:the\s+|a\s+|his\s+|her\s+|their\s+)?door\b",
        r"\bthe\s+door\s+(?:creaked|swung|slid|flew)\s+open\b",
        r"\bdoor\s+creaked\s+open\b",
    )),
    ("knock", 0.88, (
        r"\b(?:knocked|rapped|pounded)\s+(?:on|at)\s+(?:the\s+|a\s+|his\s+|her\s+|their\s+)?door\b",
        r"\b(?:a|three|two|two loud|three sharp)\s+knocks?\s+(?:sounded|echoed|came)\b",
    )),
    ("glass_break", 0.94, (
        r"\b(?:glass|window|crystal|mirror)\s+(?:shattered|smashed|burst|broke into pieces)\b",
        r"\bshards of glass\b",
    )),
    ("sword_clash", 0.93, (
        r"\b(?:swords?|blades?|steel)\s+(?:clashed|collided|rang|struck|crossed)\b",
        r"\b(?:metal|steel)\s+(?:clanged|rang out|clashed)\b",
        r"\bblade struck (?:the\s+)?blade\b",
    )),
    ("explosion", 0.92, (
        r"\b(?:an?\s+)?explosion\s+(?:ripped|erupted|echoed|rocked|boomed)\b",
        r"\b(?:the\s+)?(?:bomb|device)\s+(?:exploded|detonated)\b",
        r"\bblast\s+(?:erupted|roared|hit|shook)\b",
    )),
    ("horse_hooves", 0.90, (
        r"\b(?:horse|horses)\s+(?:galloped|galloping|charged|raced)\b",
        r"\bhooves\s+(?:clattered|thundered|pounded|approached|receded)\b",
        r"\bgalloping hooves\b",
    )),
    ("heartbeat", 0.88, (
        r"\b(?:his|her|their)\s+heart\s+(?:pounded|hammered|raced)\s+in\s+(?:his|her|their)\s+chest\b",
        r"\bheartbeat\s+(?:thundered|pounded|raced|quickened)\b",
        r"\bpulse\s+(?:pounded|hammered|raced)\s+in\s+(?:his|her|their)\s+(?:ears|neck|wrist)\b",
    )),
    ("gasp", 0.83, (
        r"\b(?:gasped|gasping|let out a gasp|drew in a sharp breath|sharp intake of breath)\b",
    )),
    ("water_splash", 0.88, (
        r"\b(?:splashed|plunged|dove|dived)\s+into\s+(?:the\s+|a\s+)?(?:water|pool|river|lake)\b",
        r"\bwater\s+(?:splashed|sprayed)\s+(?:over|against|around)\b",
    )),
    ("thunder", 0.86, (
        r"\bthunder\s+(?:rolled|rumbled|cracked|roared|boomed|exploded)\b",
        r"\b(?:a|the)\s+thunderclap\b",
        r"\bthunderstorm\s+(?:approached|rolled|raged)\b",
    )),
    ("rain", 0.86, (
        r"\b(?:rain|rainfall)\s+(?:poured|drummed|hammered|lashed|pat{1,2}ered|streamed|tapped|rattled)\b",
        r"\bit\s+was\s+raining\b",
        r"\bthe\s+rain\s+(?:fell|grew heavier|began|intensified|continued)\b",
        r"\brain\s+lashed\s+against\b",
    )),
    ("wind", 0.82, (
        r"\b(?:wind|gusts? of wind)\s+(?:howled|whistled|gusted|roared|rattled|picked up|swept)\b",
        r"\bwind\s+howled\s+through\b",
    )),
    ("waves", 0.82, (
        r"\bwaves?\s+(?:crashed|lapped|rolled|washed|pounded|broke)\s+(?:against|over|on|onto|the shore|the rocks|the beach)?\b",
        r"\b(?:surf|sea)\s+(?:crashed|roared|pounded|rolled)\b",
        r"\b(?:stream|river|waterfall)\s+(?:babbl(?:ed|ing)|rushed|cascaded|roared)\b",
    )),
    ("birds", 0.82, (
        r"\b(?:birds?|songbirds?)\s+(?:chirped|sang|called|fluttered|twittered)\b",
        r"\b(?:birdsong|chirping birds|birds? chirping)\b",
    )),
    ("fire", 0.82, (
        r"\b(?:fire|flames?|campfire|logs?)\s+(?:crackled|roared|popped|snapped|flickered)\b",
        r"\bfire\s+(?:was|is)\s+crackling\b",
    )),
    ("crowd", 0.80, (
        r"\b(?:crowd|spectators|audience)\s+(?:roared|cheered|murmured|erupted|chanted|booed|applauded)\b",
        r"\bcheering crowd\b",
    )),
    ("magic", 0.85, (
        r"\b(?:magic|magical energy|mana|runes?)\s+(?:surged|crackled|swirled|flared|sparked|glowed|pulsed)\b",
        r"\b(?:cast|casting) (?:a |the )?(?:spell|incantation)\b",
        r"\bspell\s+(?:burst|flared|sparked|shimmered|exploded|activated)\b",
    )),
)


def detect_story_events(text: str, max_events: int = MAX_EVENTS_PER_CHUNK) -> list[StoryEvent]:
    """Return text-position-anchored cues for explicit audible story actions."""
    source = str(text or "")
    if not source.strip():
        return []
    found: list[StoryEvent] = []
    for kind, confidence, patterns in _RULES:
        best = None
        for pattern in patterns:
            match = re.search(pattern, source, flags=re.IGNORECASE)
            if match and (best is None or match.start() < best.start()):
                best = match
        if best is None:
            continue
        nearby = source[max(0, best.start() - 80):min(len(source), best.end() + 80)]
        if kind == "running_footsteps" and re.search(
            r"\b(?:running out of (?:time|patience|money|options)|run(?:ning)? a business|run(?:ning)? the show|run(?:ning)? late)\b",
            nearby, flags=re.IGNORECASE,
        ):
            continue
        profile = EVENT_PROFILES[kind]
        found.append(StoryEvent(kind, best.start(), best.end(), confidence,
                                profile.duration, profile.gain, profile.category))

    found.sort(key=lambda event: (event.char_start, -event.confidence))
    filtered: list[StoryEvent] = []
    for event in found:
        overlapping = [old for old in filtered
                       if event.char_start <= old.char_end + 24
                       and old.char_start <= event.char_end + 24]
        if overlapping:
            if event.kind == "running_footsteps" and any(x.kind == "walking_footsteps" for x in overlapping):
                filtered = [x for x in filtered if x not in overlapping]
            elif event.kind == "door_slam" and any(x.kind == "door_open" for x in overlapping):
                filtered = [x for x in filtered if x not in overlapping]
            elif any(x.kind == event.kind for x in overlapping):
                continue
        filtered.append(event)
    return filtered[:max(1, int(max_events))]


def _stereo_wave(path: Path, samples: array) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(samples.tobytes())
    return path


def synthesize_story_effect(path: Path | str, event_type: str, variant_seed: int = 0) -> Path:
    """Write a small generated sound cue. No external audio assets are needed."""
    if event_type not in EVENT_PROFILES:
        raise ValueError(f"Unsupported story sound effect: {event_type}")
    duration = EVENT_PROFILES[event_type].duration
    frame_count = max(1, int(SAMPLE_RATE * duration))
    rng = random.Random(f"ryu-sfx:{event_type}:{int(variant_seed) % 997}")
    samples = array("h")
    previous_noise = 0.0

    for index in range(frame_count):
        t = index / SAMPLE_RATE
        pos = t / duration
        noise = rng.uniform(-1.0, 1.0)
        previous_noise = previous_noise * 0.72 + noise * 0.28
        filtered = previous_noise
        value = 0.0

        if event_type in {"running_footsteps", "walking_footsteps", "horse_hooves"}:
            stride = 0.235 if event_type in {"running_footsteps", "horse_hooves"} else 0.39
            local = t % stride
            strike = math.exp(-local * (52.0 if event_type != "walking_footsteps" else 37.0)) if local < 0.11 else 0.0
            freq = 58.0 if event_type == "horse_hooves" else 74.0
            value = (math.sin(2.0 * math.pi * freq * t) * 0.34 + (noise * 0.35 + filtered * 0.50) * 0.38) * strike * (0.82 - 0.35 * pos)
        elif event_type in {"door_open", "door_slam", "knock"}:
            if event_type == "door_open":
                freq = 260.0 - 150.0 * min(1.0, pos)
                creak = math.sin(2.0 * math.pi * (freq * t - 75.0 * t * t)) * (0.16 + 0.15 * math.sin(math.pi * pos))
                thump = math.sin(2.0 * math.pi * 83.0 * t) * math.exp(-max(0.0, duration - t) * 20.0) if pos > 0.86 else 0.0
                value = creak * 0.45 + filtered * 0.16 + thump * 0.20
            elif event_type == "door_slam":
                hit = math.exp(-max(0.0, t - 0.035) * 17.0) if t >= 0.035 else 0.0
                value = (math.sin(2.0 * math.pi * (62.0 + 22.0 * pos) * t) * 0.62 + noise * 0.28) * hit
            else:
                local = t % 0.24
                hit = math.exp(-local * 38.0) if local < 0.10 and t < 0.74 else 0.0
                value = (math.sin(2.0 * math.pi * 145.0 * t) * 0.48 + noise * 0.22) * hit
        elif event_type == "rain":
            drops = rng.uniform(0.2, 0.8) if rng.random() > 0.9975 else 0.0
            value = filtered * 0.22 + noise * 0.09 + drops
        elif event_type == "thunder":
            env = math.exp(-3.8 * pos) * min(1.0, t / 0.12)
            value = (math.sin(2.0 * math.pi * (44.0 + 31.0 * pos) * t) * 0.42 + filtered * 0.60 + noise * 0.08) * env
        elif event_type == "wind":
            swell = 0.42 + 0.58 * (0.5 + 0.5 * math.sin(2.0 * math.pi * t / 3.5))
            value = (filtered * 0.66 + noise * 0.12) * swell
        elif event_type == "birds":
            local = t % 0.62
            env = math.exp(-max(0.0, local - 0.035) * 8.0) if local < 0.24 else 0.0
            freq = 1500.0 + 780.0 * min(1.0, local / 0.18)
            value = math.sin(2.0 * math.pi * (freq * t + 390.0 * t * t)) * env * 0.32 + filtered * 0.025
        elif event_type == "waves":
            swell = (0.5 + 0.5 * math.sin(2.0 * math.pi * t / 2.65 - 0.6)) ** 1.7
            value = (filtered * 0.55 + noise * 0.08) * swell
        elif event_type == "fire":
            crack = rng.uniform(0.25, 0.9) if rng.random() > 0.9982 else 0.0
            value = filtered * 0.22 + noise * 0.045 + crack * (1.0 - pos) ** 1.4
        elif event_type == "crowd":
            murmur = (math.sin(2.0 * math.pi * 174.0 * t) + 0.55 * math.sin(2.0 * math.pi * 236.0 * t) + 0.33 * math.sin(2.0 * math.pi * 390.0 * t)) * (0.5 + 0.5 * math.sin(2.0 * math.pi * t / 0.73))
            value = filtered * 0.20 + murmur * 0.12
        elif event_type == "sword_clash":
            env = math.exp(-5.3 * pos) * (1.0 if t > 0.018 else t / 0.018)
            ring = math.sin(2.0 * math.pi * 930.0 * t) + 0.58 * math.sin(2.0 * math.pi * 1470.0 * t) + 0.24 * math.sin(2.0 * math.pi * 2230.0 * t)
            value = (ring * 0.29 + noise * 0.58) * env
        elif event_type == "magic":
            freq = 380.0 + 950.0 * pos
            shimmer = math.sin(2.0 * math.pi * freq * t) + 0.35 * math.sin(2.0 * math.pi * freq * 2.01 * t)
            env = min(1.0, t / 0.12) * math.exp(-1.6 * pos)
            value = shimmer * env * 0.25 + filtered * env * 0.045
        elif event_type == "explosion":
            env = math.exp(-4.7 * pos) * min(1.0, t / 0.018)
            value = (math.sin(2.0 * math.pi * (39.0 + 65.0 * (1.0 - pos)) * t) * 0.64 + filtered * 0.62 + noise * 0.16) * env
        elif event_type == "heartbeat":
            cycle = t % 0.94
            p1 = math.exp(-cycle * 26.0) if cycle < 0.13 else 0.0
            local2 = cycle - 0.18
            p2 = math.exp(-local2 * 32.0) if 0 <= local2 < 0.10 else 0.0
            value = math.sin(2.0 * math.pi * 57.0 * t) * (p1 * 0.70 + p2 * 0.52)
        elif event_type == "gasp":
            env = math.sin(math.pi * pos) ** 0.65 * (0.60 + 0.40 * (1.0 - pos))
            value = (filtered * 0.72 + noise * 0.14) * env
        elif event_type == "glass_break":
            env = math.exp(-4.0 * pos) * min(1.0, t / 0.008)
            ring = math.sin(2.0 * math.pi * 1330.0 * t) + 0.46 * math.sin(2.0 * math.pi * 1940.0 * t) + 0.25 * math.sin(2.0 * math.pi * 2840.0 * t)
            value = (ring * 0.30 + noise * 0.55) * env
        elif event_type == "water_splash":
            env = math.exp(-3.4 * pos) * min(1.0, t / 0.015)
            value = (filtered * 0.65 + noise * 0.34) * env

        value *= min(1.0, t / 0.018) * min(1.0, max(0.0, (duration - t) / 0.07))
        value = max(-0.88, min(0.88, value))
        sample = int(value * 32767.0)
        samples.append(sample)
        samples.append(int(sample * 0.985))

    return _stereo_wave(Path(path), samples)
