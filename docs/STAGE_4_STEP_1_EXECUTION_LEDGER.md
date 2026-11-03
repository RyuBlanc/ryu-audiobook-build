# Stage 4 — Step 1 Execution Ledger

**Working branch:** `stage-4/step-1-pronunciation-studio`  
**Stage 3 base:** Build Windows App #1998, commit `6034fc8cb71ed3c994482983d1467d3ae8cedc57`  
**Latest Step 1 source candidate:** `02fc1f5d5d08f4370b111b3b81977ca4df639391`  
**Latest matching-head test gate:** Build Windows App #2010 — [run 41370768604](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41370768604)  
**CI result:** 1,009 tests passed; frontend JavaScript syntax validation passed; no failed tests; package job intentionally skipped.  
**Overall Step 1 implementation status:** <strong>IMPLEMENTED — AUTOMATED TESTS PASSED.</strong> Target-PC audio listening, real local AI analysis runtime and save/reopen acceptance remain separate runtime gates.

## Substep status

| Substep | Requirement coverage | Implementation / automated evidence | Remaining acceptance |
|---|---|---|---|
| 1.1 | PS-01, PS-02 — Dictionary is the only primary management view; exact S.No / Written / Pronounce as / Audio Preview / Options / Enable order | Implemented in the approved Premium V2 Pronunciation Studio; demo term data and Review Terms / Voice Test Matrix tabs removed. Exact six headings, no demo data, source-based row styling and renderer contract covered by the full suite on #2010. | Installed Windows UI visual acceptance at target resolution; verify the live packaged screen. |
| 1.2 | PS-03, PS-05, PS-07 — all-applicable-scope search, manual Add/Edit, single and bulk delete | Search filters the complete fetched Current Book + matching Series + Global list by Written, Pronounce as, AI/Manual and scope. Manual save/edit preserves origin; editing retains exact scope identity; bulk delete groups exact identities by scope; S.No recalculates from filtered rows. Backend persistence and UI contract tests passed on #2010. | Target-PC save/edit/delete/bulk-delete and close/reopen acceptance. |
| 1.3 | PS-06 — Analyze Book and reviewed AI suggestions | Uses the existing local `AudiobookBrain` multilingual pronunciation-analysis prompt/schema; starts a separate background job, reports progress, validates candidates against saved source text, rechecks duplicates, filters ordinary English and low-confidence suggestions, surfaces language/IPA/script/reason/confidence/alternatives, and never enables or saves before user acceptance. Mocked worker and review-flow regression tests passed on #2010. | Real local AI model availability/runtime, representative imported-book analysis and user review acceptance on target PC. |
| 1.4 | PS-04 — Saved-profile selection and Written / Pronounce as audio comparison | Profile selector is sourced from saved Voice Studio profiles and refreshed after Voice Studio profile changes. Both text variants use the selected saved profile through the real voice-preview job; row previews bypass dictionary substitutions so the comparison is literal; row-specific Pause/Replay is bound to the entry identity. Existing preview contract plus UI flow tests passed on #2010. | Listen with multiple real saved profiles; verify selected provider/voice, actual sound, playback and error states on target PC. |
| 1.5 | PS-08, PS-09 — Individual Enable and global Pronunciation ON/OFF | Individual row switch persists via `pronunciation.save`. Pronunciation Studio and Production Studio Generate share the saved per-project `pronunciation_enabled` value. The same synthesis resolver applies Global OFF/ON and individually enabled Current Book → matching Series → Global rules to preview and final generation. Persistence/application tests passed on #2010. | Target-PC ON/OFF, individual enable/disable, preview/final audio comparison, save/reopen and affected-checkpoint validation with real project audio. |
| 1.6 | PS-10, PS-11 — AI/manual distinction and pronunciation acceptance | Manual rows use green accents; AI rows use gold accents. Origin plus AI evidence is persisted through edit; stale AI results cannot overwrite or reclassify a manual entry. Duplicate checks run again when analysis completes. Automated tests passed on #2010. | PS-11 actual multilingual and target-PC audio listening campaign remains open; CI does not establish perceived pronunciation quality. |

## Functional flow implemented

1. **Open Pronunciation Studio:** the application fetches saved entries for the active project only: Current Book rows, that project's matching Series rows, then the shared Global Library rows. Other projects' Current Book rows and unrelated Series stores are not mixed into the list.
2. **Search and filter:** filter by written form, spoken form, language, scope and AI/manual origin against the complete backend-loaded record set. Filtering rerenders the table and recalculates visible S.No values without deleting hidden records.
3. **Add manually:** enter Written and Pronounce as, language/handling and scope. Save persists a Manual-origin row and its enabled state; the entry appears in the saved dictionary after refresh.
4. **Edit:** load one selected row into the editor. Save updates the exact original entry in its existing scope. A stale original identity fails visibly instead of creating a second row; provenance and AI evidence are retained.
5. **Analyze Book:** submit saved chapter text to the existing local AudiobookBrain analysis job. Progress is reported independently. Candidate output is source-grounded, confidence-checked, duplicate-checked, editable, and shown as an AI review draft. No candidate is auto-saved or auto-enabled.
6. **Accept AI recommendation:** edit Written and Pronounce as if needed, choose Current Book / matching Series / Global scope, then accept. The saved row remains AI-origin and disabled; a manual record cannot be overwritten/reclassified by a stale AI result.
7. **Preview a row:** select a saved Voice Studio profile, then generate the Written or Pronounce as text through the real preview job. The row preview explicitly bypasses dictionary rules to avoid transforming the text being compared. Pause and Replay are bound to the same row identity.
8. **Enable a rule:** the row-level switch persists that exact entry's enabled state. Disabled rules remain saved but are excluded from effective synthesis.
9. **Global setting:** either global switch saves the active project's one authoritative setting. Global OFF returns no pronunciation rules to synthesis; Global ON applies only individually enabled, applicable rules using the preserved scope precedence.
10. **Delete:** single-row delete targets its scope. Multi-select remains stable while filtering, and bulk delete removes only selected written-term/scope identities. Selection and pending AI review state are cleared on project change.
11. **Production:** Production Studio Generate reads the same project switch, and full production plus ordinary voice preview call the same effective dictionary resolver. Source chapter text, dialogue spans, cast offsets and chapter checkpoint invalidation logic remain unchanged.

## Matching-head CI history and failure corrections

All runs below are on the dedicated Step 1 branch. Regular pushes run the regression/syntax job only. The build/package job was skipped by design; no Stage 4 Windows artifact is claimed from these runs.

| Build | Run ID | Source SHA | Result | Tests | Failure / correction |
|---:|---:|---|---|---:|---|
| #1999 | 41368326623 | `b21764b5027c77a34fbe5064d9de76df7723a328` | Failure | 1,004 | Five failures: folderless analyzer harness lacked a project folder; old integration test still expected the removed demo term list; bulk-delete fixture omitted the active matching Series; empty original identity inflated duplicate count; table-heading regex matched `thead`. Corrected in follow-up commits. |
| #2000 | 41368491317 | `6e784a0e54d3cedad67c3bd8553d0f324222b738` | Failure | 1,005 | Remaining folderless analyzer harness and stale integration expectation plus duplicate-count / table-heading assertions. Corrected in the next revisions. |
| #2001 | 41368686034 | `e5fb3cf4bf5ffec46bc80feea9dbb66d2844c757` | Failure | 1,005 | Same remaining analyzer harness and old integration expectations; corrected in the next revisions. |
| #2002 | 41368937442 | `e7630561646ab1baf5e5a3e2badd28b9d452b004` | Failure | 1,006 | One test-only error: the new analyzer test used a plain lambda, then called a Mock assertion on it. Product tests passed; test fixture corrected. |
| #2003 | 41369145397 | `31d40e2a21fed6a9838f525f25eb5f5f6c09f4b0` | Failure | 1,007 | Same Mock assertion error persisted in that attempt; corrected by using a real Mock reference. |
| #2004 | 41369240067 | `19d8f86c28180e23261ca447bb25701bb8c68934` | Success | 1,007 | Syntax validation and full regression suite passed. |
| #2005 | 41369680849 | `fb0b506c0bdd8dc20708980a5d9b8f86e4aa5cab` | Success | 1,008 | Local AudiobookBrain worker and mocked review tests passed. |
| #2006 | 41369901066 | `7681c510d14f5638938f525f25eb5f5f6c09f4b0` | Success | 1,008 | Corrected Python regex/source-grounding and AI progress UI passed. |
| #2007 | 41370058903 | `3b287906d29d693ae137166155616cfae1a33062` | Success | 1,008 | Saved voice selector refresh after Voice Studio profile changes passed. |
| #2008 | 41370193788 | `9cf4e23536b85c872da14e407b4f78569ce291e2` | Success | 1,008 | AI evidence persistence and ordinary-English false-positive guard passed. |
| #2009 | 41370421630 | `2cf9e5daaec327b703be88a33a204a57fa7b61c8` | Success | 1,009 | Latest-dictionary duplicate recheck and manual-entry protection against stale AI acceptance passed. |
| #2010 | 41370768604 | `02fc1f5d5d08f4370b111b3b81977ca4df639391` | Success | 1,009 | Entry-specific Pause/Replay and stable row-identity regression contracts passed. |

**#2010 workflow details:** test job succeeded; frontend JavaScript syntax validation succeeded; `Ran 1009 tests in 41.150s`; no test failures/errors. Package job skipped by workflow conditions.

## Preservation / no-collision rules

- The new branch starts at the verified Stage 3 Build #1998 source commit and contains only Step 1 work layered on top.
- The Stage 3 branch and Build #1998 artifacts were not changed, deleted or rebuilt.
- Historical Stage 4 PR #19 was not merged or used as a base.
- Sound Design / Music Library code was not modified in Step 1.
- The synthesis substitution engine, scope precedence, source text, cast/dialogue offsets, generation signatures and chapter checkpoint invalidation logic were retained.
- No package checkpoint, release artifact or Version 1.2.0 tag has been created by Step 1.
- The Stage 4 ledger remains open for Steps 2–4 and runtime acceptance.

## Remaining Step 1 runtime acceptance — keep visible

These are not failed automated tests; they require the real installed application, saved profiles, local AI runtime and actual rendered audio on the target PC:

- PS-01/PS-02: inspect the installed Premium V2 screen and confirm the Dictionary-only interface, exact columns, row actions, colors and responsive layout.
- PS-03/PS-05/PS-07/PS-08/PS-10: exercise add/edit/delete/bulk-delete, search all scopes, individual Enable, origin styling and save/reopen with real project data.
- PS-04/PS-11: listen to Written and Pronounce as previews using multiple real saved profiles; verify Japanese/romanized and other foreign terms, character dialogue, selected voice identity, scope conflicts, enabled/disabled differences and restart/reopen.
- PS-09: listen to real synthesis with global Pronunciation OFF vs ON, compare individual switches, and compare preview against final generation.
- Verify analysis using the installed local AI model and an actual imported novel; verify model-unavailable failure is visible and does not silently create fake AI suggestions.

**Step 1 closeout rule:** implementation and automated CI are complete on #2010. Do not mark PS-04 / PS-11 or the full Step 1 runtime acceptance complete until the target-PC checks above have evidence. Do not create a packaged artifact just to relabel a Step 3 build. The next development substage is Stage 4 Step 2.1 (pronunciation-to-production connectivity audit), after this Step 1 runtime acceptance is explicitly recorded or carried forward as pending.
