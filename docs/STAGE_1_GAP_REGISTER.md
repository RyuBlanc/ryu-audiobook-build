# Stage 1 Gap Register — Ryu's Audiobook Premium V2

**Updated:** 24 October 2026 (Models Center and job-monitor follow-up)
**Audited code:** `eca9cf1a8330e2dcfce697f66233a73740e25ae0`
**Working branch:** `fix/import-qa-speaker-hover-hardware`
**Rule:** status is based on source inspection or named test evidence. A registered handler or successful build alone does not mean the user-facing workflow is accepted.

## Follow-up audit — previous UI comparison and interaction polish (21 October 2026)

### Confirmed frontend findings

- The previous full-app prototype has 14 sidebar destinations; Premium V2 has 15 (adds Help & Guide). The new screen contains more controls, so raw ID changes are not evidence that a feature was removed.
- Previous control IDs that no longer exist include `voiceGrid`, `voiceWave`, `voicePlay`, `voiceStop`, `selectedVoice`, `characterList`, `characterName`, `characterVoice`, `characterVoiceSelect`, `assignVoice`, `addPronunciation`, `pronSearch`, `pronTable`, `saveSoundPreset`, `trackGrid`, `selectedTrack`, `musicVolumeValue`, `musicVolume`, `saveSettings`, and `themeSelect`. Several have likely equivalents in the expanded UI (for example, advanced Voice Studio, Character Studio, Pronunciation Studio, Sound Design, and advanced Settings), but each needs a semantic parity check before classifying it as truly removed.
- The Import → Chapters → Narrator → Characters → Pronunciation → Sound → Generate tracker initially had static `is-done`, `has-warning`, and `is-current` classes. This could show Generate as active regardless of the page and sample completion/review states regardless of the current project. The frontend has now been changed so the tracker follows the current screen, and static sample completion/warning states are cleared. A regression test was added; CI verification is pending.
- The sidebar already toggles its active navigation class in `go(id)`; the top workflow tracker did not reliably follow navigation.
- The HTML has legacy timer-driven import/generation/benchmark/player behavior and sample dashboard data. The adapter intercepts some actions, not every control. Remaining prototype paths must be audited and neutralized individually; do not use blanket event suppression that could break legitimate interactions.
- The adapter polls jobs every 1.5 seconds and rebuilds the background-job list with `innerHTML`. This is a confirmed unnecessary DOM replacement path and a potential flicker source, particularly while the job panel is open. Main-screen flicker still requires profiling in the packaged WebEngine app before assigning a single root cause.
- Startup `wire()` performs a sequence of broad refreshes across projects, voices, chapters, characters, pronunciation, sound, jobs, history, models, performance and settings. This creates a heavy startup burst; measure and stage these reads rather than indiscriminately refreshing all screens.

### Backend gaps already confirmed by source audit

1. Project lifecycle: `project.create` is unavailable as a standalone command; duplicate/archive/delete/export and backup/restore commands are not exposed.
2. Chapter editing: find/replace, undo/redo and safe re-detection protection remain incomplete or UI-local; verify persistence and conflict handling.
3. Dialogue/casting: source-backed manual assignment exists, but bulk AI acceptance/prediction remains guarded; confirm assign/unassign visibility and actual synthesis routing in Windows.
4. Voice provider: preview/profile commands exist, but provider/model/voice ID/duration need real-provider acceptance. Premium cloud candidate generation and secure provider credential management are explicitly not connected.
5. Production: dedicated preflight, retry/rebuild, immutable history detail and durable checkpoint recovery are incomplete/unverified.
6. Pronunciation: import/export, conflict tracking, per-profile test-result storage and invalidation of affected audio are not complete.
7. Sound: catalog/import/assignment commands exist; licensing, real playback, loudness, missing files, ducking/fades and preview-vs-final mix remain unaccepted.
8. Player: output metadata and transport exist; persisted resume position/bookmarks and robust chapter timeline persistence are not evidenced.
9. Models: `models.list`, `models.install`, `models.verify`, `models.repair` and `models.uninstall` are connected for supported local components. Lifecycle work runs as a guarded background job and refreshes the model and relevant voice catalogues at completion. Remote model-update checks, universal default-selection and model test-generation actions are not established; the visible catalogue refresh is local-only.
10. Performance: `performance.info` remains unavailable by capability design; do not show timer-based benchmark output as measured hardware performance.
11. Settings/storage: custom roots and secure credential storage are incomplete; project/job data currently uses JSON/filesystem/QSettings rather than the documented SQLite target. Restart recovery is not accepted.
12. Diagnostics and packaging: diagnostic redaction is best-effort; branding, install/upgrade/uninstall and manual packaged-app smoke tests remain release gates.

### Flicker / responsiveness remediation plan

- Stop rebuilding job-list DOM when its panel is closed; when open, update existing rows/progress nodes in place rather than replacing the entire list on every poll.
- Reduce startup contention by loading critical project/navigation state first and deferring noncritical models, performance and catalog refreshes until their screens are opened.
- Prevent duplicate event-handler installation and duplicate poll timers after bridge reconnect/reinitialization.
- Remove/guard legacy timer-based prototype behavior only where a real backend handler owns that control; ensure unsupported controls report unavailable instead of faking progress/success.
- Profile DOM mutations, navigation latency, CPU, and WebEngine responsiveness in the exact packaged build. Do not claim flicker is fixed until verified on Windows.

### Flow / UI decisions

- Keep the seven-step production tracker visually neutral by default and highlight only the step corresponding to the active page. Do not show a step as completed or warning unless backed by real saved project state.
- Dashboard, Library, Player, History, Models, Performance, Settings and Help remain accessible through the sidebar without forcing the production sequence.
- Preserve the current visual system; use existing styles for the active step rather than redesigning the tracker.

## P0 — correctness risks before production acceptance

| ID | Gap / evidence | Required closure | Roadmap stage |
|---|---|---|---|
| G-01 | The authoritative HTML still contains static sample project/job/cast content, legacy prototype functions and timer-driven behavior (`simulateImport`, generation/model/benchmark renderers, `setTimeout`/`setInterval`, and some `localStorage` usage). The adapter intercepts/guards selected actions but not every visible control has been proven to avoid prototype success paths. | Build a per-control event map; remove or neutralize only the demo behavior that conflicts with backend behavior, without changing the approved appearance. Add tests ensuring unsupported controls never mutate fake data or announce success. | 1, 5, then regression in 10 |
| G-02 | Chapter editor operations are incomplete across the UI/bridge contract. Handlers include list/update/clean/add/delete/reorder/split, and Stage 2 now exposes add/rename/delete/move/merge through a contextual chapter-list action menu without adding always-visible controls. Merge preserves dialogue-assignment offsets and the adapter flushes pending edits before structural actions. Persisted human review state and the Review filter are connected. Explicit skip-for-generation state now persists per chapter and is honored by book generation; find/replace, undo/redo and re-detection protection remain incomplete. The Clean Text button previously bypassed the backend cleaner; Stage 2 now routes it through `chapter.clean`, which uses `clean_import_noise` and reports the number of removed likely page-noise lines, with a contract assertion. | Test extraction and cleanup with reproducible books; wire supported edit operations, preserve manual edits and persist review/skip/exclusion state or document unavailable actions honestly. | 2 |
| G-03 | Character Studio differentiates saved cast operations from prototype per-line AI recommendations. The adapter now routes individual dialogue confirmation through a source-validating assignment bridge. Static confidence is not treated as verified evidence; bulk acceptance and prototype queue actions remain guarded. | Stage 3 now adds explicit dialogue-line assignment against a uniquely matched saved source passage, persists offsets/speaker(s)/manual evidence in chapter JSON, rejects stale or ambiguous text, and restricts confirmation to the saved character list. Bulk acceptance and queue predictions remain guarded as prototype-only. Still required: Windows UI acceptance, assignment visibility/edit/removal, narrator fallback verification, and proof that saved line assignments route to synthesis. | 3 |
| G-04 | Voice UI/profile selection and preview use real bridge operations, but actual provider/profile/voice ID/model/settings and requested duration require end-to-end verification on the installed app. | Add request-contract tests for saved profile and 10/30/60-second UI targets, actual returned duration and audio playback. Test 10/20/30/45/60 where the backend supports them. | 4 |
| G-05 | Production has generate/preview and basic job controls, but no complete dedicated preflight, retry/rebuild/history-detail API. Durable job rows are not proof of worker checkpoint recovery. | Run short multi-chapter generation and interrupt/restart/retry cases; validate audio/metadata/markers before completion, reuse valid chunks, and persist structured failures. | 6 |

## P1 — feature parity and durable state

| ID | Gap / evidence | Required closure | Roadmap stage |
|---|---|---|---|
| G-06 | `project.create` is explicitly unavailable. No bridge commands for project duplicate/archive/delete/export/backup-restore. | Preserve import as real project-creation flow; implement only using existing project service with safe confirmation/ownership semantics, or keep controls clearly unavailable. | 5, 7 |
| G-07 | `chapter.split` was registered and invoked but missing from the capability map. Stage 1 adds the flag and regression assertion. More general capability-vs-handler drift still needs automated checking. | Keep registration, advertised capability and adapter use synchronized in tests. | 1 |
| G-08 | Pronunciation list/save/delete/analyze and single saved-profile preview exist, but bulk test-selected/test-all, per-profile result storage, import/export, conflict tracking and affected-audio invalidation are not complete backend operations. | Connect the voice test matrix to actual saved profiles and keep results/errors per profile; do not use timer-only 'test complete' results. | 5 |
| G-09 | Sound design has real catalogue/import/assignment/manifest/cue/chapter-BGM commands. End-to-end licensing, durations, loudness, missing assets, preview/final consistency and mix quality are not yet accepted. | Test imported and bundled files from disk through preview and final assembly; track unknown licensing accurately. | 5, 6 |
| G-10 | Job rows are stored in `premium_v2_jobs.json`; unfinished jobs are marked interrupted after startup. `history.list` reads the same job records, not a separate immutable history store. | Implement dedicated durable history separate from task-manager visibility/cleanup; verify checkpoint recovery and retry without regenerating valid chapters. | 6, 7 |
| G-11 | `player.get_active` returns output metadata and browser audio controls cover transport/speed/seek, but backend playback position/bookmarks and robust chapter timeline persistence are not evidenced. | Verify playback against real output; persist resume position and synchronize main/mini-player state across navigation/restart. | 5, 7 |
| G-12 | Models Center now exposes inventory, install, verify, repair and uninstall for supported local components. Lifecycle operations use background jobs with active-job protection and refresh the model inventory plus relevant voice catalogues after completion. Commit `35297b7` corrected nested Chatterbox/Qwen runtime storage accounting; its full regression-test job passed 530 tests. | Keep update checks clearly local-only; add default selection or test-generation only when backed by real operations. Validate storage/health in the packaged Windows app; live CPU/GPU/VRAM telemetry remains unavailable. | 8 |
| G-13 | `performance.info` is advertised as false; live hardware telemetry is unavailable. The supplied HTML has a timer-style benchmark demonstration to guard. | Connect real telemetry/benchmark where supported or mark each metric unavailable; ensure demo timers cannot claim measured performance. | 8 |
| G-14 | Custom project/audio/model/cache/output roots and secure provider-specific credential storage are not complete. Settings fields cannot be assumed to persist just because they render. | Map every settings field to storage and a test; implement OS credential store support before enabling credential UI. | 7 |
| G-15 | SQLite is documented as target schema but current project and job paths are JSON/filesystem/QSettings. Current workflow-stage/chapter selection and player resume persistence are not fully verified. | Decide on a staged migration with backups, preserve existing project folders, and add close/reopen integrity tests before switching authoritative storage. | 7 |

## P2 — release quality and acceptance

| ID | Gap / evidence | Required closure | Roadmap stage |
|---|---|---|---|
| G-16 | Diagnostic export is real and best-effort sanitized, but the source acknowledges arbitrary third-party log formats may escape redaction. | Inspect actual exports and test redaction coverage; never describe redaction as a security guarantee. | 5, 8 |
| G-17 | Installer branding/logo cleanup and install/upgrade/uninstall acceptance remain separate work; current CI packaging does not establish visual acceptance on the user's PC. | Inspect original logo asset, create transparent correctly padded variants, then verify install, shortcuts, cancellation and uninstall/data preservation. | 9 |
| G-18 | No final manual visual comparison across 1920×1080, 1366×768, 1280×720 and narrow windows is evidenced by Run #731. | Compare the exact HTML and packaged WebEngine app on those sizes and fix layout regressions without redesigning. | 10 |
| G-19 | Existing CI run passed tests/packaging, but the complete 20-step real-book/real-audio workflow has not been accepted manually. | Complete the import→chapters→voice→characters→pronunciation→sound→generation→recovery→playback checklist on Windows and record evidence. | 10 |

## Recommended execution order

1. **Stage 2:** add reproducible extraction/cleanup/chapter fixtures and fix confirmed text-loss/segmentation defects.
2. **Stage 3:** persist speaker assignments and stop exposing line-level AI results as saveable.
3. **Stage 4:** prove the selected saved voice and duration reach the real preview provider.
4. **Stage 5:** restore remaining screen action parity, bulk pronunciation tests and history/player controls using existing services.
5. **Stages 6–8:** complete durable generation recovery, state/security, supported model actions and truthful performance telemetry.
6. **Stages 9–10:** logo/installer and final visual/functional acceptance.

## Stage 1 exit check

- [x] Repository, branch, PR and exact code baseline verified.
- [x] Three user-supplied implementation/UI specifications inspected alongside the latest approved HTML.
- [x] All 15 screens inventoried and key backend service/bridge operations mapped.
- [x] Explicit capability mismatch found and corrected (`chapter.split`).
- [x] Current known limitations and test evidence updated without claiming full acceptance.
- [x] Prioritized gap register created with closure criteria and owning roadmap stage.
- [x] Source-level semantic mapping added for legacy no-ID control groups; representative selectors/event paths/backend calls are guarded by `test_legacy_controls_without_ids_have_semantic_successors_and_event_paths`.
- [ ] Stage 6 still requires manual target-Windows interaction acceptance; this is not a Stage 1 source-audit blocker.

## Stage 2 checkpoint — import integrity

- Exact-content duplicate detection and actionable existing-project guidance are implemented in the host before a new import job is created.
- Import completion data reports the preserved source path and flags chapter boundaries for review.
- Chapter review status defaults legacy chapters to `needs_review`, persists `reviewed`/`needs_review` with chapter JSON, and drives the existing Review filter.
- Explicit chapter exclusion now persists as `skip_for_generation`, is available through the contextual chapter action, preserves the chapter text, and excludes only flagged chapters from audiobook generation. Job messages, returned job data, and project state distinguish empty chapters from intentionally excluded chapters; a stale contract test and misleading progress summary were corrected in the same batch.
- Still open: parser/chapter fixtures, runtime import retry/cancel/failure acceptance, and Windows edit/save/reload acceptance. Import cancellation, format-specific diagnostics, and staged-file cleanup now have source-contract checks. Premium V2 currently has no re-detect command; importing creates a new project and does not replace chapters in an existing project. If re-detection is added later, it must require explicit confirmation and preserve manual edits or provide a before/after review. Find selects the first case-insensitive match, Replace confirms and replaces all case-insensitive matches, and chapter undo/redo supports grouped editing with a bounded history (10 snapshots; disabled for chapters over 1,000,000 characters to limit memory use). Stage 2 is not complete.


### Import cancellation and diagnostics checkpoint

- Import jobs now expose Cancel in the existing background-job list. Cancellation is checked after extraction and after chapter detection, before project creation; the source is preserved and cancellation is reported only when the worker reaches a safe boundary.
- Temporary dropped-file staging copies are removed after the import worker exits. Original user-selected source files are never deleted.
- Extraction failures now provide format-specific recovery guidance (including scanned-PDF/OCR guidance) while retaining bounded underlying error details. Retry remains selecting the source file again after correcting the issue; no silent automatic retry is performed.
- Stage 2 remains open pending fixture tests, runtime import retry/cancel/failure acceptance, and Windows edit/save/reload acceptance. Re-detection policy is currently: no re-detection feature is exposed, and import creates a new project rather than replacing existing chapters.


### 2026-10-21 — reproducible chapter fixture coverage

- Added deterministic fixtures for heading-based chapters with preamble text, empty chapter headings, plain text with no headings, and the supported `Life.0` heading family.
- Added a project save/reload round-trip test to verify edited chapter text, review status, generation exclusion, and dialogue assignments remain intact.
- Verified by source inspection that Premium V2 has no re-detect command today; its import path detects chapters for a newly created project and does not replace chapter text in an existing project. Re-detection is therefore unavailable rather than silently destructive. Any future re-detect feature must require explicit user intent and protect manual edits.
- These are automated unit/contract tests; they do not replace actual import-cancel/retry/failure or Windows GUI acceptance. Stage 2 remains open.


### Stage 3 checkpoint — explicit dialogue assignment

- Added `chapter.dialogue.assign` to the allow-listed bridge and capability map. It accepts only a saved character or alias, validates that the selected dialogue text occurs exactly once in the saved chapter text (unless a chapter number is explicitly provided), and saves original text offsets, manual source, confidence 1.0, and backward-compatible single/multi-speaker fields. Ambiguous, stale, overlapping, or unsaved-character assignments are rejected without writing chapter state.
- Wired individual dialogue confirmation in the existing AI Story Review modal to the saved character list and backend assignment. Displayed prototype confidence is explicitly not used as evidence. Bulk acceptance and queue predictions remain blocked until they can be tied to real source passages.
- Added deterministic tests for exact and whitespace-wrapped matching, stale sample rejection, duplicates, reassignment, overlaps, and multi-speaker compatibility. Stage 3 remains open pending CI, packaged Windows UI acceptance, and proof that saved line assignments affect synthesis as intended.


## Legacy control parity inventory — 21 October 2026

**Basis:** old prototype `docs/prototypes/Ryus_Audiobook_Dragon_Studio_Premium_Final.html` compared against the approved Premium V2 HTML `assets/frontend/ryu_audiobook_premium_v2.html` control IDs. This is a *markup/semantic successor* audit, not proof that every control's runtime behavior is accepted. Every row marked preserved or replaced still requires the relevant interaction test or Windows acceptance.

**ID audit result:** 89 unique old control IDs; 69 IDs are retained verbatim; 20 IDs have been replaced by newer controls. No old ID is classified as confirmed missing solely because its ID changed. Backend gaps remain separately tracked below.

| Old control ID | Classification | Current control / successor | Runtime status / note |
|---|---|---|---|
| `app` | Preserved | `app` | Shell; Windows interaction not yet verified |
| `sidebar` | Preserved | `sidebar` | Navigation shell; visual parity and keyboard behavior not yet verified |
| `nav` | Preserved | `nav` | Navigation container; all destinations need acceptance |
| `menuToggle` | Preserved | `menuToggle` | Responsive menu behavior not yet verified |
| `pageTitle` | Preserved | `pageTitle` | Dynamic title behavior not yet verified |
| `globalSearch` | Preserved | `globalSearch` | Search behavior requires control-level verification |
| `themeToggle` | Preserved | `themeToggle` | Theme persistence requires restart test |
| `notifyBtn` | Preserved | `notifyBtn` | Notification/jobs action; verified only by source inspection |
| `workspace` | Preserved | `workspace` | Main workspace container |
| `dashboard` | Preserved | `dashboard` | Real project-card opening has a regression test |
| `pauseDash` | Preserved | `pauseDash` | Pause action is limited to supported generation jobs |
| `library` | Preserved | `library` | Library page; project lifecycle gaps remain |
| `librarySearch` | Preserved | `librarySearch` | Backend project search wired; runtime not yet accepted |
| `libraryFilters` | Preserved | `libraryFilters` | Filter semantics need runtime acceptance |
| `libraryGrid` | Preserved | `libraryGrid` | Populated from local project records |
| `import` | Preserved | `import` | Import flow needs real-file and recovery acceptance |
| `dropzone` | Preserved | `dropzone` | Drag/drop and browse parity need Windows acceptance |
| `fileInput` | Preserved | `fileInput` | File selection requires packaged-build acceptance |
| `browseBtn` | Preserved | `browseBtn` | Browse/import handler requires runtime acceptance |
| `importStatus` | Preserved | `importStatus` | Status messaging is shared; visual flicker still being profiled |
| `importBar` | Preserved | `importBar` | Progress source is backend job state |
| `chapters` | Preserved | `chapters` | Chapter editor exists; full editing edge cases remain |
| `cleanText` | Preserved | `cleanText` | Must be checked against source-preserving behavior |
| `saveChapter` | Preserved | `saveChapter` | Save path exists; crash/restart durability not accepted |
| `chapterSearch` | Preserved | `chapterSearch` | Client-side chapter filter |
| `chapterList` | Preserved | `chapterList` | Backend chapter records; split/re-detection protection still open |
| `chapterTitle` | Preserved | `chapterTitle` | Edit/save behavior requires runtime acceptance |
| `chapterEditor` | Preserved | `chapterEditor` | Undo/redo and safe autosave still require acceptance |
| `saveState` | Preserved | `saveState` | Save indicator needs failure/restart testing |
| `wordCount` | Preserved | `wordCount` | Count accuracy requires acceptance |
| `voices` | Preserved | `voices` | Voice Studio exists; provider/credential gaps remain |
| `saveProfile` | Preserved | `saveProfile` | Save/update profile behavior needs provider-specific testing |
| `voiceGrid` | Replaced | `voiceWorkspace`, `profileLibrary` | New multi-step voice workspace; old grid parity not yet accepted |
| `voiceWave` | Replaced | `wave`, `assignedWave`, `soundWave` | Waveform successor identified; waveform source/accuracy not yet verified |
| `voicePlay` | Replaced | `playPreview` | New preview control; audio identity/duration must be accepted |
| `voiceStop` | Replaced | `stopPreview` | Stop/cancel behavior must be tested during generation and playback |
| `selectedVoice` | Replaced | `profileVoice`, `previewVoice`, `previewProvider` | Selection state is spread across profile and preview controls; consistency test needed |
| `characters` | Preserved | `characters` | Character Studio exists; full source-backed casting acceptance remains |
| `analyzeCharacters` | Preserved | `analyzeCharacters` | Real analysis job exists; output accuracy and recovery remain |
| `characterList` | Replaced | `assignedCharacterList`, `quickCharacterList`, `manualStory` | Split into assignment/library/story views; parity test needed |
| `characterName` | Replaced | `editCharacterName` | New character editor; persistence and alias behavior need acceptance |
| `characterVoice` | Replaced | `editCharacterVoice`, `assignCharacter` | Assignment flow replaced; real synthesis routing needs Windows test |
| `characterVoiceSelect` | Replaced | `editCharacterVoice` | Voice selector moved into editor; manual assignment regression test needed |
| `assignVoice` | Replaced | `assignCharacter`, `confirmAiCharacter` | New manual/AI assignment paths; both need end-to-end acceptance |
| `pronunciation` | Preserved | `pronunciation` | Pronunciation Studio exists; dictionary import/export and conflict handling remain open |
| `addPronunciation` | Replaced | `addPronunciationAdvanced`, `saveNewPron` | New entry flow; validation and persistence require acceptance |
| `pronSearch` | Replaced | `pronTermSearch`, `pronSearchAdvanced` | Search split by term and dictionary views; behavior parity needs test |
| `pronTable` | Replaced | `pronDictionaryBody` | Dictionary table replaced; import/export/conflict behavior remains open |
| `sound` | Preserved | `sound` | Sound Design exists; final mix consistency and licensed assets remain open |
| `saveSoundPreset` | Replaced | `saveSoundPresetAdvanced`, `applySoundToProduction` | Preset save/sync split into save and production handoff; end-to-end sync needs acceptance |
| `trackGrid` | Replaced | `soundTrackGrid`, `cueGrid` | Music/effects separated; filter and selection parity needs acceptance |
| `selectedTrack` | Replaced | `selectedSoundTitle`, `selectedSoundMeta` | Selection metadata replaced; preview and assignment consistency needs acceptance |
| `musicVolumeValue` | Replaced | `advancedMusicVolumeValue` | New volume value control; persisted mix needs acceptance |
| `musicVolume` | Replaced | `advancedMusicVolume` | New volume control; output loudness and final-mix behavior remain open |
| `generate` | Preserved | `generate` | Production Studio exists; complete preflight/recovery flow remains open |
| `cancelJob` | Preserved | `cancelJob` | Cancellation is job-type/state limited; terminal-state handling needs acceptance |
| `genRing` | Preserved | `genRing` | Progress display; backend percentage and duration accuracy need real-book test |
| `genPercent` | Preserved | `genPercent` | Progress display; actual generation progress must be checked |
| `genStage` | Preserved | `genStage` | Stage text is sourced from backend job state |
| `genChapter` | Preserved | `genChapter` | Chapter progress needs real-book acceptance |
| `elapsed` | Preserved | `elapsed` | Timing accuracy not yet verified |
| `remaining` | Preserved | `remaining` | ETA accuracy not yet verified |
| `previewGenerate` | Preserved | `previewGenerate` | Preview duration and audio identity must be tested at 10/30/60 seconds |
| `startGenerate` | Preserved | `startGenerate` | Full generation must pass preflight, resume, retry, and real-book acceptance |
| `pauseGenerate` | Preserved | `pauseGenerate` | Pause/resume is generation-only; checkpoint recovery needs acceptance |
| `player` | Preserved | `player` | Player exists; resume/bookmarks persistence not evidenced |
| `playerTimeline` | Preserved | `playerTimeline` | Seek accuracy and timeline persistence need acceptance |
| `currentTime` | Preserved | `currentTime` | Playback time needs acceptance |
| `mainPlay` | Preserved | `mainPlay` | Real output playback and source URL need acceptance |
| `history` | Preserved | `history` | History exists; immutable details and recovery links remain open |
| `historyFilters` | Preserved | `historyFilters` | Filter behavior has source wiring; full history acceptance remains open |
| `models` | Preserved | `models` | Model Center exists; update/verify/repair/uninstall are not fully connected |
| `performance` | Preserved | `performance` | Page exists; hardware telemetry is explicitly unavailable when not measured |
| `runBenchmark` | Preserved | `runBenchmark` | Control exists, but `performance.info` is intentionally unsupported; do not present a fake benchmark |
| `benchmarkResult` | Preserved | `benchmarkResult` | Must clearly communicate unavailable capability without fabricated values |
| `settings` | Preserved | `settings` | Settings page exists; custom roots/credential security and restart persistence remain open |
| `saveSettings` | Replaced | `saveSettingsAdvanced` | New advanced settings save; persistence and restart test needed |
| `themeSelect` | Replaced | `themeSelectAdvanced` | New theme selector; persistence and visual parity need acceptance |
| `miniPlayer` | Preserved | `miniPlayer` | Mini-player exists; background playback/resume needs acceptance |
| `miniPlay` | Preserved | `miniPlay` | Mini-player playback needs real-output acceptance |
| `miniProgress` | Preserved | `miniProgress` | Progress synchronization needs acceptance |
| `hideMini` | Preserved | `hideMini` | Hide/restore behavior needs acceptance |
| `toasts` | Preserved | `toasts` | Toast lifecycle/overlap contributes to flicker investigation |
| `modalBack` | Preserved | `modalBack` | Modal behavior needs keyboard/close acceptance |
| `modalTitle` | Preserved | `modalTitle` | Pronunciation modal content |
| `modalWord` | Preserved | `modalWord` | Pronunciation modal content |
| `modalPron` | Preserved | `modalPron` | Pronunciation modal content |
| `modalCancel` | Preserved | `modalCancel` | Cancel behavior needs acceptance |
| `modalSave` | Preserved | `modalSave` | Save behavior needs persistence acceptance |

### Controls without stable IDs

The old prototype also has navigation items, duration buttons, provider cards, filters, track previews, playback-speed controls, seek/skip buttons, and chapter/context actions without unique IDs. The new UI has corresponding control groups, but these cannot be classified safely from IDs alone. Their **semantic mapping is not yet verified** until each old control is matched to a new selector and an event-handler/test path. Do not treat the ID count above as proof of feature parity.

### Semantic map for legacy controls without stable IDs — 21 October 2026

This closes the **source-level mapping** gap noted above. Selectors are based on the current approved Premium V2 HTML and adapter; labels and selectors are not treated as proof of Windows runtime acceptance.

| Legacy control group | Premium V2 selector / locator | Event path and backend contract | Source-audit result |
|---|---|---|---|
| Sidebar navigation | `.nav-btn[data-page]` | HTML `go(id)` navigation; `data-page` maps to the 15 destination sections | Mapped; destination smoke test remains a Stage 6 acceptance item |
| Production workflow strip | `[data-go]`, `.flow-stage` | `go(id)` updates the current workflow step; backend project state is not inferred from decorative step text | Mapped; active-step contract is regression-tested |
| Voice preview duration | `#voices .toolbar` then `.seg button.active` | Adapter reads the selected seconds and sends `duration_seconds` through `voice.preview`; requested and actual duration are compared in the result UI | Mapped; real-provider duration/playback still requires Windows acceptance |
| Voice preview mode | `#voices .seg` button groups | Adapter resolves Current Chapter / Selected Passage / Custom Text, validates selected text, and sends the chosen preview text | Mapped; text-selection edge cases remain runtime acceptance |
| Voice provider/model cards | `.provider[data-provider]` | Delegated click path reads `button.closest('.provider').dataset.provider`; model installation calls `models.install` and tracks the returned job | Mapped; provider candidate/credential features not backed by services remain unavailable |
| Library filters/search | `#libraryFilters button`, `#librarySearch` | `refreshProjects()` filters backend `project.list` results; search input triggers refresh | Mapped; filter correctness with multiple real projects remains acceptance |
| Chapter selection/filter/search | `[data-chapter-number]`, `#chapterSearch`, `#manualChapterSearch` | Adapter selects a saved chapter; search narrows chapter rows. Review/skip/add/rename/delete/reorder/merge/split/find/replace/undo/redo paths are implemented through the chapter adapter actions where supported | Mapped; persistence and conflict cases remain acceptance |
| Sound source filters | `#soundSourceFilter [data-source]` | `refreshSounds()` filters the real `sound.catalog` results by bundled/imported source and search text | Mapped; catalog/licence accuracy remains acceptance |
| Sound track selection and preview | `#soundTrackGrid [data-select-sound]`, `#previewSelectedTrack`, `#soundPreviewBook` | Track selection records a real catalog path; preview uses local audio or the sound-preview backend job; production sync calls `sound.save_manifest` | Mapped; final mix parity and playback remain acceptance |
| Background job actions | `[data-job-action][data-job-id]` | Adapter renders actions from durable job records and dispatches supported pause/resume/cancel commands by job ID | Mapped; state transitions/restart recovery remain acceptance |
| Player seek/skip/speed | Player transport buttons identified by their visible labels (`↶15`, `15↷`, `0.75×`, `1×`, `1.25×`, `1.5×`) | Adapter changes `playerAudio.currentTime` / `playbackRate` and synchronizes player and mini-player indicators | Mapped; seek precision and restart-resume remain acceptance |
| Chapter contextual actions | `[data-chapter-number]` in the chapter list | Context prompt routes supported actions to `chapter.add/delete/reorder/merge/split/review/skip` and persists text snapshots before structural changes | Mapped; action-level persistence still needs Windows acceptance |
| Modal controls | `#modalSave`, `#modalCancel`, `#modalBack` | Pronunciation save/cancel uses the existing modal and `pronunciation.save` / `pronunciation.list` backend operations | Mapped; keyboard/focus behavior remains acceptance |
| Responsive navigation | `#menuToggle` and `.nav-btn[data-page]` | Existing shell toggles the responsive menu and routes navigation without adding new visual controls | Mapped; compact-window acceptance remains Stage 6 |
| Notifications / job panel | `#notifyBtn`, `#backgroundJobsButton` | Opens the existing job panel and refreshes `job.list`; polling updates backend state | Mapped; flicker/latency must be measured in the packaged app |

The regression test `test_legacy_controls_without_ids_have_semantic_successors_and_event_paths` now guards representative selectors, delegated event paths, preview duration, player transport, contextual chapter actions, and corresponding backend calls. Controls whose service operation is unavailable are documented as unsupported rather than counted as functional parity. Stage 1 is complete at the source-audit level; target-Windows interaction acceptance remains a separate Stage 6 gate.

### Additional Premium V2 controls

Premium V2 adds controls for AI dialogue review and assignment, reusable Character Library, multi-step voice creation, premium voice candidates, pronunciation test matrix, per-chapter BGM and cue assignment, production mix preview/sync, job recovery, diagnostics, settings sections, and Help & Guide. These are additive; their existence does not replace the obligation to preserve the older controls' behavior.

### Explicit release classification

- **Preserved:** old control ID still exists in the approved Premium V2 markup. This is not a claim that runtime behavior is fully accepted.
- **Replaced:** old ID is absent but a named Premium V2 successor exists. The successor's semantics and end-to-end behavior still need tests.
- **Missing:** no successor can be demonstrated after semantic and event-handler inspection. No old feature should be declared missing based only on an ID change.
- **Unsupported:** UI may exist, but a backend operation is explicitly unavailable (example: hardware benchmark telemetry).
- **Not yet verified:** mapping, persistence, real audio, recovery, or packaged Windows behavior lacks sufficient evidence.


## Stage 2 implementation log — real backend actions

### Implemented: Models → Verify (21 October 2026)

- Added allow-listed `models.verify` to the desktop bridge capability map and dispatcher.
- Verification checks actual Qwen model directories and required `config.json`/Safetensors files on disk. It does not download models, load the ML runtime, or claim success when files are absent.
- Supports individual known Qwen model IDs and CustomVoice, VoiceDesign, and Voice Clone capability aliases. Composite capabilities report ready only when their required model-file combination is present.
- Connected the existing Models screen Verify control to the backend operation; the UI reports passed/missing file status and the exact model IDs checked.
- Added an integration-contract regression test for capability registration, dispatch wiring, real local-file check usage, and no-download behavior.
- **Still unsupported:** per-model Update, Repair and Uninstall remain explicitly unavailable; this change does not pretend those actions are connected. General non-Qwen model verification also remains limited until provider-specific on-disk rules exist.
- **Validation:** Run #802 (`da3383e1339843dafd600bbfdc00285cd00b5b14`) failed only because the static test expected `if action === 'verify'` instead of the actual `if (action === 'verify')` syntax. The test was corrected and expanded with no-ID control-path checks in commits `5112aff50c6182775d40a7bfb3a41c1bd46c71ce` and `f1942f85245fec3a794725f5d2ba2ab331001f1f`; Run #805 is the current validation run. Do not mark the change CI-validated until the current run passes.

### Stage 1 closure boundary

The **source-level control audit is now closed** for the currently inventoried legacy control groups: all 89 old IDs are classified (69 retained, 20 mapped to named successors), and the no-ID groups below are mapped to stable selectors plus their event/backend paths. Regression tests guard both inventories. This closes the source audit, not manual acceptance: successor IDs and source handlers do not prove equivalent runtime behavior. Stage 6 must still verify interactions, persistence, responsiveness and real audio in the packaged Windows build.


## Stage 4 Prompt 5 — cross-stage audit evidence and release blockers (23 October 2026)

- Audit commit: `aa9b4587c39c65f4d8a66c9bede8ec191dac7704`; branch `stage-4-pronunciation-sound-design`.
- Stage 3 PR #18 remains open at `d5d17f41393910596ad793dfe8df8753c6a1a836`. Stage 4 is 50 commits ahead and 0 behind; its merge base is the Stage 3 head. Merge Stage 3 first, then reconcile Stage 4. Never force-reset to an older baseline.

### Cross-stage editor defect — fixed and verified
- `app/chapters/editor.py` had failed to preserve assignment records from the next chapter during merge, partition/remap spans during split, and retain multi-speaker/cast metadata through remapping. The fix remaps exact assignment text into resulting chapter content and discards stale/removed-heading spans instead of guessing.
- `tests/test_cross_stage_chapter_assignment_integrity.py`: all five tests passed in Run #945 (merge, paragraph split, split-at-selection, metadata retention on edits, and project save/reload compatibility).
- **Full suite:** Run #945, `Ran 464 tests in 30.608s` / `OK`, Windows Server 2025, Python 3.12.10, exact head `aa9b4587c39c65f4d8a66c9bede8ec191dac7704`. https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39862896213.

### Windows package and scan evidence — Run #945
- Passed: frozen EXE self-test; bundled Piper/Kokoro voice assets and critical modules; Inno Setup installation and installer compilation; original logo transparency/content check; release SHA-256 manifest; installer, manifest, and portable-artifact uploads; cleanup of older Windows build runs/artifacts.
- **Defender scanned both executables:** log explicitly says the portable `Ryu's Audiobook.exe` scan and `Ryu's Audiobook Setup.exe` scan each “found no threats.” The fail-closed guard rejects nonzero exit codes, skipped scans, or output without a recognized completed-scan result. Custom scan passed `-DisableRemediation`. This run resolves the previous Run #940 / #938 “scan skipped” ambiguity for this commit.
- Artifacts (expire 2026-11-21 UTC): portable `Ryu-Audiobook-Portable-945`, ID `12463925128`, 1,348,226,514 bytes, ZIP SHA-256 `abd8bbfbd426d698d5cd8cdcc55207e12a28762aedd4667caa0ff41654c3b3a3`; installer `Ryu-Audiobook-Installer-945`, ID `12463695558`, 648,309,461 bytes, ZIP SHA-256 `652788ed1e55bca8bbc41f9d4eff7f8f40b18f0479c48fa1b12750afb92fb9d0`; manifest `Ryu-Audiobook-Release-SHA256-945`, ID `12463311632`, 513 bytes, ZIP SHA-256 `1b8527b90fbb861d3c727915f97ba0289ec206f10efbb742cba572b812b90e74`. Executable hashes recorded inside manifest: portable EXE `337C69B6E7F15F7222099E8792C26B6DA1DF38D5E01F7CF699B6FAC940F8BF7F`; installer EXE `DCC024150176CFBF240FE1AAC09A0C380F4820987A2C29F3A25A777CD5F09A3C`.
- `springly_sprigs.mp3` successfully downloaded in Run #945, so the earlier transient curl exit 35 from Run #940 does not describe this run. `Publish verified installer release` was skipped by workflow conditions; no GitHub release publication is claimed. No test/build/scan/upload step failed, and no steps/jobs were cancelled in Run #945.

### Remaining acceptance gates — keep Stage 4 open
- Stage 1: target-PC hardware freeze/crash and packaged UI responsiveness/flicker.
- Stage 2: TXT/EPUB/PDF/DOCX import; duplicate/cancel/retry; full chapter edit/merge/split/find-replace/undo-redo/save/reopen.
- Stage 3: actual selected saved profile/provider preview and voice quality; Voice Studio/Character Studio persistence/error UI; analysis result persistence; rename/alias/duplicate/delete behavior.
- Stage 4: real listening for pronunciation on/off and voice identity; sound preview versus final mix; cue boundaries, BGM-off and duration; provider/FFmpeg failure, cancellation, retry, cleanup and checkpoint/source-text preservation.
- Keep the approved Premium V2 HTML visually unchanged. Automated CI does not establish target-PC operation or perceived audio quality.



### Models Center and shared job-monitor follow-up — 24 October 2026

- Source review confirmed allow-listed `models.list/install/verify/repair/uninstall` handlers, background lifecycle jobs, and completion-time refreshes for inventory, saved voice profiles, and applicable provider catalogues.
- Corrected storage reporting so nested Chatterbox runtime files are counted and Qwen runtime files/metadata are measured separately from the individual Qwen weight folders.
- The first run for the storage fix, Build #1162, passed the full regression-test job: **530 tests in 36.774 seconds**. Its Windows packaging job was superseded by the shared job-monitor timer correction; use the next branch run for the updated package result.
- Found and corrected an initial-terminal polling race in `monitorJob`: if a job was already terminal during the first tick, the timer could be created after that tick had finished. The new regression contract verifies that the timer is created only if the initial tick remains non-terminal.
- Still open: target-Windows interaction/visual acceptance; actual model installation/repair/uninstall on the user's PC; true model-provider preview/narration acceptance; and live hardware telemetry, which remains explicitly unavailable.


## 2026-10-24 current-branch reliability addendum

Production Pause/Cancel is generation-type guarded. Chapter switching saves a pending draft before navigation and aborts on save failure. Stale replies are ignored across project/chapter/cast/pronunciation/sound/cues/model/voice/provider/history lists; unchanged DOM is retained and search is debounced. See docs/SIX_STAGE_AUDIT_AND_ACCEPTANCE.md for the 15-screen ledger. Do not claim zero flicker/crash without repeated target-Windows evidence.
