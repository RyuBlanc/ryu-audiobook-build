# Stage 3 Final Artifact Checkpoint — 1 November 2026

## Scope and decision

This checkpoint captures the verified Stage 3 source state after the Premium V2 narrator-preview save-scope fix. The default Premium V2 interface, regression suite, provider functional smoke and real multi-chapter Piper/M4B acceptance are green.

**Source commit before this checkpoint:** `b84e39abd4acbbf0ccf21f55e9609faa6421aa67`  
**Branch:** `stage-3/restart-from-stage2-closeout-1794`

The final Windows package build is gated on this checkpoint. This document does not claim that the target-PC Qwen performance or subjective acoustic-listening criteria have been verified.

## Verified gates

| Gate | Run / evidence | Result |
|---|---|---|
| Full regression suite | Build Windows App #1899, run [41278585482](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41278585482) | **962 / 962 passed** in 38.067 seconds |
| Premium V2 default WebEngine acceptance | Provider Functional #303, run [41278585479](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41278585479), artifact #13072346385 | **Passed — 20 assertions** |
| Real Piper + Edge synthesis and Voice Studio preview | Provider Functional #303, same run | **Passed** |
| Real Chatterbox Nano synthesis | Provider Functional #303, same run | **Passed** |
| Chatterbox pinned API | Provider Runtime #303, run [41278585480](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41278585480) | **Passed** |
| Kokoro real synthesis | Provider Runtime #303, same run | **Passed** |
| Qwen expression protocol | Provider Runtime #303, same run | **Passed** |
| Real Qwen 1.7B VoiceDesign synthesis | Provider Runtime #298, run [41275601268](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41275601268), artifact #13071655233 | **Passed** — real model loaded, warm worker reused, 30-second preview produced |
| Real multi-chapter audiobook and M4B | Provider Functional #303, artifact #13071739190 | **Passed** — two chapters, FFmpeg decode successful, two chapter markers |
| Final Windows installer / portable / SHA-256 package | Build Windows App #1883, run [41258708013](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41258708013) | Earlier checkpoint passed; a new package is required for this source state |

### Premium V2 UI acceptance — 20 assertions

The retained Premium V2 browser evidence verifies:

- Active project and all four saved Voice Studio profiles hydrate in the shipped Premium V2 interface.
- Assigned Cast uses saved assignment provenance: Mira has 2 lines across 2 chapters, 50% AI-assigned, with one separate manual row and one AI row.
- Selected saved character profile, exact saved dialogue row, real Piper preview and embedded playback work.
- Narration is automatically identified as Narrator; unknown quoted dialogue remains Needs Speaker Review.
- Manual Ren assignment saves against the exact source offsets and series identity.
- Series narrator default saves from a saved Voice Studio profile and its Create Series sample preview generates and plays real audio.
- Project narrator override remains independent of the Series Default; Reset restores live inheritance.
- Project Narrator preview accepts narration-only selected source text, uses the effective narrator profile, creates a real preview and successfully plays it in the embedded player.

### Real Piper preview and M4B evidence

Provider Functional #303 logs confirm:

| Requested preview | Actual duration | Synthesis elapsed |
|---:|---:|---:|
| 10 seconds | 10.101 seconds | 2.983 seconds |
| 30 seconds | 30.117 seconds | 1.970 seconds |
| 60 seconds | 60.141 seconds | 3.682 seconds |
| 90 seconds | 90.699 seconds | 5.484 seconds |

The same real multi-chapter test produced an M4B with 2 chapter markers. The saved narrator was used for narration segments; Mira's saved profile was called in both chapters and Ren's saved profile was called for his dialogue. Crowd, door-slam and rain story-event cues were detected. FFmpeg decoded the completed M4B successfully.

### Real Qwen evidence

The actual Qwen run used `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`, not a protocol mock. It generated a 31.440-second preview and warm/angry expression audio, reused the worker, and generated the Japanese pronunciation preview. The Japanese source became `リムルが来た。` and the saved Rimuru pronunciation rule was counted exactly once.

The warm 30-second preview took **307.885 seconds on the hosted CPU**. Therefore:

- Real Qwen VoiceDesign functionality: **passed**.
- Qwen 30-second preview under 60 seconds on hosted CPU: **not met**.
- Qwen under-60-second target on the supported target GPU: **not measured here**.

## Requirement status

The original requirement identifiers are preserved. This checkpoint does not renumber or silently remove any item.

| Requirement group | Verified here | Remaining qualification |
|---|---|---|
| VS-01 | Actual Qwen VoiceDesign model, 30-second output, worker reuse and real audio verified | Under-60-second target not met on hosted CPU; target GPU benchmark remains unverified |
| VS-02 | Saved profile identity and same character voice routing across chapters verified | Subjective acoustic listening for voice consistency remains unverified |
| VS-03 | Expression classification/protocol and real Qwen audio generation verified | Audible emotional delivery quality remains unverified |
| VS-04 | Story-event cue detection includes crowd, door-slam and rain in the real M4B acceptance | Subjective acceptance of the final background/crowd/effect mix remains unverified |
| VS-05 | Real Piper, Edge, Chatterbox and Kokoro provider checks passed | Cross-provider subjective emotion/effects parity remains unverified |
| VS-06 | Japanese pronunciation rule transformed source text correctly and produced real Qwen/Kokoro audio evidence | Human listening confirmation of exact spoken pronunciation remains unverified |
| VS-07 | Pronunciation rule and expression protocol tests passed | Audible emotion/pronunciation interaction remains unverified |
| VS-08 | Regression and Premium V2 UI acceptance passed for saved profiles, audition, playback and assignment | No new code change remains open in the tested Stage 3 fixes |
| CS-01–CS-08 | Default Premium V2 browser acceptance covers live project identity, profile selectors, saved provenance metrics, exact-span assignment, audition and persistence | No additional automated blocker identified |
| CS-09–CS-12 | Automatic Narrator / Needs Speaker Review, series default, project override/reset, selected narration preview and production-profile playback verified | No additional automated blocker identified |
| Step 11.8 | Real-provider multi-chapter M4B and default Premium V2 flow verified | Subjective final-audio listening remains outside automated evidence |
| Step 11.9 | Earlier package checkpoint #1883 passed | New package checkpoint must be built from this commit |

## Explicitly excluded / deferred

- Installing the final Windows Setup.exe on the user's personal PC is excluded from this in-chat test scope and remains the user's own check.
- No cleanup is authorized by this checkpoint. Retain the new package artifacts, the #1883 baseline and the rollback packages until the final build is verified and the user authorizes cleanup.
- A hosted CPU run cannot prove the sub-60-second Qwen target on the user's GPU. No claim is made that this has passed.

## Final package gate

Create the Windows artifact checkpoint from this source state. The build must pass its own regression, packaging, frozen executable, installer, Defender, hash-manifest and artifact-upload steps. Verify the Installer, Portable and Release-SHA256 artifacts before marking Step 11.9 complete.

Do not start cleanup as part of this checkpoint.
