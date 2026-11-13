# Stage 5 — Measured Generation ETA and Audiobook Duration

## Scope

This checkpoint repairs the Production Studio estimate shown while a long-form audiobook is being synthesized. It does not claim that Qwen exposes token-level progress.

## Implementation

- The chapter generator measures wall time around the actual TTS synthesis call. Batch synthesis is measured as one batch and its text workload is aggregated.
- GenerationManager forwards the measured duration, workload size and completed-work counters as a distinct timing event.
- Production Studio excludes the first synthesis call from steady-state timing because it can include cold model loading and accelerator warm-up.
- ETA is based on the median of recent measured synthesis seconds per text unit, smoothed against the previous estimate. It is not inferred from the interval between UI callbacks.
- Chapter changes and provider diagnostics preserve the last valid measured ETA.
- The web frontend counts that estimate down between timing events using its measurement timestamp. A stale estimate is explicitly labelled when the active chunk outlasts it.
- The native Generate page uses the same measured timing event and does not extrapolate from elapsed time divided by completed work.
- Narration progress remains the ratio of completed normalized text workload. It does not invent Qwen token completion.
- The project summary exposes a clearly labelled text-based listening-length estimate. Once chapters finish, the UI can project runtime from measured audio duration and completed text workload; the validated M4B duration remains authoritative.
- Production Studio also displays the count of validated/saved synthesis chunks so users can distinguish committed progress from a currently rendering Qwen chunk.
- M4B assembly is shown as a separate phase. No packaging ETA is invented where the packager does not report a reliable measure.

## Automated regression coverage

`tests/test_stage5_generation_eta_stability.py` covers actual synthesis timing callbacks, outlier resistance, frontend countdown, the native page's measured-sample contract, runtime estimates, the 1:1 progress-ring contract, and the paused-job ETA clock reset on resume.

## Acceptance still required

- The exact-head regression suite and Windows package checkpoint must pass.
- On the target PC, run a long Qwen audiobook across several chapters and verify that elapsed time increases, the measured ETA counts down between chunks, then refreshes from completed chunk timings without large one-sample jumps.
- Verify narrator-only and character-cast generation, cancellation, pause/resume, recovery and final M4B playback remain intact.
- Compare Qwen timing on the user's NVIDIA device and any supported AMD/Intel devices separately. CI without the physical target GPU does not establish real-device performance.
- Listen to the final audiobook and verify its measured duration and chapter markers. A text-based listening-length estimate is only an approximation.


## Monotonic ETA correction — Dragon Studio follow-up

- While a published estimate is still positive, subsequent chunk measurements may shorten it, but a slower single chunk cannot increase the displayed remaining time.
- When the estimate reaches zero before the workload finishes, the UI retains its existing "past the last measured estimate" state rather than jumping back to a positive number.
- Faster measurements can shorten the estimate with the existing 25% downward smoothing; slower measurements cannot increase an active estimate. A replacement estimate is published only after three further completed chunks confirm the prior estimate was exceeded; it is explicitly marked as recalibrated.
- Regression coverage verifies the reported 23-second countdown case, isolated slow-chunk handling, and sustained-overrun recalibration.

## Exact-head packaged checkpoint — Build #3323 (12 Nov 2026)

- Exact tested head: `1c235746646a4a3ba0263178cb1bba045ebffd93`; PR run [#3323](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43139856426).
- The regression suite passed 1,523 tests and the Windows package job passed, including the package's UI/installer and real bundled-Piper two-chapter M4B acceptance.
- The package run confirms the measured ETA/progress implementation remains buildable and its automated regressions remain green. It does **not** verify a long-duration real Qwen generation on the target PC.
- Still required: observe several chapters of real generation and verify measured chunk progress, stable/decreasing remaining ETA, warm-up handling, elapsed synthesis, pause/resume, audiobook listening-duration projection and final measured M4B duration. Compare ETA behaviour on real selected provider/backend, not simulated timings.
- Hardware target remains separate: real NVIDIA/AMD/Intel Qwen results are required; hosted CPU and mocked backend tests do not establish GPU preview performance.



## A/B continuation regression — 13 November 2026

- The new `test_pause_resume_excludes_paused_time_from_eta_countdown` verifies the saved estimate is frozen during pause, its wall-clock timestamp is cleared, and resume establishes a fresh wall-clock timestamp plus a fresh monotonic anchor.
- The regression simulates a long suspended interval and proves that only active post-resume time is deducted from the measured remainder.
- The Windows workflow runs `tests.test_stage5_generation_eta_stability` as a dedicated focused Stage B step before the full regression suite. Packaging remains gated on the full tests job.
- No interpolation of narration percentage during a currently rendering Qwen chunk is introduced. Percentage remains a truthful completed-work ratio; validated chunk count and active synthesis status provide additional context.
- Target-PC long-book listening, Qwen hardware timing, physical DPI and manual audio acceptance remain separate from this automated A/B checkpoint.



## Build #3370 A/B continuation — package gate result

- The exact-head focused Stage B module passed **16/16**, including `test_pause_resume_excludes_paused_time_from_eta_countdown`; the full regression suite passed **1,544/1,544**.
- The same run built and verified the frozen application and passed the real bundled-Piper two-chapter M4B acceptance. Its M4B evidence artifact was uploaded (artifact ID `14002562242`).
- The Windows package did not complete: packaged Sound Design acceptance failed at the final mismatched Task Manager View-action repair. This check had also failed in #3368 and passed in #3369 while the frontend source remained unchanged, indicating a timing-sensitive acceptance trigger rather than a confirmed A/B application regression.
- The packaged test incorrectly waited 10 seconds for the next periodic poll while assuming 1.5-second active-job polling. The production scheduler intentionally backs off to 10 seconds when idle and 30 seconds while hidden and idle. The acceptance now requests a real immediate refresh through the existing Task Manager button after each deliberate View-action mutation, then still proves the same row and action identity are preserved.
- The Stage A/B Windows package checkpoint stays **open** until the corrected exact-head run passes the complete packaged acceptance and creates the Windows installer/portable/hash artifacts.


## Exact-head A/B package checkpoint — Build #3371 (13 Nov 2026)

- Exact tested head: `550cccc0508d0341889e7c88bfe44bea9ff93da1`; [Build Windows App #3371](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43351171744).
- Focused Stage B measured-generation progress/ETA suite passed **16/16**, including the long-pause/resume clock-anchor regression. Focused Stage 6 preflight passed **48/48** and the full suite passed **1,544/1,544**.
- The exact-head Windows package also passed frozen-app verification, bundled voice modules, real two-chapter Piper M4B generation/decode, packaged Sound Design/Music Library acceptance, installer creation/startup, hosted install/launch/upgrade/uninstall, logo/hash checks, package-size report and Microsoft Defender scans.
- Both packaged Task Manager View-action repairs passed. The acceptance now triggers the normal immediate refresh; the adaptive production polling intervals remain unchanged.
- The Stage A/B automated and hosted Windows package checkpoint is **passed** at this SHA.
- This does not close real long-running Qwen generation, target-PC ETA/progress/listening-duration comparison, GPU performance, full-book output, or physical DPI/display acceptance. Keep those as separate acceptance gates.
