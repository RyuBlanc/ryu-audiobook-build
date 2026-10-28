# Stage 3 Plan — Voice Studio and Character Assignment

**Working branch:** `integration/stage3-feature-preservation`  
**Latest successful artifact checkpoint:** Build Windows App #1486 completed successfully on 28 October 2026 using tested commit `e02972e5c9451c4d25766186de5d7cf20b4a57d6`. The full regression suite passed 766/766 (0 failed, 0 errors, 0 skipped), including the standalone subdued-emotion cue regression.  
**UI rule:** preserve the approved Premium V2 HTML and existing control layout. Improve real backend behavior, validation, persistence, and tests; do not replace connected behavior with demo data.

## Objectives

### 3.1 Voice Studio profile lifecycle
- [x] Regression contract covers supported-provider validation, unique-name collision, required voice ID/reference audio, and explicit permission for cloning; Run #894 passed.
- [x] Regression test covers saved custom-profile persistence and catalogue reload with Unicode names and paths; Run #894 passed.
- [x] Regression contracts cover deletion refusal for built-in profiles and profiles still assigned as narrator/character; Run #894 passed. Packaged-app interaction still requires target-PC acceptance.
- [ ] Target-PC acceptance: confirm selected preview actually uses the selected saved profile/provider and reports provider failures clearly.
- [ ] Target-PC acceptance: verify custom/reference voices and built-in voices remain distinguishable and reload after application restart.

### 3.2 Character analysis and cast persistence
- [x] Regression coverage includes dialogue attribution, manual-assignment names, first-person narrator self-identification, and common-word false-positive guards; included in successful Run #1486 (766/766).
- [x] Re-analysis preserves voice-profile assignment and edited cast metadata for case-insensitive exact-name matches; regression test passed in Run #894.
- [x] Behavioral tests cover case-insensitive rename, alias normalization, duplicate names, deletion guards for legacy/multi-speaker assignments, and preservation of omitted metadata; included in successful Run #1486 (766/766).
- [x] Persistence-level test reloads saved project state after character analysis and verifies confidence/examples, voice profile, user notes, aliases, dialogue totals and unassigned counts; passed on #1480/#1483/#1485.

### 3.3 Dialogue assignment and generation routing
- [x] Regression tests for legacy/multi-speaker assignment shapes, ambiguous quote rejection, exact/stale-span unassignment and multi-speaker candidate detection passed in Run #894.
- [x] Backend bridge tests verify chapter reorder, merge and split assignment offsets against actual chapter text; an assignment crossing a split boundary is safely dropped. Tests passed on #1484 (765/765) and the later full suite #1485.
- [x] Regression test confirms assigned dialogue routes to cast profiles while surrounding narration uses the narrator; Run #894 passed.
- [x] Missing assigned cast profile now fails with actionable guidance rather than silently using the narrator; regression test passed in Run #894.
- [ ] Target-PC acceptance: verify UI displays saved assignment state and preview/generation failures accurately.

### 3.4 Verification and release gates
- [x] Historical baseline Run #894 passed the full unittest suite and Windows build/package workflow on commit `ec20d76106e01971e16c045a475eb72f78115c83`.
- [x] Test-only Run #1485 passed 766/766 cases on `ae3fd8b9eed9244c97132591ff9a8a45ee11e5f2`.
- [x] Artifact checkpoint Run #1486 passed 766/766 and completed the Windows package workflow on `e02972e5c9451c4d25766186de5d7cf20b4a57d6`. Frozen-app validation, bundled-asset/module checks, installer packaging, logo transparency/hash generation, Microsoft Defender scans, artifact uploads, and cleanup passed. Public release publishing was skipped by workflow policy.
- [x] Run #894 passed the Windows build/package workflow, frozen-app verification, bundled assets/modules checks, installer build, SHA-256 manifest and Microsoft Defender scan. Release publication was skipped by workflow policy.
- [ ] Target-PC acceptance: exercise Voice Studio and Character Studio in the packaged Windows app, including actual audio preview and generation.
- [ ] Keep hardware-specific Stage 1 validation and Stage 2 import acceptance explicitly open until tested on the target PC.

## Current audit observations

- Backend commands already exist for voice list/save/delete/reference import/select/preview, character analysis/assign/update/delete, and dialogue assign/unassign.
- Character analysis runs as a background job and saves candidate records into project state.
- Re-analysis currently carries forward the previous `voice_profile` and `chapter_appearances` by case-insensitive exact character name. User-edited metadata and renamed-character matching need explicit verification.
- Chapter-level dialogue assignments are persisted in project JSON and support legacy single-speaker plus newer multi-speaker records.
- The Windows workflow must explicitly include this branch to produce fresh CI evidence.

## Current work and checkpoint evidence

### Stage 3 — Voice Studio and voice quality

Automated coverage has been extended for:
- Case-insensitive first-person narrator recognition and common-word false-positive guards.
- Case-insensitive character rename, alias normalization, duplicate-name protection, and deletion blocked while saved dialogue assignments refer to the character or its aliases.
- Character-analysis persistence after state reload, including confidence/examples, saved voice profile, notes, aliases, dialogue totals and unassigned counts.
- Chapter reorder/merge/split assignment integrity, with text-span verification and safe removal of an assignment crossing a split boundary.
- Preview profile/provider/voice identity and truthful timing telemetry for the 30-second preview target.
- Explicit happy/cheerful, laughing, sad/subdued, crying/sobbing, angry, fearful/tense, surprised, bored, calm and serious delivery cues. The bored delivery style stays in the existing neutral reference family to avoid inventing a new voice identity.

Runs #1480, #1483, #1484 and #1485 passed at 758/758, 762/762, 765/765 and 766/766. The final Stage 3 checkpoint, Run #1486, passed 766/766 on commit `e02972e5c9451c4d25766186de5d7cf20b4a57d6` and completed the Windows build and artifact workflow successfully.

| Run #1486 artifact | Artifact ID | Archive size (bytes) | Artifact ZIP SHA-256 |
|---|---:|---:|---|
| `Ryu-Audiobook-Test-Evidence-1486` | `12787405456` | `48,931` | `22b875d02e7fb8d5a09ad3901589a5dfa6ec6707cb1521c594fb67e358d38993` |
| `Ryu-Audiobook-Installer-1486` | `12787702526` | `878,067,165` | `71cad91085d1fcff96f61a8a27144320eec2a332e82f838bedbb24f3983a25ad` |
| `Ryu-Audiobook-Portable-1486` | `12787004695` | `1,349,466,654` | `46496fccd59d139097449577c041b2a2898958a4150d6c3b055bebddff24c36a` |
| `Ryu-Audiobook-Release-SHA256-1486` | `12787567955` | `778` | `a479aafd5006fc3baf8addf747d619393662d457e38d455e0a2552c23ef1783a` |

Release executable hashes recorded by the successful build log:
- `Ryu's Audiobook Setup.exe`: `D2BEEFEA92CBC1247F3BDA1DA71BA9C1192C757E7AFEBCF99A8B9C9A59893ED9` (878,067,001 bytes).
- `Ryu's Audiobook Core Setup.exe`: `7F35C76936440F7A918EDE416630A975B2721157D8D01B8F392C560AF5A8ABB4`.
- `Ryu's Audiobook.exe`: `C447C84CE48461359A700E6CBB6E8A9827304AF1D0967A6027D6F9368756BC7E`.

The Microsoft Defender scan reported no threats for the portable executable, functional installer executable or core installer executable. The artifacts remain available until approximately 27 November 2026. The package sizes remain above the previously discussed 500 MB target; package-size optimization belongs to the later Models/Packaging stage and was not attempted in this checkpoint.

**Runtime boundary:** per the user's instruction, hands-on Windows UI checks, hardware-specific preview-latency measurements and listening-based voice identity/emotion acceptance are deferred until all stages are complete. They remain open release gates and are not claimed to have passed.

### Authoritative stage mapping and next work

The master continuation prompt defines overall Stage 2 as Sound Design and Music Library, and overall Stage 6 as Library/import/chapter work. The earlier #1478 evidence document labels the Import/Chapter batch “Stage 2”; that automated checkpoint must not be mistaken for completion of the master register's Sound Design stage.

The next focused work batch is the outstanding Sound Design consistency gate: global Voice Only/BGM Off must suppress both background music and configured Opening/Next Chapter/Closing cues across generation and previews; the fixed Scene Transition assignment must be removed from the UI/backend and must not be mixed as a legacy fixed cue. Contextual story effects remain a distinct capability. Run focused tests first and do not trigger another package until this coherent batch passes.

## Completion rule

Do not mark Stage 3 complete from a green build alone. Require regression tests, verified package output, and a clearly documented target-Windows acceptance result. Do not claim voice quality is correct without listening to the generated preview/audio.


## Full-feature candidate reconciliation — 2026-10-28

- The earlier Stage 3-only branch produced builds #1496–#1501, but is not the acceptable source for the next all-feature candidate: it is hundreds of commits behind the full-feature baseline and lacks newer modules such as reusable Character Library, recoverable project Trash, current Dashboard, Settings and functional HTML installer components.
- Active integration branch: `integration/stage3-feature-preservation`, starting from full-feature source commit `efaca414fe4db0e4f2596ea19e5a567b7e793215`. Preserve the existing Dashboard, Library/recovery, Character Library, Settings, Premium V2 adapter, Stage 4 pronunciation/sound-design code and all bundled assets.
- Code review confirmed that several Stage 3 fixes are already present in the newer implementation: case-insensitive first-person narrator detection; fail-closed routing when an assigned voice profile is missing; safe chapter assignment remapping on split; request-ID/profile-signature guards for stale preview callbacks; and compound slash-title/Part heading handling. Do not overwrite these richer implementations with older Stage 3 versions.
- The integration adds focused behavioral regression tests for partial character edits, safe deletion while assignments still reference a character, Voice Cast visibility/persistence, and stale preview request callbacks; it also expands chapter-heading edge-case tests. The existing full-feature Stage 3 voice/character suite and cross-stage assignment tests remain in place.
- The branded native dark installer and full-resolution logo pipeline are already present on this baseline. Compression changes to LZMA2/ultra/solid only; no feature, model, voice, BGM/cue or payload file is removed. Package-size goal must be judged from resulting artifacts, not assumed.
- CI explicitly tests this integration branch, uses branch-scoped non-cancelling concurrency, retains test evidence and release artifacts for 90 days, and has automatic pruning disabled. Ordinary commits run tests only; artifact packaging remains deferred until this test-only candidate passes.
- No artifact from the older Stage 3-only branch is accepted as the all-feature candidate. Product version remains 1.1.1 until frozen requirements have passed final acceptance; do not publish Version 1.2.0 early.
- Packaged Windows runtime/audio acceptance remains open. CI cannot prove the wizard appearance on the user's PC or that selected voice identity, generated audio, playback and settings persistence are accepted.


## Integration test-only Run #1503 — failure analysis and correction — 2026-10-28

- Run #1503 tested full-feature integration commit `d46baa3c402956b59f10f0f24b222ff5701e798d`: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40652903861.
- The suite ran 782 tests and reported 1 failure / 2 errors. The test evidence artifact `Ryu-Audiobook-Test-Evidence-1503` (artifact ID `12799828407`) was uploaded successfully and must be retained.
- The Roman Part-heading fixture was incorrectly encoded with literal backslash-n characters; fix the test input to contain actual line breaks. This is a test-fixture correction, not a parser regression.
- The Voice Cast UI test did not supply the current `get_project` callback, so the widget correctly had no active project and no rows. Update the test to pass that callback and then verify visible assignment persistence across widget recreation.
- An existing regression test still expected the previous destructive cleanup script. Replace it with a contract asserting that both cleanup workflows and the underlying script are non-destructive. This aligns testing with the explicit evidence-retention rule.
- No installer artifact was produced by Run #1503. Correct these issues and run the complete test suite again on a new fix commit. The package/checkpoint gate remains closed until all tests pass.
