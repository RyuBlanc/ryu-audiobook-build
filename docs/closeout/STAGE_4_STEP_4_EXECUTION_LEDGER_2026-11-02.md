# Stage 4 Step 4 — execution ledger
Audit date: 2 November 2026

Repository: https://github.com/RyuBlanc/ryu-audiobook-build
Working branch: `stage-4/step-4-audio-assembly`
Current source checkpoint before the artifact build: `6160e6b029d9bd9919906741dea13bca65cb2331`

## Stage 4 sequencing status

- Step 1 — Pronunciation Studio: prior Step 1 checkpoint recorded; remaining manual/UI/runtime acceptance remains governed by the Stage 4 master handoff.
- Step 2 — Sound Design and Pronunciation integration: prior Step 2 checkpoint recorded; actual target-PC listening acceptance remains open.
- Step 3 — Preview and Production integration: successful Windows package checkpoint #2062 and tests-only checkpoint #2063 were reported before Step 4.
- Step 4 — Audio assembly, integrity and final closure: implementation and automated validation in progress; this ledger does not declare Stage 4 closed.

## Step 4 work completed in source

### GEN-01 — Effective generation configuration
Added `tests/test_stage4_generation_configuration.py`. The regression checks the production bridge-to-GenerationManager handoff for saved narrator/provider identity, effective pronunciation dictionary, narration speed/pacing, bitrate, same/chapter BGM strategy, chapter overrides, opening/next-chapter/closing cues, volumes, ambience, fades, effects, cover and Generate-form metadata.

### GEN-02 — Checkpoint invalidation and reuse
Added persistent `chapter_id` values to chapter records while preserving positional Chapter constructor compatibility. Legacy chapter JSON receives unique stable IDs on load and is persisted. Existing narration manifests receive an ID only on exact number-and-title match; migration does not guess when the match is ambiguous.

The generator now finds existing chapter checkpoint folders by stable ID, reuses valid chunks after chapter reorder/rename, and writes the ID into narration and chunk manifests. Duplicate checkpoint folders for one ID fail with an actionable error.

Pronunciation/provider/voice and existing checkpoint invalidation contracts remain in the regression suite; this work does not replace those existing contracts.

### GEN-03 — Cancellation, retry and recovery
Preserved the existing preview cancellation, FFmpeg failure cleanup, retry, stale-output and recovery regression coverage. Cancellation remains safe-boundary based for provider/FFmpeg operations that cannot be interrupted mid-call.

### GEN-04 — Empty and ineligible chapters
Preserved the existing generation preflight and full-book preview eligibility checks for empty, skipped and ineligible chapters, including clear rejection when no eligible chapters remain.

### GEN-05 — Final M4B integrity
Changed final M4B validation to decode the complete audio stream with FFmpeg instead of decoding only the first 0.25 seconds. Updated the real FFmpeg validation regression accordingly. Existing container, chapter, metadata, cover, bitrate and duration checks remain in the relevant test suite.

### GEN-06 — Preview/final audio parity
Added a real FFmpeg preview-versus-final assembly regression using a controlled test project for:
1. Same BGM.
2. Chapter-Based BGM, including an explicitly unassigned/No BGM chapter.
3. Voice Only.

The test validates identical sample rate/duration and compares decoded audio output. On run #2075 the Same BGM comparison exceeded the test's 2% waveform-error threshold (2.51%); Chapter-Based BGM and Voice Only passed. The current head was rerun in #2076 and the combined parity test passed. The earlier failure remains recorded; the tolerance was not increased to conceal it.

### Cross-module chapter and Sound Design integrity
Chapter BGM assignments are now persisted under stable chapter IDs and are resolved by ID before the legacy number alias. Number aliases are retained for compatibility with old narration manifests and number-only adapter callers.

Legacy number-keyed BGM assignments are mapped to stable IDs when the project loads, before the user can reorder/split/merge chapters. The migration keeps the old numeric aliases. The BGM adapter accepts stable IDs, rejects stale/nonexistent IDs and keeps older number-only callers working.

The full-book preview now locates saved narration by stable chapter ID instead of relying only on the current `NNN_` folder prefix. Legacy manifests use strict number/title matching; multiple matches fail visibly instead of selecting an arbitrary chapter.

Regression coverage includes:
- Legacy project chapter-ID migration and persistence.
- Legacy BGM assignment migration on project load.
- Reorder and split identity behavior.
- Merge retaining the leading chapter identity.
- BGM save with stale display number but correct stable ID.
- Stable-ID assembler lookup ahead of conflicting numeric alias.
- Generator reuse of the existing chapter checkpoint folder after reorder.
- Full-book preview selecting the moved chapter's saved audio rather than a decoy matching the current number prefix.

## Verification history

| Build | Run ID | Result | Notes |
|---|---:|---|---|
| #2064 | 41440044308 | Failed | Initial GEN-01 test expected metadata fields not present on the current Generate UI; test corrected to match the actual saved UI contract. |
| #2065 | 41440400706 | Failed | Windows output-path assertion compared different path spellings; test corrected to compare resolved paths. |
| #2066 | 41440775225 | Success | 1,046 tests passed; Step 4.1 configuration handoff regression. |
| #2067 | 41441216532 | Failed | Expected test-first red run before stable chapter identity implementation. |
| #2068 | 41442021110 | Failed | Legacy lightweight test chapter objects lacked the new optional ID; compatibility handling added. |
| #2069 | 41442436965 | Failed | Empty/unconfigured chapter override was incorrectly surfaced as a saved row; backend corrected to omit empty overrides. |
| #2070 | 41442919551 | Success | Empty override correction and compatibility regression passed. |
| #2071 | 41443034258 | Cancelled | Superseded by a newer source push; cancellation is not classified as a code failure. |
| #2072 | 41443187767 | Failed | Test module import failed due to a malformed multiline context-manager fixture; fixture corrected. |
| #2073 | 41443371466 | Failed | Same fixture syntax issue; corrected in the next commit. |
| #2074 | 41443627448 | Success | 1,054 tests passed; stable-ID preview lookup and three-mode preview/final parity passed. |
| #2075 | 41444246982 | Failed | 1,055 tests ran; only Same BGM waveform parity exceeded the 2% threshold (2.51%). Merge/load-ID checks passed. |
| #2076 | 41444458705 | Success | Current source SHA `6160e6b...`; 1,055 tests passed in 48.062 seconds. JS syntax, Qt lifecycle, full regression, merge/migration and all three preview/final parity scenarios passed. |

Full regression result for #2076: **1,055 tests passed**. Frontend JavaScript syntax validation and isolated native Qt lifecycle regression also passed.

Run #2076 test job: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41444458705

The build job was skipped in #2076 because this was a tests-only checkpoint. It produced no Windows installer/portable/hash artifacts.

## Remaining Step 4 gates

1. Run the final Windows package checkpoint from the exact post-ledger source commit, with regression, critical packaged asset/module checks, installer compilation, SHA-256 manifest, fail-closed Microsoft Defender scans and all required artifact uploads.
2. Record exact source SHA, build/run ID, installer/portable/manifest artifact IDs, sizes, hashes and expiry.
3. Perform target-PC installed-app acceptance and real audio listening. CI does not establish that the user’s Windows machine successfully installs or that the resulting audiobook sounds correct.
4. Exercise real final audiobook generation/recovery on the target PC and inspect a generated M4B for actual playback, chapter navigation, metadata, cover, bitrate and complete decoding.
5. Retain any blocked/unavailable hardware/runtime acceptance explicitly; do not reopen unrelated completed Stage 1–3 source work.

## Release boundary

This Step 4 artifact checkpoint is not a Version 1.2.0 release. Do not bump the version, tag 1.2.0 or publish a GitHub Release until the frozen master register is accepted, required target-PC listening/runtime evidence is recorded, and the exact release commit has passed its release gate.

## Continuation checkpoint

- Stage: Stage 4, Step 4 — final closure.
- Branch: `stage-4/step-4-audio-assembly`.
- Source SHA before artifact-ledger commit: `6160e6b029d9bd9919906741dea13bca65cb2331`.
- Latest passing tests-only run: #2076 / 41444458705.
- Latest failed run retained for history: #2075 / 41444246982 (Same BGM parity threshold).
- Latest successful Windows package before Step 4: #2062 on the Step 3 branch; it is not a Step 4 package.
- Next action: artifact checkpoint build, then inspect package artifacts and record target-PC acceptance still pending.
