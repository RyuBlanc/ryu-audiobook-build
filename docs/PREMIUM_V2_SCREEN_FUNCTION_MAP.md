# Screen-to-Function Map — Premium V2

**Status:** Phase 1 audit baseline; not an implementation-complete claim.  
**Visual source:** user attachment `Ryus_Audiobook_Premium_V2.html` (1,436,954 bytes; SHA-256 to be recorded during packaging).  
**Functional source:** existing PySide6/Python application in this repository.  
**Previous references:** `docs/prototypes/Ryus_Audiobook_Dragon_Studio_Premium_Final.html` and `docs/prototypes/Ryus_Audiobook_Voice_Studio_Fixed_All_Steps.html` are historical references, not substitutes for Premium V2.

## Audited shell

The attached Premium V2 has 15 `data-page` destinations and 15 matching page sections: Dashboard, Library, Import Studio, Chapter Studio, Voice Studio, Character Studio, Pronunciation, Sound Design, Production Studio, Audiobooks, History, Models, Performance, Settings, and Help & Guide. The document contains approximately 387 interactive elements, nine inline script blocks, no duplicate IDs in the initial DOM scan, and embedded assets. The older attached HTML has 14 destinations and about 199 interactive elements. Do not silently drop Help & Guide or newer controls.

## Function map

| Screen | HTML anchor / important controls | Existing backend candidates | Integration / acceptance requirement |
|---|---|---|---|
| Dashboard | `#dashboard`, Continue project, View job, Pause, Import Book | `app/ui/dashboard_page.py`, `app/core/project.py`, `app/core/state.py`, job/generation modules | All metrics from persisted projects/jobs; actions navigate to the selected project or real job. Remove fixed demo percentages. |
| Library | `#library`, search, All/Active/Completed/Attention, Continue/Listen/Review/Open | `app/ui/library.py`, `app/core/project.py`, `app/core/paths.py` | Persisted library; search/filter/sort, project lifecycle actions, confirmed destructive actions and real job badges. |
| Import Studio | `#import`, `#fileInput`, `#dropzone`, Browse files, import report | `app/ui/import_page.py`, `app/documents/parser.py`, `app/documents/importer.py`, `app/chapters/detector.py` | Validate actual supported formats; preserve source; extraction/chapter/language analysis; durable job for long operations; retry and truthful errors. |
| Chapter Studio | `#chapters`, `#chapterEditor`, `#saveChapter`, split/merge/search/cleanup | `app/ui/chapter_editor.py`, `app/chapters/editor.py`, `app/chapters/detector.py`, `app/tts/narration.py` | Project-backed edit, autosave, undo/redo, chapter operations, scans and previews; no fake save state. |
| Voice Studio | `#voices`, `#voiceWorkspace`, profile steps, provider/model controls, preview/assign/save | `app/ui/voice_page.py`, `app/tts/voice_profile.py`, `app/tts/profile_provider.py`, `app/tts/providers/*`, `app/tts/model_registry.py` | Actual installed/available provider state, real previews, saved profiles, assignment persistence, secure credentials, model-missing recovery. |
| Character Studio | `#characters`, character library, analysis, aliases, assign voice, edit/save | `app/ui/voice_cast_page.py`, `app/ui/character_review.py`, `app/ui/dialogue_assignment.py`, `app/ui/dialogue_manager.py`, `app/chapters/characters.py`, `app/chapters/dialogue.py` | Analyze real project text; persist characters/aliases/appearances/assignments; report unresolved voices; analysis as a real job. |
| Pronunciation | `#pronunciation`, dictionary entries, voice test matrix, import/export | `app/tts/pronunciation_suggester.py`, `app/tts/narration.py`, `app/tts/voice_profile.py` | Persist book/series/global rules; actual saved profiles in test matrix; test results per profile; conflicts and affected audio tracked. Inventory indicates parts of the current HTML use browser storage and need backend replacement. |
| Sound Design | `#sound`, track/effect imports, assignment, gain/fades, preview and manifest | `app/audio/sound_design.py`, `app/audio/preview_mixer.py`, `app/audio/story_events.py`, `app/ui/assembly_page.py` | Real asset files, validated assignments, persisted manifest, actual mix preview/loudness; long operations use shared jobs. |
| Production Studio | `#generate`, preflight, preview, generate, pause/resume/cancel/retry | `app/ui/generation_page.py`, `app/tts/manager.py`, `app/tts/generator.py`, `app/tts/readiness.py`, `app/tts/resume.py`, `app/audio/assembler.py` | Real preflight and shared durable job states/checkpoints; no timer-based progress; validate final output and M4B chapters. |
| Audiobooks player | `#player`, `#playerTimeline`, play/pause, chapter list, mini-player | `app/ui/audiobooks_page.py`, `app/audio/assembler.py`, `app/ui/workflow.py` | Load actual generated output; real duration/seek/chapter navigation/playback position; main and mini-player stay synchronized. |
| History | `#history`, filters, open/retry/log/output | `app/ui/history_page.py`, generation manager/state/logging | Durable audit records independent of task-manager cleanup; real errors, timings, output refs and retry details. |
| Models | `#models`, install/repair/uninstall/test | `app/ui/models_page.py`, `app/tts/model_registry.py`, provider runtimes and build/model helpers | Filesystem/registry-backed state, checksums, job-backed install/repair, block unsafe uninstall, show missing-model references. |
| Performance | `#performance`, benchmark, device/memory/cache/diagnostics | `app/ui/hardware_page.py`, `app/hardware/detect.py`, `app/hardware/backend.py`, `app/tts/benchmark.py` | Measured values only; unsupported metrics shown unavailable; benchmark off UI thread; safe cache cleanup and diagnostics export. |
| Settings | `#settings`, appearance, paths, audio, privacy, diagnostics, About/update log | `app/ui/settings_page.py`, `app/core/paths.py`, `app/core/state.py`, `app/main.py` | Persist settings, paths and preferences; secure credential store; diagnostics/integrity checks must run for real. |
| Help & Guide | `#help`, workflow topics and guide actions | No dedicated page in the current listed `app/ui/` inventory; candidates are workflow and actual service docs | Implement guide content and links based on real app behavior. Do not fake diagnostic/help actions. |

## Cross-screen shell and popups

| HTML feature | Existing implementation candidate | Required outcome |
|---|---|---|
| Sidebar/header/workflow strip | `app/ui/workflow.py` currently owns the PySide6 desktop shell | Premium V2 is rendered as the frontend, not approximated by a second widget redesign. |
| Background Jobs popover | `app/tts/manager.py` and durable job service (audit needed) | UI state comes from actual backend job records/events; pause/resume/cancel/retry are safe backend commands. |
| Toasts, custom dialogs, dropdowns | HTML controls and modal markup | Preserve custom HTML presentation; connect every action; display errors as well as success. |
| Search, filters, selection, popovers | HTML JavaScript and backend query commands | Preserve interaction and connect state; no browser-only source of truth. |
| Themes, responsive layout, reduced motion | HTML CSS/JS | Do not restyle; verify widths 1920x1080, 1366x768, 1280x720, tablet and supported mobile. |
| localStorage/sessionStorage | Inline HTML scripts 5–7 use browser storage | Migrate durable application data to backend persistence; only noncritical UI preferences may remain frontend-local if explicitly documented. |

## HTML implementation risks found in initial static scan

- Inline script blocks contain `simulateImport` and timer-driven progress/render functions; replace demo behavior with backend job events.
- No `fetch()` calls were found in the attached HTML scripts. Several features are local-only, not connected to the existing Python application.
- Browser storage is used by some sound/pronunciation flows, which will not by itself meet the restart-safe shared-data requirement.
- HTML has 15 destinations while previous desktop acceptance tests assert 14. Those tests must be revised to test the actual Premium V2 baseline without losing existing desktop-only functionality.
- The current backend uses PySide6 widgets. The existing requirements do not list Qt WebEngine or a WebChannel bridge. A frontend-host integration must be added to the existing framework and packaged; it must not open an external browser or development server.
- Static inspection is not visual/runtime acceptance. No popup-by-popup Windows run or end-to-end workflow has been claimed by this audit.

## Phase exit criteria

Phase 1 exits only after the new HTML is stored as the packaged app's authoritative frontend, each control has a mapped backend action or a truthful unavailable state, shared persistence design is implemented, and a runnable integration test covers the bridge. Visual parity and full end-to-end tests remain separate release gates.
