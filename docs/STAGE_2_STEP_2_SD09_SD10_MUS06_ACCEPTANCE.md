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
