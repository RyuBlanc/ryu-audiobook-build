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
- [ ] Automated fixtures cover numbered/Roman chapters, prologue/epilogue, preambles, books without headings, and dialogue-like false headings; still add explicit named-section and empty-heading fixtures.
- [x] Verify covered chapter boundaries preserve body text; project save normalizes chapter numbering to current order, and regression tests verify reordered chapters reload in that order.
- [ ] Persistence regression now covers chapter title/text edits, reorder, dialogue assignments, review status, and skip-for-generation after reload. Still verify all editor operations (add/delete/merge/split/clean/find-replace/undo-redo) in automated or packaged-app tests.
- [ ] Keep re-detection disabled unless it can show a before/after review and protect manual edits.

### 2.4 Automated and Windows acceptance
- [ ] Run the complete unittest regression suite and Windows package/installer pipeline on the latest branch head; Run #871 passed before the newest persistence/failure-path fixtures.
- [ ] Inspect failures and fix them before merging.
- [ ] On a target Windows install, import one fixture in each supported format, edit and save chapters, restart/reopen, and compare text and chapter counts.
- [ ] Record any Windows-only acceptance that cannot be performed in cloud CI as an explicit release gate.

## Work started in this branch

1. Added transactional project creation: copy and write into a private staging folder, reload-verify the project, then publish the completed folder by rename. On errors, staging is removed.
2. Added import integrity regression tests for BOM handling, chapter boundary separation, watermark cleanup, persistence of review/skip flags, and failed source-copy cleanup.
3. Added this branch to the Windows workflow trigger so these changes receive the full build/test/package pipeline.

## Current status after Run #871

Run #871 passed on commit `3607554656b8217a9bf37a39d32d35cc88c9e61c`. Additional regression coverage was then added for edited/reordered chapter persistence, invalid-source rejection, and repeated boilerplate cleanup; these newer commits must pass the next Windows workflow before they can be counted as verified. Stage 2 is not yet declared complete until that run passes and the packaged-Windows acceptance gate below is either performed or explicitly recorded as outstanding.

## Known limitations / risk boundaries

- CI can validate parser fixtures and package behavior, but it cannot prove correct extraction for every real book or test Windows UI interaction on the user's specific PC.
- Scanned/image-only PDFs are not automatically OCR'd. The import should block or clearly diagnose sparse extraction rather than create a misleading partial audiobook.
- Existing projects use JSON/filesystem persistence; this stage does not silently migrate them to SQLite.
- Stage 1 hardware-specific freeze/crash validation remains a separate target-PC acceptance item; Stage 2 proceeds in parallel with that outstanding evidence and does not mark it resolved.
