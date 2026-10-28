# Stage 2 Plan — Import Integrity, Text Cleanup, and Chapter Structure

**Working branch:** `stage-2/import-integrity`  
**Baseline:** Stage 1 merge commit `1fbb5e9ae897315bb5a5ca96d0a4ef68178f1e2a`  
**Rule:** preserve the approved Premium V2 UI. Change backend behavior and tests; do not redesign the interface or report simulated completion.

## Goals and exit criteria

### 2.1 Source import integrity
- [x] Exercise TXT (including UTF-8 BOM), EPUB reading order/spine, PDF searchable-text quality, and DOCX paragraphs/tables using reproducible fixtures.
- [x] Publish a project only after source staging, project metadata, chapter JSON, and a reload verification succeed.
- [x] Confirm failed source copy, metadata/chapter write, and missing-source validation do not publish a partial project; automated regression tests cover these failure paths.
- [ ] Verify duplicate import guidance, cancellation, retry, and failure status in the packaged Windows app.

### 2.2 Cleaning without story loss
- [x] Test known ebook watermarks/page counters and repeated boilerplate against normal narrative, URLs, punctuation, dialogue, and Unicode with fixtures.
- [x] Cleanup is conservative for covered fixtures and reports removed lines/counts; expand real-book fixture coverage during acceptance.
- [x] Confirm reflow preserves paragraph/dialogue/heading boundaries and hyphenated line wraps with regression fixtures.

### 2.3 Chapter detection and editing
- [x] Automated fixtures cover numbered/Roman chapters, prologue/epilogue, preambles, books without headings, empty-heading boundaries and named/compound slash-title/Part headings. Continue adding real-book fixtures during acceptance.
- [x] Verify covered chapter boundaries preserve body text; project save normalizes chapter numbering to current order, and regression tests verify reordered chapters reload in that order.
- [ ] Persistence regression now covers chapter title/text edits, reorder, dialogue assignments, review status, and skip-for-generation after reload. Still verify all editor operations (add/delete/merge/split/clean/find-replace/undo-redo) in automated or packaged-app tests.
- [x] Re-detection now requires an explicit before/after preview and a matching saved-data fingerprint before applying; preview-only calls do not mutate the project, and stale/missing preview tokens are rejected by regression tests.

### 2.4 Automated and Windows acceptance
- [x] Run the complete unittest regression suite and Windows package/installer pipeline on the final Stage 2 branch head; Run #877 passed on commit `05e03c14637bb4ff3fe8514a50101ebde0d2ab4b`.
- [ ] Inspect failures and fix them before merging.
- [ ] On a target Windows install, import one fixture in each supported format, edit and save chapters, restart/reopen, and compare text and chapter counts.
- [ ] Record any Windows-only acceptance that cannot be performed in cloud CI as an explicit release gate.

## Current validation on `fix/native-ui-font-scale-learning-ai`

- Run #1464 passed on tested code commit `579c378ae81ab9c06e7c68feae5485574f3f02cc`: 732/732 tests passed, with installer, portable app, SHA-256 manifest, Defender scan, and test evidence uploaded. See [Stage 2 evidence](STAGE_2_IMPORT_CHAPTER_EVIDENCE.md).
- Follow-up commit `a2666867425ab0c0710b5fd34417ae608280fb62` clears number-keyed chapter undo/redo stacks after structural edits so old snapshots cannot be applied to a different chapter after renumbering.
- Follow-up commits add deterministic editor-operation tests for text/title and dialogue-assignment integrity, delete renumbering, reorder metadata, merge/split offsets, invalid split safety, history invalidation, Unicode Find/Replace offsets, and redetection preview/stale-fingerprint behavior. The latest complete checkpoint run must pass before these tests are counted as verified.
- Structural history invalidation is a safety guard, not full cross-structure undo. Undo/redo remains scoped to the active chapter's text-edit history.

## New automated coverage added for the current checkpoint

- Chapter history is invalidated after structural chapter mutations to prevent stale per-number undo snapshots from being applied to a different chapter.
- Case-insensitive chapter Find/Replace uses match offsets in the original string, avoiding Unicode lowercasing length changes.
- Re-detection requires a before/after review and an unchanged-source fingerprint; preview is non-mutating, and missing/stale fingerprints are rejected.
- Import edge tests cover duplicate guidance (browse and dropped file), staging cleanup, unsupported/empty file rejection, cancellation before publishing, and recoverable extraction failure without source loss.

## Remaining Stage 2 gates

- [ ] Latest checkpoint CI run passes on the current branch head, including all regression tests and (for the artifact-checkpoint commit) Windows packaging.
- [ ] Extend automated/packaged acceptance for import cancellation timing, duplicate import, unsupported/empty/damaged files, retry/error states, and cleanup on failure.
- [ ] Exercise chapter add/delete/move/merge/split/clean/find-replace/undo-redo through the packaged UI; core operation tests alone do not prove the UI interaction contract.
- [ ] On the target Windows install, import TXT, EPUB, searchable PDF, and DOCX; edit/save/reopen, compare source/body text and chapter counts, and capture exceptions/logs.
- [ ] Record real-book outcomes and any limitations; do not claim zero-defect or full interactive acceptance from CI alone.

## Work started in this branch

1. Added transactional project creation: copy and write into a private staging folder, reload-verify the project, then publish the completed folder by rename. On errors, staging is removed.
2. Added import integrity regression tests for BOM handling, chapter boundary separation, watermark cleanup, persistence of review/skip flags, and failed source-copy cleanup.
3. Added this branch to the Windows workflow trigger so these changes receive the full build/test/package pipeline.

## Current status after Run #871

Run #877 passed on final Stage 2 commit `05e03c14637bb4ff3fe8514a50101ebde0d2ab4b`, including added coverage for edited/reordered chapter persistence, invalid-source rejection, and repeated boilerplate cleanup. PR #17 was merged as `9aa1ba5cc9be0808d596c1e2c0618584433c9917`. Automated implementation and package gates passed; packaged-Windows acceptance remains explicitly outstanding.

## Known limitations / risk boundaries

- CI can validate parser fixtures and package behavior, but it cannot prove correct extraction for every real book or test Windows UI interaction on the user's specific PC.
- Scanned/image-only PDFs are not automatically OCR'd. The import should block or clearly diagnose sparse extraction rather than create a misleading partial audiobook.
- Existing projects use JSON/filesystem persistence; this stage does not silently migrate them to SQLite.
- Stage 1 hardware-specific freeze/crash validation remains a separate target-PC acceptance item; Stage 2 proceeds in parallel with that outstanding evidence and does not mark it resolved.


## 2026-10-24 reliability addendum

Chapter selection flushes a queued autosave before navigation and blocks selection if save fails. Job polling and catalogue/list refreshes are guarded against overlaps/stale replies. Generation completion refreshes output metadata and History without rebuilding the Chapter editor. Target-Windows import/edit/save/reopen and real audio acceptance remain open.
