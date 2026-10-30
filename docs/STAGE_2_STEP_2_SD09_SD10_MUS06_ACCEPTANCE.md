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
