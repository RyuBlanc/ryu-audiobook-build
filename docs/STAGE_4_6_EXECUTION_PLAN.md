# Ryu's Audiobook — Stage 4–6 Execution Plan

**Branch:** `fix/import-qa-speaker-hover-hardware`  
**Source-of-truth rule:** the supplied Premium V2 HTML is the visual baseline; the existing Python application and services are the behavioral/backend baseline. Do not redesign the HTML or claim an operation works unless the backend response and resulting state prove it.

## Stage 4 — Voice preview correctness and honest readiness

**Current focus:** duration and playable-output integrity. CI Run 819 passed on commit `66c88b29`; packaged Windows preview acceptance remains pending.

- [x] Preserve the selected profile and supported 10/20/30/45/60-second target through the preview job request.
- [x] Measure and return the actual generated duration.
- [x] Reject a preview as successful if its audio duration cannot be measured.
- [x] Prevent the UI from showing Ready when the job has no playable file URL or valid duration.
- [x] Add automated contract tests for requested durations, selected-profile routing, measured output duration, and fail-closed readiness.
- [ ] Pass CI on the latest commit.
- [ ] Run actual previews with representative local and custom voices at 10/30/60 seconds on Windows; compare requested versus measured duration, confirm in-app playback and transport, and record any provider-specific shortfall.
- [ ] Verify preview text modes (current chapter, selected passage, custom text), permission/model errors, and retry behavior on the packaged build.

**Exit gate:** latest CI green (Run 819 passed); actual preview file opens in the embedded player; the chosen voice is used; measured duration is displayed; short output is clearly disclosed and never mislabeled as the requested duration. Manual Windows acceptance remains open.

## Stage 5 — Voice-profile identity and cast-to-synthesis consistency

**Automated gate passed:** Run 825 passed on commit `17569d62`; the profile-identity regression suite covers narrator-only and cast-aware cache invalidation, saved profile round-trip, and reference-audio digest changes. Packaged restart and real multi-speaker acceptance remain open.

- [ ] Verify saved profile fields survive save → app restart → reload → preview → narrator selection → character assignment.
- [ ] Confirm the same provider, model/backend, voice ID, language, reference audio and provider-specific parameters are used after reload; do not silently substitute a different voice.
- [ ] Test narrator fallback for unassigned dialogue and explicit per-character profile routing for assigned dialogue.
- [x] Include narrator profile identity, cast assignments and profile synthesis settings in generation signatures so changed voice settings invalidate stale chunks; add reference/anchor audio content digests. Automated regression tests cover provider changes, cast prompt edits and reference-file replacement. CI verification is pending.
- [x] Add focused regression tests for narrator profile changes, cast prompt changes, reference audio replacement and missing-reference state. Existing Stage 3 tests cover aliases, stale offsets, manual assignments and alternating voices. Packaged restart/multi-speaker acceptance remains pending.
- [ ] Mark unsupported providers, credentials, models, or hardware paths unavailable with actionable messages rather than simulated readiness.
- [x] Run CI for profile-identity/cache invalidation changes (Run 825 passed). Test the exact packaged build against a small multi-speaker book remains pending.

**Exit gate:** saved voice identity is stable across restart and every preview/generation path; changed voice/cast settings cannot reuse incompatible audio chunks; unavailable profiles fail safely with recovery instructions.

## Stage 6 — Production reliability and release acceptance

**Status:** automated build/packaging passed on Run 841 (21 October 2026, commit `4305ea8136e2e96ee1bd51608f956f36dab563fb`): configured tests, frozen-app checks, voice-asset checks, installer compilation and installer/portable artifact uploads succeeded. A follow-up release-integrity/Defender scan gate is now in the workflow and must pass on the latest commit before artifacts are treated as release candidates. Windows Security has reported `Trojan:Win32/Bearfoos.A!ml` on the user's installed executable; security clearance and manual Windows acceptance remain release blockers. Artifact links: [Installer 835](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39632819459) and [Portable 835](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39632819459). A follow-up hardening change now disables known unsupported prototype controls (bulk AI dialogue acceptance, custom storage-root selection, per-model update/repair/uninstall, and live hardware benchmarking) with accessible, truthful reasons rather than allowing them to imply a working action. That follow-up requires its own CI run. Backend generation preflight rejects empty chapter sets before a worker starts. The installer wizard has branded palette/copy and compiles, but its actual Windows rendering and user-data-preserving uninstall have not been manually verified. The full packaged workflow, visual parity, and release acceptance remain open.

- [x] Add backend-level empty-chapter preflight with actionable recovery guidance; add regression tests for empty, mixed, and valid chapter sets.
- [x] Apply Premium V2 visual identity to the Windows setup wizard (near-black/slate surfaces, warm-gold headings, Segoe UI, branded welcome/finish copy) while retaining the native wizard flow and app icon.
- [x] Add installer contract tests for visual branding, standard launch/shortcut behavior, and preservation of user data on uninstall.
- [x] Rebuild installer and portable artifacts; Run 835 compiled the installer and uploaded both artifacts successfully. Automated contract/build checks passed on that commit.
- [ ] Verify the actual wizard rendering and user-data-preserving uninstall on Windows; packaging success is not a visual/manual acceptance result.
- [ ] Pass the new release gate that validates original logo PNG transparency/multi-size ICO and emits SHA-256 hashes for the installer, app EXE and logo assets.
- [ ] Confirm Microsoft Defender custom scans of the exact installer and app EXE are clean on the latest commit; investigate and submit the user's `Trojan:Win32/Bearfoos.A!ml` detection to Microsoft rather than bypassing protection.
- [ ] Visually verify the logo in Explorer/shortcuts/installer at small and large sizes, with no added canvas background or lost detail.
- [ ] Capture and review the installer welcome, destination, progress and finish pages after the contrast fix; confirm all labels are legible against dark surfaces.
- [ ] Validate the full path: import → chapter review → narrator/cast → pronunciation → sound design → preview → selected/full generation → M4B validation → in-app playback/history.
- [ ] Confirm real progress/stage/current chapter, elapsed time, ETA where measurable, failure state and output location come from backend jobs, not timer-only UI behavior.
- [ ] Exercise pause/resume/cancel at safe checkpoints, retry after provider failure, restart recovery, and valid completed-chunk reuse.
- [ ] Test mixed empty/non-empty chapters and an all-empty book; skip or block with a precise explanation without silently failing unrelated chapters.
- [ ] Validate M4B duration, stream metadata/bitrate, chapter markers, title/author/narrator and cover; reject empty or corrupt outputs.
- [ ] Verify history remains useful after completed-job cleanup and app restart; keep failure details and recovery guidance.
- [ ] Compare all 15 Premium V2 destinations and critical controls with the approved HTML at 1920×1080, 1366×768 and 1280×720, without changing the source design.
- [ ] Test both installer and portable artifacts from the same accepted commit; record Windows launch, core workflow, offline/local-first, and uninstall/data-preservation results. The installer must retain the approved Premium V2 dark/gold/dragon visual identity, standard install/launch controls, and user-data preservation.
- [ ] Audit remaining prototype-only handlers and disable or connect every visible action; update known limitations and the test report.
- [ ] Preserve source and required assets; remove only stale generated build artifacts after the current verified artifacts are available.

**Exit gate:** current commit CI green; no unresolved high-severity production regression; complete short-book and multi-chapter smoke tests pass on the exact installer/portable build; all remaining limitations are documented accurately.

## Release discipline

A green packaging run proves automated tests and packaging steps passed; it does not prove all voice providers, GPUs, UI dimensions, or real-world books work. Do not mark a stage complete until its exit gate is met. Do not claim “bug-free”; report verified checks and remaining limitations separately.
