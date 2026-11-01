# Ryu's Audiobook — Final Completion Roadmap

**Repository:** `RyuBlanc/ryu-audiobook-build`  
**Working branch:** `fix/import-qa-speaker-hover-hardware`  
**Canonical UI reference:** `docs/prototypes/Ryus_Audiobook_Voice_Studio_Fixed_All_Steps.html`  
**Behavioral acceptance checklist:** `docs/DRAGON_STUDIO_ACCEPTANCE_CHECKLIST.md`  
**Implementation specification:** `docs/UI_UX_IMPLEMENTATION_SPEC.md`

## Release principle

“Bug-free” is treated as a release target, not a claim that software can never contain defects. No release is considered complete until the current source commit passes automated tests, the exact Windows build is packaged, and the core workflows are manually smoke-tested. A prototype or successful packaging job alone is not sufficient.

## Priority 0 — Protect core workflows

- [ ] Saved Qwen clone/custom voice identity remains stable across profile save, app restart, preview, character assignment, and full generation.
- [ ] Changing a saved cast profile changes the generation signature so stale audio chunks are not reused. Regression test added; verify in CI.
- [ ] Character detection recovers explicit speaker labels, Japanese quote forms, em-dash dialogue, short CJK names, aliases and dialogue examples on real-world sample novels.
- [ ] Voice cast assignments persist per project and route the assigned profile to the matching dialogue during actual generation.
- [ ] Mixed books skip empty chapters safely; all-empty books are blocked with a clear repair message.
- [ ] Generate navigation always opens the real production screen and remains usable if optional panels fail.
- [ ] Supported preview durations (10, 30, 60, 90 seconds) use the selected target, report actual output duration, and never silently substitute a shorter preview.
- [ ] Preview and generation keep expensive inference off the UI thread; Play/Pause/Stop/Cancel work in-app and the window remains responsive.
- [ ] Progress, elapsed time, ETA, error states, cancellation and resume reflect real work rather than timer-only or guessed completion.

## Priority 1 — Complete the approved HTML-referenced UI

Use the supplied Voice Studio HTML as the canonical visual language for every screen. Preserve all existing features; visual parity never justifies removing working controls.

- [ ] Shared shell: grouped sidebar, active-state highlight, collapsible navigation, project indicator, top bar, search, theme control, notifications and mini-player.
- [ ] Dashboard: real local-project counts, recent work, attention/recovery states and functional navigation.
- [ ] Library: real search/filters, open, rename, safe delete and interrupted-project recovery.
- [ ] Import Studio: supported formats, drag/drop, extraction progress, cancellation, text preview, metadata and no silent truncation.
- [ ] Chapter Studio: detect/re-detect, rename, reorder, split, merge, edit, delete, multi-select, autosave and empty-chapter recovery.
- [ ] Voice Studio: four-step Voice Library → Configure → Voice Profile → Preview & Assign workflow; guided mode and Show All Steps; saved profile persistence; provider-specific settings; truthful readiness; preview progress and in-app transport.
- [ ] Character Studio: detected cast, dialogue examples, confidence/review, narrator fallback, assign/unassign, and actual voice propagation into synthesis.
- [ ] Pronunciation Studio: book-level overrides, common-word protection, test selected pronunciation and in-app playback.
- [ ] Sound Design Studio: contextual BGM, ambience, opening/chapter/scene/closing cues, manual import, preview, volume/ducking and persisted presets.
- [ ] Production Studio: readiness gate, chapter/full generation, accurate progress/ETA, pause/cancel/retry/resume and actionable failures.
- [ ] Audiobooks: playable completed files, chapter navigation, metadata/artwork display and open-output-folder action.
- [ ] Generation History: real job state, logs, failure reasons and recovery actions.
- [ ] Models Center: actual install/repair status, progress, cancel, integrity and local storage information.
- [ ] Performance Center: actual hardware detection, backend availability, safe model recommendation and benchmark results.
- [ ] Settings: local paths, privacy/offline behavior, theme, default bitrate and cleanup/uninstall-related options where supported.
- [ ] Responsive/full-screen: no clipped controls, inaccessible menus, overlapping panels, or navigation that requires restarting the app.
- [ ] Every visible control is connected to real behavior; no prototype-only success states or placeholder actions.

## Priority 2 — Audiobook production quality

- [ ] M4B output opens in supported players and includes correct chapter markers, title, author, cover artwork and other supported metadata.
- [ ] Verify selectable AAC bitrates from 128 to 320 kbps; default is 256 kbps unless the user changes it.
- [ ] Validate output duration, audio stream metadata, channel layout, chapter timing and absence of corrupt/empty segments.
- [ ] Long books resume from valid completed chunks; changing text, voice identity or relevant settings invalidates incompatible chunks.
- [ ] Preserve paragraph breaks, dialogue pacing, punctuation, multilingual text and Japanese/other names through extraction, cleanup and narration.
- [ ] Contextual sound selection must be relevant and licensed. Do not fabricate a 1,000-track catalogue; build the catalogue from verified sources with source/license metadata and clear fallback behavior.
- [ ] Preview mix and final assembly use consistent sound-design settings and sensible narration ducking.

## Priority 3 — Windows, offline and hardware acceptance

- [ ] Test the installer and portable package produced from the same accepted commit.
- [ ] First launch works without developer tools installed; logs explain missing runtime/model problems.
- [ ] Offline mode keeps book content and custom reference audio local; network providers are clearly marked as online.
- [ ] Validate an RTX 3050 4 GB VRAM path and an RTX 4060 8 GB VRAM path; verify CPU/DirectML fallback where supported.
- [ ] Complete a short book end-to-end, then a multi-chapter long-book resume test. Record duration, output quality, memory use and failures.
- [ ] Verify install, upgrade, uninstall, user-data preservation choice, and cleanup of application-owned files without deleting user books.
- [ ] Keep source code and required assets; clean only stale generated build artifacts/runs after confirming they are safe to remove.

## Current verified state

- [x] Windows build workflow #399 succeeded on commit `eae32304d3e3fc6e117667c0d5564c96afa1d9ad`, including regression tests, frozen-app checks, voice-asset checks, installer packaging and portable packaging.
- [x] Installer and portable artifacts were produced by build #399.
- [ ] Build #399 did not publish a public Release asset because the workflow's release step was skipped; its artifacts are available through the Actions run and expire on 2026-10-20.
- [ ] The cast-signature regression change in commit `b0d31954c2e4d62d5407579dc3cc09a6af202278` requires its own passing CI result.
- [ ] The new guided Voice Studio navigation requires CI and a Windows visual smoke test.
- [ ] None of the above CI results substitute for manual runtime tests on both target PCs.

## Definition of release-ready

A candidate is release-ready only when:
1. All Priority 0 items pass automated or documented manual tests.
2. All 14 navigation destinations are checked against the canonical HTML and acceptance checklist.
3. No high-severity UI or generation regressions remain open.
4. Short-book, empty-chapter, custom-voice, cast-assignment, preview-duration and long-book-resume scenarios pass.
5. The exact installer commit passes CI and launches successfully on Windows.
6. Any known limitation is documented; no unsupported feature is advertised as working.
