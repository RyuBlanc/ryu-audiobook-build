# Stage 2 Plan — Import Integrity, Text Cleanup, and Chapter Structure

**Working branch:** `stage-2/import-integrity-post-stage1`  
**Baseline:** Stage 1.10 artifact checkpoint #1637, commit `4c3ac39ee8b1664d76422bcaf8a7460b7df77635`  
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
- [ ] Keep re-detection disabled unless it can show a before/after review and protect manual edits.

### 2.4 Automated and Windows acceptance
- [x] Run the complete unittest regression suite and Windows package/installer pipeline on the final Stage 2 branch head; Run #877 passed on commit `05e03c14637bb4ff3fe8514a50101ebde0d2ab4b`.
- [ ] Inspect failures and fix them before merging.
- [ ] On a target Windows install, import one fixture in each supported format, edit and save chapters, restart/reopen, and compare text and chapter counts.
- [ ] Record any Windows-only acceptance that cannot be performed in cloud CI as an explicit release gate.

## Work started in this branch

1. Added transactional project creation: copy and write into a private staging folder, reload-verify the project, then publish the completed folder by rename. On errors, staging is removed.
2. Added import integrity regression tests for BOM handling, chapter boundary separation, watermark cleanup, persistence of review/skip flags, and failed source-copy cleanup.
3. Added this branch to the Windows workflow trigger so these changes receive the full build/test/package pipeline.

## Prior Stage 2 evidence from the legacy branch

Run #877 passed on final Stage 2 commit `05e03c14637bb4ff3fe8514a50101ebde0d2ab4b`, including added coverage for edited/reordered chapter persistence, invalid-source rejection, and repeated boilerplate cleanup. PR #17 was merged as `9aa1ba5cc9be0808d596c1e2c0618584433c9917`. Automated implementation and package gates passed; packaged-Windows acceptance remains explicitly outstanding.

## Known limitations / risk boundaries

- CI can validate parser fixtures and package behavior, but it cannot prove correct extraction for every real book or test Windows UI interaction on the user's specific PC.
- Scanned/image-only PDFs are not automatically OCR'd. The import should block or clearly diagnose sparse extraction rather than create a misleading partial audiobook.
- Existing projects use JSON/filesystem persistence; this stage does not silently migrate them to SQLite.
- Stage 1 hardware-specific freeze/crash validation remains a separate target-PC acceptance item; Stage 2 proceeds in parallel with that outstanding evidence and does not mark it resolved.


## 2026-10-24 reliability addendum

Chapter selection flushes a queued autosave before navigation and blocks selection if save fails. Job polling and catalogue/list refreshes are guarded against overlaps/stale replies. Generation completion refreshes output metadata and History without rebuilding the Chapter editor. Target-Windows import/edit/save/reopen and real audio acceptance remain open.


## Current Stage 2 execution — post-Stage 1.10 baseline

- The new working branch is based on the exact successful Stage 1.10 checkpoint #1637. The older `stage-2/import-integrity` branch is retained unchanged because it diverged from the current Stage 1 line.
- Stage 2 follows the repository's test-first rule: add a regression assertion, confirm it fails on the current implementation, make the minimal source fix, run the full regression suite, then create an artifact checkpoint only after the tests are green.
- First active gap: the Premium V2 bridge's chapter-split handler does not keep saved dialogue/cast assignments with the passage they describe. The new regression tests require assignments wholly on the right side to move with corrected offsets and reject splits that cut through an assignment without mutating or saving the project.
- No UI redesign is included. Existing source-import and chapter-fixture coverage remains in place and will not be redone without evidence of a regression.
- Target-Windows import/edit/save/reopen acceptance remains a separate manual gate; passing CI does not claim that every real book has been accepted.
