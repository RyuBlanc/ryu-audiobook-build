# Stage 4 — Step 2 Closeout Evidence (2 November 2026)

Repository: `RyuBlanc/ryu-audiobook-build`  
Working branch: `stage-4/step-1-pronunciation-studio`  
Scope: Stage 4 Step 2 — Pronunciation, Sound Design, Offline AI report and audio-output integration.

## Status

**Implementation and Windows automated regression gates: PASS.**  
**Matching Windows artifact checkpoint from the latest Step 2 source: PENDING this commit's workflow.**  
**Target-PC interactive acceptance and subjective listening: PENDING external evidence.**

Do not mark Step 2 fully accepted until the matching artifact checkpoint succeeds and the target-PC items below are recorded. The user-facing interface remains the approved Premium V2 UI; existing Stage 2 Sound Design/Music Library screens were not rebuilt.

## Latest test evidence

- Run #2050: Windows application artifact checkpoint passed on `b195208477b97e88b4c7e5d03852d2fd0c523d06`; 1,033/1,033 tests passed, frozen app and packaged Stage 2 Sound Design/Music Library acceptance passed, installer and portable artifacts uploaded. [Run #2050](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41384450246)
- Run #2051: first-open dynamic report loading and explicit 18% master BGM default changes passed; 1,036/1,036 tests passed on `1a66d6c9c2d5bd042673b83ce862d37d69e6b723`. The build job was skipped because this was a focused implementation/test commit, not an artifact checkpoint. [Run #2051](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41391307213)
- Run #2052: added real FFmpeg/M4B integration tests passed; 1,039/1,039 tests passed on `b2b4451965c0f382a2e25eca232a213c9217a6b1`. [Run #2052](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41391707158)

The #2052 new integration tests rendered and decoded real M4B files and verified:
1. Opening cue → first chapter → Next Chapter cue → each subsequent chapter → Closing cue, at the expected order and once per applicable boundary.
2. Voice Only contains narration without the saved book BGM or configured fixed cues.
3. Same BGM uses the book-default track; Chapter-Based BGM uses explicit chapter assignments and does not fall back to the book-default track for unassigned chapters.

Expected FFmpeg error traces from negative-path cleanup tests (such as injected FFmpeg failure and unmeasurable preview duration) are deliberate test stimuli; the full suite ended with 1,039 tests and OK.

## Substep evidence

### 2.1 — Pronunciation settings into production

Status: **Automated connectivity passed; target-PC speech acceptance pending.**

The effective dictionary used by production and preview honours the saved project master pronunciation switch, individual enabled entries and Book → matching Series → Global precedence. The production-generation path passes the effective saved rules into the generation manager. Regression coverage verifies scope resolution, disabled entries, source-text preservation, replacement counts/normalization and checkpoint invalidation.

Relevant tests include:
- `tests/test_stage4_pronunciation_application.py`
- `tests/test_stage4_pronunciation_persistence.py`
- `tests/test_stage4_pronunciation_dictionary.py`
- `tests/test_stage4_voice_preview_contract.py`

### 2.2 — Same BGM, Chapter-Based BGM and Voice Only

Status: **Automated and rendered-M4B integration passed.**

The shared assembler consumes the saved BGM strategy. Chapter-Based BGM is an exclusive strategy: unassigned chapters remain without BGM and a saved book-default path is not used as a fallback. Voice Only suppresses both BGM and fixed cues without deleting saved preferences.

Relevant coverage:
- `tests/test_stage4_sound_design_preview.py`
- `tests/test_stage828_sound_design_preview.py`
- `tests/test_stage4_sound_design_audio_integration.py`

### 2.3 — Opening, Next Chapter and Closing cues

Status: **Automated validation and rendered-M4B placement/order test passed.**

Only the three supported fixed cue slots are used. Unassigned slots remain silent; missing explicit assignments fail closed rather than falling back to unrelated tracks. The new FFmpeg integration test validates actual cue order and boundary timing in a decoded M4B.

Still required: human listening on the target PC to confirm the selected cues sound suitable and are audible at the intended levels.

### 2.4 — Volume, fades, timing and missing assets

Status: **Automated/package checks passed; target-PC level/listening review pending.**

- Fresh and legacy project state now has an explicit master BGM default of 0.18 (18%).
- The master BGM gain is capped at 50% at the assembler boundary.
- Zero volume is preserved as zero.
- Saved fades, chapter offsets and end behaviours are passed to the common assembler.
- Missing, unsupported, unreadable or incorrectly typed selected assets fail closed.
- Source assets are protected from output overwrite.

Relevant coverage:
- `tests/test_stage4_sound_design_catalogue.py`
- `tests/test_stage4_sound_design_preflight.py`
- `tests/test_stage4_sound_design_preview.py`
- `tests/test_stage828_sound_design_preview.py`
- `tests/test_stage4_preview_assembly.py`

### 2.5 — Dynamic offline AI report and saved learning context

Status: **Dynamic implementation and widget/regression tests passed; real imported-book runtime acceptance pending.**

The report window reads the current project's saved `analysis/audiobook_brain.json`, renders only the sections actually present in saved analysis, refreshes after new saved data, and displays an explicit empty state rather than fabricated samples. The report now loads on first open instead of requiring the user to click Refresh before seeing existing data.

Saved contextual learning reads the active Book, its matching Series, Global pronunciation preferences and only explicitly user-confirmed speaker examples.

Relevant coverage:
- `tests/test_stage4_ai_analysis_report.py`
- `tests/test_stage4_offline_ai_context.py`
- `tests/test_stage4_offline_ai_quality.py`
- `tests/test_dialogue_assignment.py`

## Failure and cancellation history

Earlier failed workflow runs were not erased or relabelled as successes. Their root causes were addressed in subsequent commits and later matching-head regressions passed:

- #2013: preview BGM strategy/Voice Only leakage; addressed by #2014 and confirmed by #2050/#2052.
- #2015–#2021: offline-AI chunk/nested-scene and sound-cue/asset-validation regressions; subsequent scene merger and sound-design changes passed by #2036 and later full suites.
- #2031–#2035: nested scene payload and AI learning integration regressions; scene music correction #2036 succeeded; subsequent scoped learning and full-suite checks passed.
- #2040–#2045: offline AI report/UI, Qt lifecycle and regression discovery issues; subsequent fixture and harness corrections passed in #2049/#2050.
- #2046–#2048: Python Boolean literal and missing book-analysis fixture errors; fixture correction #2049 succeeded; #2050/#2051/#2052 passed.

Cancelled historical runs #2016, #2022 and #2024–#2029 remain recorded as **cancelled**, not code failures. Cleanup runs #937 and later are maintenance entries, not application builds.

## Target-PC acceptance still required

Automated tests and synthetic M4B checks do not establish perceived speech/music quality or installed-app interaction. Record these after installing the matching checkpoint:

1. Run Analyze Book on a real imported book; inspect actual chapter summaries, themes, character arcs, relationships, evidence quotes and pronunciation candidates. Close and reopen the report and confirm saved data reloads.
2. Save, edit, clear, relink and reopen real BGM/cue assignments. Confirm the 18% fresh-project master default on an actual fresh project.
3. Listen to real pronunciation previews and production speech with global pronunciation ON/OFF, individual entries enabled/disabled, selected saved profiles and Book/Series/Global conflict cases.
4. Listen to Same BGM, Chapter-Based BGM and Voice Only; confirm no book-default fallback and no BGM/cues in Voice Only.
5. Listen to Opening, each Next Chapter boundary and Closing cues; assess narration/music/cue balance, volume zero/bounds, fades and offsets.
6. Compare the full-book preview with final-generation output from the same saved configuration.
7. Exercise cancellation/retry and restart/reopen after actual saved-setting changes.

Cross-stage PROD-15 chapter-specific preview/download remains outside Step 2 and must be carried into its planned later substep; it is not claimed complete by this closeout.

## Next gate

This record is committed with an artifact-checkpoint marker. The resulting Windows workflow must pass its full test job, frozen-app verification, packaged Sound Design/Music Library acceptance, installer build, manifest/hash generation, malware scan and installer/portable upload on the exact checkpoint SHA. Record its final run URL, SHA and artifact IDs before declaring the Step 2 package checkpoint complete.
