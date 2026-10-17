# RYU'S AUDIOBOOK
## DRAGON STUDIO EDITION
## COMPLETE UI/UX IMPLEMENTATION SPECIFICATION

======================================================================
1. PROJECT PURPOSE
======================================================================

Ryu's Audiobook is a local-first, AI-powered Windows desktop application
for converting complete books into professionally assembled audiobooks.

The application supports workflows including:

- Importing EPUB, PDF, TXT, DOCX, and other supported book formats.
- Extracting and editing book text.
- Detecting and organising chapters.
- Selecting an audiobook narrator.
- Previewing narration inside the application.
- Detecting characters and dialogue.
- Assigning individual voices to characters.
- Correcting pronunciation.
- Adding contextual background music and sound effects.
- Generating previews and complete audiobooks.
- Recovering interrupted or failed generation jobs.
- Exporting a complete M4B audiobook with metadata, artwork, and chapter
  markers where supported.
- Playing completed audiobooks inside the application.
- Managing local speech engines, AI models, storage, and performance.

This redesign must improve usability, responsiveness, clarity, and visual
quality without removing or weakening any currently implemented feature.

The interface must feel like a professional audiobook-production studio,
not a basic text-to-speech utility.

======================================================================
2. NON-NEGOTIABLE FEATURE-PRESERVATION RULES
======================================================================

The redesign must preserve the following existing capabilities:

1. Library and local project management.
2. PDF, EPUB, TXT, DOCX, and all other currently supported imports.
3. Chapter detection and re-detection.
4. Chapter renaming, ordering, splitting, merging, deletion, and editing.
5. Multi-chapter selection and deletion where currently supported.
6. Text cleanup and book-analysis tools.
7. Autosave and project-state persistence.
8. Narrator voice selection.
9. Voice-provider and backend selection.
10. Offline neural voices.
11. Voice categories and filters.
12. Voice profiles.
13. Voice metadata and advanced voice information.
14. Voice-preview generation.
15. Selectable preview duration.
16. Integrated preview playback with play, pause, and stop.
17. Character and dialogue analysis.
18. Character search.
19. Dialogue examples.
20. Character voice assignment and removal.
21. Low-confidence speaker review.
22. Narrator fallback for unassigned dialogue.
23. Pronunciation dictionary.
24. Pronunciation preview.
25. Story-aware background music.
26. Opening, chapter-transition, scene-transition, and closing sounds.
27. Locally imported music and sound assets.
28. Automatic and manual sound selection.
29. Audiobook metadata.
30. Cover selection and embedding.
31. Output-folder selection.
32. M4B assembly and export.
33. Audio-quality and bitrate selection.
34. Generation estimates.
35. Generation-readiness checks.
36. Preview generation.
37. Selected-chapter generation.
38. Full-audiobook generation.
39. Generation progress.
40. Pause, cancel, retry, resume, and recovery.
41. Completed-audiobook playback.
42. Open-output-folder actions.
43. Installed-model management.
44. Runtime repair and model repair.
45. Hardware detection.
46. Backend verification.
47. Performance benchmarking.
48. Local-first storage.

A screen must never be removed merely because the functionality can be
placed somewhere else.

Advanced features may be reorganised into collapsible panels or sensible
subsections, but the functionality must remain accessible.

The redesign must not claim that visual controls are connected to backend
functionality until the corresponding backend integration has actually
been implemented.

======================================================================
3. BRAND IDENTITY
======================================================================

Product name:

RYU'S AUDIOBOOK

Edition name:

Dragon Studio Edition

Product description:

Premium Local AI Audiobook Production Suite

The uploaded Ryu's Audiobook logo is the official brand asset.

The uploaded logo must be used in:

- Application splash screen.
- Sidebar header.
- Dashboard branding area.
- Import empty state.
- Library empty state.
- Character-analysis empty state.
- About screen.
- Audiobook-player branding.
- Application icon and Windows executable icon where technically suitable.

The logo must not be repeatedly placed inside every card. Excessive logo
repetition would reduce the premium appearance.

The logo must retain its original crimson, gold, book, headphones, and
audiobook identity. Do not replace the logo with a generic dragon icon.

======================================================================
4. VISUAL DESIGN SYSTEM
======================================================================

4.1 Dark theme

Main background:
#090A0F

Secondary background:
#0F131A

Card background:
#141821

Elevated card:
#181D28

Primary border:
#282E38

Secondary border:
#353C49

Primary crimson:
#B21F3F

Crimson hover:
#D4375D

Deep burgundy:
#6F1023

Premium gold:
#D6B06A

Primary text:
#F5F5F6

Secondary text:
#A5ACB8

Muted text:
#727B8B

Success:
#33C76F

Warning:
#F4B740

Information:
#4898FF

Error:
#E54B4B

4.2 Light theme

Main background:
Cream-white or warm off-white.

Card background:
White.

Secondary card background:
Warm cream.

Primary accent:
The same crimson used in dark mode.

Borders:
Muted warm grey.

Primary text:
Very dark burgundy-grey.

The light theme must not become pure, glaring white. It should remain
consistent with the premium crimson-and-gold brand.

4.3 Typography

Preferred font:
Inter

Windows fallback:
Segoe UI

Page title:
30–32 px, weight 700.

Section heading:
20–24 px, weight 600 or 700.

Card title:
16–18 px, weight 600.

Body text:
14–16 px.

Metadata:
12–13 px.

Chapter editor:
15–17 px with a 1.7–1.85 line height.

4.4 Components

Standard card:

- 16–18 px radius.
- One-pixel subtle border.
- Dark charcoal background.
- Restrained shadow.
- No strong neon effect.
- A subtle crimson highlight may appear on selected cards.

Primary button:

- Crimson background.
- White text.
- Clear label.
- Icon only when the meaning is immediately clear.
- Minimum height approximately 40–44 px.

Secondary button:

- Card or surface background.
- Visible border.
- Primary text.

Danger button:

- Transparent or dark background.
- Red border and red label.
- Used only for destructive actions.

Input fields:

- Minimum height approximately 42–44 px.
- Clear focus ring.
- Visible labels when the purpose is not obvious.
- Do not rely on placeholder text as the only label.

Status badges:

- Green for completed or ready.
- Blue for active or running.
- Amber for warnings and review.
- Red for failed or blocked.
- Grey for inactive or unavailable.

4.5 Motion

Hover:
Approximately 150 ms.

Panel transition:
Approximately 200–250 ms.

Drawer transition:
Approximately 250–300 ms.

Animations must be subtle and professional.

Avoid:

- Bright gaming-style neon effects.
- Excessive pulsing.
- Large bouncing controls.
- Unnecessary loading animations.
- Motion that delays normal interaction.

======================================================================
5. GLOBAL APPLICATION SHELL
======================================================================

The application shell must remain consistent across all main screens.

The shell consists of:

1. Persistent left sidebar.
2. Compact top bar.
3. Project workflow tracker.
4. Main workspace.
5. Optional global mini-player.
6. Notification system.
7. Modal and drawer system.

======================================================================
6. LEFT SIDEBAR
======================================================================

The sidebar must contain the Ryu's Audiobook logo, application name, and
grouped navigation.

Navigation structure:

HOME
- Dashboard
- Library

PROJECT
- Import Studio
- Chapter Studio
- Voice Studio
- Character Studio
- Pronunciation Studio
- Sound Design Studio

PRODUCTION
- Production Studio
- Audiobooks
- Generation History

SYSTEM
- Models Center
- Performance Center
- Settings

Sidebar requirements:

- The active page must have a visible crimson highlight.
- The sidebar must support collapse and expansion.
- The collapsed sidebar must retain understandable icons and tooltips.
- The current project must be displayed near the bottom.
- The current-project indicator should show:
  - Book title.
  - Small cover or fallback artwork.
  - Autosave state or last-saved information.
- System pages must remain visually separated from creative project pages.
- Sidebar navigation must not reload the entire application.
- The selected project and unsaved data must persist when switching pages.

On narrow windows:

- Convert the sidebar into a drawer.
- Allow the drawer to open through a clearly visible menu button.
- Close the drawer after selecting a page.
- Do not cover permanent controls without a way to close the drawer.

======================================================================
7. TOP BAR
======================================================================

The top bar must display:

- Current page.
- Current project name.
- Global search.
- Background-job status.
- Theme control.
- Notifications.
- Settings shortcut where appropriate.

Global search may search:

- Project title.
- Author.
- Chapter.
- Character.
- Voice.
- Generation job.

The background-job indicator should communicate:

- Running job count.
- Whether generation is active.
- Whether a job requires attention.
- A shortcut to Production Studio or Generation History.

======================================================================
8. PROJECT WORKFLOW TRACKER
======================================================================

A compact project workflow tracker must appear on relevant project pages.

Stages:

1. Import
2. Chapters
3. Narrator
4. Characters
5. Pronunciation
6. Sound Design
7. Generate
8. Listen and Export

Possible states:

- Completed.
- Current.
- Warning.
- Not started.
- Blocked.

The tracker must be informative, not a forced wizard.

Users should still be able to freely move between pages.

Clicking a stage should open the relevant screen.

The tracker must communicate actual project state. It must not display a
stage as complete if required settings are missing internally.

======================================================================
9. DASHBOARD
======================================================================

Purpose:

Provide a clear summary of audiobook projects, recent work, generation
activity, and recovery actions.

Main sections:

9.1 Welcome header

Display:

- A short welcome message.
- A concise product description.
- Import Book action.
- Open Library action.

9.2 Summary metrics

Display:

- Total projects.
- Completed audiobooks.
- Active projects.
- Projects needing attention.
- Optional local storage usage.
- Optional running-generation count.

9.3 Continue Project

Display:

- Book cover.
- Actual title.
- Author.
- Selected narrator.
- Chapter count.
- Character-assignment count.
- Current preparation percentage.
- Last edited chapter.
- Continue Project button.

Clicking Continue Project must restore the project's latest working state,
including the last selected screen and chapter when available.

9.4 Active Generation

Display:

- Book title.
- Current chapter.
- Current generation stage.
- Real overall percentage.
- Elapsed time.
- Estimated remaining time when reliable.
- View Job action.
- Pause or Resume action where supported.

9.5 Recent Projects

Each project card should display:

- Cover.
- Title.
- Status.
- Narrator.
- Progress or duration.
- Last opened date where available.

9.6 Recent errors or attention

Show recoverable problems such as:

- Missing character voice.
- Empty chapter.
- Failed chapter.
- Missing model.
- Invalid output folder.

Errors must include a direct corrective action.

======================================================================
10. AUDIOBOOK LIBRARY
======================================================================

Purpose:

Manage all imported books and audiobook-production projects.

Default view:

Cover-based project grid.

Optional view:

Compact list view.

Toolbar:

- Search.
- Status filters.
- Sort.
- Grid/list switch.
- Import Book.
- Multi-selection when required.

Search fields:

- Title.
- Author.
- Series.
- Narrator.
- Project name.

Filters:

- All.
- Active.
- Completed.
- Generating.
- Needs Attention.
- Failed.
- No Generated Audio.

Sort options:

- Recently opened.
- Recently imported.
- Title.
- Author.
- Progress.
- Status.

Each project card should display:

- Book cover.
- Book title.
- Author.
- Chapter count.
- Narrator.
- Progress percentage.
- Generated-audio duration when available.
- Status badge.
- Last opened date where useful.

Card actions:

- Open Project.
- Continue Project.
- Generate.
- Listen.
- Rename.
- Open Folder.
- Duplicate Project where supported.
- Archive where supported.
- Delete.

Renaming requirements:

- Renaming the project must update the correct project title.
- The application name must never replace the book title.
- The source book title and project display name should be stored
  separately if the application supports custom project names.

Deletion requirements:

- Use confirmation.
- Clearly state whether generated audio, the project folder, the original
  imported source, or temporary files will be removed.
- Do not silently delete source files outside the managed project folder.

Empty state:

- Use the uploaded logo.
- Explain that no projects exist.
- Provide one primary Import Book action.
- Do not show a blank page.

======================================================================
11. IMPORT STUDIO
======================================================================

Purpose:

Import source material, validate extraction, edit detected metadata, and
create a local audiobook project.

Initial state:

- Large drag-and-drop area.
- Browse Files action.
- Supported format labels.
- Local-storage reassurance.
- Recently imported items where appropriate.

Supported formats must reflect the backend's actual capabilities.

Do not display a file type that the backend cannot import.

On file selection:

Show progress stages such as:

1. Reading source file.
2. Extracting readable text.
3. Detecting title and author.
4. Extracting or locating cover artwork.
5. Detecting chapters.
6. Preparing local project.

Do not show an endless loading spinner without explanation.

Import result must display:

- Source filename.
- Format.
- Detected title.
- Author.
- Series where available.
- Language.
- Word count.
- Detected chapter count.
- Estimated narration duration.
- Cover preview.
- Extracted-text preview.
- Extraction warnings.

Editable fields:

- Project name.
- Book title.
- Author.
- Series.
- Language.
- Cover.

Actions:

- Change Cover.
- Review Extracted Text.
- Retry Extraction.
- Cancel Import.
- Create Project.

Error states must explain:

- Unsupported format.
- Password-protected file.
- Scanned PDF without readable text.
- Corrupted source.
- Empty extraction.
- Import permission problem.

Never silently discard extracted content.

After project creation:

- Save project locally.
- Open Chapter Studio.
- Retain the source-file path and extraction details where appropriate.

======================================================================
12. CHAPTER STUDIO
======================================================================

Purpose:

Organise and edit long books before narration and generation.

Desktop layout:

- Left: chapter navigator.
- Centre: chapter editor.
- Right: chapter insights.
- Bottom: save and autosave status.

12.1 Chapter navigator

Display:

- Search Chapters.
- Search Book Text.
- Filters.
- Chapter status.
- Chapter ordering.

Chapter statuses:

- Ready.
- Empty.
- Needs Review.
- Voice Review.
- Generated.
- Failed.
- Skipped.

Chapter actions:

- Add.
- Rename.
- Reorder.
- Move Up.
- Move Down.
- Split.
- Merge With Next.
- Delete.
- Multi-select.
- Delete Selected.
- Mark for Review.

Current functionality such as Re-detect Chapters, Clean Text, Analyse
Book, View Characters, and Rename Project must remain available.

These actions should be grouped into sensible menus instead of being
presented as an unorganised row of equally prominent buttons.

12.2 Editor

Display:

- Selected chapter title.
- Editable text.
- Preserved paragraphs.
- Preserved punctuation.
- Preserved dialogue formatting.
- Readable typography.
- Find and Replace.
- Word count.
- Estimated narration time.
- Autosave status.

Text-selection toolbar:

- Assign Speaker.
- Add Pronunciation.
- Split Chapter at Selection.
- Mark Selection for Review.

12.3 Insights panel

Display:

- Word count.
- Estimated audio duration.
- Dialogue percentage.
- Characters found.
- Speaker-confidence warnings.
- Pronunciation status.
- Chapter-generation status.

12.4 Empty chapters

Empty chapters must be clearly visible.

Before generation, allow the user to:

- Edit the chapter.
- Remove the chapter.
- Skip the chapter.
- Exclude it from generation.
- Keep it as an intentional empty separator when supported.

An empty chapter must not unexpectedly stop the entire audiobook job.

12.5 Re-detection protection

If the user selects Re-detect Chapters:

- Explain what will change.
- Protect manual edits.
- Offer backup or merge behaviour.
- Do not overwrite manual chapter work without warning.

======================================================================
13. VOICE STUDIO
======================================================================

Purpose:

Browse, compare, preview, configure, and select the narration voice.

Layout:

- Left: categories and filters.
- Centre: voice gallery and preview.
- Right: selected narrator and settings.

13.1 Voice categories

Include categories supported by the available metadata:

- All Voices.
- Storyteller.
- Fantasy.
- Epic.
- Calm.
- Conversational.
- Regional.
- Favorites.
- Offline.
- Imported or custom.
- Authorized cloned profiles.

Do not fabricate voice attributes that the backend does not provide.

13.2 Filters

Possible filters:

- Language.
- Accent or region.
- Voice style.
- Provider.
- Backend.
- Installed/available.
- Favorites.

If gender-presentation metadata exists and is needed, use the backend's
actual labels and do not infer metadata from voice names.

13.3 Voice cards

Each card should show:

- Voice name.
- Language.
- Accent or region where known.
- Style tags where known.
- Backend or provider, preferably in secondary details.
- Preview action.
- Select action.
- Favorite action where supported.

13.4 Selected narrator

The selected narrator must be visually prominent.

Display:

- Voice name.
- Provider or backend.
- Language.
- Current project usage.
- Voice-profile name.
- Readiness status.

Critical consistency rule:

The voice shown as selected must be the voice passed to preview and final
generation.

Do not allow display selection and internal generation selection to
become unsynchronised.

13.5 Preview Studio

Provide:

- Preview source:
  - Current chapter.
  - Selected text.
  - Custom text.
- Preview durations:
  - 10 seconds.
  - 30 seconds.
  - 60 seconds.
- Generate Preview.
- Play.
- Pause.
- Stop.
- Seek where available.
- Volume.
- Progress and loading status.
- Error and retry.

If a selected duration cannot be produced, explain the reason and show
the actual generated duration.

Do not silently generate 10 seconds after the user selected 30 seconds.

Preview playback must remain inside the application.

13.6 Voice settings

Show only settings supported by the selected backend:

- Speed.
- Pitch.
- Expressiveness.
- Stability or equivalent.
- Style strength or equivalent.

Unsupported settings must be disabled or hidden with an explanation.

13.7 Voice profiles

Allow:

- Save named profile.
- Load profile.
- Rename profile.
- Delete profile with confirmation.
- Apply profile to narrator.
- Persist profile settings.

======================================================================
14. CHARACTER STUDIO
======================================================================

Purpose:

Identify story characters, review dialogue, correct uncertain speakers,
and assign consistent voices.

Layout:

- Top: analysis summary.
- Left: detected-character list.
- Centre: dialogue inspector.
- Right: voice assignment.

14.1 Summary

Display:

- Number of detected characters.
- Assigned voices.
- Unassigned voices.
- Characters requiring review.
- Overall cast readiness.

14.2 Character list

Provide:

- Search.
- Main/Supporting/Minor filters where detection supports them.
- Assigned/Unassigned filters.
- Confidence status.
- Occurrence count.
- Voice-assignment status.

Character actions:

- Add.
- Rename.
- Merge.
- Remove.
- Mark as Narrator.
- Mark as Unknown Speaker.
- Assign Voice.
- Remove Assignment.

14.3 Dialogue inspector

Display:

- Character name.
- Total dialogue lines.
- Chapters containing the character.
- Representative dialogue samples.
- Confidence level.
- Ambiguous dialogue.
- Links back to the source chapter.

The interface must clearly distinguish:

- Dialogue punctuation detected.
- A likely speaker inferred.
- A confirmed character assignment.
- A voice assigned to the character.

Detecting quotation marks is not the same as identifying a speaker.

14.4 Confidence states

Use understandable labels:

- High Confidence.
- Probable.
- Needs Review.
- Unknown.

Never silently treat uncertain identification as confirmed.

14.5 Voice assignment

Display:

- Current voice.
- Preview.
- Change Voice.
- Save Assignment.
- Remove Assignment.
- Speed, pitch, and volume only where supported.
- Narrator fallback.

Assignments must be stored per project and preserved when navigating
between pages or reopening the project.

======================================================================
15. PRONUNCIATION STUDIO
======================================================================

Purpose:

Correct uncommon names, fantasy terms, Japanese words, and other
difficult vocabulary.

Sections:

- Suggested Review.
- Current Book Dictionary.
- Global Dictionary.
- Pronunciation Preview.

Dictionary fields:

- Written word.
- Preferred pronunciation.
- Phonetic method.
- Scope.
- Enabled state.
- Selected voice for preview.
- Last edited date where useful.

Actions:

- Add.
- Edit.
- Delete.
- Enable/Disable.
- Move between book and global scope.
- Preview.
- Accept suggestion.
- Edit suggestion.
- Reject suggestion.

Speech-engine support:

- Only display phoneme formats supported by the active speech backend.
- Clearly explain unsupported IPA, SSML, phoneme, or language features.
- Do not imply universal phonetic support.

Suggestions:

- Prioritise proper names and unusual terms.
- Avoid flagging ordinary English vocabulary without good reason.
- Allow batch review.

Preview must use the selected narrator or explicitly selected test voice.

======================================================================
16. SOUND DESIGN STUDIO
======================================================================

Purpose:

Add story-appropriate background music, ambience, transitions, and sound
cues without turning the audiobook into a random playlist.

Layout:

- Left: categories.
- Centre: track and effect catalogue.
- Right: current assignment and mix controls.

16.1 Categories

Organise authorized local assets into categories such as:

- Fantasy Adventure.
- Dark Fantasy.
- Action and Battle.
- Suspense and Mystery.
- Horror and Tension.
- Emotional and Tragic.
- Romance.
- Peaceful Ambience.
- Comedy and Lighthearted.
- Magic and Supernatural.
- School Life and Slice-of-Life.
- Sci-fi and Futuristic.
- Exploration and Travel.
- Dramatic Revelation.
- Calm Narration and Transition.

16.2 Catalogue

Each real track should display:

- Track name.
- Duration.
- Mood.
- Genre.
- Intensity.
- Source or asset pack where appropriate.
- Licensing or authorization metadata where required.
- Integrated Preview.
- Assign action.

Do not fabricate nonexistent tracks.

Placeholder track names used in a visual prototype must be clearly
identified as demonstration content.

16.3 Search and filters

Allow filtering by:

- Genre.
- Mood.
- Scene.
- Intensity.
- Narrative context.
- Duration.
- Locally imported content.

16.4 Assignment

Allow assignment to:

- Entire book.
- Selected chapter.
- Multiple selected chapters.
- Opening.
- Closing.
- Scene transition.
- Environmental ambience.

16.5 Mix controls

Provide:

- Enable/Disable.
- Narration-relative volume.
- Fade in.
- Fade out.
- Crossfade or transition style.
- Preview Combined Audio.
- Reset Mix.

16.6 Story cues

Separate controls for:

- Book opening sound.
- Chapter flip or chapter transition.
- Scene-transition effect.
- Book closing sound.
- Environmental ambience.

Each cue requires:

- On/Off toggle.
- Selected asset.
- Preview.
- Volume.
- Replace.
- Remove.

16.7 Automatic sound direction

If automatic selection exists:

- Explain that selection uses scene mood or context.
- Show why a track was selected where possible.
- Allow manual replacement.
- Do not choose assets randomly.
- Do not override manual choices without permission.

16.8 Asset management

Support:

- Import authorized audio.
- Browse local catalogue.
- Organise asset folders.
- Find missing assets.
- Remove unused assets.
- Confirm destructive cleanup.

======================================================================
17. PRODUCTION STUDIO
======================================================================

Purpose:

Bring all settings together, generate previews, produce selected chapters,
generate the complete audiobook, recover failures, and assemble output.

This is the most important screen in the application.

Layout:

- Left: project summary.
- Centre: generation engine and controls.
- Right: readiness and recovery.
- Optional lower panel: metadata, output, logs, and completed result.

17.1 Project summary

Display:

- Cover.
- Book title.
- Author.
- Language.
- Narrator.
- Character-assignment summary.
- Pronunciation summary.
- Music and sound summary.
- Selected chapters.
- Output format.
- Output quality.
- Output directory.

17.2 Readiness checks

Display actual status for:

- Source book.
- Chapters.
- Empty chapters.
- Narrator.
- Voice backend.
- Character voices.
- Pronunciations.
- Music assets.
- Sound cues.
- Output directory.
- Required models.
- Available storage.

Warnings must provide a corrective action.

Examples:

- Review 3 Characters.
- Fix Empty Chapter.
- Repair Voice Backend.
- Select Output Folder.
- Locate Missing Music Asset.

Do not block generation for optional warnings unless necessary.

17.3 Preview generation

Provide:

- Chapter selection.
- Preview start point where supported.
- Duration:
  - 10 seconds.
  - 30 seconds.
  - 60 seconds.
- Narration-only option.
- Include Characters option.
- Include Music option.
- Include Sound Effects option.
- Generate Preview.
- Play.
- Pause.
- Stop.
- Regenerate.
- Save Preview where supported.

Playback must remain inside the application.

17.4 Generation actions

Provide:

- Generate Selected Chapters.
- Generate Full Audiobook.
- Resume Generation.
- Retry Failed Chapters.
- Pause.
- Resume.
- Cancel.

The primary full-generation button must remain visible without requiring
the user to scroll to the bottom of an extremely long form.

Use a sticky action area where necessary.

17.5 Progress

Display real progress:

- Overall percentage.
- Current chapter.
- Current processing stage.
- Completed chapters.
- Remaining chapters.
- Failed chapters.
- Elapsed time.
- Estimated remaining time.
- Generation speed where meaningful.

Possible processing stages:

- Preparing text.
- Applying pronunciation.
- Rendering narration.
- Rendering character dialogue.
- Mixing chapter audio.
- Applying music.
- Applying sound effects.
- Encoding.
- Assembling M4B.
- Embedding metadata.
- Creating chapter markers.
- Validating output.

The progress bar must not freeze at an arbitrary percentage.

Do not show 100 percent until output validation has completed.

17.6 Errors and recovery

Every failure should identify:

- Affected chapter.
- Failed stage.
- Plain-language cause.
- Suggested corrective action.
- Retry option.
- Technical details in an expandable section.

Successful chapters should not be regenerated unnecessarily.

The existing partial-work and resume system must be preserved.

17.7 Metadata and output

Provide:

- Title.
- Author.
- Narrator.
- Publisher.
- Series.
- Language.
- Year.
- Genre.
- Cover.
- Output format.
- Bitrate.
- Output folder.

Advanced metadata should be collapsible so that generation does not feel
like paperwork.

Accurately display actual codec and bitrate.

Do not claim that increasing bitrate can restore quality missing from
source audio.

17.8 Completed state

After validation, display:

- Audiobook Ready.
- Output filename.
- Format.
- Bitrate.
- Duration.
- File size.
- Chapters embedded.
- Metadata embedded.
- Cover embedded.
- Play Audiobook.
- Open Output Folder.
- Open in Audiobooks.
- Regenerate Failed Chapters where required.

======================================================================
18. AUDIOBOOK PLAYER
======================================================================

Purpose:

Play generated audiobooks entirely inside Ryu's Audiobook.

Display:

- Cover.
- Title.
- Author.
- Narrator.
- Current chapter.
- Elapsed time.
- Total duration.
- Progress timeline.

Controls:

- Play.
- Pause.
- Stop.
- Seek.
- Previous chapter.
- Next chapter.
- Rewind by a short interval.
- Forward by a short interval.
- Volume.
- Playback speed.
- Sleep timer where supported.
- Chapter list.
- Open Output Folder.
- Return to Project.

Playback position should be preserved where supported.

The current chapter must be highlighted.

Do not unexpectedly open an external player.

18.1 Global mini-player

A compact mini-player may remain available while the user navigates other
screens.

Display:

- Small cover.
- Book title.
- Current chapter.
- Play/Pause.
- Progress.
- Close or minimise.

The mini-player must not cover critical buttons.

On smaller windows, it should adapt or collapse.

======================================================================
19. GENERATION HISTORY
======================================================================

Purpose:

Track active and previous production jobs.

Filters:

- All.
- Running.
- Completed.
- Failed.
- Cancelled.
- Retried.

Each job should display:

- Project.
- Date.
- Status.
- Progress.
- Duration.
- Output format.
- Output status.
- Failed chapter count.

Actions:

- Reopen Project.
- View Running Job.
- Resume.
- Retry Failed Chapters.
- Play Audiobook.
- Open Output Folder.
- View Details.
- Delete History Entry.

Logs:

- Show a plain-language explanation first.
- Place technical logs inside an expandable troubleshooting panel.
- Allow copying diagnostic details.
- Avoid presenting overwhelming logs by default.

======================================================================
20. MODELS CENTER
======================================================================

Purpose:

Manage installed local components without placing developer-level
information in the normal creative workflow.

Sections:

- Offline Narration.
- Voice Design.
- Authorized Voice Cloning.
- Character and Dialogue Analysis.
- Audiobook Analysis.
- Supporting Runtime Components.

Each component should display:

- Friendly name.
- Technical model name in secondary details.
- Installed status.
- Version.
- Storage usage.
- Health.
- Update availability.
- Backend dependency.
- Repair action.

Actions:

- Install.
- Update.
- Verify.
- Repair.
- Reinstall.
- Reset Cache.
- Open Model Folder where safe.
- Remove with confirmation.

Do not hide useful technical information, but place it under Advanced
Details instead of making technical model names the primary UI.

======================================================================
21. PERFORMANCE CENTER
======================================================================

Purpose:

Provide understandable system diagnostics, backend recommendations, and
performance estimates.

Summary:

- Overall system health.
- CPU status.
- GPU status.
- CUDA or acceleration availability.
- Narration-engine readiness.
- Character-analysis readiness.
- Recommended backend.
- Estimated generation performance.

Detailed hardware:

- CPU.
- Architecture.
- Logical core count.
- RAM.
- GPU.
- GPU memory where available.
- Supported acceleration.
- Free local storage where relevant.

Backend recommendations:

- Backend name.
- Recommended device.
- Availability.
- Verification state.
- Repair action.

Benchmark:

- Run Benchmark.
- Stop Benchmark.
- Estimated real-time factor.
- Estimated chapters per hour.
- Estimated generation time for the current project.
- Recommended concurrency.
- Recommended backend.

Benchmark estimates must be labelled as estimates.

======================================================================
22. SETTINGS
======================================================================

Settings categories:

1. Appearance.
2. Storage.
3. Speech and Generation.
4. Audio.
5. Library Management.
6. Diagnostics.
7. About.

22.1 Appearance

- Dark theme.
- Light theme.
- Follow system theme where supported.
- Crimson accent variants.
- Interface scale.
- Reduced motion.
- Compact or comfortable density where supported.

22.2 Storage

- Project directory.
- Generated-audio directory.
- Voice-profile directory.
- Music and sound library.
- Temporary-file directory.
- Storage usage.
- Change Folder.
- Open Folder.

Changing storage paths must explain whether existing content will move or
only future content will use the new path.

22.3 Speech and Generation

- Default backend.
- Default narrator.
- Default narration speed.
- Default preview duration.
- Default output format.
- Default bitrate.
- Generation concurrency.
- Empty-chapter policy.
- Failed-chapter policy.
- Resume behaviour.

22.4 Audio

- Narration volume.
- Background-music volume.
- Sound-effect volume.
- Default cue settings.
- Playback speed.
- Continue-playback preference.
- Output-device selection where supported.

22.5 Library Management

- Import preferences.
- Metadata preferences.
- Cover preferences.
- Temporary-file cleanup.
- Unused-resource cleanup.
- Backup and restore where supported.
- Import and export project settings.

Cleanup operations must identify exactly what will be deleted.

22.6 Diagnostics

- Application version.
- Installed backends.
- Model availability.
- Dependency health.
- View Logs.
- Export Diagnostic Report.
- Check Missing Resources.
- Verify Local Backend.

22.7 About

Display:

- Uploaded Ryu's Audiobook logo.
- RYU'S AUDIOBOOK.
- Dragon Studio Edition.
- Version.
- Local-first product description.
- License information where required.

======================================================================
23. NOTIFICATIONS
======================================================================

Use non-blocking toast notifications for:

- Save completed.
- Import completed.
- Voice selected.
- Voice profile saved.
- Character assignment saved.
- Pronunciation entry added.
- Sound preset saved.
- Preview completed.
- Audiobook generated.
- Recoverable warning.

Use confirmation dialogs only for:

- Deleting projects.
- Deleting chapters.
- Deleting voice profiles.
- Removing models.
- Removing stored audio assets.
- Cancelling active generation when work may be lost.
- Clearing caches or temporary files.

Notifications must not endlessly repeat.

======================================================================
24. LOADING, EMPTY, ERROR, AND COMPLETED STATES
======================================================================

Every applicable screen must include:

- Loading state.
- Empty state.
- Error state.
- Completed state.

Loading states must describe the current operation.

Bad:
"Loading..."

Better:
"Detecting chapter headings..."

Empty states must explain:

- Why the screen is empty.
- What the user should do next.
- Which action will resolve it.

Error states must provide:

- Clear cause.
- Affected resource.
- Recovery action.
- Optional technical details.

Never leave a blank page or endless spinner.

======================================================================
25. RESPONSIVE WINDOWS BEHAVIOUR
======================================================================

Primary desktop target:

1920 × 1080.

Required laptop target:

1366 × 768.

The UI must also remain usable when the Windows application is resized.

Large desktop:

- Three-column creative studio layouts.
- Four metric cards per row.
- Persistent full sidebar.

Laptop:

- Two metric cards per row.
- Narrower left and right panels.
- Scrollable content.
- Sticky primary actions.
- No clipped Generate button.

Small application window:

- One-column stacking where necessary.
- Sidebar becomes a drawer.
- Secondary panels become drawers or collapsible sections.
- Tables gain horizontal scrolling.
- Mini-player condenses.
- Critical buttons remain visible.
- Bottom controls must not be covered by the Windows taskbar.

The interface must account for Windows display scaling such as:

- 100%.
- 125%.
- 150%.

No important control may depend on a fixed 1920 × 1080 canvas.

======================================================================
26. ACCESSIBILITY AND USABILITY
======================================================================

Requirements:

- All controls must be keyboard accessible.
- Active focus must be visible.
- Text and controls must have sufficient contrast.
- Icons with unclear meaning must include labels or tooltips.
- Colour must not be the only status indicator.
- Buttons need clear disabled states.
- Loading actions need progress or status feedback.
- Destructive actions require explicit wording.
- Tab order should follow the visual workflow.
- Important actions should not depend exclusively on hover.
- Audio controls must expose labels for assistive technology.

======================================================================
27. DATA AND STATE CONSISTENCY
======================================================================

Project state must persist across navigation and restarts where current
functionality supports it.

Persist:

- Current project.
- Last opened page.
- Last selected chapter.
- Edited text.
- Chapter ordering.
- Selected narrator.
- Voice profile.
- Character assignments.
- Pronunciation entries.
- Background music.
- Sound cues.
- Mix settings.
- Preview duration.
- Output format.
- Output folder.
- Generation state.
- Playback position.

The visible UI and backend state must always agree.

Examples:

- If Amy is visually selected, preview and generation must use Amy.
- If background music is disabled, generation must not mix it.
- If a chapter is excluded, generation must not process it.
- If a 30-second preview is selected, the backend must receive 30 seconds.
- If a project is renamed, the library and project header must show the
  new project name without changing the application name.
- If generation is at 76 percent, the displayed percentage must reflect
  real backend progress.

======================================================================
28. PROTOTYPE VERSUS BACKEND IMPLEMENTATION
======================================================================

The existing premium HTML prototype demonstrates:

- Visual design.
- Navigation.
- Responsive layouts.
- Theme switching.
- Library filters.
- Import progress simulation.
- Chapter editing simulation.
- Voice-selection simulation.
- Character-assignment simulation.
- Pronunciation-entry creation.
- Sound-track selection.
- Generation-progress simulation.
- Player-state simulation.
- Notifications.
- Modals.
- Performance-benchmark simulation.

The prototype does not itself implement:

- Real book extraction.
- Real chapter detection.
- Real AI character analysis.
- Real voice generation.
- Real audio playback from generated files.
- Real music mixing.
- Real M4B encoding.
- Real model installation.
- Real hardware benchmarking.
- Real local project persistence.

The production application must connect the approved interface to the
existing Ryu's Audiobook backend instead of replacing working backend
features with demonstrations.

======================================================================
29. IMPLEMENTATION PRIORITY
======================================================================

Phase A: Shared foundation

- Application shell.
- Theme system.
- Uploaded logo.
- Sidebar.
- Top bar.
- Workflow tracker.
- Buttons.
- Inputs.
- Cards.
- Status badges.
- Notifications.
- Dialogs.
- Responsive behaviour.
- Project-state service.

Phase B: Core project workflow

- Dashboard.
- Library.
- Import Studio.
- Chapter Studio.
- Voice Studio.
- Character Studio.

Phase C: Production tools

- Pronunciation Studio.
- Sound Design Studio.
- Production Studio.
- Preview system.
- Progress and recovery.
- Final assembly.

Phase D: Completed-work experience

- Audiobook Player.
- Mini-player.
- Generation History.
- Output and export actions.

Phase E: System tools

- Models Center.
- Performance Center.
- Settings.
- Diagnostics.
- About.

At every phase, verify that previously working functionality remains
available before continuing.

======================================================================
30. FINAL ACCEPTANCE CHECKLIST
======================================================================

Branding:

[ ] Uploaded Ryu's Audiobook logo is used without replacement.
[ ] Crimson and gold identity is preserved.
[ ] Dark and light themes are coherent.
[ ] Components use the same visual language.

Navigation:

[ ] Every page opens correctly.
[ ] Active navigation is visible.
[ ] Current project is always identifiable.
[ ] Sidebar works on large and small windows.
[ ] Navigation does not discard unsaved changes.

Import:

[ ] All currently supported formats remain available.
[ ] Import progress is clear.
[ ] Extraction errors are visible.
[ ] Metadata is editable.
[ ] Extracted text can be reviewed.
[ ] Project files are saved locally.

Chapters:

[ ] Chapter editing remains available.
[ ] Reorder, split, merge, rename, and delete remain available.
[ ] Re-detection does not silently overwrite manual edits.
[ ] Empty chapters are visible.
[ ] Empty chapters do not unexpectedly stop full generation.
[ ] Long novels remain manageable.
[ ] Autosave works.

Voices:

[ ] Current voice library remains available.
[ ] Voice providers and backends remain available.
[ ] Selected narrator is prominent.
[ ] Selected voice matches the backend selection.
[ ] Voice previews play internally.
[ ] Preview duration works correctly.
[ ] Voice profiles persist.

Characters:

[ ] Character analysis remains available.
[ ] Dialogue samples remain available.
[ ] Speaker confidence is visible.
[ ] Dialogue detection is distinguished from speaker identification.
[ ] Character voice assignments persist.
[ ] Narrator fallback is clearly communicated.

Pronunciation:

[ ] Current pronunciation dictionary remains available.
[ ] Suggestions can be reviewed.
[ ] Entries can be previewed.
[ ] Unsupported phoneme formats are explained.
[ ] Corrections are applied during generation.

Sound design:

[ ] Background music remains available.
[ ] Opening, transition, and closing sounds remain available.
[ ] Music can be previewed internally.
[ ] Volume and fade controls remain available.
[ ] Whole-book and chapter assignment remain available.
[ ] Automatic selection is contextual, not random.
[ ] Local assets and permissions are respected.

Production:

[ ] Generate screen always opens.
[ ] Existing Generate controls are not removed.
[ ] Generate Preview remains available.
[ ] Generate Selected Chapters remains available.
[ ] Generate Full Audiobook remains available.
[ ] Play, Pause, and Stop Preview remain available.
[ ] Pause, Resume, Cancel, and Retry remain available.
[ ] Resume partial work remains available.
[ ] Progress reflects actual backend work.
[ ] Current chapter and stage are displayed.
[ ] Errors identify the affected chapter.
[ ] Successful chapters are not unnecessarily regenerated.
[ ] Output folder is visible.
[ ] M4B assembly is validated before completion.

Player:

[ ] Playback remains inside the application.
[ ] Play, Pause, Stop, Seek, Previous, and Next work.
[ ] Chapter navigation works.
[ ] Cover, title, author, and narrator are shown.
[ ] Playback position is preserved where supported.

System:

[ ] Existing model installation and repair remain available.
[ ] Existing hardware detection remains available.
[ ] Existing backend verification remains available.
[ ] Benchmark results are labelled as estimates.
[ ] Diagnostics are understandable.
[ ] Technical details remain available under expanded sections.

Responsive behaviour:

[ ] No menu is cut off at 1366 × 768.
[ ] Generate controls remain reachable.
[ ] Bottom controls are not covered.
[ ] Scrolling works.
[ ] Windows scaling is supported.
[ ] Tables and editors remain usable in resized windows.

Final requirement:

The completed redesign must make Ryu's Audiobook feel like a polished,
premium, local audiobook-production studio while preserving the current
application's complete feature set and backend capabilities.