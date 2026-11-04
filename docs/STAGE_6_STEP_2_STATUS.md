# Stage 6 — Step 2 Audiobooks Library and Actual Output Integrity

**Project:** Ryu's Audiobook — Dragon Studio Edition  
**Branch:** `stage-6/baseline-audit`  
**Implementation head:** `14b9a42485345ee9e86fe27cd4743cc34663aa8a`  
**Accepted packaged checkpoint:** [Build #2274](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41806424525)  
**Accepted exact source SHA:** `c60354c995d9adce886984fc37a9be3c13ee04a4`  
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
- **Packaged Windows verification:** #2274 passed end-to-end on exact source SHA `c60354c995d9adce886984fc37a9be3c13ee04a4`. The 1,146-test regression job, JavaScript syntax validation and isolated Qt lifecycle regression passed. Frozen EXE verification and bundled Piper/Kokoro/starter-audio asset checks passed. The packaged acceptance passed all four Stage 6 Audiobooks markers: `stage6_audiobooks_compact_multiple_real_output_cards`, `stage6_audiobooks_open_loads_correct_book_paused`, `stage6_audiobooks_play_action_starts_real_audio`, and `stage6_audiobooks_switch_preserves_project_output_identity`. The same run also passed existing Sound Design, Production Preview, Stage 5.4 full generation, Background Jobs pause/resume/cancel/retry/recovery, M4B chapter markers, Stage 5.5 playback, and restart-recovery acceptance. The Windows installer, portable app and SHA-256 manifest were built and uploaded; Microsoft Defender scan passed. Public release publishing was skipped by workflow design. **Step 2 packaged acceptance is complete.**
- **Failure reconciliation:** #2255 was an intermediate patch whose renderer replacement had also removed neighbouring adapter helpers; this was corrected by restoring the original helper code and narrowing the replacement. #2256/#2257 exposed three contract mismatches in the added tests/fixtures (renderer boundary, existing `openPlayer` signature compatibility, and packaged-runner import isolation); those were corrected in #2258. No valid run was manually cancelled. #2255–#2257 were intermediate implementation/test-contract failures and were superseded by #2258. #2259 exposed missing `imageio_ffmpeg`; #2263 exposed the Pillow diagnostic contract; #2266 exposed missing `mutagen` in the private Python. #2270 passed all four new Stage 6 Audiobooks assertions but exposed a downstream Stage 5.4 control-generation timeout. The failure was isolated with targeted harness diagnostics and resolved on the follow-up exact-head packaged run #2274, which passed the full combined packaged acceptance. The prior failures remain documented as superseded candidates, not silently discarded.

## Requirement status

| Requirement | Status | Rule |
|---|---|---|
| AB-01 | VERIFIED COMPLETE | Build #2274 passed all four exact-head packaged Audiobooks acceptance markers, on source SHA `c60354c995d9adce886984fc37a9be3c13ee04a4`; installer, portable and SHA-256 artifacts uploaded. |
| AB-02 | VERIFIED COMPLETE (carry-forward) | Preserve #2253 M4B-to-WebEngine playback path; reopen only on regression. |
| AB-07 | VERIFIED COMPLETE (carry-forward) | Preserve project/output/cover/title/author/narrator/chapter association; reopen only on regression. |

**Formal closeout:** Step 2 COMPLETE — exact-head Build #2274 passed and artifacts were uploaded. This section retains the implementation-head identifier for the original code commit; accepted package head is `c60354c995d9adce886984fc37a9be3c13ee04a4`.

## Explicit non-goals

No rewrite of the full player controls, chapter/playhead synchronization, mini-player, playback-position persistence, History, Task Manager, legacy native Audiobooks UI, or the Stage 5.5 output pipeline. Those remain in their assigned Stage 6 steps.


## Step 2 closeout — Build #2274

- Run: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41806424525
- Source SHA: `c60354c995d9adce886984fc37a9be3c13ee04a4`
- Regression: 1,146 tests passed; JavaScript syntax and isolated Qt lifecycle passed.
- Frozen application and bundled voice/starter-audio verification: passed.
- Packaged UI: all four Stage 6 audiobook acceptance markers passed.
- Carry-forward integration: Sound Design, Production Preview, real Stage 5.4 multi-chapter generation, Pause/Resume/Cancel, Retry, History/output ownership, M4B chapter metadata, Stage 5.5 playback, and restart recovery passed.
- Release pipeline: Inno Setup installer built; functional HTML installer built; original logo transparency/hash checks passed; Microsoft Defender scan passed; installer, portable package and SHA-256 manifest uploaded.
- Artifact records (all non-expired at verification; expiry 4 December 2026):
  - Installer `Ryu-Audiobook-Installer-2274`, 884,023,251 bytes, artifact [13310574401](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41806424525/artifacts/13310574401), archive digest `sha256:2016b31c5f4091d5d695b58b4fbe8fa94bc8fc90ec781ba5c9d550693375c6d2`.
  - Portable `Ryu-Audiobook-Portable-2274`, 1,367,980,272 bytes, artifact [13311073747](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41806424525/artifacts/13311073747), archive digest `sha256:5aa517942d420f664cbee931c3dd87ab4a9f0b55c894977a6b5c827a1308ccb4`.
  - SHA-256 manifest `Ryu-Audiobook-Release-SHA256-2274`, 778 bytes, artifact [13309999513](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41806424525/artifacts/13309999513), archive digest `sha256:859bac6d14d6b7b66d50168b0dd5d80cc1c22ee3a95972ad289b25efe3370bcb`.

**Decision: Stage 6 Step 2 COMPLETE.** AB-02 and AB-07 remain preserved, verified carry-forward requirements; no rebuild of the M4B source pipeline was needed.
