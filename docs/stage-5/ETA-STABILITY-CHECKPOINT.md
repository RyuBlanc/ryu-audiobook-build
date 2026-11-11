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

`tests/test_stage5_generation_eta_stability.py` covers actual synthesis timing callbacks, outlier resistance, frontend countdown, the native page's measured-sample contract, runtime estimates and the 1:1 progress-ring contract.

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
