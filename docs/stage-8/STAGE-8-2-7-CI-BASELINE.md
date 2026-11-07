# Stage 8.2.7 — CI stabilization baseline

**Repository:** `RyuBlanc/ryu-audiobook-build`  
**Working branch:** `stage-7/step-6-safe-auto-fallback`  
**Starting branch HEAD before this checkpoint:** `b9ae3e8fa497390e81ac393888acfecfe0ae7501`  
**Prior packaged baseline:** Build #2677, commit `e71c16b980c0dd1a669028761a9152ae246a6b0a`  
**Latest regression-only baseline:** Build #2680, commit `b9ae3e8fa497390e81ac393888acfecfe0ae7501`

## Stage 8 execution sequence

This work preserves the approved six-package sequence. Help & Guide is included within frontend/backend parity and final acceptance; it is not a seventh package.

1. **8.2.7 — CI stabilization:** establish a traceable regression and Windows packaging baseline; investigate failures/skips and preserve assertions.
2. **8.2.8 — Sound Design completion:** chapter BGM, cue insertion, mixing, Book Mix Preview and preview/final consistency.
3. **8.2.9 — Frontend/backend parity:** audit every approved destination and important control, persistence, navigation, responsiveness, error states and updated Help & Guide.
4. **8.2.10 — Generation reliability:** preview/full/selected-chapter generation, truthful progress, pause/resume/cancel/retry/recovery and M4B integrity.
5. **8.2.11 — Windows release validation:** installer and portable package from the same candidate; frozen app/assets and runtime smoke tests.
6. **8.2.12 — Final acceptance and Version 1.2.0 release:** full regression, user journey, evidence, limitations and release decision.

## Verified baseline evidence

### Build #2680 — regression suite

- Workflow: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42308707136
- Commit: `b9ae3e8fa497390e81ac393888acfecfe0ae7501`
- Tests job: success.
- Full regression suite: **1,258 tests passed**.
- Focused Stage 6 History/Task Manager preflight: passed.
- Frontend JavaScript syntax validation: passed.
- Isolated native Qt lifecycle regression: passed.
- Build job: **skipped**. This was a documentation-only commit and the workflow's build job runs on main, an `[artifact-checkpoint]` commit, or manual dispatch. A passing test-only run is not a package result.

### Build #2677 — prior Windows package baseline

- Workflow: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42306806612
- Commit: `e71c16b980c0dd1a669028761a9152ae246a6b0a`
- Tests job: success.
- Windows build job: success.
- Completed checks included frozen application verification, bundled voice assets/critical modules, packaged Sound Design/Music Library acceptance, installer payload, functional HTML installer, logo/hash checks and Defender scans.
- Installer artifact: `Ryu-Audiobook-Installer-2677`, 884,808,062 bytes; artifact archive digest `sha256:c1eb5f8cd62284e40c9e474a8f54bb6a75a77abcd8db478aa684bf50c88a3ef6`.
- Portable artifact: `Ryu-Audiobook-Portable-2677`, 1,368,242,573 bytes; artifact archive digest `sha256:b30ea1562ea88f0661c56907525b4da6df320d87582c3ca61914321604352fc4`.
- Release SHA-256 manifest artifact: `Ryu-Audiobook-Release-SHA256-2677`.
- Piper benchmark evidence artifact: `Ryu-Audiobook-Stage7-Piper-Benchmark-2677`.
- Artifacts were reported unexpired with expiry on 2026-12-06.
- The public release publishing step was skipped. No Version 1.2.0 release is authorized by this baseline.

## CI workflow behavior confirmed

`.github/workflows/build-windows.yml` runs regression tests on the Stage 7 branch family. The Windows package job is intentionally gated: it runs on main, when the commit message contains `[artifact-checkpoint]`, or for manual workflow dispatch. Therefore Build #2680's skipped package job is expected under the current workflow policy, not a failed test.

This baseline checkpoint is intentionally committed with the `[artifact-checkpoint]` marker so the workflow can validate and package the exact updated branch commit. The resulting run must be recorded below after GitHub Actions completes.

## Open acceptance items — do not mark as passed

- A package from the exact current Stage 8 candidate commit is still required.
- CI packaging does not prove installer or portable launch, real playback, real audio generation, UI responsiveness or absence of flicker/crashes on target Windows devices.
- NVIDIA, AMD and Intel accelerator checks remain pending until tested on corresponding hardware. The carried-forward warmed 30-second Qwen preview target is under 60 seconds; the latest recorded CPU timings are approximately 298–305 seconds, so that CPU target is not met.
- Investigate the large installer and portable sizes. Do not remove required offline assets or user data to meet a size target.
- No Version 1.2.0 version bump, tag or public release until all required acceptance evidence is recorded or a limitation is explicitly accepted.

## Stage 8.2.7 execution record

| Gate | Status | Evidence |
|---|---|---|
| Starting branch and commit | Verified | `b9ae3e8fa497390e81ac393888acfecfe0ae7501` |
| Regression baseline | Passed | Build #2680; 1,258 tests |
| Previous Windows package baseline | Passed | Build #2677; commit `e71c16b980c0dd1a669028761a9152ae246a6b0a` |
| Exact-branch candidate package | Pending | Record new artifact-checkpoint run here |
| Failure/skip root-cause audit | In progress | Package skip explained by workflow condition; no failed job in #2680 |
| Full requirement-level traceability | Established; verification pending | 128 requirement IDs and final acceptance items recorded in `STAGE-8-REQUIREMENT-TRACEABILITY.md`; statuses remain open until evidence is attached |
| Runtime/manual acceptance | Pending | Must be recorded separately from CI |



## Latest Stage 8 candidate reconciliation

The Stage 8 source branch has since advanced beyond the original `b9ae3e8` baseline with test-first Sound Design changes, Premium V2 action wiring fixes and the in-app Help & Guide. The current evidence record is `docs/stage-8/STAGE-8-REQUIREMENT-TRACEABILITY.md`.

- Sound Design: Chapter-Based explicit-only fallback, Same BGM single-track selection, single-bed legacy ambience handling, chapter asset validation and full-book preview safety/cancellation regressions are committed. Thirteen regression tests were added; none is marked passed without a matching-head run.
- Premium V2 parity: 108 direct adapter command names were statically checked against 132 host handlers; zero missing direct command names. The legacy storage action routes to Settings > Storage, stale source-less queue rows are hidden, and real Character Studio actions are no longer blocked by the old document-level guard.
- Help & Guide: searchable and expandable topic cards cover the major screens, latest BGM and preview rules, Qwen model-size setup, storage, recovery, troubleshooting and known limitations.
- Responsiveness: the full aspect-ratio, portrait, window-state, split-screen, mixed-monitor and 100/125/150/200% scaling matrix is recorded for manual execution.

The latest source-only checkpoint is Build #2798 on exact HEAD `7e8a20fdc9d812f558060f30b31faee49305f6a0`: the regression job passed 1,314 tests and the Windows package job was skipped because the commit did not contain `[artifact-checkpoint]`. The exact-head Windows package remains pending and is requested by the current documentation checkpoint commit.


## Exact-HEAD regression checkpoint — Build #2765

| Gate | Status | Evidence |
|---|---|---|
| Regression workflow | Passed | Build #2765; run 42358327101 |
| Exact tested commit | Verified | 65b6a8773e6bcd10e31041dfa2924fc3f07b9d92 |
| Windows package job | Skipped | Workflow condition requires [artifact-checkpoint], main, or manual dispatch |
| Installer / portable artifacts | Pending | No artifacts were produced by #2765 |
| SHA-256 manifest | Pending | Must be generated from the exact artifact-checkpoint commit |
| Packaged Windows acceptance | Pending | Must follow the exact-head package build |

Build #2765 closes the package-report regression assertions introduced during Stage 8 package optimization. It is a regression-only success, not a release package checkpoint. The next commit is intentionally an artifact-checkpoint documentation commit so the workflow runs both tests and the Windows packaging job against the same exact HEAD. No requirement is marked verified complete solely from this workflow.

### Follow-up regression checkpoint — Build #2767

- Exact commit: `df35adc0ecc34ffcb2ffc1f574cf5deaf797e0ba`.
- Workflow: [Build #2767](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42360081999).
- Result: regression `tests` job passed; Windows `build` job was skipped because this commit did not request an artifact checkpoint.
- Correction: packaged Production Preview selector acceptance now resolves the live option node on each poll and records selector diagnostics on timeout. A dedicated source-contract test protects this behavior.
- Boundary: this is regression evidence only. It does not supersede failed packaged acceptance in #2766 and does not establish frozen-app, installer, portable-package, or runtime acceptance.


## Stage 8 accumulated checkpoint evidence — Build #2758

- Exact source commit: `48436fa0f84e3d011cfe93dc6154d10fbe65ab11`.
- Workflow: [Build #2758](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42355220964) — both `tests` and `build` jobs succeeded.
- Regression suite: 1,280 tests passed.
- Windows package: HTML installer and portable artifacts created from the exact tested source.
- HTML installer artifact: `Ryu-Audiobook-Installer-2758`, 884,188,623 bytes.
- HTML installer SHA-256: `C60FC64DF84AB13F89F3D237F41A5AA4E44229C2AA71F9C1284ACA82A1F62C72`.
- Portable artifact: `Ryu-Audiobook-Portable-2758`, 1,368,264,705 bytes.
- Portable ZIP SHA-256: `6dfa47e6bfef788118bc854568284f331df323783e16a9c98dc7892e8428bc3d`.
- Release SHA manifest artifact: `Ryu-Audiobook-Release-SHA256-2758`; its archive SHA-256 is `3d16ceff0a3ea690803d37736ab3c16610f3247d9e7d8ec01d78eaa49c0bb797`.
- Packaged acceptance exercised Premium V2/native bridge startup, real frozen-app Music Library imports/filters/audio preview, chapter BGM rules and persistence, full-book mix preview, selected Production chapter preview, generation, embedded M4B chapters, playback/player, job retry/recovery, History/Task Manager and the automated 41-viewport responsiveness matrix.
- Windows installer integration installed, upgraded, launched the offline self-test/Premium V2 app, uninstalled and preserved user data.
- Package reporter recorded a 500,000,000-byte target miss. Package-size optimization remains deferred; do not remove offline assets to chase the target.
- **Release boundary:** build used `RYU_APP_VERSION=1.1.1`. This is a successful Stage 8 candidate package, not a Version 1.2.0 installer/release. Physical target-PC, actual listening, monitor/DPI and GPU-vendor checks remain separate.



## Latest source checkpoint — Build #2798 (7 November 2026)

- Branch: `stage-7/step-6-safe-auto-fallback`.
- Exact source HEAD: `7e8a20fdc9d812f558060f30b31faee49305f6a0`.
- Workflow: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42372464405.
- Regression: **1,314 tests passed**.
- Frontend syntax, isolated native Qt lifecycle regression and focused Stage 6 History/Task Manager preflight passed.
- Windows build job: skipped because the source commit did not contain `[artifact-checkpoint]`. This is not a package failure and did not produce installer/portable artifacts.
- The #2795/#2796 failures were traced to four stale contract assertions: three expected 1.1.1 after the source version became 1.2.0, and one expected the new `import.latest.get` bridge handler to have a capability-map entry. Those contracts were corrected; #2798 passed all 1,314 tests.

## Prior packaged checkpoint — Build #2768

- Commit: `9ff9bc05d70444c375c692839d2e8346d34b70cf`.
- Workflow: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42365316494.
- Regression: **1,293 tests passed**; Windows package job passed.
- Frozen-app acceptance: 97 logged PASS checks, including real Sound Design/Music Library operations, chapter BGM strategies/offsets, cues, full-book mix preview, selected Production chapter preview and Save As, 30/60/90-second measured previews, full generation, M4B chapters, player/mini-player, pause/resume/cancel/retry/recovery, persistence and 41 viewport emulations.
- Installer artifact `Ryu-Audiobook-Installer-2768`: 846,239,172 bytes.
- Portable artifact `Ryu-Audiobook-Portable-2768`: 1,183,224,790 bytes.
- Release SHA manifest `Ryu-Audiobook-Release-SHA256-2768`: 3,046 bytes.
- Piper benchmark artifact `Ryu-Audiobook-Stage7-Piper-Benchmark-2768`: 803 bytes.
- Artifacts expire 7 December 2026. Packaged app version was 1.1.1; it predates current 1.2.0 source updates and is not the current candidate.

## Current candidate package request

The current commit includes the `[artifact-checkpoint]` marker so the workflow should run both regression and Windows packaging on the exact new HEAD. Record the new run, test total, package artifacts, checksums, sizes and expiry here only after the workflow completes. No public release/tag is being created by this checkpoint.



## Final exact-head Windows package checkpoint request — 7 November 2026

The previous #2681 package is retained as historical Stage 8.2.7 evidence, but it is not the latest source candidate. Do not rebuild #2672 or #2681. The branch was rechecked immediately before this checkpoint request:

- Working branch: `stage-7/step-6-safe-auto-fallback`.
- Exact pre-checkpoint branch HEAD: `8774de2caf80068f1ef2bde27c88a0b8ec6c2776`.
- Latest source regression run: Build #2803, workflow https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42378185367 — tests passed; Windows build job skipped because this was not an artifact-checkpoint commit.
- #2803 source correction: Generate page grid sizing for available workspace width; packaged acceptance contract asserts the responsive 1280x720 overflow condition.
- Prior packaged failure #2799/#2800: packaged acceptance raised `ReferenceError: stage8ResponsiveDestinations is not defined`. These failures had successful test jobs but failed the packaged UI acceptance step, so no installer/portable artifacts were produced.
- Prior packaged failure #2801: the Generate page overflowed at 1280x720 (scrollWidth 1058, available width 1004). This is the responsive defect addressed by the #2803 source correction; packaged confirmation is still required.
- Build #2802 also passed its regression job but skipped Windows packaging.
- The branch had no commits newer than `8774de2caf80068f1ef2bde27c88a0b8ec6c2776` at the pre-check.

This request intentionally adds an `[artifact-checkpoint]` documentation commit on top of the exact source HEAD above. Its purpose is to trigger the existing `.github/workflows/build-windows.yml` package gate without changing application source. The resulting workflow must run the tests and Windows build jobs on the same resulting HEAD.

### Required outcome for this checkpoint

1. Full regression suite and focused Stage 6 History/Task Manager preflight pass on the exact checkpoint commit.
2. Packaged Sound Design/Music Library acceptance passes, including the corrected responsive Generate page at 1280x720 and the existing restart/persistence checks.
3. Frozen application validation, bundled voice/model assets and critical modules pass.
4. Functional HTML installer is built and its UI/native bridge startup is verified.
5. Core Windows installer install/upgrade/launch/uninstall checks pass where present in the current workflow; user data preservation is verified.
6. Installer and portable artifacts are uploaded from the same exact commit.
7. Release SHA-256 manifest, package-size report and Microsoft Defender results are uploaded/recorded.
8. Stage 7 Qwen CPU/Piper evidence is retained. NVIDIA, AMD ROCm, Intel XPU and hands-on physical target-PC acceptance remain DEFERRED / NOT RUN, not passed.
9. The package size target below 500 MB remains an audit target; report actual sizes and do not remove required offline assets to force compliance.
10. The public Version 1.2.0 release/tag remains gated by complete release acceptance. This artifact checkpoint does not publish a release.

### Execution status

- Source HEAD verified before checkpoint commit: `8774de2caf80068f1ef2bde27c88a0b8ec6c2776`.
- Documentation marker commit: pending.
- Matching-head regression: pending.
- Matching-head Windows package: pending.
- Packaged acceptance and artifact verification: pending.

After GitHub Actions completes, replace the pending statuses with the exact run URL, run number, resulting HEAD SHA, test totals, every job/step conclusion, artifact names/sizes/digests/expiry and any failures. Do not infer completion from the workflow's overall label alone.


## Build #2804 failure analysis and narrow Sound-page correction — 7 November 2026

- Workflow: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42381481432
- Exact checkpoint commit: `8870c6d44ab122d86a344b95507061ca79f991ea`.
- Regression job passed: **1,319 tests**.
- Frozen EXE self-test and three Premium V2 startup launches passed. Bundled offline Piper/Kokoro assets and 26 real starter BGM tracks were verified. The packaged workflow generated real M4B/M4A outputs and passed the restart/persistence, playback, project identity, History and Task Manager checks reported before the responsive failure.
- Packaged acceptance then failed on the Sound page at **600x800**: page scrollWidth **666 px**, available workspace width **590 px** (76 px overflow). Generate at 1280x720 passed: 994 px against 1004 px available.
- The 41-resolution Stage 7 matrix remains preserved. The earlier Stage 7 fixture covered the shared shell, Player, Library, Mini-player, History, Task Manager and job details; it did **not** activate every destination at every viewport. Stage 8's expanded all-15-destination loop exposed the previously untested Sound-page case.
- The failure occurred before installer packaging; downstream installer/portable build, Defender scan and uploads were skipped. #2804 produced no artifacts.
- Root-cause correction committed in source commit `238b7875cb6edbeeec40969054ed59da7b44e9b2`: narrow Sound-page grid now uses `minmax(0,1fr)`, its grid children are shrinkable, and the Sound toolbar/selection controls are constrained within the viewport. The existing all-destination responsive assertion was not weakened or removed.
- This is a targeted CSS correction, not a restart of Stage 7's responsive work. Matching-head packaged verification is still required.

## Matching-head checkpoint after Sound-page correction — 7 November 2026

- Source correction commit: `238b7875cb6edbeeec40969054ed59da7b44e9b2`.
- Source branch: `stage-7/step-6-safe-auto-fallback`.
- This documentation-only `[artifact-checkpoint]` commit requests a regression + Windows package run on the exact resulting HEAD, with the CSS fix as its parent.
- Regression: pending.
- Packaged Sound Design/Music Library acceptance: pending.
- Installer/portable packaging and uploads: pending.
- No Stage 8 package is marked complete by this checkpoint request alone. The six approved packages 8.2.7–8.2.12 still require their own requirement-level and release-gate evidence. The Version 1.2.0 release remains gated; #2804's frozen EXE was v1.1.1.


## Responsive acceptance investigation and corrective preflight — 7 November 2026

### Failure evidence

- Build #2804 (commit `8870c6d44ab122d86a344b95507061ca79f991ea`) passed 1,319 regression tests and frozen-app startup, then failed packaged responsive acceptance at 600x800: scrollWidth 666, available width 590.
- Build #2806 (commit `ed955bbf255e942444cb2923428ead38def94793`) repeated the same 666/590 failure after the initial CSS adjustment.
- Build #2808 (commit `525257e27fc4594a6dd9ee4b683adf0b61d9748a`) failed at 664/590 after changing the responsive fixture. The same logs confirm real M4B full generation, Production Preview Save As, retry M4B, restart persistence, player restoration, History and Task Manager checks completed before the responsive assertion stopped the job.
- These failed runs produced no installer/portable artifacts. Their downstream installer, Defender and upload steps were skipped.

### Confirmed causes and corrections

1. **Mobile Sound import panel retained the tablet flex row.** The `max-width:1150px` CSS sets `.sound-import-box` to a horizontal flex row. The previous `max-width:760px` block never overrode that declaration. At 600px, the import explanation, label, category selector and import button could therefore remain on one horizontal row. The mobile rule now switches this panel to a single-column grid, constrains its children to the available width and makes the selector/button full-width. Source correction is in commit `539f1a8f0bb96c8f8ec42e18754754f6795f4d7a`.

2. **Responsive fixture must use one complete app DOM.** The prior fixture cloned the complete `#app` and separately re-appended a Sound page extracted from it; its removal regex was double-escaped, so it did not reliably remove the original page. The corrected fixture now uses the one complete `#app` clone, asserts exactly one `#sound` element and checks that the real `#soundTrackGrid` markup exists. It also reports the top overflowing descendant elements (bounds, scroll width, min-width, grid columns and overflow mode) if a page still fails. The all-15-destination/41-viewport assertions remain unchanged.

3. **Intermediate preflight correction.** Commit `93909739e291f81305f7d98199107d984da5ec65` had a malformed intermediate CSS insertion. Test-only Build #2809 failed the new mobile CSS contract test for that reason. The mobile media rule was reconstructed in full in `539f1a8f0bb96c8f8ec42e18754754f6795f4d7a`.

### Matching-head regression preflight

- Build #2810: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42388007419
- Exact source HEAD: `539f1a8f0bb96c8f8ec42e18754754f6795f4d7a`.
- Full regression suite: **1,321 tests passed** (44.931 seconds).
- The new tests `test_sound_import_controls_stack_at_narrow_viewports` and `test_responsive_fixture_uses_one_complete_sound_page_and_reports_overflowing_elements` both passed.
- Frontend JavaScript syntax validation, isolated Qt lifecycle and focused History/Task Manager preflight passed.
- Windows package job was skipped because this was intentionally a test-only commit. This is a valid source preflight, not a new package artifact.

### Next exact-head package checkpoint

The following `[artifact-checkpoint]` commit is documentation-only and requests the Windows package on the exact source HEAD above. The packaged Sound Design acceptance must pass the actual Sound page through the full 41-viewport/all-15-destination matrix. Only then can the workflow continue to installer/portable packaging, Defender, manifests and uploads. If responsive acceptance still fails, use its new element-level diagnostics and do not weaken the assertion.



## Sound track-grid overflow correction and matching-head preflight — 7 November 2026

- Build #2811 failed packaged responsive acceptance with a precise actual-Sound-page diagnostic at 600x800: page scrollWidth 668 versus available 590.
- The element-level evidence identified `#soundTrackGrid` as a two-column grid with computed columns `257px 257px` and scrollWidth 636. Each `.sound-track-info` descendant also had internal scroll widths up to 350px in a 218px-wide content box. The previous mobile import-panel override did not change this grid.
- Source correction commit `c7b79a4f1efb6f186d0b01e1c7a36f3b61fbc35f`: at max-width 760px, Sound track grid becomes a single `minmax(0,1fr)` column; grid children/cards/info are constrained to available width and track text may wrap. No responsive assertion was weakened.
- Regression contract tests now require the single-column grid and constrained track content.
- Build #2812: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42391383182 — exact source commit `c7b79a4f1efb6f186d0b01e1c7a36f3b61fbc35f`; full regression **1,321 tests passed**. Windows packaging was skipped by design.
- The all-destination responsive overflow test remains enabled. Matching-head Windows acceptance is the next gate; if any further overflow remains, element diagnostics will identify the actual descendant.

