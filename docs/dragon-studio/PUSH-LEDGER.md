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

## Corrective push — pending
Expected scope:
- `tests/test_qwen_runtime_safety.py`: replace finite fake clock with incrementing monotonic clock; make both new tests close provider in finally.
- `app/tts/providers/qwen_character.py`: close worker stderr handle after diagnostic tail capture on timeout/early exit.
- `.github/workflows/qwen-cpu-contract-acceptance.yml`: explicit always-run PowerShell copy into artifact directory; upload that directory only.
- `docs/dragon-studio/POST-1.2.0-BUG-REGISTER.md`: record confirmed root cause and fix.
- This file: update with exact correction SHA and run IDs after push.

Status before commit: prepared, not pushed; tests/package pending. Run focused Qwen diagnostic tests first, then full regression and exact-head Windows package. Inspect the CPU real-preview artifact separately for worker stderr.
