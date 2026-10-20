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
- Added a separate persisted `skip_for_generation` flag and contextual skip/unskip action. Book generation now excludes flagged chapters without deleting their text and records intentional exclusions separately from empty chapters.
- Find/replace, undo/redo, re-detection protection and Stage 2 runtime acceptance remain open.
