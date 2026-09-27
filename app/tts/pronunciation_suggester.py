from __future__ import annotations

import re

_KNOWN = {
    "hyoudou issei": "Hee-doh Is-say",
    "issei hyoudou": "Is-say Hee-doh",
    "ise": "Ee-say",
    "rias": "Ree-ahs",
    "rias gremory": "Ree-ahs Grem-or-ee",
}

_STOPWORDS = {"the", "this", "that", "chapter", "volume", "school", "academy"}

def suggest_pronunciation(name: str) -> str:
    key = re.sub(r"\s+", " ", name.strip()).casefold()
    if key in _KNOWN:
        return _KNOWN[key]
    words = [w for w in key.split() if w]
    return " ".join(_suggest_word(word) for word in words)

def _suggest_word(word: str) -> str:
    # Conservative readable approximation for romanized Japanese names.
    # This is a draft for the user to review, not a claim of authoritative IPA.
    replacements = [
        ("tch", "ch"), ("shi", "shee"), ("chi", "chee"),
        ("tsu", "tsoo"), ("fu", "foo"), ("ji", "jee"),
        ("ryu", "ryoo"), ("ryo", "ryoh"), ("kyo", "kyoh"),
        ("sho", "shoh"), ("cho", "choh"),
    ]
    value = word
    for src, dst in replacements:
        value = value.replace(src, dst)
    value = re.sub(r"ou$", "oh", value)
    value = re.sub(r"oo$", "oh", value)
    value = re.sub(r"ei$", "ay", value)
    value = re.sub(r"ei", "ay", value)
    value = re.sub(r"([aeiou])([bcdfghjklmnpqrstvwxyz])([aeiou])", r"\1-\2\3", value)
    value = re.sub(r"([aeiou])([bcdfghjklmnpqrstvwxyz])", r"\1-\2", value)
    value = value.replace("aa", "ah").replace("ee", "ee").replace("ii", "ee")
    value = value.replace("uu", "oo")
    return value.title()

def suggest_names_from_text(text: str) -> list[str]:
    candidates: set[str] = set()
    patterns = [
        r"\b([A-Z][a-z]+(?:[-'][A-Z][a-z]+)?(?:\s+[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?){1,2})\b",
        r"\b([A-Z][a-z]{2,})\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            value = match.group(1).strip()
            if len(value) > 2 and value.casefold() not in _STOPWORDS:
                candidates.add(value)
    return sorted(
        candidates,
        key=lambda x: (-len(re.findall(r"\b" + re.escape(x) + r"\b", text)), x.casefold()),
    )
