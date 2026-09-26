from __future__ import annotations

from dataclasses import dataclass
import re

from app.chapters.detector import Chapter


@dataclass
class Character:
    name: str
    role: str
    dialogue_count: int = 0
    examples: list[str] | None = None


@dataclass
class CharacterAnalysis:
    narrator: Character
    characters: list[Character]


DIALOGUE_PATTERNS = [
    re.compile(r'[“"]([^”"]{2,500})[”"]'),
    re.compile(r'「([^」]{2,500})」'),
    re.compile(r'『([^』]{2,500})』'),
]

ATTRIBUTION_AFTER = re.compile(
    r'(?i)\b(?:said|asked|replied|answered|shouted|yelled|whispered|muttered|'
    r'called|cried|exclaimed|continued|added|insisted|wondered)\s+'
    r'([A-Z][A-Za-zÀ-ÖØ-öø-ÿ\'’-]{1,30}(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ\'’-]{1,30}){0,2})'
)
ATTRIBUTION_BEFORE = re.compile(
    r'(?i)\b([A-Z][A-Za-zÀ-ÖØ-öø-ÿ\'’-]{1,30}(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ\'’-]{1,30}){0,2})'
    r'\s+(?:said|asked|replied|answered|shouted|yelled|whispered|muttered|called|cried|exclaimed)'
)


def analyze_chapter(chapter: Chapter) -> CharacterAnalysis:
    """Local, reviewable first-pass character/dialogue analysis."""
    text = chapter.text
    found: dict[str, Character] = {}

    def add(name: str, dialogue: str = "") -> None:
        name = _clean_name(name)
        if not _is_plausible_name(name):
            return
        key = name.casefold()
        item = found.get(key)
        if item is None:
            item = Character(name=name, role="Story Character", examples=[])
            found[key] = item
        item.dialogue_count += 1
        if dialogue and len(item.examples or []) < 3:
            item.examples.append(_clean_dialogue(dialogue))

    for match in ATTRIBUTION_AFTER.finditer(text):
        start = max(0, match.start() - 650)
        add(match.group(1), _nearest_dialogue(text[start:match.start()]))

    for match in ATTRIBUTION_BEFORE.finditer(text):
        end = min(len(text), match.end() + 650)
        add(match.group(1), _nearest_dialogue(text[match.end():end]))

    if not found:
        names: dict[str, int] = {}
        for match in re.finditer(r'\b([A-Z][A-Za-zÀ-ÖØ-öø-ÿ\'’-]{2,24})\b', text):
            name = match.group(1)
            if name in {"The", "This", "That", "Then", "Chapter", "Part"}:
                continue
            names[name] = names.get(name, 0) + 1
        for name, count in sorted(names.items(), key=lambda x: (-x[1], x[0])):
            if count >= 3:
                found[name.casefold()] = Character(name, "Possible Character", 0, [])

    characters = sorted(found.values(), key=lambda c: (-c.dialogue_count, c.name.casefold()))
    for character in characters:
        character.role = (
            "Primary Character" if character.dialogue_count >= 8
            else "Supporting Character" if character.dialogue_count >= 2
            else "Possible Character"
        )

    return CharacterAnalysis(Character("Narrator", "Narrator", 0, []), characters)


def _nearest_dialogue(text: str) -> str:
    matches = []
    for pattern in DIALOGUE_PATTERNS:
        matches.extend(pattern.findall(text))
    return matches[-1] if matches else ""


def _clean_name(value: str) -> str:
    return re.sub(r'\s+', ' ', value.strip(" ,.;:!?-")).strip()


def _clean_dialogue(value: str) -> str:
    value = re.sub(r'\s+', ' ', value).strip()
    return value[:240] + ("…" if len(value) > 240 else "")


def _is_plausible_name(value: str) -> bool:
    if not value or len(value) > 80:
        return False
    words = value.split()
    return 1 <= len(words) <= 3 and all(re.match(r"^[A-ZÀ-ÖØ-Þ]", word) for word in words)
