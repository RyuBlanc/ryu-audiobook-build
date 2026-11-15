# Stage E — Character Intelligence, Cast Routing and Production UX Hardening

**Stage:** E — remaining software/product engineering before final physical acceptance  
**Repository:** `RyuBlanc/ryu-audiobook-build`  
**Implementation branch:** `dragon-studio/stage-e-character-intelligence-cast-production-ux-2026-11-15`  
**Base source head:** `6d970bf70911848c90bcb178b1a166a10bf8305d`  
**Previous stage:** Stage D engineering closeout — D0–D5 accepted; D6 deferred to Stage F  
**Latest Stage E exact-head artifact checkpoint:** Build #3470 / [run 43714021829](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43714021829), exact source SHA fc3a0f8e1d64790b1a61024f8d883653b2dad51c: full regression **1,692/1,692**, E1–E4 focused gates passed, and both tests and Windows build jobs passed. The exact-head package includes the frozen app, D5 profile round-trip, production generation/recovery and installer/portable acceptance.
**Status:** COMPLETE — E0–E5 hosted engineering, full regression and exact-head Windows package accepted. All physical target-device checks remain explicitly deferred to Stage F.

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

### E1 — Multilingual, source-grounded Character Studio analysis (DS-AI-012) — SOURCE/TEST GATE PASSED

- Support Japanese, Chinese, Korean, accented Latin names and Indian-language scripts, including Unicode combining marks in Devanagari, Tamil, Telugu, Bengali and other scripts present in real source text.
- Detect explicit speaker labels, dialogue tags, aliases and quote forms without truncating or corrupting source spelling.
- Keep candidate/alias identity Unicode-normalized; do not merge distinct characters or discard a user-confirmed alias such as `Captain Mira`.
- Common English prose/interjections such as `the`, `any`, `oh`, `hmm` and `actually` must not become cast identities solely because AI suggests them.
- AI output must be grounded in the exact chapter and quote. If local AI returns no usable characters, retain deterministic/source-grounded fallback rather than reporting a false empty success.
- Coverage must span all chapters and the complete candidate/passage set. No hidden 120-passage or similar cap may make later text disappear; processed/total chapters and incomplete coverage must be explicit.

**Original E1 finding and correction:** At the Stage D base, SPEAKER_NAME_TOKEN relied on Python re's word class, which excludes Unicode combining-mark categories Mn/Mc/Me and missed real Indian-script speaker labels. Commit c105a6bf1998f824dfad9424b904e30c882dfa96 replaced the explicit speaker token/consumers with Unicode letter+mark property matching, added input-name validation, and added end-to-end Hindi, Tamil, Telugu, Bengali, Gujarati and Punjabi fixtures. E1 focused and full regression gates now pass; existing CJK, accented-Latin, false-positive and confirmed-alias protections remain in the passing suite.

### E2 — Narrator and series-scoped cast consistency (DS-CAST-008) — SOURCE/TEST GATE PASSED

- Preserve explicit per-book Narrator-only choice and its default-off behavior when normal cast selection is available.
- Preserve accepted zero-valid-character-profile behavior: automatically use the saved narrator when no valid character voice profiles exist and a valid narrator is saved; respect an explicit saved user opt-out.
- With cast-aware generation active, route the series-scoped character profile to the matching dialogue; never collapse same-named characters from different series into the first match.
- Unresolved dialogue must use the configured Unassigned Character fallback or remain blocked/review-required under the current readiness rules; never silently use the wrong voice.
- Readiness, Voice Studio preview/assignment, Production preview and final generation must agree on narrator/cast identity and generation signature.
- Preserve saved dialogue assignments and confirmed aliases during re-analysis, chapter split/merge, save/reload and retry.

### E3 — Production presentation and cover-art separation (DS-UI-009) — SOURCE/TEST GATE PASSED

- Keep Production cards, configuration, progress and primary actions readable and consistently grouped without removing working controls.
- Selected/project cover artwork remains the artwork itself. The Ryu watermark is permitted only on an empty-cover placeholder, never over a real selected cover.
- Keep cover art, app logo and Windows shell branding as separate assets and roles.
- Preserve the current placeholder-vs-real-cover regression; inspect broader layout defects before changing already-correct code. Stage E uses source and viewport emulation; physical no-flicker, mixed-DPI and multi-monitor inspection belongs to Stage F.

**Existing guard:** `tests/test_cover_art_presentation.py` asserts placeholder-only watermark CSS and frontend project-cover state toggling. Do not duplicate or weaken it.

### E4 — Help & Guide accuracy (DS-HELP-014) — SOURCE/TEST GATE PASSED

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

1. **E0 — Baseline/source audit: COMPLETE.** Preserved Stage D base SHA and mapped E1–E4 requirements to source and tests.
2. **E1 — Unicode and multilingual source labels: SOURCE/TEST GATE PASSED.** Indian-script speaker-label and after-quote tests pass with existing CJK/accented-Latin and false-positive safeguards.
3. **E1 follow-up — Full-book analysis: SOURCE/TEST GATE PASSED.** 150 dialogue passages across three chapters, source-grounded fallback, full segment traversal and cancellation-before-commit contracts pass.
4. **E2 — Cast/narrator integration: SOURCE/TEST GATE PASSED.** Preview now uses the same strict series-scoped cast resolution, exact chapter assignments, narrator identity and global Unassigned Character fallback as production generation.
5. **E3 — Production presentation: SOURCE/TEST GATE PASSED.** 41 focused layout/progress/cover-art tests pass; real-cover/placeholder watermark separation remains covered. No additional source defect was accepted without a reproducible regression.
6. **E4 — Help & Guide: SOURCE/TEST GATE PASSED.** Eight focused help tests pass, preserving the detailed seven-stage guide and documenting current limitations.
7. **E5 — Exact-head package: COMPLETE.** Build #3470 passed the 1,692-test full regression and exact-head frozen Windows package on fc3a0f8; installer, portable, SHA-256 manifest, Defender and packaged acceptance evidence were uploaded.

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


## 9. E1–E4 source/test verification ledger — 15 November 2026

**Accepted source/test head:** a99786938d98004ceb1df91d603d31d05babd858 on the active Stage E branch.

### Latest successful gates

- **Build #3463** / [run 43706538292](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43706538292), source SHA c105a6bf1998f824dfad9424b904e30c882dfa96: E1 Unicode implementation and focused character regressions passed; full regression 1,684/1,684.
- **Build #3464** / [run 43707567532](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43707567532), test SHA 67eb042f0456b9eba2ce10006907ee684723ad89: E1 focused 40/40, full-book 150-passage/fallback/cancel contracts and full regression 1,688/1,688 passed.
- **Build #3468** / [run 43710004680](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43710004680), test SHA 8509bca54a041b81dfd19d7c99f51d8312f70208: E2 preview/cast focused suite 181/181 and full regression 1,692/1,692 passed after correcting the source-contract test literals.
- **Build #3469** / [run 43710739978](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43710739978), exact tested head a99786938d98004ceb1df91d603d31d05babd858: E1 40/40, E2 181/181, E3 41/41, E4 8/8, full regression 1,692/1,692. The tests job passed; the build job was skipped because the head was not an explicit artifact checkpoint.

### Failed attempts preserved

- **Build #3465** / [run 43709432289](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43709432289), commit 3f8523fc2fffe79ac13ff62e0de4ce9bfbf36133: the E2 preview-routing source change exposed stale lightweight test fixtures without the new routing snapshot method and an integration contract that still expected the removed inline name-only map. The full regression failed; it remains a failure.
- **Build #3466** / [run 43709542835](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43709542835), commit f3b1035f9e94808afa61324fc0f86f9790624b29: the Unassigned-only preview-router correction was added, but the same legacy fixture/contract failures remained in the full regression. It remains a failure.
- **Build #3467** / [run 43709935729](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43709935729), commit be4cc2f65326ed4f67974e71f167cf2be29ed497: the new E2 focused gate could not import the integration-contract test because escaped quotes produced a Python SyntaxError at line 316. It remains a failure.
- **Build #3468** corrected those contract-test string literals; #3469 then independently passed E1–E4 and the full regression. The failed attempts above are not relabelled or removed.

### E5 package gate — COMPLETE

Build Windows App **#3470** / [run 43714021829](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43714021829) passed on the exact Stage E head fc3a0f8e1d64790b1a61024f8d883653b2dad51c. The tests and build jobs both completed successfully. The test job ran the Stage B, Stage 6, C1–C4, D3–D5 and E1–E4 gates before the full suite; the full suite reported **1,692 tests, OK**.

The Windows package job passed frozen-app verification, bundled voice assets/modules, real bundled-Piper multi-chapter M4B plus FFmpeg chapter-marker decode, packaged Sound Design/Production acceptance, the D5 three-profile bundle round-trip and fresh-process reload, real narrator-only full-book generation, retry/restart recovery, chaptered M4B playback/seek, installer build/startup, install/launch/upgrade/uninstall, logo/hash checks, package size reporting, Microsoft Defender scans and required artifact uploads. Defender reported no threats for the application, HTML installer and core installer. Only Publish verified installer release was skipped by the candidate workflow; no public release was published.

Artifacts from #3470: installer 14162537175 (847,380,138 bytes), portable 14163025967 (1,191,837,669 bytes), SHA-256 manifest 14162528273 (3,049 bytes), real multi-chapter M4B evidence 14162070795 (9,033,841 bytes), and Stage 7 Piper benchmark 14162867421 (805 bytes). GitHub reported artifact expiry on **15 December 2026**. These sizes are GitHub artifact archives; the manifest contains the actual executable hashes.

The earlier E1–E4 source/test evidence and failed-attempt history remain preserved above. Builds #3465–#3467 remain failed; #3468 corrected the regression-test literals, #3469 passed E1–E4, and #3470 completed the exact-head artifact checkpoint. Do not relabel the historical failures.

Stage F is now the active final physical/manual acceptance stage. D6 two-PC transfer/audition, real target-device Qwen/GPU measurements, representative full-book listening/recovery, physical responsive/flicker/freeze inspection, and installed shell-icon/installer visual checks remain NOT RUN until performed on the user's actual systems.

