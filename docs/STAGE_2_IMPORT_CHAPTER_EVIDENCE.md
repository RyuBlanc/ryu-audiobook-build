# Stage 2 — Import and Chapter Studio Evidence

Date: 27 October 2026  
Repository: RyuBlanc/ryu-audiobook-build  
Working branch: fix/native-ui-font-scale-learning-ai

## Scope for this checkpoint

This batch follows the repository's Import + Chapter Studio roadmap. It does not repeat Stage 1 fixes or change the approved visual layout.

- Added a contextual **Cancel import** action tied only to the import job created by Import Studio. It calls the existing backend job-cancel path and reports the cancellation request while preserving the source file.
- Added **redetect** to the existing Chapter Studio contextual actions. Re-detection operates on saved, edited chapter text (not the original import), saves only after successful mapping, and aborts without changing the project if any content would be rewritten, removed, or left outside the detected chapters.
- When boundaries change, changed chapters return to Needs Review; exact one-to-one chapter metadata and manually edited titles are retained where safely matchable.
- Explicitly skipped text remains excluded after a split/merge of boundaries; this conservatively skips a new chapter if it overlaps previously excluded text.
- Dialogue assignment offsets are remapped from absolute source spans. Assignments that no longer map exactly to one chapter are dropped rather than left with stale offsets, and the user is told the count.
- Added dedicated regression tests for re-detection text preservation, manual title/review/skip persistence, assignment remapping, empty chapters, and failure-without-mutation.

## Automated test evidence

Final counts, run URL, commit SHA, and artifact identifiers will be recorded here after the artifact-checkpoint run completes. An ordinary CI test pass is not treated as manual Windows acceptance.

## Packaged-Windows acceptance checklist

- [ ] Start a TXT import and cancel mid-extraction / chapter detection; verify the job becomes cancelled and no incomplete project is published.
- [ ] Import TXT, EPUB, searchable PDF, and DOCX; verify extraction order, opening text, chapter count, and no silent truncation.
- [ ] Test file-picker and drag/drop routes, duplicate import guidance, unsupported/empty/damaged files, and source preservation.
- [ ] Right-click a chapter and run re-detect with unchanged headings; confirm manual titles, review state, skipped state, text, and dialogue assignments are retained where applicable.
- [ ] Attempt re-detection with a heading/noise pattern that would rewrite or remove text; confirm it stops and the saved project remains unchanged.
- [ ] Test re-detection that splits one manually edited chapter into several; verify every saved character stays in order, mapped assignments retain correct text/offsets, affected chapters need review, and skipped passages remain excluded.
- [ ] Test add/rename/delete/reorder/merge/split, clean, find/replace, undo/redo, multi-select delete, rapid chapter switching, autosave error, close/reopen, and exact text comparison.
- [ ] Validate with real books at representative lengths and record errors/logs rather than claiming an unsupported zero-defect result.
