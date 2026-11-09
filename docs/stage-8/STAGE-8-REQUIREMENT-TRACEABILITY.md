# Stage 8 — Frozen Requirement Traceability Matrix

**Source of truth:** the exact user-pasted Master Bug & Change Register and Additional UI Continuation preserved in `docs/stage-8/source-registers/`, Stage 8 Detailed Requirements, the Cross-App Addendum, and the existing staged execution plan. The two pasted files are byte-exact and their SHA-256 hashes are recorded in the source-register README.
**Repository:** `RyuBlanc/ryu-audiobook-build`
**Current repair branch:** `fix/application-wide-closure-2026-11-08`
**Implementation commits:** regression test `ef8044248daf2f109025861d231831f54cd19ca4`; assembler fix `cb25247c4dc95ff9f8ae518fe40dd7a52e17d583`; defect record `025a467112e60244bec541b5943283b838119ed5`.

## Status rules

- **OPEN:** incomplete, broken, not integrated or not yet evidenced.
- **IN PROGRESS:** actively being investigated/implemented.
- **CODE CHANGED — NOT VERIFIED:** source/test change exists, matching-head tests have not passed.
- **AUTOMATED TESTS PASSED:** relevant tests passed on the identified commit; runtime may remain pending.
- **RUNTIME ACCEPTANCE PENDING:** CI/code may pass but actual installed Windows behaviour remains unverified.
- **VERIFIED COMPLETE:** implementation, matching-head CI and all required runtime/audio evidence are recorded.
- **BLOCKED / UNSUPPORTED — EXPLICITLY DOCUMENTED:** only with a specific reason and explicit treatment.

Do not treat Build #2680's 1,258 passing tests as proof for code committed afterwards. Do not mark a requirement complete from a static element/function-name test. Manual Windows/audio acceptance remains distinct from CI.


## Current evidence overlay — 8 November 2026 (Build #2950 source-head reconciliation)

**Active branch:** `stage-5/xapp08-recovery-reentry-2026-11-08`  
**Application source candidate:** `976f8dbc132359f8c4b470688d61a1f3bd9ec209`  
**Windows CI:** [Build #2950](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42502827868) — `tests` passed, **1,428 tests passed**; focused Stage 6 preflight passed 45 tests. The `build` job was skipped because this branch's workflow only packages on an `[artifact-checkpoint]` commit or manual dispatch. The next commit is an evidence/package checkpoint and does not change application code.

This is the latest verified source-head regression result. It supersedes #2943–#2949 as the current CI verdict. #2944–#2949 were unsuccessful test attempts caused by stale or incorrectly-scoped test assertions after the readiness gate was strengthened; the assertions were corrected and #2950 passed. Those failed attempts are retained in Actions history, not described as product regressions.

### Matching-branch functional evidence

| Build | Tests | Verified area | Remaining acceptance |
|---|---:|---|---|
| #2930 | 1,407 | Actual retry/recovery route creates a new job linked to the interrupted narrator-only job, preserves saved narrator identity and bypasses character providers. | Real interruption/recovery on installed Windows using a real audiobook remains open. |
| #2932 | 1,411 | Audiobook loading, playback preference persistence, cache rebuild without changing M4B, chapter/listening position validation. | Listen to real output in the installed Windows app remains open. |
| #2935 | 1,415 | Real GenerationManager worker pause/resume at a saved chunk boundary and cancel while paused. | Real long-running generation cancellation/recovery on target hardware remains open. |
| #2936 | 1,416 | Two-chapter GenerationManager-to-M4B integration, embedded chapter metadata/cover and container validation. | Listen through the full audiobook and validate target-device playback remains open. |
| #2938–#2939 | cumulative suite | Production preview Save-path correction, saved narrator/chapter identity, preview/final-generation parity. | Real provider audio and listening checks remain open. |
| #2940–#2942 | 1,424 at #2942 | Durable progress-stage mapping, independent Production Preview job lifecycle, and typed durable full-generation job identity. | Packaged-app interaction remains open. |
| #2950 | 1,428 | Metadata/output readiness summary, eligible/empty/excluded chapter counts, shared full-generation gate, gate persistence during job polling, narrator-only readiness handling. | Exact-head Windows package and installed-app acceptance are pending. |

### Readiness correction included in #2950

- The project summary now reports eligible, empty and excluded chapters separately.
- A new project's default M4B destination can be ready before an output file exists. Custom output folders that do not yet exist are considered ready only when their nearest existing ancestor is writable; the generation handler creates the folder.
- The Production Generate button and Dashboard readiness flow both require saved metadata, an available saved narrator, at least one eligible chapter, supported M4B output and a writable/creatable destination.
- Narrator-only mode explicitly bypasses the character-voice readiness stage.
- The job-poll refresh applies the same prerequisite function as the initial render; it cannot re-enable generation using an older metadata-only rule.

### Current package status

Build #2922 remains a successful Windows package checkpoint on the earlier XAPP-08 branch, not a package of this Stage 5 recovery-reentry source head. #2950 passed tests but skipped packaging. The next `[artifact-checkpoint]` workflow run is required to prove that the exact reconciled Stage 5 candidate can be frozen, run through packaged acceptance, installed/upgraded/uninstalled, scanned, and uploaded as installer/portable artifacts. Do not call #2922 the latest package for the Stage 5 candidate.

### Still open and deliberately not inferred from CI

- Real installed-Windows playback and listening, including the new M4B chapter navigation.
- Real interrupted audiobook recovery and pause/resume/cancel using an actual saved project on the installed app.
- Qwen 30-second preview under 60 seconds. Earlier 1.7B measurements around 298–305 seconds remain evidence that this target was not met; no newer passing <60-second measurement has been supplied.
- Multilingual pronunciation correctness by listening to representative names and passages.
- Full visual review of every screen at the user's actual display scaling, multi-monitor arrangement and window sizes.
- Any requirement whose control, persistence, recovery or output behavior has not been exercised end-to-end on the packaged Windows application.


## Historical evidence overlay — XAPP-08 / Build #2929 snapshot

This overlay separates the latest packaged candidate from the latest regression-only source head. Build #2922 is the latest verified Windows package checkpoint currently evidenced here; Build #2929 is a newer regression-only checkpoint and must not be represented as a package build. The older #2866/#2847/#2887 snapshots remain historical evidence, not current release evidence.

**Latest source-head evidence — 8 November 2026:** the XAPP-08 branch head `712d84468b6f9a1ae49b3870cebc91056274af5d` (Build #2929) passed the Windows regression job with **1,406 tests**. The `build` job was skipped by the feature-branch workflow condition. The preceding #2925 test failed on a test expectation that compared both recovery jobs against the last loop's generation mode; #2926 corrected the assertion to use the expected identity keyed by each original job ID, and #2929 passed. The newly added Recover-to-GenerationManager regression is on `stage-5/xapp08-recovery-reentry-2026-11-08` and is awaiting its matching-head CI result.

**Latest packaged checkpoint — Build #2922:** commit `cb8afef216bc39f2b0966c04a2abed07eee7aa22` on `fix/xapp-08-explicit-narrator-only-2026-11-08` passed both `tests` and `build` jobs. Installer, portable app, SHA-256 manifest and Stage 7 Piper benchmark artifacts were uploaded. Because #2922 predates the later #2923–#2929 source commits, its artifacts are not a package of the #2929 head or this recovery-reentry candidate.

| Requirement area | Current evidence | Acceptance status |
|---|---|---|
| Character Studio large review queue / chapter navigator | #2841/#2846: queue pagination, chapter filters/metrics, source-backed counts and correct word counts. #2887 cumulative suite passed. | Automated regressions passed. Actual full-book navigation and source comparison on the user's saved novel remain pending. |
| False-character cleanup / pronunciation | #2878–#2886 sequence: English prose/interjections rejected, user-confirmed aliases preserved, pronunciation worker isolated from UI bridge, foreign single-token names require source occurrence and non-English evidence; #2882/#2886/#2887 passed cumulative regression. | Automated regression evidence passed. Must verify cleanup of the existing saved cast and pronunciation output against the actual book. |
| Canonical dialogue passage index (XAPP-03) | Project-local revision-aware atomic index with stable IDs, source slices/offsets, chapter/source/assignment revisions and assignment states; consumed by Character Studio and cast-aware Production. Unit tests cover stale source slices, revision rebuild and stable IDs. | Automated evidence present. Actual 1,175 vs 1,196 book count reconciliation and installed-app review remain runtime acceptance pending. |
| Models/Sound responsiveness (XAPP-09) | Single-flight background catalogue jobs; last-known-good snapshots; UI awaits scan completion asynchronously. | Automated regression evidence present. Large target-PC filesystem scans concurrent with preview/generation remain runtime acceptance pending. |
| Sound Design / Music Library | #2887 package pipeline includes packaged Sound Design/Music UI acceptance and matching-head Windows artifact. | Automated/package acceptance passed. Human listening, licensing/source inspection and actual project mix parity remain open. |
| Windows packaging and Defender | Build #2887 exact head `5f811eb60a912353926704b6ba7c8fbfed41e0cc`; installer, portable, SHA manifest and Piper benchmark uploaded. Windows install/launch/upgrade/uninstall and user-data preservation steps passed. Defender separately reported no threats for app, HTML installer and core installer. | Packaged CI checkpoint passed. User-machine installation and prior endpoint-specific alert disposition remain separate. |
| Frozen Master requirement set | 133 stable IDs from the pasted Master Register plus continuation; 20 Cross-App Addendum IDs remain separately tracked below. | Not complete. No bulk closure inferred from CI. |

**Exact Build #2887:** [Actions run](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42477948917), **1,387 tests passed**, Windows build succeeded, app version 1.1.1. Installer artifact ID `13616938581`; portable `13616784388`; SHA manifest `13617037536`; Piper benchmark `13617435436`.

**500 MB installer target:** explicitly deprioritized by the user and non-blocking for functional closure. Preserve required offline voice models and starter assets.

**Still open:** actual-book quality/count reconciliation; saved voice identity heard through preview and production after restart; Qwen device/task benchmarks and 30-second under-60-second target on agreed hardware; narrator-only and multi-character full M4B playback/recovery; real Task Manager timing/cancellation/restart; complete control/persistence/restart audit; target display/DPI/multi-monitor runtime; pronunciation dictionary/profile/conflict/audio-invalidation; Help & Guide final parity; and any frozen Master items without a matching behavioral test/runtime proof.

## Frozen requirement IDs

This inventory extracts all stable requirement IDs from the Master Bug & Change Register. The title is a compact index; the full original requirement text remains authoritative and must not be weakened.

| ID | Priority | Requirement | Current status | Evidence / next gate |
|---|---:|---|---|---|
| UI-01 | P0 | Premium V2 is the required default UI. | AUTOMATED REGRESSION VERIFIED — installed-app visual acceptance open | Premium V2 default/native fallback contract passed in the #2950 cumulative Windows suite. |
| UI-02 | P0 | Fix overlapping and unreadable elements. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| UI-03 | P0 | Resolve flickering without requiring Reduce Motion to be off. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| UI-04 | P0 | Desktop application behaviour. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| UI-05 | P0 | Notifications, errors and empty states. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| UI-06 | P0 | Responsive layout acceptance. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| UI-07 | P0 | Preserve existing stability improvements. | AUTOMATED REGRESSION VERIFIED — user-workflow acceptance open | UI stability, refresh/selection/scroll, navigation, autosave and lifecycle regressions passed in the #2950 cumulative suite. |
| VS-01 | P0 | 30-second preview under 60 seconds. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| VS-02 | P0 | Preserve character voice identity. | AUTOMATED REGRESSION VERIFIED — audible identity acceptance open | Saved narrator/character routing and Production preview parity/recovery tests passed #2930, #2939 and #2950. |
| VS-03 | P1 | Emotion-aware narration. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| VS-04 | P1 | Story-aware background effects and voices. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| VS-05 | P1 | Make emotion/effects global. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| VS-06 | P0 | Accurate multilingual pronunciation. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| VS-07 | P1 | Emotion and pronunciation must cooperate. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| VS-08 | P0 | Preserve all previous Voice Studio fixes. | AUTOMATED REGRESSION VERIFIED — installed-app voice acceptance open | Voice Studio refresh, profile identity and preview state regression coverage passed in the #2950 cumulative suite. |
| CS-01 | P1 | Real Assigned Cast list. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| CS-02 | P1 | Project isolation and live assignment data. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| CS-03 | P1 | Audio Profile dropdown. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| CS-04 | P1 | Test selected character dialogue. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| CS-05 | P1 | Assignment statistics. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| CS-06 | P1 | Display selected-character dialogue. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| CS-07 | P1 | Source highlighting. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| CS-08 | P1 | Persist assignments. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| CS-09 | P1 | Clear character assignments. | OPEN — implementation/evidence reconciliation required | Continuation requirement; verify assignment removal and saved state in the user's book. |
| CS-10 | P1 | Test Character Studio dialogue. | OPEN — implementation/evidence reconciliation required | Continuation requirement; verify selected profile routing and audible output. |
| CS-11 | P1 | Preserve chapter and source context. | OPEN — implementation/evidence reconciliation required | Continuation requirement; verify source passage and chapter context through review and restart. |
| CS-12 | P1 | Reconcile character statistics with dialogue records. | OPEN — implementation/evidence reconciliation required | Continuation requirement; reconcile actual-book counts and readiness indicators. |
| PS-01 | P1 | Simplify the interface. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PS-02 | P1 | Required dictionary table. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PS-03 | P1 | Search all relevant entries. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PS-04 | P1 | Audio Profile selection. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PS-05 | P1 | Add Entry. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PS-06 | P1 | Analyze Book. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PS-07 | P1 | Single and multiple delete. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PS-08 | P1 | Individual Enable toggle. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PS-09 | P1 | Global pronunciation toggle. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PS-10 | P1 | Differentiate AI and manual rows. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PS-11 | P1 | Test pronunciation behaviour in real audio. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| SD-01 | P1 | Remove specified top-right actions. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| SD-02 | P1 | Connect Same BGM/Chapter-Based BGM. | CODE CHANGED — NOT VERIFIED | Assembler regression test test_chapter_based_bgm_never_falls_back_to_auto_music (ef804424); preview regressions for No BGM and explicit-track-only routing (fb82fe0); assembler fix cb25247c; chapter-preview fix 37d30f9. Matching-head execution pending. |
| SD-03 | P1 | Chapter BGM filters. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| SD-04 | P1 | Chapter track selection. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| SD-05 | P1 | Chapter volume. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| SD-06 | P1 | Start offset and end behaviour. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| SD-07 | P1 | Save chapter assignment. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| SD-08 | P1 | Separate cue library. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| SD-09 | P1 | Cue card readability. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| SD-10 | P1 | Cue preview. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| SD-11 | P1 | Save Cue Changes and autosave. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| SD-12 | P1 | Connect cues to final production. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| SD-13 | P1 | Live Mix & Production Sync summary. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| SD-14 | P1 | Live levels. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| SD-15 | P1 | Final production handoff. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| MUS-01 | P1 | Real music library. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| MUS-02 | P1 | Required categories. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| MUS-03 | P1 | Real category filtering. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| MUS-04 | P1 | Import track workflow. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| MUS-05 | P1 | Track persistence. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| MUS-06 | P1 | Selected Track panel. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| MUS-07 | P1 | Master BGM volume. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| MUS-08 | P1 | Chapter volume. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| MUS-09 | P1 | BGM/voice-only configuration. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-01 | P0 | Add Input Project Details. | AUTOMATED REGRESSION VERIFIED — installed-app acceptance open | Metadata dialog, save, history, cover and rollback tests passed in the #2950 cumulative suite (1,428). |
| PROD-02 | P0 | Metadata fields. | AUTOMATED REGRESSION VERIFIED — installed-app acceptance open | Ten required fields, validation and persisted read-back/rollback tests passed in #2950. |
| PROD-03 | P0 | Metadata completion gate. | AUTOMATED REGRESSION VERIFIED — packaged acceptance open | #2950 verifies missing metadata, narrator availability, eligible chapters, M4B type and output folder gates; job refresh cannot bypass the gate. |
| PROD-04 | P0 | Metadata persistence and output. | AUTOMATED REGRESSION VERIFIED — real-book output acceptance open | Atomic metadata save/read-back, usable default/custom M4B destination and two-chapter M4B assembly tests (#2936, #2950). |
| PROD-05 | P0 | Real progress animation. | AUTOMATED REGRESSION VERIFIED — installed-app observation open | Durable generation stage/progress mapping passed #2940 and cumulative #2950 (1,428 tests). |
| PROD-06 | P0 | Separate preview and full generation states. | AUTOMATED REGRESSION VERIFIED — installed-app acceptance open | Independent typed Production Preview and full-generation job identity/monitor coverage passed #2941–#2942 and cumulative #2950. |
| PROD-07 | P0 | Preview generation controls. | AUTOMATED REGRESSION VERIFIED — real listening open | Preview identity/parity, saved chapter ownership, duration and Save-path tests passed #2938–#2939 and cumulative #2950. |
| PROD-08 | P1 | Live pronunciation toggle. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-09 | P1 | Live BGM/cue toggle. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-10 | P1 | Live project summary. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-11 | P1 | Music summary. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-12 | P1 | Output summary. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-13 | P1 | Live Readiness Center. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-14 | P0 | Consistent job state. | AUTOMATED TESTS PASSED — RUNTIME ACCEPTANCE PENDING | #2929 (commit 712d844): 1,406-test Windows regression run passed; History/Task Manager generation-mode visibility contract and backend terminal identity are covered. Installed Windows UI verification and exact-head package remain pending. |
| PROD-15 | P1 | Chapter-specific preview audio and download. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| AB-01 | P2 | Compact audiobook cards. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| AB-02 | P0 | Fix audio file loading. | AUTOMATED REGRESSION VERIFIED — installed-app playback open | #2932 real backend loading/cache restoration regressions; full suite remains green at #2950. |
| AB-03 | P0 | Full player controls. | AUTOMATED REGRESSION VERIFIED — real audio operation open | #2932 preference/transport contracts and #2950 cumulative suite; manual player control/listening remains open. |
| AB-04 | P0 | Chapter playback. | AUTOMATED REGRESSION VERIFIED — real chapter listening open | #2932 player chapter/listening-position coverage and #2936 embedded M4B chapter metadata; installed-app playback remains open. |
| AB-05 | P1 | Persistent mini-player. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| AB-06 | P1 | Playback position persistence. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| AB-07 | P0 | Preserve completed output integrity. | AUTOMATED REGRESSION VERIFIED — real output playback open | #2932 cache rebuild preserves authoritative M4B; #2936 validates assembled chaptered M4B; #2950 cumulative suite. |
| HIS-01 | P2 | Accurate history records. | AUTOMATED REGRESSION VERIFIED — installed-app history acceptance open | Terminal job ownership/results and History details are covered by #2928–#2929 and the cumulative #2950 suite. |
| HIS-02 | P2 | Date filtering. | AUTOMATED REGRESSION VERIFIED — installed-app history acceptance open | Search/date filtering source and backend record tests passed in the #2950 cumulative suite. |
| HIS-03 | P1 | Durable history. | AUTOMATED REGRESSION VERIFIED — restart acceptance open | Independent durable job/history persistence and generation identity coverage passed #2928–#2929 and #2950. |
| JOB-01 | P2 | Fix readability and layout. | AUTOMATED REGRESSION VERIFIED — target-window visual acceptance open | Task Manager bounded dialog and responsive layout contract tests passed in the #2950 cumulative suite. |
| JOB-02 | P2 | Job details. | AUTOMATED REGRESSION VERIFIED — installed-app detail acceptance open | History/Task Manager open-details and narrator generation identity display tests passed #2929 and #2950. |
| JOB-03 | P2 | Accurate totals and filters. | AUTOMATED REGRESSION VERIFIED — installed-app data acceptance open | Backend History and Task Manager filter/record contracts passed in the #2950 cumulative suite. |
| JOB-04 | P1 | Safe operations. | AUTOMATED REGRESSION VERIFIED — real lifecycle acceptance open | Pause/resume/cancel/retry/recover ownership and safe state tests passed #2930, #2935 and #2950. |
| JOB-05 | P1 | Consistency with History. | AUTOMATED REGRESSION VERIFIED — installed-app acceptance open | Durable History/Task Manager generation identity and details tests passed #2929 and #2950. |
| MOD-01 | P1 | Audit actual model installation inventory. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| MOD-02 | P1 | Synchronize voice/model selectors. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| MOD-03 | P1 | Model lifecycle. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| MOD-04 | P1 | Preserve profile and storage integrity. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| MOD-05 | P2 | Be clear about remote actions. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PERF-01 | P1 | Actual PC compatibility information. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PERF-02 | P1 | Real benchmark. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PERF-03 | P1 | Real backend recommendations. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PERF-04 | P2 | PC comparison. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PERF-05 | P0 | Preview performance target. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| IMP-01 | P1 | Correct import and source preservation. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| IMP-02 | P1 | Correct chapter segmentation. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| IMP-03 | P1 | Preserve chapter editing. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| IMP-04 | P0 | Prevent autosave/navigation races. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| IMP-05 | P1 | Source/project persistence. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| LIB-01 | P1 | Safe single and multiple project deletion. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| LIB-02 | P1 | Preserve history. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| LIB-03 | P1 | Recoverable projects. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| LIB-04 | P1 | Project identity and save state. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| LIB-05 | P2 | Known project-lifecycle limitations. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| GEN-01 | P0 | Real generation workflow. | AUTOMATED REGRESSION VERIFIED — full-book listening open | #2936 exercised GenerationManager through two chapters and actual M4B assembly; cumulative suite passed #2950. |
| GEN-02 | P1 | Resumable and recoverable generation. | AUTOMATED REGRESSION VERIFIED — real interrupted-book acceptance open | #2930 recovery re-entry retains narrator-only identity and job lineage; pause checkpoint coverage #2935; cumulative #2950. |
| GEN-03 | P1 | Pause/cancel/retry. | AUTOMATED REGRESSION VERIFIED — installed-app lifecycle acceptance open | #2935 real worker pause/resume/cancel at chunk boundary; retry/recovery lineage tests are included in the cumulative #2950 suite. |
| GEN-04 | P1 | Empty/ineligible chapters. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| GEN-05 | P0 | M4B validation and metadata. | AUTOMATED REGRESSION VERIFIED — target-player listening open | #2927 strict metadata/cover validation and #2936 two-chapter M4B metadata/cover/container integration; cumulative #2950. |
| GEN-06 | P0 | Preview/final parity. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| GEN-07 | P0 | Narrator-only generation for books without configured character profiles. | PACKAGED WINDOWS ACCEPTANCE PASSED — ACTUAL-BOOK/LISTENING OPEN | User-confirmed 1.2.0 behavior: automatically use the available saved narrator at zero valid configured character profiles; persist the effective mode across preview, generation, recovery and restart; use no dummy character profiles; retain normal cast routing once profiles are configured; missing narrator remains a blocking error. Build #3006 at exact source head `9da241b` passed packaged GEN-07 and Sound Design/Music Library acceptance. User's saved-book and listening acceptance remains open. |
| PKG-01 | P1 | Installer below 500 MB target. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PKG-02 | P2 | Investigate slow downloads. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PKG-03 | P1 | Preserve installer quality and branding. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PKG-04 | P0 | Verify exact artifacts. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| HELP-01 | P2 | Update the complete guide after implementation. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| HELP-02 | P2 | Reflect actual functionality. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| HELP-03 | P2 | Document limitations honestly. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| REL-01 | P0 | Reconcile outstanding change branches. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| REL-02 | P0 | Verify full regression suite. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| REL-03 | P0 | Package the exact verified candidate. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| REL-04 | P0 | Test the real Windows app. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| REL-05 | P0 | Real audio acceptance. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| REL-06 | P0 | Never misrepresent completion. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| REL-07 | P0 | Version 1.2.0 release/versioning gate. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |

## Additional consolidated requirements without individual IDs

- Voice identity remains stable while emotion varies naturally; story-aware sound effects are contextually appropriate.
- Character Studio Assigned Cast, profile selection, selected-dialogue Test Voice transport, real dialogue/chapter statistics and AI/manual source highlighting.
- Pronunciation Dictionary layout, search across saved data, AI/manual provenance, profile-aware audio preview, add/analyze/edit/delete/bulk-delete, individual/global enable state and preview/final consistency.
- Version 1 BGM strategies are mutually exclusive: Same BGM means one book-default track throughout; Chapter-Based ignores the book default and uses only one explicitly assigned track per chapter or No BGM. No silent fallback or layered BGM.
- Chapter filters, selected-track confirmation, chapter volume ceiling, start offset, end/fade behaviour, fixed Opening/Next Chapter/Closing cues, live mix summary and real audio levels.
- Music Library category filtering, import/category metadata, persistence, actual preview transport, 18% master default and 50% maximum.
- Input Project Details metadata and completion gate; live Production summary/readiness and Settings-derived output path.
- Real preview/full-generation progress and timing; selected-chapter preview must use only the selected saved chapter, play and download the actual preview, and remain isolated from full-book generation.
- Compact Audiobooks cards, actual local audio playback, full player controls and persistent mini-player.
- Help & Guide must describe the verified current application and honestly document limitations.
- Full final acceptance checklist in Master Register Section 23, including responsiveness, flicker, crash/recovery, UI controls, packaging, hardware and real-audio checks.

## Release-wide non-negotiable gates

- Preserve Premium V2 and all existing working features.
- No fake success, placeholder state or guessed hardware/performance data.
- Test first; fix root causes; preserve meaningful assertions.
- Preview, production assembly and final output must use the same saved effective configuration.
- Keep all hardware-specific NVIDIA/AMD/Intel and physical Windows checks pending until actual evidence exists.
- Do not update the app version, tag or publish Version 1.2.0 until REL-01 through REL-07 and the full Section 23 checklist are satisfied or explicitly accepted as exceptions.

## Current Stage 8 package status

1. **8.2.7 CI stabilization:** current source HEAD `7e8a20fdc9d812f558060f30b31faee49305f6a0` passed Build #2798 with **1,314 tests**. The Windows package job was skipped because this commit did not contain `[artifact-checkpoint]`. The prior exact package is #2768 at `9ff9bc05d70444c375c692839d2e8346d34b70cf`; it is not the current source candidate.
2. **8.2.8 Sound Design completion:** Chapter-Based explicit-only routing, Same BGM single-track behavior, single-bed legacy ambience, active-asset validation, full-book preview safety/cancellation, and measured Production chapter-preview paragraph offsets are implemented. The current 1,314-test suite passed on #2798, including the 34-test Stage 8.2.8 test module. Exact-head packaged audio acceptance and human listening remain pending.
3. **8.2.9 Frontend/backend parity + Help & Guide:** the current Premium V2 source contains 15 sidebar destinations (14 application destinations plus Help), the searchable Help & Guide, and the packaged acceptance script for destination navigation, Help search/empty results/expand/collapse and responsive viewport checks. Static adapter audit recorded 108 direct command names matched to 132 host handlers. #2798 source regression passed; the updated packaged acceptance script still needs execution on the current candidate. Physical mixed-monitor/DPI/minimized-window acceptance remains pending.
4. **8.2.10 Generation reliability:** current source and regression coverage include selected-chapter preview identity, measured duration, independent preview/full-generation job state, cancellation, pause/resume, retry/recovery, output integrity and M4B preview/final audio comparison. The matching-head #2798 regression suite passed. Exact-head frozen-app execution and user listening remain pending.
5. **8.2.11 Windows release validation:** #2768 is the latest verified package before the current source updates. It produced installer artifact 846,239,172 bytes and portable artifact 1,183,224,790 bytes from version 1.1.1. The current #2798 source has no matching-head installer/portable artifacts yet. The 500,000,000-byte size target remains unmet and optimization stays deferred; do not remove offline assets.
6. **8.2.12 Final acceptance/release:** the current source reports application version 1.2.0, but no public release/tag has been created. This next package is a test candidate, not proof of final release acceptance. Final release remains gated by exact-head package evidence, current packaged acceptance, friend/target-Windows feedback, and explicit documentation of deferred hardware checks.

**Inventory count:** 128 stable requirement IDs. The matrix remains a requirement ledger, not a count of completed tests. Only rows with direct, matching-head evidence should advance; no bulk completion is inferred from the green suite.


## 8.2.8 test-first fix checkpoint

- Regression test commit: `ef8044248daf2f109025861d231831f54cd19ca4`.
- Source fix commit: `cb25247c4dc95ff9f8ae518fe40dd7a52e17d583`.
- Defect record commit: `025a467112e60244bec541b5943283b838119ed5`.
- This checkpoint requests the Windows workflow's full artifact-checkpoint gate on the current candidate. Record the resulting run and artifact hashes only after verifying the Actions result.
- Until matching-head tests pass, SD-02 remains CODE CHANGED — NOT VERIFIED. Real Windows audio acceptance remains pending even after CI passes.


## REL-01 — Live branch and pull-request dependency audit

**PR dependency graph and file comparisons were audited at working HEAD `811822a0497b6943ba61b85105b797a9409b2a18`; the branch has since advanced with Sound Design tests/fixes through `998320c29046d6b84b82d578d12704ebcdc93eb6`. The recorded branch-divergence conclusions remain to be rechecked before any PR merge.

| PR | Current state | Head / base | Comparison with working branch | Integration decision |
|---|---|---|---|---|
| #15 | Open, draft, not mergeable | `fix/import-qa-speaker-hover-hardware` → `main`; head `9aa1ba5` | Its head is an ancestor of the working branch. | Do not merge a duplicate stack. Verify its relevant import, UI, hardware and model fixes remain present in current code. |
| #18 | Open, ready, mergeable | `stage-3/voice-studio-character-assignment` → `fix/import-qa-speaker-hover-hardware`; head `47db24f` | Diverged; 27 commits unique to PR #18 are not in current branch. Changed files include Character Inspector backend/tests, Character/Voice host and frontend adapter. | Outstanding integration dependency. Do not merge blindly: current branch has a substantially evolved Premium V2 host/adapter and already contains frontend-derived inspector UI. Compare behavior and selectively port missing verified capabilities. |
| #19 | Open, draft, not mergeable | `stage-4-pronunciation-sound-design` → Stage 3; head `c33479c` | PR head is an ancestor of the working branch. | Stage 4 stack is already in current lineage; do not duplicate-merge. Verify its required behavior against the current register. |
| #20 | Open, draft, mergeable | `fix/installer-branding-accessibility` → Stage 4; head `05c4efb` | PR head is an ancestor of the working branch. | Branding changes are already in current lineage; retain runtime wizard visual acceptance as pending. |
| #26 | Open, ready, mergeable | `fix/library-delete-recovery-live-character-data` → `main`; head `80b53bb` | Diverged; 43 commits unique to PR #26 are not in current branch. | Do not merge blindly. `app/core/project_trash.py` is byte-identical in current branch; current host/adapter already expose Character Library bridge/UI behavior and current `app/core/character_library.py` is newer/different. PR #26's separate page and import-status module are absent; audit whether the current integrated UI provides equivalent functionality before porting anything. |
| #4 | Open, ready, not mergeable | `fix/qwen-preset-selection-and-audio-stage` → `main`; head `60d4285` | Diverged; 2 commits unique to PR #4 are not in current branch. | The preset-change behavior is already present in current `app/ui/voice_page.py` with equivalent draft/selection reset logic but different status wording. Verify regression coverage before deciding whether the PR can be closed as superseded. |

### Specific parity observations from source inspection

- Current `app/ui/premium_v2_host.py` exposes Character Library list/save/delete/import/restore bridge actions and persists project/series metadata.
- Current `assets/frontend/premium_v2_backend_adapter.js` renders an Assigned Cast inspector, saved-profile selector, dialogue rows, line count, unique chapter count, AI-assigned percentage and AI/manual row styling. This is a different implementation from PR #18's new Python `character_inspector.py`; confirm the percentage/source calculation and selected-dialogue playback with behavioral tests rather than importing duplicate implementations.
- Current `app/core/project_trash.py` matches PR #26's file exactly, so that portion is already integrated.
- Current `app/ui/voice_page.py` already clears a saved profile when a Qwen VoiceDesign preset changes and labels the result as an unsaved draft. PR #4's behavior is present in evolved form; its test coverage still needs confirmation.

**REL-01 status:** IN PROGRESS. The branch graph is now recorded; functional equivalence and selective integration are not yet accepted.

## Exact-candidate verification boundary

The most recent commits on this branch include the test-first BGM regression, assembler fix, evidence record, 128-ID traceability matrix and this PR audit. Build #2680's 1,258 passing tests predate these source changes. No matching-head passing CI result or real Windows audio acceptance is recorded here. The current candidate must pass the full regression suite and a Windows artifact-checkpoint build before any affected requirement can advance beyond CODE CHANGED — NOT VERIFIED.


## Updated Sound Design test-first checkpoint

- Assembler regression test: `ef8044248daf2f109025861d231831f54cd19ca4`.
- Assembler root-cause fix: `cb25247c4dc95ff9f8ae518fe40dd7a52e17d583`.
- Production chapter-preview regression tests: `fb82fe037296c6cdfd330f921fef3d500d4abbab`.
- Production chapter-preview root-cause fix: `37d30f94a8244d0eac87dc6b4601195cf5ff9030`.
- Defect record update: `709b9a708687ba6b7ea7e0723be9212c9e2174aa`.
- Exact matching-head tests and Windows packaging are still unverified. The next candidate checkpoint must use a commit message containing `[artifact-checkpoint]` so the Windows build job is eligible to run.


## Additional 8.2.8 preview coverage

- Full-book preview regression test commit: `bc5429e72e8d8d4857aa91f10925e6cc37d2cc36`.
- Sound Design defect record updated at `b8d7b11699535438b44cb32491af5382a7f7ae09`.
- The latest candidate checkpoint includes all three regression additions and both source fixes. Matching-head CI remains unverified; do not infer success from the older 1,258-test Build #2680.


## Additional Sound Design requirements and current gaps

- Chapter-Based validation test/fix: `9c456dbb18498ec0461ce0391b20045092bcb7c4` / `5b31851b663a9ccadebe3fb36d89e972d067bfd1`.
- Same BGM single-track regression/fix: `ef431137c5850bbae9f88d9f99cec641a6a579c1` / `24cf31f0f6b76ea8e700e0c60ee99bd04835b241`.
- Defect record updated at `998320c29046d6b84b82d578d12704ebcdc93eb6`.
- **Source-level correction verified on #2798:** Production chapter preview now preserves paragraph boundaries when the selected saved Chapter-Based assignment uses `after_first_paragraph`. `build_voice_preview` returns the measured `first_paragraph_end_ms` from actual synthesized preview units; the bridge passes that measured boundary into the chapter BGM mixer. It fails closed if the exact boundary is unavailable or falls after the preview end. This is no longer an unimplemented source gap. Exact-head packaged audio/listening acceptance remains pending.
- Seven regression tests have been added across the Sound Design test commits. None is marked passed until a matching-head run is inspected.


## Latest Sound Design single-track correction

- Same BGM manual single-layer regression and stale-ambience validation test: `a50a5397c691d1c871c49b3c7257d0b56dd3fbec`.
- Chapter-Based No BGM legacy-ambience regression: `6fd085416ab410f0ea27233a45c4dc1be836c33b`.
- Voice-preview single-track regression: `aac289f9f17c4ccdea876b716a6637a50621da19`.
- Source fixes: assembler `fa339850428e16d61d0d028f365d4e0355035c9b`, validation `22fc0238e4ac153e028f843316799a32c3d9f9e7`, voice preview `b7a4f366887f68c13ef7f7f1177a6150ae6719a1`.
- Defect record updated at `dfacf903df912539d44025bddb1a95c8e15d873e`.
- **Updated #2798 status:** individual Production chapter preview now carries a measured paragraph boundary from the generated preview audio and applies it to the chapter BGM mix. The preview intentionally fails closed if the first paragraph is not fully represented or an exact boundary cannot be measured. Regression tests passed on #2798; packaged real-audio listening remains pending.
- Thirteen Sound Design regression tests have been added across the test commits listed in this matrix. No passing matching-head CI result is yet recorded.


## Full-book preview safety gates

- Disposable-copy preservation test: `acc3296f9812692792b976dc3a29b7d7a3db69aa`.
- Cancellation and partial-output deletion test: `a58d9674e7315381a858b643b45b7e578aa6b4ef`.
- Defect/evidence record updated at `36c1dbede72ba52bcf20d95197086020a3a3fedc`.
- These tests cover saved-narration immutability, temporary staging cleanup, cancellation state and partial preview removal. They still require execution in CI.


## Stage 8.2.9 — Premium V2 frontend/backend parity audit

**Source/test head before this checkpoint:** `10d2a0b1b794f3e2f53914d1d358f0b6de2cf136`.

### Static command parity

- Audited the Premium V2 backend adapter against `app/ui/premium_v2_host.py`.
- 108 distinct direct adapter `call(...)` command names were found; all 108 have a matching host handler. No missing direct command names were found in this scan.
- Existing contract tests include adapter/dispatcher command parity, all 15 navigation destinations, production preview integration, storage controls, and performance benchmark separation.
- This is static command/contract evidence only; it does not prove each rendered button works at runtime.

### Dead-end controls and blocked Character Studio actions fixed

- Legacy Settings `Choose Folder` no longer remains disabled with an unsupported-action message. It is relabeled **Manage storage locations** and navigates to the working Settings > Storage tab, where the supported project, audio asset and model roots can be selected.
- The document-level click guard no longer blocks functional Character Studio actions: Accept High Confidence, Skip Suggestion, Use Library, Create New and Quick Create.
- Stale AI queue prototype rows without an exact `data-dialogue-id` are hidden rather than displayed as inert disabled actions. Real source-backed dialogue rows retain their navigation/action path.
- Source commits include `47ec2d2`, `dfc231d` and `2e66456`; the updated contract test is in `10d2a0b`.

**Requirements touched:** CS dialogue review/assignment and manual character actions; MOD storage-root navigation; UI parity and no-placeholder-control acceptance.

**Status:** CODE CHANGED — NOT VERIFIED. The updated contract test and full regression suite must pass on the exact candidate; interactive Windows acceptance must confirm the Settings > Storage navigation and each Character Studio action.



## Stage 8.2.9 — In-app Help & Guide update

**Source/test head before this checkpoint:** `77d35bef5500493cfd1ee35519087ac08e8e9339`.

- Added a task-based in-app Help & Guide renderer to the Premium V2 `#help` destination.
- The guide has searchable, expandable/collapsible topic cards covering Getting Started; Dashboard and Library; Import; Chapters; Voice Studio; Character Studio and Character Library; Pronunciation; Sound Design; Music Library; Production; Audiobooks; History and Background Jobs; Models; Performance; Settings and Storage; Troubleshooting; and Known Limitations.
- It explains the current Same BGM / Chapter-Based / No BGM / Voice Only rules, one-track policy, cue limits, preview durations, Qwen 0.6B/1.7B selection and VoiceDesign model requirement, storage migration, generation recovery, playback and actual benchmark interpretation.
- It explicitly documents scanned/image-only PDF OCR and M4A/MP3 limitations, hardware-dependent acceleration, and the current short chapter-preview limitation for After first paragraph BGM offset.
- Help contract test: `cb2e6f2c24ec9144966732183c244837ca8f27cb`; Qwen setup coverage test: `f2b65cc750d10d6902dc2faa5cdb68cb0b0d794b`.
- Help implementation/content commits: `7e9bcf19ca002af1817cc7c3269767066fcce3d5`, `68c8940d0601630fc1dc021da3ebd59eb8349c70`, `77d35bef5500493cfd1ee35519087ac08e8e9339`.

### Frontend/backend static parity result

At the same source head, a static scan found 108 distinct direct backend command calls in the Premium V2 adapter and 132 host handler keys; all 108 direct command names had a matching handler (zero missing). This is a source-level contract result, not proof of runtime click behavior.

**Status:** HELP-01..03 and the touched UI parity controls are CODE CHANGED — NOT VERIFIED. The Help page must be opened and searched on the packaged Windows app, and each described workflow must be checked against the actual controls before the guide is accepted.


## Final UI responsiveness and flicker acceptance matrix

This matrix is mandatory for the final Windows acceptance pass. Static CSS checks or a maximized-window screenshot do not replace it.

### Aspect-ratio and orientation coverage

- 4:3
- 5:4
- 3:2
- 16:10
- 16:9
- 21:9 ultrawide
- 32:9 super-ultrawide
- Portrait orientation

Use representative native resolutions for each ratio, including narrow and high-resolution layouts where available.

### Window and desktop layout coverage

- Minimized → restored, maximized → restored, repeated resize and rapid navigation.
- Half-screen and quarter-screen snapped layouts.
- Full-screen and normal windowed operation.
- Single monitor, extended monitors and mixed-resolution monitors.
- Mixed-DPI monitor movement while the app is open.

### Windows display scaling

- 100%
- 125%
- 150%
- 200%

### Required observations on every layout

- No clipped, overlapping or unreachable buttons, labels, menus, dialogs, tables, toolbars or playback controls.
- No persistent horizontal overflow; long text, filenames, model paths, errors and metadata wrap or scroll within their own panel.
- Sidebar collapse/expand, page scrolling, nested scrolling, dropdowns, modals, tooltips and keyboard focus remain usable.
- Dashboard cards, Library tables, import/chapter editors, Voice/Character/Pronunciation/Sound panels, Production controls, Audiobook player, History/Jobs, Models, Performance, Settings and Help reflow without losing state.
- Mini-player remains correctly positioned and usable while navigating and resizing.
- No white/black flashes, layout jumps, repeated DOM rebuild flicker, frozen input, lost text edits or WebEngine renderer crashes during resize/navigation.
- Verify repeated navigation and resize cycles, not just a single screenshot.

**Acceptance evidence:** record OS version, display resolution, aspect ratio, scaling percentage, monitor arrangement, window state, screen/module tested, observed result and any defect ID. Any untested combination remains OPEN; do not claim universal responsiveness from one PC or one monitor.


## Stage 8.2.10 — Generation reliability and chapter-preview audit

The current source and contract tests already cover the core PROD/GEN preview and generation flows; no duplicate implementation was added during this audit.

### Production chapter preview behavior traced

- The backend resolves the active project and selected saved chapter, rejects missing/empty chapters and validates the requested chapter ID against the saved chapter identity.
- It uses the project's saved narrator profile, assigned character voices, pronunciation rules and saved Sound Design state; arbitrary transient Voice Studio provider/voice/text overrides are stripped from the Production preview request.
- Preview jobs have a distinct `production-preview` type and independent monitor from full-book generation.
- The chapter selector records chapter number, stable ID and chapter signature. A changed selection invalidates the old preview and requires a new preview for the selected chapter.
- Completion checks the active project folder and requested/returned chapter identity before attaching audio to the player.
- The UI reports real progress, elapsed/ETA data and measured audio duration; the preview is playable and has a separate Save/Download action.
- The backend Save handler accepts only a completed Production preview belonging to the same project and chapter, verifies the exact output path under the preview directory, and opens a native Save As dialog.

### Existing automated coverage

- `test_production_generation_and_preview_use_independent_job_monitors`
- `test_production_preview_uses_saved_sound_design_and_reports_selected_mix_configuration`
- `test_production_preview_reports_real_progress_timing_and_measured_duration`
- `test_production_preview_is_a_typed_cancellable_job_with_real_chapter_identity`
- `test_production_preview_selector_creates_status_and_keeps_selected_chapter_before_job`
- `test_production_preview_completion_uses_native_project_and_optional_chapter_id_identity`
- `test_production_preview_save_is_separate_from_voice_studio_save_and_validates_job_scope`
- `test_production_pronunciation_and_sound_design_state_are_saved_before_preview_and_full_generation`
- Existing regression coverage also includes generation cancel, pause/resume at safe chapter boundaries, atomic resume state, completed-chunk reuse, empty-chapter handling and M4B packaging/progress.

**Status:** source/contract coverage for PROD-05..09, PROD-15 and related GEN requirements passed the matching-head Build #2798 regression suite (1,314 tests). The previous #2768 frozen-app run also passed real selected-chapter preview, playback, Save As, 30/60/90-second measured audio, cancellation, full-book generation, M4B chapter metadata, playback, pause/resume/retry/recovery and 41-viewport emulation on its older commit. The current #2798 candidate still needs its own packaged run. Human listening, actual After first paragraph BGM audio, and target-device behavior remain pending.


### Generation retry/recovery safety tests added

- Test file: `tests/test_stage6_history_task_manager.py`.
- Test commits: `53ad60d0ff7ec1590b0017ccb31e5b4d176832d3`, `a1f9a401f1c39e002c00b361e78da5c357812096`, `9c6f89011f03959e22b0f6c1db4206e5672c32ac`, `7abd79f5b3a5701cc8e9f1f9654f7421adb8c3ba`.
- Six new tests cover failed-job retry lineage/count, interrupted-job recovery lineage, rejection of non-recoverable and non-generation jobs, rejection of non-interrupted/unflagged recovery, protection against a newer generation owning the project, and prevention of a second active generation for the same project.
- These tests exercise the existing host retry/recovery guards; no source change was made in this audit.
- Matching-head test execution remains pending.


## Stage 8.2.11 — Windows package-size investigation

### Verified Build #2677 baseline

The small SHA-256 manifest artifact from Build #2677 was downloaded and inspected. These are exact file sizes and hashes from commit `e71c16b980c0dd1a669028761a9152ae246a6b0a`:

| Package file | Size (bytes) | SHA-256 |
|---|---:|---|
| HTML Setup.exe | 884,807,898 | `f3548de6d50b612b48a802df3c56580a763d746aa16980aa46c1713cc6abc407` |
| Core Setup.exe | 657,915,759 | `ed3c1165c367e535da8a4640c7b1720be02026dd897885708e1bb3cf6926c44b` |
| Main application EXE | 12,151,399 | `634265e02bc7aea789077adb4de68dbc9837eecb8d3a522e84a74e7da18e842d` |

- The HTML installer is 226,892,139 bytes larger than the core installer (about 226.9 MB size delta). The wrapper is built as a separate PySide6/QtWebEngine application and embeds the core installer; this is a strong optimization candidate, but the delta is not yet a per-file attribution.
- The portable artifact was 1,368,242,573 bytes. The installer artifact ZIP was 884,808,062 bytes, effectively the size of the single Setup.exe.
- The 500 MB target (500,000,000 bytes, decimal) is not met by the core installer, HTML installer or portable artifact.
- The Qwen integration smoke model is downloaded to the Actions runner temporary directory, not intentionally bundled into the application payload.
- Offline Piper/Kokoro model assets, QtWebEngine, ONNX runtime components and starter audio are intentional product dependencies. No required assets have been removed.

### New size-profile evidence

- Added `package_size_report.py` to report the frozen application total, file count, top-level directories, largest 50 files, offline Piper/Kokoro/starter-audio sizes, runtime component directories, installer sizes and the payload metadata.
- The reporter supports PyInstaller's root and `_internal` asset layouts and uses a decimal 500,000,000-byte target.
- Added a regression test for component accounting and a Premium V2 contract test requiring the report to be generated and uploaded with the release SHA manifest.
- The Windows workflow now generates `package-size-report.json` and includes it in the release manifest artifact. This report will be available only after a successful matching-head build.

**Status:** baseline size target FAILED; attribution and optimization are IN PROGRESS. Do not delete offline models, runtime providers, licensed starter audio or other required assets to force the target. First inspect the new per-file report; then evaluate safe options such as removing duplicated installer UI runtime or making genuinely optional providers/assets separately installable without losing offline capability.


## Stage 8 exact-HEAD CI checkpoint — 2026-11-07

- Candidate source commit: `f46f74ddd95cc2499deee342bceeefb14877ae28`.
- Windows Actions run #2757: `42354876609` — **SUCCESS**.
- Completed gates: Python dependency installation; Premium V2 adapter, installer and packaged Sound Design JavaScript syntax; isolated native Qt lifecycle regression; focused Stage 6 History/Task Manager preflight; complete remaining regression suite.
- The workflow's `build` job was intentionally skipped because this commit did not contain the `[artifact-checkpoint]` marker. Therefore this run is regression evidence only, not installer/portable package evidence.
- Next exact-candidate action: create a documentation-only `[artifact-checkpoint]` commit, then verify the dependent Windows build and artifact jobs on that new exact HEAD. Do not transfer the #2757 test result to a different commit without rerunning its required gates.


## Build #2758 evidence reconciliation (2026-11-07)

The successful exact-source checkpoint is preserved as historical evidence; it is not discarded or superseded by later regression-only commits.

- Build #2758 exact source: `48436fa0f84e3d011cfe93dc6154d10fbe65ab11`.
- Regression job: 1,280 tests passed.
- Windows package job: succeeded; HTML installer/portable artifacts and SHA manifest were uploaded.
- Frozen-app acceptance passed for the integrated Sound Design/Music Library/Production/Generation/Player/History/Task Manager workflows listed in the CI baseline record.
- 41 viewport emulation cases passed; OS-level multi-monitor/DPI/minimized-window checks remain pending.
- Application metadata in this build: Version 1.1.1. It is not the final Version 1.2.0 candidate.
- Evidence detail and hashes: `docs/stage-8/STAGE-8-2-7-CI-BASELINE.md`.

### Evidence status policy applied

The 128-row requirement inventory is a requirement ledger, not a count of tests. A green full suite does not automatically mean all 128 rows are complete. For a row to advance:
1. Use a matching test/build commit after the relevant code change.
2. Identify a behavioural test or packaged interaction proving the actual requirement; static presence checks alone are insufficient.
3. Keep physical listening, target PC/GPU, manual DPI/monitor and user-observed workflows in `RUNTIME ACCEPTANCE PENDING` until that evidence exists.
4. Record run number, commit, gate, observed result and remaining gate in the row.

The #2758 run supports automated/package evidence for the Sound Design, Music Library, Production, Generation, Player, History/Task Manager, installer and responsive-emulation requirements exercised by that run. It does not prove all requirement rows, all visual screens, audio quality by human listening, target hardware, or 1.2.0 release metadata. Per-row changes are intentionally made only when the associated tests can be mapped without ambiguity; do not bulk-mark the inventory complete.



## Current exact-head reconciliation — 7 November 2026

### Build #2798 — latest source regression checkpoint
- Branch: `stage-7/step-6-safe-auto-fallback`.
- Exact HEAD: `7e8a20fdc9d812f558060f30b31faee49305f6a0`.
- Run: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42372464405
- Regression job: **SUCCESS — 1,314 tests passed** (50.297 seconds).
- Frontend JavaScript syntax, isolated native Qt lifecycle regression and focused Stage 6 History/Task Manager preflight passed.
- Windows build job: **SKIPPED**, not failed. This source commit did not contain the workflow's `[artifact-checkpoint]` marker.
- Therefore #2798 is the latest matching-head source regression pass, not a Windows installer/portable build.

### Failure reconciliation before #2798
- #2795 and #2796 failed the full regression step with four contract assertions: three still expected 1.1.1 after the branch had been prematurely changed to 1.2.0, and the Premium V2 capability map lacked the newly registered `import.latest.get` handler.
- The capability-map defect was corrected before #2798. The version assertions were changed to 1.2.0 at that time, but that conflicts with Master Register Sections 0, 21 and 23, which gate the version bump on final acceptance.
- This follow-up restores the required 1.1.1 version gate and re-aligns the four version contracts. The next matching-head regression run must confirm this correction. No functional test is being weakened.

### Changes already present on this branch — preserve, do not redo
- Persistent latest-import record and Import page card with an Open imported project action.
- Character chapter-split handling that preserves/rebases only valid assignments and invalidates stale offsets when editor text differs from saved source; deletion refuses to orphan saved dialogue assignments.
- Measured Production chapter-preview paragraph boundary support for Chapter-Based BGM.
- Fifteen Premium V2 sidebar destinations including Help, searchable Help & Guide content, and packaged acceptance checks for Help search/no-results/expand/collapse.
- Version gate correction: keep APP_VERSION at 1.1.1 until all required acceptance gates pass; 1.2.0 remains the planned final release version only.

### Previous packaged checkpoint — Build #2768
- Exact commit: `9ff9bc05d70444c375c692839d2e8346d34b70cf`.
- Run: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42365316494
- Regression suite: **1,293 tests passed**.
- Windows package job: passed, including frozen-app verification, installer/portable creation, Microsoft Defender, SHA-256 manifest and artifact upload.
- Frozen-app acceptance logged 97 passing checks, including Sound Design/Music Library, real full-book mix previews, selected-chapter Production preview and Save As, 30/60/90-second measured previews, real multi-chapter generation, M4B chapters, player/mini-player, pause/resume/cancel/retry/recovery, persistence and 41 responsive viewports.
- Installer artifact: `Ryu-Audiobook-Installer-2768`, 846,239,172 bytes.
- Portable artifact: `Ryu-Audiobook-Portable-2768`, 1,183,224,790 bytes.
- SHA manifest artifact: `Ryu-Audiobook-Release-SHA256-2768`, 3,046 bytes.
- Piper benchmark artifact: `Ryu-Audiobook-Stage7-Piper-Benchmark-2768`, 803 bytes.
- Artifacts expire 7 December 2026. The packaged app version was 1.1.1; this package predates the current 1.2.0 source updates and must not be handed out as the latest candidate.

### Current package and acceptance decision
The next workflow run is intentionally requested with the `[artifact-checkpoint]` marker. It must run both the full regression suite and Windows package job against the new exact HEAD. The resulting artifacts must be downloaded from that same run. Do not use #2768 artifacts as substitutes for the current candidate.



## REL-01 — Live PR recheck at Build #2798 HEAD

Rechecked against current open PR metadata and GitHub commit comparisons with working HEAD `7e8a20fdc9d812f558060f30b31faee49305f6a0`:

| PR | Current GitHub state | Comparison result | Decision |
|---|---|---|---|
| #15 | Open, draft | PR head is an ancestor of current branch (0 commits behind). | Already in current lineage; do not merge again. |
| #19 | Open, draft | PR head is an ancestor of current branch (0 commits behind). | Already in current lineage; do not merge again. |
| #20 | Open, draft | PR head is an ancestor of current branch (0 commits behind). | Already in current lineage; do not merge again. |
| #18 | Open, ready | Diverged; PR head has 27 commits not in current branch. | Do not merge wholesale. Compare its Character Inspector behavior with the current evolved Premium V2 Character Studio implementation and port only a proven missing behavior. |
| #26 | Open, ready | Diverged; PR head has 43 commits not in current branch. | Do not merge wholesale. Current branch already has recoverable project trash, Character Library bridge behavior and the newer latest-import status card; verify remaining parity before deciding whether any isolated change is missing. |
| #4 | Open, ready | Diverged; PR head has 2 commits not in current branch. | Current Voice Studio contains equivalent Qwen preset draft-reset behavior. Do not merge blindly; keep only if a distinct tested behavior is missing. |

**REL-01 disposition:** duplicate merges are not required for #15/#19/#20. #18/#26/#4 remain open dependency reviews, not permission to merge entire branches. No unrelated PR was merged during this checkpoint.



## REL-07 version-gate correction — 7 November 2026

The #2790–#2798 branch history changed `APP_VERSION` to 1.2.0 before the full release acceptance gates had passed. This conflicts with the Master Register's explicit versioning rule. The current candidate must therefore remain **1.1.1** while friend/Windows acceptance and remaining Stage 8 requirements are completed. The planned 1.2.0 version is to be applied only after acceptance, on the exact accepted source commit, immediately before the final installer/portable release build.

The following contracts are restored to 1.1.1 for the candidate:
- `tests/test_audiobook_brain.py`
- `tests/test_regressions.py`
- `tests/test_ui_stability_111.py`
- `tests/test_application_version_contract.py`

The `1.2.0+build.test` fixture in package-size-report tests is test data, not the application's release version, and is intentionally unchanged.

 
## XAPP-08 — Narrator-only Generation implementation overlay (8 November 2026)

- Narrator-only routing is an explicit per-book opt-in (`narrator_only_generation`); zero character profiles no longer silently activate it.
- The setting is saved in the active book's project state and defaults off when absent. The Production checkbox persists the setting for the selected book and validates active-project ownership before accepting the save.
- Enabling narrator-only mode resolves the saved book narrator override or inherited series default. Missing or unavailable narrator profiles continue to block generation.
- When enabled, every source passage (including quoted/dash-led dialogue) uses the saved narrator and cast routing is bypassed. When disabled, normal cast-aware speaker-review validation runs, even when no character voice profile is assigned.
- Production chapter preview reads the same saved mode and bypasses cast routing when enabled. Full generation records the effective mode in the project/job state.
- Full-generation persistence coverage now also asserts that the saved book state and the durable job/launch result expose `generation_mode` and `narrator_only` for the chosen mode; the cast-aware Stage 5.3 path must explicitly remain `character_cast` when the toggle is off. Narrator-only-specific runtime acceptance remains open: generate/listen to the full book, inspect M4B metadata/chapter playback, and test interruption/cancel/retry/resume on packaged Windows under XAPP-08/13.


### XAPP-08 — Full-generation cast isolation correction (8 November 2026)

- Source review found that the original explicit narrator-only resolver and Production preview bypass were not sufficient: full-book Production still resolved saved character profiles and could wrap the narrator provider with `CastAwareProvider`.
- The full-generation path now skips character-profile resolution and cast-provider construction when the persisted per-book narrator-only flag is enabled. This means unavailable character profiles cannot block narrator-only generation, and the only TTS identity passed to the generation manager is the saved narrator.
- A Stage 5.3 production-path regression now creates a narrator-only book with a saved character voice assignment and asserts that the generation manager receives the saved narrator-bound provider, no cast router, and narrator-only state/mode in the project state, job result and launch response.
- The normal cast-aware path remains covered and must continue routing character dialogue to assigned profiles when narrator-only is off.
- This is automated source evidence only until a matching-head Windows regression/package run and actual full-book audio/M4B acceptance complete.


## Recovery-reentry evidence overlay — 9 November 2026

This overlay updates the evidence available after the historical #2950/#2929 snapshot. It does not delete prior failed attempts or close requirements that still need packaged Windows, target-device, actual-book or audible acceptance.

### Exact-head automated evidence

| Area | Implementation / matching run | Automated result | Remaining boundary |
|---|---|---|---|
| GEN-07 / XAPP-08 narrator-only generation | `f4ff2c65136e4115a73dcb7794bfe358a38f45b8`, [#2981](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42548580031) | 1,436 tests passed; frontend syntax, native Qt lifecycle and 45 focused tests passed. | Frozen Windows package, real narrator-only full book, M4B/playback and recovery listening. |
| XAPP-03 / XAPP-12 canonical dialogue readiness | `3fb5c83cb8265b5b30ec9028de0de3c58fa17d30`, [#2982](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42548740386) and `b9ce3be284718a03edabaeecf9e788cfb35c1084`, [#2983](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42548758031) | Both exact-head runs passed 1,436 tests and the 45-test focused preflight. Production summary reports the canonical revision-aware passage index; Dashboard and Production generation gates consume backend-derived review/readiness state. | Reconcile actual-book passage counts and inspect Character Studio/Production live in the frozen Windows app. |
| XAPP-05 / XAPP-06 profile and legacy Qwen backend migration | `f13c14380551a487aa6e6511d46bfe11ddd22ec5`, [#2970](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42547124660) | 1,433 tests passed. Invalid legacy Qwen backend values are normalized and persisted atomically; valid explicit compute backends are preserved; profile saves normalize as well. | Confirm saved profile migration on a real existing user catalogue and restart. |
| XAPP-09 responsiveness | #2981–#2983 focused checks | 45 UI/History/Task Manager preflight tests and native Qt lifecycle check passed on matching source. | Large target-PC catalogue scan while preview/generation are active, real UI freeze/flicker and multi-monitor/DPI acceptance. |
| PROD/GEN durable generation lifecycle | #2981 cumulative regression | Current 1,436-test suite includes generation job identity, History/Task Manager and recovery/control regression coverage. | Current-head packaged interruption/retry/resume/cancel and full-book acceptance. |
| PS / SD / MUS / AB | Existing Stage 5/Stage 8 regression and prior package records retained | Configuration and renderer regressions remain in suite; Stage 5.5 historical M4B/AudioBooks package checkpoint #2253 remains historical accepted evidence. | Current-head frozen app, actual listening, language pronunciation quality, Sound Design/BGM/cue mix parity and chapter playback/seek. |

### Narrator-only and shared-readiness rules now enforced

- Narrator-only mode is an explicit per-book setting and requires **zero valid configured character voice profiles**. A saved but unavailable/deleted character-profile name is not counted as a valid profile.
- Adding a valid character profile after narrator-only is enabled makes the resolver persist narrator-only OFF and return to strict multi-character speaker review. Production and the Dashboard both fail closed while the stale flag remains inconsistent.
- Production Preview and full-book generation use the same saved narrator/mode resolver. Narrator-only preview disables character-cast routing.
- The immediate generation response, project state and durable job result carry the same narrator-only flag, generation mode and valid character-profile count.
- Production readiness uses the canonical revision-aware passage index and exposes pending/conflicting passages, index issues, assignment issues and index revision. Dashboard and Production gates consume these backend-derived readiness fields; the legacy “prepared” percentage retains its previous meaning and is not repurposed as the hard generation gate.

### Hardware and performance acceptance remains open

- The dedicated NVIDIA and AMD/Intel Qwen acceptance workflows must produce real device/backend/inference/timing artifacts. The green #2952/#2953 regression workflows are not physical-GPU benchmark proof.
- The historical Qwen 1.7B CPU previews of roughly 268–305 seconds do not meet the 30-second-preview-under-60-second target. No matching-head physical NVIDIA, AMD ROCm or Intel XPU result currently proves that target.
- Runtime selection and accelerator-install policy regressions cover supported CUDA/ROCm/XPU candidate detection and guarded runtime activation/fallback. They do not replace the real hardware benchmark.

### Integration and release boundary

- Current working branch at this overlay: `stage-5/xapp08-recovery-reentry-2026-11-08`.
- At recovery head `3c8eb6270160820978bad7c2931112a00bdc516b`, the branch compares as 113 commits ahead and zero behind PR #31's head `82a39ffa2b54b8ce7cab5468affde0cbaf02db0e`; PR #31 remains open and draft. The recovery branch is already stacked on that integration candidate; do not create a duplicate branch or merge the PR's existing lineage into itself.
- Current recovery-reentry code has passing matching-head regression evidence but no new exact-head frozen-Windows artifact checkpoint yet. Do not call the present branch a release candidate, publish 1.2.0, or mark the frozen Master inventory complete.
- Requirements that still call for actual-book inspection, physical hardware, human listening, installed-app navigation, display/DPI or a fresh packaged Windows artifact remain **RUNTIME ACCEPTANCE PENDING** or **OPEN**, even where their code regressions pass.

## 9 November 2026 — GEN-07 narrator-only active-project closure

**Working branch:** `stage-5/xapp08-recovery-reentry-2026-11-08`  
**Exact source head before artifact checkpoint:** `6e696bbe6f5f61a1c5ca21c8fd8f2b29636bc8fd`

### Defect and test-first evidence

The packaged GEN-07 flow exposed a real cross-project UI state defect. The narrator-only checkbox is created once and reused across project navigation, but its original change handler closed over the `project` object from the first render. After switching projects, the displayed project could be current while that retained handler still sent the first project's folder. The backend's `expected_project_folder` ownership guard correctly rejected the stale request; that guard was not weakened.

- **Build #2994** — commit `7e40fcac1c0ac752598f3c1dcc22d2e8a08d226b`: test-first regression failed as intended. **1,438 tests ran; exactly the new stale-project listener assertion failed.** [Actions run](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42554088864).
- **Fix commit** — `6e696bbe6f5f61a1c5ca21c8fd8f2b29636bc8fd`: the handler now reads the currently displayed active project and independently reads the native `project.get_active` identity at interaction time, normalizes Windows path spelling, sends the verified active folder to the backend, verifies the saved folder, and updates the live project summary. The handler no longer depends on the first-render `project` closure.
- **Build #2995** — exact fix head `6e696bbe6f5f61a1c5ca21c8fd8f2b29636bc8fd`: **1,438 tests passed**, including the new regression; the 45-test focused Stage 6 preflight, native Qt lifecycle step and frontend JavaScript syntax step passed. [Actions run](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42554340947).

### Acceptance boundary

Build #2995's Windows packaging job was skipped by the feature-branch workflow condition. It produced no Windows installer/portable artifacts. Therefore this overlay records **AUTOMATED TESTS PASSED** for the listener correction, not packaged Windows acceptance or final GEN-07 completion.

The next `[artifact-checkpoint]` run must execute the frozen Windows executable, full packaged Sound Design acceptance (which includes the GEN-07 narrator-only full-book fixture), installer/portable build, install/upgrade/uninstall and user-data preservation checks, SHA-256 manifest generation, and artifact-to-commit verification.

Even if that run passes, the user's actual saved book, installed-PC full-book listening, real interruption/recovery, and physical Qwen CUDA/AMD/Intel/iGPU benchmarks remain separate acceptance gates. This correction does not close unrelated P0/P1 requirements or authorize Version 1.2.0 release.



## 9 November 2026 — GEN-07 packaged project-summary persistence correction

**Active branch:** `stage-5/xapp08-recovery-reentry-2026-11-08`  
**Failing packaged checkpoint:** Build #2996, source head `807f17337a366639cd23aa4a0ee4c5781ebe6215`  
**Regression:** `d3a89ea475b816a969a2ae65cd0ed94600ec7f1a`  
**Source correction:** `e8885c010eba64c92eba604bec2f246a2fa8f626`

Build #2996 passed 1,438 regression tests, frozen application startup and bundled asset checks. Its real packaged Sound Design/Music Library acceptance generated the narrator-only book, and the durable job and History assertions passed. The final owning-project assertion failed because the project summary did not return `character_voice_profile_count`, even though generation completion persists that immutable per-generation value in `state.json`. The summary already exposed a separate `configured_character_voice_profile_count` derived from the current saved character assignments; that is not the same field as the generation snapshot asserted by GEN-07.

The added regression requires the active-project summary to return the persisted `generation_mode`, `narrator_only_generation`, and `character_voice_profile_count`. The fix exposes the saved count with non-negative integer normalization and falls back to the currently configured count for older projects without a generation snapshot. It preserves the existing derived configured-cast field and does not weaken job ownership, output validation, or readiness guards.

**Status:** code and regression committed; matching-head full tests and packaged Windows acceptance are pending. Build #2996 produced no installer or release artifacts because the package gate correctly stopped at the failed acceptance. Actual saved-book listening, user-PC performance, physical Qwen device tests, and display/DPI acceptance remain pending.


## Cross-App Addendum — XAPP-01 through XAPP-20

The Cross-Application Defect Closure & Integration Addendum supplied with this continuation remains authoritative for full requirement text, acceptance criteria, viewport coverage, and workflow order. This status ledger supplements that text; it does not replace it. A code/test result does not satisfy installed-app, saved-book, real-audio, physical-device, or user-PC acceptance.

| ID | Priority | Current evidence and remaining closure |
|---|---:|---|
| XAPP-01 | P0 | Character-analysis pipeline and regression coverage exist; actual-book, cross-chapter identity/alias quality and user correction acceptance remain pending. |
| XAPP-02 | P0 | False-positive rejection and exclusions have code/test evidence; audit the user's existing cast against the actual book and verify dismiss/correction persistence. |
| XAPP-03 | P0 | Revision-aware persisted passage index and automated tests exist; reconcile actual dialogue counts and assignments in the saved book. |
| XAPP-04 | P0 | Full-text chapter navigator/passage review code has regression coverage; verify large-book navigation and review in both modes in the packaged UI. |
| XAPP-05 | P0 | Profile assignment and routing code/tests exist; verify each saved character voice through preview and final output after project restart. |
| XAPP-06 | P0 | #2970 recorded 1,433 passing tests for persisted legacy Qwen backend migration; verify migration against an existing user catalogue and restart. |
| XAPP-07 | P0 | Backend selection and benchmark paths exist; real CustomVoice, VoiceDesign and Clone inference/device evidence, per-device timings and preview target remain pending. |
| XAPP-08 | P0 | Build #3006, attempt 3, passed exact-head regression and packaged Windows acceptance at `9da241b`, including automatic zero-profile narrator routing, persistence, Sound Design/Music Library UI, installer, portable app, Defender scans and install/launch/upgrade/uninstall. Actual saved-book generation/listening, interruption recovery and user-PC acceptance remain open. |
| XAPP-09 | P0 | Async catalogue and responsiveness regressions are present; verify target-PC responsiveness under concurrent scan, preview and generation workloads. |
| XAPP-10 | P1 | Durable job state/control paths have automated coverage; verify truthful progress, cancellation and restart recovery in the installed app. |
| XAPP-11 | P0 | Saved narrator/profile identity paths have automated coverage; verify profile assignment, reopen, audition and final narrator consistency on a real saved project. |
| XAPP-12 | P0 | Shared readiness/index calculations have automated coverage; reconcile every readiness indicator against actual dialogue records and book counts. |
| XAPP-13 | P0 | Recovery, retry, pause/resume and cancellation code/tests exist; run actual interrupted generation and recovery on packaged Windows and validate output. |
| XAPP-14 | P1 | Assignment/statistics/source-display code has tests; verify exact Assigned Cast metrics, highlighting and persistence against the actual book. |
| XAPP-15 | P0 | UI/backend contracts exist; complete the Addendum's full visible-control audit across all screens, including persistence and restart behavior. |
| XAPP-16 | P1 | Dashboard/workflow active-project paths have tests; verify project identity and saved state across every cross-screen route in the packaged UI. |
| XAPP-17 | P1 | Help & Guide source exists; verify search, navigation and functional parity against the final integrated package. |
| XAPP-18 | P0 | PR #31 remains open/draft with no inline review threads. Recovery head `3821ff1` compares as 119 commits ahead and zero behind PR #31 head `82a39ff`; preserve this lineage and reconcile candidate dependencies before release. |
| XAPP-19 | P1 | Build #3006 produced installer, portable app and SHA manifest for exact candidate `9da241b`; packaged install/launch/upgrade/uninstall and user-data preservation passed. Artifacts: installer `13652403526` (ZIP SHA-256 `9566e5ee21e99a81d6884f210a477ff5cb9ccc7222e22ca231efa9cfb564e148`); portable `13652019833` (ZIP SHA-256 `6995f68965aea86b9360bd89110b7b06f107844cc47a849422a89e36d9edff6d`); manifest `13652537878` (ZIP SHA-256 `6a3ccc44e492ec8312d2ff039988e3b5dac39d6ecbd474049ab27dc6575a8f90`). Installer payload SHA-256 `871035e7399a0f48620576bc3b52692279877655441fea68b82a9a89bed0eb60`; portable application EXE SHA-256 `08df61e94824c6dc8cb8babd3537d5c1b16868796897c8865822f446d1552978`. This is a 1.1.1 candidate, not the final 1.2.0 release. |
| XAPP-20 | P0 | Full integrated user-journey set remains open until matching-head tests, packaged Windows gates and all required runtime evidence are recorded together. |

**Global acceptance still pending:** user-PC saved-book analysis/generation, real listening, actual interruption/recovery, physical Qwen hardware and task-specific performance, target-PC responsiveness, supported display/DPI/multi-monitor behavior, complete accessibility/layout review, current-head installer/portable parity, and release gates. Do not mark Version 1.2.0 complete without the original Master Register's evidence requirements.


## 9 November 2026 — GEN-07 packaged Audiobooks playback-flow correction

**Source candidate:** `3c8eb6270160820978bad7c2931112a00bdc516b` on `stage-5/xapp08-recovery-reentry-2026-11-08`.

Build #3000 passed the full 1,438-test regression job, frozen application verification and bundled voice/module checks. The packaged Sound Design/Music Library acceptance also passed the GEN-07 generation, durable job and History checks, owning-project snapshot, narrator identity, M4B metadata and output ownership. It then failed waiting for narrator-only playback because the harness navigated to Audiobooks and waited for audio to start without opening the generated-book card or pressing Play. The product's Audiobooks flow deliberately loads a selected book paused and requires its explicit Play control; the same real workflow was already exercised for the recovered-generation fixture.

- Test-first guard commit: `2e5c3708d840e05f19216ab2e4b9b3a0d02a220d`. Build #3001 surfaced an incorrect test-source anchor in that guard (one contract-test error); it did not exercise or reveal a product regression.
- Correction commit: `3c8eb6270160820978bad7c2931112a00bdc516b`. The fixture now locates the owning audiobook card, invokes Open, verifies the loaded paused media source belongs to the expected generated M4B, reacquires the live card after its render, clicks Play, and verifies actual playback remains on that same audio element. The contract test protects these UI actions and project/output identity assertions.
- Build #3002 passed **1,438 tests** on the corrected source head; packaging was skipped because this was a normal fix commit.

**Status:** the playback-flow correction is automated-test verified. Build #3006 at exact source head `9da241b` passed the full packaged acceptance and Windows installer/portable pipeline. Actual saved-book listening, target-PC performance, physical Qwen device tests, and display/DPI acceptance remain pending.

## 9 November 2026 — Build #3006 exact-head package acceptance

**Exact candidate:** `9da241b87d3aa6e2f34b7c6d2569d3efa7794e88` on `stage-5/xapp08-recovery-reentry-2026-11-08`.

[Build #3006](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42566008930), attempt 3, passed both jobs on this exact source head. The regression job ran **1,438 tests**. Packaged Windows acceptance passed the auto-enabled narrator-only full-book fixture, Sound Design/Music Library and Stage 5.3 Production acceptance. The installer pipeline passed frozen-app/module checks, native and HTML installers, install/launch/upgrade/uninstall, user-data preservation, SHA-256 generation, Defender scans (no threats reported), and portable upload. Release publication was skipped by the repository's release gate.

Artifacts and payload checksums are recorded in XAPP-19 above. The packaged application is still **1.1.1**. This proves a current recovery-branch package candidate; it does not close the actual saved-book, physical Qwen hardware/performance, human listening, supported DPI/display, user-PC installation, or 1.2.0 release gates. The user requested setup on their PC; perform that only against an accepted package and after action-time confirmation.

## 9 November 2026 — packaged control-overlap check and download recovery

Build #3007 stopped at JavaScript syntax validation because the large acceptance file was uploaded through a truncated base64 read. The exact source was restored; this was a file-transfer mistake, not an application failure. Build #3008 then passed **1,439 regression tests**, including a new packaged check that measures independent interactive-control overlap across all 15 page destinations at 1280×720. Its build job stopped before freeze and packaged acceptance because the official llama.cpp release download returned HTTP 504 after retries.

To keep the real Qwen integration smoke intact, the workflow now has a second official GitHub release-asset route and validates the published SHA-256 (`1110e183589e0e2ac5b365fb5c3c4a7e149e0760c1989cac18ee426b08e5813a`) before expanding the llama.cpp CPU archive. The next exact-head checkpoint must pass the full suite, download validation, packaged acceptance, and installer/portable gates. The prior #3006 1.1.1 artifacts remain the latest successful exact-head package; there is no verified package of the new overlap/download-recovery source yet.

## 9 November 2026 — User-confirmed zero-profile narrator default

The user explicitly selected automatic Narrator-Only Mode whenever a project has zero valid configured character voice profiles and a valid saved narrator. This governs 1.2.0 and supersedes the historical “explicit per-book setting” wording above. The UI starts enabled in this state and persists a user's explicit opt-out; adding configured profiles returns to cast-aware routing. A missing narrator still blocks generation. The test-first behavior commit `acd020ee7d3b60b685a62d53d7fde54a33836f70` produced the expected failures against prior explicit-only behavior in Build #3004. Source fix `71cb5cd1bdf33ffce495fe0185584e2fcfcd0042` passed behavioral tests after two stale test expectations were corrected. Matching-head regression and packaged acceptance then passed in #3006 at `9da241b`.

## 9 November 2026 — authoritative pasted registers added

Byte-exact copies of the user's 9 November pasted Master Bug & Change Register and Additional UI Continuation are preserved under `docs/stage-8/source-registers/`. The continuation contributes five stable IDs absent from the prior matrix: CS-09–CS-12 and GEN-07. The inventory now records 133 Master/continuation IDs plus all 20 Cross-App Addendum IDs. Existing requirements and completed stages are retained; the source texts remain unchanged.


## 9 November 2026 — Build #3009 packaged Models Center overlap

Build #3009 passed its regression job but failed packaged acceptance on attempt 2: at the restored 1366×768 viewport, Models Center had overlap between model folder/path actions and adjacent Verify files / Open Voice Studio controls. Attempt 1 also timed out in Production chapter selection. The current fix confines model actions to wrapping flex rows with bounded button widths; the packaged all-page overlap assertion remains enabled. Build #3010 must confirm the actual UI geometry and finish every install/portable gate before any release claim.


## 9 November 2026 — Build #3010 and Production selection race

Build #3010 passed the regression job, including the new Models Center action-wrap contract. Its package job was skipped because the push did not carry the workflow's `[artifact-checkpoint]` marker; it produced no package evidence. Review of #3009 attempt 1 showed Production preview chapter selection reverting to Chapter Studio's selection after a live saved-chapter refresh, while attempt 2 independently found the Models Center overlaps. The selector now retains a still-valid explicit Production chapter when refreshed title/text/identity changes, while invalidating stale preview audio. Build #3011 is the packaging checkpoint for both fixes; exact-head package gates remain pending.


## 9 November 2026 — Build #3011 packaged overlap follow-up

Build #3011 passed all 1,442 regression tests and frozen executable checks. Packaged acceptance passed Production chapter selection after the refresh-state fix and generated the Stage 5.4 full-book and retry M4B fixtures. It then detected a remaining 16×9-pixel control overlap at 1920×1080 between a Models Center `Copy path` button and the installation queue's `Clear completed` button. The overlap assertion remains strict; its failure report now includes both control bounds and model-card ownership. Next exact-head checkpoint must use that geometry to correct the layout, then complete installer, portable, scan and hash gates.
