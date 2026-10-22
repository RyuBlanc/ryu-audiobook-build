# Stage 3 Plan — Voice Studio and Character Assignment

**Working branch:** `stage-3/voice-studio-character-assignment`  
**Baseline:** Stage 2 merge commit `9aa1ba5cc9be0808d596c1e2c0618584433c9917`  
**UI rule:** preserve the approved Premium V2 HTML and existing control layout. Improve real backend behavior, validation, persistence, and tests; do not replace connected behavior with demo data.

## Objectives

### 3.1 Voice Studio profile lifecycle
- [ ] Test profile validation, unique naming, provider compatibility, reference-audio requirements, and permission confirmation for voice cloning.
- [ ] Test atomic profile persistence and catalogue reload, including Unicode names and paths.
- [ ] Test update/delete behavior, including refusal to delete profiles still assigned to a book character.
- [ ] Verify selected voice preview uses the requested saved profile/provider and reports failures clearly.
- [ ] Verify custom/reference voices and built-in voices remain distinguishable and load after application restart.

### 3.2 Character analysis and cast persistence
- [ ] Test deterministic character detection with attributed dialogue, aliases, first-person narration, and unassigned dialogue.
- [ ] Re-analysis must preserve manual voice-profile assignments and user-edited metadata for characters that remain matched.
- [ ] Test case-insensitive matching, alias edits, duplicate names, rename and delete semantics.
- [ ] Verify analysis output, confidence/examples, dialogue totals, and unassigned counts are saved and reloaded accurately.

### 3.3 Dialogue assignment and generation routing
- [ ] Test single-speaker and multi-speaker assignment, compatibility with legacy `speaker` records, and safe unassignment by exact source span.
- [ ] Test assignments survive chapter reorder/merge/split where offsets are expected to change.
- [ ] Test cast-aware provider routing sends attributed quotes to the saved character voice and narration to the narrator voice.
- [ ] Missing or deleted voice profiles must fail with actionable guidance, not silently fall back to the wrong character voice.
- [ ] Verify the UI receives backend truth for assignment status and preview/generation errors.

### 3.4 Verification and release gates
- [ ] Run targeted character/voice tests and the full unittest suite.
- [ ] Run Windows build/package/installer workflow on this branch and inspect every failed step.
- [ ] Verify Voice Studio and Character Studio workflows in the packaged Windows app.
- [ ] Keep hardware-specific Stage 1 validation and Stage 2 import acceptance explicitly open until tested on the target PC.

## Current audit observations

- Backend commands already exist for voice list/save/delete/reference import/select/preview, character analysis/assign/update/delete, and dialogue assign/unassign.
- Character analysis runs as a background job and saves candidate records into project state.
- Re-analysis currently carries forward the previous `voice_profile` and `chapter_appearances` by case-insensitive exact character name. User-edited metadata and renamed-character matching need explicit verification.
- Chapter-level dialogue assignments are persisted in project JSON and support legacy single-speaker plus newer multi-speaker records.
- The Windows workflow must explicitly include this branch to produce fresh CI evidence.

## Completion rule

Do not mark Stage 3 complete from a green build alone. Require regression tests, verified package output, and a clearly documented target-Windows acceptance result. Do not claim voice quality is correct without listening to the generated preview/audio.
