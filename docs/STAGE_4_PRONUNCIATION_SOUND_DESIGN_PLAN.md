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
- [ ] Run the complete unittest suite on the latest Stage 4 head. Run #931 exercised 451 tests and found one assertion mismatch in the new deleted-cue regression (implementation correctly raised an actionable missing-selection error); the expectation was corrected for the next run.
- [ ] Run the Windows frozen-app, bundled-asset, installer, SHA-256, and Microsoft Defender workflow on the latest Stage 4 head. Run #931 stopped at regression tests before packaging; latest-head verification is pending.
- [ ] Target-PC acceptance: edit/save/reopen pronunciation rules and sound-design assignments, generate previews, and compare actual output with requested settings.
- [ ] Preserve and track all earlier open acceptance gates: Stage 1 hardware freeze/crash validation; Stage 2 supported-format import/edit/reopen validation; Stage 3 Voice Studio/Character Studio UI and actual voice-preview acceptance.
- [ ] Do not mark Stage 4 complete from green CI alone.

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
- Latest-head Windows rerun is required after this correction. Do not claim packaging, installer, SHA-256, Defender, or complete Stage 4 acceptance until the new workflow actually confirms those gates.
- Remaining manual acceptance: target-PC listening and cue boundary/audibility/mix quality, plus Stage 1–3 carry-forward checks listed above.
