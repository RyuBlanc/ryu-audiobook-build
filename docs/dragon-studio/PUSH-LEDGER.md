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
