# Known Limitations — Premium V2 Integration

**Status date:** 2026-10-19. This is a live release-gate list, not a claim of completed implementation.

## Confirmed by inspection

1. The user-provided Premium V2 HTML is not currently the repository's packaged frontend. The repository uses a PySide6 widget shell (`app/main.py`, `app/ui/workflow.py`).
2. The existing requirements list PySide6 but do not list Qt WebEngine or QWebChannel integration dependencies.
3. The HTML contains 15 destinations, nine inline scripts, and approximately 387 interactive elements. The previous HTML reference has 14 destinations and approximately 199 controls.
4. Static scan found timer-driven demo code including `simulateImport`; scripts contain no `fetch()` calls. Some pronunciation/sound data uses browser storage. This is not yet a backend integration.
5. Current desktop persistence includes project JSON and state JSON. The required shared SQLite schema and durable background-job service are not confirmed as implemented.
6. Existing source does contain meaningful backend services for import/parsing, chapter detection/editing, voice profiles/providers, character/dialogue handling, pronunciation suggestions, sound design/mixing, generation, M4B assembly, model registry, hardware, history and settings. Exact per-control parity still needs runtime mapping and integration.
7. Repository tests that describe 14 destinations must be updated to validate the Premium V2 15-destination frontend without deleting existing application capabilities.
8. The supplied screenshots show a Build 491 Voice Studio state and a prior GitHub workflow view; they are context/evidence, not a substitute for running the current installer.

## Not yet verified

- Exact same-to-same visual parity in an embedded desktop WebEngine window at all specified dimensions.
- Complete control-to-backend wiring, custom modal behavior, responsive behavior and keyboard/focus accessibility.
- SQLite migration, restart recovery for projects/jobs/playback, or durable event streaming.
- Full functional acceptance workflow from import through M4B playback/history/diagnostic export.
- Installer/portable package launch and uninstall behavior for a build containing Premium V2.
- Provider-specific model downloads, custom voice workflows and GPU readings on the target Windows machines.

## Constraints

- Do not label unsupported providers or unavailable hardware metrics as usable/measured.
- Do not simulate job progress or report success before the backend confirms completion.
- Do not delete old HTML references or desktop features until their functions are mapped and preserved.
- Do not embed credentials in HTML, JavaScript, project JSON, or logs.
- Do not claim the final installer exists until a current CI artifact has completed and the exact artifact has been verified.
