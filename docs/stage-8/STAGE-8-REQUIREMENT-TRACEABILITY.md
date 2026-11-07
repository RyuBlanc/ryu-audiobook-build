# Stage 8 — Frozen Requirement Traceability Matrix

**Source of truth:** Master Bug & Change Register (Sections 0–24), Stage 8 Detailed Requirements, and the six-package Stage 8 execution plan supplied on 7 November 2026.
**Repository:** `RyuBlanc/ryu-audiobook-build`
**Working branch:** `stage-7/step-6-safe-auto-fallback`
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

## Frozen requirement IDs

This inventory extracts all stable requirement IDs from the Master Bug & Change Register. The title is a compact index; the full original requirement text remains authoritative and must not be weakened.

| ID | Priority | Requirement | Current status | Evidence / next gate |
|---|---:|---|---|---|
| UI-01 | P0 | Premium V2 is the required default UI. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| UI-02 | P0 | Fix overlapping and unreadable elements. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| UI-03 | P0 | Resolve flickering without requiring Reduce Motion to be off. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| UI-04 | P0 | Desktop application behaviour. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| UI-05 | P0 | Notifications, errors and empty states. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| UI-06 | P0 | Responsive layout acceptance. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| UI-07 | P0 | Preserve existing stability improvements. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| VS-01 | P0 | 30-second preview under 60 seconds. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| VS-02 | P0 | Preserve character voice identity. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| VS-03 | P1 | Emotion-aware narration. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| VS-04 | P1 | Story-aware background effects and voices. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| VS-05 | P1 | Make emotion/effects global. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| VS-06 | P0 | Accurate multilingual pronunciation. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| VS-07 | P1 | Emotion and pronunciation must cooperate. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| VS-08 | P0 | Preserve all previous Voice Studio fixes. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| CS-01 | P1 | Real Assigned Cast list. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| CS-02 | P1 | Project isolation and live assignment data. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| CS-03 | P1 | Audio Profile dropdown. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| CS-04 | P1 | Test selected character dialogue. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| CS-05 | P1 | Assignment statistics. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| CS-06 | P1 | Display selected-character dialogue. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| CS-07 | P1 | Source highlighting. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| CS-08 | P1 | Persist assignments. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
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
| SD-02 | P1 | Connect Same BGM/Chapter-Based BGM. | CODE CHANGED — NOT VERIFIED | Regression test test_chapter_based_bgm_never_falls_back_to_auto_music; source fix cb25247c. Matching-head execution pending. |
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
| PROD-01 | P0 | Add Input Project Details. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-02 | P0 | Metadata fields. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-03 | P0 | Metadata completion gate. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-04 | P0 | Metadata persistence and output. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-05 | P0 | Real progress animation. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-06 | P0 | Separate preview and full generation states. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-07 | P0 | Preview generation controls. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-08 | P1 | Live pronunciation toggle. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-09 | P1 | Live BGM/cue toggle. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-10 | P1 | Live project summary. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-11 | P1 | Music summary. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-12 | P1 | Output summary. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-13 | P1 | Live Readiness Center. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-14 | P0 | Consistent job state. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| PROD-15 | P1 | Chapter-specific preview audio and download. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| AB-01 | P2 | Compact audiobook cards. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| AB-02 | P0 | Fix audio file loading. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| AB-03 | P0 | Full player controls. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| AB-04 | P0 | Chapter playback. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| AB-05 | P1 | Persistent mini-player. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| AB-06 | P1 | Playback position persistence. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| AB-07 | P0 | Preserve completed output integrity. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| HIS-01 | P2 | Accurate history records. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| HIS-02 | P2 | Date filtering. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| HIS-03 | P1 | Durable history. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| JOB-01 | P2 | Fix readability and layout. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| JOB-02 | P2 | Job details. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| JOB-03 | P2 | Accurate totals and filters. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| JOB-04 | P1 | Safe operations. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| JOB-05 | P1 | Consistency with History. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
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
| GEN-01 | P0 | Real generation workflow. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| GEN-02 | P1 | Resumable and recoverable generation. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| GEN-03 | P1 | Pause/cancel/retry. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| GEN-04 | P1 | Empty/ineligible chapters. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| GEN-05 | P0 | M4B validation and metadata. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
| GEN-06 | P0 | Preview/final parity. | OPEN — implementation/evidence reconciliation required | No matching-head evidence recorded yet. |
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

1. **8.2.7 CI stabilization:** baseline audited; #2680 passed 1,258 tests on the prior documentation-only HEAD; #2677 packaged successfully on an older commit. A new exact-candidate package run still needs confirmation.
2. **8.2.8 Sound Design completion:** first Chapter-Based BGM auto-mode fallback defect found; test and source fix committed; matching-head CI/audio validation pending.
3. **8.2.9 Frontend/backend parity + Help & Guide:** not started.
4. **8.2.10 Generation reliability:** not started.
5. **8.2.11 Windows release validation:** not started for final candidate.
6. **8.2.12 Final acceptance/release:** not started; v1.2.0 remains gated.

**Inventory count:** 128 stable requirement IDs. This matrix is a tracking index, not proof of implementation. Update each row only when matching evidence exists.

## 8.2.8 test-first fix checkpoint

- Regression test commit: `ef8044248daf2f109025861d231831f54cd19ca4`.
- Source fix commit: `cb25247c4dc95ff9f8ae518fe40dd7a52e17d583`.
- Defect record commit: `025a467112e60244bec541b5943283b838119ed5`.
- This checkpoint requests the Windows workflow's full artifact-checkpoint gate on the current candidate. Record the resulting run and artifact hashes only after verifying the Actions result.
- Until matching-head tests pass, SD-02 remains CODE CHANGED — NOT VERIFIED. Real Windows audio acceptance remains pending even after CI passes.


## REL-01 — Live branch and pull-request dependency audit

**Audited against current Stage 8 working HEAD:** `811822a0497b6943ba61b85105b797a9409b2a18`.

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
