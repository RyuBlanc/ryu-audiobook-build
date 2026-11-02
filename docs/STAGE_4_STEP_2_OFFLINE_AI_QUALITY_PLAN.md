# Stage 4 Step 2 — Offline AI Quality and Learning Workstream

**Branch:** `stage-4/step-1-pronunciation-studio`  
**Status:** Added to Step 2 scope; implementation and acceptance are in progress.  
**Constraint:** All novel text, analysis, feedback memory, and inference remain local to the installed application. No cloud AI dependency is introduced.

## 1. Objective

By the end of Stage 4 Step 2, Ryu's Audiobook should provide a stronger, evidence-grounded offline analysis workflow across:

1. Novel-level themes, motifs, genre signals, narrative structure, and the overall emotional journey.
2. Chapter-level summaries, purpose, turning points, scene boundaries, emotional beats, mood/intensity, pacing, and narration direction.
3. Character identity, aliases, traits, motivations, goals, relationships, speech style, and development across chapters.
4. Multilingual and fictional-name pronunciation analysis, with exact source spelling, source language/script, TTS-friendly reading, IPA when supported, alternatives, confidence, and an explicit review flow.
5. A local feedback memory that improves later recommendations from corrections the user explicitly accepts or confirms.

The existing novel/chapter analysis flow is to be preserved and improved, not replaced with demo data or a cloud service.

## 2. Current repository baseline (audited)

- `app/ai/brain.py` provides the local `AudiobookBrain`, chapter-by-chapter core and scene passes, a character bible, scene mood/direction, pronunciation candidates, and continuity notes.
- The current chapter schema contains characters, dialogue, scenes, pronunciation, and continuity notes. It does not yet define a dedicated book-theme report, chapter-purpose/turning-point structure, full character arcs, or a relationship graph.
- `app/ai/model_runtime.py` currently installs a llama.cpp server and selects between Qwen3 1.7B and Qwen3 4B GGUF based on NVIDIA VRAM detection. It does not currently select AMD/Intel GPU runtimes based on actual supported backend availability.
- `app/chapters/character_learning.py` persists explicitly confirmed speaker-assignment examples per series. This is a useful safe-learning pattern, but is not yet a complete memory system for pronunciation corrections, character facts, emotional interpretation, or book themes.
- Pronunciation candidates are source-checked and confidence-filtered before AI suggestions are offered; accepted AI suggestions remain reviewable and are not silently auto-enabled.

## 3. First quality corrections

These are small, testable repairs before expanding the analysis schema:

- Make the excerpt chunker honour its configured overlap so names, scene transitions, and emotional beats near chunk boundaries retain context.
- Parse scene direction using the actual nested response schema (`narrator_direction` and `music`), while retaining compatibility with legacy flat scene payloads.
- Align the scene prompt with the schema supplied to the local inference runtime.
- Preserve source text and exact chapter offsets. Every evidence span must point to the original chapter text; normalization or pronunciation replacement must never shift the source offsets.
- Keep invalid/malformed model output, low-confidence guesses, and model-unavailable states visible. Never silently convert a failed model call into invented analysis.

## 4. Target analysis structure

Use a versioned, backward-compatible analysis result rather than changing existing fields in place.

### 4.1 Book-level report

- Book overview and supported genre signals.
- Main themes and sub-themes, each linked to chapter evidence.
- Recurring motifs, symbols, conflicts, and narrative questions.
- Overall emotional trajectory across the novel, with chapter-level changes.
- Major plot/structure milestones and continuity risks.
- Canonical cast index and character relationship graph.
- Confidence and coverage indicators; explicitly label unknown or weakly supported conclusions.

### 4.2 Chapter-level report

- Concise summary based only on the chapter.
- Chapter role/purpose in the larger story, when earlier/later chapter context is available.
- Main events, turning points, revelations, and unresolved hooks.
- Emotional beats as an ordered sequence (emotion, intensity, source evidence, approximate chapter offset).
- Scene list with location/time only when supported, mood, narrator pace/energy/delivery, ambience/music/SFX suggestions, and confidence.
- Continuity facts introduced, changed, or resolved in this chapter.

### 4.3 Character report

- Stable canonical ID/name and aliases, with evidence for every alias.
- Role, traits, motivations, goals, fears, relationships, and speech style.
- Chapter-by-chapter state and development arc (including contradictions or meaningful change rather than overwriting the first observation).
- Exact dialogue examples with chapter and source offsets.
- Separate observed fact, model inference, and user-confirmed fact.

### 4.4 Pronunciation report

- Exact original written form and source span.
- Detected language, script, and transliteration status.
- Recommended spoken form for the selected narrator/provider, and IPA only where the model is confident.
- Alternatives where the reading is genuinely ambiguous; do not select one silently.
- Confidence, short evidence/reason, and a clear unknown/needs-review state.
- Manual correction and acceptance saved as a user-approved pronunciation memory with series/book scope and provenance.

## 5. Safe continuous-learning design

“Learning as the project moves on” means a persistent local feedback loop, not silently changing model weights after every interaction.

- Record only explicit user actions: accept, edit-and-save, confirm, reject, or correct.
- Store the source excerpt/offset, chapter, canonical entity or term, accepted correction, series/book scope, model/prompt/schema version, and timestamp.
- Retrieve relevant confirmed examples for later chapters in the same series. Do not leak knowledge between unrelated series or books.
- Keep rejected/uncertain candidates from becoming positive training examples.
- A later correction replaces the conflicting example for the same source/context; retain an audit trail.
- Provide a way to inspect, undo, export, and clear the local learning memory.
- Use this memory first for retrieval and constrained ranking. Do not auto-fine-tune or rewrite model weights in the background.
- Optional LoRA/QLoRA adapter training can be evaluated later from curated, consented examples and a frozen benchmark; it is not required to ship the Step 2 feedback loop.

## 6. Local model and hardware strategy

- Keep model choice separate from analysis schemas and prompts so the application is not tied to one model generation.
- Benchmark the current Qwen3 1.7B/4B baseline against a current open-weight candidate, including Qwen3.5-4B. The official Qwen3.5-4B model card lists Apache-2.0 licensing and a 262,144-token native context; this is a candidate for evaluation, not an automatic replacement.
- Check GGUF conversion/quantization quality, llama.cpp support, structured-output reliability, multilingual pronunciation accuracy, memory usage, and cold/warm latency before adopting a new checkpoint.
- Probe supported backends rather than relying only on `nvidia-smi`. Test CPU fallback and available NVIDIA CUDA, AMD HIP/ROCm or Vulkan, and Intel-supported backends on actual target hardware.
- Bundle the runtime and model manager in the installed app; provide model install/repair/health/status, storage size, backend selected, and a truthful CPU/GPU acceleration status.
- Keep a small compatible default profile and allow a higher-quality optional profile where the target hardware can support it. Do not assume that a 27B model is appropriate for every user's PC.

## 7. Evaluation and acceptance gates

Build a versioned, local regression set covering:
- Japanese, Korean, Chinese, Hindi, Tamil, Telugu, Malayalam, Kannada, Bengali, Marathi, and other supported languages as appropriate.
- Romanized names, native scripts, honorifics, plural/possessive forms, code-switching, fictional terms, invented names, homographs, and ambiguous readings.
- Ordinary English words near sentence starts (must not become pronunciation overrides).
- Multi-chapter aliases, changing character relationships, unreliable narrators, emotional shifts, flashbacks, parallel scenes, and long chapters that cross chunk boundaries.

Required gates:
1. Every cited quote/name/pronunciation term must be found in the original source at the recorded chapter/offset. No fabricated source evidence.
2. Schema validation must pass; malformed JSON is repaired or reported as failed, not silently accepted.
3. Existing character/dialogue/scene/pronunciation regressions remain green.
4. High-confidence pronunciation precision is measured against human-reviewed examples; confidence thresholds are calibrated from results, not guessed.
5. Theme, emotion, and character-arc outputs are judged against a reviewed gold set, with evidence coverage and false-positive rates reported.
6. Accepted feedback must change a later recommendation only within the correct book/series scope; rejected feedback must not be learned as positive.
7. CPU, AMD, Intel and NVIDIA runs report actual backend, time-to-first-token, tokens/sec, peak memory, and model profile. No assumed GPU acceleration.
8. A real imported novel is analysed offline after the model/runtime is installed, with network access disabled during inference.
9. Target-PC acceptance includes review/edit/accept/reject/reopen persistence and pronunciation listening with real narrator profiles.

## 8. Step 2 work order

- **2.1 Pronunciation-to-production connectivity:** retain shared resolver, global and individual switches, source/cast-offset safety, and affected-chapter checkpoint invalidation. Automated integration gate passed in Build #2012; target-PC audio acceptance remains open.
- **2.2 Saved Sound Design integration:** align short/full previews with Voice Only, Same BGM, Chapter-Based BGM, cue switches, volumes/fades, and no-fallback rules. The new short-preview correction passed Build #2014; actual listening/installed-app acceptance remains open.
- **2.3 Cue placement and chapter boundaries:** verify opening, next-chapter, closing, chapter-specific BGM, start offsets, end behavior, first-paragraph boundaries, skipped chapters, and no double insertion.
- **2.4 Audio settings and failure recovery:** verify volumes, fades, invalid/missing asset behavior, preview/final parity, cancellation, FFmpeg/provider errors, retry, cleanup, and checkpoint safety.
- **2.5 Offline AI quality and learning:** fix chunk/schema defects, add versioned book/chapter/theme/emotion/character/pronunciation analysis, persist scoped user-approved learning, benchmark local model candidates and hardware backends, and run the offline golden-set plus real-novel acceptance gates.

## 9. Definition of Step 2 AI completion

Step 2 AI work is complete only when the enhanced reports are present in the installed application, stored locally, source-grounded, editable/reviewable, and useful across multiple chapters; the feedback loop demonstrably improves later analyses without cross-project leakage; the chosen model works with the installed runtime on supported CPU/GPU backends; and the evaluation report records actual quality/performance results.

This is an application-quality target, not a claim that a new foundation model has been trained from scratch or that every language has human-level pronunciation accuracy.
