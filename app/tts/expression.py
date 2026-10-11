from __future__ import annotations

import re


# These styles deliberately stay subtle. They are not separate voices; they are
# delivery targets for the same designed character identity.
EXPRESSION_STYLES = {
    "neutral": (
        "Natural conversational audiobook delivery. Keep the same speaker identity, "
        "age, timbre, accent, and vocal placement. Calm, attentive, lightly expressive, "
        "with natural sentence-level pitch movement and breathing."
    ),
    "thoughtful": (
        "Same exact speaker identity and timbre, but gently thoughtful and uncertain. "
        "Use a small hesitation, softer onset, restrained pitch movement, and a short "
        "natural pause where the wording implies uncertainty. Do not become dramatic."
    ),
    "warm": (
        "Same exact speaker identity and timbre, with subtle warmth and quiet amusement. "
        "Use a gentle smile in the voice, slightly lighter phrasing and a soft reactive "
        "lift when appropriate. A faint breathy chuckle is acceptable only when the text "
        "clearly supports it. Never turn it into a different character."
    ),
    "concerned": (
        "Same exact speaker identity and timbre, with restrained concern. Use slightly "
        "tighter pacing, a small downward or hesitant pitch movement, and careful emphasis "
        "on important words. Keep the emotion believable and understated."
    ),
    "excited": (
        "Same exact speaker identity and timbre, with controlled excitement or surprise. "
        "Allow brighter pitch movement and quicker phrasing on emphasis, but keep the "
        "performance natural rather than theatrical."
    ),
}

EXPRESSION_TEMPERATURES = {
    "neutral": 0.82,
    "thoughtful": 0.86,
    "warm": 0.90,
    "concerned": 0.88,
    "excited": 0.92,
}


def classify_expression(text: str) -> str:
    value = str(text or "").strip()
    low = value.casefold()
    if not value:
        return "neutral"

    if (
        "…" in value
        or "..." in value
        or re.search(r"\b(hmm+|maybe|perhaps|i think|i wonder|not sure|could it|am i|really\?)\b", low)
    ):
        return "thoughtful"

    if (
        re.search(
            r"\b(laugh|laughed|laughing|chuckle|chuckled|smile|smiled|smiling|grin|grinned|amused|relieved|relief|joked|playful|tease|teasing)\b",
            low,
        )
        or "heh" in low
        or "haha" in low
    ):
        return "warm"

    if re.search(
        r"\b(worry|worried|worrying|afraid|fear|feared|danger|dangerous|careful|terrified|anxious|cry|cried|trembl|hurt|pain|serious|uneasy|concerned)\b",
        low,
    ):
        return "concerned"

    if (
        value.count("!") >= 2
        or re.search(r"\b(wow|amazing|incredible|unbelievable|yes!|awesome|fantastic|excited|suddenly)\b", low)
    ):
        return "excited"

    if "?" in value and len(value.split()) <= 24:
        return "thoughtful"

    return "neutral"


def expression_instruction(base_voice_description: str, style: str) -> str:
    base = str(base_voice_description or "").strip()
    style_text = EXPRESSION_STYLES.get(style, EXPRESSION_STYLES["neutral"])
    natural_rules = (
        " Preserve punctuation and paragraph meaning. When a proper noun or short phrase clearly belongs to another supported language, prefer its native pronunciation rather than spelling it with English phonetics. Treat an internal ellipsis (…) as a "
        "real brief hesitation, not ordinary sentence punctuation. Treat an em dash as a "
        "small interrupted-thought pause. Do not read stage directions aloud. Do not flatten "
        "questions or uncertainty into a generic declarative sentence. Never change speaker identity."
    )
    return f"{base}\n{style_text}{natural_rules}".strip()


def expression_temperature(style: str) -> float:
    mapped = reference_style(style)
    return float(EXPRESSION_TEMPERATURES.get(mapped, EXPRESSION_TEMPERATURES["neutral"]))


# Keep the reference bank small enough for 4-GB GPUs. These aliases still
# provide distinct delivery direction without creating five separate speaker banks.
STYLE_ALIASES = {
    "neutral": "neutral",
    "thoughtful": "thoughtful",
    "warm": "warm",
    "concerned": "thoughtful",
    "excited": "warm",
}


def reference_style(style: str) -> str:
    return STYLE_ALIASES.get(str(style or "neutral"), "neutral")
