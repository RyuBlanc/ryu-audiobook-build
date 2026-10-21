# Update Log — Premium V2 Integration

## 2026-10-20 — Stage 1 gap audit and function mapping

### Verified baseline
- Audited branch `fix/import-qa-speaker-hover-hardware`, open PR #15, head commit `eca9cf1a8330e2dcfce697f66233a73740e25ae0`.
- Verified GitHub Actions Run #731 completed successfully on that commit: 308 automated tests reported passing and installer/portable artifacts uploaded.
- Verified the user-supplied Premium V2 HTML matches the Git blob of `assets/frontend/ryu_audiobook_premium_v2.html` at the audited commit by recomputing the Git blob SHA.
- Static HTML inventory: 15 page sections, 384 form/button controls and no duplicate initial DOM IDs.

### Changes made
- Reconciled the screen map and backend API map against the real adapter/host instead of treating the intended bridge contract as implemented.
- Added `docs/STAGE_1_GAP_REGISTER.md` with priority, evidence, closure criteria and owning roadmap stage.
- Updated the integration test report, database-schema status, update log and `KNOWN_LIMITATIONS.md` to distinguish source facts, prior CI evidence and pending Windows manual acceptance.
- Fixed capability-map drift by advertising `chapter.split` as available because its allow-listed host handler and adapter call already exist; added a regression assertion.

### Confirmed limitations kept explicit
- Project creation command is unavailable outside the import flow.
- Hardware telemetry is not connected; performance values must remain unavailable/unmeasured.
- Per-line AI speaker suggestion/assignment is not persisted.
- Secure provider-specific credential storage and Premium cloud voice candidate endpoint remain unavailable.
- Custom storage roots, bulk pronunciation test result persistence, complete per-model actions, SQLite migrations and durable playback-position persistence remain open.
- Job rows persist to JSON and unfinished rows are marked recoverable/failed after restart; `history.list` currently reflects job records rather than an independent history service.

### Acceptance state
- This stage is an audit, mapping and capability-contract correction, not a claim of complete feature parity.
- The new audit commit's CI run must be checked separately from Run #731.
- The full Windows end-to-end workflow and visual comparison remain pending.
### Stage 2 — Chapter cleaning integration
- Routed Premium V2 Clean Text through the real `chapter.clean` bridge operation instead of browser-only whitespace substitutions.
- Switched the host handler to the existing `clean_import_noise` service so explicit cleanup can remove known URL/watermark/report/page-number noise and reflow text.
- Returned a `removed_count` and updated the status message to make cleanup transparent to the user.
- Added/strengthened integration-contract assertions. Existing parser tests already cover common import-noise patterns; Windows end-to-end acceptance remains pending.


## Stage 2 — import integrity checkpoint

- Added exact-content duplicate detection before an import job is created. The backend hashes the selected source and compares it against preserved source files in existing local projects; a duplicate receives an actionable error naming the existing project rather than silently creating a second copy.
- Import completion data now includes the preserved source-file path and an explicit chapter-boundary review warning. This is a truthful review reminder, not a claim that automatic chapter detection is perfect.
- Added integration-contract checks for duplicate detection ordering, source preservation and the import report fields.
- The approved HTML/CSS remains untouched. Stage 2 remains open pending parser/chapter fixture coverage and runtime acceptance for retries, malformed files, duplicate files and edit/save/reload behavior.


## Stage 2 — persisted chapter review state

- Added a backward-compatible `review_status` field to the chapter record with `needs_review` as the default for existing projects.
- Added the allow-listed `chapter.review` bridge command, which validates and saves `reviewed` or `needs_review` status into the project's chapter JSON.
- Connected the existing Review filter to the persisted status and exposed a contextual `review` action on the chapter list. The approved HTML file remains unchanged.
- Added static contract checks for bridge/capability registration, persistence, filtering and compatibility with legacy chapter JSON.
- Added a separate persisted `skip_for_generation` flag and contextual skip/unskip action. Book generation excludes flagged chapters without deleting their text. Corrected the stale empty-chapter contract test and ensured job progress, returned job data, and project state distinguish empty chapters from intentional exclusions.
- Find/replace, undo/redo, re-detection protection and Stage 2 runtime acceptance remain open.


## 2026-10-20 — Stage 2 chapter editor commands

- Added case-insensitive find and confirmed replace-all actions through the existing chapter-list contextual menu without changing the approved HTML layout.
- Added grouped chapter undo/redo, keyboard shortcuts (Ctrl/Cmd+Z and Ctrl/Cmd+Y or Shift+Z), redo invalidation after new edits, a 10-snapshot cap, and a 1,000,000-character limit to bound memory use on low-resource PCs.
- Added integration-contract coverage for the new editor actions. CI and real Windows edit/save/reload acceptance are still required; Stage 2 remains open.


## 2026-10-21 — Stage 2 import cancellation and diagnostics

- Added safe-boundary cancellation for import jobs and exposed Cancel in the existing background-job list for import only. Cancellation does not kill parser threads; it is honored after extraction or chapter detection and before project creation.
- Temporary drag/drop staging files are cleaned when the worker exits; the original user-selected file and any project source copy remain preserved.
- Added format-specific import extraction diagnostics with recovery guidance for PDF, EPUB, DOCX, and TXT errors. Retrying is explicit: fix the source or choose it again; there is no blind automatic retry.
- Added integration-contract coverage for the import cancellation and diagnostic behavior. Fixture-based chapter tests and target-Windows acceptance remain pending.


## 2026-10-21 — Stage 2 deterministic chapter fixtures

- Added repeatable chapter-detector coverage for preamble attachment, empty heading boundaries, plain-text fallback, and `Life.0` heading recognition.
- Added a filesystem round-trip test for manually edited chapter text, review status, generation exclusion, and dialogue assignments.
- Confirmed there is no Premium V2 re-detection command to overwrite chapter edits: importing runs detection only while creating a new project. Re-detection remains unavailable until a safe, explicit workflow can be designed without changing the approved UI.
- Runtime Windows acceptance for import cancellation, failure/retry, and edit/save/reopen remains pending.


## 2026-10-21 — Stage 3 explicit dialogue assignment

- Added an allow-listed `chapter.dialogue.assign` bridge command and persisted explicit speaker assignments to chapter data using original source offsets. Only saved characters/aliases can be selected; ambiguous or stale passages are rejected without mutation.
- Wired individual dialogue confirmation in the existing review modal to real saved cast records. Static confidence scores are not treated as evidence; bulk acceptance and prototype queue actions remain guarded.
- Added focused regression coverage for exact/whitespace-wrapped matching, stale text, duplicate occurrences, overlaps, reassignment, and multi-speaker compatibility. CI and Windows acceptance are pending.

## 2026-10-21 — Stage 2 import staging integrity

- Changed exact duplicate-import hashing to read files incrementally, avoiding a full in-memory copy of large source books during duplicate checks.
- Fixed an early-failure path where a duplicate drag-and-drop import could leave its temporary staging copy behind before a background worker existed.
- Added regression coverage for streamed hashing, cleanup of temporary drop files, idempotent cleanup, and preservation of user-selected source files outside the managed staging directory.
- Windows CI validation and manual import cancellation, duplicate, failure/retry, and edit/save/reopen acceptance remain release gates.

## 2026-10-21 — Run 810 regression failure diagnosis

- Run 810 executed 352 tests: all four new streaming/staging tests passed, while one static source-contract assertion failed because it expected the empty-bytes literal with single quotes and the helper uses equivalent double quotes.
- Corrected the assertion to match the actual source expression. Run 811 must pass before this patch is considered CI-validated; packaged Windows interaction acceptance is still separate.


## 2026-10-21 — Stage 3 assignment lifecycle hardening

- Added a persisted removal command for one saved dialogue-speaker assignment. Removal requires exact chapter number, source offsets, source text and a unique assignment record; stale text or ambiguous records fail without mutation.
- Added a Remove saved assignment action to the existing dialogue-review modal at runtime. The approved Premium V2 HTML source remains unchanged.
- Tightened dialogue-review rendering to match saved assignments only by validated source offsets, avoiding normalized-text fallback that could attach old assignments to repeated or edited quotes.
- Added regression coverage for exact removal, stale-source rejection, duplicate-record rejection, bridge registration and strict UI matching.
- Packaged Windows acceptance and end-to-end synthesis checks remain required before Stage 3 can be marked fully accepted. CI validation for this change is pending.


## 2026-10-21 — Stage 4 voice-preview integrity hardening

- Kept the selected saved voice profile and all supported preview targets (10, 20, 30, 45 and 60 seconds) flowing into the backend worker.
- Changed preview completion to fail closed if the generated audio has no measurable positive duration; a generated file without valid duration is no longer reported as a successful ready preview.
- Tightened the frontend ready-state gate: it requires a playable local file URL and a finite, positive measured duration. Missing/invalid output disables preview playback and leaves an actionable validation message instead of showing Ready.
- New preview requests stop any prior preview playback, disable Play while generation is running, and reset the visible progress bar before polling the real job status.
- Added regression tests for unmeasurable output duration and frontend ready-state conditions. Run 812 succeeded on the preceding Stage 3 commit; the new Stage 4 commit's CI result is still pending. Actual provider playback and duration acceptance on the target Windows machine remain required.


## 2026-10-21 — Stage 5 voice identity and cache integrity

- Added a dedicated narrator-profile identity to cast-aware generation signatures. The signature now covers the selected narrator profile's provider, model, backend, voice, language, prompts, seeds and synthesis controls instead of relying on the narrator voice label alone.
- Included character-profile synthesis settings plus SHA-256 digests of reference and anchor audio in the signature, so replacing a reference file in place invalidates incompatible cached chunks.
- Added regression tests for narrator-provider changes, cast prompt changes, reference audio replacement and missing-reference state.
- Run 819 passed on the Stage 4 integrity commit. Actual Windows preview acceptance remains outstanding; Stage 4 is CI-green, but its full manual exit gate is not yet signed off.
- Stage 5 CI status is pending until the combined source and test commit is built.
