# Stage 2 Plan — Import Integrity, Text Cleanup, and Chapter Structure

**Working branch:** `stage-2/import-integrity`  
**Baseline:** Stage 1 merge commit `1fbb5e9ae897315bb5a5ca96d0a4ef68178f1e2a`  
**Rule:** preserve the approved Premium V2 UI. Change backend behavior and tests; do not redesign the interface or report simulated completion.

## Goals and exit criteria

### 2.1 Source import integrity
- [x] Exercise TXT (including UTF-8 BOM), EPUB reading order/spine, PDF searchable-text quality, and DOCX paragraphs/tables using reproducible fixtures.
- [x] Publish a project only after source staging, project metadata, chapter JSON, and a reload verification succeed.
- [x] Confirm failed source copy, metadata/chapter write, and missing-source validation do not publish a partial project; automated regression tests cover these failure paths.
- [ ] Verify duplicate import guidance, cancellation timing, retry, and failure status interactively in the packaged Windows app (automated paths are covered, target-PC UI acceptance remains open).

### 2.2 Cleaning without story loss
- [x] Test known ebook watermarks/page counters and repeated boilerplate against normal narrative, URLs, punctuation, dialogue, and Unicode with fixtures.
- [x] Cleanup is conservative for covered fixtures and reports removed lines/counts; expand real-book fixture coverage during acceptance.
- [x] Confirm reflow preserves paragraph/dialogue/heading boundaries and hyphenated line wraps with regression fixtures.

### 2.3 Chapter detection and editing
- [x] Automated fixtures cover numbered/Roman chapters, prologue/epilogue, preambles, books without headings, empty-heading boundaries and named/compound slash-title/Part headings. Continue adding real-book fixtures during acceptance.
- [x] Verify covered chapter boundaries preserve body text; project save normalizes chapter numbering to current order, and regression tests verify reordered chapters reload in that order.
- [x] Automated regression coverage now exercises chapter title/text changes, deletion and renumbering, move payload retention, merge/split text and dialogue-assignment offsets, invalid split safety, Unicode-safe Find/Replace indexing, and invalidation of number-keyed undo/redo after structural edits. Full packaged-UI acceptance for all of these operations remains open.
- [x] Re-detection now requires an explicit before/after preview and a matching saved-data fingerprint before applying; preview-only calls do not mutate the project, and stale/missing preview tokens are rejected by regression tests.

### 2.4 Automated and Windows acceptance
- [x] Run the complete unittest regression suite and Windows package/installer pipeline on the current Stage 2 checkpoint: Build Windows App #1478 passed on commit `cbe8b41a46b1d5807699e67fbd54a5d1e698c6a0` (752/752 tests; package verification, Defender scan and artifact uploads passed).
- [x] Inspect and fix the failures found during checkpoint validation: updated the obsolete re-detection contract assertion and corrected CP1252/Unicode output handling in the Windows CI runner. #1478 passed after these corrections; no merge was performed.
- [ ] On a target Windows install, import one fixture in each supported format, edit and save chapters, restart/reopen, and compare text and chapter counts.
- [ ] Record any Windows-only acceptance that cannot be performed in cloud CI as an explicit release gate.

## Current validation on `fix/native-ui-font-scale-learning-ai`

- Run #1478 passed on tested commit `cbe8b41a46b1d5807699e67fbd54a5d1e698c6a0`: 752/752 tests passed, with installer, portable app, SHA-256 manifest, Defender scan and test evidence uploaded. See [Stage 2 evidence](STAGE_2_IMPORT_CHAPTER_EVIDENCE.md).
- Follow-up commit `a2666867425ab0c0710b5fd34417ae608280fb62` clears number-keyed chapter undo/redo stacks after structural edits so old snapshots cannot be applied to a different chapter after renumbering.
- Follow-up commits add deterministic editor-operation tests for text/title and dialogue-assignment integrity, delete renumbering, reorder metadata, merge/split offsets, invalid split safety, history invalidation, Unicode Find/Replace offsets, redetection preview/stale-fingerprint behavior, and import duplicate/cancellation/retry/failure paths. These tests passed in #1478.
- Structural history invalidation is a safety guard, not full cross-structure undo. Undo/redo remains scoped to the active chapter's text-edit history.

## New automated coverage added for the current checkpoint

- Chapter history is invalidated after structural chapter mutations to prevent stale per-number undo snapshots from being applied to a different chapter.
- Case-insensitive chapter Find/Replace uses match offsets in the original string, avoiding Unicode lowercasing length changes.
- Re-detection requires a before/after review and an unchanged-source fingerprint; preview is non-mutating, and missing/stale fingerprints are rejected.
- Import edge tests cover duplicate guidance (browse and dropped file), staging cleanup, unsupported/empty file rejection, cancellation before publishing, and recoverable extraction failure without source loss.

## Remaining Stage 2 gates

- [x] Latest checkpoint CI run passes: #1478 completed successfully with 752/752 tests, Windows installer/portable packaging, hash generation, Defender scan and artifact uploads.
- [ ] Verify import cancellation timing, duplicate guidance, empty/unsupported/damaged files, retry/error states and cleanup interactively in the packaged Windows app. Automated tests cover duplicate handling, cancellation after extraction/detection before publication, empty/unsupported rejection, recoverable extraction failure, retry and temporary staging cleanup; packaged UI acceptance remains open.
- [ ] Exercise chapter add/delete/move/merge/split/clean/find-replace/undo-redo through the packaged UI; automated model/adapter regressions pass, but core tests do not prove the complete UI interaction contract.
- [ ] On the target Windows install, import TXT, EPUB, searchable PDF, and DOCX; edit/save/reopen, compare source/body text and chapter counts, and capture exceptions/logs.
- [ ] Record real-book outcomes and any limitations; do not claim zero-defect or full interactive acceptance from CI alone.

## Work started in this branch

1. Added transactional project creation: copy and write into a private staging folder, reload-verify the project, then publish the completed folder by rename. On errors, staging is removed.
2. Added import integrity regression tests for BOM handling, chapter boundary separation, watermark cleanup, persistence of review/skip flags, and failed source-copy cleanup.
3. Added this branch to the Windows workflow trigger so these changes receive the full build/test/package pipeline.

## Historical implementation status

Run #877 and PR #17 are prior Stage 2 history. The current checkpoint is Build Windows App #1478, which passed on 28 October 2026 at commit `cbe8b41a46b1d5807699e67fbd54a5d1e698c6a0`: 752/752 tests passed, installer/portable packages were built, release hashes generated, Defender found no threats, and all four CI artifacts were uploaded. The exact installer and package artifact details are recorded in [Stage 2 evidence](STAGE_2_IMPORT_CHAPTER_EVIDENCE.md). Target-Windows interactive acceptance remains explicitly outstanding.

## Known limitations / risk boundaries

- CI can validate parser fixtures and package behavior, but it cannot prove correct extraction for every real book or test Windows UI interaction on the user's specific PC.
- Scanned/image-only PDFs are not automatically OCR'd. The import should block or clearly diagnose sparse extraction rather than create a misleading partial audiobook.
- Existing projects use JSON/filesystem persistence; this stage does not silently migrate them to SQLite.
- Stage 1 hardware-specific freeze/crash validation remains a separate target-PC acceptance item; Stage 2 proceeds in parallel with that outstanding evidence and does not mark it resolved.


## 2026-10-24 reliability addendum

Chapter selection flushes a queued autosave before navigation and blocks selection if save fails. Job polling and catalogue/list refreshes are guarded against overlaps/stale replies. Generation completion refreshes output metadata and History without rebuilding the Chapter editor. Target-Windows import/edit/save/reopen and real audio acceptance remain open.
