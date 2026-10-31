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


## Acceptance regression found in packaged Build #1498 — 2026-10-28

- The user-installed screenshot showed black body text on a dark destination page and the default Inno Setup wizard image instead of the Ryu logo. The artifact title was 1.1.1.1498; the product version remains intentionally 1.1.1 until the complete frozen release is accepted.
- Root cause verified against the built source: this Stage 3 branch still used WizardStyle=modern plus a label-only InitializeWizard color override, and did not set WizardSmallImageFile or a branded wizard panel. Ordinary wizard labels therefore remained dark on the dark surface and the standard Inno image remained visible. The installer-branding branch had a newer implementation, but it was not an ancestor of the Stage 3 checkpoint commit.
- Adaptive fix is limited to installer presentation/packaging and evidence retention. It keeps the native installer, application files, voice models, BGM/cue catalogue, install paths, user-data preservation, and launch/shortcut behavior. It uses native dark-mode styling, generated transparent brand images, and stronger lossless installer compression; it does not remove features or reduce audio quality.
- CI cleanup is being disabled for the Windows build workflow, and the scheduled storage cleaner is being changed to preserve every Windows build/test/checkpoint run as evidence. Artifact retention is extended to 90 days.
- Focused validation is the updated tests/test_stage6_installer_branding.py; the full regression suite and a matching artifact checkpoint are required before this package can be accepted.
- This is an acceptance-triggered cross-stage correction; it does not reopen already-passing Voice Studio/character-analysis fixes. Stage 3 still requires packaged Windows/audio acceptance, and Stage 4 must not begin until the current Stage 3 checkpoint is verified.


## Installer acceptance correction follow-up — 2026-10-28

- Root cause confirmed from installed Build #1498: it was built from the Stage 3 branch while the newer installer-branding change lived on a different stacked feature branch. The old installer script used a label-only color override and default Inno Setup illustration.
- Installer uses native dark wizard mode, an explicit small logo and a branded portrait panel. Wizard assets are Windows BMPs, composited only for the installer onto the matching dark background. The application PNG/ICO retain transparency and native source resolution.
- Compression is set to LZMA2 ultra/solid. No voice models, audio tracks, UI modules, source code, or other features are removed to reduce size. The actual size target can only be claimed after the generated artifact size is measured.
- Workflow concurrency is branch-scoped and no longer cancels an active build when a different branch's validation starts. The checkpoint workflow no longer deletes prior runs, the scheduled cleanup workflow is disabled until manual release review, and uploaded artifacts are retained for 90 days.
- The previous successful test-only run #1500 is evidence for the prior source SHA, not this correction. This correction needs its own focused tests, then a full checkpoint test and packaging run on one exact source SHA.
- A separate source-scope gate remains: the Stage 3 branch contains the recent Stage 3 fixes but not all later-stage feature branches. Do not describe a Stage 3-only artifact as a complete all-feature product until the requested feature scope is reconciled and verified.

## Stage 3 Step 3 — Assigned Cast and dialogue inspector implementation — 2026-10-31

### Scope closed by this step

This step implements and automatically verifies the Step 3 scope from the staged plan: **CS-01, CS-02, CS-05, CS-06 and CS-07**. It does not close the broader Stage 3/Voice Studio scope or claim target-PC runtime acceptance.

- **CS-01 — Assigned Cast:** the Premium V2 list is populated from the active project's saved character records and only includes characters with a saved character voice assignment. Each row shows character name, active project/story and the live count of assigned dialogue lines. Search covers canonical name, aliases and assigned voice.
- **CS-02 — Project isolation and saved state:** all inspector data is read from the active project's own saved state and chapter records. Project open/import invalidates the prior selection and pending inspector requests. A row/character from the previous project cannot be carried into the new project's inspector.
- **CS-05 — Statistics:** the inspector displays exactly Assigned Voice, Dialogue Lines, Chapters and AI Assigned. Counts use saved dialogue-assignment records whose offsets and text still match the active chapter. Chapter count uses distinct chapter numbers. AI Assigned is calculated from saved `source` metadata, not AI confidence. Legacy assignments with missing source remain visible as unknown and are not guessed to be AI or manual.
- **CS-06 — Dialogue inspector:** all matching saved dialogue lines for the selected character are available in stable 30-row pages, with a Load More action. Both AI and manual assignments are included. Selected row state is retained when an already-loaded page is refreshed; a selected line is passed to Test Voice by its saved chapter/offset identity.
- **CS-07 — Source highlighting:** manual rows use a green full-row tint/accent; AI-analyzed rows use a golden full-row tint/accent. Selection adds a separate outline and selected tint while preserving the source-specific accent/background.

### Related preview safety added while implementing the inspector

The original `voice.preview` path applies production's saved cast router. That could override a different profile chosen for a Character Studio audition. A dedicated `character.dialogue.preview` action now validates the active project's exact saved passage and confirms the selected character is one of its saved speakers. It uses the exact selected saved Voice Studio profile for this audition and bypasses the production cast router only for this preview. It does not write narrator or character assignment state. Existing production synthesis and ordinary Voice Studio preview routing retain their previous cast-aware behavior.

The UI caches completed dialogue/profile previews for replay, pauses/resumes the current audio, and stops old audio when the selected character, dialogue row, profile or project changes. A late preview completion is not played if the inspector selection has changed while it was generating.

### Matching-head test evidence

- Test source commit: `65425bc2feeb251e199ec1a3eb0b3131ff9bfb2b`.
- Windows Actions test-only run **#41191777934**: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41191777934
- Result: **449 tests passed in 63.397 seconds**; the regression job completed successfully.
- The run includes behavioral coverage for mixed AI/manual records and alias matching, distinct chapter counts, zero assignments, unknown legacy provenance, stale span exclusion, 37 dialogue lines across 30-row pages, project isolation, saved-only Assigned Cast search by name/alias/voice, local-only preview-profile selection, direct preview profile selection without modifying narrator/assignment, rejection of another character's passage, source-preserving selection styling and Node syntax validation of the frontend adapter.
- This was a test-only commit. Frozen-app packaging, installer, Defender, SHA-256 and artifact upload steps were intentionally skipped in this run.

### Requirement status after the test-only gate

| Requirement | Automated disposition | Remaining acceptance |
|---|---|---|
| CS-01 | AUTOMATED TESTS PASSED | Confirm the real packaged screen and counts on the target PC |
| CS-02 | AUTOMATED TESTS PASSED | Confirm project switching and reopen behaviour in the installed app |
| CS-05 | AUTOMATED TESTS PASSED | Compare live project counts against a user-selected real book |
| CS-06 | AUTOMATED TESTS PASSED | Inspect long-list scrolling and selected-line preview in the installed app |
| CS-07 | AUTOMATED TESTS PASSED | Visual confirmation against the supplied Premium V2 reference at target resolutions |

### Explicitly not closed by this Step 3 test run

- The matching Windows artifact checkpoint is the next gate; this test-only run did not package the app.
- Manual target-PC acceptance of the packaged Character Studio screen, navigation/restart persistence and actual audio playback remains pending.
- The preview integration safety above does not by itself close every CS-03/CS-04 requirement or every VS-02/VS-08 subrequirement. Progress/status, real playback, pause/replay and profile identity still need packaged audio acceptance.
- Voice Studio's wider frozen scope VS-01 through VS-08, including the under-60-second real 30-second preview benchmark and all other Step 4–10 plan work, remains separate.
- Stage 1 target-PC hardware acceptance and Stage 2 target-PC import/edit/reopen acceptance remain independent release gates.

**Decision:** Step 3's implementation and automated regression gate are green on the identified source SHA. Do not mark the step fully accepted until the matching artifact checkpoint is successful and the target-PC UI/audio acceptance is recorded.
