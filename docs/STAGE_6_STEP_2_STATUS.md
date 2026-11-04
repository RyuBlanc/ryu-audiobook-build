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
- **Packaged Windows verification:** Build #2259 successfully built and self-tested the frozen EXE and verified bundled voice assets, but its packaged acceptance step stopped before the UI tests because the selected private Python lacked `imageio_ffmpeg`. The failure was environmental bootstrap, not an AB-01 assertion. Workflow fix: install `imageio-ffmpeg` into that exact private interpreter and probe it before acceptance. AB-01 remains open until a new exact-head checkpoint reports all four Stage 6 markers and uploads the release artifacts.
- **Failure reconciliation:** #2255 was an intermediate patch whose renderer replacement had also removed neighbouring adapter helpers; this was corrected by restoring the original helper code and narrowing the replacement. #2256/#2257 exposed three contract mismatches in the added tests/fixtures (renderer boundary, existing `openPlayer` signature compatibility, and packaged-runner import isolation); those were corrected in #2258. No valid run was manually cancelled. Build #2259 (`76805b9`) test job passed (1,146 regressions, JS syntax, isolated Qt lifecycle); frozen build/self-test and bundled asset verification passed. Its only failure was `PACKAGED SOUND DESIGN UI ACCEPTANCE FAILED: No module named 'imageio_ffmpeg'` at 08:00:07Z. The durable private Python bootstrap was missing a dependency installed in the separate CI Python. This is corrected in the workflow bootstrap and guarded by an explicit import/FFmpeg-path probe; a new checkpoint is required.

## Requirement status

| Requirement | Status | Rule |
|---|---|---|
| AB-01 | AUTOMATED TESTS PASSED | 1,146 matching-head tests passed; frozen-Windows packaged acceptance remains pending. |
| AB-02 | VERIFIED COMPLETE (carry-forward) | Preserve #2253 M4B-to-WebEngine playback path; reopen only on regression. |
| AB-07 | VERIFIED COMPLETE (carry-forward) | Preserve project/output/cover/title/author/narrator/chapter association; reopen only on regression. |

## Explicit non-goals

No rewrite of the full player controls, chapter/playhead synchronization, mini-player, playback-position persistence, History, Task Manager, legacy native Audiobooks UI, or the Stage 5.5 output pipeline. Those remain in their assigned Stage 6 steps.
