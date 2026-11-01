# Test Report — Premium V2 Integration

**Audit date:** 20 October 2026
**Current source commit before Stage 1 audit commit:** `eca9cf1a8330e2dcfce697f66233a73740e25ae0`

## Static checks performed for this audit

| Check | Result | Evidence |
|---|---|---|
| Approved HTML fingerprint | Pass | Local file is 1,436,954 bytes, SHA-256 `e70f630d99e75f07fdd704bb1931910dd972795390ae0af0d29b07b9118abf95`; computed Git blob SHA matches repository frontend blob `0da8d4a60c69530325fff9af7e516d251dc442cd`. |
| Page inventory | Pass | Exactly 15 `section.page` screens: dashboard, library, import, chapters, voices, characters, pronunciation, sound, generate, player, history, models, performance, settings, help. |
| Static controls | Pass as inventory only | 384 buttons/inputs/selects/textareas; no duplicate IDs among 279 initial IDs. Count is not an interactive-coverage result. |
| Prototype/demo residue scan | Gap confirmed | Inline HTML contains timer/demo functions and `localStorage` usage. Every visible action must be checked against the adapter and host. |
| Bridge/command inventory | Gap confirmed / partially connected | 61 host dispatcher handlers and 54 distinct literal adapter bridge-call names; some UI functions are still guarded or prototype-only. |
| Capability-map parity | Small defect corrected in this commit | `chapter.split` handler and adapter call existed but the capability map omitted it; the map and contract test are updated. |
| Python unit test suite in this environment | Not run locally | Repository source was inspected through connected GitHub source tools; the prior Windows CI run is the available full test evidence. |

## Latest verified CI run before this audit commit

- Run: [#731 — Build Windows App](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39397963882)
- Commit: `eca9cf1a8330e2dcfce697f66233a73740e25ae0`
- Result: completed successfully.
- Tests: `Ran 308 tests in 34.431s`.
- Windows packaging: installer creation and portable application packaging/artifact upload succeeded.
- Installer artifact: [Ryu-Audiobook-Installer-731](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39397963882/artifacts/12253986738).
- Portable artifact: [Ryu-Audiobook-Portable-731](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39397963882/artifacts/12254815829).
- No GitHub Release publication is claimed.

The Stage 1 audit commit changes bridge capability advertisement/tests and documentation, so this CI result must not be represented as testing those new edits. The workflow triggered by the new commit must be inspected before claiming the updated branch passes.

## Outstanding acceptance

| Test | Result | Next action |
|---|---|---|
| Embedded WebEngine startup and navigation | Not manually accepted | Launch the exact new package on Windows and visit all 15 pages. |
| Full control-to-handler coverage | Incomplete | Finish and maintain the control matrix in `PREMIUM_V2_SCREEN_FUNCTION_MAP.md`; guard all demo-only controls. |
| Import/extraction and chapter boundaries | Not end-to-end accepted | Run supported-format fixtures and long-book tests; preserve story punctuation and manual edits. |
| Saved voice/profile and exact preview duration | Not end-to-end accepted | Inspect actual preview request, generated duration, audio and playback for saved-profile selection. |
| Cast assignments and production routing | Partial | Persist speaker-line assignments and verify the chosen character voice is used in synthesis. |
| Pause/resume/retry/checkpoint and restart recovery | Not fully accepted | Exercise real jobs, verify reused chunks and independent history. |
| Output validation and player | Not end-to-end accepted | Verify actual audio stream, duration, chapters, metadata, cover and in-app playback. |
| Models/performance/settings security | Partial/unavailable | Verify connected operations and honest disabled behavior; do not invent measurements or store secrets in plaintext. |
| Visual comparison at target resolutions | Not run | Compare exact source and packaged app at 1920×1080, 1366×768, 1280×720 and supported narrower widths. |
| Manual install/uninstall | Not run | Complete only after implementation gates and retain user data unless explicit deletion was chosen. |

**Conclusion:** The current source and packaging have a successful automated baseline, but the application is not yet accepted as fully connected or bug-free. See `docs/STAGE_1_GAP_REGISTER.md` for prioritized closure criteria.