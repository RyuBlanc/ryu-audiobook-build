from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from app.documents.parser import clean_text, remove_page_noise


@dataclass(frozen=True)
class NarrationResult:
    source_text: str
    narration_text: str


def _normalize_typography(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    replacements = {
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u00a0": " ",
        "\u2013": "–",
        "\u2014": "—",
        "\u2212": "−",
    }
    return "".join(replacements.get(char, char) for char in text)


def _join_wrapped_lines(text: str) -> str:
    lines = text.split("\n")
    output: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            if output and output[-1] != "":
                output.append("")
            i += 1
            continue

        if not output or output[-1] == "":
            output.append(line)
            i += 1
            continue

        previous = output[-1]
        # Preserve explicit dialogue/paragraph boundaries.
        if (
            previous.endswith(('"', "”", "’", "'", ".", "!", "?", ":", ";", "…", "—"))
            or line.startswith(('"', "“", "「", "『", "-", "•"))
            or previous.startswith(('"', "“", "「", "『"))
        ):
            output.append(line)
            i += 1
            continue

        # PDF line wrapping: a lowercase/number continuation strongly
        # indicates the same sentence. Join it with a space.
        if line and (line[0].islower() or line[0].isdigit()):
            if previous.endswith("-") and not previous.endswith("--"):
                output[-1] = previous[:-1] + line
            else:
                output[-1] = previous + " " + line
            i += 1
            continue

        # A line ending without terminal punctuation followed by a short
        # lowercase continuation is also commonly an extraction wrap.
        if not re.search(r"[.!?…]$", previous) and len(previous.split()) < 14:
            if previous.endswith("-"):
                output[-1] = previous[:-1] + line
            else:
                output[-1] = previous + " " + line
            i += 1
            continue

        output.append(line)
        i += 1

    return "\n".join(output)


def apply_pronunciation_dictionary(text: str, dictionary: list[dict] | None = None) -> str:
    """Apply explicit written -> spoken pronunciation overrides.

    Matching is case-insensitive and phrase-aware. Only entries marked
    enabled are applied. The source text is never modified; this operates
    only on the narration copy.
    """
    if not dictionary:
        return text

    result = text
    entries = []
    for item in dictionary:
        if not isinstance(item, dict) or item.get("enabled", True) is False:
            continue
        written = str(item.get("written", "")).strip()
        spoken = str(item.get("spoken", "")).strip()
        if written and spoken:
            entries.append((written, spoken))

    entries.sort(key=lambda pair: len(pair[0]), reverse=True)
    for written, spoken in entries:
        pattern = re.compile(r"(?<!\\w)" + re.escape(written) + r"(?!\\w)", re.IGNORECASE)
        result = pattern.sub(lambda match: spoken, result)
    return result


def prepare_for_narration(
    text: str,
    pronunciation_dictionary: list[dict] | None = None,
) -> NarrationResult:
    """Prepare extracted book text for TTS without rewriting its meaning.

    This is intentionally a conservative narration layer: it fixes extraction
    and typography artifacts, but does not perform grammar correction or
    paraphrasing. The original source text is returned unchanged to the caller.
    """
    source = text
    narration = clean_text(remove_page_noise(source))
    narration = _normalize_typography(narration)
    narration = _join_wrapped_lines(narration)

    # Normalize whitespace while retaining paragraph boundaries.
    narration = re.sub(r"[ \t]+", " ", narration)
    narration = re.sub(r" *\n *", "\n", narration)
    narration = re.sub(r"\n{3,}", "\n\n", narration).strip()

    # Keep common PDF/extraction spacing from becoming awkward TTS input.
    narration = re.sub(r"\s+([,.;:!?])", r"\1", narration)
    narration = re.sub(r"([—–])\s+", r"\1 ", narration)
    narration = apply_pronunciation_dictionary(narration, pronunciation_dictionary)

    return NarrationResult(source_text=source, narration_text=narration)
