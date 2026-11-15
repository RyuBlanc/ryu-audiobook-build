# Stage E — Character Intelligence, Cast Routing and Production UX Hardening

**Stage:** E — remaining software/product engineering before final physical acceptance  
**Repository:** `RyuBlanc/ryu-audiobook-build`  
**Implementation branch:** `dragon-studio/stage-e-character-intelligence-cast-production-ux-2026-11-15`  
**Base source head:** `6d970bf70911848c90bcb178b1a166a10bf8305d`  
**Previous stage:** Stage D engineering closeout — D0–D5 accepted; D6 deferred to Stage F  
**Baseline regression:** Build #3460 / [run 43700894123](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43700894123), **1,681/1,681** tests passed. The documentation-only build job was skipped as expected.  
**Status:** ACTIVE — source audit and test-first work begin from the preserved Stage D head.

## 1. Purpose

Close the remaining non-physical character-analysis, voice-cast consistency, Production presentation and Help & Guide engineering requirements before final physical acceptance.

The repository roadmap is A → B → C → D → E → F. Stage D's hosted profile-library engineering is accepted. The real two-PC D6 check, target-hardware measurements and all other physical/manual acceptance are intentionally deferred to Stage F; Stage E must not manufacture simulated physical passes.

## 2. Stage D boundary

- D0–D3: versioned Qwen profile data, portable export, transactional import/recovery, compatibility/collision handling accepted on their recorded hosted checkpoints.
- D4: Voice Library taxonomy, filtering, saved identity/detail inspection and native actions included in the exact-head package.
- D5: exact-head packaged CustomVoice + VoiceDesign + Clone export/preflight/import, two byte-verified audio assets, stable IDs and fresh-process reload; final import-path confinement passed.
- Exact D5 package source: `fbed26a0beadd5ebe845173f8e2e059668248d8c`; Build #3457 and repeat exact-SHA package Build #3458 passed. Cumulative regression: **1,681/1,681**.
- Documentation revalidation: #3459 and #3460 each passed the full **1,681/1,681** suite; their Windows build jobs were skipped because they were documentation-only commits.
- D6 has **not** passed. It remains a physical PC-A → PC-B transfer and audition worksheet and is deferred to Stage F.

Do not reopen accepted D1–D5 behavior without a demonstrated regression. Preserve failed-run history and exact artifacts.

## 3. Included requirements

### E1 — Multilingual, source-grounded Character Studio analysis (DS-AI-012)

- Support Japanese, Chinese, Korean, accented Latin names and Indian-language scripts, including Unicode combining marks in Devanagari, Tamil, Telugu, Bengali and other scripts present in real source text.
- Detect explicit speaker labels, dialogue tags, aliases and quote forms without truncating or corrupting source spelling.
- Keep candidate/alias identity Unicode-normalized; do not merge distinct characters or discard a user-confirmed alias such as `Captain Mira`.
- Common English prose/interjections such as `the`, `any`, `oh`, `hmm` and `actually` must not become cast identities solely because AI suggests them.
- AI output must be grounded in the exact chapter and quote. If local AI returns no usable characters, retain deterministic/source-grounded fallback rather than reporting a false empty success.
- Coverage must span all chapters and the complete candidate/passage set. No hidden 120-passage or similar cap may make later text disappear; processed/total chapters and incomplete coverage must be explicit.

**Initial source finding:** `app/chapters/characters.py` builds `SPEAKER_NAME_TOKEN` using Python `re`'s `\w`. Python `\w` excludes Unicode combining marks (Mn/Mc/Me). Existing multilingual fixtures cover Japanese, Chinese, Korean and accented Latin, but not Indian-script labels with vowel marks. A direct reproduction of the current token pattern failed on common Hindi/Tamil/Telugu/Bengali names such as `मीरा`, `கவிதா`, `లక్ష్మి` and `রিয়া`. E1 must add an end-to-end failing test first, then apply the narrowest robust correction without broad false-positive capture.

### E2 — Narrator and series-scoped cast consistency (DS-CAST-008)

- Preserve explicit per-book Narrator-only choice and its default-off behavior when normal cast selection is available.
- Preserve accepted zero-valid-character-profile behavior: automatically use the saved narrator when no valid character voice profiles exist and a valid narrator is saved; respect an explicit saved user opt-out.
- With cast-aware generation active, route the series-scoped character profile to the matching dialogue; never collapse same-named characters from different series into the first match.
- Unresolved dialogue must use the configured Unassigned Character fallback or remain blocked/review-required under the current readiness rules; never silently use the wrong voice.
- Readiness, Voice Studio preview/assignment, Production preview and final generation must agree on narrator/cast identity and generation signature.
- Preserve saved dialogue assignments and confirmed aliases during re-analysis, chapter split/merge, save/reload and retry.

### E3 — Production presentation and cover-art separation (DS-UI-009)

- Keep Production cards, configuration, progress and primary actions readable and consistently grouped without removing working controls.
- Selected/project cover artwork remains the artwork itself. The Ryu watermark is permitted only on an empty-cover placeholder, never over a real selected cover.
- Keep cover art, app logo and Windows shell branding as separate assets and roles.
- Preserve the current placeholder-vs-real-cover regression; inspect broader layout defects before changing already-correct code. Stage E uses source and viewport emulation; physical no-flicker, mixed-DPI and multi-monitor inspection belongs to Stage F.

**Existing guard:** `tests/test_cover_art_presentation.py` asserts placeholder-only watermark CSS and frontend project-cover state toggling. Do not duplicate or weaken it.

### E4 — Help & Guide accuracy (DS-HELP-014)

- Update task-based instructions after E1–E3 behavior is accepted.
- Preserve the detailed seven-stage guide and existing help topics; reconcile narrator-only, character review, cancellation/recovery, profile/model compatibility and Production behavior with the actual accepted application.
- Do not advertise physical hardware, two-PC transfer, unsupported backend or release capability as complete before Stage F evidence.
- Retain source-contract tests for the live guide and preserved guide sections.

## 4. Stage F carry-forward and exclusions

Stage E is software engineering, automated/hosted validation and exact-head packaging. It does not close:

- D6 physical two-PC profile transfer and CustomVoice/VoiceDesign/Clone audition.
- Actual NVIDIA CUDA, AMD ROCm, Intel XPU or target-device Qwen timing claims, including the 30-second preview under-60-second goal.
- Real target-PC long multi-chapter/full-novel generation, playback, elapsed/progress/ETA/duration comparison and interruption/recovery.
- Installed-PC model install/repair/remove and saved-profile audition/restart.
- Physical 1280×720, 41-viewport, ultrawide/portrait, mixed-monitor/DPI and flicker/freeze inspection.
- Physical Windows shortcut/taskbar transparency, actual installer wizard geometry and final user Help & Guide inspection.

These items remain open in the verification queue and must be collected in Stage F. Hosted simulations, unit tests, same-machine process restarts and CI runner devices cannot substitute for the named physical acceptance.

## 5. Existing tests and implementation to preserve

- `tests/test_character_detection_regression.py`: explicit labels, dialogue tags, Japanese/Chinese/Korean and accented Latin identity.
- `tests/test_character_identity_unicode.py`: Unicode-normalized series/character identity keys.
- `tests/test_character_name_quality.py`: reject false English words/aliases while preserving explicit evidence such as `Captain Mira`.
- `tests/test_character_ai_analysis_contract.py`: book-wide local AI pipeline, source-grounded fallback, processed/total coverage and no silent suggestion cap.
- `tests/test_narrator_only_generation.py` and `tests/test_legacy_voice_cast_generation_routing.py`: narrator-only semantics, unassigned fallback, scoped-map parity and same-name multi-series routing.
- `tests/test_cover_art_presentation.py`: selected-cover and empty-placeholder watermark separation.
- `tests/test_help_guide_current_requirements.py`: current Help & Guide requirements and preserved guide.

This inventory is not an assertion that every requirement is complete. Add targeted tests for uncovered behaviors; do not weaken already-covered cases.

## 6. Implementation sequence

1. **E0 — Baseline/source audit:** preserve exact base SHA and map each requirement to implementation/test files.
2. **E1 — Unicode regression first:** add Indian-script speaker-label/dialogue-tag tests including combining marks; run a focused check, then correct parsing while retaining Japanese/CJK/accented Latin coverage.
3. **E1 follow-up — Full-book analysis:** verify no passage/chapter truncation, deterministic fallback on empty AI results, exact chapter/quote grounding and cancellation that never commits partial cast state.
4. **E2 — Cast/narrator integration:** add only missing parity tests for series-scoped identities, per-book narrator-only choice, saved narrator identity, Unassigned fallback and preview/final routing.
5. **E3 — Production presentation:** inspect CSS/adapter state and packaged geometry contracts; fix only reproducible gaps and preserve all visible controls.
6. **E4 — Help & Guide:** reconcile and test user instructions after E1–E3 behavior is stable.
7. **E5 — Exact-head package:** focused E tests, full regression, frozen Windows app, integrated packaged UI/Production acceptance, installer, portable, install/launch/upgrade/uninstall, Defender and artifact hashes on one exact commit.

Every source change requires a focused regression and full-suite result. Test-only/documentation-only runs with a skipped build job are useful checks but are not artifact acceptance.

## 7. Stage E exit criteria

- Indian-script/combining-mark source labels and dialogue tags are preserved without introducing false cast records.
- AI and deterministic analysis cover all chapters/passages; fallback and safe cancellation semantics are verified.
- Narrator-only/cast-aware selection, series scoping, saved assignments and Unassigned fallback agree across readiness, preview and generation.
- Production cover-art/brand separation and any reproducible layout defects have passing tests and packaged acceptance.
- Help & Guide is accurate and preserved sections remain intact.
- Focused tests, full regression and exact-head Windows package gates pass on one source SHA.
- Failed attempts remain individually recorded with real causes and corrections.

## 8. Stage F handoff

Stage F is consolidated physical/manual acceptance and final release-readiness. It will execute D6 and every Stage C/Stage E physical carry-forward item on the user's real target systems after engineering stages A–E are complete. Stage F closes only with device/build/backend-specific evidence, real audio/listening results, UI/installer observations and exact-head artifact hashes. Version 1.2.0 publication/final sign-off remains separate and requires explicit owner approval after the acceptance ledger is complete.
