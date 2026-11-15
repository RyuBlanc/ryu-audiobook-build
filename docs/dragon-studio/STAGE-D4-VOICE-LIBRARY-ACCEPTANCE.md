# Stage D4 — Saved Qwen Voice Library UI Acceptance

**Stage:** D4 — production Voice Library interface and native actions  
**Repository:** `RyuBlanc/ryu-audiobook-build`  
**Implementation branch:** `dragon-studio/stage-d4-voice-library-interface-2026-11-15`  
**Accepted D3 baseline:** `946049393836d9f2628f1e1c6bd26312b0111197`  
**Latest exact-head D4 package evidence:** `fbed26a0beadd5ebe845173f8e2e059668248d8c`
**Latest hosted package:** Build Windows App #3457 / [run 43696836352](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43696836352)
**Status:** COMPLETE — D4 UI and native actions passed the exact-head Build #3457 Windows package on `fbed26a0beadd5ebe845173f8e2e059668248d8c`.

## 1. Delivered interface and integration

D4 adds the saved Qwen Voice Library to the production Premium V2 Voice Studio. It reads the existing `voices.json` profile catalogue and reuses the established saved-profile loader and project/series assignment safeguards; it does not create a parallel library or classify local Qwen profiles as Cloud.

The library experience includes:

- All, Designed, Cloned, Preset and Cloud categories with the existing taxonomy meanings.
- Qwen model/engine filtering independent of profile category, plus profile-name/language search.
- Saved-profile detail inspection for provider, voice ID, model ID, language, Qwen mode, prompt, notes, VoiceDesign anchor transcript, Clone reference text, seed, style preset, exaggeration, CFG weight, schema version and authorization.
- Destination model/runtime compatibility and the source profile's required model roles without silently substituting a model size or backend.
- Profile-owned asset integrity and revision-history inspection.
- Real native export, D3 compatibility preflight and transactional import commands; no prototype-only success result.

The inspection detail was tightened after source review: the backend exposed the anchor transcript but the UI did not show it separately, and saved style/exaggeration/CFG/schema values were not all visible. Commit `67eacdd02b7cc2884057c28d1cf1564b4a0495e4` added those fields and dedicated backend/UI regressions.

## 2. Native acceptance-path isolation

The Windows package test needs to call the same native export and import-preflight handlers without automating a desktop file-picker window. Commit `49e498938f2b5b28d6d655545f580776d764bf2b` adds an opt-in path resolver guarded by `RYU_VOICE_LIBRARY_ACCEPTANCE_ROOT`.

- Without that environment variable, normal user export/import still uses the native Save/Open file dialogs.
- In the packaged acceptance process, both supplied paths must resolve inside a unique temporary root.
- Symbolic links and path escapes are rejected; export refuses to overwrite an existing test bundle.
- The feature is an acceptance harness route, not a user-facing bypass or persistent application preference.

## 3. Test evidence and source history

| Build | Exact source SHA | Result | Evidence |
|---|---|---|---|
| #3445 | `784533b0075cdfe63468db769a10aac364c9f639` | Passed | Initial saved Voice Library UI and native bridge commands; package job skipped. |
| #3446 | `12f5d06d805ead6395f176b69c5a81ed6a6b3e36` | Passed | Profile revision inspection and safe import-skip behaviour; package job skipped. |
| #3447 | `2a1f9c54ee8a0548216ad20ca4c0922e10be15a0` | Passed | D3 rollback coverage restored and skipped-anchor case added; cumulative regression 1,665. |
| #3448 | `67eacdd02b7cc2884057c28d1cf1564b4a0495e4` | Passed | Full saved identity detail correction; D4 focused 21 tests, cumulative regression 1,667. |
| #3449 | `49e498938f2b5b28d6d655545f580776d764bf2b` | Passed | Opt-in path confinement for packaged export/preflight; D4 focused 22 tests, cumulative regression 1,668. |
| #3450 | `bf9a91bbba15533b52d2a01313b68d9135f4a921` | Passed | D3 21/21, D4 22/22, D5 contract 3/3, cumulative regression 1,671/1,671; source-test checkpoint. |
| #3457 | `fbed26a0beadd5ebe845173f8e2e059668248d8c` | **Passed — exact-head Windows package** | D3 21/21, D4 22/22, D5 contract 3/3, path security 10/10, full regression **1,681/1,681**; frozen-app D5 three-profile round-trip, installer/portable, Defender and install/launch/upgrade/uninstall passed. |

The #3448–#3450 commits were source/test checkpoints. Their Windows build jobs were skipped because the commits did not request an artifact checkpoint. No D4 installer/portable artifact is claimed from those runs.

## 4. Final D4 hosted package acceptance — COMPLETE

Build Windows App **#3457** / [run 43696836352](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43696836352), exact head `fbed26a0beadd5ebe845173f8e2e059668248d8c`, included the D4 production UI and native actions in the exact-head frozen Windows package. The D4 focused suite passed **22/22** and the integrated packaged Sound Design/Voice Library acceptance passed. The full regression was **1,681/1,681**; both workflow jobs passed.

This closes D4 hosted acceptance. Actual target-PC visual inspection, responsiveness/DPI/mixed-monitor checks and physical interaction checks remain part of the wider final hardware acceptance register; this hosted result does not claim those device-specific checks.

The D5 follow-on import-path confinement is tracked and accepted separately in [STAGE-D5-PACKAGED-VOICE-LIBRARY-ACCEPTANCE.md](STAGE-D5-PACKAGED-VOICE-LIBRARY-ACCEPTANCE.md).
