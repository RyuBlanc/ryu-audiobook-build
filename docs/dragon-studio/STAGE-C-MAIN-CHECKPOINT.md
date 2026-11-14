# Stage C — Main Engineering Checkpoint and Stage D Handoff

**Checkpoint date:** 14 November 2026  
**Repository:** `RyuBlanc/ryu-audiobook-build`  
**Tracking PR:** [#35 — Dragon Studio: Post-1.2.0 Qwen & Responsiveness Acceptance](https://github.com/RyuBlanc/ryu-audiobook-build/pull/35)  
**Tracking branch:** `dragon-studio/1.2.0-post-release-bugfixes`  
**Baseline before this checkpoint record:** `796c951ed0862053259d6fb4eb16afe25fdd3aaa`  
**Exact-head hosted package evidence:** Build Windows App #3418 / [run 43571681201](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43571681201)

## 1. Checkpoint decision

Stage C is accepted as the **engineering and non-physical integration checkpoint**, and Stage D may begin from this preserved baseline.

The project owner explicitly confirmed on 14 November 2026 that the previously listed non-physical Stage C integration items are now complete and that the remaining work is the physical target-machine check. That owner confirmation is recorded here as an **owner-attested acceptance statement**. Detailed local run logs, full-book output links and device benchmark evidence were not attached to the GitHub record available during this checkpoint review; this document does not misrepresent that missing material as independently inspected CI evidence.

This is **not** a claim that physical Windows/accelerator acceptance has passed. The parent Stage C remains physically open until the target-machine checklist in Section 5 is completed. Stage D is allowed to proceed without reopening C1–C4 implementation work.

## 2. C1–C4 sub-stage status

| Sub-stage | Main checkpoint status | Evidence and boundary |
|---|---|---|
| **C1 — Voice identity and assignment** | **Complete** | Focused C1 10/10 and exact-head #3418 hosted package acceptance passed. The remaining target-machine visual/interaction review is carried as physical sign-off, not reopened implementation. |
| **C2 — Profile lifecycle and repair** | **Complete** | Focused C2 9/9 and hosted lifecycle/rollback/restart acceptance passed, including the earlier exact-head #3382 package checkpoint. Target-machine visual/runtime inspection remains physical sign-off. |
| **C3 — Accelerator and performance** | **Software/hosted work complete; physical device sign-off carried forward** | Focused C3 8/8 and #3418 hosted regression/package passed. The formal C3 document still requires actual device/backend telemetry and saved-profile benchmark evidence for each backend claimed as supported. The owner reports the non-physical integration work complete; the hardware/device result must remain separately attributable to its actual machine, backend, model and measured preview. CPU-only Provider #448 evidence is not a GPU pass. |
| **C4 — Multilingual identity and expression** | **Implementation/provider/package checkpoint complete** | Focused C4 37/37; Provider Runtime Smoke #448 passed real CPU CustomVoice/Clone/VoiceDesign, saved-profile reload and multilingual identity continuity; #3418 hosted Windows package passed. The owner reports the remaining non-physical full-book integration/listening work complete. Target-machine review is carried forward. |

C1 and C2 are not reopened. Do not repeat the focused C1/C2 suites merely to clear old target-machine checklist labels.

## 3. Exact-head hosted evidence

Build Windows App **#3418**, run [43571681201](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43571681201), validated the prior PR head `796c951ed0862053259d6fb4eb16afe25fdd3aaa`.

- Stage B: **16/16**.
- Stage 6: **48/48**.
- C1: **10/10**.
- C2: **9/9**.
- C3: **8/8**.
- C4: **37/37**.
- Full regression: **1,596/1,596**.
- Windows packaging: passed frozen-app and bundled-asset verification, packaged UI/Production acceptance, M4B/FFmpeg fixture, core and HTML installer build/startup, install/launch/upgrade/uninstall, branding transparency/hash checks, package-size reporting, Defender and artifact uploads.
- Packaged GenerationManager acceptance passed pause/resume/cancel, retry, interruption, process restart/recovery, checkpoint reuse and History/project/job/output identity.
- Packaged responsive checks passed the 41-viewport emulation and 15-destination overlap scan. The Help destination/content/navigation contract passed.

Artifacts from #3418:
- Installer: [14105118499](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43571681201/artifacts/14105118499) — 847,140,795 bytes.
- Portable: [14105078539](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43571681201/artifacts/14105078539) — 1,190,866,285 bytes.
- SHA/package manifest: [14106040093](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43571681201/artifacts/14106040093).
- Real M4B fixture: [14104564531](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43571681201/artifacts/14104564531).

Provider Runtime Smoke **#448**, run [43499302368](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43499302368), remains the cited real CPU Qwen identity evidence: saved CustomVoice 0.6B/1.7B, authorized Base Clone, Japanese VoiceDesign and nine additional language profiles passed reload/identity checks; its character-to-M4B fixture covered two chapters. The recorded 30-second CPU VoiceDesign preview times (187.318s and 336.607s) did **not** meet the 60-second target and must not be presented as GPU performance.

## 4. Owner-attested non-physical integration closeout

The project owner has confirmed that these non-physical parent Stage C activities are complete as of this checkpoint:

- Representative full-length Qwen audiobook generation and listening/integration review.
- Long-generation progress, elapsed time, ETA, final duration and recovery review.
- Cross-module narrator/character identity and profile workflow integration review.
- Help & Guide content/readability review for the current feature set.
- Remaining non-physical Stage C integration checks previously listed in the Stage C reconciliation.

These are recorded as **owner-attested complete**. The current PR record did not expose the underlying local logs/audio/device reports for independent replay or hash verification. Add those evidence references when available; do not invent run numbers or artifact IDs.

## 5. Physical target-machine carry-forward — still open

Only the physical acceptance lane remains open for this checkpoint:

1. Actual Windows application visual/interaction inspection on the target PC: normal, minimized, restored, maximized and split-screen use; no flicker, frozen controls or crashes.
2. Actual display/DPI/multi-monitor checks at the intended 100%, 125%, 150% and 200% scaling, including mixed monitors, ultrawide and portrait layouts.
3. Actual installed shortcut/taskbar icon and cover-art/app-brand separation inspection.
4. Actual installer wizard geometry and button/footer visibility at the target display resolution and scaling.
5. Device-specific accelerator evidence must remain tied to the real device/backend. Do not infer CUDA/ROCm/XPU acceptance from hosted CPU jobs, hardware-candidate detection or this owner-attested integration checkpoint. Where a supported GPU performance claim is made, retain the real decoded preview, backend telemetry, model identity and elapsed-time evidence.

These are carry-forward sign-off checks. They do not reopen C1/C2 implementation or invalidate the #3418 hosted package checkpoint.

## 6. Stage D handoff

- **Stage C main engineering checkpoint:** recorded at this document and the exact-head hosted evidence above.
- **Next active stage:** Stage D.
- Preserve Stage C's accepted implementation and CI history. Do not restart or re-run completed C1–C4 work unless a Stage D change demonstrates a regression.
- Keep the physical carry-forward list in Section 5 visible and separate from Stage D's implementation backlog.
- The current roadmap names the sequence A → B → C → D → E → F but does not define a Stage D scope/acceptance charter. Before Stage D source changes, record its objective, included requirement IDs, exclusions, focused tests, regression gates and exact package criteria in a Stage D-specific plan. Do not infer a Stage D feature scope from the label alone.
- PR #35 remains draft/unmerged. This checkpoint does not authorize merging PR #35, publishing a release or deleting historical failed runs.

## 7. Checkpoint integrity rules

- Preserve all Stage 1–8 milestones and historical failures.
- A future Stage D checkpoint must be tied to its exact branch, commit SHA, successful tests, Windows package, artifacts and applicable runtime evidence.
- Do not weaken tests, relabel failed workflows or mix artifacts from different commits.
- The 500 MB installer target remains deprioritized; keep required offline assets.
