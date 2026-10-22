# Stage 4 Plan — Pronunciation and Sound Design

**Working branch:** `stage-4-pronunciation-sound-design`  
**Baseline:** Stage 3 implementation head `d5d17f41393910596ad793dfe8df8753c6a1a836` (Stage 3 PR #18 remains open)  
**UI rule:** preserve the approved Premium V2 HTML and all existing control layout. Fix backend behavior and tests; no redesign, simulated results, or replacement of real audio with demo data.

## Stage 4 objective

Make pronunciation handling and story-aware sound design predictable, persistent, safely applied to real synthesis, and verifiable in the packaged Windows application. Keep audio generation resumable and preserve chapter timing, source text, and existing projects.

## 4.1 Pronunciation dictionary and text preparation

- [x] Audit pronunciation dictionary data shape, normalization, duplicate/conflicting entries, case sensitivity, Unicode, invalid/empty entries, and current-book versus library scopes (implementation + regression coverage added in Prompt 1).
- [x] Add regression tests for save/reload persistence, edit/delete, deterministic duplicate resolution, scope isolation, and project isolation.
- [x] Keep chapter source text and saved dialogue offsets unchanged; resolve cast/offset spans before applying pronunciation replacements to cast segments.
- [x] Add coverage for overlapping phrases, word boundaries, punctuation, repeated terms, Unicode NFC-equivalent names, disabled/invalid entries, and non-cascading replacements.
- [x] Verify pronunciation-adjusted chunk text participates in per-chapter generation signatures: affected chapters reset; unrelated chapters retain reusable work.
- [x] Expose actual preview replacement counts and selected profile/provider/voice identity; report prepared replacement/rule counts during production generation.
- [x] Apply Current book, matching Series, and Global library rules to real preview and production synthesis with deterministic precedence; corrupt stores fail visibly.

## 4.2 Sound-design catalogue and story assignments

- [x] Audit cue/BGM catalogue records, asset paths, missing files, metadata, and safe defaults; catalogue rows surface persisted title/license/duration metadata.
- [x] Validate audio readability during import and before use; corrupt, unsupported, missing, and zero-duration assets produce actionable errors.
- [x] Explicitly selected music/cue paths no longer fall through to an unrelated library track when missing or unreadable.
- [x] Add focused regression tests for catalogue metadata, import isolation, invalid/missing assets, cue/BGM assignments, BGM-off behavior, bounded fades/gain, and output/source separation.
- [x] Keep saved paths visible to validators instead of converting missing selections to `None`; preserve zero-volume values rather than replacing them with defaults.
- [x] Guard against final audiobook output overwriting any selected sound-design source asset.
- [ ] Target-PC listening and UI save/edit/clear/reload acceptance remain open.

## 4.3 Preview, synthesis and audio assembly

- [ ] Test voice preview with pronunciation rules enabled and disabled, and verify the selected profile/provider is the one requested.
- [ ] Test sound-design preview uses real assigned cues/music, reports the actual rendered duration, and cleans up temporary files.
- [ ] Verify chapter transitions and opening/closing cues are applied once at the correct boundaries, including when BGM is off.
- [ ] Test cancellation, provider/FFmpeg failures, retry, cleanup, and resumability for preview and final assembly.
- [ ] Test generation signatures/checkpoints change when pronunciation rules or sound-design assignments change, without invalidating unrelated work.
- [ ] Listen to representative speech/music/SFX mixes on the target PC; automated duration checks do not establish audio quality.

## 4.4 Regression, packaging and acceptance

- [x] Add focused Stage 4 regression tests and run them during development (Run #919 passed on `422fcb1bde50761f31a67653996e397953ef118a`).
- [x] Run the complete unittest suite on Stage 4 head `6cb04fca5a941778979f347d5f8ee7a07e15b643`: Run #938 executed 459 tests and passed.
- [x] Run Windows frozen-app, bundled-asset, installer, SHA-256 manifest, and artifact-upload gates on `6cb04fca5a941778979f347d5f8ee7a07e15b643`: Run #938 completed successfully. Defender's command step returned exit code 0 but explicitly logged both EXE scans as “skipped”; treat Defender clean-scan verification as unresolved, not as a confirmed scan.
- [ ] Target-PC acceptance: edit/save/reopen pronunciation rules and sound-design assignments, generate previews, and compare actual output with requested settings.
- [ ] Preserve and track all earlier open acceptance gates: Stage 1 hardware freeze/crash validation; Stage 2 supported-format import/edit/reopen validation; Stage 3 Voice Studio/Character Studio UI and actual voice-preview acceptance.
- [x] Do not mark Stage 4 complete from green CI alone.

## Prompt 1 implementation notes

- Dictionary fields are NFC-normalized and validated before writes; legacy written/spoken aliases remain readable.
- Current-book entries remain in the active project's `state.json`; global-library and named-series entries use app-owned JSON stores with atomic replacement. Existing legacy rows stored in project state remain book-local to avoid unexpectedly sharing them across projects.
- Saves canonicalize duplicate case-insensitive written forms within a scope, return conflict-resolution metadata, and reject unsupported scopes rather than persisting misleading metadata.
- The approved HTML file was not edited. The existing dictionary table now renders real persisted rows with scope/status and a delete action, and list/table selection is scope-aware.
- Automated tests added in `tests/test_stage4_pronunciation_persistence.py`. Actual TTS application of global/series scopes, generation-signature invalidation, UI runtime behavior, and target-PC save/reopen still require follow-up in Prompt 2 / acceptance.

## Stage 3 carry-forward — do not lose these items

Stage 3 Run #894 succeeded on `ec20d76106e01971e16c045a475eb72f78115c83`; the Stage 3 plan was updated after that run. Stage 3 PR #18 is open. Automated/package gates passed, but these items remain open and must not be silently treated as complete:

- [ ] Packaged Windows acceptance for actual selected-profile preview/provider identity and voice quality.
- [ ] Verify Voice Studio and Character Studio UI state, persistence/reload, and preview/generation error reporting.
- [ ] Behavioral tests for case-insensitive character updates, alias edits, duplicate names, delete semantics, and assignment references.
- [ ] Persistence-level verification of character-analysis results, confidence/examples, dialogue totals, and unassigned counts across save/reopen.
- [ ] Assignment integrity through chapter reorder/merge/split, including explicit offset migration or safe invalidation.
- [ ] Broader character detection fixtures for first-person narration, aliases, attributed dialogue, and unassigned dialogue.
- [ ] Stage 1 target-PC freeze/crash validation.
- [ ] Stage 2 target-PC TXT/EPUB/PDF/DOCX import, duplicate guidance, cancel/retry, chapter editing and reopen comparison.

## Stage 4 baseline audit

The existing application includes a pronunciation dictionary, a cast-aware voice preview path, a sound-design preview path, BGM/transition cue settings, and an audio assembly pipeline. This stage begins by testing the real implementation and fixing gaps; do not assume every listed behavior is already correct.



## Latest verification evidence

- **Run #919** completed successfully on `422fcb1bde50761f31a67653996e397953ef118a` on 2026-10-22: complete unittest/application build, frozen app, bundled assets, installer, SHA-256 manifest, Microsoft Defender scan, and artifact uploads passed. Verified run: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39793982369.
- Automated gates above are checked off only for that exact commit. Target-PC listening and save/reopen acceptance remain open; green CI is not Stage 4 sign-off.

## Completion rule

Close Stage 4 only when targeted and full automated tests pass, the Windows package gates pass on the latest code, the Stage 3 carry-forward checklist is preserved, and target-PC acceptance is either completed with evidence or explicitly left open. Never claim the actual sound is correct without listening to rendered output.


## Prompt 2 implementation notes

- Pronunciation substitutions are applied after cast/dialogue segmentation has consumed saved offsets, before pacing and TTS chunk generation. Source chapter text and stored assignment offsets are not rewritten by substitutions.
- Effective synthesis rules combine current-book, matching-series, and global-library entries in that precedence order. Duplicate written terms resolve deterministically; a disabled higher-priority row suppresses lower-scope fallback for the same term.
- Generation signatures hash the actual prepared chunk text and provider/voice identity. A changed pronunciation that changes a chapter's synthesis text invalidates incompatible checkpoints; chapters whose prepared text is unchanged remain reusable.
- Preview job results report selected saved profile/provider/voice ID, voices used by generated segments, and actual per-rule replacement counts. Production progress reports the actual substitutions prepared for synthesis.
- The approved HTML was not changed. Target-PC save/reopen, audio listening, and selected-provider acceptance remain open.


## Prompt 3 implementation notes

- Run #927 passed on commit `bc1bf253ec7394fabd87b10d92811f9473bef379`: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39806080839.
- Prompt 3 tightens the real asset path: catalogue metadata is surfaced; imports validate audio readability and persist sidecar metadata; metadata write failures are reported rather than swallowed.
- Saved sound-design paths are validated for existence, supported extension, and measurable audio duration. Production and preview call sites no longer turn missing saved paths into `None` before the validation boundary.
- Explicitly selected music/cue files no longer fall through to an unrelated library track when missing or unreadable. The user must reassign the file in Sound Design.
- The final output path is rejected if it resolves to a selected sound-design source asset.
- The approved Premium V2 HTML layout remains unchanged. Target-PC listening and interactive save/edit/clear/reload acceptance remain open.


## Prompt 3 verification correction

- Run #930: 451 tests, three failures (two expectation/fixture issues and the sound import integration contract). The code/test contract was corrected in commit `0c54d7c7762f68ad9647ec7468628f48cc395a03`.
- Run #931: 451 tests, one remaining assertion mismatch because the missing explicit cue error used the established wording “no longer exists” rather than the test's expected word “missing”. The regression expectation is broadened to accept either actionable wording. Packaging was not reached in either failed run.
- Do not treat Prompt 3 or Stage 4 as verified until a subsequent latest-head run passes the suite and Windows package gates.


## Prompt 3 additional control wiring

- Background-music fade-in/fade-out selections are now sent to the backend, bounded to 0–30 seconds, saved in the book sound manifest, restored into the existing selectors, and passed into production assembly.
- A selected zero volume remains zero instead of being replaced by a default. Disabling BGM persists an off mode while retaining the selected fade configuration.
- Legacy prototype listeners on the existing Sound Design buttons are removed by cloning those controls without changing their visible markup, preventing duplicate fake import/preview/save actions alongside backend calls.
- The approved HTML has no dedicated ambience selector or ducking control. Existing backend ambience/sidechain ducking remains supported, but adding new user-facing controls is intentionally out of scope for this no-redesign stage.


## Prompt 4 — Preview, mixing, and final assembly

- Full-book Sound Design preview now copies saved chapter working directories into a disposable staging area before invoking the production assembler. The assembler writes chapter M4A and concat metadata inside those directories; staging prevents preview from changing project chapter files or reusable generation checkpoints.
- Full-book preview now passes the saved BGM fade-in/fade-out values to the same assembler as production and uses production's 0.90 narration-speed fallback when the setting is absent.
- Voice and full-book previews register cancellable job events, stop at safe synthesis/assembly boundaries, mark cancellation distinctly, discard partial preview output, and clean their event registrations. A provider or single FFmpeg operation already in progress may finish before the next safe-boundary check.
- Full-book preview still uses saved narration and reports measured final duration; it does not re-synthesize chapters or claim duration from requested settings.
- Automated evidence will be added by the Prompt 4 regression suite and the latest Windows workflow. Target-PC listening, cue audibility/boundaries, and perceived mix quality remain manual acceptance items.


## Run #937 investigation and Prompt 4 continuation

- Run #937 failed on commit `b7b3b382f5320158b3c178340d3b4d65d31964dd`: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39854793296.
- The Windows workflow ran 459 unittest cases and stopped at `test_full_book_mix_preview_reuses_saved_narration_and_validates_all_chapters`. The test asserted the old direct `chapter_dirs` argument, while the worker correctly passes disposable `staged_dirs` so the production assembler cannot mutate saved chapter checkpoints. Other reported Stage 4 preview tests passed. Packaging steps were not reached in Run #937.
- Prompt 4 correction: update the source-contract regression to assert that chapter directories are copied into a temporary staging area and the assembler receives those staged directories. This aligns the test with the checkpoint-preservation behavior rather than weakening the implementation.
- Run #938 subsequently verified this correction and the packaging gates on commit `6cb04fca5a941778979f347d5f8ee7a07e15b643`; see the detailed Run #938 record below. Defender's tool reported the two scans as skipped, so actual malware-scan verification remains unresolved.
- Remaining manual acceptance: target-PC listening and cue boundary/audibility/mix quality, plus Stage 1–3 carry-forward checks listed above.



## Run #938 verification — Prompt 4 regression and Windows package gates

- **Workflow:** https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39858239448
- **Run:** #938, completed successfully on 2026-10-22; event `push`; branch `stage-4-pronunciation-sound-design`.
- **Verified source commit:** `6cb04fca5a941778979f347d5f8ee7a07e15b643` (parent: `b7b3b382f5320158b3c178340d3b4d65d31964dd`). Run #938 verifies the preview staging regression-test correction and the code at that SHA; it does not verify any later documentation-only commit.
- **Automated tests:** `Ran 459 tests in 35.545s`; workflow continued through the packaging steps, so the test command and build step succeeded.
- **Packaging checks passed:** frozen EXE self-test; bundled voice assets/critical modules; Inno Setup installation and installer compilation; original logo transparency/content validation; SHA-256 manifest generation; upload of installer, SHA-256 manifest, and portable application.
- **Defender qualification:** the Defender script reported “Microsoft Defender returned clean scan results for both release executables,” but the same log explicitly says scanning both `Ryu's Audiobook.exe` and `Ryu's Audiobook Setup.exe` “was skipped.” The command step returned success, yet the run alone does **not** establish that the two files underwent a completed malware scan. Verify Defender status/signature/policy and repeat a real targeted scan before claiming this gate is clean.
- **Artifacts:** installer `Ryu-Audiobook-Installer-938` (artifact ID `12461655394`, ZIP SHA-256 `5ad0614d969a6b60f4155a1bb6cb5671921a8586a82b8691b7d96949aa3ef534)); release SHA-256 manifest `Ryu-Audiobook-Release-SHA256-938` (artifact ID `12460284957`, ZIP SHA-256 `6314cf511081dd6fc20b2d1e76401338bf44a6109e792b8d10978021926bc149)); portable app `Ryu-Audiobook-Portable-938` (artifact ID `12460877630`, ZIP SHA-256 `ab7911cf14e06c6a032d69208aa30709f396f06f7a8d85fa1285e991fd6071ad`). Artifacts expire on 2026-11-21 UTC; download and preserve what you need before expiry.
- **Workflow cleanup/publishing:** older Windows build run/artifact cleanup step completed successfully. “Publish verified installer release” was skipped by workflow conditions; no GitHub release publication is claimed.
- **Run #937 root cause resolved:** the prior regression asserted the assembler received the original saved chapter directories. The implementation intentionally creates disposable `staged_dirs` with `shutil.copytree` before assembly. The test now verifies staging semantics, preventing preview assembly from mutating reusable chapter working files.
- **Remaining manual acceptance:** target-PC listen to real voice previews with pronunciation on/off and confirm selected saved provider/profile/voice identity; listen to full-book mix with real music/cues, compare measured duration and preview/final parity, and verify opening/chapter/scene/closing cues occur once at intended boundaries including BGM-off cases. Exercise UI save/edit/clear/reopen for pronunciation and sound assignments; test cancel/retry and project checkpoint preservation on a real project. Automated tests do not establish perceived audio quality.
- **Carry-forward blockers:** Stage 1 freeze/crash validation; Stage 2 TXT/EPUB/PDF/DOCX import, duplicate guidance, cancel/retry and chapter edit/reopen validation; Stage 3 packaged Voice Studio/Character Studio behavior, persistence, selected voice preview/provider identity, and character/assignment integrity remain open per the checklist above.
- **Stage 4 status after Run #938:** automated suite and packaging passed on the verified SHA, but Stage 4 remains open pending Defender scan clarification/actual scan and target-PC acceptance/carry-forward checks.


## Prompt 5 — Cross-stage regression and packaging audit (23 October 2026)

- **Audit branch/head before this consolidated audit commit:** `stage-4-pronunciation-sound-design`, `6fa0b46d93b5638a0a1ccc2eb01b2973756f341a`.
- **Previously verified baseline:** Run #940 succeeded on `9a1b9edacb133634e0f2b443f6616bd1b04b0c3b`; 459 tests passed, frozen-app/assets/installer/manifest/artifact-upload gates passed. The Defender output in that run explicitly said both EXE scans “was skipped,” so that run did not prove an actual scan. Release publication was skipped by workflow conditions.
- **Cross-stage defect found:** chapter split/merge operations could drop assignments from the following chapter, leave assignment offsets pointing at the wrong text after splitting, and strip multi-speaker/cast evidence fields during text edits. This breaks Stage 3 cast routing after Stage 2 chapter editing, despite the assignments being persisted in project JSON.
- **Implementation:** `app/chapters/editor.py` now remaps exact assignment text after split/merge, adjusts offsets across chapter boundaries, discards assignments that intersect a removed heading or split boundary rather than guessing, and retains metadata such as `speakers`, `multi_speaker_mode`, `confidence`, and source fields.
- **Regression coverage:** `tests/test_cross_stage_chapter_assignment_integrity.py` covers merge from both chapters, paragraph split, split-at-selection, edit metadata preservation, and split/merge save-reload compatibility. These tests are newly added; their pass count is not claimed until the latest-head workflow finishes.
- **Defender hardening:** the Windows workflow now treats “was skipped” output as a failed security gate and uses `-DisableRemediation` for custom scans so configured file exclusions do not silently bypass scanning. The command must still return success and recognizable completed-scan output; any skipped scan blocks artifact upload.
- **Asset observation:** Run #940 warned that the optional `music/comedy/springly_sprigs.mp3` source download failed (curl exit code 35). The packaging script marks that supplemental track unavailable and removes it from the packaged manifest; the required starter-music count and core cue checks passed. The missing optional track is recorded, not treated as evidence that the entire sound catalogue failed.
- **CI status:** a fresh full Windows workflow is required for this combined code/test/workflow/doc commit. Prior attempts #941–#943 were cancelled by newer pushes before validation; do not count them as passing runs. The run that checks this consolidated commit must establish the actual test count, frozen EXE, bundled assets, installer, hashes, and Defender behavior.
- **Manual acceptance remains open:** Stage 1 target-PC freeze/crash/hardware checks; Stage 2 TXT/EPUB/PDF/DOCX import, duplicate/cancel/retry, chapter operations and edit/reopen; Stage 3 actual saved-profile/provider preview, Voice Studio/Character Studio persistence/error reporting, cast assignment through reorder/merge/split and real synthesis; Stage 4 real voice/music/cue listening, measured duration, cue boundaries, BGM-off, preview/final parity, cancel/retry and checkpoint preservation. Green CI does not close these gates.
- **PR sequencing:** Stage 3 PR #18 (`stage-3/voice-studio-character-assignment`, head `d5d17f41393910596ad793dfe8df8753c6a1a836`) remains open. Stage 4 descends from that exact head (zero commits behind; changes are additive). Merge/resolve Stage 3 PR #18 first, then re-check/rebase Stage 4 against the merged Stage 3 result before opening/merging Stage 4; do not force-reset Stage 4 to an older base or drop Stage 3 commits.
- **Status:** Prompt 5 is in progress. No manual hardware/audio acceptance is marked complete.
