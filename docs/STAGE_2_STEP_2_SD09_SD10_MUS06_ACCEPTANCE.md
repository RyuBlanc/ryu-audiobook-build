# Stage 2 — Step 2 packaged Sound Design acceptance

**Source of truth:** `RYU'S AUDIOBOOK — MASTER BUG & CHANGE REGISTER`, Sections 6–7.

**Step 2 requirement IDs:** `SD-09`, `SD-10`, `MUS-06`.

**Status at this checkpoint:** `RUNTIME ACCEPTANCE PENDING`. The matching-head regression suite has passed; the frozen Windows executable must still pass the artifact-checkpoint acceptance job before any of these three requirements can be called verified complete.

## Exact acceptance scope

| Requirement | User-visible behavior | Packaged acceptance evidence required |
|---|---|---|
| SD-09 | Cue cards show readable names, selected state and actual track information. | Two separately imported cue fixtures must render as separate cards. Each card must show the catalogue-matching title and Imported/WAV metadata. The selected card must expose its selected state and the Selected Cue panel must show the chosen item. Title and metadata rectangles must not overlap or escape the card. |
| SD-10 | Play/Pause/Replay previews the selected cue, not another library item. | The frozen app must decode and play the selected cue's own local file, advance media time, pause without advancing, resume, replay from the beginning, and stop/switch when another cue is selected. |
| MUS-06 | Selected Track shows name/source/relevant information and one Play/Pause control operates on the selected music. | The frozen app must show the selected imported music track's title, Imported source, WAV format and duration. Its own local file must play, pause, resume, and stop when another track is selected; the next preview must use the second track's file. |

## Step 1 overlap retained in this gate

These checks remain prerequisites to reaching the Step 2 flows: Sound Design navigation; Music Library import and category metadata; the nine Music Library category controls; Built-in/Imported/All source filtering; Fantasy filtering and live search; the 50% master-volume cap and saved 42% test value; explicit book-default save; and candidate selection not silently replacing that saved default.

The source-filter checks are deliberately based on the rendered catalogue rows, not the filter button's highlighted state:
- Built-in waits for a non-empty list where every row is labelled `Bundled with application`.
- Imported waits for exactly the two imported test tracks and no bundled tracks.
- All waits for both bundled and imported rows.
- Fantasy waits for non-empty Fantasy Adventure rows.

This avoids accepting an empty/intermediate render frame as a successful filter result.

## Test method

`tests/stage2_packaged_sound_ui_acceptance.js` is injected only when the opt-in acceptance environment variables are present. It uses the real Qt WebChannel bridge and the real WebEngine Audio implementation in the frozen application. The test wraps the Audio constructor only to observe the actual media elements; it does not replace the media implementation with a fake player.

`tests/packaged_sound_ui_acceptance.py` creates uniquely named music and cue WAV fixtures, points the app at a two-chapter acceptance project, launches the frozen Windows executable, validates the saved music state and distinct Music/Cue metadata sidecars, then restores the previous active-project setting and deletes the fixtures/project.

The runner is standard-library-only so it does not depend on the setup-python toolcache that can be removed during the Windows build's private Python bootstrap. The workflow probes and uses the verified private Python interpreter for this step.

## Regression evidence — corrected slider acceptance

- Branch: `stage-2/sound-design-music-library-post-stage1`
- Tested commit: `624eda83894034c1fb68f45f13bb54dfa4609bfe`
- Workflow run: [#1740 — corrected slider regression](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41063388760)
- Result: **841 tests passed**; frontend JavaScript syntax validation passed.
- The new regression contract verifies that the packaged acceptance driver focuses the actual BGM range control before editing, retains focus through the input event, and confirms both the visible and backend-saved value remain at 42%.
- The workflow's Windows `build` job was skipped on #1740 because that commit did not carry the `[artifact-checkpoint]` marker. The next checkpoint must therefore run the full Windows build and packaged acceptance on the exact new commit.

## Cue-library refresh regression — Run #1741 follow-up

- Failed packaged run: [#1741](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41064878700), commit `93ec222f6d340eb4e6710f4d5e8f7eaf3b8dc377`.
- The Windows executable build, frozen startup checks, and Music Library checks passed, including the corrected 42% save and real music preview transport. The first cue failure was that the two imported cue cards were absent from `#cueGrid`; cue playback checks were not reached.
- The native import/catalogue path had already returned both cue fixture records with `role="cue"`, `source="Imported locally"`, and `.wav` format. The renderer's `refreshSoundCues()` depended on the shared `sounds` array having been populated by a separate Music Library refresh.
- Fix commit: `6045dee0ab50f11f8fe9b252d4df927cd2b4614b` — `refreshSoundCues()` now loads `sound.catalog` and `sound.cues.get` together and checks the catalogue/cue request epochs before publishing/rendering. A regression contract was added in `tests/test_stage2_packaged_sound_ui.py`.
- The code change is committed, but it is **not verified in the frozen executable yet**. Run #1742 is the normal push validation; because its commit message lacks `[artifact-checkpoint]`, its Windows build is not enabled. A subsequent artifact-checkpoint run is required before the cue issue can be called resolved.

## Music Library stale-grid regression — Run #1743 follow-up

- Failed packaged run: [#1743](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41068423673), commit `82f16028e5d88239b32ccc5cee2ba3049d0b0196`.
- Windows executable build, frozen self-test, three Premium V2 startups, bundled Piper/Kokoro assets, and the packaged acceptance launch all passed.
- Packaged acceptance stopped at the first Music Library source filter. Native catalogue diagnostics showed 34 valid records: 32 `Bundled with application`, 2 `Imported locally`; role counts were 28 music and 6 cue. The Built-in filter button was active, but the Music Library grid contained zero rendered Select rows. This is a UI render/cache failure, not a missing native catalogue.
- Fix commit: `810314b6225dcf48bf2f0a7d8cb604a333f0a66f` — Music Library refresh now validates the actual rendered Select-row count against the filtered catalogue, and rebuilds the grid if the DOM is empty or incomplete even when the data signature is unchanged. A regression contract covers the stale-DOM case.
- The cue-library fresh-catalogue correction from `6045dee0ab50f11f8fe9b252d4df927cd2b4614b` is retained.
- The fix remains **pending frozen-app verification** until a new artifact-checkpoint run passes the Music source filters and proceeds through the cue-card/playback assertions.

## Earlier regression baseline

- Tested commit: `6696c164c152e9ae59a575578920aa8826c51449`
- Workflow run: [#1737 — Step 2 regression](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41051159974)
- Result: **840 tests passed** before the focused-slider regression contract was added.

## Evidence still required

- A successful Windows `build` job on the exact artifact-checkpoint commit.
- A successful `Run packaged Sound Design Music Library acceptance` step, including all named browser checks and the post-run project-state/sidecar validations.
- The package runner verifies WebEngine decoding, media source, playback time and pause/resume state. It does not replace a human listening check on the user's installed PC/speakers; that acoustic acceptance remains distinct.

## Scope protection

This checkpoint covers only `SD-09`, `SD-10`, and `MUS-06`, plus the retained Music Library prerequisite checks described above. It does **not** mark the remaining SD/MUS requirements, Production handoff, the complete 24-item register, or Version 1.2.0 as complete. Later work-order steps remain in scope and must retain their original requirement IDs and behavior.

## Latest regression gate

Run #1746 passed on 68c4afb: JavaScript syntax passed; 843 tests passed in 37.083s. Runs #1744 and #1745 failed on an obsolete test assertion; #1745 did not reach the Windows build. Packaged verification remains pending.

## Music/Cue cross-refresh race — Runs #1747–#1749

- [#1747](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41071765068) built and verified the frozen executable and bundled Piper/Kokoro assets successfully, but packaged acceptance failed at the Built-in Music filter. The native catalogue still contained 34 rows (32 bundled, 2 imported; 28 music and 6 cue), while the rendered Music grid had zero rows. Installer packaging was correctly skipped after this acceptance failure.
- Root cause identified from the UI event flow and request guards: `refreshSounds()` and `refreshSoundCues()` shared `soundListEpoch`. The import handler refreshes the Music catalogue and then the Cue library; a source/category refresh can overlap that sequence. The Cue refresh incremented the Music grid epoch and caused the in-flight Music render to return before rebuilding the DOM. The row-count repair alone could not repair a render cancelled before the DOM update.
- Production fix: commit `76000f9b56958b3d7ca09b0eea2f92a90d6d306b` gives cue refreshes their own `cueListEpoch`, retains the fresh native catalogue + cue-assignment load, and no longer advances or checks the Music Library render epoch. The packaged failure diagnostics now also report grid existence, signature, row count and visible text.
- [#1748](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41074194154) found one overly broad assertion in the new test: it searched for the name `soundListEpoch` even in an explanatory comment. It did not report a JavaScript syntax or application failure. The test was narrowed to forbid the actual shared-epoch operations rather than the comment.
- [#1749](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41074552773) passed on `c747fc67b68f5b88990c44f7e597a12eeb7ddb1c`: JavaScript syntax validation passed; **843 tests passed in 40.789 seconds**.
- Next gate: run the frozen Windows artifact acceptance on the green-tested source. Do not close `SD-09`, `SD-10`, or `MUS-06` until the Built-in/Imported/All/Fantasy Music filters, cue cards, and actual cue/music playback all pass in the frozen executable.

## Packaged cue-card timing investigation — Runs #1750–#1751

- [#1750](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41075207417) passed regression tests, frozen executable verification, and bundled voice/module verification. In the packaged app, **all Music Library checks passed**: Built-in, Imported, All, Fantasy and search filters; imported track selection and metadata; saved 42% BGM level; real WAV play/pause/resume and track switching; explicit book-default save; and protection against candidate selection overwriting the saved default.
- #1750 then stopped at the cue-card assertion. The driver had waited for both cue fixtures to appear in the native catalogue but immediately queried the cue DOM without waiting for the renderer. That acceptance condition was weaker than the Music Library filters, which explicitly wait for the rendered rows.
- Driver/test correction commit: `79d1f81e6c03ae00949b3539eedae8e7909dd871`. The packaged test now waits up to 15 seconds for the two exact imported cue paths in `#cueGrid`; on timeout it reports catalogue role counts, expected and rendered paths, grid existence/signature/text, selected source and search state. No application code was changed in this correction.
- [#1751](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41076814352) passed on `79d1f81e6c03ae00949b3539eedae8e7909dd871`: frontend JavaScript syntax passed; **844 tests passed in 24.362 seconds**.
- Frozen Windows verification of cue cards and playback remains pending; a new artifact-checkpoint run is required. The current successful Music Library checks must remain in the combined gate.

## Cue-card render-wait test gate — Run #1752

- [#1752](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41077106695) passed on the test-only driver correction parent `79d1f81e6c03ae00949b3539eedae8e7909dd871`: frontend JavaScript syntax passed; **844 tests passed in 39.942 seconds**.
- The packaged acceptance script now waits for both imported cue fixture paths to appear in `#cueGrid` before inspecting card layout/selection/playback. If that wait expires, the script emits catalogue role counts and cue-grid diagnostics to determine whether the remaining issue is a real renderer defect.
- This was the regression-only run. A full Windows artifact checkpoint is required to determine whether the cue-card and real cue playback steps pass in the frozen executable.

## Consolidated Stage 2 acceptance gate — regression baseline

- The expanded packaged Stage 2 runner now creates a three-chapter project with saved paragraph-aligned narration chunks, two Music Library tracks, one imported track for each remaining supported category, two fixed cue fixtures and a six-second invalid cue fixture. It exercises Music Library filtering/imports, Chapter BGM strategy and explicit assignments/timing/volumes, cue slot save/clear/failure retry, Mix values, full-book previews, Voice Only, Production handoff/save failure, project switching and a second frozen-app process restart.
- The restart phase reads the saved native catalogue/project state in a newly launched frozen executable. The runner independently validates the JSON state, chapter assignments/timing/end policies, three cue slots, mix levels, imported asset metadata and project cleanup.
- The slider regression assertion was corrected to match the actual configured value expression while preserving the required order: focus, value edit, input and change. No production code changed in this correction.
- Regression baseline: [#1763](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41147418738) passed on `3a2ab79b12e883dc55ed9f3fee2bdd9ad7762286`: frontend JavaScript syntax validation passed and **844 tests passed in 37.141 seconds**.
- The next artifact checkpoint must pass the entire expanded packaged workflow and restart phase before SD/MUS closure is considered.

## Category fixture import source/destination correction — Run #1765

- [#1764](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41147606862) passed the 844-test regression suite, Windows freeze, frozen-executable validation and bundled voice assets. Its expanded packaged UI acceptance stopped at the first extra category import because the harness passed the expected Audio Library destination path as the native import source; the native importer correctly rejected the nonexistent destination. The earlier Music and Cue controls and playback checks had passed.
- Correction commit: `3dcab8cba10fcc5c8b883b5db13ff9006b83c8bc`. The acceptance fixture now records both `source_path` (the generated temporary WAV supplied to `sound.import`) and `path` (the final Audio Library catalogue destination). The native import wrapper uses only the real source path; all catalogue, category, project-switch, metadata and restart assertions continue to validate the destination path.
- A new regression test asserts that source/destination distinction and the final category metadata check.
- [#1765](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41148752076) passed the full regression suite and frontend JavaScript syntax validation on that exact source commit.
- Next: repeat the consolidated frozen Windows package acceptance, including full workflow and second-process persistence. The Stage 2 items remain open until all expanded packaged checks and restart assertions pass.

## Regression gate for corrected category source path

- [#1766](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41148980962) passed the frontend JavaScript syntax gate and complete regression suite on `74c9be04f0c4cb56d6eb3cb6aea792b8e1322278`. The category fixture contract now distinguishes the temporary WAV source passed to the native importer from the expected Audio Library destination stored in the catalogue assertions.
- Re-run the complete frozen Windows Stage 2 UI workflow and its restart phase before marking the remaining SD/MUS requirements accepted.

## Expanded packaged Stage 2 acceptance — failure diagnosis and regression correction (31 October 2026)

- [#1766](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41148980962) and [#1767](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41149365779) both passed the complete pre-package regression suite, Windows freeze, frozen executable self-test, and bundled model/voice asset verification. Both stopped at the first Chapter BGM row-selection wait after the expanded Music Library and category acceptance had passed.
- The failure was in the browser acceptance driver, not the application’s Chapter BGM implementation. The chapter-row click handler calls `renderChapterBgm()`; that renderer intentionally replaces the list with `list.innerHTML = rows.map(...)`. The test held a reference to the old button and polled that detached element for its active class. The newly rendered row was not queried, so the wait timed out even though the live list was rebuilt. The six-second cue import rejection in both logs was the deliberate negative test and had already been recorded as passed.
- Driver correction: `c698ad3ee0c9ca01b39d2dfad02d304618709d68` now keeps a selector rather than a DOM element and re-queries the current Chapter BGM row on every wait poll. The production event handler and renderer were not modified.
- Regression lock: `005089a0bbf6cd977653b0c27a56693fff73e178` adds `test_chapter_selection_wait_requeries_row_after_real_renderer_rebuild`, asserting the browser test checks the replacement DOM node and the app renderer performs the expected list rebuild.
- [#1768](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41151354178) passed on the driver correction: JavaScript syntax validation passed; **845 tests passed in 37.005 seconds**.
- [#1769](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41151365205) passed on final source head `005089a0bbf6cd977653b0c27a56693fff73e178`: JavaScript syntax validation passed; **846 tests passed in 40.459 seconds**, including the new stale-DOM regression test.
- The next single artifact checkpoint runs the complete expanded frozen Windows flow: all Music categories and source results; cue limits/classification/cards/playback; Chapter BGM source/category filters, explicit selection, per-chapter levels/offset/end rules, Same/Chapter-Based round-trip and no fallback; cue three-slot autosave, failed-save recovery and explicit Clear All; Mix values; real full-book previews in Same and Chapter-Based modes and Voice Only; Production handoff failure/retry and generation-toggle sync; Dashboard project switching; JSON/asset validation; and a second frozen-app process restart. Keep all SD/MUS requirements open until this Windows package acceptance and restart phase pass.

## Chapter BGM acceptance save-lock correction — Runs #1770–#1772 (31 October 2026)

- [#1770](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41151837241) passed the full 846-test regression suite, Windows freeze, frozen executable verification, and bundled voice/critical-module verification. The expanded packaged Stage 2 acceptance passed Music Library and all eight category/source checks, cue classification and real cue playback, then stopped at the Chapter BGM persisted-values assertion.
- The six-second cue-import rejection reported in the same log was the intended negative test and had already passed. It was not the failure cause.
- The actual Chapter BGM interaction sequence exposed a race in the acceptance driver: pressing the chapter track's explicit **Select** action saves asynchronously. During that save/refresh, the application intentionally disables the chapter editor controls and only re-enables them after the saved state has been reloaded and the status becomes `Chapter assignment saved.`. The driver previously waited only for the saved track path, which appears before the UI save/refresh finishes, then edited the disabled volume/offset/end controls. The refresh could restore saved values over those early edits.
- Driver correction: commit `04d444932ccce039397f3e8f85d3f67e19be028b` adds `waitForChapterSaveComplete()`. The driver now waits for the selected track, completed-save status, and all editor controls to be enabled before editing chapter timing/volume. Its explicit save wait checks the exact saved volume, start offset and end behavior for Chapter One and Two and includes actual stored values in failure diagnostics. Chapter Three No BGM remains explicitly checked. No application production code was changed.
- [#1771](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41153009841) ran 847 tests and found one error in the new Python regression contract: its text-slice boundary searched for `selectChapter()` after the save helper even though `selectChapter()` is defined earlier in the browser driver. The packaged driver code itself passed the JavaScript syntax check.
- Regression-contract correction: commit `ebc746ac2b3bdd2b9d040cd159868e12fada2772` now ends the helper source slice at the first `await selectChapter(1);` workflow call. The behavioural assertions were not removed or relaxed.
- [#1772](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41153261441) passed on `ebc746ac2b3bdd2b9d040cd159868e12fada2772`: frontend JavaScript syntax validation passed; **847 tests passed in 45.760 seconds**.
- Next gate: run the consolidated Windows package acceptance again on this exact tested code. It must pass chapter assignment save completion/values, Same/Chapter-Based switching and no fallback, both full-book preview strategies, Voice Only preview, cue save failure/retry and explicit Clear All, Mix/Production handoff, project switching, and the second frozen-app restart/persistence phase. Keep all SD/MUS requirement IDs open until that packaged acceptance passes.
