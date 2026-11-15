# Stage D5 — Packaged Qwen Voice Library Import/Export Acceptance

**Stage:** D5 — exact-head frozen-app integration and artifact acceptance  
**Repository:** `RyuBlanc/ryu-audiobook-build`  
**Implementation history:** the first shared-harness round-trip was accepted on the D4 branch; final import-path hardening and exact-head package acceptance were completed on `dragon-studio/stage-d5-voice-library-packaged-acceptance-2026-11-15`, then carried forward to the D6 branch.
**Final D5 exact-head SHA:** `fbed26a0beadd5ebe845173f8e2e059668248d8c`
**Final D5 package:** Build Windows App #3457 / [run 43696836352](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43696836352)
**Status:** COMPLETE — packaged D5 three-profile round-trip, fresh-process reload and final import-path confinement passed on the exact-head #3457 Windows package.

## 1. What the packaged acceptance exercises

The existing `tests/packaged_sound_ui_acceptance.py` + `tests/stage2_packaged_sound_ui_acceptance.js` harness launches the actual frozen Windows executable and attaches to its real Qt WebChannel/native bridge. D5 adds an isolated profile fixture set and drives the production native commands:

1. Seed one CustomVoice, one VoiceDesign with an explicit identity-anchor WAV, and one authorized Clone with its reference WAV. Each profile has a unique test ID/name and a saved model pairing, language, prompt, seed and configuration.
2. Back up the existing `Voices/voices.json` bytes and add only these three fixtures for the acceptance process.
3. Call `voice.list` and `voice.library.inspect` through the real frozen app; verify profile identity/settings and exact SHA-256 for the VoiceDesign anchor and Clone reference WAV.
4. Call `voice.bundle.export` with the selected three profiles. Verify the export result and independently inspect the completed `.ryuvoice` ZIP for manifest integrity and the exact set of stable profile IDs. Verify that model weights and runtime files are not included.
5. Delete only the three uniquely identified test profiles, call `voice.bundle.choose_import` to run D3 compatibility/collision preflight, and require each ID to be classified as a new profile.
6. Call `voice.bundle.import` with an explicit import action for each new ID. Verify the original IDs, type, name, language, model pairing, prompt, notes, seed, anchor/reference text, style, exaggeration, CFG weight and authorization.
7. Verify the imported anchor/reference assets remain byte-identical by comparing their SHA-256 values with the source fixtures.
8. The runner launches a second, fresh frozen-app process and repeats profile reload, identity/configuration and asset-hash checks.

The fixture catalogue is restored byte-for-byte (or removed if it did not exist before the test). Only the uniquely named test profile's `Qwen Profile Assets` and `Qwen Profile Revisions` folders are removed. Original source test WAVs and the bundle live below the acceptance temporary directory and are removed with that directory.

## 2. File-picker isolation and production behaviour

The packaged runner sets `RYU_VOICE_LIBRARY_ACCEPTANCE_ROOT` to a unique temporary directory. The host accepts test export/open paths only when they resolve within that directory; symlinks and path traversal are rejected. In a normal application session the variable is absent, so native Save/Open dialogs remain the production behaviour.

## 3. Focused and cumulative hosted evidence

Build Windows App #3450 / [run 43690410288](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43690410288), exact commit `bf9a91bbba15533b52d2a01313b68d9135f4a921`:

| Gate | Result |
|---|---:|
| D3 transactional import/recovery | 21/21 |
| D4 Voice Library taxonomy, compatibility and UI | 22/22 |
| D5 packaged Voice Library acceptance contract | 3/3 |
| Full regression | **1,671/1,671** |
| Tests workflow | Passed |
| Windows build job | Skipped — this was a test-only commit without `[artifact-checkpoint]` |

The 3/3 D5 tests verify that the frozen-app fixture is isolated/restored, the browser acceptance invokes the real export/preflight/import/fresh-process commands, and the native path override is confined to the opt-in temporary root while production file dialogs remain intact.

## 4. First packaged round-trip checkpoint — ACCEPTED ON #3452

Build Windows App **#3452** / [run 43691113837](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43691113837), exact SHA **a2f7efb2f4bc4a58cc6a2fe56215e45e4d9c1c3e**:

- D3 focused import/recovery: **21/21**.
- D4 Voice Library taxonomy/compatibility/UI: **22/22**.
- D5 packaged acceptance contract: **3/3**.
- Full regression: **1,671/1,671**.
- Frozen Windows package job: **passed**, including the shared packaged Sound Design and D5 Voice Library acceptance.
- The frozen-app log recorded CustomVoice, VoiceDesign and Clone profile IDs; export integrity; 2 byte-verified audio assets; successful transactional import; and successful reload in a second frozen-app process.
- Installer, portable application, SHA-256 manifest, Defender scan, install/launch/upgrade/uninstall and the existing multi-chapter M4B evidence were uploaded successfully.

This accepts the hosted D5 data round-trip. It does not replace D6 physical two-PC transfer/audition acceptance.

## 5. Follow-on import-path hardening — ACCEPTED ON #3457

Source review found that export and import preflight used the opt-in confined acceptance-path resolver, but the final voice.bundle.import commit handler passed bundle_path directly to the transactional importer. The D5 continuation centralizes path resolution in app/ui/voice_library_acceptance.py, applies it to the final commit operation as well, and adds 10 functional traversal/symlink/junction/path-type tests. The accepted D4 packaged acceptance files remain the base; no duplicate packaged runner is introduced.

The final hardening checkpoint passed the focused D3/D4/D5 contracts, all 10 path-security tests, the full regression suite, and the exact-head frozen Windows package on #3457.

## 5. D6 is separate

D5 verifies the application-managed data path and restart behaviour on one hosted Windows package. It does not prove two physical PCs have completed a real transfer or that an actual compatible Qwen model reproduces the voice acoustically. D6 remains a real user-device transfer/audition acceptance item and is deferred until the engineering stages are complete.


## 6. Final D5 exact-head Windows artifact acceptance — COMPLETE

Build Windows App **#3457** / [run 43696836352](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43696836352), exact SHA **`fbed26a0beadd5ebe845173f8e2e059668248d8c`**:

| Gate | Result |
|---|---:|
| D3 transactional import/recovery | 21/21 |
| D4 Voice Library UI/library | 22/22 |
| D5 packaged acceptance contract | 3/3 |
| D5 path-security regression | 10/10 |
| Full regression | **1,681/1,681** |
| `tests` workflow job | Passed |
| `build` workflow job | Passed |

The frozen-app log recorded:

- Three stable profile IDs: `stage-d5-custom-084469617e00`, `stage-d5-design-084469617e00` and `stage-d5-clone-084469617e00`.
- Profile types Preset/CustomVoice, Designed/VoiceDesign and Cloned/Clone.
- Successful export, preflight and transactional import with the same three IDs.
- Bundle SHA-256: `9d69880a612182b2d0975c89832932097bdc97248d67b4aa9f5b5de3340a5c2e`.
- Two byte-verified audio assets: `3def3ca0f1b5c8848457c6aac08486c5e143c0f8f9f90773e840f7d267b5d478` and `3c645d884345694df222d7ef7b0144b71e7ba05d306b8bd2eba343f1a5a6a6d2`.
- Fresh frozen-app process reload of all three profiles and both verified assets.

The 10 path-security tests cover disabled acceptance mode, missing path rejection, relative and absolute in-root destinations, relative traversal, absolute out-of-root paths, import file existence/type, direct symlink, symlinked parent and invalid acceptance root. The final import-commit handler applies the same confined path resolution as export and preflight; outside the opt-in test environment the normal native file dialogs remain unchanged.

### Build #3457 artifacts

| Artifact | ID | Size (bytes) | GitHub artifact ZIP digest |
|---|---:|---:|---|
| Installer | `14155946288` | 847,513,902 | `sha256:3d3b9eb55fbfcbb92971b15f5674c8c9081c25c6e08373c810b09aed95378b83` |
| Portable | `14155203714` | 1,191,009,995 | `sha256:7a31d8d10bed4c4fb2b297777399e467d1acdeb6417fc29c4b85ba2cb9facc6e` |
| Release SHA-256 manifest | `14156115594` | 3,049 | `sha256:5723db8431ec0ee6c8345310f51432519450fd8b1e54c6e6da95d372f2475233` |
| Real multi-chapter M4B | `14155232491` | 9,049,610 | `sha256:38fa2ee2d98886bc75a21638372e30573117fdc0be54b2747608f4d07461ac12` |
| Stage 7 Piper benchmark | `14154984256` | 801 | `sha256:0e280b8f523672deac9506a9631624b7b71688f306e6c3e678ea933811cd8199` |

The values above are GitHub Actions artifact ZIP digests and sizes, not the hashes of the installer/portable files inside those archives. The application/installer file hashes are in the release SHA-256 manifest. GitHub reported expiry on **15 December 2026**.

D5 closes hosted one-machine packaged import/export and import-path security acceptance. It does **not** replace D6 physical two-PC transfer/audition acceptance.
