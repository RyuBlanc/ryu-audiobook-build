# Stage 4 — Step 1 Execution Ledger

**Working branch:** `stage-4/step-1-pronunciation-studio`  
**Base:** Build Windows App #1998, commit `6034fc8cb71ed3c994482983d1467d3ae8cedc57`  
**Scope:** PS-01 through PS-11 implementation and automated evidence  
**Artifact policy:** no package checkpoint until the Step 1 focused and full regression gates pass.

## Substep status

| Substep | Requirement coverage | Status at implementation commit |
|---|---|---|
| 1.1 | PS-01, PS-02 — Dictionary-only main screen and exact six-column table | Implemented; matching-head CI pending |
| 1.2 | PS-03, PS-05, PS-07 — all-applicable-scope search, Add/Edit/Delete, bulk delete, stable scope identity | Implemented; matching-head CI pending |
| 1.3 | PS-06 — Analyze saved book text, confirmed character names/aliases, deduplication, disabled AI review queue | Implemented; matching-head CI pending; analyzer remains conservative |
| 1.4 | PS-04 — saved-profile preview of Written and Pronounce as; pause/replay | Implemented; automated/packaged and real-profile listening evidence pending |
| 1.5 | PS-08, PS-09 — individual Enable and synchronized project-level global switch | Implemented; matching-head CI pending; real synthesis ON/OFF listening pending |
| 1.6 | PS-10, PS-11 — AI/manual provenance and row highlighting; acceptance matrix | Implemented in UI/backend; matching-head CI pending; target-PC multilingual listening remains separate |

## Functional flow covered

1. Pronunciation Studio loads saved Current Book entries, only the active project's matching Series entries, and Global Library entries.
2. Search and origin/scope filters operate on that complete fetched list; the visible S.No is recalculated after filtering.
3. Manual Add/Edit persists the selected scope and keeps its manual/AI origin. Editing a written form updates the same record instead of silently creating a second row.
4. Analyze Book reads saved chapter text and confirmed Character Studio names/aliases, removes candidates already present in any applicable scope, and presents editable AI drafts separately. Accepting a draft saves it disabled; it never activates a pronunciation without review.
5. Each row previews the Written and Pronounce as text using an explicitly selected saved Voice Studio profile. Pause and Replay operate on the generated audio.
6. Single and bulk deletion address exact written-term/scope identities. Individual Enable updates only that row.
7. Pronunciation Studio and Production Studio Generate share one project-state setting. Global OFF makes the shared synthesis resolver return no pronunciation rules; Global ON retains per-entry Enable filtering and Current Book → matching Series → Global precedence.
8. AI-origin entries use a gold row accent; manual entries use a green row accent.

## Preservation constraints

- Existing Premium V2 layout language and navigation are retained; no application rewrite.
- Existing source text, dialogue spans, substitution ordering, generation signatures, and chapter checkpoint invalidation logic are not replaced.
- Sound Design / Music Library implementation is not modified.
- Historical Stage 4 PR #19 is not merged or used as a base.
- The #1998 Stage 3 artifact remains the base; all Step 1 changes are isolated to this branch.
- No Windows artifact checkpoint is claimed by this ledger.

## Acceptance boundary

Green CI can establish automated contracts only. PS-04 and PS-11 still require listening to real generated audio with multiple installed profiles, foreign-language names, scope conflicts, ON/OFF comparisons, and preview/final consistency on the target PC. This ledger must be updated with the exact Windows CI run, commit SHA, test counts, and any failed-test root cause after CI completes.
