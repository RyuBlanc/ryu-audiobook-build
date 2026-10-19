# Update Log — Premium V2 Integration

## 2026-10-19 — Phase 1 audit baseline

### Added
- Screen-to-function mapping for all 15 Premium V2 destinations.
- Typed backend bridge command/event contract covering projects, import, chapters, voices, characters, pronunciation, sound, production/jobs, player, history, models, performance, settings and help.
- Target local SQLite schema and data-safety constraints.
- Known-limitations register distinguishing inspected facts from unverified behavior.

### Inspection findings
- Latest attached HTML: 1,436,954 bytes; 15 destinations; approximately 387 interactive elements; nine inline scripts; no duplicate IDs found in initial DOM scan.
- Earlier attached HTML: 873,127 bytes; 14 destinations; approximately 199 interactive elements.
- Existing app is Python/PySide6 and has reusable service candidates across import, TTS, character/dialogue analysis, sound design, assembly, hardware, model management and existing pages.
- Premium V2 still contains browser-side demonstration behavior and localStorage usage; those cannot remain authoritative for application data/jobs.

### Not yet completed
- Premium V2 embedded in the packaged desktop host.
- Backend bridge implementation and all control connections.
- SQLite migration and durable job/event service.
- Visual parity tests and full Windows end-to-end acceptance.
- Installer artifact built and runtime-verified with Premium V2.

No unsupported success claims are made in this update log.

### Embedded frontend implementation started
- Added the exact Premium V2 HTML asset at `assets/frontend/ryu_audiobook_premium_v2.html`.
- Added `app/ui/premium_v2_host.py`, a local Qt WebEngine host and allow-listed JSON bridge.
- The current bridge has real app-info, local-project-list and settings-read commands; unsupported commands return an explicit `not_connected` error instead of pretending to succeed.
- The desktop entry point selects the embedded HTML when the bundled asset exists; the historical widget shell remains a fallback for source/build trees missing that asset.
- Added a Premium V2 integration-contract test file and WebEngine packaging hooks/dependencies.
- Connected the dashboard/library's initial project listing and headline counts to persisted local project records. Project opening and job operations are explicitly disabled until their commands are connected.

### Current gate
This is a staged integration, not a complete app. The full 20-step functional acceptance, complete screen wiring, durable jobs/SQLite migration, visual comparison and Windows runtime smoke are still open.
