# Stage 3 — Step 1 Baseline and Requirement Traceability Audit

**Audit date:** 2026-10-31  
**Active branch:** stage-3/stage2-checkpoint-integration  
**Audited HEAD:** ee1a5d990effa1dff24a3848a1f9cf5bf07717cb  
**Stage 2 checkpoint:** b47c0fbd377ceddbcb15006cec1ccab5096f522b  
**Scope:** Voice Studio VS-01–VS-08 and Character Studio CS-01–CS-08, including production and pronunciation integration.

## 1. Audit method

The official IDs in the master bug/change register are retained. This audit does not replace them with new IDs.

Evidence levels:
- **Code present:** a relevant backend/frontend path exists.
- **Automated test present:** a named test covers part of the behavior. Source-text assertions and mocks are not treated as proof of real UI/audio behavior.
- **Runtime acceptance open:** packaged Windows behavior with real project data, supported providers and real audio still needs verification.
- **Gap/blocker:** a concrete implementation defect or missing capability was found.

A green test or successful package build is not sufficient evidence of end-to-end acceptance.

## 2. Baseline integrity

The active Stage 3 branch is **9 commits ahead** of the Stage 2 checkpoint and **0 commits behind** it. The merge base is the Stage 2 checkpoint. The branch comparison shows changes only in:
- .github/workflows/build-windows.yml
- app/ui/premium_v2_host.py
- assets/frontend/premium_v2_backend_adapter.js
- tests/test_premium_v2_integration_contract.py

The Stage 2 checkpoint and the older stage-3/voice-studio-character-assignment branch were not merged or rewritten during this audit.

Artifact checkpoint **run #1799** has uploaded the Windows installer, portable package and SHA-256 manifest. These files prove packaging completed; they do not prove the installer was launched or that Voice Studio / Character Studio were manually accepted on the target PC.

The earlier regression gate **run #1798** was reported successful. This audit did not rerun it. No feature code was changed during Step 1.

## 3. Voice Studio audit

| Requirement | Existing implementation and tests | Status / remaining evidence |
|---|---|---|
| **VS-01 — 30-second preview under 60 seconds [P0]** | voice_page.py has a shared Qwen preview lock/cache, target-duration worker, elapsed-time reporting and progress phases. premium_v2_host.py validates 10/30/60/90-second targets, queues preview work, measures setup/synthesis time and supports cancellation. Qwen batching and fallback paths exist. Tests include test_timed_preview_uses_target_duration_and_live_progress, test_qwen_voice_preview_reuses_warm_provider_and_replaces_changed_profile, test_qwen_voice_preview_restarts_a_dead_cached_worker and test_stage823_preview_duration_acceptance. | **Partially implemented; P0 runtime gate open.** The duration acceptance uses a mock/fast provider, not a real Qwen performance benchmark. No current supported-PC measurement proves that a 30-second Qwen preview completes in under 60 seconds. Measure total elapsed time, actual generated duration, cold/warm model behavior, resource use, cancellation and UI responsiveness without reducing voice quality. The register's historical reference was about 266.5 seconds synthesis for 34.6 seconds of audio; this is not a current measurement. |
| **VS-02 — Preserve character voice identity [P0]** | voice_profile.py persists Qwen profile/anchor identity fields. expression.py provides a VoiceDesign identity instruction and expression-reference families. qwen_character_worker.py creates/reuses identity references. Production/preview signatures include voice configuration and cast assignment state. Tests include test_qwen_voice_consistency_uses_design_anchor_and_base_prompt, test_voice_design_anchor_instruction_preserves_identity_and_mood_range, test_qwen_resume_signature_tracks_exact_voice_configuration and test_cast_signature_changes_when_saved_qwen_identity_changes. | **Partially implemented; P0 listening acceptance open.** These tests establish code contracts/signatures, not perceived voice identity. Compare one saved character across Voice Studio, Character Studio, several sentences/paragraphs/chapters and full production output. Check pitch, timbre, accent, selected provider/model/profile, stale Voice State and switching profiles during synthesis. |
| **VS-03 — Emotion-aware narration [P1]** | expression.py classifies text cues and exposes multiple delivery labels mapped to four acoustic reference families. Existing labels include thoughtful, warm, concerned, excited, soft, sad, angry, tense, curious, amused, serious and reflective. Qwen splits work at reference-family changes. Tests cover expression classification/mapping and chunking. | **Partial; category coverage gap.** The ten register categories are not represented as ten distinct contextual outcomes. There is no dedicated bored classification/style; crying/sobbing collapses to sadness; laughter maps to amused; happy/surprised/calm use broader styles. Verify all ten named cases, story context, intelligibility and identity preservation. |
| **VS-04 — Story-aware background effects and voices [P1]** | app/audio/story_events.py detects text-positioned cues and has local effects for footsteps, doors, knocks, rain, thunder, wind, birds, waves, fire, crowd ambience, sword clashes, magic, explosions, horse hooves, heartbeat, gasps, glass break and water splash. assembler.py overlays enabled effects without extending book duration. Tests cover event detection, metaphor rejection, generated effects and mixing. | **Partial; content coverage and mix acceptance open.** Action/environment effects exist, including crowd ambience and glass breaking. The inspected event catalogue has no dedicated character-laughter or crying/sobbing effects; a crowd ambience cue is not proof of intelligible background voices. Verify narrative placement, duplicate suppression, level/ducking against dialogue and separation from fixed Opening/Next Chapter/Closing cues. Do not reintroduce the removed Scene Transition assignment. |
| **VS-05 — Make emotion and effects global [P1]** | Emotion classification/reference handling and story-effect generation are shared services; project sound-effect settings are persisted. | **Partially evidenced; cross-provider integration open.** The inspected code establishes Qwen expression handling and shared story-effect infrastructure, but not the complete behavior across every supported Voice Studio provider/profile and separate projects. Test selected character, current passage, story context, project switches and production generation for each supported provider. |
| **VS-06 — Accurate multilingual pronunciation [P0]** | pronunciation_suggester.py has conservative proper-name detection and deterministic Japanese/Korean/Chinese phonetic helpers. premium_v2_host.py has pronunciation list/save/delete/analyze endpoints and current-book/series/global stores. narration.py applies enabled phrase-aware rules and reports substitutions. Tests cover candidates, scope, audio-test controls, case/phrase handling and disabled entries. | **Partial; P0 AI recommendation/language-context gap.** The current pronunciation-analyze endpoint extracts names and calls deterministic suggest_pronunciation; it does not call an AI recommendation service and marks suggestions Auto-detect/review-required. Japanese phonetic conversion exists when a language is explicitly supplied, but the analyze path does not establish that language context. Verify Japanese names, English-written fantasy terms, manual correction, enabled-only scope behavior, preview and full-generation audio, and false-positive rejection. |
| **VS-07 — Emotion and pronunciation must cooperate [P1]** | Pronunciation substitutions happen during narration preparation; expression classification and pacing are separate services. | **Partially evidenced; combined audio gate open.** The inspected tests cover pronunciation and expression separately, not the combined emotional-pronunciation result. Test corrected names inside emotional dialogue and across sentence/chunk boundaries for timing, naturalness, intelligibility and unchanged character identity in preview and full generation. |
| **VS-08 — Preserve all previous Voice Studio fixes [P0]** | Current branch includes saved-profile metadata, preview-ready gating, progress/elapsed time, Qwen cache/lock and duration selection. Existing tests cover profile round-trip, cache, timing and the four-stage layout. | **Partially evidenced; full runtime verification remains open.** The 15 carried-forward items are mapped below. |

### VS-08 carried-forward items

| ID | Required behavior | Audit finding |
|---|---|---|
| VS-08.1 | Correct Qwen VoiceDesign preset naming | Naming/profile code and regression tests exist; verify saved name in packaged UI. |
| VS-08.2 | Saved profile identity/loading | Profile identity metadata and round-trip tests exist; restart/edit acceptance remains open. |
| VS-08.3 | Correct preview voice and Voice State | Selection/signature safeguards exist; spoken voice and displayed Voice State need hands-on confirmation. |
| VS-08.4 | Correct selected voice in Preview & Assign | Source selection path exists; verify exact profile selection in packaged flow. |
| VS-08.5 | Preview controls unavailable until audio is ready | Adapter gates playback/use/download/assignment on preview validity; verify ready/failed/cancelled transitions. |
| VS-08.6 | Preview download and playback | Output/play/download handlers exist; verify a real generated file and failure recovery. |
| VS-08.7 | Correct Character Studio assignment | Saved-profile and character-assignment paths exist; see CS-03/CS-04 and end-to-end gates. |
| VS-08.8 | Correct provider filters | Provider resolution/filter code and provider-selection regression coverage exist; verify every supported provider in packaged UI. |
| VS-08.9 | No visible wizard-transition flicker | No visual/runtime acceptance evidence was established in this audit. |
| VS-08.10 | 10/30/60/90-second preview choices | Current branch code and backend validation use these four values; source tests exist. |
| VS-08.11 | Default preview is 30 seconds | Current branch sets 30 seconds; source test exists. |
| VS-08.12 | Display elapsed synthesis time | Worker measures elapsed time and emits status; source test exists. |
| VS-08.13 | Bounded Qwen preview-worker reuse | Shared lock/cache and cache-replacement/worker-restart tests exist; verify memory/VRAM bounds over repeated real previews. |
| VS-08.14 | Safe panel switching during synthesis | Request invalidation/worker safeguards exist; the panel-switch race has not been accepted during a live synthesis. |
| VS-08.15 | Correct project/sidebar title and save status | Live project/save-state acceptance was not established in this audit; verify saved/unsaved transitions and navigation. |

## 4. Character Studio audit

| Requirement | Existing implementation and tests | Status / remaining evidence |
|---|---|---|
| **CS-01 — Real Assigned Cast list [P1]** | _character_list reads the selected project's saved character state. The adapter builds the inspector from active-project characters, aliases, series and assigned dialogue. Existing cast tests cover name/alias/series cases; Stage 3 contract tests cover the inspector. | **Partially implemented.** Verify no sample/stale rows, correct name/series/dialogue count, and search by name, alias and assigned voice in packaged UI. |
| **CS-02 — Project isolation/live assignment data [P1]** | Character/assignment writes use the active project and persist project state. Refresh paths rebuild the inspector from the current cast/chapters. Profile selection remains a draft until explicit save. | **Partially implemented.** Existing tests cover series-scoped identity and the Stage 3 contract checks draft-versus-save. Still run a two-project isolation test, switch projects repeatedly, save/edit/remove assignments and reopen after restart. |
| **CS-03 — Audio Profile dropdown [P1]** | Saved Voice Studio profiles are exposed by the voice catalogue and used by the Character Studio selector. The selected value is kept separate from the saved assignment until explicit Save profile. Character assignment writes character profile state, not the narrator field. | **Partially implemented.** Verify every saved profile appears with correct identity; preview uses the selected draft profile; narrator and other characters remain unchanged until the correct save action. |
| **CS-04 — Test selected character dialogue [P1]** | testSelectedCharacterVoice resolves the selected character, profile and selected assigned passage, then calls previewSavedProfile(profile, sample, current.name). | **BLOCKER found.** testSelectedCharacterVoice is declared at adapter line 5265, outside wire(). The only previewSavedProfile declaration is a const local inside wire() (wire starts at line 6357; helper is at line 7610). The caller cannot access that inner lexical binding. Test Voice will fail with an unresolved previewSavedProfile reference unless the helper is moved to a shared scope or the caller is routed through a shared preview service. The current helper always queues a new 10-second preview; pause/stop/resume/replay and reuse of a completed valid preview are not established. The Stage 3 source-contract test checks that the call exists but does not execute it. |
| **CS-05 — Assignment statistics [P1]** | Adapter derives assigned passages from saved project chapter assignments, counts distinct chapter numbers, and computes AI-assigned percentage from assignment-source metadata. Backend accepts AI provenance only when the selected suggestion matches the saved chapter, speaker, offsets and exact source text. | **Partially implemented.** Stage 3 source-contract test checks the calculation/provenance contract. Verify mixed AI/manual fixtures, zero assignments, repeated lines in one chapter, assignment edit/removal and project switch. Do not use confidence as the percentage. |
| **CS-06 — Display selected-character dialogue [P1]** | Adapter builds selectable dialogue rows for the selected character from active-project chapter assignments, with manual and AI source metadata. | **Partially implemented.** Current inspector renders at most the first 30 assigned passages. Verify behavior for characters with more than 30 passages and confirm each selected row resolves to the exact saved source span. |
| **CS-07 — Source highlighting [P1]** | Manual rows use a green accent/subtle green background; AI rows use a gold accent/subtle gold background; selection is styled separately. | **Code present; visual acceptance open.** Verify full-row styling, selection state, contrast and source distinction in packaged UI. |
| **CS-08 — Persist assignments [P1]** | Character assignment is saved to project state; reusable series character data is updated separately; voice profiles persist in the Voice Studio catalogue; dialogue source offsets/provenance are persisted on chapter assignments. | **Partially implemented.** Complete restart/reopen, navigation, project switching and profile rename/edit/delete tests. Confirm stale profile references recover safely and full generation uses the saved character profile. |

## 5. Required cross-screen functional flow

1. Save a Voice Studio profile with correct profile/provider/model identity.
2. Preview it at 10/30/60/90 seconds; display measured elapsed time and actual audio duration; play/download the valid output.
3. Load the actual cast of the selected project in Character Studio.
4. Select a saved Audio Profile for one character without changing the narrator or another character.
5. Select a real saved dialogue passage and test it with that profile; show status and support stop/pause/replay without needless regeneration.
6. Explicitly save the character-to-profile assignment; update Assigned Cast/statistics only after save succeeds.
7. Preserve cast, aliases, dialogue offsets, assignment provenance and profile references across navigation, project changes and restart.
8. Generate production audio using the selected narrator for narration and saved character assignments for their dialogue.

| Integration edge | Current source evidence | Acceptance still required |
|---|---|---|
| Voice Studio → Character Studio | Saved profile catalogue is exposed to the adapter; profile selector exists. | Verify all saved profiles and correct metadata after save/edit/restart. |
| Character Studio → Voice Studio preview | Selected character/profile/passage are resolved, but CS-04 has the scope defect above. | Fix the scope defect and prove exact selected audio is generated and played. |
| Character Studio → Character Library | Character assignment saves reusable series-scoped library data. | Verify edits, aliases, series and assigned profile stay synchronized. |
| Character Studio → Production Studio | Preview/generation code builds cast profile and alias mappings; synthesis signatures include cast state. | Generate a multi-character real chapter and inspect voice routing, narrator separation and invalidation after profile changes. |
| Pronunciation Studio → preview/full generation | Scoped dictionary list/save/delete/analyze and narration dictionary application exist. | Verify enabled-only rules and correct spoken output with emotional dialogue in preview and full generation. |
| Stage 2 Sound Design → Stage 3 | Stage 3 is based directly on Stage 2 checkpoint; the branch diff did not remove Stage 2 screen/module files. | Preserve Stage 2 regression coverage in later commits and compare packaged Sound Design after integration. |

## 6. Confirmed limitations and documentation drift

1. docs/PREMIUM_V2_SCREEN_FUNCTION_MAP.md still describes the Voice Studio preview set as 10/20/30/45/60 seconds. That entry is stale against the current branch; current code, backend validation and tests use 10/30/60/90 with 30 as default. Update the map when implementation next touches documentation.
2. The screen function map explicitly states automatic per-line AI speaker suggestions remain prototype-only/guarded. Review/confirmation UI must not be represented as completed automatic bulk speaker assignment.
3. docs/PREMIUM_V2_KNOWN_LIMITATIONS.md records prototype inline handlers and the need for control-by-control audit. Static tests do not replace packaged UI action testing.
4. A generated Windows artifact does not prove installation, launch, actual audio playback or acceptance on the target PC.

## 7. Step 1 exit decision

**Baseline and traceability audit: complete. Feature acceptance: not complete.**

The branch is correctly based on the Stage 2 checkpoint and the artifact checkpoint has produced the expected packages. Meaningful Voice Studio, Character Studio, pronunciation and story-effect services exist, but P0/P1 requirements remain runtime-unverified. A concrete CS-04 handler-scope defect was found and must be corrected before acceptance.

Implementation order:
1. Character/project data foundation and isolation (CS-01, CS-02, CS-08).
2. Assigned Cast inspector, accurate statistics, dialogue rows and source styling (CS-01, CS-05, CS-06, CS-07).
3. Saved Voice Studio profile integration and narrator separation (CS-03, VS-02, VS-08.7).
4. Correct Test Voice flow; fix previewSavedProfile scope; implement stop/pause/replay and completed-preview reuse (CS-04).
5. Identity continuity through preview and full production (VS-02).
6. Real 30-second performance benchmark and preview lifecycle acceptance (VS-01, VS-08).
7. Complete all ten emotion cases and story-effect/background-voice coverage (VS-03, VS-04, VS-05).
8. Verify multilingual recommendations, scoping and emotional interaction (VS-06, VS-07).
9. Run combined packaged end-to-end acceptance and Stage 2 regression gate.

**Do not mark VS-01, VS-02, VS-06, VS-08 or CS-01–CS-08 complete solely because source-contract tests or a build pass. Do not declare Stage 3 complete until Section 5 is accepted.**
