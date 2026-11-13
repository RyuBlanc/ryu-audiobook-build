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
