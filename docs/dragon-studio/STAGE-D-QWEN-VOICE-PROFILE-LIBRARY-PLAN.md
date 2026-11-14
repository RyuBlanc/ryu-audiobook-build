# Stage D — Qwen Voice Profile Library and Portable Transfer

**Stage:** D  
**Plan date:** 14 November 2026  
**Repository:** `RyuBlanc/ryu-audiobook-build`  
**Implementation branch:** `dragon-studio/stage-d-planning-2026-11-14`  
**Stage C accepted baseline:** `154bf0e0c1c1fe8334f68655d1629a3a9d1e3691`  
**Stage C package checkpoint:** Build Windows App #3420 / [run 43580180275](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43580180275)  
**Stage C main checkpoint:** [STAGE-C-MAIN-CHECKPOINT.md](STAGE-C-MAIN-CHECKPOINT.md)

## 1. Objective

Build a first-class **Qwen Voice Profile Library** that lets a user organize, inspect, version, back up, export, import and transfer complete Qwen voice-profile data between PCs without changing the voice's saved identity or losing profile-specific assets.

A profile transferred to another PC must retain its defining settings and associated audio assets. The destination app must explain whether the required Qwen model/runtime is compatible or needs to be installed. The user must never discover after import that the profile silently changed its voice, model pairing, language, prompt, seed or identity anchor.

The library is a profile/data portability feature. It is not a model-weight distribution system.

## 2. Existing baseline to preserve

The accepted Stage C source already has:

- `VoiceProfile` in `app/tts/voice_profile.py`, with provider, voice ID, model ID, backend preference, language, notes, authorization, Qwen mode, prompt, seed, reference text, sample path, VoiceDesign anchor path/text and Qwen profile ID.
- Saved profiles persisted in `voices.json` below `voices_root()`.
- Atomic save and legacy Qwen-profile migration behaviour.
- A stable `qwen_profile_id` used to keep saved Qwen VoiceDesign/Clone identity isolated.
- Generation signatures that include profile settings and SHA-256 digests of sample and anchor audio.
- Fresh-process saved CustomVoice, VoiceDesign and Clone reload coverage.
- Machine-wide Qwen model-size/backend preferences resolved when a provider is created. The compute backend is a destination-machine runtime choice, not a portable acoustic identity.

Do not replace this working persistence path, remove optional legacy fields, rename user profiles unnecessarily or change existing profile IDs as part of the library work.

## 3. Included profile types and library experience

The first release covers Qwen3-TTS profiles in all three existing modes:

1. **CustomVoice** — selected built-in Qwen speaker, language, prompt/instruction, seed and associated settings.
2. **VoiceDesign** — design prompt, selected language, seed, design identity, canonical anchor transcript and anchor audio.
3. **Voice Clone** — authorized reference identity, reference audio, reference transcript/text, mode, seed and associated settings.

The library should make it easy to recognize and find profiles by the existing user-facing groupings **Designed**, **Cloned**, **Preset** and **Cloud**, plus a Qwen model-based filter. Keep the filter meanings explicit and compatible with the existing Voice Library taxonomy; do not incorrectly classify a local Qwen profile as a cloud profile merely because of its display name.

At minimum, the user should be able to:
- View all saved Qwen profiles and their type, selected voice identity, language, required model pairing and compatibility state.
- Filter by profile type and model family/size; search by name and language.
- Inspect the full saved configuration and associated asset integrity.
- Export one profile or a selected set; import a profile bundle.
- See compatibility warnings before using an imported profile on the destination PC.
- Preserve existing saved profiles while adding transferred profiles.

Do not add a public cloud-sync service or account requirement in this stage.

## 4. Portable, versioned profile package

Design a documented, versioned archive format for profile bundles. The final file extension and manifest schema must be selected and documented before implementation; do not bake an unreviewed extension or schema into the runtime.

The package must contain:

- A versioned manifest with the profile schema version and bundle-format version.
- The complete serialized profile record, preserving all voice-defining settings and supported optional metadata.
- A stable profile identity and explicit Qwen mode.
- Explicit model identity/compatibility metadata: provider, model family, model role, exact model variant/size, expected Design/Base pairing where relevant, upstream model identifier/revision when known, and compatibility requirements.
- All profile-owned audio assets needed to recreate the profile, including the VoiceDesign identity anchor and/or authorized Clone reference audio.
- Relative asset paths inside the archive; no dependency on the exporting PC's absolute folders.
- SHA-256 for every included asset and a manifest-level integrity record.
- Provenance/export metadata that does not overwrite the profile's original creation or identity metadata.

Import must restore assets to application-managed, profile-owned storage and remap paths without changing their file bytes, audio content, profile identity or acoustic settings.

**Model weights are not included by default.** Qwen model weights and the isolated runtime may be large and can be installed separately. The bundle must state exactly which model variants are required, and the destination must report missing/incompatible models clearly. Do not silently substitute a different model size or CPU/GPU backend during import.

## 5. Versioning and compatibility

- Maintain separate bundle-format and profile-schema versions.
- Support forward validation and explicit migration from the current `voices.json` records.
- Every migration must preserve unknown/optional data where possible; an unsupported newer schema must fail safely rather than discard fields.
- Preserve the stable Qwen profile ID across export/import/backup/restore.
- Add a profile revision/history mechanism so a user can identify a changed revision and restore an earlier exported revision without silently mutating the current profile.
- Record model compatibility separately from the destination PC's actual compute backend.
- For VoiceDesign, retain the exact Design/Base pairing required for the saved identity; do not treat a Base model change as an interchangeable cosmetic setting.
- For Clone, preserve authorization metadata and source/reference identity; never create or imply authorization that was not present in the original profile.

## 6. Safe import, collision and recovery rules

- Import is additive by default. Existing profiles and their assets must not be overwritten.
- Detect duplicate profile IDs, same-name collisions, and a profile with a different ID but identical payload; explain the difference to the user.
- Require an explicit choice before replacing an existing profile. Preserve a recoverable backup of the replaced profile and its assets.
- Validate archive paths against traversal, absolute-path injection and symlink escape.
- Validate manifest schema, required fields, file sizes, asset presence, hashes and audio readability before installing anything.
- Stage the entire import in a temporary directory; commit it atomically only after all checks succeed.
- On any failure, roll back the staged files and leave the previous catalogue and assets untouched.
- Do not partially import a selection while reporting the complete bundle as successful.
- Do not delete an original imported bundle or the exporting PC's source assets.

## 7. Explicit exclusions

- No automatic cloud sync, user account, remote profile hosting or telemetry upload.
- No default packaging of Qwen model weights, CUDA/ROCm/XPU runtimes or Python environments.
- No destructive rewrite of the existing `voices.json` catalogue.
- No migration of unrelated Piper, Kokoro, Chatterbox, SAPI, Edge or ElevenLabs profiles into the Qwen bundle format in the first release.
- No changes to Qwen synthesis quality, accelerator selection or generation routing unless a portability regression proves a narrowly scoped fix is required.
- No reopening of completed Stage C1/C2 implementation or repeating Build #3420's completed hosted package gates without a new relevant source change or proven regression.

## 8. Acceptance requirements

### Data fidelity
- Export → import → export round-trip preserves every supported profile field and stable profile ID.
- Every profile-owned audio asset has identical SHA-256 before export and after import.
- Reference and anchor audio remain byte-identical; no resampling, transcoding, renaming that breaks references, or regenerated anchor is allowed during transfer.
- The imported profile reloads in a fresh process and produces the same provider/profile generation signature when run with the same compatible model/runtime configuration.

### Profile-mode coverage
- CustomVoice 0.6B and 1.7B records.
- VoiceDesign with exact Design 1.7B + Base 0.6B/1.7B pairing, language, prompt, seed and canonical anchor.
- Clone with authorized reference audio, reference text and profile identity.
- Legacy records missing newer optional fields.
- Multiple profiles, Unicode names/languages and same-name collision cases.

### Failure and security coverage
- Corrupt archive, corrupt manifest, missing asset, checksum mismatch, invalid audio, unsupported schema, unsafe path, oversized payload and duplicate identity.
- Missing or incompatible destination model.
- Import interrupted during staging or catalogue commit.
- Disk-full/permission failure while importing or replacing.
- Replacement rollback and recovery after application restart.
- No existing profile loss after any failed import.

### Application/package coverage
- Focused profile-library and archive-contract test suites.
- Legacy migration and fresh-process restart tests.
- Full regression suite.
- Exact-head Windows frozen application and installer/portable package.
- Packaged import/export round-trip with real profile assets.
- Preserve prior install/upgrade/uninstall, Defender and artifact/hash gates.

## 9. Implementation sequence

1. **D0 — Inventory and schema design:** inspect all current profile creation/save/load paths, asset ownership, path roots, model IDs, profile consumers and migrations. Publish field-by-field compatibility matrix and sample manifest. No runtime code changes until this design is internally consistent.
2. **D1 — Versioned profile domain model:** add explicit schema/revision/model-compatibility metadata with backwards-compatible readers and migration tests. Existing profile behaviour must remain unchanged.
3. **D2 — Asset ownership and portable serialization:** implement deterministic export with relative paths, content hashes, validation and round-trip tests.
4. **D3 — Transactional import and recovery:** implement preflight, compatibility report, additive import, collision choices, safe replacement/rollback and interrupted-operation recovery.
5. **D4 — Voice Library UI:** add the profile management experience, type/model filters, compatibility display, export/import and clear error/recovery notifications.
6. **D5 — Exact-head integration checkpoint:** focused tests, full regression, packaged import/export acceptance, Windows installer/portable artifacts and hashes.
7. **D6 — User acceptance:** transfer selected real profiles between two machines, verify identity/audio parity and inspect compatibility behaviour. Physical machine acceptance remains distinct from hosted CI.

Each sub-stage requires an exact branch/commit, focused result, cumulative regression result and relevant package evidence. Keep failed attempts and artifacts in history.

## 10. Stage C boundary

Stage C main engineering checkpoint is accepted at `154bf0e0c1c1fe8334f68655d1629a3a9d1e3691`, Build #3420 / run `43580180275` (1,596 tests, Windows package success).

The following physical target-PC checks remain a separate Stage C carry-forward lane and must not be hidden by Stage D:
- Actual Windows visual/interaction/flicker/freeze inspection.
- Real DPI/mixed-monitor/ultrawide/portrait inspection.
- Actual installed shortcut/taskbar icon and cover-art separation inspection.
- Actual installer wizard geometry at the target resolution/scaling.
- Device-specific GPU/backend and under-60-second Qwen preview evidence for each backend claimed as supported.

Stage D may proceed independently. A Stage D regression must not be used as a reason to reopen completed C1–C4 work unrelated to the regression.

## 11. Current status

**Planning charter committed; implementation not yet started.**

This branch is intentionally based on the accepted Stage C checkpoint SHA. The first implementation action is D0 inventory/schema design. No application source, model runtime, existing saved profile or user asset has been changed by creation of this plan.
