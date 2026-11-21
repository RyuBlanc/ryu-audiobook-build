# Stage F — Multilingual contextual Qwen speech and training gate

## Runtime behavior in this candidate

- Each Qwen output chunk receives a bounded window of preceding and following story text. This context is never appended to the words being spoken.
- Explicit nearby speech attributions (for example, "she whispered," immediately before a quote) and clear plot context can refine short reactions such as "Yes..." or "Really?". A complete line's own strong action or emotion remains authoritative.
- 1.7B CustomVoice and VoiceDesign receive context as instruction-only material. 0.6B CustomVoice does not support instruction text, and Base/Clone does not expose the same per-utterance instruction channel; those paths use context-derived style selection and controlled sampling instead.
- Pronunciation dictionary matching covers Japanese, Korean, Chinese, Indic, Arabic, Thai, Myanmar and Khmer scripts. The local AI review flow can propose high-confidence foreign terms as well as character names. AI suggestions remain disabled until user review and acceptance.
- Mostly-English passages stay in selected English when they contain an isolated CJK name; meaningful CJK phrases may use Qwen's multilingual Auto route. Explicit saved language remains authoritative.

## Model support boundary

Qwen3-TTS lists Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish and Italian as supported synthesis languages. Indian-language words embedded in an English audiobook therefore need a reviewed phonetic pronunciation entry for English narration; this patch does not claim native Qwen synthesis support for every Indian language.

## Fine-tuning is a separate acceptance track

No model weights are changed by this patch. The upstream Qwen3-TTS fine-tuning guide currently documents single-speaker SFT for 12Hz Base 0.6B and 1.7B. Multi-speaker and other advanced fine-tuning remain a separate upstream capability gap. This does not establish a supported fine-tuning path for every CustomVoice, VoiceDesign and Clone mode used by the app.

Before any Ryu-managed training run:
1. Use only audio and transcripts owned, licensed, or explicitly consented for this purpose. Novel text alone is not a substitute for aligned audio/transcripts or voice rights.
2. Build a versioned dataset with exact transcript alignment, language/dialect tags, original script, approved romanization/IPA, speaker identity, and before/after context.
3. Label emotion with restrained intensity and dialogue attribution, including neutral, uncertainty, warmth, fear, sadness, anger, curiosity and mixed/ambiguous cases.
4. Keep train/validation/test sets separated by source and speaker as appropriate. Evaluate pronunciation error, speaker similarity, language switching, naturalness, emotion accuracy, hallucination rate and long-form consistency with automated checks and human listening.
5. Preserve original models and profiles; store fine-tuned checkpoints as separately versioned, reversible model/profile entries.

Upstream references:
- Qwen3-TTS: https://github.com/QwenLM/Qwen3-TTS
- Fine-tuning workflow: https://github.com/QwenLM/Qwen3-TTS/blob/main/finetuning/README.md

A hosted CPU preview or passing source-level test is not proof of acceptable real-GPU speed or natural audio. Those gates remain separate.
