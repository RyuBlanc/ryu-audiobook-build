# Stage 2 Substage — Sound Design Interactivity Repair

## Status

- **Code:** merged into `stage-2/sound-design-music-library-post-stage1`.
- **Automated regression gate:** passed on the merged branch in run [#1679](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40916734383): JavaScript syntax validation passed; 785 Python tests passed.
- **Windows artifact checkpoint:** triggered by the commit adding this note; the run result is the release gate for this source revision.
- **Hands-on Windows acceptance:** pending. Do not mark this substage closed until the checklist below is completed against the built artifact and the generated audio is auditioned.

## Latest continuation checkpoint — 30 October 2026

- **Working branch:** `stage-2/sound-design-music-library-post-stage1`
- **Verified test commit:** `c66ffe5c103f49157442d2f41956e58339902b6f`
- **Test run:** [#1719](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41028308917) — passed.
- **Regression result:** 831 tests passed in 31.507 seconds; Premium V2 backend-adapter JavaScript syntax validation passed.
- **Failure corrections:** #1717's three obsolete inline-save assertions were replaced by assertions against the shared `flushSoundDesignState()` implementation and its call sites. #1718's event-handler slice was replaced with balanced-brace JavaScript extraction, and the strategy-save ordering assertion now verifies that the chapter draft is flushed before the strategy is persisted.
- **Scope of this checkpoint:** The corrective code change is limited to regression-test extraction and assertions. It does not claim that the 24 SD/MUS requirements have all passed manual acceptance.
- **Artifact status at #1719:** The Windows build job was skipped because this was an ordinary test commit, not an artifact-checkpoint event. The previously recorded #1697 artifact predates commits #1716–#1719 and does not validate them.
- **Next gate:** Run the dedicated `[artifact-checkpoint]` workflow against the same integrated Stage 2 code, then verify the Windows package and complete the installed-app/audio checklist below. Keep all unchecked runtime items open until evidence is recorded.

## Repairs in this substage

- Restored click navigation across Music Library, Chapter BGM, Opening & Cues, and Mix & Production Sync.
- Preserved chapter BGM assignments when switching to Same BGM, and restored the saved book-default track when returning to Same BGM.
- Enforced the 50% maximum for book-default and chapter BGM through the UI, host, generation manager, and final mixer.
- Added selected-cue Play/Pause/Replay and an explicit Save Cue Changes workflow, including staged clear-all behavior and retained unsaved edits after save failure.
- Separated cue assets from music assets in the catalogue and assignment pickers; rejected cue assets longer than five seconds.
- Added saved narration and cue level controls; wired their gains through full-book preview and final assembly.
- Added guards so selecting an unconfirmed music candidate does not silently replace the saved book-default track.
- Made the Production handoff save pending chapter BGM, cue assignments, and mix-level changes before navigating.

## Manual acceptance checklist

### Music Library
- [ ] All categories, search/filter, import/category selection, and track selection work in the packaged Windows app.
- [ ] The selected music track plays, pauses/resumes, and switches correctly when a different track is selected.
- [ ] Saving the book-default track is explicit; selecting a candidate alone does not replace the saved default.
- [ ] Master BGM volume displays the percentage, is capped at 50%, persists after navigation/project reopen, and changes the audible preview/final output.

### Chapter BGM
- [ ] The Chapter BGM tab opens and all chapter rows are interactive.
- [ ] Assign tracks to chapters, switch between Chapter-Based BGM and Same BGM, then switch back; assignments are retained and the saved book-default track is restored.
- [ ] An unassigned chapter in Chapter-Based mode does not fall back to the book-default track.
- [ ] Per-chapter volume is visibly capped at 50%; start offset and end behavior save and affect preview/final output.
- [ ] Changing chapters or leaving the tab does not discard an unsaved chapter edit or freeze the panel.

### Opening & Cues
- [ ] The cue catalogue contains cue assets, not music tracks; built-in and imported cues are classified correctly.
- [ ] Selected cue Play/Pause/Replay plays the selected clip, not another track.
- [ ] Slot assignments and Clear All remain staged until **Save Cue Changes** is pressed; save errors leave unsaved changes visible.
- [ ] Cue clips longer than five seconds cannot be imported or assigned.
- [ ] The saved opening, next-chapter, and closing cues are heard at the configured cue level; Voice Only/BGM Off excludes BGM and all fixed cues.

### Mix & Production Sync
- [ ] The Mix & Production Sync tab opens and its values reflect saved backend data rather than defaults/sample values.
- [ ] Narration (0–100%), cue (0–50%), and BGM (0–50%) controls save, persist, and change the audible mix.
- [ ] Save & Open Production Studio saves pending chapter/cue/mix changes before navigation and does not report success if saving fails.
- [ ] Preview and final generation use the same saved assignments and volume levels; listen for correct narration/BGM/cue balance.

### Restart / persistence
- [ ] Close and reopen the packaged app and project; verify strategy, book default, chapter assignments/timing/volume, cue assignments, and mix levels remain saved.
- [ ] Record the packaged app version, project used, acceptance result, and any remaining defect before closing this substage.

## Expanded packaged Stage 2 acceptance — failure diagnosis and regression correction (31 October 2026)

- [#1766](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41148980962) and [#1767](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41149365779) both passed the complete pre-package regression suite, Windows freeze, frozen executable self-test, and bundled model/voice asset verification. Both stopped at the first Chapter BGM row-selection wait after the expanded Music Library and category acceptance had passed.
- The failure was in the browser acceptance driver, not the application’s Chapter BGM implementation. The chapter-row click handler calls `renderChapterBgm()`; that renderer intentionally replaces the list with `list.innerHTML = rows.map(...)`. The test held a reference to the old button and polled that detached element for its active class. The newly rendered row was not queried, so the wait timed out even though the live list was rebuilt. The six-second cue import rejection in both logs was the deliberate negative test and had already been recorded as passed.
- Driver correction: `c698ad3ee0c9ca01b39d2dfad02d304618709d68` now keeps a selector rather than a DOM element and re-queries the current Chapter BGM row on every wait poll. The production event handler and renderer were not modified.
- Regression lock: `005089a0bbf6cd977653b0c27a56693fff73e178` adds `test_chapter_selection_wait_requeries_row_after_real_renderer_rebuild`, asserting the browser test checks the replacement DOM node and the app renderer performs the expected list rebuild.
- [#1768](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41151354178) passed on the driver correction: JavaScript syntax validation passed; **845 tests passed in 37.005 seconds**.
- [#1769](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41151365205) passed on final source head `005089a0bbf6cd977653b0c27a56693fff73e178`: JavaScript syntax validation passed; **846 tests passed in 40.459 seconds**, including the new stale-DOM regression test.
- The next single artifact checkpoint runs the complete expanded frozen Windows flow: all Music categories and source results; cue limits/classification/cards/playback; Chapter BGM source/category filters, explicit selection, per-chapter levels/offset/end rules, Same/Chapter-Based round-trip and no fallback; cue three-slot autosave, failed-save recovery and explicit Clear All; Mix values; real full-book previews in Same and Chapter-Based modes and Voice Only; Production handoff failure/retry and generation-toggle sync; Dashboard project switching; JSON/asset validation; and a second frozen-app process restart. Keep all SD/MUS requirements open until this Windows package acceptance and restart phase pass.

## Chapter BGM acceptance save-lock correction — Runs #1770–#1772 (31 October 2026)

- [#1770](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41151837241) passed the full 846-test regression suite, Windows freeze, frozen executable verification, and bundled voice/critical-module verification. The expanded packaged Stage 2 acceptance passed Music Library and all eight category/source checks, cue classification and real cue playback, then stopped at the Chapter BGM persisted-values assertion.
- The six-second cue-import rejection reported in the same log was the intended negative test and had already passed. It was not the failure cause.
- The actual Chapter BGM interaction sequence exposed a race in the acceptance driver: pressing the chapter track's explicit **Select** action saves asynchronously. During that save/refresh, the application intentionally disables the chapter editor controls and only re-enables them after the saved state has been reloaded and the status becomes `Chapter assignment saved.`. The driver previously waited only for the saved track path, which appears before the UI save/refresh finishes, then edited the disabled volume/offset/end controls. The refresh could restore saved values over those early edits.
- Driver correction: commit `04d444932ccce039397f3e8f85d3f67e19be028b` adds `waitForChapterSaveComplete()`. The driver now waits for the selected track, completed-save status, and all editor controls to be enabled before editing chapter timing/volume. Its explicit save wait checks the exact saved volume, start offset and end behavior for Chapter One and Two and includes actual stored values in failure diagnostics. Chapter Three No BGM remains explicitly checked. No application production code was changed.
- [#1771](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41153009841) ran 847 tests and found one error in the new Python regression contract: its text-slice boundary searched for `selectChapter()` after the save helper even though `selectChapter()` is defined earlier in the browser driver. The packaged driver code itself passed the JavaScript syntax check.
- Regression-contract correction: commit `ebc746ac2b3bdd2b9d040cd159868e12fada2772` now ends the helper source slice at the first `await selectChapter(1);` workflow call. The behavioural assertions were not removed or relaxed.
- [#1772](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41153261441) passed on `ebc746ac2b3bdd2b9d040cd159868e12fada2772`: frontend JavaScript syntax validation passed; **847 tests passed in 45.760 seconds**.
- Next gate: run the consolidated Windows package acceptance again on this exact tested code. It must pass chapter assignment save completion/values, Same/Chapter-Based switching and no fallback, both full-book preview strategies, Voice Only preview, cue save failure/retry and explicit Clear All, Mix/Production handoff, project switching, and the second frozen-app restart/persistence phase. Keep all SD/MUS requirement IDs open until that packaged acceptance passes.

## Cue save failure visibility correction — 31 October 2026

- [#1773](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41153517668) passed the full 847-test regression suite, Windows build, frozen executable checks and the Music/Chapter BGM/Cue preview assertions up to cue-save failure recovery. The deterministic `sound.cues.save` failure was injected and logged, but the browser driver timed out waiting for the visible `Save failed` status.
- The adapter previously stored the failure message only in the immediate save function's DOM write. `refreshSoundCues()` independently recalculated the status from dirty/pending flags and could replace that failure with a generic draft message during a concurrent catalogue refresh. This made a failed save difficult to distinguish from a pending draft and made retry feedback unreliable under refresh.
- Production correction: retain `cueSaveError` as adapter state; catalogue refreshes preserve it; a new edit clears the prior error; starting a retry clears it; only a successful save ends the error state. The failed assignment is not reported as saved and the draft is not discarded.
- Packaged acceptance now forces a cue catalogue refresh after the injected failed autosave, verifies the old backend assignment remains unchanged, verifies the unsaved draft remains visible and retryable, then retries explicitly and requires the saved-state indicator.
- Keep Stage 2 open until the combined Windows package acceptance and restart phase pass.

## Auto-save error-path correction — #1774 (31 October 2026)

- [#1774](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41155578190) passed the 848-test regression suite, JavaScript validation, executable freeze, and bundled voice/critical-module verification. Its expanded packaged acceptance passed Music Library filtering/import/playback, all eight category results, Chapter BGM filters/assignments/levels/offsets/end policies/no-fallback, Same/Chapter-Based strategy round-trip, and all three cue-slot autosaves. It then timed out waiting for the visible error after the deterministic cue-save rejection.
- Inspection of the actual timer-driven path showed `scheduleCueAutoSave()` had its own outer `catch` that only emitted a toast, while its status writer always wrote the generic unsaved text. The earlier #1774 correction persisted the inner `savePendingCueChanges()` error and refresh status but did not correct that scheduler-owned UI writer. Therefore the frozen acceptance failure was a real remaining UI-state defect, not a new Music/Chapter BGM regression.
- Corrective change: the scheduler now mirrors failure into `cueSaveError`, the visible `#cueSaveState`, and the retry button; future autosave scheduling does not overwrite or silently retry a latched failure. A new user draft clears the old error, and the explicit Save Cue Changes retry clears it on start and on success. The regression contract now inspects the scheduler catch/guard as well as the core save and refresh paths.
- Re-run the consolidated Stage 2 frozen package gate on this correction. Stage 2 remains open until that packaged gate passes.

## Mix & Production Sync multi-slider draft race — #1775 follow-up (31 October 2026)

- [#1775](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41156681408) passed the regression-test job, Windows freeze, frozen executable verification and bundled voice/module checks. The expanded packaged acceptance then timed out waiting for the persisted BGM, narration and cue levels in Mix & Production Sync. All preceding Music Library, chapter assignment/strategy, cue catalogue/playback, cue save/retry and Clear All assertions had passed.
- Root cause: `renderSoundMixSummary()` rehydrated every inactive level slider from the last saved backend state even while `mixLevelsDirty` was true. Moving focus from BGM to narration to cue triggered a summary render between edits; that render could overwrite a previously edited, still-unsaved control before the shared manifest save completed. This was an application draft-state race, not a timeout-only test issue.
- Production fix: commit `2cee813fb75325ec9a80f462cf16220d410e2502` guards saved-value hydration of all three controls while any mix-level draft is dirty. After a revision-stable manifest save succeeds, the adapter clears the dirty flag and renders the saved values. Failed saves retain the user's visible draft instead of silently reverting it.
- Regression coverage: `test_mix_summary_preserves_all_pending_slider_drafts` verifies all three controls are protected while dirty and the saved state is re-rendered only after a stable save.
- Regression workflow [#1776](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41162555323) is the test gate for commit `2cee813`. This follow-on artifact checkpoint is allowed to package only if the full regression job succeeds. Its result must be recorded before marking any Stage 2 requirement complete.
- Stage 2 remains open: this correction addresses the currently observed Mix-level acceptance failure only. The entire 24-item SD/MUS scope, PROD-09/10/11 integration checks, expanded packaged flow, restart persistence and required installed-Windows/audio acceptance must all be evidenced before closure.

## Voice Only full-book preview cue isolation — #1777 follow-up (31 October 2026)

- Packaged [run #1777](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41162659156) verified that the #1775 mix-slider defect was resolved: `mix_summary_and_saved_three_levels` passed with the real 42%/82%/30% values, and both Same BGM and Chapter-Based full-book previews rendered successfully.
- The next failing assertion was Voice Only preview timeline reduction. The saved Voice Only state was confirmed as `background_audio_mode=off` and `bgm_enabled=false`, but the full-book preview worker still forwarded retained BGM paths, cue paths, chapter overrides and the historical transition flag to the mixer. This relied entirely on downstream suppression and did not expose the effective sound configuration in the completed job result.
- The follow-up makes `full_book_preview` fail closed at the preview boundary: when the effective mode is off, it passes no BGM, ambience, chapter overrides or fixed cue paths and forces the fixed-cue flag off. Saved user preferences remain intact in project state for later re-enabling. The job result records effective mode and cue-slot inclusion for runtime verification. The Production Studio full-generation path now applies the same gate before constructing `GenerationManager`, preventing Voice Only from forwarding retained cue/music paths to the final-generation pipeline.
- Unit coverage `test_full_book_voice_only_strips_saved_sound_assets_before_mixer` asserts that Voice Only passes no inactive BGM/cue assets to the real assembler interface. Packaged acceptance now checks the reported effective configuration in Same BGM, Chapter-Based and Voice Only, and reports the measured preview-duration delta. It allows 0.5 seconds of AAC timing tolerance while still requiring the fixed cue timeline to disappear.
- The full 24-item SD/MUS requirement set and PROD-09/10/11 integration requirements remain in scope. Run #1777 did not produce installer/portable artifacts because the acceptance step failed; do not mark Stage 2 complete until the new packaged acceptance, restart checks, remaining production checks and installed-Windows/audio acceptance pass.

## Stage 2 Voice Only + full SD/MUS packaged checkpoint — run #1783 (31 October 2026)

- Tested source commit: `4a8b7e27d89fdf0ddb3785b606a129424dd119ea` on `stage-2/sound-design-music-library-post-stage1`.
- Regression workflow [#1783](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41164730175) passed **850 tests** (35.713 seconds); frontend JavaScript syntax validation also passed.
- This source includes the Mix & Production Sync draft-preservation fix from `2cee813` (the three unsaved BGM/narration/cue level drafts can no longer be overwritten by a summary render). The prior packaged [#1777](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41162659156) confirmed the real saved 42%/82%/30% values and both Same BGM and Chapter-Based full-book previews worked.
- Voice Only is enforced before both full-book preview and final Production generation: when `effective_background_audio_mode` is `off`, no retained book BGM, ambience, chapter overrides, auto-music variation or Opening/Next Chapter/Closing cue paths are passed to the mixer/GenerationManager; the fixed-cue flag is false. Saved preferences remain stored so switching BGM back on can restore them.
- Full-book preview job results expose effective mode and cue-slot inclusion. The packaged test verifies cue slots are included for both BGM strategies and excluded for Voice Only; it records actual preview durations and allows up to 0.5 seconds AAC timing tolerance while requiring at least 11.5 seconds of cue timeline to be removed.
- Regression contract tests were updated to assert the new fail-closed production and preview argument handling rather than obsolete ungated source expressions. The current `850/850` regression gate is green.
- This checkpoint now authorizes the frozen Windows packaged acceptance for the exact tested source. Required packaged checks remain: Same BGM/Chapter-Based/Voice Only audio output, failed-save handoff blocking and retry, Production toggle synchronization, project isolation, primary-project restoration, second-process restart persistence, Music Library metadata and final artifact upload.
- **Stage 2 remains OPEN.** Do not mark SD-01..SD-15 or MUS-01..MUS-09 complete solely from this regression pass. Close only against the full packaged acceptance and its persistence evidence, then complete installed-Windows/audio acceptance; PROD-09/10/11 summary and unique-track integration rules remain in scope. Do not bump the app version or publish Version 1.2.0 before acceptance.


## Voice Only being re-enabled by a later volume flush — #1784 follow-up (31 October 2026)

- Packaged [run #1784](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41164945443) passed the 850-test regression gate, frozen executable build, executable verification and bundled voice/module checks. The packaged acceptance again verified the Mix-level fix: all three saved levels were correct, and Same BGM and Chapter-Based previews passed.
- The failure was after the UI had persisted and returned Voice Only (background_audio_mode=off, bgm_enabled=false). The subsequent Preview Book action calls flushSoundDesignState(), which saves mix levels. The generic currentSoundManifestPayload() included enabled: chapterBgmState.bgm_enabled; a stale frontend snapshot could therefore overwrite the backend's newer Voice Only mode during this unrelated volume save, changing the preview's effective mode back to manual.
- Fix: generic mix-level/path/fade manifest saves no longer send the global enabled property. _sound_save_manifest() now preserves effective_background_audio_mode(state) when that property is absent. Only an explicit master toggle request that includes enabled may change the saved mode. The backend preserves auto as well as manual/off; Chapter-Based BGM remains enabled with no book-default track when that was the saved mode.
- Regression coverage adds a real bridge/state test for both directions: a volume-only save cannot re-enable Voice Only, and it cannot disable Chapter-Based BGM where the book track path is intentionally empty. A frontend/source contract verifies mix-level saves omit enabled and the master toggle still passes it explicitly. The packaged test from #1784 already observes the post-flush mode via the actual preview job result; it remains unchanged so the runtime assertion can prove this fix.
- Stage 2 remains OPEN until a fresh regression gate and full packaged acceptance pass, including the Voice Only preview, Production handoff/retry, project isolation and second-process persistence. No Version 1.2.0 version bump or release is authorised before the complete acceptance.

## Artifact checkpoint — Voice Only mode preservation (run #1785 regression evidence)

- Fix commit `dd44ad077f9b1c9bf21c5181a1419ff28edf4f05` is on `stage-2/sound-design-music-library-post-stage1`.
- Regression workflow [#1785](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41166134715) completed successfully: **852 tests passed in 31.025 seconds**; frontend JavaScript syntax validation also passed.
- The fix removes the renderer-cached global enabled flag from generic mix-level manifest payloads. The backend preserves the saved effective audio mode when `enabled` is omitted; only an explicit master-toggle request changes it. This preserves Voice Only while retaining preferred BGM/cue assignments for later use, and also preserves enabled Chapter-Based BGM with no book-default path.
- New regression tests passed: `test_mix_level_manifest_saves_do_not_rewrite_global_bgm_toggle` and `test_level_only_manifest_update_preserves_saved_global_mode`.
- This commit authorizes a fresh frozen Windows artifact checkpoint on the exact tested source. The previous packaged #1784 run remains failed and is not evidence of acceptance. The new package must prove Voice Only preview configuration is off with all three cue slots excluded, then pass Production handoff/retry, mode synchronization, project isolation, primary-project restoration, restart persistence and upload/release verification.
- Stage 2 remains OPEN; the 24 SD/MUS requirements and PROD-09/10/11 are not closed by the regression suite alone. Do not publish Version 1.2.0 or mark the stage complete until packaged and installed-app acceptance pass.
