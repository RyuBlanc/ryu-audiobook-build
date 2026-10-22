# Stage 2 Plan — Import Integrity, Text Cleanup, and Chapter Structure

**Working branch:** `stage-2/import-integrity`  
**Baseline:** Stage 1 merge commit `1fbb5e9ae897315bb5a5ca96d0a4ef68178f1e2a`  
**Rule:** preserve the approved Premium V2 UI. Change backend behavior and tests; do not redesign the interface or report simulated completion.

## Goals and exit criteria

### 2.1 Source import integrity
- [ ] Exercise TXT (including UTF-8 BOM), EPUB reading order/spine, PDF searchable-text quality, and DOCX paragraphs/tables using reproducible fixtures.
- [x] Publish a project only after source staging, project metadata, chapter JSON, and a reload verification succeed.
- [ ] Confirm failed copy/write/validation removes staging data and leaves no partial project visible.
- [ ] Verify duplicate import guidance, cancellation, retry, and failure status in the packaged Windows app.

### 2.2 Cleaning without story loss
- [ ] Test known ebook watermarks/page counters and repeated boilerplate against normal narrative, URLs, punctuation, dialogue, and Unicode.
- [ ] Make cleanup conservative and report what was removed; do not silently discard plausible story content.
- [ ] Confirm reflow preserves paragraph/dialogue/heading boundaries and hyphenated line wraps.

### 2.3 Chapter detection and editing
- [ ] Test explicit numbered chapters, Roman numerals, prologue/epilogue, named sections, preambles, empty headings, books with no headings, and headings that resemble dialogue/body sentences.
- [ ] Verify source text is not lost or duplicated at boundaries; preserve chapter ordering and numbering.
- [ ] Verify rename/add/delete/move/merge/split/clean, find/replace, undo/redo, review status, and skip-for-generation persistence after reload.
- [ ] Keep re-detection disabled unless it can show a before/after review and protect manual edits.

### 2.4 Automated and Windows acceptance
- [ ] Run the complete unittest regression suite and Windows package/installer pipeline on this branch.
- [ ] Inspect failures and fix them before merging.
- [ ] On a target Windows install, import one fixture in each supported format, edit and save chapters, restart/reopen, and compare text and chapter counts.
- [ ] Record any Windows-only acceptance that cannot be performed in cloud CI as an explicit release gate.

## Work started in this branch

1. Added transactional project creation: copy and write into a private staging folder, reload-verify the project, then publish the completed folder by rename. On errors, staging is removed.
2. Added import integrity regression tests for BOM handling, chapter boundary separation, watermark cleanup, persistence of review/skip flags, and failed source-copy cleanup.
3. Added this branch to the Windows workflow trigger so these changes receive the full build/test/package pipeline.

## Known limitations / risk boundaries

- CI can validate parser fixtures and package behavior, but it cannot prove correct extraction for every real book or test Windows UI interaction on the user's specific PC.
- Scanned/image-only PDFs are not automatically OCR'd. The import should block or clearly diagnose sparse extraction rather than create a misleading partial audiobook.
- Existing projects use JSON/filesystem persistence; this stage does not silently migrate them to SQLite.
- Stage 1 hardware-specific freeze/crash validation remains a separate target-PC acceptance item; Stage 2 proceeds in parallel with that outstanding evidence and does not mark it resolved.
