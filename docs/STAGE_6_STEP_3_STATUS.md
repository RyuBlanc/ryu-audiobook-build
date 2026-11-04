# Stage 6 — Step 3 Full Player and Chapter Synchronization

**Status:** IN PROGRESS — official kickoff, 4 November 2026  
**Branch:** `stage-6/baseline-audit`  
**Kickoff commit / source HEAD:** `d409780802b2f39913f4971348534647ecd6edd5`  
**Accepted Step 2 packaged source:** `c60354c995d9adce886984fc37a9be3c13ee04a4`  
**Step 2 evidence:** [Build #2274](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41806424525)  
**Requirements:** AB-03 and AB-04  
**Protected carry-forward:** AB-02 and AB-07

## 1. Objective

Complete the real Premium V2 full-player experience and embedded-chapter navigation/synchronization. Controls must affect the actual decoded local audiobook audio, and the selected chapter must follow the playhead against the authoritative embedded M4B chapter markers.

This step extends the accepted Stage 5.5 playback foundation. It does not replace the M4B source, rebuild the assembler, or change the browser-compatible MP3 derivative strategy.

## 2. Exact scope

### AB-03 — Full player controls

- Play / Pause toggles the currently selected audiobook's actual audio session.
- Seek timeline scrubbing moves the actual playhead; elapsed and total duration remain accurate and formatted.
- Volume changes affect the active media element and persist as a player preference.
- Playback-speed controls affect the active media element and persist within the supported 0.5×–2.0× range.
- Rewind 15 seconds and Forward 15 seconds move the actual playhead and clamp at 0 and the media duration.
- Full-player and mini-player Play / Pause buttons remain bound to the same selected book and Audio object; there must be no duplicate playback session or event-handler override.
- Disabled states and errors must reflect whether a playable source and finite duration are available.

### AB-04 — Embedded chapter playback

- Chapter titles and start/end times come from the actual chapter metadata read from the authoritative M4B.
- The chapter list displays the correct embedded chapter order and titles.
- Selecting a chapter seeks to its exact embedded start time; keyboard Enter/Space follows the same behavior.
- Previous / Next Chapter navigation follows the embedded marker order and handles first/last chapter boundaries without seeking outside the file.
- During ordinary playback and timeline seeking, the active chapter row and current-chapter heading update from the playhead using the embedded start/end interval.
- Chapter state is cleared/recomputed when a different audiobook is opened. No previous title, active-row highlight, marker list, or playhead identity may leak into the newly selected book.

## 3. Baseline audit — current implementation

### Existing behavior to preserve and verify

- `PremiumV2Bridge._player_get_active` validates the project's completed output, reads actual audio chapter metadata from the output M4B, and returns both the authoritative source path and the browser-compatible playback URL.
- `app/audio/playback.py` preserves the original M4B and creates/reuses a decoded browser-compatible MP3 derivative for Qt WebEngine. This is protected AB-02 work.
- The adapter already has real Audio-element state, time/duration display, timeline scrubbing, volume and rate setters, ±15-second seek helpers, previous/next chapter helpers, chapter-click seeking, and project-scoped position saves.
- The backend already persists player rate and volume settings; position persistence is project-scoped.

### Confirmed gaps / risks to address

1. **AB-04 playhead synchronization gap:** `renderSelectedAudiobook` renders chapter rows with their start times, but the live `audio.ontimeupdate` callback currently updates the timeline and time labels only. It does not select/highlight the chapter associated with the current playhead or update the current-chapter heading. Rendered chapter rows also do not expose the embedded end time as a data attribute.
2. **AB-03 Play / Pause binding risk:** the adapter first binds `mainPlay` and `miniPlay` to a selected-folder handler, but a later initializer assigns `act(openPlayer)`. The `act` wrapper forwards the click event to `openPlayer`, whose first argument is a project-folder value. This handler override is a concrete code-level mismatch and must be fixed and covered by a real packaged click test.
3. **Duplicate timeline binding:** the timeline is assigned more than once during adapter initialization. Keep one authoritative handler so scrubbing and position-save behavior are not accidentally overwritten.
4. **Coverage gap:** Stage 5.5 packaged acceptance proved actual M4B decoding/playback, embedded chapter seek and saved position. Stage 6 Step 2 proved card Open/Play and book switching. Neither checkpoint alone is a complete AB-03 control-by-control test or a playhead-driven AB-04 chapter-selection test.

The first implementation changes will be driven by failing regression tests and the exact packaged UI behavior. Do not infer successful player controls from the card-level Play marker.

## 4. Test-first verification matrix

| Area | Required assertion |
|---|---|
| Play / Pause | Both controls operate the same real audio element; media paused/playing state and control icon stay in sync. |
| Timeline | Scrubbing moves currentTime to the requested percentage; elapsed label updates; duration remains the actual media duration. |
| Volume | Slider changes the real Audio.volume and the saved preference; 0 and 100 boundaries are valid. |
| Playback rate | Selected rate changes Audio.playbackRate and persists; reject values outside 0.5×–2.0×. |
| ±15-second seek | Actual currentTime changes by 15 seconds and clamps at the beginning/end. |
| Chapter selection | Each timed row exposes the real embedded start/end; clicking and keyboard activation seek to the correct start. |
| Previous / Next | Navigate embedded chapters accurately; first/last boundaries remain inside the valid chapter list. |
| Playhead sync | On timeupdate/seeked, the active chapter matches the half-open embedded interval `start_seconds <= currentTime < end_seconds`; visual and accessible selected state update together. |
| Book switch | New book's markers, active chapter, title, cover and media state replace the old book's state; stale events from the old Audio element cannot overwrite the new display. |
| No-marker fallback | A playable book without embedded chapter timing remains playable; chapter navigation is disabled with a truthful explanation. |

### Planned frozen-app acceptance markers

- `stage6_player_full_controls_actual_audio`
- `stage6_player_seek_and_time_display`
- `stage6_player_volume_and_rate_affect_audio`
- `stage6_player_15_second_seek_clamps`
- `stage6_chapter_select_seeks_to_embedded_marker`
- `stage6_chapter_playhead_highlight_tracks_boundaries`
- `stage6_previous_next_chapter_navigation`
- `stage6_switching_book_clears_previous_chapter_selection`
- `stage6_mini_player_shares_full_player_audio_session`
- `stage6_chapter_keyboard_activation_starts_audio`
- `stage6_chapter_continuous_playback_updates_active_row`
- `stage6_chapter_space_activation_starts_audio`
- `stage6_chapter_embedded_timestamps_visible`

These are target markers for Step 3. They are not claimed as passed until the frozen Windows application emits them.

## 5. Preservation constraints

- AB-02 remains VERIFIED COMPLETE: do not rewrite M4B/MP4 validation, cached playback derivative generation, or the authoritative-source/cache identity contract.
- AB-07 remains VERIFIED COMPLETE: preserve completed output ownership and the project/title/cover/author/narrator/chapter association.
- Keep Premium V2 as the default interface.
- Do not pull Step 4 mini-player persistence/restart scope forward except where necessary to ensure the existing mini-player uses the same live player session.
- Do not weaken Stage 5.4/5.5 packaged acceptance. Preserve Stage 6 Step 2's four audiobook markers.

## 6. Exit gate

Step 3 may close only when:
1. Focused regression tests cover each AB-03 control, AB-04 embedded chapter behavior, active-chapter synchronization, stale-event/book-switch protection, and no-marker fallback.
2. The full regression suite and frontend JavaScript syntax validation pass on the intended source head.
3. The exact frozen Windows package passes the planned Step 3 real-audio markers plus the existing Stage 5.5 M4B playback and Stage 6 Step 2 audiobook-library markers.
4. The package produces its exact-head installer, portable package and SHA-256 manifest, with the existing release integrity and Defender checks passing.


## Implementation and CI checkpoint — 4 November 2026

The first Step 3 implementation commit is `ab08b17746a8a722bc3f8c97c8f00900a3e84a21`. It removes the late Play/Pause and timeline handler overrides, adds embedded chapter end intervals, playhead-driven active chapter state, chapter click/keyboard playback, and stale Audio callback guards.

- Run #41815672796: adapter syntax passed; packaged acceptance JavaScript syntax failed because the new block redeclared a top-level identifier. Corrected in `3594816b106f34ff07b4508eb7f0cf3386f61e33`.
- Run #41816006240: adapter and packaged acceptance JavaScript syntax passed; isolated Qt lifecycle passed; regression suite ran 1,150 tests with one failure caused by an exact-string regression contract requiring the established spacing in the position-save call. That formatting is restored in the next fix.
- The artifact-checkpoint packaging job did not run because the full regression step failed. Step 3 remains IN PROGRESS.

The next checkpoint adds the valid start/end interval guard for previous/next chapter navigation, explicit no-valid-marker regression coverage, and packaged checks for mini-player shared-audio behavior, keyboard chapter selection, saved rate/volume preferences, elapsed-time display and first/last chapter boundaries. These acceptance markers are required before AB-03/AB-04 can be signed off.

## Packaged CI failure review — 4 November 2026

The screenshot-listed runs #2282–#2285 are all complete and failed at the same packaged assertion. Their job reports show that the stage6_player_full_controls_actual_audio marker passed, then the harness timed out waiting for the mini-player to pause the selected audio. No subsequent Step 3 markers ran in those builds.

**Root cause:** the acceptance harness clicked #miniPlay while the Audiobooks page (#player) was active. The product intentionally hides the mini-player on that page. The test therefore interacted with a hidden control and did not prove a mini-player runtime defect. Source inspection confirms the full-player and mini-player buttons share playSelectedAudiobook; when the current media URL already matches the selected book, openPlayer toggles play/pause on the existing playerAudio.

**Correction prepared for the next single checkpoint:**
- Navigate to Dashboard, wait until the mini-player is actually visible and has a rendered client rect, then click Pause and Resume.
- Verify both the mini-player and full-player icons follow the same real Audio element and the Audio-instance count does not increase.
- Return to the Audiobooks page after the check.
- Add a source regression contract proving mainPlay and miniPlay share the selected-audiobook callback and same-URL openPlayer toggles the existing Audio element.

This is a correction to the test's page-state setup, not a weakening of the acceptance. The mini-player interaction remains a required real packaged test.

**Run discipline:** all runs #2282–#2285 are completed; there are no active Stage 6 Step 3 runs at this review point. Do not dispatch another checkpoint while one is active. Wait for the next single run to complete, inspect its final conclusion and failure markers, then fix the cause before dispatching any subsequent run.

**Current decision:** Step 3 remains IN PROGRESS. Source regression is green through 1,153 tests on the preceding commit; final packaged acceptance is still required.


## #2286 follow-up correction — 4 November 2026

#2286 passed 1,155 source tests but failed its Windows package job.

- The live Audiobook AI smoke received malformed core-pass JSON; the existing repair also failed and deterministic fallback was correctly reported. The core analysis now receives two bounded, compact, schema-aligned repair attempts. Fallback warnings remain strict failures in the live smoke.
- The mini-player test still failed after Dashboard navigation. The visibility predicate used a stale Audiobooks sidebar active label even when the player page panel was no longer visible. The rendered #player panel is now authoritative. Full and mini controls also share a direct toggle of the already-loaded Audio when its project folder matches, avoiding a backend round-trip race.

The original M4B, its embedded chapter table, and its browser-compatible playback derivative are not modified. Step 3 remains open pending one complete frozen Windows packaged acceptance.
