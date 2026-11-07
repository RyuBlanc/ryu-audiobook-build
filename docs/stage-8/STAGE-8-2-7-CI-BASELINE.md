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

The latest marker checkpoint must be validated by the exact branch's push-triggered Windows workflow. The connected GitHub status interface currently returns no combined status and no PR-triggered workflow run for the latest push candidate; this does not prove that a push workflow passed or failed. Record its actual Actions run, tests, build job, artifact hashes and expiry once visible. Until then, matching-head CI remains **PENDING / UNVERIFIED**.


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

