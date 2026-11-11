# Dragon Studio — 1.2.0 Bug-Fix Register

**Tracking branch:** `dragon-studio/1.2.0-post-release-bugfixes`  
**Baseline:** current Stage 5 functional branch plus the measured-ETA repair candidate  
**Purpose:** maintain one durable register for release blockers and old/new regressions found after the 1.2.0 release.

> This branch name establishes the long-lived bug-fix workstream. It does not claim that version 1.2.0 has already shipped or that any unverified bug is fixed. The 1.2.0 release tag and packaged artifact remain the boundary between pre-release blockers and post-release regressions.

## Working rules

1. Keep the completed Stage 1–8 implementation history intact. Do not restart completed stages or replace their accepted work.
2. Every bug gets a stable ID, exact reproduction, affected version/build, root cause, code change, focused regression test, packaged checkpoint and acceptance evidence.
3. A passing unit test does not close a UI, installer, hardware, playback or packaged-EXE defect.
4. Failed workflows remain failed until their actual failure step is understood and a corrected exact-head run passes. Do not call a failed or unavailable run green.
5. Keep fixes grouped by a small related bug set. Do not combine unrelated UI, Qwen, installer and generation changes merely to reduce run count.
6. Record whether a defect is a regression from the 1.2.0 release or an older issue that remains open. Never silently relabel an older issue as newly introduced.
7. Keep the original failed run numbers, commit hashes and logs linked to each repair. Preserve superseded PRs as closed historical records rather than deleting their history.

## Current verification queue

| ID | Area | Reported defect / acceptance | Classification | Current status |
|---|---|---|---|---|
| DS-ETA-001 | Production Studio ETA | Remaining-time estimate increased over time while elapsed time increased normally; screenshots showed 15% progress with remaining estimate moving from 22:28:45 to 22:31:01 over about 23 seconds. | Existing defect; pre-release blocker until verified | Candidate repair committed: actual synthesis-call timing, rolling median/smoothing, timestamped frontend countdown and native-page parity. **Not accepted: Builds #3198, #3199 and #3200 are failed. Root cause of those CI failures still needs exact job logs.** |
| DS-PROG-002 | Production Studio progress | Ring stayed at 15% during long-running synthesis; percentage, active chapter, total workload and validated chunk progress need to be truthful and readable. | Existing defect; pre-release blocker until verified | Validated-chunk counter and workload details implemented in candidate. **Packaged visual/runtime acceptance pending.** |
| DS-DURATION-003 | Production Studio duration | Show expected audiobook listening length before completion, measured audio duration as chapters complete, and authoritative full M4B duration after validation. | Existing missing capability / accuracy issue | Text-based estimate and completed-chapter projection implemented. Must remain clearly labelled approximate until final M4B is measured. **Not runtime-accepted.** |
| DS-QWEN-004 | Qwen Voice Studio | Saved Qwen profiles and CustomVoice/VoiceDesign/Clone paths must load, preview the selected identity, save and reload consistently, and not fail inside the isolated external runtime. | Older issue; release-blocking regression risk | Earlier PR #32 documents an external runtime `app.core` import repair and Build #3058 smoke evidence. Physical target-PC saved-profile audition and save/reload acceptance remain outstanding. Re-test all modes on the final candidate. |
| DS-QWEN-005 | Qwen performance / hardware | 30-second preview target is under 60 seconds on supported NVIDIA hardware; CPU/AMD/Intel performance and backend reporting must be accurate and evidence-backed. | Older unmet performance goal | Historical CPU preview evidence around 298–305 seconds did not meet target. Do not mark complete from hosted CI or simulated GPU smoke. Physical NVIDIA, AMD and Intel acceptance evidence is required. |
| DS-JOBS-006 | Generation job lifecycle | Pause, resume, cancel, retry, interruption, durable recovery and history must refer to the correct job and preserve valid chapter checkpoints. | Existing P0 acceptance | Preserve Stage 5.4/5.5 work; run packaged interruption/recovery acceptance against current candidate. **Not closed by ETA changes.** |
| DS-M4B-007 | Full-book output | Multi-chapter generation must retain all eligible text, produce a valid chaptered M4B, validate duration/metadata and play correctly. | Existing P0 acceptance | Must pass packaged full-book generation, FFmpeg/M4B chapter validation and actual playback. **Not closed by ETA changes.** |
| DS-CAST-008 | Narrator / character assignment | Narrator-only mode, saved narrator identity, character-cast routing and Unassigned Character handling must agree across readiness, preview and final generation. | Existing behaviour; regression risk | Revalidate explicit narrator-only toggle, default-off behaviour, no-character fallback and saved voice identity. |
| DS-UI-009 | Production Studio layout | Organize the Production Studio controls and cards; prevent cover art from being permanently watermarked/embedded into the artwork; use the selected cover as artwork only. | Older user-reported UX defect | Requires source review and packaged visual acceptance at supported sizes. Keep artwork asset and app branding separate. |
| DS-BRAND-010 | Logo / Windows shell | Remove opaque white/black corner backgrounds from the logo where transparency is required; ensure taskbar, shortcut and installed-app icons use the intended transparent brand asset. | Older user-reported release defect | Re-run alpha/transparency and frozen Windows shell icon acceptance on the final installer. |
| DS-INSTALL-011 | Installer layout | Installer content was cropped at the bottom; Next/Back and details were not fully visible; unwanted black center bar/frame appeared. | Older user-reported release defect | Re-run installer window geometry tests and actual install/upgrade/uninstall on Windows. |
| DS-AI-012 | Multilingual novel analysis | Character/dialogue analysis must handle Japanese, Chinese, Korean and accented Latin text without losing names or quote evidence; English stopwords must not become characters. | Older functional defect / regression risk | Re-run Unicode-aware analysis and source-backed dialogue assignment tests on representative books. |
| DS-RESP-013 | Responsive UI | Verify Generate page and application layouts at 1280×720 and the agreed 41-viewport matrix, including mixed display scaling, ultrawide and portrait layouts. | Existing release acceptance | Keep the known Generate-page overflow and responsive regression gates. **Not closed by ETA changes.** |
| DS-HELP-014 | Help & Guide | Help and Guide content must describe the shipped features, controls, recovery paths and real limitations accurately. | Existing release acceptance | Review after the release-scope bug fixes so the guide matches the actual packaged build. |

## Workflow failures requiring diagnosis

The current screenshot shows these failed Build Windows App push runs on the former Stage 5 branch:

| Run | Commit | Commit purpose | Status |
|---|---|---|---|
| #3198 | `6466eb6a53d9286db88ffa1aa6eb9a5047012146` | Expose validated synthesis chunk progress in Production Studio | Failed |
| #3199 | `db043b67cefc1a1a447db67b8877324db5b22040` | Verify Production Studio shows validated chunk progress | Failed |
| #3200 | `ea6710d4e5f08193b1f38301c86b44fef103c44d` | Final measured ETA and chunk-progress artifact checkpoint | Failed |

These three runs are not considered diagnosed merely because their commit subjects are known. The exact failing job/step logs must be obtained before choosing a correction. The available connected Actions lookup in the current session cannot resolve these push-triggered runs by run number; #3200 is not the internal Actions run ID.

## Closure checklist for every bug

- [ ] Reproduction recorded with source version/build and exact steps.
- [ ] Failing source path and root cause confirmed from code or logs.
- [ ] Focused regression test added and observed failing before the fix where practical.
- [ ] Fix committed on this tracking branch with a bug ID in the commit/PR description.
- [ ] Focused tests pass on the exact commit.
- [ ] Full regression suite passes on the exact commit.
- [ ] Windows packaged artifact checkpoint passes on the exact commit.
- [ ] Real Windows UI/installer/audio/hardware acceptance completed where applicable.
- [ ] Evidence (run URL, artifact, logs, screenshot or playback result) attached to the bug record.
- [ ] Help & Guide updated if the user-visible workflow or limitation changed.

## Release boundary

Before the 1.2.0 tag, release-blocking rows stay in the release candidate checklist. After the exact 1.2.0 artifact is tagged and distributed, every newly discovered issue is marked either **post-release regression** or **older issue still open**, with the affected released version and first known bad build recorded. The branch remains the shared fix queue; it is not a reason to reopen or redo already accepted stages.
