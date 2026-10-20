# Stage 1 Gap Register — Ryu's Audiobook Premium V2

**Updated:** 20 October 2026
**Audited code:** `eca9cf1a8330e2dcfce697f66233a73740e25ae0`
**Working branch:** `fix/import-qa-speaker-hover-hardware`
**Rule:** status is based on source inspection or named test evidence. A registered handler or successful build alone does not mean the user-facing workflow is accepted.

## P0 — correctness risks before production acceptance

| ID | Gap / evidence | Required closure | Roadmap stage |
|---|---|---|---|
| G-01 | The authoritative HTML still contains static sample project/job/cast content, legacy prototype functions and timer-driven behavior (`simulateImport`, generation/model/benchmark renderers, `setTimeout`/`setInterval`, and some `localStorage` usage). The adapter intercepts/guards selected actions but not every visible control has been proven to avoid prototype success paths. | Build a per-control event map; remove or neutralize only the demo behavior that conflicts with backend behavior, without changing the approved appearance. Add tests ensuring unsupported controls never mutate fake data or announce success. | 1, 5, then regression in 10 |
| G-02 | Chapter editor operations are incomplete across the UI/bridge contract. Handlers include list/update/clean/add/delete/reorder/split, and Stage 2 now exposes add/rename/delete/move/merge through a contextual chapter-list action menu without adding always-visible controls. Merge preserves dialogue-assignment offsets and the adapter flushes pending edits before structural actions. Persisted human review state and the Review filter are connected. Explicit skip-for-generation state now persists per chapter and is honored by book generation; find/replace, undo/redo and re-detection protection remain incomplete. The Clean Text button previously bypassed the backend cleaner; Stage 2 now routes it through `chapter.clean`, which uses `clean_import_noise` and reports the number of removed likely page-noise lines, with a contract assertion. | Test extraction and cleanup with reproducible books; wire supported edit operations, preserve manual edits and persist review/skip/exclusion state or document unavailable actions honestly. | 2 |
| G-03 | Character Studio differentiates saved cast operations from prototype per-line AI recommendations. Adapter explicitly says per-line AI suggestions are prototype-only and speaker-line assignments are not persisted. | Persist chapter/project-scoped speaker assignments; distinguish detected dialogue from inferred/confirmed speaker; show confidence and explicit narrator fallback; prove assigned profiles reach synthesis. | 3 |
| G-04 | Voice UI/profile selection and preview use real bridge operations, but actual provider/profile/voice ID/model/settings and requested duration require end-to-end verification on the installed app. | Add request-contract tests for saved profile and 10/30/60-second UI targets, actual returned duration and audio playback. Test 10/20/30/45/60 where the backend supports them. | 4 |
| G-05 | Production has generate/preview and basic job controls, but no complete dedicated preflight, retry/rebuild/history-detail API. Durable job rows are not proof of worker checkpoint recovery. | Run short multi-chapter generation and interrupt/restart/retry cases; validate audio/metadata/markers before completion, reuse valid chunks, and persist structured failures. | 6 |

## P1 — feature parity and durable state

| ID | Gap / evidence | Required closure | Roadmap stage |
|---|---|---|---|
| G-06 | `project.create` is explicitly unavailable. No bridge commands for project duplicate/archive/delete/export/backup-restore. | Preserve import as real project-creation flow; implement only using existing project service with safe confirmation/ownership semantics, or keep controls clearly unavailable. | 5, 7 |
| G-07 | `chapter.split` was registered and invoked but missing from the capability map. Stage 1 adds the flag and regression assertion. More general capability-vs-handler drift still needs automated checking. | Keep registration, advertised capability and adapter use synchronized in tests. | 1 |
| G-08 | Pronunciation list/save/delete/analyze and single saved-profile preview exist, but bulk test-selected/test-all, per-profile result storage, import/export, conflict tracking and affected-audio invalidation are not complete backend operations. | Connect the voice test matrix to actual saved profiles and keep results/errors per profile; do not use timer-only 'test complete' results. | 5 |
| G-09 | Sound design has real catalogue/import/assignment/manifest/cue/chapter-BGM commands. End-to-end licensing, durations, loudness, missing assets, preview/final consistency and mix quality are not yet accepted. | Test imported and bundled files from disk through preview and final assembly; track unknown licensing accurately. | 5, 6 |
| G-10 | Job rows are stored in `premium_v2_jobs.json`; unfinished jobs are marked interrupted after startup. `history.list` reads the same job records, not a separate immutable history store. | Implement dedicated durable history separate from task-manager visibility/cleanup; verify checkpoint recovery and retry without regenerating valid chapters. | 6, 7 |
| G-11 | `player.get_active` returns output metadata and browser audio controls cover transport/speed/seek, but backend playback position/bookmarks and robust chapter timeline persistence are not evidenced. | Verify playback against real output; persist resume position and synchronize main/mini-player state across navigation/restart. | 5, 7 |
| G-12 | Models list/install are connected, but per-model update/verify/repair/uninstall/default/test operations are intentionally guarded as unavailable. | Add only backend-supported operations with filesystem/checksum checks, job progress and active-job protections. | 8 |
| G-13 | `performance.info` is advertised as false; live hardware telemetry is unavailable. The supplied HTML has a timer-style benchmark demonstration to guard. | Connect real telemetry/benchmark where supported or mark each metric unavailable; ensure demo timers cannot claim measured performance. | 8 |
| G-14 | Custom project/audio/model/cache/output roots and secure provider-specific credential storage are not complete. Settings fields cannot be assumed to persist just because they render. | Map every settings field to storage and a test; implement OS credential store support before enabling credential UI. | 7 |
| G-15 | SQLite is documented as target schema but current project and job paths are JSON/filesystem/QSettings. Current workflow-stage/chapter selection and player resume persistence are not fully verified. | Decide on a staged migration with backups, preserve existing project folders, and add close/reopen integrity tests before switching authoritative storage. | 7 |

## P2 — release quality and acceptance

| ID | Gap / evidence | Required closure | Roadmap stage |
|---|---|---|---|
| G-16 | Diagnostic export is real and best-effort sanitized, but the source acknowledges arbitrary third-party log formats may escape redaction. | Inspect actual exports and test redaction coverage; never describe redaction as a security guarantee. | 5, 8 |
| G-17 | Installer branding/logo cleanup and install/upgrade/uninstall acceptance remain separate work; current CI packaging does not establish visual acceptance on the user's PC. | Inspect original logo asset, create transparent correctly padded variants, then verify install, shortcuts, cancellation and uninstall/data preservation. | 9 |
| G-18 | No final manual visual comparison across 1920×1080, 1366×768, 1280×720 and narrow windows is evidenced by Run #731. | Compare the exact HTML and packaged WebEngine app on those sizes and fix layout regressions without redesigning. | 10 |
| G-19 | Existing CI run passed tests/packaging, but the complete 20-step real-book/real-audio workflow has not been accepted manually. | Complete the import→chapters→voice→characters→pronunciation→sound→generation→recovery→playback checklist on Windows and record evidence. | 10 |

## Recommended execution order

1. **Stage 2:** add reproducible extraction/cleanup/chapter fixtures and fix confirmed text-loss/segmentation defects.
2. **Stage 3:** persist speaker assignments and stop exposing line-level AI results as saveable.
3. **Stage 4:** prove the selected saved voice and duration reach the real preview provider.
4. **Stage 5:** restore remaining screen action parity, bulk pronunciation tests and history/player controls using existing services.
5. **Stages 6–8:** complete durable generation recovery, state/security, supported model actions and truthful performance telemetry.
6. **Stages 9–10:** logo/installer and final visual/functional acceptance.

## Stage 1 exit check

- [x] Repository, branch, PR and exact code baseline verified.
- [x] Three user-supplied implementation/UI specifications inspected alongside the latest approved HTML.
- [x] All 15 screens inventoried and key backend service/bridge operations mapped.
- [x] Explicit capability mismatch found and corrected (`chapter.split`).
- [x] Current known limitations and test evidence updated without claiming full acceptance.
- [x] Prioritized gap register created with closure criteria and owning roadmap stage.
- [ ] Broader automation to check every visible control against adapter/host/capability map remains part of implementation, not complete merely because this register exists.

## Stage 2 checkpoint — import integrity

- Exact-content duplicate detection and actionable existing-project guidance are implemented in the host before a new import job is created.
- Import completion data reports the preserved source path and flags chapter boundaries for review.
- Chapter review status defaults legacy chapters to `needs_review`, persists `reviewed`/`needs_review` with chapter JSON, and drives the existing Review filter.
- Explicit chapter exclusion now persists as `skip_for_generation`, is available through the contextual chapter action, preserves the chapter text, and excludes only flagged chapters from audiobook generation. Job messages, returned job data, and project state distinguish empty chapters from intentionally excluded chapters; a stale contract test and misleading progress summary were corrected in the same batch.
- Still open: re-detection protection, parser/chapter fixtures, import retry/cancel behavior, malformed-file diagnostics, and edit/save/reload acceptance. Find selects the first case-insensitive match, Replace confirms and replaces all case-insensitive matches, and chapter undo/redo supports grouped editing with a bounded history (10 snapshots; disabled for chapters over 1,000,000 characters to limit memory use). Stage 2 is not complete.
