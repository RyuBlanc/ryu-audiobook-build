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

- **Actions run:** [Build Windows App #1464](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40548201450) — completed successfully on 27 October 2026.
- **Tested commit:** `579c378ae81ab9c06e7c68feae5485574f3f02cc`
- **Regression tests:** 732 total, 732 passed, 0 failed, 0 errors, 0 skipped; 28.745 seconds. The uploaded evidence JSON records this exact commit SHA, run number, and run ID.
- **Build validation:** JavaScript syntax, application preparation/frozen build, bundled voice assets/critical modules, core installer payload, functional HTML installer, logo transparency and SHA-256 generation, and Microsoft Defender scanning all passed.
- **Release artifacts (available in the Actions run for 30 days, through 26 November 2026):**

| Artifact | Artifact ID | Size | Artifact digest |
|---|---:|---:|---|
| `Ryu-Audiobook-Test-Evidence-1464` | `12753478505` | 46,619 bytes | `c9af4bc1704c31bdd505d57afa7bae9d62c02caa97b1ecb2e2262a5b98cfa2af` |
| `Ryu-Audiobook-Installer-1464` | `12754079470` | 878,046,356 bytes (about 878 MB) | `bac0af904ad9a30504e9931e2ea0e03d0e0c834d1b725cb63acfb3ae460ff35b` |
| `Ryu-Audiobook-Portable-1464` | `12753879857` | 1,349,451,876 bytes (about 1.35 GB) | `d5f5463909d790315c2ca3529b4bb8a35b90847ca6443774c7ec1ccba8f72180` |
| `Ryu-Audiobook-Release-SHA256-1464` | `12754439163` | 776 bytes | `4479bd93ab1b754deb520cc39901e9b97f5da3fdf7e78b99f35105f0bffe881a` |

The release manifest's SHA-256 for the installer executable is `aa3d0a5c56528115f59d5bbda2a4a859a2efef174f2d80874fefe4ee3cc85dd3` (878,046,192 bytes). The portable artifact digest above is GitHub's artifact archive digest; the build's manifest lists the executable and logo assets inside the package separately.

The repository workflow skipped public-release publishing because this is a working branch. The installer, portable app, manifest, and test evidence are uploaded as Actions artifacts in the run linked above. The automated evidence ZIP retains the workflow's shared test-evidence filename/title; its metadata verifies the Stage 2 commit and run identity.

**Acceptance boundary:** automated CI/package validation passed; manual interactive acceptance of the exact installer on a target Windows PC remains open. Do not treat this checkpoint as proof of every UI interaction, import format, chapter edit path, or cancel timing on the user's machine.

- Stage 2 editor-operation coverage now includes model-level rename/edit, delete-renumber, move payload retention, merge/split assignment offset integrity, invalid split safety, Unicode-safe Find/Replace offsets, and invalidation of stale number-keyed undo/redo history after structural edits.
- Chapter re-detection now presents before/after chapter title and text-snippet summaries without saving. Apply requires the SHA-256 fingerprint from the current preview; missing or stale fingerprints are rejected. Added tests for preview-only behavior, no-mutation rejection paths, successful apply, and matching UI adapter flow.
- Import edge-case tests now cover exact duplicate guidance for Browse imports, temporary-file cleanup for duplicate drag/drop imports, empty/unsupported files, cancellation after extraction/detection before publication, and recoverable failure status with original source preservation.

## Consolidated checkpoint candidate

The current working branch includes additional regression coverage for editor structural operations, Unicode-safe Find/Replace, non-mutating before/after re-detection preview with stale-fingerprint rejection, and import duplicate/cancellation/failure paths. The next `[artifact-checkpoint]` workflow run is the validation source of truth for these changes; counts and package artifacts are recorded only after that run finishes successfully.

## Packaged-Windows acceptance checklist

- [ ] Start a TXT import and cancel mid-extraction / chapter detection; verify the job becomes cancelled and no incomplete project is published.
- [ ] Import TXT, EPUB, searchable PDF, and DOCX; verify extraction order, opening text, chapter count, and no silent truncation.
- [ ] Test file-picker and drag/drop routes, duplicate import guidance, unsupported/empty/damaged files, and source preservation.
- [ ] Right-click a chapter and run re-detect with unchanged headings; confirm manual titles, review state, skipped state, text, and dialogue assignments are retained where applicable.
- [ ] Attempt re-detection with a heading/noise pattern that would rewrite or remove text; confirm it stops and the saved project remains unchanged.
- [ ] Test re-detection that splits one manually edited chapter into several; verify every saved character stays in order, mapped assignments retain correct text/offsets, affected chapters need review, and skipped passages remain excluded.
- [ ] Test add/rename/delete/reorder/merge/split, clean, find/replace, undo/redo, multi-select delete, rapid chapter switching, autosave error, close/reopen, and exact text comparison.
- [ ] Validate with real books at representative lengths and record errors/logs rather than claiming an unsupported zero-defect result.
