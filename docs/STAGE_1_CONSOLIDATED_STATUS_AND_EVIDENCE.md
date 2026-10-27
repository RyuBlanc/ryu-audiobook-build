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

## Latest verified automated evidence and artifact checkpoint

- **Build Windows App #1458:** [View workflow](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40538858884)
- Commit: `ab4a24b700106e17f149931c7da3d6d2dbff040d`
- Result: **PASS** — tests, Windows build/package validation, and post-build cleanup all succeeded.
- Test cases recorded: **723 passed, 0 failed, 0 errors, 0 skipped** in 42.149 seconds.
- Test evidence: [Ryu-Audiobook-Test-Evidence-1458](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40538858884)
- Windows installer artifact: [Ryu-Audiobook-Installer-1458](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40538858884) — reported artifact size 878,077,602 bytes.
- Portable Windows artifact: [Ryu-Audiobook-Portable-1458](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40538858884) — reported artifact size 1,349,440,190 bytes.
- SHA-256 manifest: [Ryu-Audiobook-Release-SHA256-1458](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40538858884).
- These Actions artifacts expire 2026-11-26 unless downloaded earlier.

Run #1458 is a successful artifact checkpoint, not a new implementation phase. The installer and portable packages were generated and uploaded from the same passing commit. The build did not publish a new public release because this is a work branch; download the candidate artifacts from the Actions run.

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
