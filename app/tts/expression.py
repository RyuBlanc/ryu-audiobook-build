from __future__ import annotations

import re

EXPRESSION_PIPELINE_VERSION = "story-expression-v2"
DEFAULT_VOICE_DESIGN_ANCHOR_TEXT = (
    "Hello. I thought I understood what was happening. "
    "Oh, really? That's actually wonderful. "
    "Wait... something isn't right. Let's think for a moment."
)

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
    "bored": (
        "Keep the same exact character identity. Use restrained energy and modest pitch movement "
        "to convey disinterest without mumbling, losing clarity, or sounding like a different speaker."
    ),
    "calm": (
        "Keep the same exact character identity. Use relaxed, even phrasing and quiet confidence "
        "without flattening the sentence or losing natural emphasis."
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
    "bored": 0.80,
    "calm": 0.81,
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
    "bored": "thoughtful",
    "calm": "neutral",
}


def classify_expression(text: str) -> str:
    """Classify the most likely delivery cue without treating every sentence as a mood."""
    value = str(text or "").strip()
    if not value:
        return "neutral"

    # Titles/headings should get a pause, not be mistaken for shouting because
    # they are typeset in capitals.
    # Only Latin all-caps headings are treated as typography. Unicode scripts
    # without case (for example Japanese) compare equal to upper(), so using
    # str.upper() alone incorrectly classified their whole sentences neutral.
    latin_letters = re.findall(r"[A-Za-z]", value)
    has_native_script = bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]", value))
    if not has_native_script and latin_letters and all(char.isupper() for char in latin_letters) and len(value.split()) <= 14 and not re.search(r"[.!?…]$", value):
        return "neutral"
    low = value.casefold()

    # Explicit delivery/action cues take priority over punctuation.
    if re.search(r"\b(whisper(?:ed|ing)?|murmur(?:ed|ing)?|softly|quietly|under (?:her|his|their) breath|hushed)\b", low):
        return "soft"
    if re.search(
        r"\b(?:sob(?:bed|bing)?|cry|cries|cried|crying|wept|weep(?:ing)?|tears?|"
        r"heartbroken|grief-stricken|mournful|sad|sadly|sorrow|regret(?:ted|fully)?|"
        r"lonely|miss(?:ed|ing) you|disappointed)\b|[泣涙悲愴寂]",
        low,
    ):
        return "sad"
    if re.search(
        r"\b(?:angry|anger|furious|enraged|angrily|snapped|barked|how dare you|"
        r"damn you|shut up)\b|(?:激怒|怒鳴|怒|腹を立)",
        low,
    ):
        return "angry"
    if re.search(
        r"\b(?:terrified|panicked|desperate|urgent|in a panic|danger|dangerous|"
        r"run away|get back|help me|don't touch|do not touch|worried|afraid|"
        r"fearful|anxious|trembl(?:ed|ing)|hurt|pain)\b|[怖恐怯震]|不安",
        low,
    ):
        return "tense" if re.search(
            r"\b(?:terrified|panicked|desperate|urgent|run away|get back|help me|"
            r"don't touch|do not touch)\b|[怖恐怯]",
            low,
        ) else "concerned"
    if re.search(
        r"\b(?:laughed|laughing|chuckled|chuckling|smiled|smiling|grinned|amused|"
        r"joked|teased|teasing|heh|haha)\b|[笑]|くすくす|爆笑",
        low,
    ):
        return "amused"
    if re.search(
        r"\b(?:surpris(?:ed|ing)?|astonish(?:ed|ing)?|startl(?:ed|ing)|stunned|"
        r"taken aback)\b|驚|びっくり|仰天",
        low,
    ):
        return "excited"
    if re.search(
        r"\b(?:happy|happily|joyful|joyfully|glad|pleased|delighted|thrilled|"
        r"cheerful|beamed)\b|幸せ|嬉",
        low,
    ):
        return "warm"
    if re.search(
        r"\b(?:bored|boredom|uninterested|listless|tedious)\b|退屈|つまらな|飽きた",
        low,
    ):
        return "bored"
    if re.search(
        r"\b(?:calm|calmly|peaceful|serene|tranquil|composed|settled)\b|穏やか|落ち着|安心",
        low,
    ):
        return "calm"
    if re.search(r"\b(maybe|perhaps|i think|i wonder|not sure|could it be|i guess|hesitat(?:ed|ing)|uncertain|hesitant)\b", low) or "…" in value or "..." in value:
        return "thoughtful"
    if re.search(r"\b(curious|wondered|intrigued|eager to know)\b", low):
        return "curious"
    if re.search(r"\b(sad|sadly|sorrow|regret(?:ted|fully)?|lonely|miss(?:ed|ing) you|disappointed)\b", low):
        return "sad"
    if re.search(r"\b(serious|seriously|in a low voice|firmly|solemnly|gravely|matter-of-fact)\b|真剣|厳か|冷静", low):
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


def voice_design_anchor_instruction(base_voice_description: str) -> str:
    """Describe one stable identity with a modest, audible range of story delivery.

    VoiceDesign accepts natural-language instructions. We use that capability
    once to create the shared reference, then reuse that single reference in
    Base cloning so per-sentence emotion does not switch to a separately
    generated voice or change the requested gender/pitch presentation.
    """
    base = str(base_voice_description or "").strip()
    anchor_direction = (
        "Create one consistent audiobook character voice matching the description above. "
        "Preserve its specified gender presentation, perceived age, pitch range, timbre, "
        "resonance, accent, and vocal placement in every sentence; do not raise the pitch "
        "outside the described range or change into a different-sounding speaker. "
        "Speak the supplied reference text as one continuous performance with subtle, "
        "believable delivery changes: begin calm and conversational; let the next sentence "
        "carry warm, pleasantly surprised energy; make the sentence beginning 'Wait...' "
        "sound briefly concerned; finish reflective and settled. Keep these changes in "
        "intonation, emphasis, rhythm, and energy rather than exaggerated acting. "
        "Do not add words, stage directions, laughter, singing, or dramatic effects. "
        "This should sound like one character reacting naturally, not four different voices."
    )
    return f"{base}\n{anchor_direction}".strip()


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
