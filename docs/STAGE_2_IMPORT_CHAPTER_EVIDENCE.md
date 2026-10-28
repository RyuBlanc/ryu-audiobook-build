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
- Added a before/after chapter re-detection preview that makes no changes by itself; applying it requires a SHA-256 fingerprint matching the current saved chapter data. Missing or stale preview tokens reject the save.
- Invalidated chapter undo/redo stacks after structural edits so history keyed by chapter number cannot be applied to another chapter after numbering changes.
- Corrected case-insensitive Find/Replace to use regex matches and offsets in the original text, avoiding corrupt offsets when Unicode case conversion changes string length.
- Added regression coverage for editor operations, Unicode Find/Replace source offsets, preview-only behavior, stale-preview rejection, and the successful preview-then-apply flow.

## Automated test and artifact evidence — successful checkpoint

- **Actions run:** [Build Windows App #1478](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40614478453) — completed successfully on 28 October 2026.
- **Tested commit:** `cbe8b41a46b1d5807699e67fbd54a5d1e698c6a0`
- **Regression tests:** 752 total; **752 passed, 0 failed, 0 errors, 0 skipped**. Test evidence JSON records this exact commit SHA, run number and run ID.
- **Build validation:** installer JavaScript syntax, application preparation/frozen build, bundled voice assets/critical modules, core installer payload, functional HTML installer, logo transparency/hash generation, Microsoft Defender scan, installer upload, release-manifest upload, and portable app upload all passed. The stale Actions-run/storage cleanup job also passed.
- **Defender:** no threats found in either installer executable.
- **Public release:** skipped because this checkpoint is on the working branch; build artifacts remain available from the Actions run for the retention period.

| Artifact | Artifact ID | Archive size | Artifact SHA-256 |
|---|---:|---:|---|
| `Ryu-Audiobook-Test-Evidence-1478` | `12784567421` | 48,176 bytes | `7d758e1267e4b9017bb46e840474ecfd30301eb7003ddd43026da719047bfafb` |
| `Ryu-Audiobook-Installer-1478` | `12785012587` | 878,100,084 bytes (~878 MB) | `3512d604015dab925f05cfbbd5a07aea272e838292f9eb471cffda768f9cfb36` |
| `Ryu-Audiobook-Portable-1478` | `12785122261` | 1,349,458,232 bytes (~1.35 GB) | `ce3afa9a2b432467117f17bb295f35db842ef942eef3db6b971185ab522f9ffc` |
| `Ryu-Audiobook-Release-SHA256-1478` | `12785047505` | 780 bytes | `5f4e09c607e3e4cb947b774a61de9d34fc0b218ed4465ded773a6114cfc606b5` |

The inspected release SHA-256 manifest records these executable files:

| File | Size | SHA-256 |
|---|---:|---|
| `Ryu's Audiobook Setup.exe` | 878,099,920 bytes | `a51c4cbb006bc8550f08a5732256059e51fea85c9a9a02fbacaa36256773a258` |
| `Ryu's Audiobook Core Setup.exe` | 651,146,735 bytes | `76101390aeead3e346e88e361bc7e302a36d58223487a7b446ff68ccba372b54` |
| `Ryu's Audiobook.exe` (portable app entry point) | 11,551,025 bytes | `49f7a164f5ebd06b9064b1ee1450feee56e66cb512c5999102cf140703cf90ff` |

The artifact archive digests above identify the GitHub ZIPs; the manifest hashes identify the files contained in the release package. The manifest and the automated evidence ZIP were downloaded and inspected. The installer and portable artifacts are larger than 500 MB; this checkpoint did not attempt lossy compression or claim a smaller package.

**Acceptance boundary:** CI and package validation passed. The exact packaged installer has not been interactively accepted on the target Windows PC. Keep the manual checklist below open; automated tests do not prove that every UI interaction and real-book import behaves correctly on the user's machine.

- Editor-operation tests cover title/text edits, delete renumbering, move payload retention, merge/split assignment-offset integrity, invalid split safety, Unicode-safe Find/Replace offsets, and invalidation of stale number-keyed undo/redo history after structural edits.
- Re-detection presents before/after chapter titles and text snippets without saving. Applying it requires a SHA-256 fingerprint matching the saved source; missing or stale fingerprints are rejected.
- Import edge tests cover duplicate guidance for Browse and dropped files, temporary staging cleanup, empty/unsupported files, cancellation after extraction/detection before publication, recoverable extraction failure, and retry while preserving the source.
- The preceding #1477 run exposed an outdated re-detection contract assertion and CP1252 report-printing failure; both were corrected. The runner was updated for UTF-8-safe output, and #1478 is the successful consolidated checkpoint.

## Packaged-Windows acceptance checklist

- [ ] Start a TXT import and cancel mid-extraction / chapter detection; verify the job becomes cancelled and no incomplete project is published.
- [ ] Import TXT, EPUB, searchable PDF, and DOCX; verify extraction order, opening text, chapter count, and no silent truncation.
- [ ] Test file-picker and drag/drop routes, duplicate import guidance, unsupported/empty/damaged files, and source preservation.
- [ ] Right-click a chapter and run re-detect with unchanged headings; confirm manual titles, review state, skipped state, text, and dialogue assignments are retained where applicable.
- [ ] Attempt re-detection with a heading/noise pattern that would rewrite or remove text; confirm it stops and the saved project remains unchanged.
- [ ] Test re-detection that splits one manually edited chapter into several; verify every saved character stays in order, mapped assignments retain correct text/offsets, affected chapters need review, and skipped passages remain excluded.
- [ ] Test add/rename/delete/reorder/merge/split, clean, find/replace, undo/redo, multi-select delete, rapid chapter switching, autosave error, close/reopen, and exact text comparison.
- [ ] Validate with real books at representative lengths and record errors/logs rather than claiming an unsupported zero-defect result.
