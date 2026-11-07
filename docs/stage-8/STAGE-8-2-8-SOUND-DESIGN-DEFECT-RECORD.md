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
