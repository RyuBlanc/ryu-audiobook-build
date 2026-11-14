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

## Verification status — Dragon Studio extension

- The original active-project cache/resolver and this branch's direct-known-folder extension passed the matching-head regression suite and complete Windows package at Build #3363 (1,541 tests, package success). The AST contract verifies the seven known-folder actions do not enumerate the entire Library, and the filesystem contract verifies the resolver accepts a direct Library child and rejects a path outside it.
- The #3358–#3362 failures were diagnosed as incomplete test doubles/path normalization and a separate missing stopwatch import; they are preserved as failed records in `docs/dragon-studio/PUSH-LEDGER.md`. The corrected exact head #3363 passed.
- The source audit found seven remaining `list_projects()` operations in the bridge; each is a true library-wide task (list/duplicate-source/series update/profile dependency/first-time character hydration/diagnostics). The Library list path caches parsed Project objects using `project.json` and `chapters.json` fingerprints.
- The frontend `window.go` wrapper refreshes project collection only for Dashboard and Library; it does not trigger `project.list` while navigating Voice, Chapters, Production, Models or History. Secondary hydration remains deferred until after the essential workspace is interactive.
- **Latest additional fix:** commit `98f604fb1fa414fb01d50d8f4a6d7186e107f1b3` moves both renderer-retry branches back to the native loading splash before starting HTML load or direct WebEngine reload. Its focused regression and packaged checkpoint are pending Build #3365.
- **Still not manually accepted:** physical target-PC responsiveness/no-flicker/no-freeze, real mixed-DPI/multi-monitor behaviour, actual shell icon and installer visuals at the user's scaling. Automated tests/package do not replace those checks.
- This repair preserves all screens, features, project/audio data and the one-time legacy migration. It does not delete or rewrite project/audio content as an optimization.
