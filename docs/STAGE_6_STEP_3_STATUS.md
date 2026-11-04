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

## #2287 / #2288 review and next artifact checkpoint — 4 November 2026

- **Build #2287** (ce8c712...) stopped in the test job before Windows packaging. The failing test was test_core_ai_malformed_json_uses_two_compact_bounded_repair_attempts: it used inspect.getsource(AudiobookBrain.analyze_chapter), but app.ai.robust replaces that method with a wrapper. The source-contract test therefore inspected the wrapper rather than the implementation in app/ai/brain.py. This was a regression-contract defect, not an application-source failure.
- **Build #2288** (d908f8f...) corrected that contract to read app/ai/brain.py directly. All 1,157 regression tests passed. Its Windows build job was skipped because this commit was not labelled as an artifact checkpoint.
- The current source includes the rendered-page-authoritative mini-player visibility rule, direct same-audio play/pause toggle keyed by project folder, and two bounded compact JSON repair attempts for the core AI pass. Deterministic fallback remains warning-producing; the live AI smoke test remains strict.
- The M4B assembler, original chaptered M4B, embedded chapter markers, validation, and browser-compatible playback derivative remain preserved.

**Next action:** run one artifact checkpoint against the current d908f8f... source. Wait for that run to complete, inspect every failed step and packaged acceptance report, and fix any actual defect before creating another run. Do not stack checkpoints.

**Current decision:** Step 3 remains IN PROGRESS. Source regression is green (1,157 tests); final frozen Windows packaged acceptance and release artifact checks remain pending.
## #2289 packaged failure review — Production metadata gate — 4 November 2026

Run #2289 passed 1,157 regression tests, the live HTTP Audiobook AI smoke, frozen application verification, and bundled voice/critical-module checks. The packaged UI runner then failed in the Production metadata acceptance before reaching the later Step 3 controls.

**Root cause:** renderProductionMetadataGate correctly disabled full generation when Publisher was missing, but renderProductionGeneration later overwrote the button state using only whether an audio job was active. The metadata-save response also omitted metadata_complete and metadata_missing_fields, forcing the UI to wait for an asynchronous project refresh before updating its in-memory gate.

**Correction:** the save bridge now returns the persisted metadata fields plus the authoritative completion/missing-field state; the adapter updates the active project immediately from that response. Both the metadata renderer and generation renderer now combine metadata completeness, unsaved metadata state, and active audio jobs for full generation. Preview remains enabled when metadata is incomplete and no audio operation is active.

Run #2289's Music Library, cue, BGM, and preview checks before the Production metadata assertion passed. The six-second cue import exception in the log is the expected negative test. Step 3 remains IN PROGRESS until a subsequent single artifact-checkpoint reaches and passes the player acceptance markers and release-artifact checks.

## #2289 / #2290 follow-up — player preference persistence — 4 November 2026

- **Build #2289** failed at the Production metadata gate assertion. The following checkpoint, **Build #2290**, passed the full packaged metadata-dialog/history/save-error/Publisher-gate check. Preserve the correction already included in the current branch.
- **Build #2290** passed the packaged M4B source/decoder integration, embedded chapter metadata, full-player controls, and shared mini-player session checks, then timed out waiting for playback-rate and volume preferences to persist.
- The player control path applied the rate/volume to the live Audio element but dispatched settings.save as fire-and-forget work. Preference writes are now serialized, return their actual backend acknowledgement, remain retryable after an individual save error, and continue to use the validated native settings persistence.
- Packaged acceptance now waits for the save operations and verifies the authoritative player.get_active read-back contains 1.25x playback rate and 37% volume. A source regression contract covers the serialized/acknowledged save path.
- This is not a relaxation of acceptance: actual audio rate/volume behavior and persisted read-back remain required.

**Next action:** one artifact checkpoint on the latest Stage 6 branch head. Verify the new regression test, full source suite, frozen app, complete packaged acceptance, installer, Defender scan, hashes and uploaded installer/portable artifacts. Inspect any new failed step before another checkpoint; do not cancel an active run or supersede completed successful work.

**Current decision:** Stage 6 Step 3 remains IN PROGRESS. The two prior failures are diagnosed; the preference-persistence correction has source-level regression coverage, but matching-head CI and packaged Windows verification are still pending.

## Follow-up validation correction — 4 November 2026

- Intermediate runs #2291–#2296 were push-triggered source-test runs for successive small commits; their failures identified stale source-string assertions in existing UI tests and in the new player save-queue contract. The actual new player save regression passed before the retryable-queue refinement.
- Existing dashboard persistence assertions now check the shared save helper rather than the removed fire-and-forget calls. The new player regression checks the retryable serialized queue, awaited native save, both player preference keys, and settings sync.
- Run #2297 is the first artifact checkpoint for the player preference fix but was based on the immediately preceding commit, before these test-contract corrections. Its result must be treated as a validation checkpoint only; the final release checkpoint must run against the corrected branch HEAD.

**Current decision:** Stage 6 Step 3 remains IN PROGRESS. Do not mark complete or publish Version 1.2.0 until corrected-head tests, packaged frozen acceptance, Windows installer/portable artifacts, Defender and SHA-256 checks all pass.

## Corrected-head regression test status — 4 November 2026

- The first #2297 artifact-checkpoint regression run used the earlier test-contract revision and failed two assertions: the existing dashboard test still expected the removed direct fire-and-forget call, and the new Stage 6 test expected the queue before its retry guard was added.
- Both contracts are now corrected on branch HEAD: the Dashboard test asserts both preference paths route through savePlayerPreferences; the Stage 6 test asserts the catch-and-then serial queue, awaited settings.save, player read-back contract and backend persistence keys.
- #2297 is closed as a failed validation attempt and did not enter packaging. The current corrected-head checkpoint will establish the releasable state; no version bump or public release is authorized until it passes.

**Current decision:** Step 3 remains IN PROGRESS; matching-head source and packaged Windows verification remain mandatory.

## #2300 / #2301 packaged player-preference persistence review — 4 November 2026

- Both artifact checkpoints passed source regressions, frozen application verification, and bundled voice/critical-module checks. Both packaged acceptance runs reached the Stage 6 player controls after passing Sound Design, Music Library, Production metadata gate, Stage 5.3 preview/generation, M4B chapters, browser-compatible playback and mini-player shared-audio checks.
- Both packaged runs failed only at the final wait for persisted playback rate (1.25x) and volume (37%). The six-second cue rejection and deterministic cue/manifest/metadata save failures in the logs are required negative tests and did not fail their individual acceptance markers.
- The player UI applied rate and volume to the actual media and updated the active speed button, but `player.get_active` did not return the saved preference values. The prior asynchronous-save correction alone was therefore insufficient.
- Native read-back is now made explicit: `settings.get` returns validated `player_rate` and `player_volume`; `settings.save` returns those values in its acknowledgement; the player read path syncs QSettings before loading saved rate/volume. The frontend rejects an acknowledgement that does not match the requested value. Packaged acceptance checks both settings read-back and the player response, while regression tests cover these contracts.
- These changes are diagnostic and strict; no expected values or acceptance steps have been removed or reduced.

**Next action:** run one corrected-head artifact checkpoint. The exact required path is 1,159+ regression tests, frozen app, bundled assets, complete packaged acceptance including 1.25x / 37% preference persistence, then Inno Setup, functional HTML installer, logo verification, SHA-256, Defender and installer/portable uploads.

**Current decision:** Stage 6 Step 3 remains IN PROGRESS. #2300 and #2301 are failed historical checkpoints; #2301 passed source tests, freeze, and bundled assets, but its packaged acceptance timed out on player preference read-back. The new explicit acknowledgement/read-back correction has not yet been verified by CI.

## Mini-player / AI recovery audit and player preference root-cause correction — 4 November 2026

### Historical failures reviewed

- **#2286 — visible Dashboard mini-player acceptance:** packaged test failed while waiting for the visible mini-player to pause the selected audio. This was the original mini-player toggle issue.
- **#2287 — mini-player toggle + AI JSON recovery:** source regression failed because the test searched the wrapper `_safe_analyze_chapter` for `for repair_attempt in range(2)`, although the bounded retry loop belongs to `app/ai/brain.py` and the wrapper delegates to `_original_analyze_chapter`. This was a stale source-location assertion, not evidence that the live AI retry loop failed.
- **#2288 — AI repair regression contract:** the test contract was corrected; the full 1,157-test source suite passed.
- **#2306 — current packaged player issue:** the visible Dashboard mini-player shared-audio acceptance passed. The AI malformed-JSON bounded-repair test and all three mini-player source contracts also passed in the 1,159-test suite. The only packaged acceptance error was player rate/volume persistence.

### Root cause isolated

- A document-level capture-phase `click` handler intercepted the full-player speed buttons and called `stopImmediatePropagation()`, preventing the target `onclick` installed by `bindAudiobookPlayerControls()` from running.
- That capture handler changed `playerAudio.playbackRate` directly and updated the active button, but bypassed `applyPlayerRate()` / `savePlayerPreferences()`. This made the real audio speed and UI look correct while the durable settings remained unchanged, explaining the repeated timeout in #2290 and #2306.
- The speed-button capture handler now routes through `await applyPlayerRate(rate, true)`. On save failure, the shared handler already surfaces the error; the capture handler does not emit a second duplicate error.

### Guardrails added

- Added a source regression asserting the capture-phase speed branch calls `applyPlayerRate(rate, true)` and no longer writes `playerAudio.playbackRate` directly.
- Split packaged persistence acceptance into independent strict read-backs for volume (37%) and playback speed (1.25x). Both `settings.get` and `player.get_active` must confirm each value. The actual media controls remain separately asserted.
- No changes were made to the mini-player implementation or AI runtime/recovery implementation because their current regression and packaged checks are passing.

**Next action:** verify this targeted change with the source suite and one artifact checkpoint. Confirm mini-player shared-audio acceptance, AI bounded JSON repair, volume persistence and speed persistence; then complete installer, portable, Defender and SHA-256 gates. Do not close Step 3 or publish until all gates pass.

**Current decision:** Stage 6 Step 3 remains IN PROGRESS. #2286/#2287 historical causes are corrected and their current regression contracts pass; #2306 is a historical packaged preference failure. The capture-phase speed persistence correction is committed with targeted regression and isolated packaged acceptance, but matching-head CI/package verification is pending.

## Corrected player-speed source gate and latest regression verification — 4 November 2026

- Runs #2307–#2310 reached source regression but failed because `tests/test_premium_v2_integration_contract.py` still required the removed direct speed assignment `playerAudio.playbackRate = Number(audioLabel.replace(...))`. That assertion described the old non-persisting behavior and was incompatible with the new shared persisted-save path.
- The integration contract now inspects the capture-phase player handler, requires `await applyPlayerRate(rate, true)`, forbids the old direct assignment, and verifies the shared helper calls `savePlayerPreferences({player_rate:rate})`.
- **#2311 passed:** 1,160 tests in 52.824s, including the AI malformed-JSON bounded-repair test, the three mini-player source/acceptance contracts, the new player-speed persistence contract, and the updated legacy-control integration contract. JavaScript syntax and isolated native Qt lifecycle checks also passed.
- Packaged acceptance now checks player volume persistence and playback speed persistence separately, each requiring matching `settings.get` and `player.get_active` values. This retains strict 37% / 1.25x acceptance while making any future failure specific to one control.
- The application diff since #2306 is limited to `assets/frontend/premium_v2_backend_adapter.js`, `tests/stage2_packaged_sound_ui_acceptance.js`, `tests/test_stage6_audiobook_library.py`, `tests/test_premium_v2_integration_contract.py` and this status record. Mini-player and AI runtime implementation remain untouched.

**Next action:** run one artifact checkpoint against the corrected source state. Confirm 1,160+ regression tests, frozen app, bundled assets, packaged Sound Design and Stage 5.3 generation, mini-player shared-audio behavior, 37% volume persistence and 1.25x speed persistence; then continue installer, HTML installer, logo, SHA-256, Defender and artifact uploads.

**Current decision:** Stage 6 Step 3 remains IN PROGRESS. #2311 is a green source-test run; the packaged Windows acceptance and release artifacts still require matching-head verification.

## Frozen-app #2312 diagnosis and chapter-transport correction — 5 November 2026

- **#2312 source job passed:** the matching-head source suite passed; the frozen Windows app then completed all packaged checks through chapter keyboard activation.
- **Confirmed passing in #2312 packaged app:** Stage 6 full-player actual Play/Pause, Dashboard mini-player shared Audio object, volume 37% persistence, speed 1.25x persistence, 15-second seek clamp, embedded chapter timestamps, chapter selection/seek, playhead highlight, continuous chapter boundary tracking, and Enter/Space chapter activation.
- **Only packaged acceptance failure:** `Next moves to the last embedded chapter` timed out at `tests/stage2_packaged_sound_ui_acceptance.js` line 2343. The installer steps were correctly skipped because the full packaged acceptance gate had not passed.
- **Root cause:** the document-level click capture handler matched the visible `◀` and `▶` glyphs. In the real player markup the Previous and Next chapter buttons use those glyphs, while the distinct `#mainPlay` button also uses `▶`. The capture handler treated `◀` as a 15-second rewind and every `▶` as Play/Pause, then stopped the target handlers. This is why the first “Next” assertion could pass without moving (the playhead was already on the second chapter) while the meaningful first-to-second transition failed.
- **Correction committed:** removed the stale global capture-phase `#player` transport branch. Rewind, previous chapter, main Play/Pause, next chapter, forward and speed controls already have direct bindings (`bindAudiobookPlayerControls()` / shared `playSelectedAudiobook`) and now receive their intended click events without a competing capture handler.
- **Regression guard added:** `test_player_chapter_transport_is_not_intercepted_by_global_capture_handler` asserts no global `#player` capture branch remains, Previous/Next call `jumpPlayerChapter('previous'|'next')`, and full/mini Play/Pause share `playSelectedAudiobook`.
- The `play() request was interrupted by a call to pause()` console entries occurred around the packaged test's intentional preview cancellation / pause steps. The acceptance's terminal error was the chapter-navigation timeout; no separate change to playback error handling was made.

**Next action:** run source tests on the targeted fix, then one new artifact checkpoint. The frozen acceptance must demonstrate actual first-to-second and second-to-first chapter navigation, first/last boundary behavior, and preserve the already-passing mini-player, AI, 37% volume and 1.25x persistence checks. Only then proceed to Inno Setup, functional HTML installer, release hashes, logo and Defender gates.

**Current decision:** Step 3 remains IN PROGRESS. #2312 confirmed the previous mini-player/AI/player-preference acceptance; chapter navigation was its sole packaged blocker. The targeted capture-handler fix is committed but not yet verified by CI.

## Final direct-transport contract alignment and next checkpoint — 5 November 2026

- The first correction removing the global capture-phase player transport handler exposed two source contracts that still assumed the deleted handler existed: the Stage 6 speed test and the Premium V2 integration contract. These tests failed with `ValueError: substring not found`; they did not report a runtime player regression.
- Both contracts now validate the intended direct event paths: Previous/Next call `jumpPlayerChapter`, rewind/forward call the bounded `seekPlayerBy`, `#mainPlay` and `#miniPlay` share `playSelectedAudiobook`, and speed calls `applyPlayerRate(rate, true)` followed by `savePlayerPreferences`.
- **#2317** is running the full suite on the code and test-contract corrections. Frontend syntax and native Qt lifecycle gates passed; its full regression step is still in progress.
- **#2318** is the next frozen-app artifact checkpoint and includes the latest source plus both corrected contracts. It must re-run the packaged test that previously failed at Next-to-second-chapter navigation.

**Acceptance focus:** confirm Next from the first embedded chapter seeks to the second marker, Previous returns to the first, first/last boundaries stay clamped, and all previously passed packaged checks (mini-player shared audio; 37% volume and 1.25x speed persistence; keyboard chapter selection; AI recovery regression) remain green. Do not skip packaged acceptance or close Step 3 on source tests alone.
