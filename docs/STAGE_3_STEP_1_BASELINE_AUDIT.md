# Stage 3 — Step 1: Baseline implementation and integration audit

**Audit date:** 31 October 2026  
**Canonical working branch:** `stage-3/restart-from-stage2-closeout-1794`  
**Canonical base commit:** `b47c0fbd377ceddbcb15006cec1ccab5096f522b`  
**Protected package baseline:** Stage 2 final closeout run [#1794](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41176587678)  
**Audit scope:** VS-01…VS-08 and CS-01…CS-08 (16 requirements).  
**Supersedes:** The older `docs/STAGE_3_VOICE_STUDIO_CHARACTER_ASSIGNMENT_PLAN.md` as the live Stage 3 execution status. That older file remains unchanged as historical material.

## 1. Baseline lock and evidence

The restart branch was created directly from the Stage 2 final closeout commit. GitHub comparison returned `identical` (0 ahead / 0 behind) before this audit commit. The Stage 2 files below were verified present at the new branch tip:

- `docs/STAGE_2_SOUND_DESIGN_INTERACTIVITY_REPAIR.md`
- `tests/stage2_packaged_sound_ui_acceptance.js`
- `tests/packaged_sound_ui_acceptance.py`
- `tests/test_stage2_cue_gating.py`
- `tests/test_stage2_bgm_strategy.py`

### Stage 2 closeout evidence

| Evidence | Verified value |
|---|---|
| Branch | `stage-2/sound-design-music-library-post-stage1` |
| Commit | `b47c0fbd377ceddbcb15006cec1ccab5096f522b` |
| Run | [#1794](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41176587678) |
| Full regression | 859 tests passed in 36.283 seconds |
| Packaged Sound Design / Music Library acceptance | Passed |
| Frozen app / bundled assets / installer / Defender | Passed |
| Installer artifact | 877,996,412 bytes; artifact ID 13033283025 |
| Portable artifact | 1,349,563,803 bytes; artifact ID 13033875926 |
| SHA-256 manifest | 777 bytes; artifact ID 13032988458 |

Artifact sizes and IDs above are from the successful upload logs for #1794. They are not the unrelated Stage 3 build #1821 artifacts.

### Strict source-selection rule

1. All Stage 3 work must be committed only to `stage-3/restart-from-stage2-closeout-1794`, descended from `b47c0fbd377ceddbcb15006cec1ccab5096f522b`.
2. Do not checkout, merge, cherry-pick, rebase from, copy code from, or build artifacts from any quarantined Stage 3 / Stage 4 branch.
3. Do not use the old Stage 3 branch, the old Stage 3 integration branch, the premature Stage 4 branch, or build #1821 as a code or installer baseline.
4. Before every test or package gate, verify repository, branch, commit SHA and parent ancestry. Before any artifact is accepted, verify the run's exact head SHA and the artifact names/sizes against that same run.
5. Stage 2 files and acceptance tests remain part of the regression gate. Do not close or skip a Stage 2 gate to make Stage 3 green.
6. This Step 1 commit changes only this audit document and the workflow branch allow-list. It does not change application/runtime source or produce a package.

## 2. Existing implementation inventory

| Area | Existing code on the locked Stage 2 source | Current evidence / notes |
|---|---|---|
| Voice Studio UI | `app/ui/voice_page.py`; `assets/frontend/premium_v2_backend_adapter.js`; Premium V2 HTML | Provider/profile selection, voice save, preview, progress, playback and duration surfaces exist. |
| Voice profile persistence | `app/tts/voice_profile.py`; `app/ui/premium_v2_host.py` | Saved profiles preserve provider, voice ID, language, model/backend, reference/authorization data and Qwen mode/prompt/seed/anchor/profile identity. |
| Provider binding | `app/tts/profile_provider.py`; `app/tts/cast_provider.py` | Saved profile creates the provider; cast router can route saved dialogue assignments to character profiles and keep narrator fallback separate. |
| Character data and learning | `app/chapters/characters.py`; `app/chapters/character_learning.py`; `app/core/character_library.py` | Analysis, aliases, reusable series records and source-backed learning records exist. |
| Character Studio UI | `app/ui/voice_cast_page.py`; `app/ui/native_character_studio.py`; Premium V2 adapter | Manual / AI / assigned views, project data loading, filters, dialogue selection and profile controls exist. |
| Assignment persistence | `app/ui/premium_v2_host.py` handlers `_chapter_dialogue_assign`, `_chapter_dialogue_unassign`, `_character_assign` | Exact source offsets are validated; assignment saves to active project; stale/overlapping spans are guarded. |
| Preview pipeline | `app/tts/preview.py`; host `_voice_preview`, `_preview_worker`; native `VoicePreviewWorker` | 10/30/60/90 duration choices, elapsed status, measured duration, cancel checks, profile identity and Qwen worker/cache paths exist. |
| Expression | `app/tts/expression.py`; `app/tts/providers/qwen_character.py` | Text expression classification and stable-identity instruction presets exist; Qwen uses expression-sensitive chunking. |
| Contextual effects | `app/audio/story_events.py`; `app/audio/assembler.py`; `app/tts/manager.py` | Explicit text-triggered story events are time-aligned to chunk audio and mixed separately from the three fixed book cue slots. |
| Pronunciation | `app/tts/pronunciation_suggester.py`; host dictionary handlers; `app/tts/narration.py`; preview/generation | Scoped entries, manual enablement, Unicode-aware substitution and application to preview/full generation exist. |

## 3. Requirement-to-code-to-test matrix

**Status meanings:** *Partial* means a real implementation/test foundation exists but one or more stated acceptance conditions are missing or unproven. *Open* means the required behavior is not established by the current source. No row is considered fully accepted from this audit alone.

| Requirement | Existing code / test evidence on this source | Audit status | Concrete gap / acceptance still required |
|---|---|---|---|
| **VS-01 — Preview under 60 seconds for 30-second audio** | `voice_page.py` has 10/30/60/90 options and a shared Qwen preview lock/cache. Host `_preview_worker` reports setup, synthesis, total seconds, measured audio duration and `performance_target_met`. Tests: `test_stage823_preview_duration_acceptance.py`; preview timing tests in `test_stage4_voice_preview_contract.py`. | **Partial** | Test fixtures prove duration logic and batching behavior, not sub-60-second performance on the actual target PC / model / provider. Run a measured hardware matrix after the functional fix work; preserve audio quality and report model load separately from synthesis. |
| **VS-02 — Consistent voice identity** | `VoiceProfile`, `ProfileBoundProvider`, `CastAwareProvider`, Qwen identity/profile IDs and generation signatures. Tests: `test_stage5_voice_identity.py`, `test_stage3_voice_character_regressions.py`, `test_premium_v2_voice_save.py`. | **Partial** | Automated signatures and routing safeguards exist. Need end-to-end selected-profile preview vs chapter/full-book output listening, multiple chapters/paragraphs, cast switching, reload and narrator-independence acceptance. |
| **VS-03 — Story-aware emotion** | `app/tts/expression.py` defines cue labels and text classification; Qwen provider splits on expression changes and uses four stable reference-style families. | **Partial** | Current classification is English-regex-led and maps nuanced labels into four acoustic families. The requested happy, laughter, sadness, crying, anger, fear/tension, surprise, bored, calm and serious outcomes are not each behaviorally/audio validated; some have no distinct detector. Need multilingual/context examples, stable identity and neutral false-positive tests. |
| **VS-04 — Contextual story effects / background events** | `story_events.py` detects explicit English phrases for actions/ambience (e.g. footsteps, doors, rain, thunder, crowd, sword, explosion, gasp); assembler positions and limits effects using actual chunk durations. Fixed opening / next-chapter / closing cues remain separate; scene transition is explicitly not a fourth fixed slot. | **Partial** | Events are conservative phrase/regex matches, not semantic story comprehension. Procedural effects are synthesized; human laughter/crying/dialogue/background voices requested in the master list are not evidenced as supported event classes. Need direct detector/mixer tests for every accepted event, false positives, offsets, overlap, level, chapter boundary and Voice Only. |
| **VS-05 — Emotion/effects usable across supported profiles and projects** | Story effects are configured from saved project settings and applied in the common audiobook assembly path. Qwen expression path is provider-specific. | **Open / Partial foundation** | There is no evidence that the emotion behavior applies consistently across every supported provider/profile. Project-level effect settings are present, but cross-provider, cross-project and selected-character-context behavior needs explicit integration tests and implementation. |
| **VS-06 — Multilingual names and pronunciation rules** | Host pronunciation analysis/save/delete/list; current-book, series and global entries; `narration.py` applies scoped enabled entries; preview and production pass the effective dictionary. Tests: `test_stage4_pronunciation_dictionary.py`, `test_stage4_pronunciation_persistence.py`, `test_pronunciation_candidate_guard.py`. | **Partial** | Japanese/Unicode and candidate guards have unit coverage, and suggestions are disabled pending review. Need real multi-language novel samples, name/alias/context grounding, user correction, preview and full generation, and no unrelated-word substitution. |
| **VS-07 — Pronunciation must preserve emotion/timing/identity** | Pronunciation replacement is applied to a narration copy; original source text and cast offsets are preserved before substitutions. Tests: `test_stage4_pronunciation_application.py`, `test_stage4_pronunciation_dictionary.py`. | **Partial** | Unit tests cover text, offsets and invalidation, not rendered audio quality, pause/prosody/emotion or cross-provider identity after replacement. Must compare affected/unaffected lines and chapter output. |
| **VS-08 — Carry 15 earlier Voice Studio fixes** | Evidence includes preset-friendly-name/profile identity tests, selected-profile preview tests, provider catalogue/filter stability tests, playback/download contracts, supported duration/default tests, elapsed telemetry, warm Qwen worker/cache tests and native/HTML no-overlap / stable-update tests. Main files: `voice_page.py`, `premium_v2_host.py`, Premium V2 adapter. | **Partial** | The code/test foundation is present for the 15 register items: preset name; saved identity/load; preview voice/Voice State; Preview & Assign selection; ready gating; playback/download; Character Studio assignment; provider filters; flicker-free switching; 10/30/60/90; 30s default; elapsed time; bounded worker reuse; safe wizard switching during synthesis; sidebar title/save status. Still need one end-to-end regression matrix and target-PC acceptance for every item; no item is accepted merely from source inspection. |
| **CS-01 — Real active-project Assigned Cast** | Host `_character_list` reads saved characters for `_active_project()`. Premium V2 renders real name, series, aliases, assigned voice, dialogue and chapter counts; assigned search includes name, series, role, aliases and voice profile. | **Partial** | Verify that the displayed population matches the intended Assigned Cast definition (including whether unvoiced project cast rows should appear), counts only valid saved spans, and search/reload behavior on target UI. |
| **CS-02 — Project isolation and live assignment refresh** | Assignment handlers save to the active project; frontend assignment flow refreshes chapters, characters and library; project-bound native page loads state from active project folder. | **Partial** | Need explicit browser/native switch-project, save-vs-unsaved, assignment/unassignment, close/reopen and second-process persistence tests that assert zero cross-project leakage and correct empty-state transitions. |
| **CS-03 — Audio Profile dropdown / preview-only selection** | Premium V2 populates the character Audio Profile selector from saved Voice Studio profiles. The selector has an explicit Save Profile action; preview uses the selected saved profile. Backend `character.assign` updates only the selected character record; narrator changes use a separate `voice.select` command. | **Partial** | Add tests proving dropdown selection alone never writes narrator or another character; explicit Save changes only the selected character; deleting/renaming/refreshing profiles keeps the selector correct. |
| **CS-04 — Test actual selected character dialogue** | `testSelectedCharacterVoice()` calls `previewSavedProfile` with a saved profile, and native Voice Cast has an assigned-sentence test using the preview worker. | **Open / Partial** | Current Premium V2 test action chooses `savedPassages[0]` (first saved passage) or example fallback, rather than a specifically selected dialogue row. Need exact selected dialogue row/profile binding, progress, play/pause/stop/replay, preview cache/reuse and stale-selection race checks. |
| **CS-05 — Four cast statistics including AI Assigned %** | Inspector currently shows assigned voice, dialogue line count, distinct chapter count and a confidence percentage. Dialogue count derives from saved source spans. | **Open** | The fourth metric is currently confidence, not AI Assigned %. In addition, the manual assignment backend marks saved assignments `source="manual"`; the AI high-confidence acceptance path also calls that same assignment handler without an AI source marker. This loses AI-vs-manual provenance. Preserve source at acceptance and compute AI lines / all assigned lines × 100 from saved source metadata, not confidence; count each chapter once. |
| **CS-06 — Show AI and manual dialogue for selected character** | Character Studio has separate manual and AI modes, source-backed suggestion rows and saved assignment rows; the project dialogue list is built from active chapter text and exact spans. | **Partial** | Need one selected-character dialogue view that includes both confirmed AI-origin and manually assigned dialogue from the current project, and allows a specific row to be selected for Test Voice. Current Assigned Cast inspector samples saved passages; AI suggestions are reviewed in a separate queue. |
| **CS-07 — Distinct AI/manual row highlighting** | CSS contains green `.is-assigned` / confirmed and gold `.review` / `.is-ai-review` styles. | **Partial** | The live story renderer attaches `.is-assigned` for saved rows but does not attach `.is-ai-review` there; source provenance is also lost when AI acceptance is written as manual. Need source-aware full-row classes, stable selection styling that preserves the source tint, and visual tests for selected/unselected AI and manual rows. |
| **CS-08 — Persist assignments and preserve routing identity** | Assignment handlers validate source offsets/text, save project state, preserve aliases on rename, scope character names by series, block deleting in-use voice profiles, and cast-aware production uses saved profile routing with narrator fallback. Tests: `test_stage3_dialogue_assignment_persistence.py`, `test_stage3_voice_character_regressions.py`, `test_character_learning_memory.py`, `test_dialogue_assignment.py`. | **Partial** | Need explicit close/reopen and second-process tests across navigation/profile edit/project switch, plus rename/delete/reorder/merge/split integrity. Audit risk: `_character_delete` removes the project cast row but has no corresponding chapter-assignment cleanup in that handler; verify and define a safe behavior before accepting delete. |

## 4. Important code-level findings to address first

1. **AI/manual provenance is currently not reliable.** AI “accept high confidence” sends `chapter.dialogue.assign`; that backend path stores the passage with `source="manual"`. This blocks trustworthy CS-05 AI percentage and CS-07 styling until provenance is retained across save/reload.
2. **CS-05 has a visible metric mismatch.** The inspector renders confidence as its fourth metric. The requirement calls for AI Assigned %, calculated from saved AI-source dialogue assignments.
3. **CS-04 does not use an explicitly selected passage in Premium V2.** Its test action takes the first saved assignment. The fix must bind the actual selected line and current selected saved profile.
4. **CS-06/CS-07 are not yet one coherent per-character source-aware dialogue inspector.** AI and manual surfaces exist, but the selected-character list, source marker and selected-row highlight need to be connected.
5. **VS-03/VS-04 are partial heuristic foundations.** Emotion cues and story effects exist; language coverage, semantic false positives, missing event types, cross-provider behavior and audio acceptance are open.
6. **VS-01 is instrumented, not proven on the user's PC.** CI timing mocks and deterministic WAV tests are not hardware performance evidence.
7. **Character delete may leave stale chapter spans.** Treat this as a data-integrity risk to test before changing behavior; do not silently delete unrelated dialogue.

These findings are source-audit observations. They are not claims that every UI/runtime failure has already been reproduced.

## 5. Existing regression tests to reuse (do not duplicate without a gap)

| Test file | Existing coverage to retain |
|---|---|
| `tests/test_premium_v2_voice_save.py` | Saved profile persistence, alias-of-built-in handling, authorization and reference-audio requirements, in-memory preview profile. |
| `tests/test_stage3_dialogue_assignment_persistence.py` | Exact source spans, offsets, stale/duplicate/overlap rejection, manual/multi-speaker assignment, cast routing and unassignment. |
| `tests/test_stage3_voice_character_regressions.py` | Character metadata, aliases/rename, character profile routing, narrator fallback, missing profile and protected profile deletion. |
| `tests/test_live_character_studio_contract.py`; `tests/test_native_character_studio_contract.py` | Live/native Character Studio data flow, series/profile selection, source-backed suggestions and real preview entry points. |
| `tests/test_character_learning_memory.py`; `tests/test_dialogue_assignment.py` | Source-grounded, series-isolated learning and saved assignment integrity. |
| `tests/test_stage4_voice_preview_contract.py`; `tests/test_stage823_preview_duration_acceptance.py`; `tests/test_stage4_preview_assembly.py` | Selected profile, 10/30/60/90 durations, actual duration validation, cancellation, batching/cache and playback/preview safeguards. |
| `tests/test_stage5_voice_identity.py` | Narrator/character profile generation signatures and stable identity inputs. |
| `tests/test_stage4_pronunciation_dictionary.py`; `tests/test_stage4_pronunciation_persistence.py`; `tests/test_stage4_pronunciation_application.py`; `tests/test_pronunciation_candidate_guard.py` | Unicode/scoped pronunciation rules, source preservation, offset and cache invalidation behavior. |
| `tests/test_stage4_sound_design_catalogue.py`; `tests/test_stage828_sound_design_preview.py` | Real audio catalogue, cue persistence, BGM strategy, full-book preview and Voice Only constraints. |
| Stage 2 packaged acceptance files | Must remain in every relevant full build/regression checkpoint. |

Do not create duplicate tests for an already-proven contract. Add targeted tests for the gaps in section 4 before changing their implementation.

## 6. Stage 3 complete execution order

The requirement register remains authoritative. The sequence below is the agreed 10-step delivery plan; Step 1 is this audit, not permission to skip any later requirement.

| Step | Workstream | Requirement IDs | Closure gate |
|---|---|---|---|
| **1** | Existing implementation and integration audit | All 16: VS-01…08, CS-01…08 | Branch/source lock, requirement→code→test matrix, failed/gap register, baseline tests. |
| **2** | Character data and assignment foundation | CS-01, CS-02, CS-08 | Project isolation, provenance-preserving persistence, assignment lifecycle and restart regression. |
| **3** | Assigned Cast and statistics | CS-01, CS-02, CS-05, CS-06, CS-07 | Correct four metrics, AI/manual provenance, selected-character dialogue list and row styling. |
| **4** | Voice Profile integration | CS-03, VS-02, VS-08 | Saved profiles from Voice Studio, preview-only selection, explicit assignment save, narrator isolation. |
| **5** | Actual character dialogue testing | CS-04, VS-02 | Exact selected dialogue/profile audition, job status, playback controls, cache and selection-race tests. |
| **6** | Voice identity and preview stability | VS-02, VS-08 | Same selected profile/identity from preview through chapter/full generation; profile changes and navigation/restart. |
| **7** | Voice preview performance | VS-01 | Real timing breakdown for 30-second preview; target under 60 seconds where machine/model permits; no quality regression. |
| **8** | Emotion and contextual sound effects | VS-03, VS-04, VS-05 | Emotion coverage, story-event detection/mix, supported providers/projects, source-timed effects and false-positive tests. |
| **9** | Pronunciation and emotion compatibility | VS-06, VS-07 | Multilingual dictionary/AI recommendations/manual corrections; preview/full-gen pronunciation and prosody listening. |
| **10** | End-to-end integration and acceptance | All 16 | Combined project→voice→cast→dialogue audition→save/reopen→production generation flow, full regression, packaged app and target-PC checks. |

## 7. Mandatory test and artifact gates

- **A — Focused tests:** Add/reuse targeted behavioral tests for each fix. Test the changed behavior and its negative cases.
- **B — Cross-module tests:** Voice Studio ↔ profile catalogue ↔ Character Studio ↔ dialogue assignment ↔ cast router ↔ Production generation.
- **C — Full regression:** Run `python -B -m unittest discover -s tests -v` and frontend JavaScript syntax checks, retaining the complete logs. Preserve Stage 2 packaged SD/MUS acceptance in the package gate.
- **D — Windows artifact checkpoint:** Only after A/B/C pass. Use an explicit `[artifact-checkpoint]` commit on this exact restart branch. Verify the artifact run's head SHA equals the intended source SHA and its installer/portable/manifest are from that run.
- **E — Installed application acceptance:** Confirm on the user's Windows machine with actual saved project, installed models, voice preview, assignment, project switch/restart and representative audio listening. CI success alone cannot close this gate.

For every failure: capture the exact run, failed step, failing assertion/log and source SHA; fix the cause with a regression test; rerun the smallest failing test first; then rerun the full relevant gate. Do not repeat an unchanged failing run and do not discard failure evidence before a successful checkpoint.

## 8. Step 1 outcome

The current source has significant pre-existing implementation worth retaining, so Stage 3 does **not** need a blind rewrite. However, the audit confirms the requirements above are not yet fully accepted. The first implementation priorities are AI/manual provenance and CS-05 statistics, selected-line test binding (CS-04), the selected-character dialogue list/source styling (CS-06/CS-07), and profile/project lifecycle coverage (CS-02/CS-03/CS-08). VS requirements remain in the same stage and must be completed in Steps 4–9.

**Step 1 is the baseline audit. It does not close Stage 3 and does not authorize packaging.**
