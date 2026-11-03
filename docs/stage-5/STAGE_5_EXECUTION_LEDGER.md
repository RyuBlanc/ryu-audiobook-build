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


## 13. Required metadata scope correction

The supplied Stage 5 detailed plan explicitly places all ten fields under the heading "Required metadata fields". The previous five-field gate was too permissive. The shared validator now requires every listed field: Book Title, Author, actual Narrator profile, Publisher, Series, Series Volume, Language, four-digit Release Year, Genre and a real non-empty JPG/JPEG/PNG cover path. The M4B cover formats are limited to the formats accepted by the assembler after the save path normalizes supported source images to PNG/JPEG/JPG.

The prior Stage 4 pronunciation-generation fixture has been updated with valid publisher, series volume, year and cover values so that its original pronunciation-specific assertions continue to test pronunciation rather than failing the new Stage 5 preflight. The Step 5.1 metadata contract suite now separately proves each declared required field blocks completion when absent or invalid.


## 14. Validator escape correction

The ten-field validator commit had over-escaped the Python NUL-character replacement and Release Year digit regex in its generated source. These are corrected in the follow-up: the normalizer removes actual NUL bytes, and the year validator uses the intended four-digit decimal expression. The exact-commit full regression must confirm that a complete metadata record with a real four-digit year and valid project cover passes the gate.


## 15. #2096 packaged metadata acceptance failure and correction

Run [#2096](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41543922208) passed the full regression suite, frozen application build, frozen EXE verification and bundled assets. Its packaged Sound Design acceptance exercised the metadata editor through the forced save failure and successful retry; all earlier packaged checks passed. The single final assertion failed because the immediate post-save cover check expected forward slashes in the Windows path. The restart assertion had already been corrected to normalize backslashes, but this earlier assertion had not. The saved cover is stored at the expected project-local `assets\\cover.png`; the test now normalizes the separator consistently and reports the exact mismatched metadata keys if another field ever differs.

## 16. #2098 packaged narrator acceptance fixture dependency correction

Run [#2098](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41550944891) passed the complete regression job (1,079 tests), JavaScript syntax validation, native Qt lifecycle check, frozen EXE build/self-test and bundled asset verification. Its packaged UI job stopped before launching the application because the acceptance Python script imported `app.tts.voice_profile`, which imports `imageio_ffmpeg`; the lightweight acceptance interpreter does not install that optional TTS dependency. This was an acceptance-harness dependency error, not an application or narrator-selection failure.

The packaged fixture now uses the stable built-in Voice Studio catalogue name `Offline Character • Anime Hero` directly. The frozen application's real `voice.select` command remains the authority: it must resolve and save the profile through the installed profile catalogue before the read-only metadata field and restart persistence assertions can pass. No application runtime dependency was added to the acceptance environment.



## 17. Stage 5.2 Generation Engine implementation

Baseline: Step 5.2 source audit began from successful packaged checkpoint #2099 on branch stage-5/step-1-production-metadata, commit d8e52ea894282c282c0785da867585d246ee4470.

Source audit findings:
- Premium V2 already used the real production.generate_book backend job and the real production.preview synthesis worker.
- Full generation exposed one Generation Engine ring, while the Production preview was sent through the application-wide monitorJob singleton. The singleton owns one activeJob, one interval and one monitor epoch, so a new monitored task could supersede the previous monitor and could write its progress into the shared Generation Engine ring.
- The preview worker already reports real segment progress, a measured elapsed heartbeat, actual output duration, total elapsed time, synthesis elapsed time and a backend-derived ETA when progress supports one.
- Full generation already reports actual chapter/chunk/assembly progress, elapsed time, backend-derived ETA and safe pause/resume/cancel operations.
- The backend already supports preview cancellation through job.cancel; the Production screen did not expose a separate Cancel Preview control.
- The Production preview selector already forwards the selected 10/30/60/90-second duration to the backend target-duration limiter. The existing 30-second default and preview synthesis implementation were preserved.

Implementation in this checkpoint:
- Added independent Production-specific monitor slots for full audiobook generation and Production preview. The general monitorJob singleton remains unchanged for import, Voice Studio, Character Studio, Pronunciation and other unrelated workflows.
- Bound full-generation Pause/Resume/Cancel exclusively to the full audiobook job ID; they no longer depend on the shared activeJob global.
- Routed Production chapter preview jobs through the same real preview worker but tagged them with the durable job type production-preview, distinct from ordinary Voice Studio voice-preview jobs.
- Persisted the selected chapter number and project chapter count on the preview job row so the Production panel can display the real selected chapter.
- Added a separate Production preview progress/timing display, explicit Replay and Cancel Preview controls, and Background Jobs cancellation support for preview jobs.
- The preview progress bar reads the job's real progress. Elapsed time uses the job's real start timestamp/elapsed field. Remaining time is shown only when the backend supplies a valid eta_seconds; measured generated duration and total/synthesis time come from the completed preview result.
- Replay reuses the already validated preview audio. Playback and download remain disabled until preparePreviewPlayback verifies a real file URL and positive measured audio duration.

Substep status at commit time:
- 5.2.1 — Source/functional-flow audit: COMPLETE.
- 5.2.2 — Idle/generating state and actual job progress display: CODE CHANGED — NOT VERIFIED.
- 5.2.3 — Independent preview/full-generation state and controls: CODE CHANGED — NOT VERIFIED.
- 5.2.4 — 10/30/60/90-second backend duration flow: EXISTING BACKEND FLOW PRESERVED; new UI wiring regression added; matching-head verification pending.
- 5.2.5 — Play/Pause/Stop/Replay and real preview cancellation: CODE CHANGED — NOT VERIFIED.
- 5.2.6 — Real timing, measured duration and failure display: CODE CHANGED — NOT VERIFIED.
- 5.2.7 — Exact-commit regression and packaged Windows acceptance: PENDING CI.

Requirements in scope: PROD-05, PROD-06 and PROD-07. PROD-08, PROD-09, PROD-15 and GEN-06 remain OPEN for their planned later integration step. No code-level work in this checkpoint closes Stage 5.1's outstanding manual acceptance or its metadata-gate policy reconciliation.

The backend intentionally serializes synthesis and full audiobook generation. This implementation gives both operations independent ownership and state rendering; it does not claim that simultaneous preview and full-book synthesis are supported.



## 18. Step 5.2 regression hardening and exact-head results

The first artifact checkpoint attempt, run #2100 on commit 1db667937a97b67dc08d02ce0dfe518216627091, passed dependency installation, frontend JavaScript syntax validation and the isolated native Qt lifecycle regression, but the full suite reported 8 failures/errors (1,082 tests). The failures exposed contracts that needed to be preserved or deliberately updated:
- Four existing polling/UI-stability tests located refreshJobsImpl() by its original zero-argument function signature. Passing an optional snapshot parameter changed that source contract unnecessarily. The adapter now keeps refreshJobs() / refreshJobsImpl() unchanged and uses the monitor's normal shared job refresh.
- The Production Pause/Resume/Cancel contract still expected the old global activeJob target. The test now verifies the independent productionFullJobId path while retaining the generic monitorJob regression checks for unrelated modules.
- Stage 4 preview contract tests expected the old preview command shape. They now verify the explicit _production_preview job type and the stale-request guard.
- The new Production preview job now also participates in _assert_no_active_audio_synthesis, so other backend entry points cannot start a second audio synthesis while a Production preview is active.

Runs #2101, #2102, #2104 and #2105 were cancelled as the same branch received the next focused correction commits; these did not provide pass/fail evidence for the final source.

Run #2103 was an intermediate commit (81cd91919fda4ba85cc0974d13b30cbc25226013) and failed on the remaining old refresh/preview contract assertions. Those were corrected before the final consolidated regression run.

Run #2106 completed successfully on commit 97a4d3094dac80827bfc8ce1f0df0b12141d46e6:
- 1,082 regression tests passed in 48.684 seconds.
- Premium V2 frontend JavaScript syntax validation passed.
- Isolated native Qt lifecycle regression passed.
- The build/package job was skipped because this commit was a regression-only correction, not an artifact checkpoint.

Further Step 5.2.2 hardening in this checkpoint:
- The full-generation progress text now displays Idle instead of an invented 0% when no job exists; it reports a percentage only for a real job or verified completed output.
- Failed full-generation jobs show the actual backend error/message in the Generation Engine status.
- The Production preview monitor now displays the real current chapter number and title recorded on its durable job, and includes that identity in active/completed/failed preview status.
- Step 5.2 remains CODE CHANGED — NOT VERIFIED until the matching-head artifact checkpoint and packaged job complete. Manual installed-Windows acceptance of generation, preview playback/replay and cancellation remains a separate runtime item.



## 19. Step 5.2 packaged checkpoint #2107

The user confirmed [Stage 5 Step 5.2 artifact-checkpoint Run #2107](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41562699194) completed successfully on commit `6ef7dea5c028ba477d86511b353ad03583dfe44b`.

Exact run evidence: 1,083 regression tests passed in 54.783 seconds; frontend JavaScript syntax, isolated native Qt lifecycle, frozen Windows app verification, bundled voice assets/critical modules, packaged Sound Design/Music Library acceptance, core and HTML installer creation, original-logo/hash checks and Microsoft Defender scan passed. Installer, portable app and SHA-256 manifest artifacts uploaded. Public release publication was skipped by workflow policy.

Artifacts:
- Portable `Ryu-Audiobook-Portable-2107`: ID `13198675557`; SHA-256 `1c015c1810a17a044b2101aa15db37b17e0d654902cbb2743c9a11c9d45933d4`.
- Installer `Ryu-Audiobook-Installer-2107`: ID `13198164603`; SHA-256 `412987f572011f29fa335e6f51d0be9eb7eb05ea4ee7100c7c80ff0c6f27b79d`.
- Manifest `Ryu-Audiobook-Release-SHA256-2107`: ID `13198319465`; SHA-256 `2fd986728feaebf331b8836938cf15712cdfe4db9ce7386149413c8f7784af70`.

The follow-up separates Production Preview Save from generic Voice Studio save, validating the completed Production job, exact project folder, chapter number, and exact generated WAV path before native Save As. Regression contracts cover this command and the saved pronunciation/Sound Design hand-off before preview/full generation. These changes require exact-head tests and a new packaged Windows checkpoint before Step 5.2 sign-off. Installed-Windows real-audio listening, controls and resize/layout acceptance remain separate.

## 20. Step 5.2 exact-head correction after #2108

Run #2108 on commit `bbebe9a9ee8c13ba0cedf26a9dcbc0b97cf52e35` completed with 1,086 tests and four failures. Both new Production Preview save tests passed. The failures exposed:
- `production.preview.save` was in the dispatcher handler table but absent from `_capabilities()`; it is now advertised.
- The Production chapter-preview handler did not flush the saved Sound Design/BGM/cue/mix state or refresh the saved pronunciation dictionary before submitting a preview; it now awaits `flushSoundDesignState()` and `refreshTerms()`.
- Stage 2's UI contract still asserted the previous shared Voice Studio download handler on the Production button; it now asserts the dedicated Production save handler.
- Stage 4's Qwen cache test used `def _production_preview` as a slice boundary, which also matched the new `def _production_preview_save`; it now uses the exact `def _production_preview(self, payload:` signature.

The new exact-head workflow must pass before the Windows artifact checkpoint is accepted.


## 22. Selected-chapter Sound Design / final-assembly parity

The Production chapter preview now invokes the existing native Sound Design renderer. It resolves the selected chapter's saved stable BGM override, Same/Chapter-Based strategy and Auto music selection, applies the correct opening/next-chapter and final-chapter closing cues, and stores the effective sound configuration and measured M4A duration in the completed job. Production's mix status reports whether BGM, fixed chapter cues or Voice Only was used.

Production Save As now supports the exact completed job-owned WAV/M4A file and preserves its extension; Voice Studio remains on the original save action. After-first-paragraph BGM is explicitly rejected for a fresh preview when the exact paragraph boundary does not exist; no estimated offset is used. New tests exercise stable chapter assignment and Auto track resolution. Exact-head regression and Windows packaged verification pending.


## 23. #2111 selected-chapter parity regression failure and correction

Run #2111 (commit \`d32acd267b29fddb01978efc7965a21fb34bb300\`) stopped before packaging: 1,089 tests ran, 9 errors and 2 assertion failures.

Root causes:
- The new selected-chapter renderer called \`self._active_project()\` unconditionally. Existing isolated/projectless preview workers intentionally use a minimal host without that UI method. The preview request now captures selected chapter text, stable identity, index and first/last flags before dispatch; the renderer reads the active project only when that accessor exists and otherwise uses its captured chapter context (legacy projectless preview callers default to chapter 1).
- The renderer records whether a real cue was inserted. Production status now reports Voice Only, BGM mixed, chapter cues, or no assigned mix using the completed job's actual \`sound_configuration\`.
- A prior test edit incorrectly changed the generic Voice Studio save test to expect M4A. The Voice Studio path is restored to WAV-only; the Production-only M4A save test now verifies the dialog format, exact copy and .m4a destination.
- Production Save As preserves the source audio suffix if a user changes the extension, preventing AAC/M4A content from being mislabeled as WAV.

A fresh exact-head regression and Windows package are required before Step 5.2 closeout.


## 24. #2112 WAV-to-M4A preview correction

Run #2112 on commit \`2334bd9e1e82317f49c33ab3e37fea01befe9692\` completed JavaScript syntax and native Qt lifecycle checks, then ran 1,089 tests with four errors. All four were the same output-format issue: when no cue or BGM was selected (Voice Only or an empty Chapter-Based rule), the synthesized source remained WAV but was copied to a \`.m4a\` path. The renderer now re-encodes WAV sources to AAC/M4A, while copying sources only when they are already M4A. A dedicated projectless Voice Only test verifies the real encode command and destination format. Exact-head regression and packaging pending.


## 25. #2113 WAV encode import correction

Run #2113 on commit \`6f8b5e476b3bc2cbce7c5c0e2461d3cf20132b81\` completed 1,090 tests with five errors, all from the same \`NameError\`: the new WAV-to-AAC/M4A branch referenced assembler \`_run\` without importing it in the renderer's local import list. The missing import is added; no other failures were reported. Exact-head regression and package verification pending.


## 26. Imported cue source preservation correction

A final data-safety audit found that \`resolve_cue_track(selected_path=...)\` returns the original user-selected cue file. The Production chapter preview's \`finally\` cleanup had included that returned source in its temporary-file deletion list for opening/page and closing cues. This could delete imported library assets after a preview. The renderer now cleans only the derived temporary leveled/concatenated files and leaves the original cue source untouched. A new regression checks both opening and ending user-owned cue files survive with their original bytes after a Production sound-design preview. This correction is required in the next exact-head regression and package checkpoint.


## 27. Step 5.2 continuation — dedicated saved-chapter preview, narrator and ownership parity (3 November 2026)

Starting point: user-provided successful artifact checkpoints #2114 and #2115, with #2115 on `c2434ce3c1e0d69e9e1bc56dc707d24c289b3acd` in `stage-5/step-1-production-metadata`.

### Previous failure reconciliation

- Build #2113 on `6f8b5e476b3bc2cbce7c5c0e2461d3cf20132b81` failed because the WAV-to-AAC/M4A preview branch referenced FFmpeg assembler helper `_run` without importing it. The missing import is present in `c1e362d3fa3829e4ac51222e61a68440523a9c4f` (#2114).
- The #2115 checkpoint adds the cue-source cleanup correction: original imported opening/closing cue assets are not placed in the temporary deletion list. Its regression checks that both source files still exist and retain their exact bytes after preview.
- The screenshot supplied on 3 November shows #2114 and #2115 successful and #2113 failed. The screenshot does not expose the Actions run IDs or the full per-job test/packaging summaries; those details are not inferred here.

### Implementation added after #2115

1. Commit `808bcb6bcd7f17d2caa42516885c1ee81568bb8b` — Premium V2 now creates a Production-only chapter selector from the active project's saved `chapter.list` records. Production preview no longer depends on the Chapter Studio current selection. It flushes pending chapter edits, re-fetches saved chapters, and validates project/chapter ownership before accepting playback.
2. Commit `c57bb6e818a811259a9c459a91e3de3cce0a2604` — Production preview resolves the effective narrator from the saved project/series narrator resolver, matching the resolver used by full audiobook generation. Transient Voice Studio provider/voice-card values are stripped from the Production request. Preview job rows now retain the selected stable chapter ID, and Save rejects a mismatched chapter ID even when the chapter number is reused.
3. Commit `a3dd0329eccb1c6fae62b062c7224f1082a7cdfc` — added `tests/test_stage5_production_preview_parity.py` covering saved narrator selection/fail-closed behavior, global pronunciation OFF, chapter-ID Save rejection and the preview/final integration seams.
4. Commit `aac825b629dbfffbada91fdedb359401ea954594` — invalidate playable preview audio when the selected saved chapter is deleted, renumbered, renamed or its saved text changes. This protects against stale previews even if a chapter retains the same stable ID.
5. Commit `8a4eba2b3ad5fa849b75ebb671e57b9932d8a763` — expanded the regression contract for chapter-content invalidation.

### Existing configuration wiring confirmed by source inspection

- PROD-08: Production's pronunciation switch is synchronized with Pronunciation Studio's project-level setting. The preview worker and full generation both call `_effective_pronunciation_dictionary(state)`; global OFF returns no substitutions, and global ON filters to individually enabled entries.
- PROD-09: Production's BGM/Cues master switch uses the existing Sound Design save path after `flushSoundDesignState()`. Production preview and full generation consume the project's saved mode, track strategy, explicit chapter assignments, fixed cue paths and saved mix values. The existing Same BGM / Chapter-Based / Voice Only rules are preserved; no layered mix or silent book-default fallback was introduced.
- GEN-06: Production preview now uses the saved effective narrator, the same saved pronunciation state and the existing native Sound Design renderer. Full generation uses the same saved project settings through `GenerationManager`. Existing Stage 4 Sound Design preview tests continue to cover Voice Only, Same BGM, Chapter-Based no-fallback, custom chapter track selection and cue behavior.

### Requirement status at this source checkpoint

- PROD-08 — CODE CHANGED — NOT VERIFIED; the saved toggle path exists and the new regression checks global OFF. Full ON/OFF + individual-entry runtime verification remains.
- PROD-09 — CODE CHANGED — NOT VERIFIED; saved Sound Design flush/master switch and preview/final state handoff are present. Full mode/cue audio matrix remains.
- PROD-15 — CODE CHANGED — NOT VERIFIED; saved chapter selector, selected-chapter synthesis, output ownership and chapter-ID Save validation are implemented. Exact-head CI and Windows playback/download/project-switch acceptance remain.
- GEN-06 — CODE CHANGED — NOT VERIFIED; saved narrator and effective configuration paths are aligned in source. Scenario-matrix CI and real preview/final audio comparison remain.
- Existing PROD-05/06/07 work and #2114/#2115 fixes are preserved; they are not restarted or rewritten.

### Exact-head verification and release gate

The Build Windows App workflow includes pushes to `stage-5/**`; commits with `[artifact-checkpoint]` also request the package job. This ledger update is being committed as the matching-candidate artifact checkpoint so the workflow can run the regression suite and Windows package from one exact SHA.

The GitHub connector available in this session can fetch commit metadata, job details when a run ID is known, and PR-triggered commit runs, but does not expose the list of push-triggered workflow runs. Therefore the new candidate's Actions run number, job result, test count, installer/portable artifacts and artifact hashes must remain **PENDING** until they are visible in GitHub Actions or supplied by the user. No passing status is presumed.

Installed Windows acceptance also remains pending: select each preview duration, generate real selected-chapter audio, listen to narrator/character voice, pronunciation and BGM/cue behavior, play/pause/stop/replay, save/download the preview, switch projects/chapters during generation, and confirm the full-book generation scope is unchanged. Do not close Step 5.2 or begin Step 5.3 until the exact-head automated/package checkpoint and required runtime acceptance are recorded.


## 28. Step 5.2 final backend fail-closed correction — 3 November 2026

Two further exact-scope safeguards were added after the first preview/parity candidate:

- Commit `dba16d05349617d2eb4a45186dcc3feb0999b0d2`: `_production_preview` now discards caller-supplied `text`, transient `provider`/`voice_id`, projectless-preview allowance and pronunciation-bypass flags. It explicitly forces the selected saved chapter path, saved effective narrator, character-cast routing, effective saved pronunciation processing and native Sound Design renderer. The Sound Design renderer itself continues to apply the persisted master/mode/strategy; Voice Only therefore remains voice-only rather than bypassing the saved setting.
- Commit `a31387d42a3fd4a3ab5be502b7d2ed947c9ddad5`: the regression now deliberately sends untrusted whole-book text and false character/pronunciation/sound flags, then asserts that Production Preview removes/overrides those values and uses the saved production inputs.

This closes the backend loophole where a malformed or future UI request could accidentally preview caller-supplied text or skip a saved production setting. It also preserves the strict chapter-only synthesis requirement. Full suite and packaged Windows verification for this exact candidate remain pending.

Implementation/test candidate before this ledger checkpoint: `a31387d42a3fd4a3ab5be502b7d2ed947c9ddad5`. The following ledger commit is the matching `[artifact-checkpoint]` push and should be treated as the exact workflow candidate once its SHA is confirmed. A green result, test count and artifacts must be recorded only after the Actions run is inspected.


## 29. Step 5.2 request-time chapter identity guard and single final verification candidate — 3 November 2026

Additional correction after reviewing the project/chapter-switch race:

- Commit `2bdb88840662e9b18143dfb5cc0eb5819a9aa85a`: the Production backend validates an optional request `chapter_id` against the stable ID on the currently saved chapter before starting synthesis. A stale selector now fails before creating an audio job.
- Commit `50d519193609bb5c3f9d025f744114ff87b7eff7`: Production Preview sends the selector's stable chapter ID in its request.
- Commit `4cf063dccb5a586242dabc7b69d0b640c82891a1`: regressions verify that the UI passes the ID and the backend rejects a stale ID before the preview synthesis handler can be invoked.

### Final candidate preparation

All code corrections and regression changes for the identified Step 5.2 scope are now complete in source. This checkpoint consolidates the branch into one final matching candidate so its result, once visible, supersedes any older pending/superseded run.

The Build Windows App workflow uses a per-branch concurrency group with `cancel-in-progress: false`; multiple rapid pushes may therefore leave one run active while older pending runs are superseded by the newest pending commit. Do not interpret a cancelled/superseded pending run as a code failure. The authoritative result is the run that checks out this final candidate SHA.

The GitHub connector in this session does not expose the repository's push-triggered workflow-run listing or run dispatch. Its commit-run operation only returns pull-request-triggered runs. Therefore, after this checkpoint is pushed, exact run number/ID, job status, cancelled/failed job list, test count and package artifact metadata still must be read from the Actions run. The combined commit-status endpoint currently returns no status rows; that is not proof of success or failure.

### Step 5.2 final verification matrix

Required exact-candidate checks:
1. Premium V2 JavaScript syntax validation.
2. Isolated native Qt preview-lifecycle regression.
3. Full regression suite including Stage 2 Sound Design/Music Library, Stage 4 preview assembly, and the new Stage 5 preview parity/identity tests.
4. Windows packaged application build and existing package/installer integrity checks.
5. Confirm both `Ryu-Audiobook-Portable` and `Ryu-Audiobook-Installer` artifacts and their SHA-256 manifest are generated for the exact successful run.
6. Record the exact passing run ID, run number, head SHA, per-job status, test count, artifact IDs and hashes.

Installed-Windows runtime acceptance is still an external/hands-on gate: play the actual chapter preview at 10/30/60/90 seconds; test global pronunciation ON/OFF and individually disabled entries; test Same BGM, Chapter-Based BGM, Voice Only and opening/transition/closing cues; confirm playback, stop/replay, cancel and Save As; change projects/chapters during preview and confirm stale audio is blocked; compare the Production preview's saved narrator/configuration to a full-generation test. Do not claim these listening tests were executed by CI.

**Current closure rule:** keep PROD-08, PROD-09, PROD-15 and GEN-06 at `CODE CHANGED — NOT VERIFIED` until the exact-candidate CI/package evidence and runtime acceptance are recorded. Do not open Stage 5.3 before those gates pass.


## 30. Full Actions history audit and #2130 regression correction — 3 November 2026

The push-triggered workflow history was queried directly and each failed run's test job was inspected. This replaces the earlier incomplete statement that push-run details were unavailable.

### Successful packaged checkpoints retained

- #2107, run ID `41562699194`, commit `6ef7dea5c028ba477d86511b353ad03583dfe44`: tests and build both passed; portable, installer and SHA-256 manifest artifacts were uploaded.
- #2109, run ID `41566844270`, commit `97408889a44b58a508826c269e5872cfcaa16cfa`: tests and build both passed; portable, installer and manifest artifacts were uploaded.
- #2114, run ID `41576361204`, commit `c1e362d3fa3829e4ac51222e61a68440523a9c4f`: tests and build both passed; the FFmpeg runner import correction was packaged.
- #2115, run ID `41576648463`, commit `c2434ce3c1e0d69e9e1bc56dc707d24c289b3acd`: tests and build both passed. Test job completed with 1,091 tests in 51.872 seconds. Frozen Windows app, bundled voice assets, packaged Sound Design/Music Library acceptance, installers, portable ZIP and SHA-256 manifest completed. The user-imported cue preservation correction is in this checkpoint.

#2115 artifact references:
- Portable `Ryu-Audiobook-Portable-2115`: artifact ID `13206290064`, 1,367,555,427 bytes.
- Installer `Ryu-Audiobook-Installer-2115`: artifact ID `13206250054`, 883,752,754 bytes.
- SHA-256 manifest `Ryu-Audiobook-Release-SHA256-2115`: artifact ID `13205930319`, 774 bytes.

### Failed runs and root causes

- #2100 and #2103: early job-monitor refactoring broke existing polling source contracts and Production job-control assertions. The refresh public signatures were restored, the Production full-job ID was kept separate, and the controls' tests were updated. #2106's regression-only run passed 1,082 tests; #2107 then passed the packaged checkpoint.
- #2108: four test failures from missing `production.preview.save` capability advertisement, stale saved Sound Design/pronunciation state at preview start, and outdated Stage 2/Stage 4 integration test contracts. The capability and save/refresh hand-off were corrected before #2109's successful packaged checkpoint.
- #2111: 9 errors and 2 assertion failures from selected-chapter Sound Design renderer compatibility, projectless preview fixtures and Voice Studio versus Production Save As expectations. The renderer was made to use captured chapter context when no active-project accessor exists; cue/mix status and format-specific save tests were corrected.
- #2112: four errors because the WAV-to-AAC/M4A branch still needed the assembler `_run` helper in its local import list. #2113 then isolated the missing import defect; #2114 added it and passed packaging.
- #2116 and #2118: the Production-owned saved chapter selector changed the intended contract, but older Stage 4 tests still asserted Chapter Studio selection and the old preview callback.
- #2125 and #2126: the same three stale Stage 4 assertions remained; quick subsequent pushes cancelled the next queued run.
- #2130, run ID `41589494084`, exact head `c2c1f66801c5551530afccfb3a915325d11cc4a6`: JavaScript syntax check passed, isolated Qt lifecycle regression passed, then 1,100 tests ran with 3 failures and 1 error. The build job was skipped because the tests job failed. The failures were:
  1. stale-completion test expected the old `profileName:name` callback rather than saved `previewProfileName`;
  2. selected-chapter backend contract fixture expected the former Chapter Studio-only wording/payload;
  3. selected-chapter source contract expected `window.ryuPremiumSelectedChapter` rather than the new Production-owned selector;
  4. the new Stage 5 saved narrator test exposed that the backend validated a stable chapter ID but did not forward it into the preview worker payload.

### Final fixes after #2130

- Host commit `37102e4ba7557aa55448539e3971e27eff7870e1`: forwards the validated stable `chapter_id` to the Production preview worker job.
- Host commit `ba49f5b687459b654910b607c51f17cf68087209`: retains an actionable chapter-selection error message compatible with the public contract while keeping Production-owned saved chapter selection.
- Test commit `d67c79ffda73b1d1a01eba82f950f87af7285610`: rewrites the obsolete Stage 4 assertions to validate the Production-owned chapter selector, saved narrator resolution, stable chapter-ID handoff, stale-completion rejection and the new Production callback. The selected-chapter backend fixture now verifies the saved narrator and forced project settings.

### Cancelled/superseded runs

Runs #2101, #2102, #2104, #2105, #2117, #2119, #2120, #2121, #2123, #2124, #2127, #2128 and #2129 ended as cancelled while the same branch advanced. Their cancellation is attributable to rapid subsequent pushes/branch concurrency; the final verification candidate must supersede them. They are not reported as passing or as source-code test failures.

### Exact candidate verification gate

The next `[artifact-checkpoint]` must run on the final consolidated SHA after commits `37102e4`, `ba49f5b` and `d67c79f`. The expected run must have both `tests` and `build` jobs successful; test count, run ID, portable/installer/manifest artifact IDs and exact SHA values must be recorded from that run. A test pass with a skipped build is not sufficient to close Step 5.2.

Installed Windows runtime acceptance (real chapter audio listening, duration matrix, pronunciation/BGM/cue matrix, playback/cancellation/save and project-switch isolation) remains distinct from CI and must be completed before declaring those user-facing flows runtime-verified.


## 31. #2136 complete package baseline; #2141 packaged-selector harness correction — 3 November 2026

### Completed exact-head package checkpoint

Run [#2136](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41591534180) completed successfully on exact commit `bb5d3b2b8a803e79189ba972556dd05725ec480a`:

- Tests job passed: **1,100 tests** in 52.450 seconds; JavaScript syntax and isolated native Qt lifecycle checks passed.
- Windows build job passed: frozen app build, frozen application verification, bundled voice assets/critical modules, packaged Sound Design/Music Library UI acceptance, core installer, functional HTML installer, logo/hash verification and Microsoft Defender scan.
- Artifacts uploaded:
  - Portable: `Ryu-Audiobook-Portable-2136`, ID `13210739270`, 1,367,568,913 bytes.
  - Installer: `Ryu-Audiobook-Installer-2136`, ID `13210739232`, 883,680,924 bytes.
  - Manifest: `Ryu-Audiobook-Release-SHA256-2136`, ID `13210484613`, 780 bytes.
- Build-output SHA-256:
  - HTML installer `Ryu's Audiobook Setup.exe`: `232dca8055c0b3b7fdc5772de92d9cf9e0840c6bd3cfbe0f656499870922aa5`.
  - Core installer `Ryu's Audiobook Core Setup.exe`: `cddf4fc74c41bc3b58fd4b6cb733c8b1719b9735d5adeb24ab34f4c373d8842c`.
  - Portable main application EXE: `19095063cdf235175b9c42ede349b5fa7492fed9e64c7031743a266b1195ffa8`.
- Artifact ZIP digests: installer `1ce778b208c33ad828553a7cd89fba10ae56a5a1cb135e8650076513ca014793`; manifest `e9b8521aac428bddf9c7d66de62d170fcf8c2da9ccc2875a2a496ef37eebb0eb`; portable `e174e242d314d24523e06094ef7297f1b02c279d3f9369cab2b73d43f8d62b31`.
- Public release publication was skipped by workflow policy; the verified build artifacts are uploaded and available.

This is a successful exact-head package baseline, but it predates the additional Production chapter-preview UI smoke added in the #2141 candidate. It does not by itself close the Stage 5.2 Production Preview runtime acceptance.

### #2141 failure root cause

Run #2141 on commit `5d31633e013b73b68c04a973329c9ee6ac453b17` passed its full regression job and the Windows frozen build, but failed the packaged UI acceptance before it started Production Preview synthesis:

- The acceptance manually selected Chapter Two and then waited for `#productionPreviewChapter` to say “Chapter 2”.
- That element is intentionally the preview-job monitor's chapter label and remains at its idle selection text until a job exists. The real selector change handler instead updates `#productionPreviewStatus` with “Chapter 2 selected. Generate a new preview for this chapter.” and updates the selected option.
- The cancellation test contained the same incorrect wait for Chapter Three in the job-monitor element.
- This is an acceptance harness selector/monitor assumption error, not evidence that the Production backend rejected the selected chapter or failed synthesis. The run never reached the chapter preview start.

### Corrective changes in the next single checkpoint

- The packaged acceptance now waits for the real Production selector value, selected option title and the pre-job selection status text for both Chapter Two and Chapter Three.
- A regression contract asserts the selected-chapter status is exposed by the selector handler before a preview job exists.
- Workflow concurrency is now keyed by both branch ref and `github.run_id`, so a later push cannot replace an earlier pending run in the branch queue. `cancel-in-progress` remains false. This trades queued-run supersession for independent run execution and preserves an auditable result for each pushed candidate.
- These changes are committed together as one checkpoint; its own `tests` and `build` jobs are the deciding verification.

### Cancelled-run reconciliation

Runs #2137–#2140 and earlier #2134/#2135 etc. were cancelled/superseded while the same branch's one-pending-run concurrency group was receiving newer commits. Although `cancel-in-progress: false` prevented killing the currently running job, GitHub's per-group pending slot replaced earlier pending runs when newer pushes arrived. These cancelled runs did not all represent code failures; the latest exact candidate is what must be judged. The new per-run concurrency key removes that pending-slot replacement behaviour.

### Step 5.2 current decision

Do not move to Step 5.3 on the strength of #2136 alone. Require the next exact-head checkpoint to pass all 1,100+ regression tests, the real frozen Production Preview generation/playback/control/cancellation acceptance, and the full installer/portable/manifest package. Then record the matching run ID, SHA, test count, artifact IDs and hashes. The installed-Windows preview/final audio listening and full duration/pronunciation/Sound Design matrix remains a separate acceptance item if not exercised on the target user's installed hardware.


## 32. Production selector pre-job status preservation — 3 November 2026

The #2142 regression job passed 1,101 tests, including the selector harness contract, while its Windows package job began. Reviewing the actual UI function revealed one more mismatch: the selector change handler wrote a chapter-specific status, then `syncProductionPreviewControls()` immediately replaced it with a generic idle message when there was no preview job. The selected chapter state itself was correctly updated, but the user-facing selected-chapter status was not preserved.

The follow-up source correction makes `syncProductionPreviewControls()` render the selected chapter's name/number while idle, retaining a neutral prompt when no saved chapter is selected. The contract test now verifies both the selector's selected state and the pre-job status rendering. The #2142 workflow is not cancelled; the per-run concurrency key keeps it independently auditable while this corrected head is verified.


## 33. #2142 packaged UI failure and #2143 exact-head regression pass — 3 November 2026

### #2142 — packaged selector status regression reproduced

Run [#2142](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41605043619) on commit `e8940efe95967e2c508c71bc03604711066a3952`:
- Tests job passed: 1,101 tests, JavaScript syntax and isolated Qt lifecycle regression all passed.
- Build job passed its installer syntax, frozen app build, frozen EXE verification and bundled voice asset/module verification.
- Packaged Sound Design/Music Library acceptance passed all preceding Stage 2 / metadata / project-switch checks, then failed at the new Production Preview selection step: `Timed out waiting for Production-owned Chapter 2 selection`.
- This was the known idle-status overwrite: the selector stored the selected chapter but `syncProductionPreviewControls()` rewrote the selected-chapter status to a generic prompt. It failed before preview synthesis, so it is not evidence of a preview worker/synthesis failure. The correction is in #2143's source commit.

### #2143 — final source regression pass

Run [#2143](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41606123216) on exact source commit `b8966283e7bc5686a8c8f934683a0cf5ff3b301c`:
- Tests job passed: **1,101 tests in 56.537 seconds**.
- Frontend JavaScript syntax validation passed.
- Isolated native Qt lifecycle regression passed.
- Build job was skipped because the commit was not labelled `[artifact-checkpoint]`. This is a workflow condition, not a code failure.

The only source change after #2142 is the Production Preview idle-status preservation and its regression contract. The following artifact-checkpoint commit is documentation-only and should be packaged against this verified source state.

### Exact package candidate to close Step 5.2

The current commit explicitly includes `[artifact-checkpoint]` to force the Windows build job. Its exact-head run must pass:
1. 1,101+ full regressions, JavaScript syntax and native Qt lifecycle;
2. frozen Windows app build, verification and bundled model/voice assets;
3. packaged Production chapter preview: saved Chapter Two M4A generation and measured duration, saved Voice Only configuration, real Play/Pause/Stop/Replay, and cancellation of the separate 90-second Chapter Three preview;
4. existing packaged Sound Design/Music Library and metadata/project-switch acceptance;
5. HTML/core installer, portable ZIP, release SHA-256 manifest, logo and Defender checks, artifact uploads.

No older run is to be cancelled or reported as a failure merely because a later commit exists. Workflow concurrency is now unique per run ID; all runs remain independently auditable.

Step 5.2 remains open until that exact-head packaged acceptance succeeds. User-machine real-audio listening and preview/final pronunciation/BGM matrix remain separate manual acceptance items and must not be represented as completed by CI alone.


## 34. #2144 packaged Production Preview failure — root-cause fixes — 3 November 2026

### Run evidence

- #2142 passed its 1,101-test regression job and frozen app checks, then failed before preview synthesis because the packaged test waited for the job-monitor chapter label before a job existed. The selector assertion was corrected.
- #2143 passed 1,101 tests in 56.537 seconds; it was regression-only, so the artifact build was skipped by workflow policy.
- #2144 passed its 1,101-test job, frontend syntax check, native Qt lifecycle test, frozen app build, frozen EXE check and bundled voice verification. Packaged Sound Design/Music Library acceptance reached Production Preview, the backend job completed with a measured AAC/M4A result, but the UI did not reach its ready state and the installer/package steps were skipped.

### Corrections in this commit

1. Added the missing `#productionPreviewStatus` status element to the dynamic Production Preview monitor. The adapter previously attempted to update this node without creating it, so the packaged acceptance could never observe the Ready state.
2. Replaced cached `window.ryuPremiumActiveProject` completion checks with the native `project.get_active` response, and normalized Windows path separators/case before comparing active/request/job project ownership.
3. Stable chapter IDs are now compared when both request and job expose an ID. For legacy/imported chapter rows without a frontend ID, the worker's stable ID is adopted before Save; project folder and chapter number ownership remain mandatory.
4. Save uses the native active project and the same optional-ID matching rule, preserving the backend job's stable chapter identity.
5. The packaged acceptance now prints a diagnostic snapshot of UI status/button states and the completed job's project/chapter/result whenever the Ready predicate times out. This turns any remaining issue into a specific assertion rather than an opaque wait.

The six-second cue-import rejection and injected cue/manifest/metadata save failures in #2144 are deliberate negative acceptance cases. They were not the run's failure cause; the earlier packaged Sound Design, metadata and project-switch checks passed.

The next exact-head run must pass all regressions, frozen app build, existing packaged Sound Design acceptance, Production Preview chapter-only M4A/playback/cancellation acceptance, installer packaging, release hashes, Defender checks and portable/installer/manifest upload. No Stage 5.2 requirement is marked complete based on source changes alone.


## 35. #2145 regression result and stale contract correction — 3 November 2026

Run #2145 on exact candidate `46bfaf3bd8cd04b878e2136f7d0840e1b95fafbe`:
- Frontend JavaScript syntax validation passed.
- Isolated native Qt lifecycle regression passed.
- Full regression run: 1,102 tests, 1 failure.
- The only failure was `test_generate_preview_ignores_stale_completion_after_newer_request`, which still asserted the superseded source string `activeFolder!==productionPreviewRequestProjectFolder`. The current implementation deliberately resolves the native active project through `project.get_active`, normalizes active/request/job paths, compares normalized folders and chapter number, then compares chapter IDs when both are available.
- This was a stale source-contract assertion, not a runtime or ownership-guard failure. The test now asserts the native project lookup, normalized path comparisons, chapter-number guard and optional stable-ID comparison used by the actual handler.
- No application code was changed in response to this test failure.

The next artifact checkpoint is the deciding verification for this correction. Require its test job to pass and its Windows build job to pass the packaged Sound Design/Music Library and Production Preview generation/playback/cancellation acceptance before closing Stage 5.2.


## 36. #2146 AAC playback diagnosis and final Production Preview acceptance correction — 3 November 2026

### Run history reconciled

- #2141 (`5d31633`) passed the 1,100-test regression suite but failed in packaged Sound Design/Music Library acceptance when Production Preview could not reach playable/ready status.
- #2142 (`e8940ef`) passed 1,101 tests and frozen app/voice checks, then failed because the packaged test checked a job-monitor chapter label before a preview job existed. The selector/status timing was corrected.
- #2143 (`b896628`) passed 1,101 tests in 56.537 seconds; it was a regression-only run and the build job was skipped by the workflow's artifact-checkpoint policy.
- #2144 (`a7a7137`) passed its 1,101-test job and frozen build checks, but packaged Production Preview did not become playable. Its status-node/ownership issues were corrected before the next attempt.
- #2145 (`46bfaf3`) failed one regression only because a source contract still expected the superseded `activeFolder!==productionPreviewRequestProjectFolder` expression. The current native `project.get_active` and normalized ownership implementation is intentional; that stale test was corrected without changing runtime code.
- #2146 (`991bd01`) passed 1,102 tests and all frozen app/voice checks. Packaged Sound Design/Music Library, metadata, and project-switch acceptance passed. The Production Preview backend then successfully generated Chapter Two M4A (measured 7.64s) but the UI player emitted `Playback error`; the result's `file_url` pointed to AAC/M4A and the embedded Qt WebEngine reported that no supported source could be found.

### Actual cause and correction

The failure was not the M4A encoder or the chapter worker. The generated M4A existed, had a valid measured duration and correct chapter/project identity, but the packaged HTML audio player did not have an AAC decoder available. The production save path correctly needs the M4A asset, so replacing the M4A output or weakening the playback acceptance would be wrong.

- Commit `9cd64ba0c0bdab5b75c5e2471504ff0ff523fbbf`: `_preview_worker` now keeps `result.output_path` as the authoritative M4A and uses a per-job PCM WAV copy as the browser playback `file_url`. It runs FFmpeg to decode the M4A to stereo 44.1 kHz PCM, verifies the WAV file and ensures duration matches within 1.5 seconds. The WAV path is retained for playback and removed on cancellation/failure; `production.preview.save` continues to validate/copy the M4A output.
- Commit `d050f726583352b054705b47581c03f61f6d103f`: packaged acceptance verifies separate M4A save output and WAV playback URL.
- Commit `caaec6438da56e701a1ca2a27e47f5184b9b2e2b`: regression contract covers the output/playback split and PCM conversion.
- Commit `573a7a5be4e22e86383d1ffe5c81556e446fa85c`: saved Chapter Two fixture now includes sufficient text for real 30/60-second duration targets.
- Commit `24fd8f92226fae060b1ee074bad345edc80f36c6`: packaged acceptance now runs real 30- and 60-second preview generations in addition to the 10-second playback test; 90-second Chapter Three remains the live cancellation test.
- Commit `e3470540f03fec7cc98037f8bb3f43964b4c37f5`: adjusts the source assertion to check the actual `_run([` FFmpeg helper invocation.
- Commit `25d8af7deb79367581dfe577dda17625a265a3ad`: initializes the playback cleanup path before synthesis/conversion so error cleanup cannot throw when no playback copy exists.

### No-cancellation workflow policy

The current workflow has concurrency group `ryu-audiobook-windows-build-${{ github.ref }}-${{ github.run_id }}` and `cancel-in-progress: false`. Each run has a distinct concurrency key; a later push therefore does not supersede or cancel the prior pending run in the same branch. Earlier cancellations #2137–#2140 and others occurred before this isolation change. Future completed/failed runs remain independently auditable.

### Final exact-head verification candidate

The following `[artifact-checkpoint]` commit is the authoritative candidate. It must pass the full test job, JavaScript and Qt lifecycle checks, frozen Windows packaging, Stage 2 Sound Design/Music Library acceptance, Stage 5 Production preview M4A/WAV generation, duration matrix, Play/Pause/Stop/Replay, 90-second cancellation, installer, SHA-256, Defender and artifact uploads. The exact passing run ID, head SHA, test count, artifact IDs/sizes and SHA-256 values will be appended after verification.

Stage 5.2 remains open until that exact-head packaged run succeeds. The still-open PROD-14 and GEN-01–GEN-05 rows remain in the later full-generation/job-history/recovery scope; they are not being marked complete by this preview step.
