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

## Regression evidence before this artifact checkpoint

- Branch: `stage-2/sound-design-music-library-post-stage1`
- Tested commit: `6696c164c152e9ae59a575578920aa8826c51449`
- Workflow run: [#1737 — Step 2 regression](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41051159974)
- Result: **840 tests passed**; frontend JavaScript syntax validation passed.

## Evidence still required

- A successful Windows `build` job on the exact artifact-checkpoint commit.
- A successful `Run packaged Sound Design Music Library acceptance` step, including all named browser checks and the post-run project-state/sidecar validations.
- The package runner verifies WebEngine decoding, media source, playback time and pause/resume state. It does not replace a human listening check on the user's installed PC/speakers; that acoustic acceptance remains distinct.

## Scope protection

This checkpoint covers only `SD-09`, `SD-10`, and `MUS-06`, plus the retained Music Library prerequisite checks described above. It does **not** mark the remaining SD/MUS requirements, Production handoff, the complete 24-item register, or Version 1.2.0 as complete. Later work-order steps remain in scope and must retain their original requirement IDs and behavior.
