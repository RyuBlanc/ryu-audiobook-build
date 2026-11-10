# Ryu Audiobook — Stage 8 Friend Acceptance Checklist

**Purpose:** Validate the exact Stage 8 Windows candidate in a real Windows environment. This is a test handoff, not a claim that Stage 8 is already released. The application version must remain 1.1.1 until all final acceptance gates are passed; 1.2.0 is applied only for the final accepted release.

## Before testing

- Use only the installer and/or portable artifact from the same latest successful artifact-checkpoint run. Do not use Build #2768 as the current candidate; it predates the latest source changes even though it is also version 1.1.1.
- Until final release acceptance, the candidate should display version 1.1.1 plus its unique build number. Version 1.2.0 is reserved for the final accepted release.
- Record the exact build number shown in the app's About/version area and the artifact name.
- Record Windows edition/build, CPU, RAM, GPU, available disk space, display resolution and Windows scaling percentage.
- Use a small non-sensitive test book. Keep a backup of its source file.
- Do not uninstall the application, delete app data, clean model folders or remove the test project until the test report and logs have been collected.

## A. Launch, project and import

- [ ] Installer starts, completes and launches the Premium V2 Dragon Studio interface by default.
- [ ] Close and reopen the app; Premium V2 and the correct version/build remain.
- [ ] Import a supported TXT, EPUB, searchable PDF or DOCX file.
- [ ] Inspect title, author, extracted text, chapter count and word coverage; report missing/truncated content.
- [ ] The latest-import card shows the correct book and its Open action opens that exact project.
- [ ] Navigate away, reopen the app and confirm the imported project remains available.

## B. Chapter editing and characters

- [ ] Rename and reorder a chapter; save and navigate away/back to confirm persistence.
- [ ] Split a chapter; verify dialogue/character assignments remain attached to the correct text.
- [ ] Edit text, wait for Saved status, restart and confirm the latest text remains.
- [ ] Run Character Analysis; inspect assigned/unassigned dialogue and narrator fallback.
- [ ] Assign a saved voice profile to a character and test that character's actual dialogue.
- [ ] Confirm deleting a character cannot silently orphan saved dialogue assignments.

## C. Voice and pronunciation

- [ ] Open Voice Studio and navigate Voice Library → Configure → Voice Profile → Preview & Assign.
- [ ] Save a profile, close/reopen the project and load the same profile.
- [ ] Generate 10- and 30-second previews where the provider is available; record requested and actual duration.
- [ ] Listen and confirm the selected voice is the voice heard and later assigned.
- [ ] Add a book-specific pronunciation entry; preview it and confirm the same rule is used in Production.
- [ ] Confirm unavailable providers/models show a truthful actionable error rather than a success state.

## D. Sound Design — critical Stage 8.2.8 checks

Use a project with at least two non-empty chapters and saved narration.

- [ ] Same BGM uses one book-default music track across chapters; it does not choose a different track for each chapter.
- [ ] Chapter-Based: assign a custom track to Chapter 1 and No BGM to Chapter 2.
- [ ] Confirm Chapter 2 remains narration-only; no book-default, automatic or legacy ambience fallback is audible.
- [ ] Try Immediate, After 10 seconds and After first paragraph on a sufficiently long preview. Record the audible start point; if the first paragraph exceeds the preview, the app should explain why it cannot verify the boundary rather than guess.
- [ ] Test configured fades/end behavior and narration ducking at the saved levels.
- [ ] Test Opening, Next Chapter and Closing cues; confirm unassigned slots do not insert fallback sounds.
- [ ] Test Voice Only; it must exclude BGM and fixed cues without deleting saved assignments.
- [ ] Generate Book Mix Preview from saved narration; confirm it does not re-synthesize or modify source narration.
- [ ] Generate the final audiobook with the same settings and compare cue/BGM placement, duration and levels with the preview.

## E. Production, output and playback

- [ ] Select a chapter in Production and generate Preview Audio; confirm only that chapter is previewed.
- [ ] Play, stop, replay and save/download the completed preview.
- [ ] Switch chapter/project and confirm stale preview audio is not attached to the new selection.
- [ ] Run full-book generation on the small test book; note progress, elapsed time and ETA.
- [ ] If safe, test pause/resume, cancel, retry and recovery; confirm completed valid chunks are reused.
- [ ] Open the finished audiobook; test play/pause, seek, volume, speed and chapter navigation.
- [ ] Confirm mini-player and full player remain synchronized.
- [ ] Check title, author, narrator, cover, chapter titles/timing and measured audio duration.

## F. Help, navigation and responsive behavior

- [ ] Open Help & Guide from the sidebar.
- [ ] Search for a real topic and confirm matching sections appear.
- [ ] Search for a nonexistent term and confirm the no-results message.
- [ ] Test Expand all and Collapse all.
- [ ] Visit all 15 sidebar destinations; report blank pages, dead controls, missing data or incorrect project identity.
- [ ] Resize to 1366×768 and 1280×720; test a narrow half-screen window and restore/maximize.
- [ ] If available, test portrait, ultrawide, 125%/150%/200% scaling and movement between monitors.
- [ ] Report flicker, black/white flashes, clipped text, overlapping panels, frozen controls or lost edits.

## Report format

For each failed or questionable item, record:
1. Section and checkbox.
2. Pass / Fail / Blocked.
3. Exact action taken.
4. Expected result.
5. Actual result and error text.
6. Screenshot or short recording if visual.
7. Log files and approximate time.
8. Whether the issue repeats after restarting the app.

**Do not label the app bug-free.** The Qwen 30-second preview under-60-second target was not met on the hosted CPU (268.184 seconds); NVIDIA/AMD/Intel accelerator checks remain deferred until the corresponding hardware is available. Record actual timings rather than estimating.


## G. Production UI and notification repair checkpoint — 11 November 2026

These checks were added after the earlier friend-acceptance checklist. They must be exercised on the packaged Windows candidate; source tests alone do not count as hands-on acceptance.

- [ ] Import a book with a real cover and confirm the Ryu's Audiobook placeholder watermark is absent over the image.
- [ ] Remove the cover and confirm the branded red/gold gradient placeholder and watermark return.
- [ ] Start a full audiobook job and confirm the ring arc, displayed percentage, chapter, elapsed time and remaining-time estimate describe that same full-book job.
- [ ] Start or inspect a chapter preview and confirm its progress does not change the full-book ring.
- [ ] Confirm the Generation Engine order is chapter preview controls first, audiobook settings second, and full audiobook Generate/Pause actions last. No empty toolbar gap remains.
- [ ] Resize the Production Studio card and enter long metadata, output paths and long readiness messages; confirm left, center and readiness content wrap without overlap.
- [ ] Confirm Narrator-Only Generation is rendered as an on/off switch with an information hover. When enabled, it must route every passage, including dialogue, to the saved narrator only when no valid character voice profiles are configured. With any valid configured character profile, the switch must explain why it is unavailable.
- [ ] Confirm pronunciation and Voice Only/BGM & cues controls still save and affect preview and final generation.
- [ ] Click the top-right notification dot while a task is running. It must open recent notification cards, not Background Jobs/Task Manager.
- [ ] Trigger several job updates; confirm progress does not create a repeated stack of duplicate notifications and notifications disappear within 30 seconds.
- [ ] Verify a model from Models Center; detailed diagnostics should remain on the model card while the floating notification remains short.
- [ ] Open Help & Guide and confirm the original seven-stage guide, task shortcuts, model guidance, recovery instructions, quality checklist and FAQs remain present. The guide must not display an unrelated sample project's readiness percentage or example badges.
- [ ] Confirm Qwen Auto / 0.6B / 1.7B preference is visible and persists consistently across Voice Studio, Production and Performance Center.
- [ ] When a real NVIDIA/AMD/Intel test PC is available, confirm Qwen reports a GPU active only after the isolated runtime self-test and a successful inference report that device. Explicit GPU selection must fail visibly and preserve the previous runtime if activation fails.

**Evidence boundary:** the branch CI covers the static UI contracts and regression tests. The real Windows installer/portable build, actual book synthesis, cover rendering in WebEngine, notification timing and physical-GPU inference still require the checks above on the packaged application and appropriate hardware.
