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
- The artifact-checkpoint commit following these focused runs is the Step 3 Windows package candidate. Its frozen-app, installer, bundled-asset, manifest, malware-scan and artifact-upload outcomes must be recorded from the actual workflow before claiming package acceptance.

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
