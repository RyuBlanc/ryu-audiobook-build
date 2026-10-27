# Ryu's Audiobook — Stage 1 Consolidated Status and Evidence

**Updated:** 2026-10-27  
**Repository:** `RyuBlanc/ryu-audiobook-build`  
**Working branch:** `fix/native-ui-font-scale-learning-ai`

## Baseline — do not restart completed work

The prior conversation recorded the Stage 1 artifact checkpoint as successful:

- **Build Windows App #1453**
- Baseline commit: `dcc4dd17e778704804b99d23f924c18d073749fa`
- Checkpoint commit message: `[artifact-checkpoint] Validate Stage 1 stability and metadata fixes`

This is the baseline for continuity. Stage 1 implementation work is not being restarted. The older Actions run is no longer available through the current GitHub Actions API (it returns 404 after workflow-run cleanup), so this report preserves the checkpoint details from the prior conversation rather than claiming to have re-read its deleted logs.

## Latest accessible automated evidence

- **Build Windows App #1457:** [View workflow](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40537584156)
- Commit: `860914e80c8a36841a9fd3880296b03aa0436b18`
- Result: **PASS**
- Test cases recorded: **723 passed, 0 failed, 0 errors, 0 skipped**
- Evidence artifact: [Ryu-Audiobook-Test-Evidence-1457](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40537584156)
- Artifact contents: `stage1-test-results.json`, `stage1-test-results.txt`, `stage1-acceptance-matrix.md`
- Evidence artifact retention expires 2026-11-26 unless downloaded earlier.

Run #1457 was a tests-only work-branch run; its Windows packaging job was skipped by workflow policy. The next artifact-checkpoint run is required to produce a fresh installer and portable package for the same accepted code line. The workflow's required regression-test gate will execute as part of that package checkpoint; this is release-gate verification, not a restart of implementation.

## Stage 1 automated/source status

| Area | Evidence status |
|---|---|
| Metadata readiness gate and corrupt/unreadable cover validation | Automated contract/regression coverage exists; prior #1453 checkpoint recorded successful |
| Playable-output readiness and playback recovery | Automated regression coverage exists |
| Effects/motion and UI stability safeguards | Automated contract coverage exists; run #1457 passed |
| Job polling, stale-response protection, and in-place row updates | Automated contract coverage exists; run #1457 passed |
| Responsive shell, text scale, window preferences, and navigation | Automated contract coverage exists; run #1457 passed |
| Full automated suite | 723/723 passed in run #1457 |
| Fresh Windows installer/portable artifact after this checkpoint | Pending new artifact-checkpoint workflow |
| Manual interactive acceptance on the installed Windows build | Pending; cannot be inferred from source tests or a green CI build |

## Remaining Stage 1 closure gate — runtime only

Do not reopen completed source tasks unless the packaged runtime exposes a reproducible defect. On the fresh Windows artifact, record PASS/FAIL/BLOCKED for:

1. **UI-01 — Startup:** launch the installed app, confirm Premium V2 opens, settings persist, and no fallback UI appears.
2. **UI-02 — Readability:** inspect text overlap, clipping, contrast and ghost/doubled text.
3. **UI-03 — Flicker:** set Effects to High and Reduce Motion OFF; navigate repeatedly and observe idle and active-synthesis behavior for flicker/black flashes.
4. **UI-04 — Desktop behavior:** minimize, maximize/restore, move/resize, scroll/collapse the sidebar, then restart and verify saved preferences.
5. **UI-05 — Notifications/errors:** verify messages do not cover controls/player and success is only shown after actual success.
6. **UI-06 — Responsive layouts:** inspect 1920×1080, 1366×768, 1280×720 and a narrow window; exercise menus, dialogs, selections and scrolling.
7. **UI-07 — Repeated navigation:** navigate across pages while job polling/synthesis is active; verify no lost draft, scroll jumps, frozen UI or stale progress.
8. **Production metadata/output:** verify incomplete metadata blocks full-book generation with actionable guidance, preview remains separate, and a real generated audio file plays/replays with clear missing-file recovery.

For UI-03, explicitly record that Effects=High and Reduce Motion=OFF. The acceptance target is smooth operation without requiring Reduce Motion to be enabled.

## Closure rule

Stage 1's implementation and automated test baseline are carried forward as complete. Do not repeat those tasks. Stage 1 can be marked fully closed after the fresh installer/portable package is built from the passing checkpoint and the runtime-only checks above are recorded against that exact build. Any actual failure should be fixed narrowly and regression-tested; do not restart the stage wholesale.
