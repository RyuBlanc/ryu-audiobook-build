from __future__ import annotations

import re


# Light-novel and ebook headings vary widely. Keep these rules deterministic,
# anchored to the whole line, and conservative around narrative sentences.
_WORD_NUMBER = (
    r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"twenty[- ]?(?:one|two|three|four|five|six|seven|eight|nine)|"
    r"thirty|thirty[- ]?(?:one|two|three|four|five|six|seven|eight|nine)|"
    r"forty|forty[- ]?(?:one|two|three|four|five|six|seven|eight|nine)|"
    r"fifty|fifty[- ]?(?:one|two|three|four|five|six|seven|eight|nine)|"
    r"sixty|seventy|eighty|ninety|hundred|first|second|third|fourth|fifth|"
    r"sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|"
    r"fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|nineteenth|"
    r"twentieth|thirtieth|fortieth|fiftieth|sixtieth|seventieth|eightieth|"
    r"ninetieth|last)"
)
_NUMBER_TOKEN = rf"(?:\d{{1,4}}|[IVXLCDM]{{1,12}}|{_WORD_NUMBER})"
_SUFFIX = r"(?:(?P<delim>\s*[-:–—|.]\s*)(?P<delimited_title>.*)|\s+(?P<space_title>.*))?"

_CHAPTER_PREFIX_RE = re.compile(
    rf"^(?:chapter|chap(?:ter)?\.?|ch\.?)\s+(?P<number>{_NUMBER_TOKEN}){_SUFFIX}$",
    re.I,
)
_NUMBERED_SECTION_RE = re.compile(
    rf"^(?P<label>part|volume|vol\.?|book|arc|act|episode|ep\.?|section|"
    rf"intermission|scene|life|side[\s-]+story|extra|bonus)\s+"
    rf"(?P<number>{_NUMBER_TOKEN}){_SUFFIX}$",
    re.I,
)
_NAMED_SECTION_RE = re.compile(
    r"^(?P<label>prologue|epilogue|foreword|preface|introduction|afterword|"
    r"interlude|intermission|side[\s-]+story|extra|bonus|author['’]s\s+note|"
    r"translator['’]s\s+note|illustrations|cast\s+of\s+characters)"
    r"(?:(?P<delim>\s*[-:–—|]\s*)(?P<delimited_title>.*)|\s+(?P<space_title>.*))?$",
    re.I,
)
_TITLE_WITH_NUMBER_RE = re.compile(
    r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ _'’&/-]{0,35}\.(\d{1,4})\s*(.*)$",
    re.I,
)
_NEW_LIFE_RE = re.compile(r"^New\s+Life(?:\s*[:–—-]\s*(.*))?$", re.I)
_SLASH_TITLE_RE = re.compile(
    r"^[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ0-9'’\-]*"
    r"(?:\s+[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ0-9'’\-]*){0,3}/"
    r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ0-9'’\-]*"
    r"(?:\s+[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ0-9'’\-]*){0,3}$"
)

# Public for import/reflow callers and source-level compatibility. All actual
# decisions are made by heading_title(), including the body-sentence guard.
CHAPTER_HEADING_PATTERNS = (
    _CHAPTER_PREFIX_RE,
    _NUMBERED_SECTION_RE,
    _NAMED_SECTION_RE,
    _TITLE_WITH_NUMBER_RE,
    _NEW_LIFE_RE,
    _SLASH_TITLE_RE,
)
TOC_HEADING_RE = re.compile(
    r"^(?:table\s+of\s+contents|contents(?:\s+(?:of|for)\s+.{1,80})?)\s*[:.]?$",
    re.I,
)
_BODY_STARTERS = {
    "a", "an", "and", "as", "at", "because", "before", "but", "by",
    "could", "did", "do", "does", "he", "her", "here", "his", "how",
    "i", "if", "in", "into", "is", "it", "its", "my", "now", "of",
    "on", "or", "our", "she", "should", "so", "someone", "something",
    "than", "that", "then", "there", "they", "this", "those", "to",
    "until", "we", "were", "what", "when", "where", "which", "while",
    "who", "why", "will", "with", "would", "you", "your", "said",
    "asked", "replied", "answered", "looked", "turned", "walked",
}


def _normalize_line(line: str) -> str:
    value = str(line or "").replace("\u00a0", " ")
    value = re.sub(r"\s+", " ", value).strip()
    # Some EPUBs wrap headings with decorative brackets. Do not unwrap angle
    # quote dialogue such as <<a spell or telepathic line>>.
    wrappers = (
        (r"^【(.*)】$", r"\1"),
        (r"^\[(.*)\]$", r"\1"),
        (r"^「(.*)」$", r"\1"),
        (r"^『(.*)』$", r"\1"),
    )
    for pattern, replacement in wrappers:
        match = re.match(pattern, value)
        if match:
            value = match.group(1).strip()
            break
    return value


def is_slash_title_candidate(line: str) -> bool:
    """Recognize title-case headings such as 'Return/Attack' conservatively."""
    value = _normalize_line(line)
    if not value or len(value) > 80 or re.search(r"(?:https?://|www\.|<<|>>)", value, re.I):
        return False
    if re.search(r"[.!?。！？,:;]$", value):
        return False
    return bool(_SLASH_TITLE_RE.fullmatch(value))


def _suffix_parts(match: re.Match[str]) -> tuple[str, bool]:
    if match.groupdict().get("delimited_title") is not None:
        return (match.group("delimited_title") or "").strip(), True
    if match.groupdict().get("space_title") is not None:
        return (match.group("space_title") or "").strip(), False
    return "", bool(match.groupdict().get("delim"))


def _looks_like_body_sentence(line: str, suffix: str, has_explicit_separator: bool) -> bool:
    """Reject likely narrative lines that merely start with a chapter-like word."""
    suffix = suffix.strip()
    if not suffix:
        return False
    if len(line) > 120:
        return True
    # Quotes and sentence-final punctuation strongly indicate prose/dialogue,
    # not a heading. This also stops 'Chapter 2 was...' being treated as a title.
    if re.search(r'["“”„‟「」『』‘’]', suffix):
        return True
    if re.search(r"[.!?。！？…][\"”’」』)\]]*$", line):
        return True
    if len(re.findall(r"[.!?。！？]", suffix)) >= 2:
        return True
    if "," in suffix and len(suffix.split()) >= 7:
        return True
    if len(suffix.split()) > 14:
        return True
    first_word = re.match(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", suffix)
    if first_word and not has_explicit_separator and first_word.group(0).casefold() in _BODY_STARTERS:
        return True
    return False


def heading_title(line: str, *, allow_slash: bool = False) -> str | None:
    """Return a heading's display title, or None for ordinary narrative text.

    The parser anchors candidates to a whole line, supports common numeric and
    named section styles, and rejects sentence-like suffixes before splitting.
    """
    candidate = _normalize_line(line)
    if not candidate or len(candidate) > 140:
        return None
    if re.search(r"(?:https?://|www\.|justlightnovels\.com|asianovel\.com|mp4directs\.com)", candidate, re.I):
        return None
    if candidate.casefold() in {"table of contents", "contents"}:
        return None

    # Some light novels put the actual section heading on the next line:
    # "BLACK DOG/BIRTH" followed by "Part 1". Treat the pair as one displayed
    # title once the importer combines it, so it is also a chapter boundary.
    compound = re.fullmatch(
        rf"(?P<base>.+?\s*/\s*.+?)\s*[:：–—-]?\s+"
        rf"(?P<section>(?:part|volume|vol\.?|book|arc)\s+{_NUMBER_TOKEN})",
        candidate,
        re.I,
    )
    if compound:
        base = _normalize_line(compound.group("base"))
        section = re.sub(r"\s+", " ", compound.group("section").strip())
        if is_slash_title_candidate(base):
            return f"{base}: {section}"

    for pattern in (_CHAPTER_PREFIX_RE, _NUMBERED_SECTION_RE, _NAMED_SECTION_RE):
        match = pattern.fullmatch(candidate)
        if match:
            suffix, explicit_separator = _suffix_parts(match)
            if _looks_like_body_sentence(candidate, suffix, explicit_separator):
                continue
            return candidate

    match = _TITLE_WITH_NUMBER_RE.fullmatch(candidate)
    if match:
        suffix = (match.group(2) or "").strip()
        # The dotted number is itself a structural separator (e.g. Life.1 Title).
        if not _looks_like_body_sentence(candidate, suffix, True) and len(suffix.split()) <= 12:
            return candidate

    match = _NEW_LIFE_RE.fullmatch(candidate)
    if match:
        suffix = (match.group(1) or "").strip()
        if not _looks_like_body_sentence(candidate, suffix, True):
            return candidate

    if allow_slash and is_slash_title_candidate(candidate):
        return candidate
    return None


def is_chapter_heading_like(line: str) -> bool:
    """Compatibility helper used by text reflow to preserve chapter boundaries."""
    return heading_title(line, allow_slash=True) is not None
