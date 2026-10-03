from __future__ import annotations

import re

COMMON_ENGLISH_WORDS = {
    "a","an","and","are","as","at","be","been","being","but","by","can","could",
    "did","do","does","for","from","had","has","have","he","her","here","hers",
    "him","his","how","i","if","in","into","is","it","its","just","may","me",
    "more","most","my","no","not","of","on","one","or","our","ours","she","so",
    "some","such","than","that","the","their","theirs","them","then","there",
    "these","they","this","those","to","too","under","up","us","very","was",
    "we","were","what","when","where","which","who","whom","why","will","with",
    "would","you","your","yours",
    # Common content words that are frequently capitalized at sentence starts
    # and must never become pronunciation overrides just because the model
    # assigned them a non-English language label.
    "all","another","any","anything","around","back","because","before","between",
    "both","bring","call","called","can","close","come","comes","confirmed","day",
    "dead","down","each","even","every","first","found","from","get","give","go",
    "good","gravity","great","hey","holy","home","house","just","keep","know",
    "last","later","let","life","little","look","looks","made","make","man","master",
    "maybe","much","must","never","new","now","only","other","over","part","right",
    "said","same","see","sir","small","still","sure","take","tell","than","thing",
    "think","through","time","today","together","under","very","wait","want","well",
    "went","while","world","would",
}

_KNOWN = {
    "hyoudou issei": "Hee-doh Is-say",
    "issei hyoudou": "Is-say Hee-doh",
    "ise": "Ee-say",
    "rias": "Ree-ahs",
    "rias gremory": "Ree-ahs Grem-or-ee",
}

_STOPWORDS = COMMON_ENGLISH_WORDS | {"chapter", "volume", "school", "academy"}

def is_common_english_phrase(text: str) -> bool:
    """Return True when a candidate is ordinary English vocabulary, not a name."""
    words = [
        re.sub(r"[^A-Za-z'’-]", "", part).casefold()
        for part in str(text or "").split()
    ]
    words = [word for word in words if word]
    return bool(words) and all(word in COMMON_ENGLISH_WORDS for word in words)

def nativeish_pronunciation(name: str, language: str | None = None) -> str:
    """Create a TTS-friendly native-ish phonetic spelling for common romanized names.

    This is deliberately conservative. It is a readability aid for an English
    narrator, not an authoritative linguistic transcription.
    """
    key = re.sub(r"\s+", " ", str(name or "").strip()).casefold()
    lang = re.sub(r"[^a-z]", "", str(language or "").casefold())
    if key in _KNOWN:
        return _KNOWN[key]

    if lang in {"japanese", "ja", "jpn"}:
        value = key
        replacements = [
            ("dzu", "zoo"), ("tsu", "tsoo"), ("shi", "shee"), ("chi", "chee"),
            ("tchi", "chee"), ("fu", "foo"), ("ji", "jee"), ("ryu", "ryoo"),
            ("ryo", "ryoh"), ("kyo", "kyoh"), ("sho", "shoh"), ("cho", "choh"),
            ("ja", "jah"), ("ju", "joo"), ("jo", "joh"), ("nya", "nyah"),
            ("nyu", "nyoo"), ("nyo", "nyoh"),
        ]
        for src, dst in replacements:
            value = value.replace(src, dst)
        value = re.sub(r"ou", "oh", value)
        value = re.sub(r"oo", "oh", value)
        value = re.sub(r"ei", "ay", value)
        value = re.sub(r"([bcdfghjklmnpqrstvwxyz])(?=[aeiou])", r"-\1", value)
        value = re.sub(r"-+", "-", value).strip("-")
        # Clean the leading hyphen introduced by consonant-onset words.
        value = value.lstrip("-")
        return value.replace("  ", " ").title()

    if lang in {"korean", "ko", "kor"}:
        value = key
        replacements = [
            ("hyeon", "hyun"), ("gyeong", "kyung"), ("jeong", "jung"),
            ("seong", "sung"), ("yeong", "young"), ("eun", "uhn"),
            ("eop", "up"), ("eo", "uh"), ("eu", "uh"), ("ae", "eh"),
            ("oe", "weh"), ("ui", "wee"), ("woo", "oo"),
        ]
        for src, dst in replacements:
            value = value.replace(src, dst)
        value = re.sub(r"([bcdfghjklmnpqrstvwxyz])(?=[aeiou])", r"-\1", value)
        value = re.sub(r"-+", "-", value).strip("-")
        return value.replace("  ", " ").title().lstrip("-")

    if lang in {"chinese", "mandarin", "zh", "cmn"}:
        value = key
        replacements = [
            ("zh", "j"), ("q", "ch"), ("x", "sh"),
            ("c", "ts"), ("z", "dz"),
        ]
        for src, dst in replacements:
            value = value.replace(src, dst)
        return value.replace("  ", " ").title()

    return suggest_pronunciation(name)

def suggest_pronunciation(name: str) -> str:
    key = re.sub(r"\s+", " ", name.strip()).casefold()
    if key in _KNOWN:
        return _KNOWN[key]
    words = [w for w in key.split() if w]
    return " ".join(_suggest_word(word) for word in words)

def _suggest_word(word: str) -> str:
    return nativeish_pronunciation(word, "japanese")

def suggest_names_from_text(text: str) -> list[str]:
    candidates: set[str] = set()
    patterns = [
        r"\b([A-Z][a-z]+(?:[-'][A-Z][a-z]+)?(?:\s+[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?){1,2})\b",
        r"\b([A-Z][a-z]{2,})\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            value = match.group(1).strip()
            if len(value) > 2 and value.casefold() not in COMMON_ENGLISH_WORDS:
                candidates.add(value)
    return sorted(
        candidates,
        key=lambda x: (-len(re.findall(r"\b" + re.escape(x) + r"\b", text)), x.casefold()),
    )
