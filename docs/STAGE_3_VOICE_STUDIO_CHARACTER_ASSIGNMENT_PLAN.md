# Stage 3 Plan — Voice Studio and Character Assignment

**Working branch:** `fix/native-ui-font-scale-learning-ai`  
**Automated baseline before checkpoint:** full regression run #1485 passed 766/766 on `ae3fd8b9eed9244c97132591ff9a8a45ee11e5f2`; this checkpoint commit adds a direct subdued-cue regression and must pass its own test gate before packaging.  
**UI rule:** preserve the approved Premium V2 HTML and existing control layout. Improve real backend behavior, validation, persistence, and tests; do not replace connected behavior with demo data.

## Objectives

### 3.1 Voice Studio profile lifecycle
- [x] Regression contract covers supported-provider validation, unique-name collision, required voice ID/reference audio, and explicit permission for cloning; Run #894 passed.
- [x] Regression test covers saved custom-profile persistence and catalogue reload with Unicode names and paths; Run #894 passed.
- [x] Regression contracts cover deletion refusal for built-in profiles and profiles still assigned as narrator/character; Run #894 passed. Packaged-app interaction still requires target-PC acceptance.
- [ ] Target-PC acceptance: confirm selected preview actually uses the selected saved profile/provider and reports provider failures clearly.
- [ ] Target-PC acceptance: verify custom/reference voices and built-in voices remain distinguishable and reload after application restart.

### 3.2 Character analysis and cast persistence
- [x] Regression coverage includes dialogue attribution, manual-assignment names, first-person narrator self-identification, and common-word false-positive guards; current test-only run #1485 passed 766/766 before the final checkpoint commit.
- [x] Re-analysis preserves voice-profile assignment and edited cast metadata for case-insensitive exact-name matches; regression test passed in Run #894.
- [x] Behavioral tests cover case-insensitive rename, alias normalization, duplicate names, deletion guards for legacy/multi-speaker assignments, and preservation of omitted metadata; the full suite passed on #1485.
- [x] Persistence-level test reloads saved project state after character analysis and verifies confidence/examples, voice profile, user notes, aliases, dialogue totals and unassigned counts; passed on #1480/#1483/#1485.

### 3.3 Dialogue assignment and generation routing
- [x] Regression tests for legacy/multi-speaker assignment shapes, ambiguous quote rejection, exact/stale-span unassignment and multi-speaker candidate detection passed in Run #894.
- [x] Backend bridge tests verify chapter reorder, merge and split assignment offsets against actual chapter text; an assignment crossing a split boundary is safely dropped. Tests passed on #1484 (765/765) and the later full suite #1485.
- [x] Regression test confirms assigned dialogue routes to cast profiles while surrounding narration uses the narrator; Run #894 passed.
- [x] Missing assigned cast profile now fails with actionable guidance rather than silently using the narrator; regression test passed in Run #894.
- [ ] Target-PC acceptance: verify UI displays saved assignment state and preview/generation failures accurately.

### 3.4 Verification and release gates
- [x] Historical baseline Run #894 passed the full unittest suite and Windows build/package workflow on commit `ec20d76106e01971e16c045a475eb72f78115c83`.
- [x] Test-only Run #1485 passed 766/766 cases on `ae3fd8b9eed9244c97132591ff9a8a45ee11e5f2`; the checkpoint commit adds the isolated `subdued` emotion cue test and records current evidence.
- [ ] This commit requests the Stage 3 artifact checkpoint. Record its exact test/build result and artifact hashes after the run completes.
- [x] Run #894 passed the Windows build/package workflow, frozen-app verification, bundled assets/modules checks, installer build, SHA-256 manifest and Microsoft Defender scan. Release publication was skipped by workflow policy.
- [ ] Target-PC acceptance: exercise Voice Studio and Character Studio in the packaged Windows app, including actual audio preview and generation.
- [ ] Keep hardware-specific Stage 1 validation and Stage 2 import acceptance explicitly open until tested on the target PC.

## Current audit observations

- Backend commands already exist for voice list/save/delete/reference import/select/preview, character analysis/assign/update/delete, and dialogue assign/unassign.
- Character analysis runs as a background job and saves candidate records into project state.
- Re-analysis currently carries forward the previous `voice_profile` and `chapter_appearances` by case-insensitive exact character name. User-edited metadata and renamed-character matching need explicit verification.
- Chapter-level dialogue assignments are persisted in project JSON and support legacy single-speaker plus newer multi-speaker records.
- The Windows workflow must explicitly include this branch to produce fresh CI evidence.

## Current work after Stage 2

Stage 2 PR #17 was merged after Run #877 succeeded. The Stage 2 packaged-Windows acceptance items remain release gates: duplicate import guidance, cancellation/retry, real supported-format imports, and edit/reopen comparison on the target PC. Stage 1 hardware-specific freeze/crash acceptance also remains open.

Stage 3 automated verification was extended on `fix/native-ui-font-scale-learning-ai`: case-insensitive first-person narrator recognition; case-insensitive character rename/alias normalization; duplicate-name protection; character deletion blocked while saved dialogue assignments reference its canonical name or aliases; analysis output/state-reload coverage; bridge-level chapter reorder/merge/split assignment integrity; and truthful preview performance telemetry. Emotion classification now explicitly covers happy/cheerful, laughing, sad/subdued, crying/sobbing, angry, fearful/tense, surprised, bored, calm and serious delivery while keeping the bored style in the existing neutral reference family so it does not require a separate voice identity. Runs #1480, #1483 and #1484 passed at 758/758, 762/762 and 765/765; Run #1485 passed 766/766 on `ae3fd8b9eed9244c97132591ff9a8a45ee11e5f2`. The package-triggering commit includes a final direct `subdued` cue test and must pass its own test job before Windows packaging proceeds.

**Runtime boundary:** per your instruction, hands-on Windows, model-dependent latency measurement, and listening-based voice identity/emotion acceptance are deferred until all stages are complete. They remain open release gates, not claimed as passed.

**Stage map alignment note:** the supplied master continuation prompt maps overall Stage 2 to Sound Design/Music Library and places Import/Chapter work in Stage 6. The #1478 checkpoint validated the Import/Chapter automated batch; it does not close the master register's Sound Design/Music Library requirements. Those remain open unless separately verified.

## Completion rule

Do not mark Stage 3 complete from a green build alone. Require regression tests, verified package output, and a clearly documented target-Windows acceptance result. Do not claim voice quality is correct without listening to the generated preview/audio.
