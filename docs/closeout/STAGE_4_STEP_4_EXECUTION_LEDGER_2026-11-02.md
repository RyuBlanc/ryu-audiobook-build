# Stage 4 Step 4 — execution ledger
Audit date: 2 November 2026

Repository: https://github.com/RyuBlanc/ryu-audiobook-build
Working branch: `stage-4/step-4-audio-assembly`
Current functional source head before the final artifact-checkpoint commit: `fd99dc7b382fe94fce84877c8b8ac021fd2ebd2c`

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

The test validates exact preview/final mixer-configuration equality, identical sample rate/duration and decoded spectral-content parity at the opening/cue/chapter anchors. Run #2075 exposed independent AAC encode sample-level variation (2.51% waveform RMSE against the 2% check); Chapter-Based BGM and Voice Only passed. The parity test was made codec-robust by comparing configuration exactly and decoded frequency-content signatures, not by widening a sample-RMSE tolerance. The original #2075 failure remains recorded.

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

### GEN-07 — Mix Summary and compatibility-alias counting
The stable chapter BGM migration intentionally returns each saved assignment under both its stable chapter ID and its legacy numeric alias. This preserved old callers but initially caused the frontend Mix Summary to count the same chapter twice because it iterated over every override-map value. The packaged-app failure in #2077 exposed the issue: saved slider values were correct, but the UI summary did not reach the expected “3 chapters” state.

Fix in assets/frontend/premium_v2_backend_adapter.js: renderSoundMixSummary() now builds a single effective override row per actual project chapter, resolving stable ID first and numeric fallback second. Active BGM rows, missing-track counts, assigned-chapter count and fallback track aggregation use this de-duplicated chapter list. Numeric aliases remain available for compatibility.

Added tests/test_stage2_sound_ui_contract.py::test_mix_summary_counts_each_stable_chapter_once_despite_legacy_number_aliases. #2080 passes this regression and the full 1,059-test suite. A fresh packaged UI acceptance/build is required to prove the runtime fix in the frozen Windows executable.
### GEN-08 — Production preview and job controls
Production Studio now has dedicated Play, Stop and Download Preview controls, an explicit preview status and playback-time readout. These are separate from Voice Studio's own preview controls. Playback and stop operate on the same validated preview audio created by `production.preview`; Download uses the same native save action and retains narrator/chapter naming. Controls stay disabled until validated audio exists, and playback status/time are synchronized with the active preview.

`tests/test_stage2_sound_ui_contract.py::test_final_production_preview_generation_and_job_buttons_are_present_and_connected` verifies the rendered Production Studio controls and their frontend/backend wiring: chapter Preview, Generate Book, Pause, Cancel, Play, Stop, Download, full-book Mix Preview, sound-draft flush, registered bridge commands and capabilities. Run #2083 passed this contract as part of the full suite.
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
| #2077 | 41445167744 | Failed | The 1,055-test job passed; frozen EXE, bundled assets and critical modules passed. Packaged Sound Design UI acceptance failed only at “Mix summary live effective values”; Inno Setup, Defender and artifact uploads were correctly skipped. Root cause: ID and numeric aliases were counted as separate chapter assignments. Fix is in #2080 source. |
| #2078 | 41445626058 | Cancelled | Codec-robust preview/final comparison and strict legacy-folder matching were superseded by a subsequent manifest-migration retry push. Not a test failure. |
| #2079 | 41446257120 | Success | 1,058 tests passed; frontend syntax and isolated Qt lifecycle checks passed. Covered persistent chapter IDs, stable-ID frontend save payload, and retryable narration-manifest migration. |
| #2080 | 41447145259 | Success | 1,059 tests passed in 49.413 seconds; frontend syntax and isolated Qt lifecycle checks passed. Added Mix Summary de-duplication coverage for stable IDs plus numeric compatibility aliases. Tests-only; build job skipped. |
| #2081 | 41447780375 | Failed | 1,059 tests passed, but packaged frozen-app acceptance failed because the restart validator read chapter BGM only by numeric keys while current chapters persist assignments by stable ID. No installer/Defender/artifact steps were reached. Validator corrected to resolve `chapters.json` IDs first. |
| #2082 | 41452945525 | Failed | Frontend syntax and Qt lifecycle passed; 1,061 tests ran with one failure in the newly added production-button contract. The contract incorrectly expected Voice Studio `playPreview` inside Production Studio markup. Corrected by adding dedicated Production Studio playback/stop/download/status/time controls and asserting those actual controls. |
| #2083 | 41454123181 | Success | 1,061 tests passed in 51.288 seconds; frontend syntax and isolated Qt lifecycle passed. Verified stable-ID packaged persistence validator, Production Studio controls and bridge actions. Tests-only; build job skipped. |

Latest full regression: #2083 **1,061 tests passed** in 51.288 seconds. Frontend JavaScript syntax validation and isolated native Qt lifecycle regression also passed. Run #2083: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41454123181.

Preceding validation runs: #2080 passed **1,059 tests** (https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41447145259); #2079 passed **1,058 tests** (https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41446257120).

#2080 and #2083 were tests-only checkpoints; their build jobs were skipped and they produced no Windows installer/portable/hash artifacts. #2077 failed at packaged Mix Summary acceptance; #2081 failed at stable-ID BGM persistence acceptance. Both causes have source/validator corrections and are covered by the #2083 passing suite, but the corrected frozen-app acceptance still must pass. #2082 had one incorrect static-HTML contract assertion; dedicated Production Studio controls were added in #2083. A fresh full artifact checkpoint is required on the current head.

## Remaining Step 4 gates

1. Run a fresh final Windows package checkpoint on the current source: full regression, frozen EXE, bundled assets/modules, packaged Sound Design UI acceptance (stable-ID persistence and Mix Summary), Production Studio UI/control checks, installer compilation, SHA-256 manifest, fail-closed Microsoft Defender scans and all required artifact uploads. The #2077, #2081 and #2082 causes are corrected in source/tests; packaged runtime acceptance remains the release gate.
2. Record exact source SHA, build/run ID, installer/portable/manifest artifact IDs, sizes, hashes and expiry.
3. Perform target-PC installed-app acceptance and real audio listening. CI does not establish that the user’s Windows machine successfully installs or that the resulting audiobook sounds correct.
4. Exercise real final audiobook generation/recovery on the target PC and inspect a generated M4B for actual playback, chapter navigation, metadata, cover, bitrate and complete decoding.
5. Retain any blocked/unavailable hardware/runtime acceptance explicitly; do not reopen unrelated completed Stage 1–3 source work.

## Release boundary

This Step 4 artifact checkpoint is not a Version 1.2.0 release. Do not bump the version, tag 1.2.0 or publish a GitHub Release until the frozen master register is accepted, required target-PC listening/runtime evidence is recorded, and the exact release commit has passed its release gate.

## Continuation checkpoint

- Stage: Stage 4, Step 4 — final closure.
- Branch: `stage-4/step-4-audio-assembly`.
- Functional source SHA before this ledger/artifact-checkpoint commit: `fd99dc7b382fe94fce84877c8b8ac021fd2ebd2c`.
- Latest passing tests-only run: #2083 / 41454123181 (1,061 tests).
- Previous passing source run: #2080 / 41447145259 (1,059 tests).
- Failed package attempts retained: #2077 (Mix Summary duplicate aliases), #2081 (acceptance checked legacy numeric keys rather than stable IDs), #2082 (incorrect Production preview-control contract). Corrected current code passed #2083 regression; these runtime gates must pass in the fresh package.
- Latest successful Windows package before Step 4: #2062 on the Step 3 branch; it is not a Step 4 package.
- Next action: final Windows artifact checkpoint on `fd99dc7…`; inspect packaged UI, stable-ID persistence, installer, Defender and artifact outcomes. Target-PC installation/listening acceptance remains open.
