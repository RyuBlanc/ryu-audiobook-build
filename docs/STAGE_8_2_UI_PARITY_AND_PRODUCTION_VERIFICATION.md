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
- [x] Run current Windows CI and inspect failures. Build #618 succeeded after the stale integration-contract assertions were aligned with current adapter behavior; this is CI evidence, not interactive runtime acceptance.
- [ ] Verify every destination can be opened at normal and reduced window sizes; verify scroll and collapsed sidebar behavior.

### 8.2.2 — Screen-by-screen behavioral parity
- [ ] Dashboard and Library: real project counts, search/filter, open/rename/delete safety.
- [ ] Import and Chapters: background extraction, cancellation/errors, text coverage, edit/reorder/merge, autosave. Chapter Studio's visible Split chapter action is connected to a persistent backend split at the editor cursor (Build #624 passed). Text edits now debounce to a persistent backend autosave after 900 ms and show saving/saved/failure status (Build #627 passed). A follow-up guard now clears any pending autosave before splitting, preventing the old full-chapter snapshot from overwriting the split result; the adapter now cancels queued snapshots, serializes in-flight autosaves to prevent out-of-order writes, and waits for any active save before splitting or manually saving. Build #630 passed the previous queued-timer guard; the stronger serialization guard is awaiting its own CI run and real-project verification. Merge remains an open functional gap because the approved Chapter Studio HTML has no visible merge control; do not add one by redesigning the HTML.
- [ ] Voice Studio and Character Studio: provider configuration, profile persistence, preview transport, assignments and character-analysis recovery.
- [ ] Pronunciation and Sound Design: real dictionary scope/override behavior, catalogue filters, presets, music/cue controls.
- [ ] Production, Audiobooks and History: readiness, progress, pause/resume/cancel/retry, playback and history safety.
- [ ] Models, Performance and Settings: truthful runtime/hardware status, safe model operations, persisted settings.

### 8.2.3 — Production acceptance
- [ ] Test actual local preview generation and playback on Windows; record requested versus actual preview duration.
- [x] Automated multi-chapter M4B acceptance covers chapter markers/titles, title, author, narrator, language, genre, cover art, decodability, and measured encoded-audio bitrate (>=128 kbps). Current full test suite passed in Build #637.
- [x] Static integration contract guards mixed valid/empty chapter handling: empty narration chapters are skipped and counted, while an all-empty book is rejected before generation. Current full test suite passed in Build #637.
- [x] Automated GenerationManager tests verify pause/resume at chapter checkpoints and cancellation while paused; Build #637 passed the full unit-test suite. [ ] Exercise cancel/retry/resume and offline behavior with the packaged Windows app.
- [ ] Test installer and portable build from the same final candidate commit.

### 8.2.4 — Release evidence
- [ ] Record commit SHA, workflow run, artifact, expected result and observed result for each accepted gate.
- [ ] Clean only stale artifacts; retain the current validated candidate.
- [ ] Do not label the app bug-free or release-complete until remaining gates have evidence.

## Current status

**Stage 8.2.2 complete for the implemented CI-covered interactions; Stage 8.2.3 production acceptance is now in progress.** This is not a claim of full interactive UI parity: merge, per-chapter sound cues, full-book mix preview, responsive/manual screen acceptance, and real Windows voice-preview verification remain open. Premium V2 is selected by `app/main.py` and embedded using `QWebEngineView` / `QWebChannel`; `requirements.txt` includes `PySide6-WebEngine`. Recent implementation work connects Dashboard recent-project cards/actions, Library search and filters, persisted Background Jobs controls, real file-input/drag-drop imports, the Chapter Studio split action, and supported Sound Design catalogue actions to the backend. Build #618 (commit `cd3103e21631a5565abf5e399190f44bc36da4a5`) completed successfully, including tests, frozen-application validation, bundled voice assets/critical modules checks, installer build, and portable artifact upload. Artifacts: `Ryu-Audiobook-Installer-618` (648,478,960 bytes) and `Ryu-Audiobook-Portable-618` (1,347,970,862 bytes); both expire 2026-10-22. This confirms CI/package creation, not successful manual Windows runtime testing. Chapter-level cue editing, full-book mix preview, and other controls remain open. No claim is made that all 15 destinations have passed interactive testing.

Build #637 (commit `85060997c54f35f13d3eaf01eb1e9178aab00ac9`) passed the full Windows CI workflow, including unit tests, frozen-app validation, bundled voice asset/critical module checks, installer creation, and portable artifact upload. The new generation-control tests cover pause/resume at a chapter checkpoint and cancellation while paused. This is automated evidence only; packaged-app interaction still needs manual Windows verification.

Build #636 (commit `97991626061758e98f02da3ab91be6de00d00b55`) passed the roadmap update workflow. Build #637's passing full test suite now validates the measured M4B bitrate assertion and mixed-empty-chapter generation contract on the same candidate lineage.

Build #630 (commit `693dd1758ccf35aac7ef81fe862de4b1c06b579c`) passed: application validation/build, frozen application, voice assets/critical modules, installer, portable artifact and cleanup. Artifacts `Ryu-Audiobook-Installer-630` (648,256,728 bytes; SHA-256 `f73af4eca59d9229b190296526611a5ad03228a69a460953e9554fad66edea8f`) and `Ryu-Audiobook-Portable-630` (1,347,977,791 bytes; SHA-256 `78568309dd641bd1a7ec7bb4097978bd1ac1f712dcd455e235f88e1ce70a3ba2`) expire 2026-10-22. Release publishing was skipped. The following stronger save-serialization fix is in a newer commit and needs its own CI run.

Build #627 (commit `d0937bb6ef09e8d8d4fe01640d15583028e84964`) passed: application validation/build, frozen application, voice assets/critical modules, installer, portable artifact and cleanup. Artifacts `Ryu-Audiobook-Installer-627` (649,497,977 bytes; SHA-256 `285dcb712847b4fdebaf4300f878d4e1aaf31d1f8558881ca44748599d78edff`) and `Ryu-Audiobook-Portable-627` (1,347,976,846 bytes; SHA-256 `980b3369d73c105e9c98bde28081df053381a9d5e88c73024958250ceee93469`) expire 2026-10-22. Release publishing was skipped. Next: validate the split/autosave race guard in CI, then continue screen-by-screen behavior and end-to-end audio verification.


## Latest Stage 8.2.3 evidence

- **Build #637:** [successful Windows build](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39303588976), commit `85060997c54f35f13d3eaf01eb1e9178aab00ac9`. Unit tests and Windows packaging passed, including the new pause/resume/cancel tests.
- **Still open:** actual local voice-preview playback and requested-vs-observed duration on Windows; packaged-app cancel/retry/resume and offline behavior; installer/portable launch smoke test on the same final candidate.
- **Visual/functional gaps still tracked:** chapter merge without redesigning approved HTML, per-chapter sound-cue assignment, full-book mix preview, responsive/manual checks across all destinations.
