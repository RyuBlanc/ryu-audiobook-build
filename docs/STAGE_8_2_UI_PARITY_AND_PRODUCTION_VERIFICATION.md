# Stage 8.2 — Full UI parity and production verification

**Branch:** `fix/import-qa-speaker-hover-hardware`  
**Started:** 2026-10-19  
**Baseline commit:** `8357e2eef8a0a217077f54b14bfaf0298e258fab`  
**Baseline Windows build:** [Build #493](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39186820298) — successful

## Stage goal

Verify all 14 Dragon Studio destinations against the approved prototype and the behavioral acceptance checklist. Preserve existing functionality; a screen is not accepted just because it looks similar. Every important control must have a real action, visible result, persistent state where expected, and automated or documented manual evidence.

## Baseline observations

- The main shell defines 14 sidebar destinations and an eight-step workflow rail.
- Static UI acceptance tests exist in `tests/test_stage73_ui_acceptance.py`; these guard routing and prototype anchors but are not substitutes for interactive runtime tests.
- The canonical acceptance criteria are in `docs/DRAGON_STUDIO_ACCEPTANCE_CHECKLIST.md`.
- The canonical full-app visual prototype is `docs/prototypes/Ryus_Audiobook_Dragon_Studio_Premium_Final.html`; the updated Voice Studio reference is `docs/prototypes/Ryus_Audiobook_Voice_Studio_Fixed_All_Steps.html`.
- Build #493 completed successfully, including the frozen application check, bundled voice asset check, installer build, and portable artifact upload. CI success does not independently prove every UI interaction works.
- The Voice Studio preview startup watchdog was added in Build #493. This is diagnostic behavior, not proof that the underlying preview-generation issue is fixed.

## Work order

### 8.2.1 — Navigation and responsive shell
- [x] Confirm the current implementation has the expected 14 navigation keys and workflow rail.
- [x] Confirm existing static acceptance coverage exercises sidebar routes and generation-navigation recovery.
- [ ] Run current UI acceptance suite in CI and inspect failures rather than relying only on source-string checks.
- [ ] Verify every destination can be opened at normal and reduced window sizes; verify scroll and collapsed sidebar behavior.

### 8.2.2 — Screen-by-screen behavioral parity
- [ ] Dashboard and Library: real project counts, search/filter, open/rename/delete safety.
- [ ] Import and Chapters: background extraction, cancellation/errors, text coverage, edit/reorder/split/merge, autosave.
- [ ] Voice Studio and Character Studio: provider configuration, profile persistence, preview transport, assignments and character-analysis recovery.
- [ ] Pronunciation and Sound Design: real dictionary scope/override behavior, catalogue filters, presets, music/cue controls.
- [ ] Production, Audiobooks and History: readiness, progress, pause/resume/cancel/retry, playback and history safety.
- [ ] Models, Performance and Settings: truthful runtime/hardware status, safe model operations, persisted settings.

### 8.2.3 — Production acceptance
- [ ] Test actual local preview generation and playback; record requested versus actual preview duration.
- [ ] Test a short multi-chapter M4B with chapter markers, title, author, cover and measured bitrate.
- [ ] Test mixed valid/empty chapters, cancel/retry/resume and offline behavior.
- [ ] Test installer and portable build from the same final candidate commit.

### 8.2.4 — Release evidence
- [ ] Record commit SHA, workflow run, artifact, expected result and observed result for each accepted gate.
- [ ] Clean only stale artifacts; retain the current validated candidate.
- [ ] Do not label the app bug-free or release-complete until remaining gates have evidence.

## Current status

**In progress.** The baseline and acceptance contract have been reviewed. No claim is made that all 14 screens have passed interactive testing. Next, run and strengthen UI acceptance coverage, then fix the first concrete failure with a regression test before rebuilding.
