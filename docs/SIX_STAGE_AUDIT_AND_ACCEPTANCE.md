# Six-Stage Implementation Audit and Windows Acceptance Ledger

Audit date: 24 October 2026  
Repository: RyuBlanc/ryu-audiobook-build  
Branch: fix/premium-v2-live-voice-chapter-workflow

## Status rules

- **Source + regression covered:** real handler/adapter paths exist and contract tests cover them.
- **Needs packaged-Windows acceptance:** do not mark accepted until the exact installer/portable app is launched and tested.
- **Not implemented / guarded:** keep visibly unavailable; never simulate success.
- A CI pass cannot guarantee zero flicker or zero crashes on every Windows PC.

## Six priority stages

| Priority | Stage | Source/test work | Remaining acceptance |
|---|---|---|---|
| 1 | **Models Center** | Managed inventory and guarded background install/verify/repair/uninstall exist for supported components. Nested Chatterbox storage is counted; Qwen model weights are not double-counted. Lifecycle completion refreshes inventory and applicable voice/provider catalogues. | Run real lifecycle operations in Windows and verify bytes/free space, failure/cancel behavior and downstream voice readiness. Refresh Status is local-only; remote updater, universal default selection and generic test-generation are not implemented. |
| 2 | **Voice Studio** | Saved profiles/provider catalogs exist; stale catalogues cannot overwrite newer selections. Preview targets 10/20/30/45/60 seconds; readiness requires playable audio and measured duration. | Verify actual provider/model/voice ID, playback and saved settings after restart. ElevenLabs key is app-local/environment-backed, not in Windows Credential Manager. |
| 3 | **Models → Voice → Narration → Player** | Real preview/generation jobs. Serialized monitor ticks, stale-job guard, generation-only pause/cancel. Generation terminal refreshes output metadata and History without reloading chapter text. | Generate and listen to a real multi-chapter audiobook; validate chapter coverage, duration, seek/speed, output metadata, interruption/resume and final file. CI cannot verify voice quality. |
| 4 | **Import + Chapter Studio** | Transactional import/format fixtures; chapter fixtures cover TXT/BOM, EPUB order, searchable PDF, DOCX paragraphs/tables, preambles, empty headings, no-heading fallback, named/Roman and compound slash-title/Part headings. Chapter refresh preserves draft/scroll; selection flushes queued autosave and stops on save failure. | Import representative formats on Windows; test clean/find/replace/undo/redo/add/rename/delete/reorder/merge/split/review/skip, rapid chapter switches, reopen and exact text/count comparison. Scanned/image-only PDF OCR is not built in. |
| 5 | **All menus + stability** | All 15 screen destinations inventoried. Latest-response guards cover model/voice/provider/project/chapter/cast/pronunciation/sound/cue/history data. Unchanged cards/lists stay mounted; Library/Sound/Cue search is debounced. | Exercise every visible control, repeated navigation, resolution changes and expected failures in the packaged app. Check low disk, missing assets/model, invalid credentials/network outage, bad file, playback/save errors and crash logs. CI alone cannot certify zero flicker/crashes. |
| 6 | **Windows build + handoff** | Workflow syntax-checks JS, runs regression tests, validates/builds Windows app, packages installer/portable, scans packaged executables and uploads SHA-256 manifest. | Confirm tests and build jobs pass on a run matching final HEAD SHA. Install/test that exact artifact on target Windows before marking manual acceptance complete. |

## Screen-by-screen menu audit

Static UI inventory: **15 destinations, 384 controls (291 buttons, 48 inputs, 40 selects, 5 textareas)**. This is the audit surface, not a claim every control passed runtime acceptance.

| Menu | Source implementation / hardening | Remaining risk |
|---|---|---|
| **1 Dashboard** | Project/job record paths; stable recent cards. | Static fallback/sample HTML remains. Verify metrics, stage tracker and Continue/View/Pause use live IDs. |
| **2 Audiobook Library** | Project list/open/search/filter; stale responses ignored, unchanged cards retained, search debounced. | Standalone create, duplicate, archive/export, backup/restore not exposed; import creates projects. Test real multi-project lifecycle/deletion recovery. |
| **3 Import Studio** | Real chooser/background import, diagnostics and transactional staging/verification. | Test drag/drop, duplicate guidance, cancellation/retry/failure, source preservation and extraction on Windows. No automatic scanned-PDF OCR. |
| **4 Chapter Studio** | Update/clean/add/rename/delete/reorder/merge/split/review/skip/find/replace/bounded undo-redo paths. Draft and scroll survive refresh; chapter switch saves before selection and stops on save error. | Real-book exact text, all edit operations, error path and restart/reopen need manual acceptance. |
| **5 Voice Studio** | Saved profiles, provider catalogues, preview jobs, selector refresh after model lifecycle. | Verify real installed voice/profile/provider/model, measured duration, playback and profile persistence. Credentials are not OS-vault backed. |
| **6 Character Studio** | Cast analysis/list, saved profiles and manual source-backed dialogue assignment; unchanged cast DOM retained. | Bulk AI speaker suggestions/accept remain guarded/prototype-only. Verify assignment edit/removal, aliases, narrator and synthesis routing. |
| **7 Pronunciation Studio** | Saved rules list/save/delete/analyze and saved-profile preview; stale list replies ignored. | Per-profile test matrix, import/export, conflict tracking and invalidation of generated audio are incomplete. |
| **8 Sound Design Studio** | Catalog/import/assignments, cue slots, chapter BGM and full-book mix preview; cue/track lists retained, cue search debounced. | Test licensed assets, missing-file handling, playback, loudness/fades/ducking, timeline and preview/final parity. |
| **9 Production / Generate** | Real generation/preview jobs; generation-only pause/cancel; terminal History/output refresh without editor rebuild. | Actual multi-chapter generation, failure/cancel/resume, audio validation and final M4B inspection remain manual. |
| **10 Player** | File playback, seek/speed and output metadata paths. | Durable bookmarks/playback position/chapter timeline not evidenced complete. Test real output and main/mini-player sync. |
| **11 Generation History** | Persisted job rows/filters; stale responses ignored and unchanged rows retained. | Not an independent immutable store. Dedicated logs/retry/resume/export and separation from job cleanup remain incomplete. |
| **12 Models Center** | Managed model/runtime inventory, background lifecycle jobs, storage fix and selector handoff. | No remote updater, universal default selection or generic test-generation action. Validate actual bytes/lifecycle in Windows. |
| **13 Performance Center** | Telemetry correctly says unavailable rather than fabricating CPU/GPU/VRAM. | Live telemetry/reliable benchmark not implemented; no demo timer may claim measured results. |
| **14 Settings** | Load/save, diagnostics and save-dialog log export paths. | Custom storage roots and Windows Credential Manager are incomplete. Test visible field persistence on restart; redaction is best-effort. |
| **15 Help & Guide** | Navigation/static help. | Ensure instructions match supported capability and test every link/action. |

## Cross-screen reliability work

- Coalesced job-list requests and serialized monitored-job ticks; stale monitor/catalogue replies ignored.
- Production Pause/Cancel guarded by active job type.
- Latest-response guards on projects, chapters, cast, pronunciation, sound/cues, models, saved voices/provider catalogues and History.
- Stable DOM for unchanged project cards, Dashboard recent items, audiobook shelf, cast, sound tracks/cues and History rows.
- Debounced Library/Sound Track/Cue search.
- Save pending Chapter Studio edits before switching; save failure blocks the switch and is shown.
- Generation completion refreshes output metadata and History without replacing the chapter editor; only import/character analysis reload chapter/cast panels.
- Added named/Roman and compound slash-title/Part chapter fixtures.

## Manual Windows acceptance checklist

- [ ] Install/launch exact final artifact. Repeat open/close and test all 15 menus at 1920×1080, 1366×768 and 1280×720. Capture stalls, clipping, bridge errors and crash logs.
- [ ] Models: inventory/install/verify/repair/uninstall, actual drive/free space, progress and cancellation.
- [ ] Voice: real saved profile at 10/30/60 seconds, playable output, measured duration and settings after restart.
- [ ] Import TXT, EPUB, searchable PDF and DOCX; check source preservation, opening text, headings and chapter count.
- [ ] Chapters: edit then immediately switch before debounce; verify saved text. Test add/rename/delete/reorder/merge/split/clean/find/replace/undo/redo/review/skip, save failure and reopen.
- [ ] Character/Pronunciation: source-backed line assignment; verify narration reflects selected character/voice/pronunciation.
- [ ] Sound: licensed cues/BGM and full-book preview compared with final output timing/fades/loudness.
- [ ] Production → Player: generate a multi-chapter book; pause/cancel/resume/retry; validate audio files, coverage, seek/speed.
- [ ] History/Settings/Help: statuses, restart persistence, diagnostic export and guide links.
- [ ] Exercise unsupported file, missing model/asset, invalid credential/network outage, low disk, playback failure and chapter-save failure. Confirm honest error state, no fake success.
- [ ] Do not report zero crashes/flicker unless repeated target-machine testing supports it.

## Known non-claims

Scanned-PDF OCR, hardware telemetry/benchmark, custom storage-root selection, OS-backed credentials, standalone project creation, independent immutable History, durable player bookmarks/chapter timeline and universal model-default/test-generation are not complete unless separately implemented and verified. Storage remains filesystem/JSON/QSettings; the documented SQLite schema is not a deployed migration. Model Refresh Status is local-only. Bulk AI per-line speaker suggestions remain guarded/prototype-only.
