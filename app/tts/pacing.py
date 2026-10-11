from __future__ import annotations

from pathlib import Path
import re
import wave


_CLOSERS = '"”»」』)]}’'
_PROFILE_EXTRA_PAUSE_MS = {
    "natural": 0,
    "relaxed": 110,
    "minimal": -70,
    "off": -999999,
}
_HEADING_PREFIX = re.compile(
    r"^(?:chapter|prologue|epilogue|interlude|afterword|foreword|part|volume|book)\b",
    re.IGNORECASE,
)
_DIALOGUE_START = ('"', "“", "「", "『", "—", "–", "-")
_SPEAKER_LINE = re.compile(r"^[A-Z][\w .'-]{0,30}:\s+['“\"]")
_ATTRIBUTION = re.compile(
    r"^(?:he|she|they|i|[A-Z][\w’'-]*(?:\s+[A-Z][\w’'-]*){0,2})"
    r"\s+(?:said|asked|replied|answered|whispered|murmured|shouted|called|cried|"
    r"continued|added|exclaimed|insisted|remarked|admitted|explained|began|finished)\b",
    re.IGNORECASE,
)


def is_heading_line(text: str) -> bool:
    """Recognize clear standalone headings without treating ordinary prose as one."""
    value = str(text or "").strip().strip("#").strip()
    if not value or len(value.split()) > 16 or re.search(r"[.!?…]$", value):
        return False
    if _HEADING_PREFIX.match(value):
        return True

    letters = [char for char in value if char.isalpha()]
    if letters and value == value.upper():
        return True

    # Title-case standalone chapter names such as "The Demon Lord Summit".
    words = [word.strip("\"'“”‘’()[]{}:;,.!?—–-") for word in value.split()]
    words = [word for word in words if word]
    minor = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "with"}
    alpha_words = [word for word in words if any(char.isalpha() for char in word)]
    return bool(
        2 <= len(words) <= 10
        and alpha_words
        and all(word[0].isupper() or word.casefold() in minor for word in alpha_words)
        and not value.endswith((":", ";", ",", "—", "–", "-"))
    )


def _starts_dialogue(text: str) -> bool:
    value = str(text or "").lstrip()
    return value.startswith(_DIALOGUE_START) or bool(_SPEAKER_LINE.match(value))


def sentence_units(text: str) -> list[str]:
    units: list[str] = []
    current: list[str] = []

    def flush() -> None:
        value = "".join(current).strip()
        if value:
            units.append(value)
        current.clear()

    i = 0
    while i < len(text):
        char = text[i]
        current.append(char)

        if char == "\n":
            # The narration reflow step has already joined visual line wraps.
            # Any remaining newline is intentional; keep its segment boundary.
            flush()
            i += 1
            continue

        if char == "." and text[i:i + 3] == "...":
            # Treat ASCII ellipses as one hesitation marker, not three full
            # stops. This prevents a meaningful pause from being lost.
            current.extend(text[i + 1:i + 3])
            flush()
            i += 2
            continue

        if char in ".!?…":
            j = i + 1
            while j < len(text) and text[j] in _CLOSERS:
                current.append(text[j])
                j += 1
            # Ellipsis is an intentional hesitation even when the next word
            # is attached directly ("me…then?"). Keep it as its own unit.
            attribution_follows = (
                j < len(text)
                and text[j].isspace()
                and bool(_ATTRIBUTION.match(text[j:].lstrip()))
            )
            if char == "…" or text[i:i + 3] == "..." or (
                not attribution_follows
                and (j >= len(text) or text[j].isspace())
            ):
                flush()
                i = j - 1

        i += 1

    flush()
    return units


def split_for_pacing(
    text: str,
    max_chars: int = 1400,
    max_sentences: int = 2,
    split_on_expression_change: bool = False,
) -> list[str]:
    """Split narration while preserving headings, paragraph boundaries and dialogue turns."""
    text = str(text or "").strip()
    if not text:
        return []

    max_chars = max(80, int(max_chars))
    max_sentences = max(1, int(max_sentences))
    # First preserve true blank-line paragraph boundaries. The document
    # reflow stage joins visual wraps before this point, so these boundaries
    # represent source structure rather than arbitrary display wrapping.
    paragraphs = [
        part.strip()
        for part in re.split(r"\n[ \t]*\n+", text)
        if part.strip()
    ]
    if not paragraphs:
        return []

    # Each token carries its paragraph id plus whether it is the last sentence
    # in that paragraph. This lets a flush preserve a longer paragraph breath.
    tokens: list[tuple[str, int, bool, bool, bool]] = []
    # (text, paragraph_id, is_paragraph_end, is_heading, is_dialogue_line)

    for paragraph_id, paragraph in enumerate(paragraphs):
        before = len(tokens)
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        ordinary: list[str] = []

        def flush_ordinary() -> None:
            if not ordinary:
                return
            merged = " ".join(ordinary).strip()
            ordinary.clear()
            if is_heading_line(merged):
                tokens.append((merged, paragraph_id, False, True, False))
                return
            pieces = sentence_units(merged)
            for piece in pieces:
                tokens.append((piece, paragraph_id, False, False, False))

        for line in lines or [paragraph]:
            if is_heading_line(line):
                flush_ordinary()
                tokens.append((line, paragraph_id, False, True, False))
            elif _starts_dialogue(line):
                flush_ordinary()
                line_pieces = sentence_units(line)
                # A quoted line remains separate from adjacent narration and
                # from another explicitly quoted speaker line. Sentences
                # within the same line may stay together as one turn.
                if line_pieces:
                    tokens.append((" ".join(line_pieces), paragraph_id, False, False, True))
            else:
                ordinary.append(line)
        flush_ordinary()

        if len(tokens) > before:
            # Mark the final unit of this paragraph unless the paragraph ends
            # in a standalone heading. A following paragraph can still merge
            # into a chunk, in which case the blank-line separator is retained.
            last_text, last_pid, _end, last_heading, last_dialogue = tokens[-1]
            if not last_heading:
                tokens[-1] = (last_text, last_pid, True, last_heading, last_dialogue)

    chunks: list[str] = []
    current: list[tuple[str, int, bool]] = []
    current_chars = 0

    def joined(items: list[tuple[str, int, bool]], mark_paragraph_end: bool = False) -> str:
        result = ""
        previous_paragraph = None
        for value, paragraph_id, _ends_paragraph in items:
            if result:
                result += "\n\n" if paragraph_id != previous_paragraph else " "
            result += value
            previous_paragraph = paragraph_id
        if mark_paragraph_end:
            result += "\n\n"
        return result

    def flush(mark_paragraph_end: bool = False) -> None:
        nonlocal current, current_chars
        if current:
            chunks.append(joined(current, mark_paragraph_end))
        current = []
        current_chars = 0

    expression_classifier = None
    expression_reference_style = None
    if split_on_expression_change:
        # Import only for providers which need story-emotion segmentation.
        # Comparing reference families keeps neutral/warm/concerned changes
        # expressive without splitting every sentence into a separate request.
        from app.tts.expression import classify_expression, reference_style
        expression_classifier = classify_expression
        expression_reference_style = reference_style

    for value, paragraph_id, ends_paragraph, heading, dialogue_line in tokens:
        # Keep a hesitation ending its own unit so the audio can carry the
        # pause before the continuation ("Instead of me... then?").
        if current and current[-1][0].rstrip().endswith(("…", "...")):
            flush(mark_paragraph_end=bool(current[-1][2]))
        if heading:
            # Headings get their own narration unit so they can receive a clear
            # pause both before and after the title.
            flush(mark_paragraph_end=bool(current and current[-1][2]))
            chunks.append(value)
            continue

        if dialogue_line:
            flush(mark_paragraph_end=bool(current and current[-1][2]))
            # Very long dialogue lines are still divided safely at sentence
            # boundaries/character limits, but regular turns remain intact.
            parts = sentence_units(value)
            line_chunk: list[tuple[str, int, bool]] = []
            line_chars = 0
            for piece in parts or [value]:
                if line_chunk and (
                    line_chars + len(piece) + 1 > max_chars
                    or len(line_chunk) >= max_sentences
                ):
                    chunks.append(joined(line_chunk))
                    line_chunk, line_chars = [], 0
                line_chunk.append((piece, paragraph_id, False))
                line_chars += len(piece) + (1 if line_chars else 0)
            if line_chunk:
                chunks.append(joined(line_chunk))
            continue

        separator = (
            "\n\n"
            if current and current[-1][1] != paragraph_id
            else " "
        )
        expression_changed = False
        if current and expression_classifier and expression_reference_style:
            current_text = " ".join(item[0] for item in current)
            current_family = expression_reference_style(expression_classifier(current_text))
            next_family = expression_reference_style(expression_classifier(value))
            expression_changed = current_family != next_family
        would_exceed = bool(current) and (
            current_chars + len(separator) + len(value) > max_chars
            or len(current) >= max_sentences
            or expression_changed
        )
        if would_exceed:
            flush(mark_paragraph_end=bool(current[-1][2]))
            separator = " "
        current.append((value, paragraph_id, ends_paragraph))
        current_chars += len(value) + (len(separator) if current_chars else 0)
        if value.rstrip().endswith(("…", "...")):
            flush(mark_paragraph_end=ends_paragraph)

        # A paragraph-ending unit is held briefly to see whether the next
        # paragraph fits in this chunk. If it does not, flush() writes an
        # invisible-to-speech blank-line marker consumed by pause_after_ms().

    flush(mark_paragraph_end=bool(current and current[-1][2]))
    return [chunk for chunk in chunks if chunk.strip()]


def pause_after_ms(
    text: str,
    profile: str = "natural",
    next_text: str | None = None,
) -> int:
    """Return a deterministic, story-aware gap between narration units."""
    profile = (profile or "natural").lower()
    if profile == "off":
        return 0

    paragraph_end = str(text or "").endswith("\n\n")
    stripped = str(text or "").strip()
    if not stripped:
        return 0

    if is_heading_line(stripped):
        base = 760
    else:
        end = stripped[-1]
        if end in "!?…":
            base = 360
        elif end == ".":
            base = 290
        elif end in ";:":
            base = 210
        elif end == ",":
            base = 110
        elif end in "—–-":
            base = 170
        else:
            base = 90

        if stripped.endswith(tuple(_CLOSERS)):
            without_closer = stripped.rstrip(_CLOSERS).rstrip()
            if without_closer.endswith(("?", "!", "…")):
                base = 360
            elif without_closer.endswith("."):
                base = 290

    if paragraph_end:
        base = max(base, 520)
    if "\n\n" in str(text or "").rstrip("\n"):
        base = max(base, 460)

    if next_text and is_heading_line(next_text):
        base = max(base, 650)
    elif next_text and _starts_dialogue(next_text):
        # A new spoken turn deserves a little breathing room, but not a
        # theatrical pause between quick exchanges.
        base = max(base, 310)

    base += _PROFILE_EXTRA_PAUSE_MS.get(profile, 0)
    return max(50, base)


def append_silence(path: Path, duration_ms: int) -> None:
    """Append PCM silence to a generated WAV without changing its voice/pitch."""
    if duration_ms <= 0:
        return

    with wave.open(str(path), "rb") as source:
        params = source.getparams()
        frames = source.readframes(source.getnframes())

    if params.comptype != "NONE":
        raise RuntimeError(f"Cannot add narration pacing to compressed WAV: {path.name}")

    silence_frames = max(0, round(params.framerate * duration_ms / 1000.0))
    if silence_frames <= 0:
        return

    silence = b"\x00" * silence_frames * params.nchannels * params.sampwidth
    temp = path.with_suffix(".pacing.wav")
    with wave.open(str(temp), "wb") as target:
        target.setparams(params)
        target.writeframes(frames + silence)
    temp.replace(path)
