# Stage D3 — Transactional Qwen Profile Import and Recovery Acceptance

**Stage:** D3 — transactional import, compatibility preflight, collision handling and recovery  
**Repository:** `RyuBlanc/ryu-audiobook-build`  
**Implementation branch:** `dragon-studio/stage-d3-transactional-qwen-profile-import-2026-11-15`  
**Accepted D2 baseline:** `06895803d859e748dc8c7292c6a3bfd895af9304` (Build #3436 and #3437)  
**Current hosted-test head:** `bdebf78ef3680b92010c9585830ae85ed1e614bb` (Build #3442)  
**Status:** implementation and hosted test gates passed; exact-head Windows artifact checkpoint pending

## 1. Deliverable

D3 adds `app/tts/qwen_profile_import.py`, a transactional importer for the existing version-1 `.ryuvoice` bundle format.

Public entry points:
- `plan_qwen_profiles_import(bundle_path)`: verify the bundle and provide destination compatibility/collision preflight.
- `import_qwen_profiles_bundle(bundle_path, resolutions=..., allow_missing_voicedesign_anchor=...)`: stage and import all selected profiles in one recoverable transaction.
- `recover_interrupted_qwen_profile_imports()`: roll back incomplete transactions.
- `voice_profile_catalogue_lock()`: serialize catalogue reads/writes across processes.

The existing `voices.json` persistence path remains authoritative. D3 does not introduce a parallel catalogue, modify profile synthesis, install model weights, or change the destination machine's Qwen model/backend preferences.

## 2. Imported data and destination storage

- Qwen CustomVoice, VoiceDesign and Clone records preserve their stable `qwen_profile_id`, mode, selected identity, model ID, language, prompt, seed, reference transcript, authorization value and supported optional/unknown fields.
- Clone conditioning audio and original sidecars are copied byte-for-byte into profile-owned storage. No resampling, transcoding or content rewrite is performed.
- Explicit VoiceDesign anchors are copied byte-for-byte into profile-owned storage.
- Worker-derived VoiceDesign neutral anchors are restored at the same deterministic cache path used by the Qwen worker; the expression-bank version is checked before the anchor is installed.
- Machine-local `sample_path` and `qwen_anchor_path` values are remapped to destination paths. The source catalogue, source files and original `.ryuvoice` bundle are not modified.
- Profile assets are stored below `Voices/Qwen Profile Assets/<profile-id>/<revision-id>/`. Revision snapshots are stored below `Voices/Qwen Profile Revisions/<profile-id>/`. Import provenance and destination compatibility are recorded separately from the voice-defining profile record.

## 3. Compatibility preflight

The preflight verifies the complete archive through the D2 inspector before any catalogue mutation. It reports:
- Required Qwen model roles and installed model variants on the destination.
- Whether exact source model pairing is present, separately from any other allowed variant.
- Destination Qwen runtime readiness and the destination backend preference.
- Missing VoiceDesign identity anchor state.
- Duplicate profile identity, revision mismatch, semantic duplicate and display-name collision.

A model/runtime is not downloaded during import. A different model size, Design/Base pairing or backend is never silently selected. The source machine's compute backend is not imposed on the destination machine. Clone authorization metadata is preserved exactly; import does not invent authorization.

## 4. Collision and revision decisions

| Condition | Default behaviour | Explicit choices |
|---|---|---|
| Same profile ID and same verified revision | Skip idempotently | Skip |
| Same profile ID, different revision | Keep incoming revision in revision history; leave current profile active | Keep both, replace after verified backup, or skip |
| Different ID, same semantic profile payload | Require a decision | Keep both or skip; provide a new display name when names collide |
| Same name, different profile ID/payload | Require a decision | Rename/keep both with a distinct new name, or skip |
| New profile | Add without replacing any saved profile | Import or skip |

Before replacement, D3 exports and re-inspects a backup of the current profile and its assets. Replacement is refused if the current revision or required asset hashes cannot be verified. Existing asset bytes are never overwritten when a destination path already contains different content.

## 5. Transaction and recovery behaviour

1. Recover any prior incomplete import while holding the cross-process catalogue lock.
2. Inspect the bundle, read all profile documents, calculate collision decisions and compatibility before writing.
3. Stage every manifest-listed payload in a private transaction directory; recheck SHA-256 while streaming each member.
4. Copy profile-owned assets with exclusive temporary files and verify their hashes before atomic placement.
5. Persist revision/provenance metadata and journal every newly created path.
6. Atomically replace `voices.json` only after all selected records/assets are ready.
7. Mark the transaction complete and remove its journal directory.

If staging, asset installation, backup, catalogue replacement or process execution fails before the complete marker, rollback restores the original catalogue and removes every transaction-created file. The next saved-profile read invokes recovery before loading the catalogue. The original imported bundle and source-PC files are not deleted.

## 6. Focused acceptance coverage

The D3 focused suite is `tests.test_qwen_profile_import`.

Build #3441 passed the initial 17 tests. Build #3442 expanded the suite to **20/20**, adding explicit fresh-process, disk-full and permission-denied scenarios. The 20 cases cover:
- CustomVoice record fidelity and unknown extension preservation.
- Clone conditioning and source sidecar byte parity.
- Explicit and worker-derived VoiceDesign anchor restoration.
- Missing anchor acknowledgement without synthesizing a replacement.
- Missing destination model/runtime reporting without backend preference mutation.
- Exact same-ID idempotency and same-ID revision history/verified replacement backup.
- Semantic duplicate and display-name collision decisions.
- Multi-profile rollback after an asset-install failure.
- Rollback after an injected failure following catalogue replacement.
- Import recovery before a fresh catalogue read.
- Fresh Python-process reload of imported CustomVoice, Clone and VoiceDesign identities/asset paths.
- Corrupt bundle rejection before catalogue mutation.
- Existing different asset bytes are not overwritten.
- Simulated disk-full during asset staging.
- Simulated permission-denied catalogue replacement with old catalogue and assets restored.

## 7. Exact-head hosted history and failures

| Build | Commit | Result | Diagnosis / evidence |
|---|---|---|---|
| #3438 | `2c14f74` | Failed | Catalogue recovery hook landed before `qwen_profile_import.py`; the existing C2 fresh-process restart test raised `ModuleNotFoundError`. The next commit added the module and the dedicated D3 gate; this run remains a historical failure. |
| #3439 | `f8f68ee` | Failed | C2 and all existing Stage B/C/D gates passed. The new D3 gate had 6 errors caused by calling `fsync` on the read-only handle used for the pre-import catalogue backup. |
| #3440 | `e598c0c` | Failed | The first descriptor correction changed the import-metadata temporary writer but did not change the read-only catalogue-backup descriptor; the same 6 D3 errors persisted. |
| #3441 | `aac10a5` | Passed | Catalogue backup is flushed using a non-truncating writable `r+b` handle. D3 focused tests 17/17; full regression 1,642/1,642. |
| #3442 | `bdebf78` | Passed | Added fresh-process reload, disk-full staging and permission-denied catalogue rollback tests. D3 focused tests 20/20; full regression 1,645/1,645. Windows package job was skipped because this was a test checkpoint. |

None of the failed attempts is relabelled or removed. Build #3441 is the first clean D3 test checkpoint; #3442 is the current expanded hosted test checkpoint.

## 8. Remaining D3 exit gate

D3 is **not yet declared fully accepted**. The next `[artifact-checkpoint]` push must pass on one exact head:
- Focused D1/D2 and D3 suites.
- Full regression suite.
- Frozen Windows application and packaged Qwen helper validation.
- Real bundled-Piper M4B and packaged Sound Design gates.
- Core and HTML installer, installer startup, install/launch/upgrade/uninstall.
- Branding/hash and package-size checks.
- Microsoft Defender and all expected artifact uploads.

D3 does not claim that the Voice Library UI exists, that packaged import/export round-trip is complete, or that a two-PC profile transfer has been performed. Those remain D4, D5 and D6.
