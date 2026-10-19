# Stage 8.2 — Full UI parity and production verification

**Branch:** `fix/import-qa-speaker-hover-hardware`  
**Started:** 2026-10-19  
**Baseline commit:** `8357e2eef8a0a217077f54b14bfaf0298e258fab`  
**Baseline Windows build:** [Build #493](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39186820298) — successful

## Stage goal

Verify all 15 Premium V2 destinations against the approved HTML and the behavioral acceptance checklist. Preserve existing functionality; a screen is not accepted just because it looks similar. Every important control must have a real action, visible result, persistent state where expected, and automated or documented manual evidence.

## Baseline observations

- The packaged Premium V2 HTML defines 15 sidebar destinations. The eight-step production workflow remains a separate workflow rail.
- Static UI acceptance tests exist in `tests/test_stage73_ui_acceptance.py` for legacy shell guardrails, and `tests/test_premium_v2_integration_contract.py` for the 15-destination Premium V2 HTML and bridge. Neither substitutes for interactive runtime tests.
- The canonical acceptance criteria are in `docs/DRAGON_STUDIO_ACCEPTANCE_CHECKLIST.md`.
- The canonical packaged visual source is `assets/frontend/ryu_audiobook_premium_v2.html` (from the user's `Ryus_Audiobook_Premium_V2.html`); older files in `docs/prototypes/` are historical references.
- Build #493 completed successfully, including the frozen application check, bundled voice asset check, installer build, and portable artifact upload. CI success does not independently prove every UI interaction works.
- The Voice Studio preview startup watchdog was added in Build #493. This is diagnostic behavior, not proof that the underlying preview-generation issue is fixed.

## Work order

### 8.2.1 — Navigation and responsive shell
- [x] Confirm the current implementation has the expected 14 navigation keys and workflow rail.
- [x] Confirm existing static acceptance coverage exercises sidebar routes and generation-navigation recovery.
- [ ] Run current UI acceptance suite in CI and inspect failures rather than relying only on source-string checks. Latest Windows workflow run #612 is queued; no result is available yet.
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

**In progress.** Premium V2 is selected by `app/main.py` and embedded using `QWebEngineView` / `QWebChannel`; `requirements.txt` includes `PySide6-WebEngine`. Recent implementation work connects Dashboard recent-project cards/actions, Library search and filters, persisted Background Jobs controls, real file-input/drag-drop imports, and supported Sound Design catalogue actions to the backend. The adapter passes a JavaScript syntax check, and regression contract tests cover these changes. The latest Windows workflow run (#612, commit `5d42174701ef82e1b6bb234b92c9ff669b11bd6e`) is queued, so the tests and packaged build are not yet validated. Chapter-level cue editing, full-book mix preview, and several other controls remain open items. No claim is made that all 15 destinations have passed interactive testing.

Next: obtain a completed Windows CI run, fix any first concrete failure, then continue screen-by-screen behavior and end-to-end audio verification.
