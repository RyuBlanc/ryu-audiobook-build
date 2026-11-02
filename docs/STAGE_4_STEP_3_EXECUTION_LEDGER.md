# Stage 4 — Step 3 Execution Ledger: Preview, Synthesis and Audio Assembly

**Status:** In progress  
**Working branch:** `stage-4/step-3-preview-assembly`  
**Baseline:** Step 2 artifact checkpoint `2213ffff90bf022d8a0599eb873e0e14df5ea8b7` (#2053, successful)  
**UI constraint:** Preserve the approved Premium V2 layout. Wire existing controls to real project/chapter data; no demo audio, placeholder results, or redesign.

## Scope and functional flow

Step 3 implements and verifies the Preview, Synthesis and Audio Assembly gates from Stage 4 plan §4.3. It also carries forward PROD-15 chapter-specific preview/download from the Step 2 closeout.

1. **Chapter-specific production preview and download (PROD-15).** Resolve the active project's selected chapter, validate that it has source narration, use the selected narrator profile and requested preview duration, return chapter identity with the measured audio result, and save only the generated preview through the existing native Save As action. An absent, stale or empty chapter must fail visibly; silently previewing chapter 1 is not acceptable.
2. **Pronunciation-aware voice preview.** Use the saved project pronunciation switch and effective Book → matching Series → Global rules for ordinary previews. Keep explicit Written-versus-Pronounce-as comparison previews literal. Return selected saved profile/provider/voice identity, actual duration and applied replacement counts. Verify enabled/disabled rules against the same source chapter.
3. **Real sound-design preview.** Use persisted BGM strategy, chapter assignment, cue paths, gain, fades and timing. Report the measured rendered duration; use only imported/assigned assets; Voice Only must not leak BGM or fixed cues.
4. **Chapter and book assembly.** Reuse saved narration where applicable, keep opening/Next Chapter/closing cues at their intended boundaries exactly once, preserve chapter order and metadata, and prevent preview staging from mutating reusable generation checkpoints.
5. **Cancellation, failure and retry safety.** Stop at documented safe synthesis/FFmpeg boundaries, mark cancellation distinctly from failure, discard partial preview files, clean temporary/staging files and provider/event registrations, and allow a clean retry.
6. **Checkpoint integrity and acceptance.** Verify changed pronunciation/sound assignments invalidate only affected synthesis work, preserve unrelated compatible chapters, and compare chapter/full-book preview with final output. Automated tests and Windows packaging do not replace target-PC listening.

## Initial work and evidence

- Branch created directly from Step 2 checkpoint `2213ffff90bf022d8a0599eb873e0e14df5ea8b7`; Step 2 history and artifacts are preserved.
- Initial audit found that the Generate-page `production.preview` action sent profile and duration but omitted the selected chapter. The backend therefore selected the first non-empty chapter when no text/chapter was provided. This violated chapter-specific preview behavior.
- Step 3 correction: the Generate-page action now sends the current selected chapter number and rejects an empty/stale selection; the backend independently validates that chapter and no longer falls back to a different chapter for a production preview.
- Chapter number/title are attached to the completed preview result and retained by the frontend. The existing native Save As flow now suggests a filename containing the actual chapter number/title, even if the user changes chapter selection before saving.
- Generate-page preview callbacks now use the preview request epoch: if a newer preview starts while an earlier job is still running, the earlier completion cannot replace the newer request's audio or status.
- Added regression coverage for missing/stale/empty selected chapters, backend forwarding, preview-result identity and frontend save wiring.
- Second audit found successful production cleanup deleted all per-chapter WAVs and manifests immediately after packaging. That made later full-book mix preview impossible and forced full narration re-synthesis for sound-design-only changes. Step 3 retains these project-local checkpoints after successful export; changed pronunciation invalidates only chapters whose prepared narration chunks change, while a new sound-design configuration is applied to a fresh M4B assembly using the retained narration.


## Focused Windows verification history

- **Run #2054** (2026-11-02): 1,041 tests passed; Premium V2 JavaScript syntax and isolated Qt lifecycle checks passed. Workflow push trigger was enabled for this branch; artifact job intentionally skipped for the focused implementation commit.
- **Run #2055** (2026-11-02): 1,042 tests passed, including successful-export checkpoint retention, selective pronunciation invalidation, and sound-only M4B reassembly with the changed BGM path.
- **Run #2056** (2026-11-02): 1,043 tests passed, including the Generate-page stale-preview completion guard.

- **Run #2057** (2026-11-02): 1,043 tests, one failure in the newly tightened preview metadata *test fixture*. The fixture declared a Qwen provider but omitted the warm-provider-cache API used by the Qwen path, so its mock bridge failed before provider creation. This did not indicate an application runtime regression. Corrected the contract fixture to use Piper while still asserting selected profile/provider/voice/chapter identity. Run #2057 did not reach the build job; rerun from the corrected artifact-checkpoint commit.

- The corrected artifact-checkpoint commit is the Step 3 Windows package candidate. Its frozen-app, installer, bundled-asset, manifest, malware-scan and artifact-upload outcomes must be recorded from the actual workflow before claiming package acceptance.

## Step 3 acceptance checklist

- [ ] Chapter-specific preview/download: selected chapter, selected narrator, supported duration, actual duration, playback and native save verified on the packaged app.
- [ ] Pronunciation ON/OFF and individual-rule preview/production parity with selected profile/provider/voice verified.
- [ ] Same BGM / Chapter-Based BGM / Voice Only and cue sequence rendered and listened to.
- [ ] Opening, Next Chapter and Closing cues verified once at the correct boundaries in real output.
- [ ] Volume, fades, offsets and measured duration compared between preview and final output.
- [ ] Provider/FFmpeg failure, cancel, retry and temporary-file cleanup verified.
- [ ] Chapter checkpoints verified after pronunciation/sound-assignment changes; unrelated chapters remain reusable. Automated regression covers selective chapter invalidation and sound-only reassembly from retained narration.
- [ ] Full unittest suite, frozen application, installer, manifest, malware scan and artifact upload pass on the final Step 3 checkpoint SHA.
- [ ] Target-PC listening and installed-app interaction recorded separately from CI evidence.

## Carried-forward acceptance — not waived by Step 3 CI

The Step 2 real imported-book AI report checks; pronunciation save/edit/reload; BGM/cue save/edit/clear/relink/reopen; real voice/profile auditions; and target-PC mix listening remain external acceptance items. Stage 1 hardware freeze/crash, Stage 2 supported-format import/edit/reopen, and Stage 3 Voice Studio/Character Studio persistence and actual voice acceptance also remain open. Do not label any of these complete from CI alone.

## Latest Step 3 audit and automated verification — 2 November 2026

- **Verified code head before the artifact checkpoint:** `130fb69be6715f34521426899c31dacb9e7b4b2f`.
- **Run #2061:** [Windows test workflow](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41427723537) completed successfully on that head. The full regression suite ran **1,045 tests in 46.347 seconds**. Premium V2 JavaScript validation and isolated native Qt lifecycle regression also passed. The build job was intentionally skipped because this commit did not carry the artifact-checkpoint marker; a package checkpoint is being initiated separately.
- Added a regression that exercises the real short-preview sound-design worker path, verifies the actual mixed output duration (10.7 seconds in the deterministic fixture), retains the rendered M4A, and confirms the intermediate voice-preview WAV and opening-cue staging M4A are deleted.
- Fixed the corresponding worker cleanup: after a successful sound-design mix, the intermediate narration WAV is deleted while the mixed M4A remains the playable preview. Failure/cancel cleanup continues to remove both partial outputs.
- Added a direct preview-worker regression for the project pronunciation master switch ON/OFF. Enabled book entries are forwarded, disabled entries are filtered, and OFF sends an empty effective dictionary. Selected profile/provider/voice identity remains covered by the existing preview contract tests.
- **Failed attempts are accounted for:** #2059 exposed malformed test line continuations in the new fixtures; #2060 confirmed the syntax fix and ran 1,045 tests but exposed a missing `_include_sound_design_preview` flag in the new mix-test fixture. Both test-only issues were corrected. #2061 is the successful corrected test result; neither earlier failure is counted as a passing run.
- The existing decoded M4B integration suite verifies opening, Next Chapter, and closing cue placement exactly once, checks Voice Only omission, and compares Same BGM versus Chapter-Based selections without fallback. Existing cancellation/retry and selective checkpoint-reuse tests also pass in the #2061 full suite.
- Remaining limitation is unchanged: CI does not listen to the installed app. Target-PC acceptance remains required for real saved-book preview selection and Save As, actual pronunciation ON/OFF speech, real BGM/SFX level/fade/offset and cue audibility, preview/final listening parity, and interactive save/edit/reopen behavior.

## Current Step 3 acceptance disposition

- **Automated/code gates:** §4.3 items 1–5 are covered and pass on #2061 (1,045 tests).
- **Manual gate:** target-PC listening and installed Windows app interaction remain open. Step 3 must not be described as fully signed off until those checks are recorded.
- **Packaging gate:** the artifact-checkpoint Windows build and its Defender/artifact outcomes must be recorded from the current candidate before handoff.

