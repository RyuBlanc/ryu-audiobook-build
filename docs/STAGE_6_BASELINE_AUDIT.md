# Stage 6 — Step 1 Baseline Audit and Requirement Gap Report

**Project:** Ryu's Audiobook — Dragon Studio Edition  
**Release target:** Version 1.2.0  
**Audit date:** 4 November 2026  
**Scope:** Audiobooks, Playback, History, Background Jobs / Task Manager  
**Repository:** https://github.com/RyuBlanc/ryu-audiobook-build

## 1. Executive decision

Stage 6 can proceed from the accepted Stage 5.5 source baseline. Do not restart the Audiobooks player or M4B integration and do not replace Premium V2 with the legacy native UI.

The latest full Windows package and real packaged M4B playback acceptance passed in Build #2253. The later Build #2254 is a documentation-only closeout commit with a passing 1,141-test regression run; it did not run the Windows packaging job. The Stage 6 branch is therefore based on the latest Stage 5.5 branch head (#2254), whose application code is unchanged from the tested #2253 application source.

The baseline audit identified real remaining Stage 6 scope:
- Premium V2's Audiobooks page is a single selected-player view, not the required compact, multi-audiobook card library.
- History has status filtering and durable terminal records, but no From Date / To Date controls, and it does not combine live queued/running jobs with terminal history in the view.
- The Task Manager's live job row markup does not match the CSS grid structure used by the `.job-row` class; required job details are also omitted from the rendered row.
- View/details is not a genuine Task Manager operation. Retry/Recover and generation controls are present and were tested in Stage 5.4.
- Full-player controls, mini-player navigation synchronization and playback-position restoration have implementation foundations, but the full Stage 6 control-by-control and restart acceptance remains outstanding.
- The full requested responsive matrix has not yet been evidenced.

No application code was changed during Step 1.

## 2. Repository and branch baseline

| Item | Audited value |
|---|---|
| Repository default branch | `main` |
| `main` HEAD at audit | `356b536499be8d3679d96496f24f3836864cb47e` |
| Current Stage 5.5 working branch | `stage-5/step-5-m4b-library-integration` |
| Latest Stage 5.5 branch HEAD | `08fbcf763bfbbb8c65841e39703ca978e2d64176` |
| Latest full Windows package source | `5315a75b1b0324796d884bdbc49a7a5eb0116a28` |
| Stage 6 audit branch | `stage-6/baseline-audit` |
| Stage 6 audit branch base | `08fbcf763bfbbb8c65841e39703ca978e2d64176` |

The comparison from Stage 5.4 `stage-5/step-4-generation-engine` to Stage 5.5 `stage-5/step-5-m4b-library-integration` is a direct continuation: Stage 5.5 is 17 commits ahead and 0 behind Stage 5.4. Stage 5.5 changes include the M4B assembler, browser-compatible playback source, Premium V2 host integration, playback tests and packaging/acceptance records.

The comparison between `main` and the Stage 5.5 branch reports a divergent history (Stage 5.5 is 1,819 commits ahead and 30 commits behind `main`). Do not merge `main` into the Stage 6 branch or retarget Stage 6 to `main` as a shortcut. Preserve the verified stage branch lineage and review any proposed integration separately.

The Stage 6 branch was created from the current Stage 5.5 branch HEAD. No Stage 6 branch existed before this audit.

## 3. Latest GitHub Actions reconciliation

### 3.1 Relevant latest runs

| Build | Run | Commit | Result | Audit interpretation |
|---|---|---|---|---|
| #2254 | https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41776104283 | `08fbcf763bfbbb8c65841e39703ca978e2d64176` | Tests passed; Windows build job skipped | Latest workflow run. 1,141 tests passed in 53.814s. Not a new installer/portable checkpoint. |
| #2253 | https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41770098774 | `5315a75b1b0324796d884bdbc49a7a5eb0116a28` | Full Windows package and packaged acceptance passed | Latest successful Windows artifact-producing build and Stage 5.5 runtime checkpoint. |
| #2252 | https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41769708812 | `5d620525e986` | Tests passed; Windows build skipped | Regression-only playback-compatibility checkpoint. |
| #2251 | https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41764283352 | `759f682a3bcb` | Failed | Packaged Audiobooks playback timed out because the AAC M4B was sent directly to the packaged Chromium/Qt WebEngine player. Corrected by the browser-compatible playback derivative. |

Build #2254 changes only:
- `docs/STAGE_5_5_M4B_LIBRARY_STATUS.md`
- `docs/stage-5/STAGE_5_EXECUTION_LEDGER.md`

No application source changed between #2253 and #2254. The #2254 regression job ran 1,141 tests and ended `OK`; its packaging job was skipped. For Stage 6, the exact tested software baseline remains #2253, with the later #2254 closeout documentation retained.

### 3.2 Build #2253 runtime and artifact evidence

Build #2253 successfully executed the frozen Premium V2 Windows application. The packaged acceptance log reports PASS for:
- Real full multi-chapter generation using the project's saved narrator.
- Empty and excluded chapter handling and saved chapter order.
- Job / History identity and output ownership.
- Embedded M4B chapter markers with actual titles and ordered timing.
- Browser-compatible playback source derived from the authoritative AAC M4B.
- Real Audiobooks playback, chapter navigation to the embedded second chapter marker and saved playback position.
- Stage 5.4 Background Jobs Pause / Resume / Cancel / Retry / Recover and process-restart recovery.
- Production chapter-preview playback, measured preview durations and Save As flow.
- Application restart persistence for project metadata, saved narrator selection and relevant sound settings.

Build #2253 uploaded three non-expired artifacts (expiry: 4 December 2026):
- Installer: [Ryu-Audiobook-Installer-2253](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41770098774/artifacts/13295407817), 884,314,151 bytes. Uploaded ZIP SHA-256: `f07889555938fadab7a6078c42127c6d7f7e0e81b823d6ab941523ef0a9cf099`.
- Portable application: [Ryu-Audiobook-Portable-2253](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41770098774/artifacts/13295113479), 1,367,975,026 bytes. Uploaded ZIP SHA-256: `fa6934374005fe37beac718afdb01d0ad114123845ee9c42a7063548a9e57f5b`.
- SHA-256 manifest: [Ryu-Audiobook-Release-SHA256-2253](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41770098774/artifacts/13295567412), 777 bytes. Uploaded ZIP SHA-256: `8b65eed768b325c4d908655af96f9354b0304e68e7f7c1ec5918d8817a7c6ec2`.

These uploaded ZIP hashes identify the GitHub artifact archives. The manifest contains the inner release-file hashes. The Defender scan, installer upload, portable upload and manifest upload passed; publishing the verified installer as a public release was skipped by design. User-device perceptual listening is not claimed by CI.

### 3.3 Failed candidate and cancellation reconciliation

- #2247–#2248: M4B mux/tagging candidates exposed loss of narrator/custom metadata and cover-stream metadata/validation assumptions. The final implementation writes/validates final-book metadata without damaging the embedded cover/audio.
- #2249: regression test failed with `NameError: name 're' is not defined` in `tests/test_stage743_output_validation.py`; the import was added and #2250 passed.
- #2251: packaged playback timed out because the AAC M4B source was not playable by the packaged WebEngine HTML Audio path.
- #2252: regression-only validation of the cached browser-compatible MP3 derivative passed.
- #2253: exact-head frozen Windows acceptance proved the real playback path, chapter seek and position persistence, then completed package/artifact creation.

Stage 5.4 candidate failures #2226–#2234 are reconciled in `docs/STAGE_5_4_GENERATION_ENGINE_STATUS.md` and were superseded by the accepted Stage 5.4 checkpoint #2235. Stage 5.5 #2253 re-ran the relevant Stage 5.4 packaged acceptance markers.

The Stage 5.4 closeout records #2215–#2218 as automatically superseded during rapid early branch updates while older concurrency settings were active; none was manually cancelled. The current `.github/workflows/build-windows.yml` uses a run-specific concurrency group and `cancel-in-progress: false`. No active Stage 5.5 run was observed during this audit. Actions Storage Cleanup runs such as #1141 are skipped by their workflow conditions; they are not failed Windows builds.

## 4. Stage 5.4 / Stage 5.5 carry-forward status

| Carry-forward requirement | Status | Evidence and Stage 6 rule |
|---|---|---|
| GEN-01 — full generation uses the saved project configuration / narrator | VERIFIED COMPLETE | Stage 5.4 closeout #2235 and Stage 5.5 packaged generation acceptance #2253. Preserve; regression only. |
| GEN-02 — compatible checkpoint reuse, valid audio chunks and stable chapter identity | VERIFIED COMPLETE | `tests/test_stage5_checkpoint_compatibility.py`, `tests/test_stage5_checkpoint_payload_integrity.py`; packaged generation acceptance #2253. Preserve stable IDs and checkpoint signatures. |
| GEN-03 — real pause / resume / cancel / retry / recovery | VERIFIED COMPLETE | `tests/test_stage5_generation_control_bridge.py`, `tests/test_stage5_generation_recovery.py`; Stage 5.4 packaged acceptance repeated in #2253. Preserve. |
| PROD-14 — consistent project/job identity and status across Production, readiness, Background Jobs, History and output | VERIFIED COMPLETE | `tests/test_stage5_terminal_job_consistency.py`, `tests/test_stage5_live_generation_job_integration.py`; packaged ownership acceptance #2253. Preserve. |
| PROD-15 — chapter-specific preview audio and download | AUTOMATED TESTS PASSED | Stage 5 production-preview parity tests and #2253 real chapter-only preview / playback / Save As acceptance. Do not recreate. Reopen only if Stage 6 regressions or ownership tests fail. |
| Chapter identity | VERIFIED COMPLETE | Stable chapter ID and checkpoint tests; actual saved chapter order and M4B embedded chapters accepted in #2253. |
| Saved narrator/profile persistence | VERIFIED COMPLETE | Saved narrator used in full-generation package acceptance #2253; metadata/profile restart acceptance also passed. |
| Project/job/output ownership | VERIFIED COMPLETE | Same originating project/job/History/output identity accepted in Stage 5.4 and repeated in #2253. |
| M4B output and browser-compatible Audiobooks playback | VERIFIED COMPLETE | #2253 actual M4B, chapter metadata, playback derivative, real playback/chapter seek/position acceptance. Keep original M4B authoritative; MP3 is a playback derivative only. |

## 5. Stage 6 requirement traceability

Statuses use the definitions in the master register. “RUNTIME ACCEPTANCE PENDING” means source/partial automated coverage exists but the full required installed-app behaviour is not yet evidenced.

### 5.1 Audiobooks and playback

| Requirement | Status | Existing implementation / evidence | Remaining Stage 6 gap |
|---|---|---|---|
| AB-01 — compact multiple-audiobook cards | VERIFIED COMPLETE | Premium V2 renders bounded responsive cards from backend project summaries, requiring a completed project and non-empty real output path. Cover/title/status are bound to the owning project; Open and Play are separate actions. `tests/test_stage6_audiobook_library.py`; Build #2274 passed 1,146 tests, syntax, Qt lifecycle, frozen EXE and all four packaged Audiobooks markers. | Step 2 completed on exact source SHA `c60354c995d9adce886984fc37a9be3c13ee04a4`; installer, portable package and SHA-256 manifest uploaded; Defender scan passed. Preserve Premium V2 as the default. |
| AB-02 — actual audio-file loading | VERIFIED COMPLETE | `app/audio/playback.py` validates M4B/MP4 source and produces a decoded, duration-checked browser-compatible derivative. `PremiumV2Bridge._player_get_active` validates the saved output and source/cache identity. `tests/test_audiobook_playback.py`; Stage 5.5 runtime markers #2253. | Preserve. Reopen only if the integrated Stage 6 tests reveal a regression or another supported source format fails. |
| AB-03 — full player controls | IN PROGRESS | Premium V2 adapter owns a real Audio session and binds play/pause, seek, time, volume, playback rate and ±15-second seek controls. #2253 proves real playback, chapter seek and position save. | Run a control-by-control installed-app acceptance for every control, including bounds, displayed time and actual audio effect. |
| AB-04 — actual chapter playback and synchronization | IN PROGRESS | Actual chapters are read from embedded M4B chapter metadata and rendered into the player. Previous/next chapter seek is implemented; #2253 passed the real embedded-chapter seek marker. | Explicitly verify clicking a chapter starts at its real timestamp, selected chapter follows the playhead during continuous playback, order/title are correct and switching audiobooks cannot leave stale chapter rows. |
| AB-05 — persistent mini-player | RUNTIME ACCEPTANCE PENDING | Premium V2 has a persistent mini-player component; the adapter keeps the same Audio object/session across page navigation, synchronizes play/pause and progress, and supports manual dismissal. | Verify navigation in both directions, pause/resume from both surfaces, correct title/cover/position, dismissal/return behaviour and no duplicate audio. Mini-player currently exposes fewer controls than the full player. |
| AB-06 — playback-position persistence | RUNTIME ACCEPTANCE PENDING | `player.position.save` stores position in the owning project's state; the adapter periodically saves and restores it when the selected audiobook loads. #2253 proved position persistence during packaged playback. | Verify close/reopen and process restart, correct audiobook/chapter restoration, no cross-project position leak, and full/mini player synchronization. |
| AB-07 — completed output integrity | VERIFIED COMPLETE | Generation attaches output only after validation and preparation of playback source. Player resolves the owning project output; #2253 verifies actual M4B chapter markers, saved narrator, playback and output ownership. | Preserve metadata/cover/chapter-to-output association and reject missing/invalid output. Add regression only if a failure is found. |

### 5.2 History

| Requirement | Status | Existing implementation / evidence | Remaining Stage 6 gap |
|---|---|---|---|
| HIS-01 — accurate operation history | OPEN | Backend writes terminal job snapshots to `premium_v2_history.json`; Premium V2 History renders operation title, project, stage/message, status, progress and elapsed time where available. | `history.list` returns the terminal journal, not live queued/running operations. The History page's Running filter therefore cannot show live jobs from that endpoint. Include live active jobs without duplicating terminal records; show chapter/phase, result/error summary and valid actions. The current View action only opens Background Jobs and displays a toast, not a full operation detail view. |
| HIS-02 — From Date / To Date filtering | OPEN | History currently has status filters (All / Completed / Running / Failed). No From Date or To Date controls or date-range predicate were found in the Premium V2 History UI or `history.list` backend path. | Add real date controls and filtering using operation timestamps; combine range with status and search; test inclusive boundaries and filter changes. |
| HIS-03 — durable terminal history | VERIFIED COMPLETE | `PremiumV2Bridge._record_history_job` stores terminal snapshots keyed by job_id in a separate durable history file. JSON persistence uses a unique temp file, flush/fsync and replace. Queue cleanup preserves history. `tests/test_stage5_terminal_job_consistency.py`, `tests/test_stage5_generation_recovery.py`; package acceptance #2253. | Preserve. Do not rebuild the journal; extend only if new operation types need durable terminal records. |

### 5.3 Background Jobs / Task Manager

| Requirement | Status | Existing implementation / evidence | Remaining Stage 6 gap |
|---|---|---|---|
| JOB-01 — readable job list and layout | OPEN | Premium V2 has a jobs modal and responsive CSS. The live renderer emits `.job-row` with a flat sequence of children, while the shared CSS grid for `.job-row` expects an icon / main-content / actions three-column structure. The live markup omits that structure, so the title and metadata can land in the wrong grid columns. | Correct the live row structure or give it a dedicated grid class; verify titles, project, progress, errors and actions do not collide or clip. |
| JOB-02 — complete job details | OPEN | Backend job records contain job type/title, project, state, progress, stage/message, timestamps, elapsed, result, error, output path and recoverability. The live row currently renders title, stage, progress, state, message/error and some actions. | Display associated project and elapsed/result information where available; make a real details view available for completed, running, failed and recoverable jobs. |
| JOB-03 — accurate totals and filters | RUNTIME ACCEPTANCE PENDING | Adapter reads `job.list`, derives Running / Queued / Completed counts and implements Active / Completed / All plus a Failed / Cancelled filter. Stage 5.4 packaged UI tests exercise job filters and controls. | Add explicit matching-head acceptance for counter values, each filter's exact records, empty states and synchronization after state transitions / queue cleanup. |
| JOB-04 — View / Cancel / Retry / Recover | OPEN | Real Cancel and generation Pause / Resume / Retry / Recover bridge actions exist. Stage 5.4 packaged acceptance #2253 verifies real pause/resume/cancel, retry ownership and restart recovery. | Add a real View/details operation in Task Manager. Current generation row actions do not include View; the History View shortcut opens the modal and reports a toast rather than showing full details. Retain state-valid Cancel / Retry / Recover behaviour. |
| JOB-05 — History / Background Jobs consistency | VERIFIED COMPLETE | Job updates and terminal snapshots share job_id; terminal journal is independent from queue visibility. `tests/test_stage5_terminal_job_consistency.py`, `tests/test_stage5_live_generation_job_integration.py`, restart-recovery tests; packaged ownership acceptance #2253. | Preserve; do not create duplicate History records or couple History retention to queue cleanup. |

## 6. Responsive UI baseline

Premium V2 contains general layout breakpoints (notably 1,250px and 800px) and mobile mini-player positioning. This is implementation evidence, not proof of the user's requested display acceptance.

No matching Stage 6 runtime matrix was found for:
- Original resolutions: 1920×1080, 1366×768, 1280×720.
- 4:3, 5:4, 16:10, 16:9, 21:9, 32:9, 3:2 and portrait resolutions in the Stage 6 plan.
- Minimized, maximized, restored, half-screen and quarter-screen windows.
- Ultrawide, extended display, mixed-resolution monitor and portrait-display scenarios.
- 100%, 125%, 150% and 200% Windows display scaling.

Do not mark responsiveness verified from CSS breakpoints or screenshots alone. Stage 8 must record viewport emulation separately from physical-display/installed-Windows verification.

## 7. Regression tests to preserve and extend

Existing relevant tests:
- Audiobook source conversion / cache / validation: `tests/test_audiobook_playback.py`.
- Terminal job and History identity: `tests/test_stage5_terminal_job_consistency.py`.
- Restart recovery and stale callback/owner guards: `tests/test_stage5_generation_recovery.py`.
- Background Jobs state/action UI contract and packaged acceptance: `tests/test_stage5_generation_job_ui_states.py`.
- Real GenerationManager + job/history/output ownership: `tests/test_stage5_live_generation_job_integration.py`.
- Pause/resume/cancel bridge: `tests/test_stage5_generation_control_bridge.py`.
- Stable chapter identity / saved narrator checkpoint compatibility: `tests/test_stage5_checkpoint_compatibility.py`.
- WAV checkpoint payload integrity: `tests/test_stage5_checkpoint_payload_integrity.py`.
- Production preview parity: `tests/test_stage5_production_preview_parity.py`.
- Existing Stage 6 preflight test: `tests/test_stage6_generation_preflight.py`; this covers empty/missing chapter generation preflight, not the new Audiobooks, History or Task Manager requirements.

New Stage 6 regression coverage is required for compact audiobook cards and output association; every full-player control; chapter/playhead synchronization; mini-player navigation; playback restoration after process restart; HIS-01 active/terminal reconciliation; HIS-02 date/status/search combinations; JOB-01 live-row layout; JOB-02 details; JOB-03 totals/filters; JOB-04 View and state-valid operations; and JOB-05 duplicate-free cross-module records.

## 8. Open pull requests and integration dependencies

The repository currently has these open PRs:
- #26 — recoverable Library deletion / live Character Library.
- #15 — speaker overlays, incomplete imports, hardware verification and model management.
- #18 — Stage 3 Voice Studio / character assignment.
- #19 — Stage 4 pronunciation / sound design / assembly.
- #20 — installer branding / accessibility.
- #4 — Qwen preset selection and draft workflow.

These PRs are on older or divergent branch lineages; the Stage 5.5 branch is not the same as the current `main` tip. Do not merge any of these into Stage 6 simply because they remain open. First compare the specific changed files and determine whether the relevant work is already present in the Stage 5.5 source. Stage 6 should preserve the Premium V2 default and the current Stage 5.5/5.4 accepted integrations.

## 9. Exact Stage 6 implementation scope

1. **Step 2 — Audiobooks Library / output integrity:** **COMPLETE** on Build #2274. AB-01 compact multi-book cards / Open / Play / switching passed packaged acceptance; AB-02 and AB-07 remain verified carry-forward requirements.
2. **Step 3 — Full player / chapter playback:** extend and verify AB-03/AB-04 control-by-control; do not rewrite the M4B source/derivative integration.
3. **Step 4 — Mini-player / persistence:** complete installed-app and restart acceptance for AB-05/AB-06; fix only gaps demonstrated by tests.
4. **Step 5 — History:** implement HIS-01 active/terminal reconciliation and full operation details, then HIS-02 date filtering. Preserve HIS-03 durable journal.
5. **Step 6 — Background Jobs:** correct JOB-01 live layout, complete JOB-02 details, prove JOB-03 counters/filters, add real JOB-04 View/details while retaining proven generation actions, preserve JOB-05.
6. **Step 7 — Integration:** rerun Stage 5.4/5.5 ownership, narrator, chapter identity, preview and M4B playback as regression-only carry-forward.
7. **Step 8 — Responsive acceptance:** complete the full resolution / window / scaling matrix from the Stage 6 plan.
8. **Step 9 — final acceptance:** exact-head regression, actual installed Windows acceptance and candidate-matched installer/portable/SHA-256 artifacts.

## 10. Step 1 completion checklist

- [x] Current Stage 5.5 branch and HEAD SHA identified.
- [x] Latest workflow, latest full Windows build, package outcome and exact source commits reconciled.
- [x] Failed Stage 5.5 candidates and the later fixes compared.
- [x] Stage 5.4/5.5 accepted carry-forward evidence reconciled.
- [x] Open PRs and branch divergence reviewed.
- [x] AB / HIS / JOB requirements mapped to existing code, tests and runtime evidence.
- [x] Concrete UI and functional gaps documented.
- [x] Existing passing functionality marked for preservation.
- [x] Existing regression tests and Stage 6 coverage gaps identified.
- [x] Exact Step 2–9 scope established without rebuilding completed work.

**Step 1 decision: COMPLETE.**  
**Deliverable:** Stage 6 baseline and requirement-gap report.  
**Step 2 decision: COMPLETE.** Build #2274 passed the full exact-head packaged checkpoint and uploaded installer, portable and SHA-256 artifacts. **Next action: Stage 6 Step 3 — Full player controls and chapter playback/synchronization (AB-03 / AB-04).** AB-02 / AB-07 remain closed unless new evidence shows regression.


### Step 2 exact-head closeout — Build #2274

Packaged run: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41806424525  
Accepted source SHA: `c60354c995d9adce886984fc37a9be3c13ee04a4`.

All four packaged Audiobooks markers passed: compact multiple real-output cards; Open loads the selected book paused; Play starts its real decoded audio; switching books preserves project/output identity. The 1,146-test regression suite, frontend syntax, isolated Qt lifecycle, frozen EXE and bundled Piper/Kokoro/starter audio checks also passed. The combined Sound Design / Production Preview / Stage 5.4 generation-control / Stage 5.5 M4B playback and restart-recovery acceptance passed. Installer, portable package and SHA-256 manifest uploaded after functional HTML installer, logo/hash and Microsoft Defender checks.

Step 2 is **COMPLETE**. Step 3 is the next scoped task: AB-03 full-player controls and AB-04 actual chapter playback/playhead synchronization. Do not rewrite the Stage 5.5 M4B assembler or browser playback derivative.


## Step 3 official kickoff — 4 November 2026

Step 3 is now IN PROGRESS on `stage-6/baseline-audit`, beginning from kickoff commit/source HEAD `d409780802b2f39913f4971348534647ecd6edd5`. The detailed baseline, concrete player-handler/chapter-playhead gaps, test-first verification matrix and exit gate are recorded in `docs/STAGE_6_STEP_3_STATUS.md`. The implementation fixes and expands acceptance for full-player Play/Pause, one authoritative timeline binding, embedded chapter intervals, playhead synchronization, keyboard/click chapter playback and stale-event protection. AB-02 and AB-07 remain protected carry-forward requirements.


## Stage 6 Step 4 — automated restart acceptance added (5 November 2026)

The packaged Windows acceptance script now verifies playback-position persistence
across two separate launches of the frozen executable. The first process opens
and plays an actual completed audiobook, pauses at a known media timestamp, and
waits for the native project-state value to confirm the save. The second process
reopens the same project and checks that the actual decoded audio seeks to the
saved timestamp, with the same saved player volume/rate.

The same acceptance navigates between Audiobooks and Dashboard, verifies that
the mini-player controls the same audio object, and checks that manually closing
the mini-player hides only the dock without stopping or replacing playback.

The checks execute in the CI-packaged Windows application. The user's physical
manual installation check remains excluded and is not claimed as performed.
Matching-head CI verification is pending.


## Failed-run audit and corrected acceptance — 5 November 2026

### #2329 — failed, source test gate
Commit \`c019ec153df8e4955e79333b2ff8884de3cd09d9\`.
The full suite reported three compatibility assertions: the terminal History
test prohibited queue snapshots; the History DOM marker expected the exact
old marker syntax; and the Task Manager row signature expected the prior
field order. These were test-contract failures, not package/runtime failures.

### #2330 — failed, source test gate
Commit \`dfe0d29beceab94773b55b0a19dee64d5e21f5bc\`.
It reproduced the same three source-contract failures (1,169 tests ran). The
Windows build was skipped because the source-test job failed; this run did not
execute the Stage 4 packaged restart acceptance.

### #2331 — failed, packaged acceptance gate
Commit \`ae082ad10794eceaae6015b676716df5713d1674\`.
The full source gate passed (1,169 tests). The Windows executable built and
bundled-asset checks passed. The frozen app reached the second process launch,
restored project metadata and playback position, then failed at a new acceptance
assertion comparing audio volume/rate against values inherited from earlier
acceptance steps. The app already reads these preferences from Settings and
applies them during \`openPlayer\`; the test had not first established known
values for its selected audiobook.

### Corrective acceptance
The packaged test now sets 1.25× speed and 42% volume through the actual
Audiobooks controls, waits for native Settings and player read-back, and checks
those exact values after a separate frozen-app launch. The restart phase also
checks real History search, Completed status, inclusive date filtering, job
details, Task Manager All/Active/Completed views, job identity sets, summary
counts, responsive row structure and operation details. These additions do
not change playback implementation or weaken Stage 5.4/5.5 gates. Matching-head
CI is required before these checks are considered passed.


## Stage 6 Step 8 — packaged viewport emulation added (5 November 2026)

The frozen-app acceptance now clones the live Premium V2 DOM and the actual
application stylesheet into an isolated Chromium iframe and emulates all 41
requested resolutions across 4:3, 5:4, 16:10, 16:9, 21:9, 32:9, 3:2 and
portrait modes. At each viewport it checks the player, History, mini-player,
Audiobooks cards, Task Manager rows and job-details dialog for bounds and the
expected responsive grid breakpoints.

It also emulates restored, half-screen, quarter-screen, maximized, ultrawide
and portrait viewport sizes and effective CSS viewport dimensions corresponding
to 100%, 125%, 150% and 200% scaling. These results are browser viewport
emulation in the packaged Windows application; they do not claim physical
minimize/restore behaviour, mixed/extended monitor topology or OS-level DPI
verification. Those require an actual Windows display session.


## Step 8 responsive defect correction — 5 November 2026

The first 41-viewport matrix exposed a fixed-width three-column player layout that could exceed the usable workspace at 1280×720 and 1366×768. The stylesheet now uses fluid 220/320/220px minimum columns between 1251px and 1450px viewport widths. The existing one-column rule at 1250px and below and the wide-desktop 330/400/330px layout remain unchanged. A source regression contract locks this correction; matching-head packaged viewport acceptance is still required.


## Step 4 runtime defect correction — 5 November 2026

Build #2332's frozen-app acceptance confirmed the preference store was correct
after restart (volume 0.42 and rate 1.25), and the restored media volume was
0.42, but the actual newly loaded Audio element reported playbackRate 1.0.
This was a genuine Qt WebEngine media-load restore defect, not a stale stored
preference. The adapter now reapplies the current selected player rate and
volume in both \`loadedmetadata\` and \`play\` handlers after the browser has
loaded the resource. A regression test checks both event handlers, while the
packaged acceptance continues to require the actual rate to be 1.25.


## Matching-head audit update — 5 November 2026

- #2332 and #2333 passed source tests and built/verified the frozen executable,
  then both failed at restart restoration because Qt WebEngine media metadata
  load reset the media element's playback speed to 1.0× although Settings and
  the player response correctly stored 1.25×. #2337 corrected this in
  \`audio.onloadedmetadata\`, applying the persisted rate and volume after media
  metadata becomes available. Its later restart acceptance passed position,
  mini-player and Stage 5.4 recovery checks.
- #2337 then exposed a Step 7 packaged-test issue: the test kept a reference to
  the Audiobooks card from before Open. The Open handler correctly refreshes
  the library after selecting a book, detaching the old card. The test now
  reacquires the card by the recovered project folder, confirms the live Play
  control is connected and still targets the same project, then clicks it.
- #2338 passed the complete source regression suite, frontend syntax checks and
  isolated Qt lifecycle test after that correction. Its build was skipped
  because the commit was a source-only test fix without the workflow's
  \`[artifact-checkpoint]\` trigger.
- #2336 likewise passed source regression after the 1280/1366 player-grid CSS
  adjustment, but its Windows packaging job was skipped for the same reason.
  It is not counted as frozen-app responsive acceptance.

The next matching-head artifact checkpoint must exercise the packaged restart,
Step 7 cross-module ownership, Step 5/6 History and Task Manager, and Step 8
41-resolution plus window/scaling emulation gates before these steps are marked
packaged-pass.


## Step 8 CSS cascade correction — 5 November 2026

The 1280–1450px Audiobooks grid override was present but ordered before the
base \`.player-grid\` rule. Because both selectors had equal specificity, the
later base declaration overrode the narrower three-column layout. The
stylesheet now declares the base grid first and the 1251–1450px override
second. The regression test asserts both declarations and their cascade
order, rather than only checking that the media-query text exists. The
package matrix remains the required runtime check for all 41 sizes.


## Task Manager legacy renderer conflict — 5 November 2026

Packaged #2339 reached Task Manager and timed out because the static reference
HTML's target-level tab handlers repainted the shared list with prototype rows.
#2340 then found a visible row without the native View action. The adapter's
render signature could remain unchanged after an external repaint.

The correction intercepts Task Manager filter clicks in capture phase before
the legacy handlers and invalidates the previous signature. The backend
renderer also validates rendered job IDs, the three-column row structure,
each View action, and absence of non-backend prototype rows before it skips a
rebuild. Focused regression tests cover both protections.


## Step 7 carry-forward ownership checks — 5 November 2026

The packaged acceptance already generates and plays a real Chapter 2 Production
Preview, validates the M4A and PCM WAV paths, exercises duration variants,
Save As and cancellation, and checks the preview job's originating project and
stable chapter ID at job start. This checkpoint extends the ownership assertion
through job completion: the completed record must retain the same project
folder and chapter ID and must have a registered output. The restarted
cross-module acceptance also compares the recovered project's narrator with
the Audiobooks Player narrator metadata.

These checks are additive and preserve the earlier Stage 5.4/5.5 preview,
M4B and recovery flows.


## Stage 6 Task Manager refresh-race correction — 5 November 2026

### Failed-run audit
- **#2339:** packaged acceptance reached Task Manager but timed out waiting for
  the All filter to render all native jobs. Audiobooks Play and cross-module
  checks were reached after the #2338 live-card reacquisition test fix.
- **#2340:** the All list rendered, but a backend row lacked its View action.
  The responsive player-grid override was not reached in this run.
- **#2341:** 1,177 tests ran and one source regression errored because its
  source-slicing assertion still searched for the former direct-render branch.
  #2342 updated that contract to the DOM integrity guard; its source suite passed.
- **#2342:** source-test checkpoint passed; it validated the stable job-refresh
  DOM repair contract but did not itself prove packaged acceptance.
- **#2343:** packaged acceptance passed player restart/mini-player, Stage 5.4
  recovery, Music Library/BGM/cue persistence, cross-module output ownership
  and History search/details. It failed at the final Task Manager View check.

### Root cause and fix
The refresh wrapper shared one in-flight promise but did not remember calls made
while that promise was resolving. If the user changed Active/Completed/All while
a job.list call was underway, the new filter refresh could be absorbed by the
old promise. This left a prior DOM snapshot visible until a later heartbeat.
The wrapper now sets a pending flag and performs one serialized follow-up render
before resolving callers. It still prevents overlapping bridge calls and
collapses concurrent requests into the latest requested state.

The packaged Task Manager acceptance now waits for the complete native row
identity set, three-column structure and row-specific View action before
clicking it. This validates the completed DOM contract rather than accepting a
matching row count during an in-flight render.


## #2345 — refresh concurrency source gate passed (5 November 2026)

Commit `bdd4f4864b5c234aff6e40dacece306f77ba4921` passed the full source
regression suite: **1,180 tests passed** in 53.4 seconds. Frontend JavaScript
syntax validation and the isolated native Qt lifecycle regression also passed.
The Windows build job was skipped because this was a source-only test-contract
correction without the workflow artifact-checkpoint trigger. This is not a
packaged acceptance result.

The next matching-head artifact checkpoint must validate the queued follow-up
refresh behaviour in the frozen Windows application, then continue the 41
viewport matrix and release gates.


## Root-cause correction — Task Manager prototype timer (5 November 2026)

The packaged failure was traced to a second renderer embedded in
\`assets/frontend/ryu_audiobook_premium_v2.html\`. It created four hard-coded
sample jobs and ran a 4-second \`setInterval\` that called \`renderJobs()\` and
replaced \`#backgroundJobsList.innerHTML\` whenever the modal was open. The
backend adapter's click-capture guards could stop prototype click handlers,
but could not stop this independent timer. Depending on timing, it replaced
native \`data-backend-job\` rows with prototype \`data-job\` rows and removed
their real View/actions.

The prototype Task Manager renderer, sample job array, fake handlers and timer
have been removed. The independent Update Log controls remain. The backend
adapter now owns Task Manager close and History navigation, and the packaged
test keeps the real Task Manager open beyond the former 4-second timer
interval before checking exact job identities and actionable View controls.

The viewport harness now sets iframe \`width\`/\`height\` attributes as well as
CSS dimensions and waits for the actual iframe browsing context to reach the
requested \`innerWidth\`/\`innerHeight\`. A synthetic resize event cannot
change a browsing context's viewport.

These are root-cause fixes and regression tests; no acceptance gate was
weakened.


## #2347 — Task Manager prototype timer root fix source gate passed (5 November 2026)

Commit \`cbb49c00d910a50a70b539ac7c8e518b2a3e9f5f\` passed all source checks.
JavaScript syntax, isolated native Qt lifecycle regression and the full suite
passed: **1,182 tests in 49.775 seconds**. The two new root-cause regression
tests passed, proving the reference HTML no longer includes the sample
Task Manager renderer/timer and packaged acceptance requires native job rows
to remain stable beyond the former four-second timer interval.

The Windows packaging job was skipped because the commit was tagged
\`[root-fix]\`, not \`[artifact-checkpoint]\`. The next run is a documentation-
only checkpoint on the same application source head and will execute frozen
Windows package/restart acceptance, including the 41-view responsive matrix.
No application source is changed by this checkpoint.


## #2348 — tablet-width player grid root cause and fix (5 November 2026)

The packaged run passed source regression, frozen executable build, bundled
assets, Stage 5.4 full generation/retry/recovery, player restart/position,
Mini-Player, cross-module ownership, History and Task Manager. It failed only
at the first tablet responsive viewport (1024x768): the base three-column
player grid remained active and measured 909.84 CSS pixels wide inside a
1024-pixel viewport after side navigation was accounted for.

The root cause was CSS cascade coverage: the base 330px / minmax(400px, 1fr) /
330px grid was overridden only for 1251–1450px, while the <=1250px generic
media rule did not override the player grid in the frozen-app CSS cascade. A
tablet-width override is now inserted immediately after the base grid rule for
801–1250px. It forces a single minmax(0,1fr) player column and sets child cards
to min-width:0 and width/max-width:100%, preventing intrinsic card width from
reintroducing horizontal overflow. Existing <=800px mobile and >1250px desktop
rules are not modified.

A source regression contract now requires this exact tablet rule and cascade
position. The strict 41-resolution packaged matrix and overflow assertion are
unchanged.


## Tablet CSS root correction — 5 November 2026

Build #2353 completed all packaged acceptance checks through Stage 6 Steps 4–7,
History and Task Manager, then correctly caught a Player grid overflow at
1024×768 (right edge 1211.84 px in a 1024 px viewport).

Commit \`7967b1df67b9d5ddd910e091e97fc75e2a9b3fb9\` adds a final tablet-width
CSS guard for 801–1250 px. It reduces Player page horizontal padding, forces
the Player grid and its direct cards to a single bounded column, applies
\`min-width:0\` and \`max-width:100%\`, and lets control toolbars wrap. The
existing desktop and mobile breakpoints are retained.

The source gate passed in #2354 (1,182 tests), but the build job was skipped
because its commit message did not include \`[artifact-checkpoint]\`. This
documentation-only checkpoint is intended to run the frozen Windows build and
the same packaged 41-resolution acceptance on the CSS-fix commit.


## #2355 root-cause analysis and preventive fix — 5 November 2026

The frozen executable, frozen verification and bundled assets passed. Packaged
acceptance failed later at the Stage 5.4 job-control metadata wait. Its six-second
cue-import rejection was the intended production validation (fixed cue clips
must not exceed five seconds). The run then emitted mix-preview media
load/play-pause interruption messages before timing out at the later gate.

The acceptance sequence did not establish a durable-state barrier after the
injected cue-save failure and before starting full-book previews and Stage 5.4.
The correction keeps production cue validation intact and adds explicit waits
for cue save debounce/in-flight persistence, native cue-state readback, and
completion of all Sound Design preview jobs before switching into Stage 5.4.
The restored Chapter-Based BGM state is verified before the job-control flow.

Mix preview playback now owns a local Audio instance. Replaced preview promises
are caught, and stale ended/error callbacks cannot clear the active preview
reference. Added regression contracts cover cue import side-effect ordering,
retry settlement, preview drain and preview ownership.


## Shared application-shell grid correction — 5 November 2026

Build #2356 reached the final responsive matrix after the Stage 5.4 cue-save/
preview drain, player restore, mini-player, cross-module ownership, History and
Task Manager checks all passed. It failed at 1024×768 with the Player grid
starting at x=292 and ending at x=1221.84 in a 1024px viewport.

The Player-only tablet guard was not the underlying cause. The common desktop
application grid still used \`grid-template-columns: var(--side) 1fr\`; the
implicit minimum size of the \`1fr\` workspace track allowed its contents to
expand the entire shell beyond the iframe viewport. The workspace was also a
grid item without \`min-width:0\`.

The correction changes the second shell track to \`minmax(0,1fr)\`, the second
row to \`minmax(0,1fr)\`, gives the application shell a bounded width, and sets
\`min-width:0\`/100% bounds on the workspace and top bar. This is a shared
layout correction, not another Player-specific width override.

The packaged 41-resolution matrix now checks the application shell, workspace,
top bar and Player page bounds at every viewport in addition to the Player,
Audiobooks cards, mini-player, History, Task Manager and job-details surfaces.
The runner requires a dedicated shared-shell marker, so it cannot pass without
these checks. Matching-head frozen-Windows verification is pending.


### Responsive shell test breakpoint guard — 5 November 2026

The shared-shell matrix explicitly distinguishes the desktop/tablet two-column
grid from the intentional single-block mobile shell at widths ≤800px. It still
requires \`min-width:0\` on the workspace and verifies shell/workspace/topbar
bounds at every viewport. This prevents the test itself from reporting the
expected mobile CSS layout as a regression.


## Matching-head responsive shell verification checkpoint — 5 November 2026

Commit \`92506e7b23f23b9e5125da74214c6f40eb925f3e\` includes the shared
application grid correction from \`0b69c486c9f5534edb8df3545b70412364c33acd\`
and the corrected mobile breakpoint expectation. The exact-head source run
#2358 passed JavaScript syntax, isolated Qt lifecycle and **1,186 regression
tests in 63.423 seconds**. The Windows build was skipped because #2358 was a
test-fix checkpoint.

Build #2357 remains active against the preceding \`0b69c48\` revision. It is
preserved, but its packaged matrix predates the mobile single-column
expectation and cannot be used as the final responsive acceptance candidate.

This artifact checkpoint runs frozen-Windows acceptance against the corrected
\`92506e7\` responsive test contract. It requires the Stage 5.4/5.5 carry-forward,
Stage 6 Steps 4–7, the full 41-viewport matrix, window/scaling emulation,
shared application-shell bounds, and the installer/portable/hash/Defender
workflow steps. Physical manual installation is not claimed by CI.




## Latest Stage 6 checkpoint — Build #2359 (5 November 2026)

Build #2359 completed successfully on commit
\`af574d29774f19a3ce7ea8ed8ba5b93cc2174ee7\`. Its source and Windows
packaging jobs passed. This is the matching-head responsive shell checkpoint
and supersedes the earlier #2357 matrix failure. #2357's package acceptance
had already passed Stage 5.4 recovery, Step 4 player restoration, Step 7
cross-module ownership, History, Task Manager and prior viewport cases; its
remaining error was the shared application shell at 800x600. #2359 passed
after the responsive harness correctly expected the intentional one-column
mobile shell at widths <=800px.

The current branch has advanced beyond #2359 with the Task Manager View-action
root repair. Build #2360 is the matching-head verification candidate for that
repair. Its tests job has started; packaged acceptance has not yet run.

**Disposition:** Step 8's automated 41-resolution CSS viewport matrix and
responsive shell checkpoint passed in #2359. Physical minimize/restore,
extended/mixed-monitor topology and OS DPI remain manual Windows-display checks
and are not claimed as completed by viewport emulation.

## Task Manager View-action integrity repair — 5 November 2026

A packaged Windows run showed backend job identities and most row structure
were present, but a row could temporarily lose its View button during queued
refreshes. The adapter now treats one View action per backend-owned row, bound
to that row's stable job ID, as an invariant. It repairs a missing or mismatched
button in place before resorting to a complete row rebuild. The existing
delegated click handler and detail lookup remain the action path.

The packaged acceptance asserts unique native job IDs, exact DOM/native ID
equality, one correctly bound View action per row, status-filter membership,
summary counts and delayed-refresh integrity. No requirement is skipped or
weakened.
