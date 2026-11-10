# Active Project Responsiveness Repair — Stage 7 Carry-forward

**Base:** Build #2819, `17266beb764ca6660c66bbf734605d986ff36f31`  
**Branch:** `stage-7/responsive-active-project-cache`  
**Scope:** remove repeated whole-Library enumeration from commands that need only the active project.  
**Preservation rule:** no UI screen, feature, project format, narration output, or bundled runtime is removed.

## Verified cause in the pre-fix source

- `PremiumV2Bridge._active_project()` called `list_projects()` and searched the result for the active folder.
- `list_projects()` enumerates every direct child of each Library root and calls `Project.load()` for each book.
- `Project.load()` reads the chapter JSON, walks `working_audio` narration folders to migrate legacy chapter IDs, and may rewrite legacy chapter BGM keys in `state.json`.
- The active-project helper is shared by ordinary chapter, voice, character, pronunciation, sound and production operations. Therefore unrelated books and narration folders could be revisited for routine actions.

## Change made on this branch

1. Resolve the selected project as a direct child of the configured or legacy Library roots; reject paths that resolve outside those roots.
2. Distinguish a missing project from a disconnected Library drive. Keep the saved active path when the configured drive is unavailable.
3. Cache the active `Project` object and its project/chapter file signatures. Reuse the object while those files are unchanged.
4. On a real change to `project.json` or `chapters.json`, reload only that project. Run legacy chapter/narration/BGM migration once per project per app session, not on every cache invalidation.
5. Route `project.open`, `project.get_active` and active-project commands through the direct resolver instead of enumerating every book.

## Regression coverage added

- Repeated active access reuses the same project instance and does not call `list_projects()`.
- Changed chapter files invalidate the cache and reload the active project.
- Reload after an in-session edit does not rerun legacy migration.
- An unavailable configured Library does not erase `project/active_folder`.
- Library folder resolution rejects paths outside direct Library children.
- Non-migrating reload does not enumerate narration folders or rewrite legacy BGM state.

## Verification status

- **CODE CHANGED — NOT VERIFIED** until this artifact-checkpoint commit completes its matching-head Windows regression and package workflow.
- The pre-fix Build #2819 run passed 1,325 automated tests and packaged the installer/portable artifacts, but it did not measure or accept routine interactive responsiveness.
- No manual claim is made for zero UI stalls, zero flicker, or the user's installed-PC behaviour.
- This repair preserves the existing migration code and performs it on the first authoritative project load; it does not delete or rewrite project/audio content as an optimization.
