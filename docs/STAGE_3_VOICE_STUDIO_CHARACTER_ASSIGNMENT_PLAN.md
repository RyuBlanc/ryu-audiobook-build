# Stage 3 Plan — Voice Studio and Character Assignment

**Working branch:** `stage-3/voice-studio-character-assignment`  
**Baseline:** Stage 2 merge commit `9aa1ba5cc9be0808d596c1e2c0618584433c9917`  
**UI rule:** preserve the approved Premium V2 HTML and existing control layout. Improve real backend behavior, validation, persistence, and tests; do not replace connected behavior with demo data.

## Objectives

### 3.1 Voice Studio profile lifecycle
- [x] Regression contract covers supported-provider validation, unique-name collision, required voice ID/reference audio, and explicit permission for cloning; Run #894 passed.
- [x] Regression test covers saved custom-profile persistence and catalogue reload with Unicode names and paths; Run #894 passed.
- [x] Regression contracts cover deletion refusal for built-in profiles and profiles still assigned as narrator/character; Run #894 passed. Packaged-app interaction still requires target-PC acceptance.
- [ ] Target-PC acceptance: confirm selected preview actually uses the selected saved profile/provider and reports provider failures clearly.
- [ ] Target-PC acceptance: verify custom/reference voices and built-in voices remain distinguishable and reload after application restart.

### 3.2 Character analysis and cast persistence
- [x] Regression coverage includes dialogue attribution, manual-assignment names, first-person self-identification, short-name aliases, and attributed-dialogue fixtures. Run #1492 passed 426 tests.
- [x] Re-analysis preserves voice-profile assignment and edited cast metadata for case-insensitive exact-name matches; regression test passed in Run #894.
- [x] Regression contract covers rename preserving the old canonical name as an alias and partial updates preserving omitted metadata; behavioral tests now cover case-insensitive updates, alias edits, duplicate-name rejection, delete semantics and assignment-reference cleanup. Run #1492 passed 426 tests.
- [x] Persistence-level tests verify analysis output, confidence/examples, dialogue totals, unassigned-dialogue count and user-authored metadata across save/reopen. Run #1493 passed 427 tests.

### 3.3 Dialogue assignment and generation routing
- [x] Regression tests for legacy/multi-speaker assignment shapes, ambiguous quote rejection, exact/stale-span unassignment and multi-speaker candidate detection passed in Run #894.
- [x] Tests cover assignment integrity through chapter reorder/merge/split, offset migration for valid spans, and safe invalidation for boundary-crossing or changed-source spans. Run #1492 passed 426 tests.
- [x] Regression test confirms assigned dialogue routes to cast profiles while surrounding narration uses the narrator; Run #894 passed.
- [x] Missing assigned cast profile now fails with actionable guidance rather than silently using the narrator; regression test passed in Run #894.
- [ ] Target-PC acceptance: verify UI displays saved assignment state and preview/generation failures accurately.

### 3.4 Verification and release gates
- [x] Run #894 passed the full unittest suite and Windows build/package workflow on commit `ec20d76106e01971e16c045a475eb72f78115c83`.
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

Stage 3 automated coverage and package gates passed the earlier Run #894 baseline and were extended in Runs #1491–#1495. The completed automated work now covers character metadata/alias lifecycle, analysis persistence, assignment offset integrity through chapter edits, cast-to-narrator routing, missing-profile fail-closed behavior, preview selection/duration contracts, and a newly discovered late-preview callback race. The newest test-only run is #1495 (431 tests passed); its dedicated artifact checkpoint follows this update.

Stage 3 is **automated-gate complete after the pending checkpoint build**, but is not fully accepted until the packaged Windows UI/audio checks listed above are completed on the target PC. Stage 1 hardware and Stage 2 import acceptance also remain open.

## Completion rule

Do not mark Stage 3 complete from a green build alone. Require regression tests, verified package output, and a clearly documented target-Windows acceptance result. Do not claim voice quality is correct without listening to the generated preview/audio.


## Stage 3 automated closure summary — 2026-10-28

The following automated closure items are complete and covered by the passing test-only runs:
- [x] Case-insensitive character updates, duplicate-name rejection, deletion semantics, and assignment-reference cleanup.
- [x] Character-analysis evidence and user-authored metadata surviving persisted save/reload, including unassigned-dialogue counts.
- [x] Assignment offsets staying attached to the correct chapter through reorder/merge/split, with safe invalidation of stale or boundary-crossing source spans.
- [x] First-person self-identification, short-name aliases, and attributed-dialogue fixtures.
- [x] Ordinary commits running the full unittest suite only; package/security/artifact gates require an explicit `[artifact-checkpoint]` commit.
- [x] Voice Studio stale-preview race fix: every preview callback is bound to the worker generation and the profile signature that launched it; obsolete signals cannot reactivate stale audio or clear a newer worker. See the targeted Run #1495 tests below.

Do not close Stage 3 from CI alone. Packaged Windows interaction and actual audio preview/generation still require target-PC acceptance.


## Test-only CI result and correction — 2026-10-28

- Run #1491 on commit `82433cac383d6ad0fb3e773ba600329d5e44d78c` ran 424 tests and failed one new regression: a capitalized first-person introduction ("My name is ...") was not classified as the narrating character.
- The root cause is case-sensitive matching in `_detect_first_person_narrator`; the follow-up makes introductory phrase matching case-insensitive while retaining name plausibility validation.
- Add chapter reorder and merge offset-integrity tests alongside the split migration tests.
- Run #1491 did not package or upload artifacts. Continue test-only CI until the full suite passes; checkpoint packaging remains deferred.


## Stage 3 test-only Run #1492 — 2026-10-28

- Run #1492 passed **426 tests** on commit `5137f4e3a32d396716476bac0c2d4ce0410a5d51`: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40628970505.
- The run verified the first-person narrator detection correction and the new chapter reorder/merge/split assignment-offset tests.
- A further explicit persistence assertion for the unassigned-dialogue count is being added before the checkpoint run.
- Packaging, installer, Defender, artifact upload, cleanup, and release steps were all skipped because this was a test-only commit.


## Stage 3 test-only Run #1493 — 2026-10-28

- Run #1493 passed **427 tests** on commit `af626c4cceeecf7da3bc749ce07a62d1d0185eaa`: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40629252242.
- This includes the explicit save/reload assertion for unassigned dialogue counts. The test-only run skipped frozen-app packaging, security scans, artifact upload, cleanup, and release steps as intended.
- The follow-up checkpoint Run #1494 reran the suite and passed the Windows frozen-app, bundled-assets/modules, installer, SHA-256, Defender and artifact-upload gates; release publication remained skipped by workflow policy.
- A subsequent review found a separate stale-preview callback race in Voice Studio. It was fixed in commit `74e312be9769b00c773e918a2575921309ebcd1e` and verified by test-only Run #1495 before the next artifact checkpoint.
- Stage 3 is not fully accepted until packaged Windows UI/audio checks are completed; Stage 1 hardware and Stage 2 import acceptance also remain open.


## Voice Studio stale-preview race fix — test-only Run #1495 — 2026-10-28

- Commit `74e312be9769b00c773e918a2575921309ebcd1e` binds each preview worker to a generation token and the selected profile signature that launched it.
- Invalidated/obsolete worker success, status, progress, failure and cancellation callbacks are ignored. A late finish from an older worker cannot clear a newer worker. Retry controls are not re-enabled until the current worker has actually finished, avoiding overlapping work against the shared preview output file.
- Added `tests/test_stage3_voice_preview_race.py`: verifies stale success cannot resurrect audio, stale status cannot overwrite current UI state, old worker completion cannot clear a newer worker, and only the current generation may update UI state.
- Run #1495 passed **431 tests in 24.661 seconds**: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40638532775. Packaging/security/artifact steps were skipped as intended for a fix commit.
- This commit is the follow-up `[artifact-checkpoint]`: it reruns the complete suite and, if green, executes frozen-app validation, asset/module checks, installer build, SHA-256 generation, Microsoft Defender scanning, and artifact uploads.
- Manual target-PC gates remain open: selected-profile audio actually plays through the chosen provider; saved profiles and assignments survive app restart/navigation; packaged Character Studio assignments are shown correctly; generation uses assigned character voices and narrator for surrounding narration; provider failures are actionable. Stage 1 hardware stability and Stage 2 import/edit/reopen acceptance remain separate open gates.


## Current-head verification and artifact checkpoint — 2026-10-28

### Latest source and test evidence before checkpoint

- Current branch: `stage-3/voice-studio-character-assignment`.
- Source commit tested: `565744d2cd05b2361d7718f15300999ac0fa1c2d`.
- Test-only run #1497: **435 tests passed in 24.016 seconds**; result `OK`: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40640437723.
- Run #1497 validated the named chapter-heading change in `app/chapters/detector.py`, including `tests/test_stage2_chapter_fixtures.py`, and the saved/recreated Voice Cast UI state in `tests/test_stage3_voice_cast_ui_persistence.py`.
- Run #1497 completed successfully but deliberately skipped frozen-app packaging and artifact upload because it was a test-only commit.
- The preceding artifact checkpoint #1496 passed its suite and created installer, portable, and SHA-256 manifest artifacts on parent commit `3715657fce3bde0ede23856cfb3f94ed31a85cf9`. It does not contain the newer changes validated in #1497.

### Closure decision

- Previously completed Stage 3 automated substages listed above remain closed; do not reopen them absent a regression or a dependency-driven change.
- The current-head 435-test result is accepted as automated evidence for the new source changes, but it is not a packaged-app checkpoint because #1497 produced no release artifacts.
- The next explicitly marked artifact-checkpoint commit must rerun the complete regression suite on the checkpoint tree and then run frozen-app checks, bundled asset/module checks, Inno Setup, SHA-256 manifest generation, Microsoft Defender scans and installer/portable uploads. Release publication must remain skipped.
- The checkpoint must be tied to the exact successful source commit and all generated artifacts must be verified against that run.
- Do not treat Stage 3 as fully accepted solely from CI. Packaged Windows runtime checks remain open for actual selected-profile audio, profile/assignment persistence across navigation and restart, Voice Cast behavior, selected character voice routing, and actionable provider errors. Physical target-PC testing is not performed by CI.
- Stage 1 target-PC hardware stability and Stage 2 target-PC import/edit/reopen checks remain separate open gates and must not be silently marked complete when Stage 3 moves forward.
- Stage 3 exit criteria: successful matching-head artifact checkpoint plus recorded target-PC acceptance or explicitly open acceptance items. No existing completed fix is to be repeated just to increase the build number.
