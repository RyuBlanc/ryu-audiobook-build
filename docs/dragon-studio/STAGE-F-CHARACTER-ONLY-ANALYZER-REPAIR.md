# Stage F — Character-only AI Book Analyzer repair

**Target branch:** \`dragon-studio/stage-f-multilingual-context-aware-tts-2026-11-21\`  
**Baseline inspected:** Build #3541 source \`6176898933efe7e8a1db613443606a3977daef85\`  
**Purpose:** Correct the reported regression where the Character Analyzer promoted a novel title or unrelated capitalised phrases as characters and took several hours to finish.

## Findings at the inspected baseline

The Character Studio worker invoked \`AudiobookBrain.analyze_book()\`. That is the broader audiobook-director pipeline, not a cast-extraction task. For each overlapping text window it performed a core request covering characters, dialogue, pronunciation, story summaries, themes, events, relationships and observations, then a separate scene-direction request. Malformed responses could trigger repeated repair requests.

The cast worker accepted a model name when it looked plausible and occurred somewhere in the book. Repetition or a high confidence score could let a title phrase or an unrelated proper-looking phrase survive. The worker did not require a model-supplied character evidence passage to match the source.

The earlier worker did not persist the model identity returned by inference. Its configured runtime was hardware-selected Qwen3 GGUF over llama.cpp unless \`RYU_AI_SERVER_URL\` supplied an external OpenAI-compatible server. Consequently, the model used for the user's previous three-hour analysis cannot be retrospectively proven from the old project report.

## New design

### Character-only inference

\`app/ai/character_cast.py\` provides a dedicated \`CharacterCastAnalyzer\`. It does not ask for or emit chapter summaries, scenes, dialogue mappings, themes, relationships, pronunciation rules or audiobook direction.

The analyzer:
1. Builds a source-derived candidate whitelist from the full chapter text. It uses the existing deterministic speaker/name recognisers, Unicode-aware speaker-label extraction and selected language-specific honorific patterns.
2. Excludes supplied work/series/chapter title phrases from the candidate inventory unless the story explicitly labels that phrase as a speaking individual.
3. Supplies a bounded set of exact source excerpts for each candidate to the local model.
4. Processes every candidate in batches of 24. It does not truncate the list to a fixed top-N.
5. Allows one compact JSON repair per failed batch, rather than restarting the entire book analysis.
6. Accepts only exact names from the source-derived batch whitelist. Every accepted name must include an exact quote that is contained in both the original chapter and the source excerpt supplied for that candidate.
7. Rejects unsupported aliases and fabricated names. A high confidence value cannot compensate for missing, paraphrased or fabricated evidence.
8. If inference and its one repair fail, returns only explicit source speaker labels for that batch and records a warning. It does not fall back to repeated capitalised words as characters.

The prompt includes short calibration examples for Japanese light-novel conventions and honorifics, English fiction, Chinese, Korean, Hindi/Devanagari and Tamil, with explicit negative examples for titles, places, organisations, objects and generic prose.

Dialogue passage indexing remains a separate deterministic/user-confirmation workflow. The AI character scan no longer sends model-generated dialogue speaker predictions into that workflow.

### Runtime/model identity

The configured text-analysis model is distinct from Qwen3-TTS voice generation:
- NVIDIA VRAM at or above 7 GB selects \`Qwen3-4B-Q4_K_M.gguf\` (\`qwen3-4b-q4\`).
- Other detected configurations select \`Qwen3-1.7B-Q5_K_M.gguf\` (\`qwen3-1.7b-q5\`).
- The local llama.cpp launch requests GPU-layer offload when the detected NVIDIA VRAM is at least 4 GB. This is an offload request, not proof that real inference executed on the GPU.
- \`RYU_AI_SERVER_URL\` overrides the local llama.cpp endpoint. In that case the analyzer records the server-reported model ID when present; otherwise it reports the model as unknown. It must not mislabel an external server as the local Qwen model.

The result records provider, model ID/file where defensible, model identity source, whether identity is verified, whether GPU offload was requested, and whether execution backend was actually verified. The external endpoint URL and secrets are never written to the report.

## Training and data honesty

This repair changes the task prompt, few-shot calibration, source filters and tests. **It does not fine-tune model weights and must not be described as completed model training.**

No representative, licensed/consented, human-labelled novel corpus or aligned training dataset was supplied with the bug report. Do not scrape or train on copyrighted novels without appropriate rights. A real fine-tuning project requires:
- licensed, public-domain or explicitly consented text samples from multiple literary traditions and scripts;
- human-labelled character identities, aliases, title/place/organisation/object negatives and exact source evidence;
- separate train, validation and held-out novel/series splits to prevent memorisation;
- per-language precision/recall, title false-positive rate, alias accuracy, Unicode preservation, inference latency and human-review scoring;
- a reversible, versioned model/checkpoint separate from the original model.

The multilingual prompt examples and regression fixtures are an initial calibration suite, not proof of extensive training or real-world multilingual accuracy.

## Required verification

- English, Japanese light-novel, Chinese, Korean and selected Indic-script fixture tests.
- Title/volume/chapter heading, place, organisation, weapon, spell and ordinary capitalised phrase rejection.
- No model-created name outside the deterministic candidate inventory.
- No character without exact source quote validation.
- Candidate batches all processed, with no silent fixed candidate cap.
- At most one repair request per candidate batch.
- No scene/dialogue/story-summary/pronunciation output from the character-only model.
- Local and external model identity reporting tests.
- Existing saved/manual cast, confirmed aliases, Unicode names, exclusions, cancellation and dialogue-assignment tests remain passing.
- Exact-head full regression and Windows package checks before the new candidate is treated as a packaged build.

## Performance acceptance still required

The prior reported three-hour analysis time is a user observation, not a captured profiler trace. The old model-call design is clearly excessive for cast-only work, and the new path reduces inference to one request per candidate batch (plus at most one repair per failed batch). However, no performance result should be claimed until the same book is rerun on the user's target PC and the report records:
- exact chapter count and source character count;
- candidate count, batch count, model request count and repair request count;
- elapsed time per batch and for the whole scan;
- provider/model identity and actual hardware/backend telemetry;
- total elapsed time and user-reviewed character precision/recall.

Do not call the book analysis accepted solely because CI tests pass.
