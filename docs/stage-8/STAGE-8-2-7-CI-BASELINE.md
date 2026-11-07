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
- NVIDIA, AMD and Intel accelerator checks remain pending until tested on corresponding hardware. The carried-forward warmed 30-second Qwen preview target is under 60 seconds; the supplied Stage 8 source records the hosted CPU path at 268.184 seconds, so that CPU target is not met.
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
| Full requirement-level traceability | Pending | To be completed from the Master Bug & Change Register and Stage 8 detailed requirements |
| Runtime/manual acceptance | Pending | Must be recorded separately from CI |

