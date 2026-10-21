# Ryu's Audiobook — Project History Wiki

> Last verified: 21 October 2026  
> Repository: [RyuBlanc/ryu-audiobook-build](https://github.com/RyuBlanc/ryu-audiobook-build)  
> Active branch: `fix/import-qa-speaker-hover-hardware`  
> Active PR: [#15](https://github.com/RyuBlanc/ryu-audiobook-build/pull/15) — open, draft, not merged  
> Latest verified Windows build: [Workflow #775](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39569947473) — passed

## Purpose and release principle

Ryu's Audiobook — Dragon Studio Edition is a local-first Windows desktop application for converting books into chaptered audiobooks. The intended experience covers importing and cleaning text, chapters, narrator and character voices, pronunciation, sound design, generation and recovery, M4B assembly, playback, model management, hardware diagnostics, and settings.

The approved HTML must become the real application frontend, wired to existing backend actions. Preserve the approved visual design and existing functions. Do not deliver just a mock-up. No visible control should claim success without a real result. A successful CI/package run does not by itself prove manual Windows functionality or release readiness.

## Project source references

- User-provided visual/design reference: `Ryus_Audiobook_Premium_V2.html`
- Full replication specification: `Ryus_Audiobook_Full_Application_Replication_Prompt.txt`
- Updated UI requirements: `# RYU'S AUDIOBOOK Updated UI.txt`
- Repository completion roadmap: [docs/FINAL_COMPLETION_ROADMAP.md](https://github.com/RyuBlanc/ryu-audiobook-build/blob/fix/import-qa-speaker-hover-hardware/docs/FINAL_COMPLETION_ROADMAP.md)
- Acceptance checklist: [docs/DRAGON_STUDIO_ACCEPTANCE_CHECKLIST.md](https://github.com/RyuBlanc/ryu-audiobook-build/blob/fix/import-qa-speaker-hover-hardware/docs/DRAGON_STUDIO_ACCEPTANCE_CHECKLIST.md)
- Detailed UI parity/production plan: [docs/STAGE_8_2_UI_PARITY_AND_PRODUCTION_VERIFICATION.md](https://github.com/RyuBlanc/ryu-audiobook-build/blob/fix/import-qa-speaker-hover-hardware/docs/STAGE_8_2_UI_PARITY_AND_PRODUCTION_VERIFICATION.md)

The repository contains multiple historical UI references. Compare source revisions before calling any older prototype canonical. Preserve the latest user-approved HTML as the visual authority for this task.

## History from project records

This is a milestone summary reconstructed from the available project chats and repository records; it is not a complete listing of every original change.

### 22 September 2026 — early voice and character issues
The user reported custom voices not loading correctly in character recognition and audiobook generation. The goal was to repair real functionality, not remove features.

### 4 October 2026 — Build V: generation progress
The user requested percentage-based progress in voice previews and generation, with previews using the actually selected voice.

### 10 October 2026 — Build VI: preview duration and responsiveness
Reported problems included a temporary no-response/not-responding popup and a 30-second preview producing only about 10 seconds. Requested duration, measured output duration, and UI responsiveness became core acceptance requirements.

### 15–16 October 2026 — Build VIII: Generate navigation and EXE
The user reported being unable to access the Generate screen and requested a completed Windows EXE/package. CI failures were to be inspected and fixed, and old generated build artifacts cleaned safely.

### 17 October 2026 — full UI direction
The project aligned around the fuller Dragon Studio / Voice Studio experience. The intended approach was to preserve existing features while making the chosen HTML interface functional in the real desktop app.

### 18 October 2026 — specification-driven implementation
The user specified the attached TXT as the full implementation specification and the latest HTML as the visual source of truth. The goal: map backend functions, connect the real frontend, and keep same-to-same UI rather than returning a proposal or demo.

### 19 October 2026 — acceptance gates and staged roadmap
Repository docs articulated release gates G0–G5 and the rule that successful packaging is not manual acceptance. The technical work was organized into Stage 8.2 substages and six remaining packages.

### 20–21 October 2026 — chapter/speaker/voice reliability
Recent commits on the active branch include:
- `651a39ca` — deterministic Stage 2 chapter fixtures.
- `4720e597` — persist explicit source-backed dialogue speaker assignments.
- `779e6a53` — render source-backed dialogue review from saved chapters.
- `0d33cd5b` — prevent stale dialogue offsets from misrouting cast voices.
- `c12b162a` — honor alternating-speaker mode in cast routing.
- `1c9ce75e` — verify voice preview profile and duration contracts.
- `44e83717` — fix voice preview test bridge clock fixture.
- `c7cee60e` — complete voice preview fixture.
- `7b8176ac` — test assigned character profile reaching the synthesis provider.

### Latest build result
Workflow [#782](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39583746634) passed on 21 October 2026 at commit `a7c6baa4a2552600af6395ab0abad9766d9a650f`. The workflow passed regression tests (341 tests), frozen application checks, bundled voice assets/critical modules, installer build, portable artifact upload, and cleanup. The adapter/dispatcher/capability parity regression passed after a test-only regex escaping fix. Publishing a public release was skipped. This run does not prove the installer or portable app was manually installed/launched and exercised on a Windows PC.

## Current stage

- **Overall 10-stage tracker:** Stage 10 — Regression and Final Release, IN PROGRESS.
- **Technical substage:** Stage 8.2.9 — Frontend/backend parity, IN PROGRESS. The adapter-to-dispatcher/capability static contract now passes in Run #782; control-by-control legacy-handler audit and Windows interaction acceptance remain open.
- Stage 8.2.8 sound design still needs manual audio acceptance; Stage 8.2.10 generation reliability has automated coverage but still needs real-book/recovery acceptance.
- The numbering differs: Stage 10 is the user's high-level tracker; Stage 8.2.9 is the current repository technical substage.

Active reliability work concerns saved character voice profiles reaching synthesis, correct preview voice and requested duration, dialogue assignments/offsets, progress and cancellation/recovery, output integrity, and persistence across restarts.

## Workflow from a fix to an accepted release

```text
1. Inspect latest approved HTML and implementation specification
                         |
2. Inventory controls and map them to backend functions
                         |
3. Fix one bounded function area without redesigning the UI
                         |
4. Add/update regression tests and frontend/backend contract checks
                         |
5. Run Windows CI: test suite -> frozen app -> bundled assets -> installer/portable
                         |
6. Read any failure logs, fix the cause, and rerun the changed commit
                         |
7. Manually launch/test that exact packaged build on Windows
                         |
8. Verify every screen, workflow, persistence path, and generated audio
                         |
9. Record commit, CI run, artifact, expected vs observed result, limitations
                         |
10. Close G0-G5 with evidence, publish the accepted release, provide the build
```

**Current position:** workflow #775 passed the automated build/package step. Failure diagnosis and fixes were done in earlier iterations. Manual packaged-app testing, comprehensive screen acceptance, evidence recording, gate closure, and public release remain required.

## Ten-stage completion tracker

| # | Stage | Current assessment |
|---|---|---|
| 1 | Gap audit and function map | In progress — acceptance documents exist; full control-by-control interactive verification remains |
| 2 | Import, text cleanup and chapters | Partially verified — tests/fixtures and chapter/import work exist; real-project acceptance remains |
| 3 | Dialogue and character assignments | In progress — persistence/routing fixes and regression test exist; real-generation verification remains |
| 4 | Voice Studio and preview | In progress — preview contracts/tests exist; real-provider playback and measured duration still need Windows acceptance |
| 5 | Restore previous functions | In progress — feature-preservation checklist exists; full parity sign-off remains |
| 6 | Production and output quality | Partially verified — automated contracts cover portions; full end-to-end audio acceptance remains |
| 7 | Persistence, storage and security | In progress — some persistence work exists; broader restart/offline/privacy tests remain |
| 8 | Models and system screens | In progress — truthful model/hardware/runtime actions need full screen acceptance |
| 9 | Logo and installer branding | CI packaging passes; full visual branding, fresh install, and launch acceptance are unverified |
| 10 | Regression and final release | **Current overall stage — in progress** |

Do not mark any stage fully complete until all of its acceptance criteria have evidence. Implemented or CI-tested sub-items do not automatically complete the entire stage.

## Technical roadmap — six packages

1. **Stage 8.2.7 — CI stabilization:** keep regression and integration-contract checks passing.
2. **Stage 8.2.8 — Sound Design:** connect chapter BGM rules, scene cues, and an actual narration/music preview through assembly; verify real audio behavior.
3. **Stage 8.2.9 — Frontend/backend parity:** audit all destinations and controls for real actions, state, progress, errors, and responsive behavior. The adapter command-name/capability check passed in #782; next is control-level prototype/legacy handler coverage.
4. **Stage 8.2.10 — Generation reliability:** verify preview duration/voice routing, progress, pause/resume/cancel/retry, provider failures, recovery, and output integrity.
5. **Stage 8.2.11 — Windows release validation:** build installer and portable packages from the same commit; manually test launch, assets, playback, and compact-window behavior.
6. **Stage 8.2.12 — Final acceptance/release:** final regression/packaging, screen parity review, evidence capture, blocker closure, and verified release.

## Known user-reported issues and requirements

These remain acceptance targets; listing them does not assert that all are currently reproducible:
- Custom voice/profile may not propagate through character recognition and full audiobook generation.
- Requested 30-second voice preview historically returned about 10 seconds.
- Preview audio must match the selected provider/profile/voice.
- No temporary “not responding” state during long previews or generation.
- Generate navigation must open the real production screen.
- Percentage progress, current stage/chapter, elapsed time, ETA, cancellation and recovery should represent real work.
- Saved character assignments must affect actual synthesis, not merely the UI.
- Sound design and chapter cue choices must affect final audio.
- Preserve every existing screen and function while matching the approved HTML.
- Package a reliable Windows installer and portable build; remove only stale generated artifacts safely.

## Release gates (G0–G5)

- [ ] **G0 — Preserve existing features:** no existing capability is silently removed.
- [ ] **G1 — Critical reliability:** custom voice propagation, character detection/assignment, empty-chapter handling, Generate navigation, preview duration, progress, and recovery verified.
- [ ] **G2 — Screen parity:** every destination and important control checked against the approved HTML/spec.
- [ ] **G3 — Production acceptance:** real generation; M4B chapters, metadata, artwork, bitrate; pause/resume/cancel/retry; offline/local-first behavior.
- [ ] **G4 — Windows packaging:** current commit passes CI/package checks and the exact installer/portable build is launched and smoke-tested.
- [ ] **G5 — Cleanup/release:** safe artifact cleanup, build provenance, and release publishing only after acceptance.

## Immediate next actions

1. Continue Stage 8.2.10: verify the assigned profile/provider is used in real synthesis and compare requested vs measured durations for supported preview targets.
2. Run and inspect CI after every implementation change; do not accept code solely because it looks right.
3. Finish Stage 8.2.9's control-by-control UI/backend map for every screen without redesigning the approved HTML.
4. Test actual voice preview and short-book generation in the packaged Windows application.
5. Verify profile persistence across restart, character assignment, empty chapter recovery, progress, pause/resume/cancel/retry, and provider/offline errors.
6. Inspect a generated M4B for playback, chapter markers, metadata, cover, duration and measured bitrate.
7. Manually launch the installer and portable package produced from the same accepted commit, including a reduced-window navigation test.
8. Record commit/build/artifact and expected-versus-observed results for each gate.
9. Close remaining gate blockers, review PR #15, and publish only after acceptance evidence is complete.

## Current verified status snapshot

| Item | Status |
|---|---|
| Latest Windows CI #775 | **Passed** |
| Regression/frozen app/assets/installer/portable CI steps | Passed for commit `7b8176ac…` |
| Public release from #775 | Not published; release-publish step skipped |
| PR #15 | Open, draft, unmerged |
| Manual installer/portable launch | Not proven by this CI run |
| Actual provider preview duration/playback | Still requires manual acceptance |
| Full interactive screen parity | Not signed off |
| G0–G5 gates | Open until evidence is recorded |
| Fully accepted high-level stages | None should be declared complete based on current evidence alone |
| Overall project stage | Stage 10 — in progress |

## Evidence links

- [Windows build #775](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39569947473)
- [Active PR #15](https://github.com/RyuBlanc/ryu-audiobook-build/pull/15)
- [Completion roadmap](https://github.com/RyuBlanc/ryu-audiobook-build/blob/fix/import-qa-speaker-hover-hardware/docs/FINAL_COMPLETION_ROADMAP.md)
- [Acceptance checklist](https://github.com/RyuBlanc/ryu-audiobook-build/blob/fix/import-qa-speaker-hover-hardware/docs/DRAGON_STUDIO_ACCEPTANCE_CHECKLIST.md)
- [Stage 8.2 production verification](https://github.com/RyuBlanc/ryu-audiobook-build/blob/fix/import-qa-speaker-hover-hardware/docs/STAGE_8_2_UI_PARITY_AND_PRODUCTION_VERIFICATION.md)

> Update this page only when a test, build, manual check, or release action has verifiable evidence. Record the commit SHA and build/artifact used. Never infer manual success from CI packaging alone.
