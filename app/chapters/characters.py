from __future__ import annotations

from dataclasses import dataclass, field
import re
from collections import Counter

from app.chapters.detector import Chapter


@dataclass
class Character:
    name: str
    role: str
    dialogue_count: int = 0
    examples: list[str] = field(default_factory=list)
    confidence: float = 0.0
    aliases: list[str] = field(default_factory=list)


@dataclass
class CharacterAnalysis:
    narrator: Character
    characters: list[Character]
    dialogue_total: int = 0
    unassigned_dialogue: int = 0


DIALOGUE_PATTERNS = (
    re.compile(r'[\u201c]([^\u201d]{2,1800})[\u201d]'),
    re.compile(r'"([^"]{2,1800})"'),
    re.compile(r'[\u300c]([^\u300d]{2,1800})[\u300d]'),
    re.compile(r'[\u300e]([^\u300f]{2,1800})[\u300f]'),
)
SPEAKER_VERBS = (
    "said|asked|replied|answered|shouted|yelled|whispered|muttered|called|"
    "cried|exclaimed|continued|added|insisted|wondered|demanded|begged|"
    "groaned|sighed|laughed|snapped|stammered|murmured|screamed|"
    "announced|introduced|explained|remarked|responded|mumbled|roared"
)

NAME_TOKEN = r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’-]{2,30}\b"

NAME_STOPWORDS = {
    "The","A","An","I","Im","I'm","I’m","Ive","I've","I’ve","Id","I'd","I’d","Ill","I'll","I’ll",
    "He","Hes","He's","He’s","She","Shes","She's","She’s","It","Its","It's","It’s",
    "We","Were","We're","We’re","We've","We’ve","They","Their","Them","You","Your","Yours",
    "My","Our","Ours","This","That","These","Those","When","What","Why","How","Where","Who","Whom","Which",
    "And","But","So","Then","As","If","Or","There","Not","Yes","No","All","One","Someone","Whoever",
    "Anyway","Maybe","Perhaps","Given","Honestly","However","Still","Would","Could","Should","Must","Might",
    "Can","Will","Do","Does","Did","Done","Have","Has","Had","Was","Be","Been","Being","Is","Are","Am",
    "To","Of","In","On","At","By","For","From","With","About","Into","Over","Under","Again","Very","Really",
    "Just","Even","Only","More","Most","Some","Any","Each","Every","Either","Neither","Both","Another","Other",
    "Such","Same","Too","Also","Here","Because","While","Though","Before","After","During","Until","Since","Than",
    "Once","Yet","Chapter","Chap","Part","Life","Page","Goldenagato","Pdf","Book","President","Club",
    "School","Building","Room","Street","Day","Night","Morning","Afternoon","Evening","God","Devil","Demon",
    "Human","Humans","Girl","Boy","Man","Woman","Someone","Something","Anything","Nothing","Everyone","Everybody",
    "Him","Her","Me","Us","His","Our","Their","These","Those","Wha","Heh","Ah","Oh","Uh","Hmm",
}


def analyze_chapter(chapter: Chapter) -> CharacterAnalysis:
    return analyze_book([chapter])


def analyze_book(chapters: list[Chapter]) -> CharacterAnalysis:
    """Local, deterministic, reviewable book-wide character analysis."""
    text = "\n\n".join(c.text for c in chapters if c.text)
    text = _clean_analysis_text(text)
    narrator_name = _detect_first_person_narrator(text)
    candidates = _discover_candidates(text)
    canonical, aliases = _canonicalize_candidates(candidates)

    records: dict[str, Character] = {
        name.casefold(): Character(
            name=name,
            role="Possible Character",
            aliases=sorted(aliases.get(name, set())),
        )
        for name in canonical
    }

    spans = _all_dialogue_spans(text)
    last_speaker: str | None = None
    assigned_dialogue = 0

    manual_speakers = {
        str(item.get("speaker", "")).strip()
        for chapter in chapters
        for item in getattr(chapter, "dialogue_assignments", [])
        if str(item.get("speaker", "")).strip()
    }
    for speaker in manual_speakers:
        if _is_plausible_name(speaker):
            canonical.append(speaker)
    canonical = sorted(set(canonical), key=str.casefold)

    for start, end, dialogue in spans:
        speaker, confidence = _speaker_near_quote(
            text, start, end, canonical, narrator_name, last_speaker
        )
        if not speaker:
            continue
        speaker = _resolve_canonical(speaker, canonical, aliases) or speaker
        key = speaker.casefold()
        if key not in records:
            records[key] = Character(name=speaker, role="Possible Character")
        item = records[key]
        item.dialogue_count += 1
        item.confidence = max(item.confidence, confidence)
        if len(item.examples) < 5:
            item.examples.append(_clean_dialogue(dialogue))
        assigned_dialogue += 1
        last_speaker = speaker

    if narrator_name:
        narrator_name = _resolve_canonical(narrator_name, canonical, aliases) or narrator_name
        records.setdefault(
            narrator_name.casefold(),
            Character(name=narrator_name, role="Narrating Character"),
        )

    characters = list(records.values())
    characters.sort(key=lambda c: (-c.dialogue_count, -c.confidence, c.name.casefold()))
    for item in characters:
        item.role = (
            "Primary Character" if item.dialogue_count >= 8 else
            "Supporting Character" if item.dialogue_count >= 2 else
            "Possible Character"
        )
        if narrator_name and item.name.casefold() == narrator_name.casefold():
            item.role = "Narrating Character"

    audiobook_narrator = Character(
        name="Narrator",
        role="Audiobook Narrator",
        confidence=1.0,
    )
    return CharacterAnalysis(
        audiobook_narrator,
        characters,
        dialogue_total=len(spans),
        unassigned_dialogue=max(0, len(spans) - assigned_dialogue),
    )


def _clean_analysis_text(text: str) -> str:
    text = re.sub(r"^\s*Page\s+\d+\s+.*mp4directs\.com.*$", "", text, flags=re.I | re.M)
    text = re.sub(r"^\s*Page\s+\d+\s*$", "", text, flags=re.I | re.M)
    text = re.sub(r"^.*mp4directs\.com.*$", "", text, flags=re.I | re.M)
    return text


def _detect_first_person_narrator(text: str) -> str | None:
    patterns = (
        r"\b([A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’-]{2,30}(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’-]{2,30})?)\s*[—-]\s*that['’]s my name\b",
        r"\bmy name is\s+([A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’-]{2,30}(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’-]{2,30})?)\b",
        r"\b(?:I['’]m|I am|this is)\s+([A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’-]{2,30}(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’-]{2,30})?)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match and _is_plausible_name(match.group(1)):
            return _clean_name(match.group(1))
    return None


def _discover_candidates(text: str) -> set[str]:
    candidates: set[str] = set()
    patterns = (
        # Explicit self-identification is highly reliable and common in
        # first-person/light-novel narration.
        rf"\bmy name is\s+({NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,2}})",
        rf"\b(?:I['’]m|I am|this is)\s+({NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,2}})",
        rf"\b({NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,2}})\s+(?:{SPEAKER_VERBS})\b",
        rf"\b(?:{SPEAKER_VERBS})\s+({NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,2}})\b",
        rf"\b(?:named|called)\s+({NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,2}})\b",
        rf"\b(?:girlfriend|boyfriend|friend|girl|boy|woman|man|student|teacher|classmate)\s+(?:named|called)\s+({NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,2}})\b",
        rf"\b({NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,2}})\s*[:—–-]\s*[“\"「『]",
        rf"[”\"」』]\s*,?\s*(?:{SPEAKER_VERBS})\s+({NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,2}})\b",
        rf"[”\"」』]\s*,?\s*({NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,2}})\s+(?:{SPEAKER_VERBS})\b",
        rf"\b({NAME_TOKEN})\s*[「『]",
        # Speaker label on its own line; the next line is checked below
        # for em/en-dash dialogue.
        rf"(?m)^\s*({NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,2}})\s*$",
    )
    for index, pattern in enumerate(patterns):
        for match in re.finditer(pattern, text):
            name = _clean_name(match.group(1))
            if index == len(patterns) - 1:
                following = text[match.end():match.end() + 20]
                dash_chars = chr(0x2014) + chr(0x2013) + "-"
                if not re.match(r"[ \t]*[" + dash_chars + r"]", following):
                    continue
            if _is_plausible_name(name):
                candidates.add(name)

    # Discover repeated proper-name tokens outside quoted dialogue too.
    # Many novels introduce a character in narration long before the first
    # explicit "Name said" tag. The previous detector missed these characters,
    # which made speaker deduction look as if it was not trying.
    quote_spans = _all_dialogue_spans(text)
    for match in re.finditer(NAME_TOKEN, text):
        token = _clean_name(match.group(0))
        if not _is_plausible_name(token):
            continue
        if any(start <= match.start() < end for start, end, _ in quote_spans):
            continue
        counts[token] += 1
        prefix = text[max(0, match.start() - 2):match.start()]
        if prefix and not re.search(r"[.!?。！？\n\r][\s\"“”]*$", prefix):
            mid_sentence[token] += 1

    for token, count in counts.items():
        # Two or more appearances in narrative text are enough to make the
        # name a candidate; speaker assignment still requires stronger local
        # evidence before it is considered high confidence.
        if count >= 2 and mid_sentence[token] >= 1:
            candidates.add(token)

    for match in re.finditer(rf"\b({NAME_TOKEN}\s+{NAME_TOKEN})\b", text):
        name = _clean_name(match.group(1))
        if _is_plausible_name(name):
            candidates.add(name)
    return candidates


def _canonicalize_candidates(candidates: set[str]) -> tuple[list[str], dict[str, set[str]]]:
    ordered = sorted(candidates, key=lambda x: (-len(x.split()), -len(x), x.casefold()))
    canonical: list[str] = []
    aliases: dict[str, set[str]] = {}
    for candidate in ordered:
        if not _is_plausible_name(candidate):
            continue
        words = candidate.split()
        target = None
        for existing in list(canonical):
            ewords = existing.split()
            if len(words) == 1 and len(ewords) > 1 and words[0].casefold() in {w.casefold() for w in ewords}:
                target = existing
                break
            if len(ewords) == 1 and len(words) > 1 and ewords[0].casefold() in {w.casefold() for w in words}:
                target = candidate
                canonical.remove(existing)
                aliases.setdefault(candidate, set()).add(existing)
                break
        if target:
            aliases.setdefault(target, set()).add(candidate)
        elif candidate not in canonical:
            canonical.append(candidate)
    canonical.sort(key=lambda x: x.casefold())
    return canonical, aliases


def _speaker_near_quote(
    text: str,
    start: int,
    end: int,
    candidates: list[str],
    narrator_name: str | None,
    last_speaker: str | None,
) -> tuple[str | None, float]:
    before = text[max(0, start - 650):start]
    after = text[end:min(len(text), end + 500)]
    name_phrase = rf"({NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,2}})"

    for pattern in (
        rf"{name_phrase}\s*(?:{SPEAKER_VERBS})\b\s*$",
        rf"(?:{SPEAKER_VERBS})\s+{name_phrase}\s*$",
        rf"{name_phrase}\s*[:—–-]\s*$",
    ):
        matches = list(re.finditer(pattern, before, re.I | re.S))
        if matches:
            name = _clean_name(matches[-1].group(1))
            resolved = _resolve_candidate(name, candidates)
            if resolved:
                return resolved, 1.0

    # Identity statements inside the dialogue itself are stronger than
    # a trailing pronoun tag, e.g. "I'm Akeno Himejima," she said.
    for identity_pattern in (
        rf"\bmy name is\s+({NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,2}})",
        rf"\b(?:I['’]m|I am|this is)\s+({NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,2}})",
    ):
        identity = re.search(identity_pattern, text[max(0, start):end], re.I)
        if identity:
            resolved = _resolve_candidate(_clean_name(identity.group(1)), candidates)
            if resolved:
                return resolved, 0.99

    # Pronoun dialogue tags are common in novels. First-person tags are
    # safe when the narrator identity is known; third-person pronouns continue
    # the immediately previous speaker rather than inventing a new character.
    for pattern in (
        rf"^\s*[,;:—–-]?\s*I\s+(?:{SPEAKER_VERBS})\b",
        rf"^\s*[,;:—–-]?\s*(?:he|she|they)\s+(?:{SPEAKER_VERBS})\b",
        rf"^\s*[,;:—–-]?\s*(?:{SPEAKER_VERBS})\s+{name_phrase}\b",
        rf"^\s*[,;:—–-]?\s*{name_phrase}\s*(?:{SPEAKER_VERBS})\b",
        rf"^\s*[,;:—–-]?\s*{name_phrase}\s*[:—–-]",
    ):
        match = re.search(pattern, after, re.I | re.S)
        if match:
            tagged = match.group(0)
            if re.search(rf"\bI\s+(?:{SPEAKER_VERBS})\b", tagged, re.I):
                if narrator_name:
                    return narrator_name, 0.97
                if last_speaker:
                    return last_speaker, 0.72
            if re.search(rf"\b(?:he|she|they)\s+(?:{SPEAKER_VERBS})\b", tagged, re.I):
                if last_speaker:
                    return last_speaker, 0.62
            name = _clean_name(match.group(1)) if match.lastindex else ""
            resolved = _resolve_candidate(name, candidates) if name else None
            if resolved:
                return resolved, 0.98

    if narrator_name and re.search(rf"\bI\s+(?:{SPEAKER_VERBS})\b", before[-220:], re.I):
        return narrator_name, 0.96

    if last_speaker and re.search(rf"\b(?:he|she|they)\s+(?:{SPEAKER_VERBS})\b", before[-180:], re.I):
        return last_speaker, 0.62

    # Light-novel formatting often puts a speaker name on the line directly
    # before a quote (Name: "..." / Name「...」) or after a quote
    # ("...", Name said). Check a wider local window without guessing from
    # arbitrary capitalized prose.
    local_before = text[max(0, start - 180):start]
    local_after = text[end:min(len(text), end + 220)]
    for candidate in candidates:
        escaped = re.escape(candidate)
        if re.search(rf"\b{escaped}\s*[:—–-]\s*$", local_before, re.I):
            return candidate, 0.94
        if re.search(rf"[”\"」』]\s*,?\s*{escaped}\s+(?:{SPEAKER_VERBS})\b", local_after, re.I):
            return candidate, 0.94
        if re.search(rf"\b{escaped}\s+(?:{SPEAKER_VERBS})\b", local_after, re.I):
            return candidate, 0.92

    # PDF extraction can separate a speaker label from the quote onto
    # adjacent lines. Prefer an exact known candidate over contextual guessing.
    adjacent = text[max(0, start - 260):start]
    adjacent_after = text[end:min(len(text), end + 260)]
    for candidate in candidates:
        escaped = re.escape(candidate)
        if re.search(rf"(?m)^\s*{escaped}\s*$", adjacent, re.I):
            return candidate, 0.93
        if re.search(rf"(?m)^\s*{escaped}\s*$", adjacent_after, re.I):
            return candidate, 0.93

    # Some light-novel layouts place the character name in nearby narration
    # without a speech verb. Only use this when exactly one known candidate
    # occurs close to the quote, and expose the lower confidence to the UI.
    nearby = []
    nearby_text = local_before + "\n" + local_after
    for candidate in candidates:
        escaped = re.escape(candidate)
        if re.search(rf"\b{escaped}\b", nearby_text, re.I):
            nearby.append(candidate)
    if len(nearby) == 1:
        return nearby[0], 0.55

    return None, 0.0


def _resolve_candidate(name: str, candidates: list[str]) -> str | None:
    key = name.casefold()
    for candidate in candidates:
        if candidate.casefold() == key:
            return candidate
        if key in {part.casefold() for part in candidate.split()}:
            return candidate
    return None


def infer_speaker_for_quote(
    text: str,
    start: int,
    end: int,
    speaker_names: list[str],
    narrator_name: str | None = None,
    last_speaker: str | None = None,
) -> str | None:
    speaker, _ = _speaker_near_quote(
        text, start, end, speaker_names, narrator_name, last_speaker
    )
    return speaker


def _resolve_canonical(name: str, canonical: list[str], aliases: dict[str, set[str]]) -> str | None:
    key = name.casefold()
    for item in canonical:
        if item.casefold() == key:
            return item
        if key in {a.casefold() for a in aliases.get(item, set())}:
            return item
    return None


def _all_dialogue_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for pattern in DIALOGUE_PATTERNS:
        for match in pattern.finditer(text):
            spans.append((match.start(), match.end(), match.group(1)))

    # Light-novel dialogue may be represented by a dash-only line.
    # Detect the Unicode code points directly rather than relying on regex
    # character-class encoding.
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip(" \t")
        if stripped:
            first = ord(stripped[0])
            if first in (0x2014, 0x2013, 0x2D):
                dialogue = stripped[1:].strip()
                if len(dialogue) >= 2:
                    start = offset + (len(line) - len(stripped))
                    end = offset + len(line.rstrip("\r\n"))
                    spans.append((start, end, dialogue))
        offset += len(line)


    spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    result: list[tuple[int, int, str]] = []
    for span in spans:
        if result and span[0] < result[-1][1]:
            continue
        result.append(span)
    return result


def _clean_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip(" ,.;:!?—–-\"“”"))
    words = []
    for word in value.split():
        word = re.sub(r"^[A-Za-z]-", "", word)
        if word in {"Mr","Mrs","Ms","Miss","Dr","Father","Mother","Sister","Brother","Mistress","Lord","Lady"}:
            continue
        if word.endswith(("’s", "'s")) and len(value.split()) == 1:
            return ""
        words.append(word)
    return " ".join(words)


def _clean_dialogue(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value[:260] + ("…" if len(value) > 260 else "")


def _is_plausible_name(value: str) -> bool:
    value = _clean_name(value)
    if not value or len(value) > 80:
        return False
    words = value.split()
    if not 1 <= len(words) <= 3:
        return False
    if any(word.strip(".,!?;:") in NAME_STOPWORDS for word in words):
        return False
    if len(value) <= 12 and value.replace("-", "").replace("’", "").isupper():
        return False
    if not all(re.match(r"^[A-ZÀ-ÖØ-Þ]", word) for word in words):
        return False
    return any(len(word.strip(".,!?;:")) >= 3 for word in words)
