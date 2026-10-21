# Ryu's Audiobook — Stage 4–6 Execution Plan

**Branch:** `fix/import-qa-speaker-hover-hardware`  
**Source-of-truth rule:** the supplied Premium V2 HTML is the visual baseline; the existing Python application and services are the behavioral/backend baseline. Do not redesign the HTML or claim an operation works unless the backend response and resulting state prove it.

## Stage 4 — Voice preview correctness and honest readiness

**Current focus:** duration and playable-output integrity.

- [x] Preserve the selected profile and supported 10/20/30/45/60-second target through the preview job request.
- [x] Measure and return the actual generated duration.
- [x] Reject a preview as successful if its audio duration cannot be measured.
- [x] Prevent the UI from showing Ready when the job has no playable file URL or valid duration.
- [x] Add automated contract tests for requested durations, selected-profile routing, measured output duration, and fail-closed readiness.
- [ ] Pass CI on the latest commit.
- [ ] Run actual previews with representative local and custom voices at 10/30/60 seconds on Windows; compare requested versus measured duration, confirm in-app playback and transport, and record any provider-specific shortfall.
- [ ] Verify preview text modes (current chapter, selected passage, custom text), permission/model errors, and retry behavior on the packaged build.

**Exit gate:** latest CI green; actual preview file opens in the embedded player; the chosen voice is used; measured duration is displayed; short output is clearly disclosed and never mislabeled as the requested duration.

## Stage 5 — Voice-profile identity and cast-to-synthesis consistency

- [ ] Verify saved profile fields survive save → app restart → reload → preview → narrator selection → character assignment.
- [ ] Confirm the same provider, model/backend, voice ID, language, reference audio and provider-specific parameters are used after reload; do not silently substitute a different voice.
- [ ] Test narrator fallback for unassigned dialogue and explicit per-character profile routing for assigned dialogue.
- [ ] Include cast assignments and profile identity/settings in generation signatures so changed voice settings invalidate stale chunks; prove unchanged settings still resume without unnecessary regeneration.
- [ ] Add regression tests for profile edits, missing/deleted profile references, aliases, repeated dialogue, mixed narrator/cast passages, and profile identity after restart.
- [ ] Mark unsupported providers, credentials, models, or hardware paths unavailable with actionable messages rather than simulated readiness.
- [ ] Run CI and test the exact packaged build against a small multi-speaker book.

**Exit gate:** saved voice identity is stable across restart and every preview/generation path; changed voice/cast settings cannot reuse incompatible audio chunks; unavailable profiles fail safely with recovery instructions.

## Stage 6 — Production reliability and release acceptance

- [ ] Validate the full path: import → chapter review → narrator/cast → pronunciation → sound design → preview → selected/full generation → M4B validation → in-app playback/history.
- [ ] Confirm real progress/stage/current chapter, elapsed time, ETA where measurable, failure state and output location come from backend jobs, not timer-only UI behavior.
- [ ] Exercise pause/resume/cancel at safe checkpoints, retry after provider failure, restart recovery, and valid completed-chunk reuse.
- [ ] Test mixed empty/non-empty chapters and an all-empty book; skip or block with a precise explanation without silently failing unrelated chapters.
- [ ] Validate M4B duration, stream metadata/bitrate, chapter markers, title/author/narrator and cover; reject empty or corrupt outputs.
- [ ] Verify history remains useful after completed-job cleanup and app restart; keep failure details and recovery guidance.
- [ ] Compare all 15 Premium V2 destinations and critical controls with the approved HTML at 1920×1080, 1366×768 and 1280×720, without changing the source design.
- [ ] Test both installer and portable artifacts from the same accepted commit; record Windows launch, core workflow, offline/local-first, and uninstall/data-preservation results.
- [ ] Audit remaining prototype-only handlers and disable or connect every visible action; update known limitations and the test report.
- [ ] Preserve source and required assets; remove only stale generated build artifacts after the current verified artifacts are available.

**Exit gate:** current commit CI green; no unresolved high-severity production regression; complete short-book and multi-chapter smoke tests pass on the exact installer/portable build; all remaining limitations are documented accurately.

## Release discipline

A green packaging run proves automated tests and packaging steps passed; it does not prove all voice providers, GPUs, UI dimensions, or real-world books work. Do not mark a stage complete until its exit gate is met. Do not claim “bug-free”; report verified checks and remaining limitations separately.
