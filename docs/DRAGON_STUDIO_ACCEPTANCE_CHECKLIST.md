# Ryu's Audiobook — Dragon Studio Acceptance Checklist

**Baseline:** `docs/prototypes/Ryus_Audiobook_Dragon_Studio_Premium_Final.html`  
**Behavioral contract:** `docs/UI_UX_IMPLEMENTATION_SPEC.md`  
**Branch:** `fix/import-qa-speaker-hover-hardware`  
**Rule:** A control is accepted only when its real desktop-app action is connected, its result is observable, state persists where expected, and a regression test or documented manual test proves it. A visual-only match does not pass.

## Release gates

- [ ] **G0 — Preserve existing features:** compare against the current implementation before modifying a screen; no previously available capability may silently disappear.
- [ ] **G1 — Critical reliability:** custom voice propagation, character discovery/assignment, empty-chapter handling, Generate navigation, preview target duration, progress/elapsed time, and recovery paths verified.
- [ ] **G2 — Screen parity:** all 14 HTML navigation destinations checked individually using the criteria below.
- [ ] **G3 — Production acceptance:** actual audio generation, M4B chapters/metadata/cover/bitrate, pause/resume/cancel/retry, and offline/local-first behavior tested.
- [ ] **G4 — Windows packaging:** current commit's tests, frozen-app validation, bundled assets, installer and portable build succeed; launch and core smoke test run against that exact build.
- [ ] **G5 — Cleanup/release:** older CI artifacts cleaned only as intended; do not share an EXE unless it is traceable to a successful validated commit.

## Screen-by-screen checklist

### 1. Dashboard — HTML `#dashboard`
- [ ] Summary counts come from real local projects, not hard-coded prototype values.
- [ ] Open Library and Import Book route to the correct screens.
- [ ] Recent/active project cards open the selected project and preserve project identity.
- [ ] Resume-generation action reports the actual project/job state.
- [ ] Notifications and global mini-player actions work without blocking navigation.

### 2. Library — HTML `#library`
- [ ] Search filters real projects by supported metadata.
- [ ] Status filters (all/active/completed/attention) match actual project state.
- [ ] Open, rename, delete single, and multi-select/delete actions behave safely where supported.
- [ ] Empty states, invalid/missing project folders, and interrupted projects have clear recovery guidance.
- [ ] Returning to a project restores its selected book and saved metadata.

### 3. Import Studio — HTML `#import`
- [ ] Browse and drag/drop accept supported formats and reject unsupported/corrupt inputs clearly.
- [ ] Extraction runs off the UI thread; UI stays responsive.
- [ ] Progress, cancellation/error reporting, and extracted-text preview are accurate.
- [ ] Author/title/cover metadata and output folder persist as appropriate.
- [ ] Imported text is not silently truncated; chapter/word coverage is checked.

### 4. Chapter Studio — HTML `#chapters`
- [ ] Chapter detection/re-detection retains manual edits unless the user confirms replacement.
- [ ] Rename, reorder, split, merge, edit, delete, and multi-select actions work where available.
- [ ] Text cleanup preserves headings, paragraph breaks, dialogue, and non-English text.
- [ ] Empty/whitespace-only chapters are clearly identified; generation can skip or request repair without silently aborting unrelated valid chapters.
- [ ] Autosave/state survives screen changes and app restart; current book title remains visible.

### 5. Voice Studio — HTML `#voices`
- [ ] Built-in/provider/backend selectors and filters affect the real voice catalogue.
- [ ] Custom/reference voice imports validate the audio and persist a named profile.
- [ ] Selected profile is the same profile used by preview and full-book generation.
- [ ] Preview duration choices (10/20/30/45/60 seconds) are respected within reasonable tolerance; actual duration is reported.
- [ ] Preview has in-app play/pause/stop and progress/elapsed feedback; no unexpected external player.
- [ ] Voice profile changes persist and stale profile selections cannot override the current choice.
- [ ] Missing model/runtime/provider failures are actionable and do not freeze the UI.

### 6. Character Studio — HTML `#characters`
- [ ] Analyze runs in a worker and leaves the UI responsive.
- [ ] Quoted dialogue, Japanese quote marks, and em-dash dialogue are handled by supported analysis paths.
- [ ] Dialogue cue count, discovered candidates, confidence, and unassigned dialogue are distinguishable.
- [ ] Search, dialogue examples, manual character add/rename, voice assignment/removal, and low-confidence review work.
- [ ] Unassigned dialogue follows the configured narrator fallback.
- [ ] Manual speaker assignments persist and are honored by full generation.

### 7. Pronunciation Studio — HTML `#pronunciation`
- [ ] Add/edit/delete entries validate written form and pronunciation.
- [ ] Search and Current Book / Global Library scopes show the correct entries.
- [ ] Book-specific entries override global entries for the same written form.
- [ ] Preview uses the same pronunciation rules as full generation.
- [ ] Common words are not given harmful false-positive suggestions; Japanese names and user overrides are preserved.

### 8. Sound Design Studio — HTML `#sound`
- [ ] Search and category filters operate on actual installed/imported catalogue tracks.
- [ ] Auto/manual music selection and volumes affect preview and final output.
- [ ] Opening, chapter/page-turn, scene-transition, and closing cues are independently selectable and audible where configured.
- [ ] Local custom audio can be imported, previewed, and persisted.
- [ ] Presets can be saved, applied, and deleted; applying a preset must not fail because a track is hidden by an active filter.
- [ ] Cue/music controls continue to work when background music is disabled.
- [ ] Catalogue content and licensing are verified before claiming a 1,000+ track library.

### 9. Production Studio — HTML `#generate`
- [ ] Readiness checks identify missing text, voices, assets, output folder, and metadata before starting.
- [ ] Preview generation, selected-chapter generation, and full-book generation target the intended content.
- [ ] Progress percentage, current stage/chapter, elapsed time, and ETA reflect actual work without jumping to 100% prematurely.
- [ ] Pause/resume occurs at safe checkpoints; cancel stops work cleanly; retry/resume reuse valid completed chunks.
- [ ] Provider outages stop cascading failures and explain which chapter failed.
- [ ] M4B contains expected chapters, metadata, cover art, and measured output bitrate.
- [ ] Empty chapters do not cause the entire book to fail without a useful recovery path.

### 10. Audiobooks / Player — HTML `#player`
- [ ] Completed local audiobooks are listed with real title/author/cover/duration.
- [ ] Play/pause, seek, chapter navigation, current time, and duration work.
- [ ] Mini-player and full player remain synchronized.
- [ ] Open output folder and file-not-found recovery work.
- [ ] Playback does not unexpectedly open an external media player.

### 11. Generation History — HTML `#history`
- [ ] History reflects real jobs and actual completion/failure/cancelled states.
- [ ] Filters and search narrow actual history records.
- [ ] Failed/interrupted jobs expose useful details and valid retry/resume actions.
- [ ] Removing history entries does not accidentally delete source books or finished audio.

### 12. Models Center — HTML `#models`
- [ ] Installed/available local models and runtimes are reported truthfully.
- [ ] Install, refresh, verify, and repair actions are connected to real local operations.
- [ ] Offline-first behavior is explicit; no fake online update status.
- [ ] Model/runtime errors identify missing dependencies and safe next steps.
- [ ] Voice models required by the current profile are checked before generation.

### 13. Performance Center — HTML `#performance`
- [ ] Hardware detection reports actual CPU, RAM, GPU, VRAM, and backend availability where supported.
- [ ] Benchmark runs safely and shows measured results, not placeholder values.
- [ ] Recommendations account for low-VRAM devices and avoid promising unsupported acceleration.
- [ ] Diagnostics do not block normal navigation and can be rerun.

### 14. Settings — HTML `#settings`
- [ ] Theme, accent, interface scale, audio bitrate, storage, speech/generation, library, diagnostics, and About controls are connected.
- [ ] Saved appearance settings apply after restart in both themes.
- [ ] Global default bitrate applies to new projects; an explicit saved project setting takes precedence.
- [ ] Local data/output paths and cleanup actions show what will be affected before destructive changes.
- [ ] Settings survive restart and do not reset unrelated preferences.

## Critical bug regression checklist

- [ ] Custom voice: import → save profile → select → preview → close/reopen → generate; confirm the exact voice/profile propagates throughout.
- [ ] Characters: use fixtures with quoted dialogue, speaker tags, and em-dash dialogue; verify nonzero characters when names/speaker cues are present, and verify manual override.
- [ ] Empty chapters: valid chapter + empty chapter + valid chapter; verify the user gets a clear warning and the chosen skip/repair policy is applied without silently discarding valid chapters.
- [ ] Preview duration: test 10/20/30/45/60 seconds for at least one local provider and one custom voice; record requested vs actual durations.
- [ ] UI responsiveness: test model startup and long preview/generation; no blocking popup or false “not responding” condition from main-thread work.
- [ ] Progress: test successful, failed, cancelled, paused/resumed, and resumed-from-partial jobs.
- [ ] Sound cues: test opening/page-turn/scene/closing independently with BGM on and off.
- [ ] M4B: inspect chapter markers, metadata, cover, duration, and actual bitrate using a media probe.
- [ ] Windows installer: fresh install, launch, first-run, one short preview, one short M4B, uninstall, and leftover-data behavior.

## Evidence log

For every accepted item, record:
- Commit SHA and build/run ID.
- Test name or manual test steps.
- Expected result and observed result.
- Artifact/build used for the manual test.
- Any limitation or platform-specific caveat.

**Current status:** checklist created as the acceptance contract. Items remain unchecked until evidence is recorded against the current commit; passing CI alone does not establish full product acceptance.
