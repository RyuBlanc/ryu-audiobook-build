from __future__ import annotations

import re

def normalize_narration_text(text: str) -> str:
    """Turn document line-wrapping into natural narration text.

    Single newlines are usually PDF/EPUB layout wrapping rather than spoken
    paragraph breaks. Preserve blank lines as paragraph boundaries while
    joining wrapped lines with spaces.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\.{3,}", "…", text)
    text = re.sub(r"\s+([,!?;:])", r"\1", text)

    # Preserve ALL CAPS. The narration layer will use caps as an
    # explicit emphasis cue rather than normalizing them away.
    return text.strip()


def split_text(text: str, max_chars: int = 1800) -> list[str]:
    text = normalize_narration_text(text)
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                chunks.append(current)
            current = paragraph
            continue

        if current:
            chunks.append(current)
            current = ""

        sentences = re.split(r"(?<=[.!?…])\s+", paragraph)
        for sentence in sentences:
            if not sentence:
                continue
            if len(sentence) > max_chars:
                for start in range(0, len(sentence), max_chars):
                    chunks.append(sentence[start:start + max_chars].strip())
            elif not chunks or len(chunks[-1]) + len(sentence) + 1 > max_chars:
                chunks.append(sentence.strip())
            else:
                chunks[-1] = f"{chunks[-1]} {sentence}".strip()

    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk]
