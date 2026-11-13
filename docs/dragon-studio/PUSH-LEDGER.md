# Dragon Studio — Push and Retry Ledger

Every commit and workflow attempt is tracked separately. A failed attempt remains failed in this history. A retry is the same commit revalidated; a code correction is a new commit.

## Rules
- Record actual changed paths and behavior, not only the subject line.
- Include commit SHA, run number, internal run ID, URL, test totals and package outcome.
- A later pass does not erase the failed attempt.
- A correction creates a new commit and is marked NEW FIX; a rerun of unchanged SHA is marked RETRY.

## History

| Commit SHA | Type | Exact changed paths / behavior | Actions run(s) | Result |
|---|---|---|---|---|
| `c951160c1b68467e11b17f0c2977d96999e147fb` | NEW FIX | `app/ui/premium_v2_host.py`; `tests/test_stage5_generation_eta_stability.py`; `tests/test_stage811_functional_checkpoint.py` — ETA upward adjustment and deterministic tests. | Build #3241 | Passed 1,496 tests and Windows package at that earlier head. |
| `a8aabd73d122562c300d9a1b8e9e66820ac10ce7` | NEW FIX | Three Qwen acceptance workflow YAMLs — add `dragon-studio/**` triggers, retaining Stage 5/7 triggers. | Build #3242, #3243 | #3243 passed regression/package; #3242 package skipped by trigger/path conditions. |
| `f9457470293cbd0213efd2d558f65b679e504d5a` | NEW FIX | `app/tts/providers/qwen_character.py` — report worker exit code/stderr tail on early exit/timeout. | Build #3244 / run 43014806424 | Tests passed (1,496); package skipped on push run. |
| `0c1fdab929f4e6e3c16cb2dfefba8c510b37cf03` | NEW TEST; FIXTURE DEFECT INTRODUCED | `tests/test_qwen_runtime_safety.py` — added timeout and early-exit diagnostics tests; finite fake-clock iterable was too short. | Build #3245 / run 43014810959 | Failed: 1,498 tests, 1 error in timeout diagnostic fixture. |
| `d03192cf62cd1712754d7b47136ea6d15ddcc318` | NEW FIX | `tests/smoke_qwen_real_preview.py` — writes startup diagnostic JSON containing error, worker pid/exit, model/backend and stderr tail. | Build #3246 / run 43014816798 | Failed on same inherited test-fixture defect. |
| `a8aabd73d122562c300d9a1b8e9e66820ac10ce7` | SAME SCOPE / PR SYNC | Same three Qwen trigger files, no further runtime behavior. | Build #3247 / run 43014817131 | Failed on inherited test-fixture defect. |
| `0c1fdab929f4e6e3c16cb2dfefba8c510b37cf03` | SAME SCOPE / PR SYNC | Same Qwen timeout test. | Build #3248 / run 43014820763 | Failed on inherited test-fixture defect. |
| `b29d9e162a32e149b5e51c16a172e30d46ded4aa` | NEW FIX (ARTIFACT COLLECTION) | `.github/workflows/qwen-cpu-contract-acceptance.yml` — adds worker log to upload path using tilde expansion. | Build #3249 / run 43014823323; Build #3250 / run 43014829590 | Both failed on inherited test-fixture defect before package. |

## Corrective push A — commits #3251–#3255

Commits `8f3ac933a5d034df1ba91ab73e69e55e889cd3f1`, `9ffec2f43fdae005d224783727fef3daa05a76c0`, `59cb7bed2c10a8b1d9cb669021216512bfcd58c4`, `51a43378b27830f20ad7861b79deea324ed53e35`, and `22ae973607794ada48b4f356321b884cebfa7eb5`.

The commits are pushed but unaccepted. The test still expected lowercase `timed out` while production correctly emitted `Timed out`, and its fake worker lacked the stream attributes needed by `close()`. CPU Qwen run #11 (internal ID `43017828264`) failed in the focused 56-test group; real preview did not run and no worker stderr artifact was available. Original failures #3251–#3258 remain failed.

## Corrective push B — commits #3259–#3262

Commits:
- `b7006e4cadbb36170909ed384773754f0c722916` — `tests/test_qwen_runtime_safety.py`: case-insensitive timeout message expectation, process-shaped fake for early exit, targeted stderr-handle cleanup.
- `86f64fa309d754a3104039c25dab5e97e81b76c8` — `.github/workflows/qwen-cpu-contract-acceptance.yml`: normalized Windows path separators in artifact collector.
- `27d569939edc20fd4d49d515ad67e8a5c91916af` — bug register: record #3251–#3258 follow-up diagnosis.
- `5bac4b58cd80bbaf5a3e528857fe3acf196fcee0` — ledger: record correction and retry state.

**Validation state:**
- Push #3259 / run `43020565701`: tests passed (1,498); build job skipped because this is a push validation.
- PR #3261 / run `43020576268`: tests passed (1,498); exact package job on this intermediate head is not the final current-head package gate.
- Current PR #3264 / run `43020594973`, exact head `5bac4b58cd80bbaf5a3e528857fe3acf196fcee0`: tests passed (1,498). Windows build job `130523687954` is in progress; package outcome pending.
- CPU Qwen run #12 / `43020566273`: real CPU runtime install is still active; real-preview outcome pending.

Original failed runs #3251–#3258 remain recorded as failures. This correction resolves the two test errors. Latest PR #3267 has passed 1,498 regression tests, while its Windows package is still running. CPU real-preview and hardware acceptance remain open.


## Documentation follow-up commits #3265–#3266

- `2897e31bedb87f3945f93765717d7282d03bb8c0` — `docs/dragon-studio/POST-1.2.0-BUG-REGISTER.md`: record the 1,498-test pass at #3264 and pending package status at that time.
- `17868d6afe1230f4d1cfb57326f260a4239af8e4` — `docs/dragon-studio/PUSH-LEDGER.md`: record the current validation state. This commit triggers PR run #3267 (internal run ID `43021199482`).

#3267 is the latest PR validation. Its tests job passed all 1,498 tests; build job `130525480144` remains in `Prepare, validate and build application`. The CPU Qwen real-preview step in run #12 (`43020566273`) remains in progress after focused contract tests and expression protocol smoke passed. No package or real-Qwen result is to be inferred until these jobs finish.

## Exact-head PR package checkpoint — Build #3323

- **Commit:** `1c235746646a4a3ba0263178cb1bba045ebffd93` — NEW FIX, test contract only: `tests/test_regressions.py`.
- **Run:** [#3323 / 43139856426](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43139856426), PR #35.
- **Regression:** all **1,523 tests passed** (67.393s); JS syntax, isolated Qt lifecycle and Stage 6 focused preflight passed.
- **Windows package:** success. Frozen app/critical bundled assets, real two-chapter Piper M4B, packaged Sound Design/Music acceptance, HTML/core installer, install/launch/upgrade/uninstall, logo/hash, package size and Defender scan passed.
- **Artifacts:** installer 846,232,402 bytes; portable 1,183,868,011 bytes; SHA manifest 3,043 bytes; real M4B 8,935,889 bytes. GitHub artifact IDs: installer `13911295415`, portable `13910333194`, M4B `13910015598`, manifest `13909829921`.
- **Skipped:** optional Stage 7 real Piper benchmark upload and public release publication. This run did not execute dedicated physical Qwen GPU workflows.
- **Status:** exact-head automated package checkpoint green; PR #35 remains open/draft. User-device Qwen profile, GPU timing, full-novel generation/playback, long-run progress/ETA, durable job interruption/recovery, physical display/DPI and Help & Guide acceptance remain open. Do not substitute the Piper smoke M4B for a full-book Qwen/cast acceptance.



## Build #3326 failure and #3327 correction record

- **Build #3326:** [run 43159563751](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43159563751), commit `0e93016f613051ae17e40b2f25f3d9183ebd4e63`. The focused preflight steps passed; the full regression step failed, so the Windows package job was skipped. The failing addition was the duplicate durable-job restart regression in `tests/test_regressions.py`; its minimal bridge fixture lacked `_reconcile_interrupted_generation_project`. The existing dedicated `tests/test_stage5_generation_recovery.py` already verifies restart recovery, stale-job project ownership and saved narrator-only recovery. The duplicate was removed rather than adding a shallow fixture shim.
- **Build #3327:** [run 43159940335](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43159940335), exact head `4acba59fa8dcd0e52cba60bb28a401b8dc43f4c6`. Full suite passed **1,523 tests** and Windows package completed successfully. The original #3326 remains recorded as failed; #3327 is the validated correction.
- Artifacts: installer 846,171,638 bytes; portable 1,183,868,011 bytes; SHA manifest 3,047 bytes; multi-chapter M4B 8,997,510 bytes. Artifact IDs: `13919385123`, `13918936894`, `13919370271`, `13917718510`.
- Public release publication and optional Stage 7 real Piper benchmark upload were skipped by workflow conditions. No public release was published.
- Following #3327, additional test-only Qwen safety coverage was added for automatic one-pass VoiceDesign preview OOM recovery and explicit CUDA/ROCm/XPU fail-closed behaviour; those tests require the next exact-head CI run.


## Qwen OOM regression-test attempts — Builds #3328–#3331

This sequence adds coverage only; production runtime files have not been changed in these commits.

- **#3328** — commit `849944bb6fa55d827b4e4a12e1ac429e2fa37d87`, [run](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43165388158): 1,525 tests; three failures and three errors. The preview test incorrectly patched nonexistent module-level `clear_model_cache`; the explicit CUDA/ROCm/XPU cases supplied the literal characters `\\n` rather than a newline, so stdin contained invalid JSON records.
- **#3329** — commit `f7c0e989b701a7282fb093cc7f099f373b0b60cc`, [run](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43165511615): same inherited test code and same six failures; it did not contain the later correction.
- **#3330** — commit `10eeee38bda357596b879cf4d0d2b93e792513e3`, [run](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43165748149): preview OOM test errors removed; remaining three subtest failures isolated to the still-escaped newline in the explicit-backend test.
- **Correction:** commit `562cfcff9ad378924ffa661d18eaef46cbfcd953` replaces that final escaped literal with a real newline. It is test-harness-only. Exact-head Build #3331 and Qwen workflow #32 are the validations for this correction; status is pending at ledger update time.


## Explicit-backend VoiceDesign fixture correction — #3331 / #3332 / #3333

- **#3331** — [run 43166519551](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43166519551), commit `562cfcff9ad378924ffa661d18eaef46cbfcd953`: 1,525 tests; three failures remain in explicit CUDA/ROCm/XPU OOM subtests. The worker reached the identity-preparation phase, but the new fake model was a bare `SimpleNamespace` and did not implement `create_voice_clone_prompt`. The OOM injection therefore never ran.
- **#3332** — [run 43166598215](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43166598215), commit `1b9c0a05e4f0a8a79d7afd9960353668480c0c43`: same regression failure inherited from #3331; this head only added run-ledger documentation.
- **Correction:** commit `8b48dc7dfcdb3472fd405a0f1d8c56d6045f373a` introduces a minimal fake VoiceDesign model implementing `create_voice_clone_prompt`, allowing the test to reach the injected OOM during synthesis. It still asserts the selected GPU is preserved and the CPU loader is never called for explicit backend selections.
- **Validation outcome:** [Build #3333](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43166950641) passed all **1,525 tests** and the complete Windows package on commit `8b48dc7dfcdb3472fd405a0f1d8c56d6045f373a`. [Qwen workflow #33](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43166944780) passed 70 focused tests, expression-audio smoke and a real 30-second VoiceDesign CPU preview. The preview took 342.812 seconds warm; this confirms CPU speech generation but fails the under-60-second performance target. Japanese pronunciation diagnostic passed. The test sequence did not change production Qwen runtime code.


## Completed exact-head builds #3333 and #3334 — what changed and why

### Build Windows App #3333

- **Run:** [#3333](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43166950641)
- **Validated commit:** `8b48dc7dfcdb3472fd405a0f1d8c56d6045f373a`
- **What was pushed:** `tests/test_qwen_runtime_safety.py` gives the explicit CUDA/ROCm/XPU VoiceDesign OOM fixture the `create_voice_clone_prompt` method expected by the actual VoiceDesign identity-preparation route.
- **Why it was pushed:** #3331 reached production prompt preparation but failed before the simulated OOM because its fake model lacked this interface. The correction makes the test exercise synthesis OOM and prove explicit backends do not silently load CPU.
- **Validation:** 1,525 regression tests passed; frozen app, voice assets, real Piper multi-chapter M4B, packaged Sound Design/Music UI, HTML/core installer, installer startup, install/launch/upgrade/uninstall, logo transparency/hashes, package-size report and Defender scan passed.
- **Artifacts:** installer 846,218,501 bytes (`13921009972`); portable 1,183,868,009 bytes (`13921897190`); SHA manifest 3,047 bytes (`13921811779`); multi-chapter M4B 8,968,384 bytes (`13921395544`).
- **Stage 7 real bundled Piper benchmark:** `en_US-amy-medium`; synthesis 3.458s; audio 12.631s; RTF 0.274; verified backend CPU; provider `CPUExecutionProvider`; RSS 365,604,864 bytes; RAM available after synthesis 13,392,416,768 of 17,174,360,064 bytes. No GPU provider was used.
- Public release publication was skipped; this PR run did not publish a release.

### Build Windows App #3334

- **Run:** [#3334](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43167024722)
- **Validated commit:** `2a1925673c5c9cedaf7cf8bbbcedf10d68e7d0a5`
- **What was pushed:** `docs/dragon-studio/PUSH-LEDGER.md` records the confirmed #3331/#3332 failure cause and the #3333 correction.
- **Why it was pushed:** preserve a durable audit trail of the test failure, exact correction and passing evidence so later work does not repeat the same fixture investigation.
- **Validation:** again passed all 1,525 tests and complete Windows package acceptance.
- **Artifacts:** installer 845,868,645 bytes (`13921513254`); portable 1,183,868,011 bytes (`13922350730`); SHA manifest 3,045 bytes (`13921677653`); multi-chapter M4B 9,008,288 bytes (`13920338603`).
- **Stage 7 real bundled Piper benchmark:** `en_US-amy-medium`; synthesis 2.837s; audio 12.701s; RTF 0.223; verified backend CPU; provider `CPUExecutionProvider`; RSS 366,682,112 bytes; RAM available after synthesis 13,196,435,456 of 17,174,360,064 bytes. No GPU provider was used.
- Public release publication was skipped; this PR run did not publish a release.

### Qwen CPU workflow #33

- **Run:** [Stage 7 Qwen Real CPU Preview #33](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43166944780), commit `8b48dc7dfcdb3472fd405a0f1d8c56d6045f373a`.
- **What was pushed:** no additional Qwen production code; this workflow exercised the corrected accelerator-contract tests and actual CPU VoiceDesign runtime.
- **Why it ran:** verify that the same Qwen model can generate actual speech under CPU execution and capture expression/Japanese diagnostics.
- **Result:** 70 focused tests passed; real `Qwen3-TTS-12Hz-1.7B-VoiceDesign` produced 30.000s audio; warm preview 342.812s; warm/angry expression audio passed; Japanese pronunciation diagnostic passed. Artifact `Ryu-Stage7-Qwen-Real-CPU-Preview-33`, ID `13921256252`.
- **Open limitation:** 342.812s is far above the under-60-second target. This hosted CPU run proves functionality only; NVIDIA/ROCm/XPU hardware acceptance remains open.

## Build summary improvements

The Windows build workflow now adds a run-purpose section to the job summary, reading the exact head commit message and changed-file list. The measured Piper benchmark summary remains below it. On pull-request runs, the benchmark metrics remain visible in the job summary, while the raw Stage 7 JSON artifact upload stays disabled by the existing PR artifact policy; the raw JSON upload is reserved for eligible non-PR runs.


## Build Windows App #3335–#3339 — build-summary change and PR policy repair

| Run | Commit purpose | Why pushed | Result |
|---|---|---|---|
| [#3335](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43173516940) | Add the run-purpose/change-set section to the Windows job summary and attempt to upload raw Stage 7 Piper JSON whenever generated | User requested every build summary to show what changed and why the run was pushed; also sought persistent Piper benchmark evidence | Failed one existing regression assertion because PR runs must not upload raw Piper benchmark JSON |
| [#3336](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43173608205) | Update DS-QWEN and packaged acceptance status in the bug register | Record #3333/#3334 evidence and remaining hardware acceptance | Same single inherited assertion failure; only docs changed |
| [#3337](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43173777908) | Add explicit CUDA/ROCm/XPU OOM fail-closed coverage to the one-pass VoiceDesign preview route | Prove an explicitly selected accelerator reports failure instead of silently switching to CPU on preview OOM | Same single inherited PR-artifact-policy assertion failed; the Qwen-specific workflow #34 independently passed 71 tests and actual 30-second CPU VoiceDesign audio |
| [#3338](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43173968701) | Correct escaped GitHub Actions expression markers in the run-summary environment variables | Ensure token/repository/event/commit/PR fields are expanded by Actions, not passed as literal text | Same single inherited PR-artifact-policy assertion failed |
| [#3339](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43174166569) | Restore the original PR-only exclusion for Stage 7 raw JSON artifact upload | Preserve repository test/security policy while retaining Piper metrics in the PR job summary | **Success: 1,526 tests and Windows package passed** |

### Exact #3339 build summary benchmark

- Voice: `en_US-amy-medium`
- Synthesis: 2.635s
- Generated audio: 12.724s
- Real-time factor: 0.207
- Verified inference backend: CPU
- ONNX provider: `CPUExecutionProvider`
- Process RSS after synthesis: 365,465,600 bytes
- Available RAM after synthesis: 13,188,767,744 / 17,174,360,064 bytes
- This is a real bundled Piper local benchmark on a hosted Windows CPU. It must not be interpreted as Qwen speed or accelerator validation.

The PR build summary now contains both (1) commit/rationale/changed-file information and (2) the measured Piper benchmark summary. Raw Stage 7 JSON evidence upload remains skipped for pull requests by design.


## Dragon Studio responsiveness and Qwen acceptance — Builds #3358–#3365

All failed attempts below remain failed historical records. The later exact-head pass is a correction, not a rewrite of earlier run outcomes.

| Build / run | Commit topic and changed scope | Confirmed failure or result |
|---|---|---|
| [#3358](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43250109002) — `7dd0baadfed00efccef13da77f632c59b27008c0` | `[Stage 7][RESPONSIVENESS] Resolve known project actions without Library scans`; seven known-folder bridge actions now use the validated direct-project resolver/cache. | Failed: five Stage 8 retry/recovery test harnesses lacked `_load_library_project`. |
| [#3359](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43250645397) — `394513bb93177252e028f0c39c0c852e762eea2d` | `[Stage 7][RESPONSIVENESS] Update retry harness for direct project loading`; added the direct loader to the Stage 6 retry fixture and prohibited fallback to `list_projects()`. | Failed: 15 remaining fixture errors across PlayerBridge, Dashboard, Voice Preview and Stage 5 retry/recovery doubles, all missing the direct-loader method. Full suite ran 1,541 tests. |
| [#3360](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43252924362) — `be8cea78139269ec7f69a36226d39ea6527aa829` | `[Stage 7][RESPONSIVENESS] Align player and recovery test fixtures with direct loading`; added the direct loader to the remaining player/recovery harnesses. | Failed on one Dashboard playback test: its mocked saved-state map used a non-normalized Windows path key. |
| [#3361](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43253119507) — `84a078545db443193f36305ecf2719e19b470ed7` | `[Stage C][QWEN-ACCEPTANCE] Import timing module for saved-profile CPU preview`; added the 30-second saved-profile VoiceDesign measurement. | Failed on the remaining Dashboard path-key error and the missing `import time` acceptance contract. Provider #412 also failed at the actual saved-profile smoke with `NameError: time is not defined`. |
| [#3362](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43253656505) — `2a0f7efc6fab2c37651f9df600334c88029a9f3c` | `[Stage 7][RESPONSIVENESS] Normalize Dashboard playback test path keys`; corrected path normalization in the test fixture. | Failed on one remaining Qwen acceptance assertion: the CPU saved-profile smoke source did not yet import `time`. |
| [#3363](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43253969983) — `500d97a7f02a026ff22a78d59f15413dbcdc4757` | `[Stage C][QWEN-ACCEPTANCE] Import stopwatch for saved-profile CPU preview`; added the missing stopwatch import. | **Passed:** 1,541 regression tests and complete packaged Windows acceptance. Frozen app, bundled assets, Piper multi-chapter M4B, packaged Sound Design/Music acceptance, core/HTML installer, install/launch/upgrade/uninstall, transparent logo/hash, Defender scan and uploads passed. |
| [#3364](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43261564599) — `c20481d838769a6e3d5c1b5c5dbfe7c389c367a0` | `[CI][PULL-REQUEST-TOPIC] Show exact change topic before Windows tests`; PR run name now includes PR number/title and the tests job fetches the exact PR head commit subject/files into the summary before running tests. | Tests passed; the topic step logged the exact commit subject. Windows packaging was still running when this ledger snapshot was written. |
| [#3365](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43263516200) — `98f604fb1fa414fb01d50d8f4a6d7186e107f1b3` | `[Stage 7][RESPONSIVENESS] Keep native splash visible during renderer recovery`; both packaged-HTML and direct-file retry paths now show native loading before WebEngine reload, with a new regression contract. | Queued at ledger snapshot time; exact-head test and package result pending. |

### Exact #3363 packaged artifact evidence

- Installer `Ryu-Audiobook-Installer-3363`: 845,833,198 bytes; artifact ID `13961839015`.
- Portable `Ryu-Audiobook-Portable-3363`: 1,183,883,104 bytes; artifact ID `13963561567`.
- SHA-256 manifest `Ryu-Audiobook-Release-SHA256-3363`: 3,042 bytes; artifact ID `13962572291`.
- Real multi-chapter M4B `Ryu-Stage3-Real-Multichapter-M4B-3363`: 8,968,114 bytes; artifact ID `13962165036`.

### Provider Runtime Smoke #414 — CPU Qwen acceptance in progress

- Run: [Provider Runtime Smoke #414](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43253955703), commit `500d97a7f02a026ff22a78d59f15413dbcdc4757`.
- Passed: Qwen accelerator discovery/runtime installer tests, expression protocol smoke, real 1.7B VoiceDesign preview, and both 0.6B/1.7B CustomVoice synthesis + saved-profile reload + decoded-audio checks.
- CPU VoiceDesign one-pass preview generated 30.000s audio in 372.782s warmed time; cold-start plus warm-up was 59.650s; four segments; worker reused. Warm/angry expression audio and Japanese pronunciation diagnostics passed (Japanese synthesis 1.040s).
- CustomVoice 0.6B output: 7.600s / 364,844 bytes; 1.7B output: 6.400s / 307,244 bytes. Both reported the real CPU backend/device.
- Final Base Clone + saved VoiceDesign + character-to-M4B production job was still in progress at ledger time. Do not mark the hosted production path complete until its final job and uploaded artifact succeed.
- This is hosted **CPU** evidence. It does not satisfy the NVIDIA under-60-second target.

### Current hardware and visual acceptance boundary

- NVIDIA acceptance #22 and AMD/Intel acceptance #30 are still pending with zero jobs assigned. No physical CUDA, ROCm or XPU result exists in this evidence set.
- Hardware acceptance scripts exercise the saved VoiceProfile -> `provider_from_profile` -> identity-locked `design` route and reject CPU fallback; they are not the legacy one-pass `design-preview` benchmark.
- The 41-viewport CSS/DOM matrix and packaged checks from earlier checkpoints remain automated evidence only. Physical mixed-DPI/multi-monitor behaviour, shell icon appearance, installer layout at the user's display scaling, full-book target-PC generation/playback and forced-interruption recovery remain open.
- The PR remains open/draft; no public release was published by these PR runs.



## Build Windows App #3370 — exact-head A/B continuation result

- PR #35 synchronize run: [#3370 / 43347009057](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43347009057), exact head `f644d9af9d12fe0af03484a60173b3619c4d6811`.
- Trigger: the new Stage A/B commit was pushed to PR #35; the pull_request synchronize event automatically ran the branch's full Windows workflow. This was not a second unrelated app fix.
- Commit scope: Stage A master-register reconciliation, Stage B pause/resume ETA regression and checkpoint record, and the dedicated Stage B CI step. The packaged executable contained the cumulative application source already on PR #35.
- Tests: focused Stage B 16/16; focused Stage 6 48/48; full regression 1,544/1,544. All test job steps passed.
- Build: frozen executable, frozen verification, bundled voice assets and real two-chapter Piper M4B all passed. Artifact `Ryu-Stage3-Real-Multichapter-M4B-3370` (ID `14002562242`, 9,037,412 bytes) was uploaded.
- Failure: packaged Sound Design acceptance timed out at `stage6_task_manager_repairs_mismatched_view_action_in_place`; the remaining installer/release steps were skipped. Do not call #3370 a Windows package pass.
- Root cause: test assumed an active 1.5s backend poll but waited exactly 10s; the production scheduler intentionally backs off to 10s idle and 30s hidden-idle. #3368 failed the same assertion; #3369 passed with the same frontend/acceptance source, showing the timing-sensitive test was nondeterministic.
- Correction: explicitly request an immediate backend refresh using the existing Task Manager button after each deliberate View-action corruption; retain strict same-row identity and no-rebuild assertions. The normal adaptive polling values are preserved.
- A new exact-head Windows run is required to close the A/B package checkpoint.


## Build Windows App #3371 — Stage A/B exact-head package checkpoint passed

- Run: [#3371 / 43351171744](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43351171744).
- Exact head: `550cccc0508d0341889e7c88bfe44bea9ff93da1`; PR #35 head matched this SHA.
- Purpose: validate the Stage B pause/resume ETA regression and the deterministic Task Manager View-action repair on the complete cumulative PR application.
- Test job: focused Stage B **16/16**, focused Stage 6 **48/48**, full regression **1,544/1,544**; every step passed.
- Build job: frozen app, bundled assets, real two-chapter Piper M4B/FFmpeg decode, packaged Sound Design/Music Library, installer, hosted install/launch/upgrade/uninstall, logo/hash, package-size, Defender and all three Windows artifact uploads passed. Public release publication was skipped because this is a PR run.
- Task Manager: missing View action and mismatched View action were both repaired in place; original native row identity was retained.
- Artifacts:
  - Installer ID `14005930515`, 845,998,580 bytes.
  - Portable ID `14004749158`, 1,183,885,216 bytes.
  - SHA-256 manifest ID `14005436978`, 3,040 bytes.
  - Two-chapter M4B evidence ID `14005200121`, ZIP 8,992,198 bytes (M4B payload 504,269 bytes; FFmpeg chapter markers=2).
- Stage A/B hosted checkpoint is now closed at the exact SHA. Preserve the artifacts; do not clean earlier runs/artifacts as part of this status update.
- Remaining work stays open: Stage C Qwen model/profile identity and real selected-profile production; physical accelerator performance; Stage D full-book acceptance; Stage E remaining product/UI/data defects; Stage F target-PC/physical release acceptance. A green PR workflow is not a public release and does not replace device acceptance.

## Build #3372 — exact-head A/B reconfirmation

- Run: [#3372 / 43355282923](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43355282923), exact SHA `65adc53da81e8faeca09bc50cf4f21f663cc5138`.
- Focused Stage B **16/16**, focused Stage 6 **48/48**, full regression **1,544/1,544**; full hosted Windows package passed.
- Artifacts: installer `14007141961`; portable `14007426176`; SHA manifest `14007535608`; two-chapter M4B evidence `14006256981`.
- This SHA is the exact parent/baseline for the Stage C1 candidate; no A/B runtime code was changed by the C1 audit.

## Stage C1 candidate — Native Character Studio VoiceDesign identity parity

- Confirmed source defect: Native Character Studio's saved Qwen VoiceDesign sentence audition rewrote the profile to the one-pass `design-preview` mode. Production and the primary Voice Studio preview use the identity-locked VoiceDesign/Base path keyed by the saved `qwen_profile_id`; the one-pass route can produce a different timbre and did not require the Base model used for long-form identity lock.
- Candidate correction: resolve preferred VoiceDesign and Base model kinds from the same global Qwen preference used by `provider_from_profile`; in Auto mode use the shared runtime selection helpers. Require both models to be installed and pass the unchanged saved profile to `VoicePreviewWorker`.
- Focused C1 tests are added for explicit 0.6B and 1.7B Base preferences, Auto fallback, Base readiness and preventing any `design-preview` substitution.
- The web Voice Studio edit handler was checked: prompt/language/seed changes detach the saved profile before a draft save. No change is justified there.
- Candidate commit is tagged `[artifact-checkpoint]` so the Dragon Studio push workflow runs focused C1 tests, the full regression suite and the exact-head Windows package before PR promotion. C1 is not complete until all gates pass.

## Stage C1 candidate run #3373 — focused step did not launch

- Run [#3373 / 43363581227](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43363581227), candidate SHA `188998bc55377d6e9e27d1ebae2b6349040647bd`.
- Setup, JavaScript validation, native Qt lifecycle (1/1), Stage B (16/16) and Stage 6 (48/48) passed.
- New Stage C1 workflow step failed before executing unittest because `$pythonExe` was defined in an earlier Actions step and was not available in the new step's PowerShell process. No C1 test, full regression or package result is claimed.
- Fixed by resolving and validating `python.exe` within the C1 step itself. No app source changes are being made for this workflow failure. Re-run the exact candidate before promoting the PR.

## Stage C1 follow-on — route scoped Voice Cast identities into production

- Confirmed production's effective cast resolver read state.characters and legacy name-only voice_cast but ignored voice_cast_identity_assignments and voice_cast_character_roster, despite Voice Cast saving those series-scoped records. Same-named characters in separate series could therefore lose their chosen profile in production. Explicit empty choices could be overwritten by stale legacy name mappings.
- Candidate source fix imports the saved roster, resolves normalized (series, character) keys, preserves explicit empty/unassigned values, and prevents legacy name-only mappings from overriding scoped entries. Ambiguous or stale references remain errors; no narrator fallback is introduced.
- Added regressions for independent same-name profiles routed through CastAwareProvider and explicit unassignment overriding a stale legacy mapping.
- Focused, full regression and exact-head Windows package validation are pending for this follow-on commit.


## Stage C1 — Voice Studio assignment entry-point follow-on

- #3376 on exact SHA 54ff7e2da9d2d78ddbe27540f5f430ca0cbd2336 passed run 43372658193: focused C1 7/7, Stage B 16/16, Stage 6 48/48, full regression 1,548/1,548 and hosted Windows packaging. Artifact IDs: installer 14014730865; portable 14013769936; SHA manifest 14014641192; M4B 14013926395; Piper benchmark 14014158132.
- Confirmed issue: Voice Studio Assign to Character offered only names, collapsing same-named series identities and updating only legacy voice_cast. The authoritative scoped identity map could therefore remain stale.
- Candidate fix disambiguates choices by series, persists through the canonical Voice Cast scoped writer, and provides a scoped-map fallback if Voice Cast is unavailable. Production scoped matching now includes aliases.
- Focused regressions exercise both assignment persistence paths, duplicate-name selection, and alias-keyed assignment precedence. Full regression and exact-head package validation are pending.

## Stage C1 candidate run #3377 — fixture import error

- Run 43382873285 / #3377 failed in the focused Stage C1 module on SHA 6424cc83ef0222603cabf39316c4941ac06dda6d.
- Stage B 16/16 and Stage 6 48/48 passed; JS syntax and Qt lifecycle passed.
- Two newly added assignment-flow tests raised NameError because tempfile was not imported. The same-name option builder test passed; failure occurred before the mocked assignment flows ran.
- Fixed with the missing tempfile import; no application logic changed and no test was removed. Next exact-head run includes the full package marker.

## Build #3378 — one stale Voice Library assignment contract

- Run [#3378 / 43383155116](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43383155116) on SHA `2e9d1e746efbc409352e7e96ba2c8c295b83120d`: focused C1 **10/10**, Stage B **16/16**, Stage 6 **48/48**; full suite executed **1,552 tests**, one failure.
- Sole failure was a legacy static test expecting the removed name-only Character Library sync implementation. The new Voice Studio assignment tests and scoped resolver tests passed.
- Corrected the flow to persist Voice Cast's full scoped state with `_save_cast(update_voice=False)` (no bulk voice overwrite), then sync exactly the selected `(series, character)` row with `update_voice=True`. The no-CastPage path uses the same one-row operation. Contract and dynamic tests now assert that only the selected Library voice is updated.
- #3378 package was skipped after the suite failure; next candidate must pass full regression and exact-head package.