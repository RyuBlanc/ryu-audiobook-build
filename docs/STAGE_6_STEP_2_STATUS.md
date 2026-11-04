# Stage 6 — Step 2 Audiobooks Library and Actual Output Integrity

**Project:** Ryu's Audiobook — Dragon Studio Edition  
**Branch:** `stage-6/baseline-audit`  
**Implementation head:** `14b9a42485345ee9e86fe27cd4743cc34663aa8a`  
**Date:** 4 November 2026  
**Scope:** AB-01, with AB-02 and AB-07 preserved as verified carry-forward requirements.

## Implementation

### AB-01 — compact Premium V2 audiobook cards

The previous adapter-generated section was incomplete: cards used the generic oversized project-card style, hard-coded a “Ready” badge, and provided only Play. The implementation now:

- Renders a responsive compact grid with a bounded maximum width so cards do not spread across ultrawide displays.
- Uses portrait 2:3 covers and consistent compact card geometry, readable two-line titles, author/narrator/chapter metadata and compact spacing.
- Uses only backend project records with `completed === true` and a non-empty `output_path`; the displayed status comes from the saved project status, not a hard-coded sample.
- Preserves the exact project folder, cover and output association on each card.
- Adds separate Open and Play actions. Open resolves the exact project through `player.get_active`, loads the verified playback source and leaves it paused. Play uses the same real player session and starts playback.
- Places the collection directly below the Audiobooks page heading and preserves the full player beneath it.

### AB-02 / AB-07 — preserved, not rebuilt

No changes were made to the Stage 5.5 M4B assembler, output registration, validation, chapter metadata extraction or cached browser-compatible playback derivative. The backend still requires a real non-empty completed output, validates the selected project/output again when the player opens, and returns the authoritative M4B plus the playback derivative and embedded chapter data.

The accepted Stage 5.5 Windows build #2253 remains the previous packaged evidence for actual M4B decoding/playback and output ownership. Step 2 adds new exact-head acceptance fixtures to recheck those associations against multiple books.

## Verification

- New Python regression contracts: `tests/test_stage6_audiobook_library.py`.
- New packaged fixture books: two distinct completed M4B files with different covers, titles, authors, narrators and embedded chapters.
- New frozen Premium V2 acceptance: multiple cards, actual status/cover/title binding, Open-without-autoplay, Play with real decoded audio, and switching books without stale output/metadata.
- Windows workflow now includes `stage-6/**`, so Stage 6 commits receive the regression job.
- **Automated verification:** PASS on exact implementation head `14b9a42485345ee9e86fe27cd4743cc34663aa8a`. Build #2258 completed `tests/run_regression_suite.py`: **1,146 tests passed in 52.642 seconds**. Frontend JavaScript syntax validation and the isolated native Qt lifecycle regression also passed.
- **Packaged Windows verification:** #2259 lacked `imageio_ffmpeg`; #2266 lacked `mutagen` in the private harness interpreter. Those dependency bootstrap gaps are corrected. #2270 passed 1,146 regressions, frozen EXE verification, bundled voice assets, and all four new Stage 6 Audiobooks markers (compact cards, Open paused, real Play, book switching). The combined older Sound Design/Stage 5.4 suite then failed later at `Timed out waiting for real Stage 5.4 control generation start` after switching back to the Stage 5.4 job-control fixture. The Start button was found enabled and the expected project was opened; the timeout means no new generation job appeared within 30 seconds. The harness now emits targeted diagnostics (active project, narrator selection, readiness, button state/status and jobs list) at that precise boundary, rather than only a generic timeout. AB-01 functional checks are proven in #2270, but formal Step 2 closure still requires the packaged checkpoint to pass and release artifacts to upload.
- **Failure reconciliation:** #2255 was an intermediate patch whose renderer replacement had also removed neighbouring adapter helpers; this was corrected by restoring the original helper code and narrowing the replacement. #2256/#2257 exposed three contract mismatches in the added tests/fixtures (renderer boundary, existing `openPlayer` signature compatibility, and packaged-runner import isolation); those were corrected in #2258. No valid run was manually cancelled. #2255–#2257 were intermediate implementation/test-contract failures and were superseded by #2258 (1,146 tests pass). #2259 exposed missing `imageio_ffmpeg`; #2263 exposed the Pillow diagnostic contract; #2266 exposed missing `mutagen` in the private Python; the bootstrap now installs and preflights all three plus `app.audio.assembler`. #2270 then passed the full 1,146 suite, frozen EXE, Piper/Kokoro and starter-audio checks, and all four Stage 6 Audiobooks markers. Its later failure is outside AB-01: the existing combined Stage 2/5.4 script timed out waiting for a new Stage 5.4 control-generation job after the audiobook checks, despite opening the expected fixture and seeing Generate enabled. A targeted harness diagnostic has been added around that real Start action to capture active project, narrator selection, production readiness, button/status state and current jobs. Do not weaken or skip the real Stage 5.4 generation acceptance.

## Requirement status

| Requirement | Status | Rule |
|---|---|---|
| AB-01 | AUTOMATED TESTS PASSED | 1,146 matching-head tests passed; frozen-Windows packaged acceptance remains pending. |
| AB-02 | VERIFIED COMPLETE (carry-forward) | Preserve #2253 M4B-to-WebEngine playback path; reopen only on regression. |
| AB-07 | VERIFIED COMPLETE (carry-forward) | Preserve project/output/cover/title/author/narrator/chapter association; reopen only on regression. |

## Explicit non-goals

No rewrite of the full player controls, chapter/playhead synchronization, mini-player, playback-position persistence, History, Task Manager, legacy native Audiobooks UI, or the Stage 5.5 output pipeline. Those remain in their assigned Stage 6 steps.
