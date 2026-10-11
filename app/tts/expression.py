from __future__ import annotations

import re

EXPRESSION_PIPELINE_VERSION = "story-expression-v2"

# The four reference styles preserve one character identity while providing
# audible differences in delivery. Other labels are mapped to these anchors.
EXPRESSION_STYLES = {
    "neutral": (
        "Natural conversational audiobook narration. Keep the same speaker identity, "
        "age, timbre, accent and vocal placement. Use gentle sentence-level pitch movement, "
        "clear phrasing and believable breath. Do not sound like a formal announcement."
    ),
    "thoughtful": (
        "Same exact speaker identity and timbre, but thoughtful or uncertain. Use a softer "
        "onset, a brief hesitation where the wording implies it, and restrained downward "
        "or searching pitch movement. Do not turn uncertainty into sadness or melodrama."
    ),
    "warm": (
        "Same exact speaker identity and timbre, with warmth, gentle amusement or contained "
        "excitement. Use a light smile in the voice and natural reactive lift on meaningful "
        "words. A faint chuckle is acceptable only when the text supports it."
    ),
    "concerned": (
        "Same exact speaker identity and timbre, with quiet concern or tension. Tighten the "
        "phrasing slightly, soften the voice when appropriate, and emphasize the words that "
        "carry risk or worry. Keep the performance controlled, never theatrical."
    ),
    "excited": (
        "Same exact speaker identity and timbre, with controlled excitement or surprise. "
        "Allow brighter pitch movement and quicker phrasing on the important words, but do "
        "not shout or turn the delivery into a different character."
    ),
    "soft": (
        "Keep the same exact character identity and vocal placement. Speak more softly and "
        "closely, with gentle breath and reduced force, while keeping every word intelligible."
    ),
    "sad": (
        "Keep the same exact character identity. Use restrained sadness, slightly gentler "
        "energy and a natural downward contour; do not cry or become breathlessly dramatic "
        "unless the text explicitly calls for that."
    ),
    "angry": (
        "Keep the same exact character identity. Deliver controlled anger through firmer "
        "consonants and focused emphasis, not an exaggerated growl or a different voice."
    ),
    "tense": (
        "Keep the same exact character identity. Use contained tension, slightly quicker "
        "or tighter phrasing and a focused, alert tone without shouting."
    ),
    "curious": (
        "Keep the same exact character identity. Sound genuinely curious, with a small "
        "upward searching contour and a natural question shape rather than a generic rise."
    ),
    "amused": (
        "Keep the same exact character identity. Use subtle amusement and lightness; do not "
        "insert laughter unless the text actually supports it."
    ),
    "serious": (
        "Keep the same exact character identity. Use grounded, composed delivery and clear "
        "emphasis on meaningful words without flattening the sentence."
    ),
    "reflective": (
        "Keep the same exact character identity. Use unhurried, inward-looking phrasing with "
        "small meaningful pauses and a gentle downward contour."
    ),
}

EXPRESSION_TEMPERATURES = {
    "neutral": 0.82,
    "thoughtful": 0.84,
    "warm": 0.88,
    "concerned": 0.86,
    "excited": 0.89,
    "soft": 0.83,
    "sad": 0.84,
    "angry": 0.87,
    "tense": 0.86,
    "curious": 0.85,
    "amused": 0.88,
    "serious": 0.82,
    "reflective": 0.83,
}

_STYLE_ALIASES = {
    "neutral": "neutral",
    "thoughtful": "thoughtful",
    "curious": "thoughtful",
    "reflective": "thoughtful",
    "soft": "thoughtful",
    "warm": "warm",
    "amused": "warm",
    "excited": "warm",
    "concerned": "concerned",
    "sad": "concerned",
    "angry": "concerned",
    "tense": "concerned",
    "serious": "neutral",
}


def classify_expression(text: str) -> str:
    """Classify the most likely delivery cue without treating every sentence as a mood."""
    value = str(text or "").strip()
    if not value:
        return "neutral"

    # Titles/headings should get a pause, not be mistaken for shouting because
    # they are typeset in capitals.
    letters = [char for char in value if char.isalpha()]
    if letters and value == value.upper() and len(value.split()) <= 14 and not re.search(r"[.!?…]$", value):
        return "neutral"
    low = value.casefold()

    # Explicit delivery/action cues take priority over punctuation.
    if re.search(r"\b(whisper(?:ed|ing)?|murmur(?:ed|ing)?|softly|quietly|under (?:her|his|their) breath|hushed)\b", low):
        return "soft"
    if re.search(r"\b(sob(?:bed|bing)?|wept|tears streamed|heartbroken|grief-stricken|mournful)\b", low):
        return "sad"
    if re.search(r"\b(furious|enraged|angrily|snapped|barked|how dare you|damn you|shut up)\b", low):
        return "angry"
    if re.search(r"\b(terrified|panicked|desperate|urgent|in a panic|danger|dangerous|run away|get back|help me|don't touch|do not touch|worried|afraid|fearful|anxious|trembl(?:ed|ing)|hurt|pain)\b", low):
        return "tense" if re.search(r"\b(terrified|panicked|desperate|urgent|run away|get back|help me|don't touch|do not touch)\b", low) else "concerned"
    if re.search(r"\b(laughed|laughing|chuckled|chuckling|smiled|smiling|grinned|amused|joked|teased|teasing|heh|haha)\b", low):
        return "amused"
    if re.search(r"\b(maybe|perhaps|i think|i wonder|not sure|could it be|i guess|hesitat(?:ed|ing)|uncertain|hesitant)\b", low) or "…" in value or "..." in value:
        return "thoughtful"
    if re.search(r"\b(curious|wondered|intrigued|eager to know)\b", low):
        return "curious"
    if re.search(r"\b(sad|sadly|sorrow|regret(?:ted|fully)?|lonely|miss(?:ed|ing) you|disappointed)\b", low):
        return "sad"
    if re.search(r"\b(seriously|in a low voice|firmly|solemnly|gravely|matter-of-fact)\b", low):
        return "serious"
    if re.search(r"\b(reflected|thought to himself|thought to herself|remembered|in retrospect)\b", low):
        return "reflective"

    # Punctuation helps only after semantic/action cues. A single exclamation
    # can convey a reaction, while urgent commands above take a tense path.
    if "?" in value and len(value.split()) <= 28:
        return "curious" if re.search(r"\b(what|why|how|really|who|where|when|which)\b", low) else "thoughtful"
    if "!" in value:
        if re.search(r"\b(wow|amazing|incredible|unbelievable|yes|awesome|fantastic|wonderful|brilliant|can't believe|no way)\b", low):
            return "excited"
        if re.search(r"\b(no|stop|wait|never|impossible|look out)\b", low):
            return "tense"
        return "excited"

    return "neutral"


def expression_instruction(base_voice_description: str, style: str) -> str:
    base = str(base_voice_description or "").strip()
    style_text = EXPRESSION_STYLES.get(style, EXPRESSION_STYLES["neutral"])
    natural_rules = (
        " Preserve the source wording and punctuation. Keep one unchanged speaker identity "
        "(same perceived age, gender presentation, timbre, accent, resonance and vocal placement); "
        "only the delivery should move with the sentence's meaning. Honor ellipses as real, brief "
        "hesitations and em dashes as interrupted-thought pauses. Questions should sound like "
        "questions; unfinished sentences should remain unfinished. Do not read formatting or "
        "stage directions aloud, add invented laughs, or over-act."
    )
    return f"{base}\n{style_text}{natural_rules}".strip()


def reference_style(style: str) -> str:
    """Map nuanced cues to one of four cached, stable-identity acoustic references."""
    return _STYLE_ALIASES.get(str(style or "neutral"), "neutral")


def expression_temperature(style: str) -> float:
    key = str(style or "neutral")
    return float(EXPRESSION_TEMPERATURES.get(key, EXPRESSION_TEMPERATURES.get(reference_style(key), 0.82)))
