# Final Closure Ledger — Ryu's Audiobook Premium V2

**Audit date:** 26 October 2026  
**Working branch:** `fix/native-ui-font-scale-learning-ai`  
**Source baseline:** successful Build Windows App #1423, commit `314afd4199e5dca7ef677b0aed313bc668692614`, plus follow-up commits listed below.  
**Purpose:** this file supersedes older status statements that describe the pre-follow-up source. It does not claim manual Windows acceptance.

## Most recent source changes

- `42c5931f23d247366dabef57248fefb3a1804e63` — job/history JSON persistence now writes to unique same-directory temporary files, flushes and fsyncs before replacing the last known-good file. Generation `narration.json` and `chunk_manifest.json` use the generator's atomic JSON writer. Regression tests simulate replacement failure and check that prior data survives and temporary files are removed.
- `a44f4367bdad9846ac1ffc0cf604dd0a128388d5` — audiobook generation now rejects `.m4a` and `.mp3` output targets because the current assembler emits a chaptered `.m4b`. This prevents silently saving a different file extension than requested. Regression test covers the backend/assembler contract.
- Successful packaging baseline #1423: 701 tests passed; installer, portable application and SHA-256 manifest uploaded. Release-publication step skipped. See https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/40219817108.
- Follow-up CI for later commits must be assessed by matching its head SHA to the branch head; a source commit alone is not proof of build success.

## Source-level work already present

- Qwen CUDA failure fallback and CPU runtime fallback; safer llama.cpp CPU fallback/download validation.
- Performance screen does not preserve prototype sample metrics as measured CPU/GPU/VRAM or benchmark results when telemetry is unavailable.
- Terminal operation history has its own `premium_v2_history.json` store, separate from the active queue and retained across queue visibility cleanup.
- Generation state uses resumable per-chunk checkpoints tied to a signature of current narration/voice/settings; invalid or missing WAV chunks are regenerated; assembly refuses missing/corrupt manifest chunks and validates the final M4B audio stream and minimum bitrate.
- Generation preflight rejects empty/ineligible chapters, and terminal job state distinguishes completed, failed and cancelled work.
- Project import is staged, source-preserving and transactional; duplicate source files are detected before project/job creation. Chapter fixtures cover multiple source formats and heading patterns.
- Chapter add/rename/delete/reorder/merge/split/clean/find/replace/bounded undo-redo, review and generation-exclusion paths are connected at source level; save failure blocks chapter switching.
- Saved manual character/dialogue assignment is source-validated and integrated into the synthesis routing path; automatic bulk AI line-level acceptance remains guarded.
- Player position saving and restore on metadata load are implemented in source. This still needs real-app restart acceptance.
- Model inventory and supported install/verify/repair/uninstall work via guarded background jobs. Refresh is local catalogue refresh, not a remote updater.
- Configured project-library and audio-output roots are supported in the existing settings/root path; legacy library locations remain visible, and storage reporting uses actual filesystem capacity.
- Project Trash/restore/purge handlers exist. Project-file writing is transactional/atomic.
- UI hardening includes stale-response guards, serialized job polling, stable rendering for unchanged sections, and progress-panel flicker remediation. Application-wide visual stability cannot be certified by static tests.

## True remaining code/product limitations

These must not be described as completed unless a separate implementation and test closes them:

1. **Output formats:** generation exports chaptered `.m4b` only. M4A/MP3 audiobook export is not implemented and is now rejected explicitly.
2. **Standalone project lifecycle:** standalone blank-project creation is unavailable; richer duplicate/archive/export/backup-restore workflow is not complete. Import creates an initial project.
3. **Hardware metrics:** live CPU/GPU/VRAM telemetry and a real benchmark are not implemented; the honest state is unavailable/not measured.
4. **Scanned PDF OCR:** image-only/scanned PDF OCR is not built in.
5. **Model actions:** remote model-update checking, universal default selection, and generic model test-generation are not implemented.
6. **Character AI:** bulk automated speaker suggestion acceptance remains prototype-only/guarded; manual source-backed assignment is available.
7. **Pronunciation:** the full per-profile test-result matrix, dictionary import/export, conflict tracking, and invalidation of already-generated audio require more work.
8. **Storage and secrets:** project-library and audio-output root selection exist, but model/cache root customization and related external-drive recovery acceptance are incomplete. Provider credentials are app-local/environment-backed, not in Windows Credential Manager.
9. **Database:** SQLite is a target/documented schema, not a deployed migration; existing project/job data uses file storage, JSON and QSettings.
10. **Diagnostics:** log redaction is best-effort, not a security guarantee.

## Manual Windows acceptance still required

CI builds and static regression tests do not prove the app is flicker-free, crash-free, or working with live providers and real audio on the user's PC. Until the exact installer/portable artifact matching the latest successful head SHA is tested, keep these acceptance items open:

- Install, launch, close and relaunch both installer and portable package; verify first-run and preserve/remove data behavior.
- Exercise all 15 destinations at 1920×1080, 1366×768 and 1280×720; check clipped controls, stale selections, UI flicker, duplicate event handling, stalls, WebEngine/bridge errors and crash logs.
- Import representative TXT, EPUB, searchable PDF and DOCX files; compare source text, chapter order/count and representative passage content. Test cancellation, corrupt/unsupported files, duplicate imports and low-disk errors.
- Run a real saved voice preview at supported durations; verify provider, profile, model, voice ID, playback and settings after restart.
- Generate a multi-chapter audiobook with real voice output; test pause/cancel/retry/restart, checkpoint reuse, selected character voices, pronunciation, cover/metadata, chapter navigation, duration and playback.
- Validate sound-design source assets, file-missing behavior, preview/final mix parity and licensed asset provenance.
- Confirm History survives restart/queue cleanup; confirm Player resume position and main/mini-player synchronization; inspect actual diagnostic exports before sharing.

## Closure rule

Mark a source item closed when the handler and regression test are present and the matching-head CI run passes. Mark a runtime item accepted only after the packaged Windows test is performed and recorded. Keep unsupported capability explicitly unavailable rather than simulating success. Do not claim zero flicker/crashes without repeated target-machine testing.


## 8 November 2026 — Character Studio large-book review closure overlay

This dated overlay supersedes the historical branch/build references above for the changes listed here only. It does not close unrelated cross-application requirements or claim installed-Windows acceptance.

**Current repair branch:** `fix/application-wide-closure-2026-11-08`  
**Source commit under this checkpoint:** `826011075ca45f27e17c788d215c82d0fe0fb5ee`

### Changes recorded

- `5b0d309e9261c3e72977ad076380c496998e19a4` — Character Studio AI review no longer silently limits the current chapter's pending queue to 120 rows. It renders bounded batches of 120 and exposes a real “Show more passages” action until all pending rows are reachable. The full pending/assigned counts remain based on the complete collection. The visible batch resets when the selected chapter or pending passage set changes.
- `826011075ca45f27e17c788d215c82d0fe0fb5ee` — AI-mode chapter navigation now reports per-chapter word count, detected passages, assigned passages, AI suggestions, pending review and skipped rows. It supports searching chapter number/title and filtering by analysis/review status without rebuilding the navigation on each keystroke.

### Exact-head automated evidence

- Build #2839 — `5b0d309e9261c3e72977ad076380c496998e19a4`: **1,368 tests passed**; Windows build job skipped. [Actions run](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42451900189).
- Build #2841 — `826011075ca45f27e17c788d215c82d0fe0fb5ee`: **1,369 tests passed**; Windows build job skipped. [Actions run](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42452095607).
- Test-first evidence: Build #2838 failed on the missing large-queue behaviour before the queue fix; Build #2840 failed on the missing chapter metrics before the navigator fix. Neither was weakened or skipped to obtain a pass.
- A Windows artifact-checkpoint run is required after this overlay is committed. Until its build job and artifact association are verified, this overlay does not claim a new installer or portable package.

### Remaining acceptance

- Exercise a book with more than 120 pending passages and confirm that repeated “Show more passages” actions expose every row exactly once, with no skipped or duplicated source passages.
- Search/filter chapters by number, title and each status in the installed app; verify word counts, passage counts and assignment counts against saved source data.
- Verify navigation, selection, filtering and scrolling in the packaged Windows application at the required display sizes/scales.
- This work does not close XAPP-01–03, XAPP-05–20, real-book AI analysis, canonical passage persistence, voice-routing, Qwen hardware, catalogue responsiveness, generation/audio or release gates.


## 8 November 2026 — Character Studio source-count and word-count correction

**Latest verified code commit:** `ec8b7a6e14350fbc19633d9e38e4d286a9f35235`  
**Branch:** `fix/application-wide-closure-2026-11-08`

Additional source corrections after the initial large-review overlay:

- `46e1e35b54ff7c25b968af76e4b9dadc39e5b4c4` — chapter Assigned, Pending and Skipped metrics now use the complete source-backed passage rows for the chapter, including saved manual assignments. AI suggestion count remains based on actual suggestion evidence rather than being conflated with manual assignments.
- `ec8b7a6e14350fbc19633d9e38e4d286a9f35235` — corrected chapter word-count tokenization to split on actual whitespace.
- `215d5feec368355ca34726573372b32913452b7a` — test-first coverage for source-backed manual/AI passage count reconciliation.
- `a7256a9fbf85493a8dc59a39bfc43c33e52387d2` — test-first coverage for whitespace tokenization. This run correctly failed on the over-escaped source regex before the fix.

### Exact-head CI evidence

- Build #2844 — commit `46e1e35b54ff7c25b968af76e4b9dadc39e5b4c4`: **1,370 tests passed**. [Actions run](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42452888537).
- Build #2845 — commit `a7256a9fbf85493a8dc59a39bfc43c33e52387d2`: failed on the intended chapter word-count regex assertion; 1,370 tests ran, one new assertion failed. The earlier Qt and Stage 6 preflights were successful. This was not waived or hidden.
- Build #2846 — commit `ec8b7a6e14350fbc19633d9e38e4d286a9f35235`: **1,370 tests passed** after the source correction. [Actions run](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42453314541).

### Acceptance still required

- Exercise chapters containing manual-only saved assignments, AI suggestions, skipped spans, dash-led dialogue and non-English quotations in the installed Windows app.
- Verify displayed word counts against representative saved chapter text and the full source-backed passage set.
- The successful CI results above do not establish an actual long-book run or installed-Windows acceptance.
- XAPP-03's persisted revision-aware canonical passage index and the historic 1,175-versus-1,196 reconciliation remain open; sharing a segmentation primitive and correcting chapter UI counts do not complete that separate requirement.
- XAPP-09's synchronous cold/forced Models and Sound catalogue scan paths remain open.
- The prior Build #2842 package attempt is on commit `2fc1434bc14e5962c5ebb9d2a470e8f379da63c2`, which predates these source corrections; it must not be presented as the package for `ec8b7a6`.


## 8 November 2026 — Catalogue responsiveness and canonical passage index closure

**Current repair branch:** `fix/application-wide-closure-2026-11-08`  
**Exact tested commit:** `5ecbd0f2490519bf862021a5b87114228b2cc325`  
**Matching-head regression run:** [Build #2866](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42462993020) — **SUCCESS, 1,374 tests passed** (44 targeted preflight tests plus the full regression suite).  
**Windows packaging:** **SKIPPED** on #2866. A new `[artifact-checkpoint]` run is required; do not reuse #2847's package as the binary for this source.

### XAPP-09 — Cold Models/Sound catalogue scans moved off the UI bridge

The former `models.list` and `sound.catalog` cache-miss/forced-refresh paths performed filesystem traversal on the synchronous Qt bridge dispatcher. The current repair uses one single-flight background scan per catalogue, returns the last-known-good snapshot immediately, records a durable job, and publishes a replacement snapshot only after a successful scan against the current source generation. Concurrent requests share the same scan. A failed scan leaves the prior snapshot intact and reports a failed job rather than replacing it with an empty catalogue.

The frontend now awaits catalogue job completion asynchronously before applying cue/music filters or showing refreshed model/voice state. Sound imports invalidate and refresh the catalogue; Voice Studio waits for model inventory; cue and chapter-BGM views share the catalogue loader. The 1,374-test matching-head suite passes.

**Status:** automated source/regression gate passed. Real cold-scan responsiveness on a large installed Models folder and large Sound library, concurrent with preview/generation on Windows, remains **RUNTIME ACCEPTANCE PENDING**. Do not yet claim the Not Responding issue is fully closed.

### XAPP-03 — Persisted revision-aware passage index integrated

The project-local `dialogue_passage_index.json` now records schema version, source revision, assignment/review revision, combined index revision, stable passage IDs, chapter identity/revision, exact source offsets/text, speaker/assignment state, AI suggestions, counts and overlap issues. Rebuilds are atomic and the loader validates the saved revision and every returned source slice before reuse.

Character Studio narration/review data and cast-aware Production's unresolved-speaker gate now read this persisted index for saved projects. AI-discovered source spans without quote/dash delimiters are added to the same review index when their offsets and exact text match the saved chapter. Overlapping AI spans are recorded as index issues and block cast-aware production until reconciled. Projectless/temporary test harnesses retain the pure segmenter fallback; installed projects use the persisted index.

**Status:** matching-head automated regression gate passed. The actual novel's historical **1,175 versus 1,196** passage discrepancy has not been proven reconciled, and the full-book installed-app review/assignment workflow remains **RUNTIME ACCEPTANCE PENDING**. This is not permission to call the count mismatch resolved without comparing against the user's saved book.

### Failure-run reconciliation

- #2848–#2855 and #2856–#2865 are historical red test-first/repair attempts. They exposed real integration and compatibility failures and were not waived.
- Build #2866 is the first current-head full-suite pass after the catalogue worker and canonical-index compatibility corrections: 1,374 tests passed on `5ecbd0f`.
- The old failed runs were **not rerun on their own commits**; the corrected, newer candidate is what passed. The Windows package gate remains outstanding on the current head.
- Previous successful Build #2847 remains a valid packaged checkpoint for its own SHA `548335540422593920f6e1795b29c8e9eb11d75f`, not for `5ecbd0f`.

### Requirements that remain open — do not silently close

- XAPP-01/02: full real-book analysis quality, cross-chapter identity/alias handling, false-positive rejection, persistent dismiss/exclusion and correction of existing false entries.
- XAPP-04/05: installed-app large-book navigation and saved profile assignment/reopen/preview/final-output routing.
- XAPP-07: real per-device Qwen CustomVoice/VoiceDesign/Clone benchmark and NVIDIA/AMD/Intel/integrated-GPU acceptance; physical inference-device evidence is still required.
- XAPP-08/13: actual narrator-only and multi-character book generation, audio listening, interruption/retry/resume and M4B validation on Windows.
- XAPP-10/11/12/14/16: real Task Manager timing/cancellation/restart, Voice Studio state consistency, one reconciled readiness state, exact Assigned Cast metrics, and cross-screen active-project state.
- XAPP-15/17: complete Premium V2 visible-control/backend/persistence/restart audit and final Help & Guide verification against the packaged app.
- XAPP-18: current release-candidate/PR dependency reconciliation remains to be recorded; no PR is to be merged merely to clear its open state.
- XAPP-19/20: same-SHA installer/portable parity and integrated runtime acceptance remain open after the next package.
- Frozen Master requirements outside XAPP-01–20 remain authoritative. Use `docs/stage-8/STAGE-8-REQUIREMENT-TRACEABILITY.md` and the Dragon Studio checklist; do not treat 1,374 passing tests as sign-off for all 128 frozen requirements.

### Package-size priority

The user has explicitly deprioritized the **500 MB executable target** in favour of functional completion. Retain the target and the size report as a documented non-priority; do not spend this closure window pruning required offline assets, and do not trade away Piper/Kokoro/Qwen runtime dependencies or bundled licensed starter assets merely to reduce package size.

**Traceability ledger synchronized:** `docs/stage-8/STAGE-8-REQUIREMENT-TRACEABILITY.md` updated in commit `e810ac09aef394673d8c98ac81763f7610d86c12`. It now carries the 8 November exact-head overlay and retains the remaining Master requirements as open where installed/runtime evidence is absent.


## Pronunciation candidate and Windows Qt teardown closure — 8 November 2026

**Latest tested code/runner commit:** `3e572dce8a3fbb3dc5d10e0254aba226500a7ff3`  
**Previous functional code commit:** `321dc94e3ec7534301195443b42e59dd5a084a91`  
**Branch:** `fix/application-wide-closure-2026-11-08`

### Corrections

- Removed the call from `_pronunciation_analysis_worker()` into the UI bridge method `_character_list()`. Background pronunciation analysis now reads the saved project cast directly and applies the same authoritative `is_likely_character_name()` / user-confirmed-record checks. This prevents pronunciation analysis from depending on Character Studio having been instantiated and avoids performing UI-facing persistence cleanup in the worker.
- Allowed a single-token Latin transliteration such as `Yamato` only when the authoritative character-name validator accepts it. The candidate must also occur as a whole token in the saved source, have explicit non-English language evidence, pass the common-English-word filter and meet the existing confidence threshold. Ordinary English prose such as `Very`, `The`, `Any` and descriptor phrases remain rejected.
- Added explicit Windows test-runner Qt teardown after all unittest cases and their cleanups complete. The runner closes test widgets, flushes deferred deletes/events, stops the QApplication and destroys its C++ object while PySide/Qt libraries remain loaded. This addresses the prior post-`OK` process exit with Windows status `-1073740791` (`0xC0000409`).

### Exact CI evidence

- Build #2881 failed on a missing test import; Build #2882 corrected that and passed 1,383 tests.
- Build #2883 exposed the pronunciation-worker/UI-bridge coupling.
- Build #2884 removed the bridge call; the worker then ran but the generic candidate guard rejected the expected in-book Japanese single-token name.
- Build #2885 accepted the name-filter correction and printed `Ran 1,387 tests` / `OK`, but the Windows process crashed during Qt interpreter shutdown with `0xC0000409`.
- Build #2886 — commit `3e572dce8a3fbb3dc5d10e0254aba226500a7ff3`: **1,387 tests passed; test job exited successfully**. The new explicit Qt teardown removed the post-suite process crash. [Actions run](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42477735032).

### Scope still not claimed complete

- This overlay does not close physical NVIDIA/AMD/Intel GPU inference and benchmark acceptance, a real long-book analysis and listening session, final audiobook playback/metadata acceptance, or the current-head Windows package.
- Build #2887 supersedes the previous #2847 package checkpoint. Its installer/portable artifacts match exact SHA `5f811eb60a912353926704b6ba7c8fbfed41e0cc`, with 1,387 tests passed, verified Windows packaging, install/upgrade/uninstall acceptance, and clean Microsoft Defender CI scans. Any source change after that SHA requires a new exact-head package before that binary is called current.
- The 500 MB executable target is explicitly not a release blocker and must not drive removal of required offline assets.
- Historical failed run records remain visible in GitHub. #2886 is the current cumulative passing regression checkpoint; do not rerun obsolete commits whose source predates the fixes.

## 8 November 2026 — Build #2887 integrated closure checkpoint

**Exact packaged head:** `5f811eb60a912353926704b6ba7c8fbfed41e0cc`  
**PR:** [#31 — Stage 8: integrated application-wide closure and release acceptance](https://github.com/RyuBlanc/ryu-audiobook-build/pull/31), open draft, base `stage-7/responsive-active-project-cache`, 70 commits, 38 changed files.  
**Run:** [Build #2887](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42477948917), full suite **1,387 passed**, Windows build succeeded.

### Artifact identities

- Installer artifact ID: `13616938581`, workflow artifact name `Ryu-Audiobook-Installer-2887`, ZIP size 846,086,086 bytes.
- Portable artifact ID: `13616784388`, workflow artifact name `Ryu-Audiobook-Portable-2887`, ZIP size 1,183,376,406 bytes.
- SHA-256 manifest artifact ID: `13617037536`, ZIP size 3,044 bytes.
- Piper benchmark artifact ID: `13617435436`, ZIP size 804 bytes.

Manifest binary SHA-256:
- HTML installer: `ead5dfa97b328f47794f4cee7a676f6c2e85192b884278967e75207688fcb9b2` (846,085,922 bytes).
- Core installer: `edf811bf60a630a5e98f54d4f2bcd1e15a6cafcede67d73b371a71d3bca60567` (619,261,899 bytes).
- Main application executable: `898a479dadd53816e2447ba7f15c51619fdea15634f4d93d7144eefd3626f384` (12,211,104 bytes).

Defender run #2887 reports no threats for the application executable, HTML installer and core installer. This is CI evidence, not proof of disposition of any prior endpoint-specific detection.

Verified benchmark: Piper CPU provider, 12.8053 seconds of audio generated in 3.5205 seconds, RTF 0.2749, on GitHub's Windows runner. No Qwen accelerator inventory was reported.

### Outstanding closure gates (do not infer from test pass)

- Actual long-book analysis, character/alias quality, false-cast cleanup on the user's saved project, and reconciliation of real dialogue totals.
- Installed Windows check of large-book review and passage index, including the known 1,175/1,196 discrepancy.
- Saved voice profile heard in Test Voice and final production after project restart.
- Qwen CustomVoice 0.6B/1.7B, VoiceDesign, Voice Clone and Automatic-mode benchmark matrix on actual NVIDIA/AMD/Intel/iGPU devices; 30-second preview under 60 seconds on agreed hardware.
- Real narrator-only and multi-character end-to-end M4B generation, playback, interruption, retry and resume.
- Task Manager elapsed time, cancellation, duplicate-job handling and restart recovery in packaged Windows.
- Full Premium V2 control-to-backend-to-persistence-to-restart acceptance and responsive display matrix.
- Full Pronunciation dictionary/profile/conflict/audio-invalidation requirements and Sound Design preview/final mix parity.
- Help & Guide parity and release PR/dependency review.
- Existing documented unsupported capabilities remain open/classified, including additional export formats, blank-project lifecycle, scanned PDF OCR, remote model updates, generic model test-generation, SQLite migration, external model/cache roots and credential storage integration.

The 500 MB executable target is not a functional release gate and remains deprioritized. Do not remove required offline voice models or starter audio to pursue it.
