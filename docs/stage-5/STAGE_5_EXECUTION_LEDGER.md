# Stage 5 — Execution Ledger

Audit date: 2 November 2026  
Repository: https://github.com/RyuBlanc/ryu-audiobook-build  
Stage 4 checkpoint: [Build Windows App #2084](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41455259436)  
Stage 4 checkpoint SHA: `ace9630d2d6b4a745c029906e0624637d4e3fdd3`  
Stage 5 branch: `stage-5/step-1-production-metadata`

## 1. Repository baseline and branch decision

- GitHub Actions reported 770 total workflow runs during the baseline audit.
- Stage 4 checkpoint #2084 succeeded on `stage-4/step-4-audio-assembly` at `ace9630d2d6b4a745c029906e0624637d4e3fdd3`.
- #2084 passed the Regression Tests job (1,061 tests) and Windows application/package acceptance jobs, with installer/portable/hash artifacts present. The public release step was skipped by its release condition.
- The Stage 4 completion record leaves target-PC installed application acceptance and real-audio listening pending. Automated evidence does not replace those manual gates.
- Default branch `main` was at `356b536499be8d3679d96496f24f3836864cb47e`, but it is **diverged** from the Stage 4 checkpoint. `main` is 30 commits ahead of the shared ancestor; the Stage 4 branch is 1,641 commits ahead of `main`. The Stage 4 branch contains the Production Studio work and Stage 5 source baseline.
- Windows build attempts #2085–#2087 on `main` were skipped because maintenance-only commits intentionally short-circuit the Build Windows App job. Later Provider Functional/Runtime Smoke runs #405/#406 passed on the `main` maintenance SHA, but do not prove a Windows app package.
- The latest verified Stage 4 packaged baseline is #2084 / `ace9630d2d6b4a745c029906e0624637d4e3fdd3`. No unverified merge/cherry-pick from divergent `main` is included.
- Stage 5 branch `stage-5/step-1-production-metadata` was created directly from the exact #2084 SHA.

## 2. Actions history reconciliation from #2084 through latest

| Run | Workflow | SHA / branch | Conclusion | Reconciliation |
|---|---|---|---|---|
| [#2084](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41455259436) | Build Windows App | `ace9630d2d6b` / Stage 4 Step 4 | Success | Immutable Stage 4 baseline; retained |
| [#2085](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41478867813) | Build Windows App | `0000689e1e30` / main | Skipped | Maintenance-commit guard; not a code failure |
| [#2086](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41479038823) | Build Windows App | `ca22ea9cc221` / main | Skipped | Maintenance-commit guard; not a code failure |
| [#2087](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41479474195) | Build Windows App | `356b536499be` / main | Skipped | Maintenance-commit guard; not a code failure |
| [#403](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41478867769) | Provider Functional Smoke | `0000689e1e30` / main | Cancelled | Newer push superseded the run; provider workflow has cancel-in-progress concurrency |
| [#404](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41478867955) | Provider Runtime Smoke | `0000689e1e30` / main | Cancelled | Superseded by newer push; concurrency cancellation |
| [#405 attempt A](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41479038642) | Provider Runtime Smoke | `ca22ea9cc221` / main | Cancelled | Superseded by next push; concurrency cancellation |
| [#404 attempt B](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41479039136) | Provider Functional Smoke | `ca22ea9cc221` / main | Cancelled | Superseded by next push; concurrency cancellation |
| [#405 final](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41479474602) | Provider Functional Smoke | `356b536499be` / main | Success | Matching-HEAD functional smoke jobs passed |
| [#406 final](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41479474408) | Provider Runtime Smoke | `356b536499be` / main | Success | Matching-HEAD runtime smoke jobs passed |

Storage-cleanup workflow runs in the same interval are housekeeping, not product acceptance. Cancelled provider attempts were superseded by newer pushes due workflow concurrency; final same-HEAD provider functional/runtime runs passed. Newer skipped Windows runs did not produce an alternative package. Older Stage 4 test/package failures remain recorded in the Stage 4 ledger; their causes were corrected by later commits and checkpoint #2084. No failed Stage 5 run exists at Stage 5 start.

## 3. Step 5.1 source audit

Existing behaviour retained:
- Native Generate already had editable metadata controls, local-project history dropdowns and saved-state restore.
- Cover helpers copy supported formats into project-local `assets`; EPUB/DOCX/PDF cover extraction already exists.
- Production Studio already had an active-project summary, output target/format/bitrate data and seven readiness indicators.
- Sound Design's `renderSoundMixSummary()` already derives from saved BGM state, de-duplicates stable chapter IDs/legacy aliases and distinguishes Same BGM, Chapter-Based BGM and Voice Only.
- Production Studio already used real chapter-preview/generation job bridge commands. Step 5.1 does not create a competing generation engine.

Step 5.1 gaps:
- Premium V2 Production Studio had no Input Project Details dialog/button.
- Production summary omitted Genre and Series Volume.
- No dedicated project-scoped Premium V2 metadata save/history bridge contract existed.
- No saved-data metadata completion state was displayed.
- Full generation lacked an independent backend metadata completion guard.

The seven existing readiness indicators and live music/output calculations are retained, not replaced with fixed green values.

## 4. Step 5.1 execution substeps

1. 5.1.1 — Input Project Details control and functional dialog.
2. 5.1.2 — Real active-project metadata, narrator profile, Character Library series, cover picker and historical values.
3. 5.1.3 — Saved-metadata completion gate; unsaved edits/save failures remain warnings; previews remain available.
4. 5.1.4 — Dynamic project summary including Genre and Series Volume.
5. 5.1.5 — Preserve accurate Same BGM / Chapter-Based BGM / Voice Only summary and unique track counting.
6. 5.1.6 — Preserve the seven backend-derived readiness indicators.
7. 5.1.7 — Exact-commit regression for metadata, history, save errors, project isolation, gate, summary, readiness and persistence.

Gate policy: Book Title, Author, actual selected Narrator profile, Language and Genre are mandatory. Publisher, Series, Series Volume, Release Year and Cover Image are optional descriptive tags. The source requirements enumerate fields but do not explicitly classify mandatory tags; this policy is documented in the requirement register.

## 5. Current status

- Step 5.1: IN PROGRESS.
- Step 5.1 source and tests are committed together for one exact-commit CI checkpoint.
- Steps 5.2–5.5: OPEN; sequential execution only after the preceding exit condition passes.
- No version bump, tag or public release during Stage 5 implementation.

## 6. Manual acceptance boundary

CI cannot establish installed Windows app launch/navigation/resizing, visual dialog quality across required display sizes, real narrator-profile refresh, cover persistence after an actual app restart, or real M4B metadata/cover embedding and listening quality. These remain explicit runtime acceptance items and must not be marked VERIFIED COMPLETE from CI alone.


## 7. Step 5.1 follow-up hardening

Run #2088 completed successfully on `e7aa0a2d2a3fafd8be949d24266892f9791e729f`: 1,070 tests passed, Premium V2 and packaged Sound Design JavaScript syntax passed, and the isolated native Qt lifecycle regression passed. The build job was skipped under the explicit feature-branch artifact-checkpoint rule.

The follow-up artifact-checkpoint source adds:
- A paired metadata write transaction covering project.json and state.json, with read-back verification and rollback to original contents on any failure.
- Cover selection returns the validated source path without prematurely copying. Save copies the cover into project assets; a failed metadata transaction restores any overwritten cover bytes.
- Long/short Release Year values are rejected, not truncated into a valid year.
- Project switching is blocked while Input Project Details contains unsaved changes; closing a clean dialog is safe.
- A confirmed backend save remains reported as saved even if a later list/summary refresh fails.
- Additional regression coverage for second-file write failure/rollback, year bounds, cover picker validation and cover persistence after project reload.

The new artifact-checkpoint run must pass the exact implementation tests and package job before Step 5.1 is eligible for closeout.


## 8. M4B metadata hand-off verification

The Production M4B assembly path accepts the series-volume tag as `series_number`, not `series_volume`. The Stage 5 bridge now maps saved `state.json.series_volume` to `metadata.series_number`, and the existing generation-configuration regression asserts that exact hand-off.

The project cover chooser continues to accept the cover formats supported by the project-cover subsystem. During metadata save, JPG/JPEG/PNG are copied as-is; supported WebP/GIF/BMP/TIFF inputs are decoded and normalized to PNG because the current M4B assembler's cover validator accepts JPG/JPEG/PNG. The conversion is part of metadata save and participates in rollback if either project metadata file fails to commit.


## 9. #2089 regression failure and correction

Run [#2089](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41540647868) completed with one test error: `test_metadata_save_rolls_back_project_json_when_state_write_fails`. The injected failure rejected every write to `state.json`, including the rollback rewrite even though the atomic write had failed before replacing the original file. The transaction now tracks successful replacements and rolls back only the files whose atomic write completed. The original state file is left untouched when its attempted atomic write raises before commit. Added cover-format conversion and cover-rollback tests to guard M4B-compatible PNG normalization.


## 10. Supported cover-format regression coverage

Stage 5 metadata tests now exercise the Premium V2 save path for WebP covers: the source is decoded, normalized to a PNG accepted by the M4B assembler, saved into project-local assets and referenced by the persisted project state. A paired failure test confirms the previous embedded PNG cover remains intact when the subsequent state.json write fails.


## 11. Packaged Production metadata acceptance added

The Windows frozen-app acceptance script is extended to exercise the Stage 5 metadata dialog inside the actual packaged executable. It verifies all ten field controls, the read-only selected narrator, history dropdown values from a second real saved project, unsaved/incomplete gating, preview remaining enabled, a deterministic first-save failure that leaves project files unchanged, a successful retry, project-local PNG cover persistence, and the exact remaining Narrator field. The same acceptance harness then starts a **new frozen-app process** and verifies that title, author, publisher, series/volume, language, year, genre and cover are restored from the active project. A valid one-pixel PNG is generated as a fixture and decoded by the real Qt image reader.


## 12. Packaged metadata acceptance fixture correction

Before the new packaged acceptance run began, source review caught a byte-escape issue in the one-pixel PNG fixture and an over-escaped Windows path assertion. The fixture now emits the PNG signature, RGBA scanline and chunks from explicit byte values; the restart assertion normalizes backslashes to forward slashes before testing the project-local cover path.
