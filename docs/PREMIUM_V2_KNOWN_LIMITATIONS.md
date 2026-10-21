# Known Limitations — Premium V2 Integration

**Status date:** 2026-10-21. This is a live release-gate list, not a claim of completed implementation.

## Confirmed by inspection

1. The Premium V2 HTML is now the selected embedded frontend at `assets/frontend/ryu_audiobook_premium_v2.html`; `app/main.py` launches `PremiumV2Window` when the asset exists. This confirms selection/packaging wiring, not full interactive parity.
2. The requirements now include `PySide6-WebEngine`; `app/ui/premium_v2_host.py` embeds `QWebEngineView`, exposes an allow-listed `QWebChannel` bridge, and loads `premium_v2_backend_adapter.js`.
3. The HTML contains 15 destinations, nine inline scripts, and approximately 387 interactive elements. The previous HTML reference has 14 destinations and approximately 199 controls.
4. The supplied HTML still contains prototype-only inline behaviors, including timer-based model/job demos and browser-storage pronunciation/sound state. The adapter now overrides the import file-input and drop handlers to start real local import jobs; other inline demo handlers still require a control-by-control audit.
5. Current desktop persistence includes project JSON and state JSON. The required shared SQLite schema and durable background-job service are not confirmed as implemented.
6. Existing source does contain meaningful backend services for import/parsing, chapter detection/editing, voice profiles/providers, character/dialogue handling, pronunciation suggestions, sound design/mixing, generation, M4B assembly, model registry, hardware, history and settings. Exact per-control parity still needs runtime mapping and integration.
7. Repository tests that describe 14 destinations must be updated to validate the Premium V2 15-destination frontend without deleting existing application capabilities.
8. The supplied screenshots show a Build 491 Voice Studio state and a prior GitHub workflow view; they are context/evidence, not a substitute for running the current installer.
9. Sanitized diagnostic export is connected to a real save dialog and bounded local-log collection. The implementation redacts common credential patterns, email addresses, and the current user home path; its packaged Windows behavior remains to be verified.

## Not yet verified

- Follow-up Windows CI run for the post-Run-835 unavailable-control hardening commit (pending). Run 835 on its parent commit passed 371 tests and produced installer/portable artifacts.
- Exact same-to-same visual parity in an embedded desktop WebEngine window at all specified dimensions.
- Complete control-to-backend wiring, custom modal behavior, responsive behavior and keyboard/focus accessibility. Known unsupported prototype actions are now disabled with accessible reasons, but a full control-by-control audit remains open.
- SQLite migration, restart recovery for projects/jobs/playback, or durable event streaming.
- Full functional acceptance workflow from import through M4B playback/history/diagnostic export.
- Installer/portable package launch and uninstall behavior for a build containing Premium V2. Run 835 proves compilation/upload only; it does not prove that the packaged UI launches or that uninstall preserves user data.
- Provider-specific model downloads, custom voice workflows and GPU readings on the target Windows machines.

## Constraints

- Do not label unsupported providers or unavailable hardware metrics as usable/measured.
- Do not simulate job progress or report success before the backend confirms completion.
- Do not delete old HTML references or desktop features until their functions are mapped and preserved.
- Do not embed credentials in HTML, JavaScript, project JSON, or logs.
- Run 835 produced current installer and portable artifacts: [Run 835 artifacts](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39632819459). The subsequent source hardening requires a fresh successful build before its artifacts can be treated as the current release candidate.
- Diagnostic export is a best-effort sanitizer, not a guarantee that every possible secret format is recognized; inspect the report before sharing it externally.
