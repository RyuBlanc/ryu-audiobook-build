# Stage 8.2.8 — Sound Design integration defect record

## Defect found: Chapter-Based BGM leaked automatic music

**Area:** M4B assembly / preview-to-final sound strategy  
**Priority:** P1 core workflow; release-blocking if wrong music is audible  
**Affected implementation:** `app/audio/assembler.py`

### Required behavior

Under the frozen Version 1 rules, Chapter-Based BGM ignores the book-default track. A chapter may contain one explicitly saved track or no BGM. An unassigned chapter must remain narration-only. Automatic mood-selected BGM must not become a fallback, and the explicit chapter track must not be layered over automatic/default music.

### Root cause confirmed by source inspection

The assembler's automatic-audio branch resolved and mixed a mood-selected music track for every chapter whenever `background_audio_mode == "auto"`. The later chapter-scoped BGM pass was restricted to `background_audio_mode == "manual"`. Therefore, a Chapter-Based project using auto audio mode could receive automatic music on unassigned chapters, and an explicitly selected chapter track could be applied after the automatic bed had already been mixed.

### Test-first change

- Test commit: `ef8044248daf2f109025861d231831f54cd19ca4`
- Added regression: `RegressionTests.test_chapter_based_bgm_never_falls_back_to_auto_music`
- The regression builds a two-chapter fixture, configures Chapter-Based BGM in auto mode, assigns one explicit track to chapter 1 and No BGM to chapter 2, and asserts that automatic music resolution is never called and the explicit chapter mixer runs exactly once with the selected track.

### Root-cause fix

- Fix commit: `cb25247c4dc95ff9f8ae518fe40dd7a52e17d583`
- In Chapter-Based strategy, automatic mood-track resolution is bypassed.
- Chapter-scoped BGM is now applied whenever audio mode is enabled (auto or manual), while global Voice Only/off still suppresses BGM.
- The existing chapter assignment resolver continues to treat legacy `default` values as `none`; it does not restore book-default fallback.

### Verification status

- Source change: committed.
- Regression test: committed.
- Local test execution: not available in this session; do not mark the regression passed until CI reports it.
- Exact candidate commit for this checkpoint: this documentation commit's HEAD.
- Windows packaging and runtime audio acceptance: pending CI and target-Windows verification.

### Required CI/audio checks

1. Run the full regression suite and confirm the new test passes.
2. Inspect the Windows build result and artifact SHA manifest for this exact HEAD.
3. Verify a Chapter-Based book with one custom chapter track and one No BGM chapter; confirm no automatic/default bed is audible in the unassigned chapter.
4. Verify Same BGM still uses one book-default track across all chapters.
5. Verify Voice Only excludes BGM and fixed cues.
6. Compare Book Mix Preview and final M4B using the same saved strategy and assignments.

Do not mark SD-02, SD-05, SD-06, SD-07, SD-12, SD-13, SD-14, GEN-06 or PROD-15 complete from this source fix alone. Each still requires its own relevant tests and audio/runtime evidence.


## Second defect found: Production chapter preview used automatic fallback

The separate Production chapter sound preview path in `PremiumV2Bridge._render_sound_design_preview` had the same policy leak. It entered the explicit chapter-assignment branch only when `background_audio_mode == "manual"`; with a legacy/stale `auto` mode it selected automatic mood music even when the saved BGM strategy was Chapter-Based.

### Test-first change

- Regression test commit: `fb82fe037296c6cdfd330f921fef3d500d4abbab`.
- Added two behavioral routing tests:
  - Chapter-Based + auto mode + No BGM must not call automatic music resolution or chapter mixer.
  - Chapter-Based + auto mode + explicit chapter track must call the chapter mixer with that exact track and must not resolve automatic music.

### Root-cause fix

- Source fix commit: `37d30f94a8244d0eac87dc6b4601195cf5ff9030`.
- The chapter preview now enters the explicit chapter assignment branch whenever the strategy is Chapter-Based, regardless of the legacy audio source mode. Same BGM continues through the existing manual/automatic source-mode handling.

### Updated verification boundary

- Both the full M4B assembler and the Production chapter-preview path now have test-first regression coverage and source fixes.
- Neither new test batch has a confirmed passing matching-head CI result in this record.
- Actual listening tests for an assigned chapter, an unassigned chapter, Same BGM and Voice Only remain required.


## Full-book mix preview regression coverage

- Test commit: `bc5429e72e8d8d4857aa91f10925e6cc37d2cc36`.
- Added `test_full_book_sound_preview_reuses_only_saved_eligible_chapter_audio`.
- The test confirms the full-book preview start path uses stable chapter IDs to locate saved narration, excludes empty/skipped chapters, does not re-synthesize narration, queues the preview worker, and reports the expected included chapter set.
- The worker's disposable-copy safety, actual M4B render and cancellation behavior still require matching-head tests and runtime acceptance.



## Third defect: BGM validation and Same BGM policy were still mode-dependent

Two further edge cases were found by tracing saved-state validation and the assembler's legacy auto mode.

### Chapter-Based validation was checking the wrong asset

- In legacy `auto` source mode, validation checked `auto_music_track_path` and did not validate explicit chapter overrides.
- This could block a valid Chapter-Based No BGM chapter because an unused automatic track had been deleted.
- Conversely, it could allow a missing explicitly assigned chapter track through validation.

**Test-first evidence**
- Regression tests: `test_chapter_based_auto_mode_ignores_stale_automatic_track_path` and `test_chapter_based_auto_mode_validates_explicit_chapter_track`.
- Test commit: `9c456dbb18498ec0461ce0391b20045092bcb7c4`.
- Fix commit: `5b31851b663a9ccadebe3fb36d89e972d067bfd1`.
- Chapter-Based validation now validates only explicitly assigned custom chapter tracks, regardless of legacy auto/manual mode; it ignores stale book-default/automatic paths. Voice Only still bypasses inactive asset validation.

### Same BGM could choose a different automatic track for each chapter

- In legacy `auto` source mode, the assembler resolved mood music independently for every chapter even when the saved strategy was Same BGM.
- This contradicted the book-level single-track rule.

**Test-first evidence**
- Regression test: `test_same_bgm_auto_mode_uses_one_track_for_every_chapter`.
- Test commit: `ef431137c5850bbae9f88d9f99cec641a6a579c1`.
- Fix commit: `24cf31f0f6b76ea8e700e0c60ee99bd04835b241`.
- The assembler now resolves one automatic legacy-mode track on the first eligible chapter and reuses that exact path for every chapter. Chapter-Based remains explicit-only.

### Remaining preview limitation to resolve

The individual Production chapter sound preview currently rejects the `after_first_paragraph` BGM start offset because its temporary preview audio does not carry saved full-chapter paragraph timing boundaries. Final full-book assembly has a boundary-aware path. This is an open preview/final parity gap; do not mark the start-offset preview requirement complete until it is implemented and tested.

### Updated verification boundary

These are source/test commits only. Matching-head CI, packaged Windows audio listening and final preview-vs-M4B comparison remain pending.
