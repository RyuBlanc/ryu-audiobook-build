# Stage C4 — Qwen multilingual voice identity and expressive continuity

**Status:** Exact-head hosted regression and real CPU Qwen provider acceptance passed at candidate HEAD `6348eb0bd9f915d76f432ce1d899f023552a5e89`. The Windows artifact checkpoint is the remaining hosted C4 gate. Physical target-PC and accelerator acceptance remain open.

**Candidate branch:** dragon-studio/candidate-c4-voice-identity-continuity-2026-11-13  
**Source/test baseline:** Build Windows App #3405, SHA 45a0d5ee66363f3c258e1512e28347e457212027.  
**Tracking PR:** PR #35 remains open/draft on the long-lived post-release branch; this C4 candidate is a separate validation branch and is not a merge or release claim.

## Scope

1. Use native-language VoiceDesign identity anchors for all supported Qwen languages: English, Japanese, Korean, Chinese, German, French, Russian, Portuguese, Spanish and Italian.
2. Preserve the selected saved Qwen language; do not silently replace it based on mixed-language/native-script input.
3. Keep a single canonical acoustic identity anchor across neutral and emotional synthesis, profile save/reload and long-form Base identity locking.
4. Keep expression classification useful across supported languages, including whisper, fear/tension, anger, sadness, surprise, warmth, boredom, calm, curiosity, seriousness and reflection.
5. Invalidate resumable Qwen Design chunks when the expression pipeline changes; do not invalidate unrelated CustomVoice chunks.
6. Validate actual saved-profile audio and the CastAwareProvider/GenerationManager character-to-M4B route. Source contracts and mocked providers are not substitutes for real inference.

## Failed runs and confirmed causes

| Build | Result | Confirmed issue / correction |
|---|---|---|
| #3390 / [run 43425907453](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43425907453) | Failed | A legacy regression assertion expected ANCHOR_TEXTS; the worker uses one canonical neutral anchor. Correct the contract, not the runtime design. |
| #3391–#3392 / [run 43426006824](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43426006824), [run 43426042631](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43426042631) | Failed | Continued stale source-contract expectations in the same early localized-anchor work; preserve as failures. |
| #3394 / [run 43428125148](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43428125148) | Failed | Eight multilingual emotion-classification cases were missing language-specific forms. #3395 added the cues and preserved selected language. |
| #3397 / [run 43450340023](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43450340023) | Failed | Test required old v8-emotion-range-anchor; worker was on v9-language-matched-anchor-direction. #3398 updated the cache-key/version assertion to the actual versioned localized anchor. |
| #3403 / [run 43461070567](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43461070567) | Failed | Portuguese train noun trem was misclassified as trembling/fear due broad prefix matching. #3404 narrowed inflections; #3405 added tremor/tremedeira nouns without matching train. |

No failed run is reclassified as green. #3404's Provider Runtime Smoke #446 was cancelled, and #3405's Provider Runtime Smoke #447 was skipped because the commit lacked the explicit acceptance tag.

## Real CPU provider evidence already completed

### Provider Runtime Smoke #441

- Run: [43452010644](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43452010644), source SHA e7be473eaf0bfd6d95762e712cee22844118c911.
- Actual 0.6B and 1.7B CustomVoice saved-profile reload/audio passed; authorized Base Clone passed; saved VoiceDesign preview/reload passed with identical anchor SHA.
- Japanese saved VoiceDesign profile was synthesized in neutral and angry delivery after reload; the Design 1.7B + Base 0.6B path was selected, actual device was CPU, and the canonical anchor SHA remained unchanged.
- Two-chapter Qwen character M4B passed with two Qwen dialogue calls, four chapter markers and FFmpeg decode.
- The 30-second saved-profile VoiceDesign preview took **229.539 seconds on CPU**. This is functional identity evidence only; the under-60-second performance goal was not met.
- Artifacts: 14051558617 VoiceDesign; 14053047675 CustomVoice; 14054567437 Clone/Design/M4B.

### Provider Runtime Smoke #444

- Run: [43460081727](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43460081727), source SHA 96f40c29f2689484c171e183ffe08b1a3ba72bd3.
- Real saved-profile neutral and angry VoiceDesign audio was generated for English, Korean, Chinese, German, French, Russian, Portuguese, Spanish and Italian. All nine profiles reloaded, and all nine retained the exact same canonical anchor SHA after reload.
- Real Base Clone and two-chapter Qwen character M4B passed (qwen_dialogue_calls=2, four chapter markers, FFmpeg decode true).
- The 30-second VoiceDesign preview took **241.443 seconds on CPU**. No GPU result is implied.
- Artifacts: 14057106365 VoiceDesign; 14057117830 CustomVoice; 14060436461 Clone/Design/M4B.

These #441 and #444 runs predate the latest Portuguese classifier correction. Exact-head real-provider acceptance was subsequently completed by Provider Runtime Smoke #448 below.

### Provider Runtime Smoke #448 — exact-head real CPU acceptance

- Run: [43499302368](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43499302368), exact candidate SHA `6348eb0bd9f915d76f432ce1d899f023552a5e89`.
- All five relevant Qwen jobs passed: expression protocol, real 1.7B VoiceDesign preview, accelerator discovery/software tests, 0.6B + 1.7B CustomVoice, and Base Clone + saved VoiceDesign + character-to-M4B. Unrelated Chatterbox and Kokoro jobs were skipped.
- Actual 0.6B and 1.7B CustomVoice audio passed, with saved-profile reload, decoded audio and actual backend/device `cpu`; logged audio durations were 7.600s and 6.400s.
- Authorized Qwen Base Clone passed using the 0.6B Base model, with profile reload and a 2.960s reference-derived output.
- Japanese saved VoiceDesign passed after profile reload with Design 1.7B + Base 0.6B, neutral 2.320s and angry 1.840s output, unchanged canonical anchor SHA and anchor version `v9-language-matched-anchor-direction`.
- Nine more saved profiles passed neutral/emotional real synthesis and reload: English, Korean, Chinese, German, French, Russian, Portuguese, Spanish and Italian. The smoke reports all nine profiles reloaded with unchanged anchor SHA.
- A separate saved VoiceDesign production path generated a 30.000s preview in 187.318s on CPU, with profile reload and identity lock.
- The standalone 1.7B VoiceDesign smoke generated 30.000s in 336.607s warmed-preview elapsed; it also recorded 55.298s cold-start-plus-warmup. Both preview paths are CPU-only and exceed the 60-second target. The log explicitly reports `QWEN_VS01_CPU_60S_TARGET=NOT_MET_ON_HOSTED_CPU`.
- Character-to-M4B passed: two chapters, two Qwen dialogue calls, four chapter markers and FFmpeg decode.
- Artifacts: VoiceDesign ID `14073723116` (1,593,194 bytes); CustomVoice ID `14073609412` (480,524 bytes); Clone/Design/M4B ID `14076896484` (4,950,282 bytes). All were successfully uploaded and were unexpired when checked.

This establishes exact-head CPU functional/identity continuity. It does not establish CUDA/ROCm/XPU inference or performance acceptance.

## Latest candidate test result

Build Windows App #3405 / [run 43462518581](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43462518581), exact SHA 45a0d5ee66363f3c258e1512e28347e457212027:

- Stage B: **16/16**.
- Stage 6: **48/48**.
- Stage C1: **10/10**.
- Stage C2: **9/9**.
- Stage C3: **8/8**.
- Stage C4 focused multilingual identity/expression suite: passed.
- Full regression: **1,595/1,595**.
- Windows packaging was skipped by design; this was an intermediate fix, not an artifact checkpoint.

## Exact-head next gates

1. Run one exact-head Windows artifact checkpoint from candidate SHA `6348eb0bd9f915d76f432ce1d899f023552a5e89` using [artifact-checkpoint]. Require the complete focused and full regression suite before packaging. Preserve every existing frozen-app, bundled-assets, M4B, Sound Design, installer, install/launch/upgrade/uninstall, user-data, transparency/hash, package-size, Defender and artifact-upload gate unchanged.
2. After the package succeeds, promote this accepted candidate to the long-lived PR #35 tracking branch by a verified fast-forward only. Keep PR #35 in draft until its accumulated review and applicable physical acceptance are addressed; do not force-push or rewrite the failed-run history.
3. Keep installed target-PC profile audition, restart/repair and representative long-book production acceptance open. Keep C3 NVIDIA CUDA / AMD ROCm / Intel XPU acceptance open until real self-hosted inference proves actual backend and timing.

## Non-negotiable acceptance rules

- Do not replace real model synthesis with a mock, synthetic WAV, protocol handshake or Piper output.
- Do not accept an anchor ID alone: verify a nonempty canonical anchor file and identical SHA after profile reload and emotional synthesis.
- Do not silently change a saved profile's language, Design/Base model pair, selected voice identity or backend.
- Do not claim GPU speed from CPU inference; keep CPU timing and GPU acceptance separate.
- Do not use the two-chapter M4B fixture as proof of representative full-novel completion.
- Preserve failed runs, exact SHAs, and all focused/full/package gates; do not remove or weaken tests to obtain a green result.


## Exact-head validation result — 14 November 2026

- Candidate branch HEAD: `6348eb0bd9f915d76f432ce1d899f023552a5e89`.
- The application source tree is unchanged from Build Windows App #3405 (source baseline `45a0d5ee66363f3c258e1512e28347e457212027`). The five later commits contain C4 acceptance documentation, ledger updates and the provider-workflow path-filter correction; they do not change application source.
- Build Windows App #3410 / [run 43499302199](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43499302199) passed on this exact head: Stage B 16/16, Stage 6 48/48, C1 10/10, C2 9/9, C3 8/8, C4 37/37 and full regression 1,595/1,595. The Windows build job was skipped because this was not yet an artifact-checkpoint push.
- Provider Runtime Smoke #448 / [run 43499302368](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43499302368) completed successfully on the same exact SHA and uploaded the three real-audio evidence archives listed above.
- Exact-head real CPU provider acceptance is passed. Windows artifact/package acceptance remains pending. CPU timing explicitly misses the under-60-second goal; no GPU result is implied.
- The next commit carries [artifact-checkpoint] only. It requests the Windows package after the full regression suite; it does not repeat the expensive real-provider smoke chain. Do not infer package success from the test job alone.
