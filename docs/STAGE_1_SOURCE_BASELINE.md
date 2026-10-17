# Ryu's Audiobook — Stage 1 Source Baseline & Feature Checklist

Baseline recorded: 2026-10-18
Repository: https://github.com/RyuBlanc/ryu-audiobook-build
Working branch: `fix/import-qa-speaker-hover-hardware`
Code baseline commit: `af483449052f5272c51208a6fcf9253efbffe99f`
Backup branch: `backup/stage-1-source-baseline-2026-10-18` (points to the exact code baseline commit above)
Open implementation PR: https://github.com/RyuBlanc/ryu-audiobook-build/pull/15

## Canonical UI references

- Dragon Studio full UI: `docs/prototypes/Ryus_Audiobook_Dragon_Studio_Premium_Final.html`
  - Blob SHA at baseline: `30119d993b840a024f61c28c6ffa9bfbe910910b`
- Voice Studio UI: `docs/prototypes/Ryus_Audiobook_Voice_Studio_Fixed_All_Steps.html`
  - Blob SHA at baseline: `6894b60468819615c3eb35b5eee1a7ffe105b75f`

These repository copies are the current reference files for parity work. The older locally named `Ryus_Audiobook_Dragon_Studio_Premium_Final_Fixed.html` is not present under that exact name in the repository; do not silently substitute a different file if the user later provides a newer fixed variant.

## Stage 1 exit checklist — source and scope baseline

- [x] One canonical application repository and working branch identified.
- [x] One exact code commit recorded for the Stage 1 baseline.
- [x] Exact-source backup branch created at that commit.
- [x] Dragon Studio HTML reference path and blob SHA recorded.
- [x] Voice Studio HTML reference path and blob SHA recorded.
- [x] Agreed feature checklist recorded below.
- [ ] Stage 1 CI for the latest preview-budget regression commit finishes green; run link: https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39075400488
- [ ] Confirm whether the user has a newer local HTML file than the canonical repository copy. This is a parity confirmation, not a blocker to proceeding with the current recorded baseline.
- [ ] Confirm a successful, retained Windows installer artifact for the exact approved commit before release; no installer is declared delivered by this baseline note.

## Agreed product feature checklist

### Local-first app, import, and book workflow
- [ ] Windows desktop app; local project/audio/voice storage; no cloud storage of manuscript or generated audio.
- [ ] Import supported manuscript formats; extract readable text; preserve paragraphs and dialogue formatting.
- [ ] Detect chapters, allow editing/renaming/reordering, and preserve user edits across save/reopen.
- [ ] Empty chapters are clearly reported and skipped only when at least one valid chapter remains; block generation if all chapters are empty.
- [ ] Library supports open, rename, delete one/multiple projects, and recover prior work safely.

### Voice Studio and narration
- [ ] Built-in/offline voices and voice profiles are selectable and persist correctly.
- [ ] Authorized custom/reference voices load, preview, save, and propagate into full generation without silently reverting to a default voice.
- [ ] Qwen voice identity/profile/seed/anchor metadata persists and changes invalidate incompatible resumable chunks.
- [ ] Character analysis returns plausible story characters, dialogue examples, confidence, aliases, and unassigned-dialogue counts.
- [ ] Voice assignments remain stable across chapters and generation resumes.
- [ ] Pronunciation overrides are scoped and opt-in; ordinary words are not rewritten unexpectedly; Japanese names can be reviewed/auditioned.
- [ ] Preview options include 10/20/30/45/60 seconds, separate Play/Pause, cancellation, real elapsed time, and accurate generated duration.

### Generation and output
- [ ] Generate navigation opens reliably with an active book and when Generate is clicked repeatedly.
- [ ] Readiness checks explain missing requirements without losing the current book or edited chapters.
- [ ] Progress and elapsed time reflect real phases; no false 100% jumps; failures identify chapter and reason.
- [ ] Generation can resume/retry safely and reports skipped/failed chapters.
- [ ] Assemble a single M4B with chapter markers, author/title metadata, and optional cover.
- [ ] AAC bitrate selector and output verification support 128–320 kbps; verify actual encoded bitrate, not only the UI label.

### Sound design
- [ ] Real, licensed/imported BGM and ambience catalogue; story-aware selection; manual override.
- [ ] Separate music, ambience, narration, and story-SFX volume controls with fades/ducking where supported.
- [ ] Separate book-opening, chapter/page-turn, and book-closing cues with preview/import/auto selection.
- [ ] Preview mix and final M4B use compatible settings; narration-only/off remains a safe default.
- [ ] No placeholder or unlicensed tracks are presented as finished catalogue content.

### UI parity, packaging, and operations
- [ ] Compare every relevant application screen to the canonical Dragon Studio HTML and Voice Studio HTML; restore any controls removed by regressions.
- [ ] Correct branding/icons, spacing, responsive/full-screen layout, selected-book title, and navigation labels.
- [ ] Hardware screen reports available CPU/GPU/runtime accurately and provides a usable fallback.
- [ ] Build number/version is visible in the installed app.
- [ ] Windows CI runs regression tests, frozen-EXE startup smoke test, bundled asset checks, installer creation, artifact upload, and release publication.
- [ ] Installer/uninstaller behavior is tested; any full-data wipe is explicit and opt-in.
- [ ] Final handoff includes the installer link, SHA-256, version/build number, known limitations, and a user test checklist.

## Stage 2 gate

Stage 2 is application stability: startup/runtime errors, Generate navigation, missing UI modules, and unresponsive navigation. Start Stage 2 from the source baseline above; do not treat an in-progress CI run as a green result. The current preview-duration change is a small regression fix on the working branch, and must pass CI before it is called verified.

## Important status distinction

This file establishes a reproducible source/scope baseline. It does not certify every feature above as implemented or tested, and it does not claim the application is bug-free. Items remain unchecked until evidence is recorded.
