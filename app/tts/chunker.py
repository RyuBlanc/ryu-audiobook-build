from __future__ import annotations

import re

def split_text(text: str, max_chars: int = 1800) -> list[str]:
    text = text.strip()
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
