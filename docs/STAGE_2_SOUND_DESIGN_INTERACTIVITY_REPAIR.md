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
