# Stage D6 — Physical Two-PC Voice Profile Transfer and Audition Acceptance

**Stage:** D6 — real-device transfer, destination compatibility and voice audition  
**Repository:** `RyuBlanc/ryu-audiobook-build`  
**Acceptance branch:** `dragon-studio/stage-d6-two-pc-voice-profile-transfer-2026-11-15`  
**Accepted hosted baseline:** `fbed26a0beadd5ebe845173f8e2e059668248d8c` (Build Windows App #3457; exact-SHA package revalidated by Build #3458 / [run 43699897254](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43699897254))  
**Status:** DEFERRED TO STAGE F — NOT PASSED. Per the user's sequencing decision, execute this physical two-PC check only after engineering stages A–E have completed. No physical transfer or audition is represented by hosted CI.

## 1. Purpose and boundary

D6 verifies that real saved Qwen profiles can move from a source Windows PC (PC-A) to a separate physical destination Windows PC (PC-B), retain profile identity and owned audio bytes, explain destination model/runtime compatibility accurately, reload after restart, and remain recognizably the same voice when auditioned with a compatible setup.

D5 already proves the packaged one-machine export → preflight → transactional import → fresh-process reload path using isolated test fixtures. D6 is a separate physical acceptance gate. A hosted runner, another process on PC-A, a mocked bridge, or a simulated model inventory cannot substitute for PC-B.

D6 does not require or authorize cloud sync, upload of user recordings, model-weight bundling, replacement of existing user profiles, or uninstalling working models to manufacture a missing-model state.

## 2. Required physical setup

- **PC-A (source):** a normal user installation containing real saved CustomVoice, VoiceDesign and authorized Clone profiles selected by the user.
- **PC-B (destination):** a separate physical Windows PC with the accepted Ryu Audiobook build installed. Record whether the required Qwen runtime/model variants are already present; do not install or remove components solely to make the test look green.
- A safe transfer medium such as a USB drive or a user-controlled local file share. The original bundle remains on PC-A after transfer.
- A compatible and explicitly recorded model/runtime configuration for the audition comparison. Record the actual backend resolved on each machine; do not assume the saved source backend is portable.
- Enough free destination disk space for the selected profile assets and revisions. Do not start an import when storage is insufficient.

Use non-sensitive machine labels (PC-A and PC-B). Do not put Windows account names, serial numbers, private directory names or personal voice-owner information in the evidence report.

## 3. Profile selection matrix

Select real profiles that are safe and authorized to transfer. Prefer one profile from each existing Qwen mode; where the source catalogue has appropriate entries, include both CustomVoice size variants.

| Required case | What to record |
|---|---|
| CustomVoice | Stable profile ID, display name, speaker/voice ID, language, prompt/instruction, seed, saved model kind (include 0.6B and 1.7B when available) |
| VoiceDesign | Stable profile ID, language, full design prompt, seed, anchor transcript, exact VoiceDesign model role and long-form Base pairing, anchor asset presence/hash |
| Clone | Stable profile ID, language, speaker/voice identity, reference transcript, authorization value, active normalized reference asset hash and original sidecar hash when present |
| Multi-profile bundle | Exact selected ID set, profile count, bundle format/schema version and bundle SHA-256 |
| Optional edge cases | Unicode profile/language names, same-name/different-ID profile, and a legacy profile with optional fields absent |

Do not create or alter personal voice profiles just to satisfy the matrix. When a category or model-size variant does not exist on PC-A, record it as unavailable and do not mark the missing case as passed.

## 4. PC-A source snapshot and export

1. Confirm the app version/build and record the source environment: Windows version, CPU/GPU model, installed RAM/VRAM, Qwen runtime version, Python/Torch/Torchaudio/Qwen TTS versions, installed model kinds/revisions and the backend actually selected for each audition.
2. In Voice Studio → Voice Library, inspect each selected profile. Record all displayed identity/compatibility fields, its stable profile ID and revision. Confirm the source reports the expected mode and model requirements.
3. Export the selected profiles to a new `.ryuvoice` file using the native Voice Library export action. Do not overwrite an existing bundle.
4. Retain the original bundle and calculate its SHA-256. Verify the exporter reports the same profile count and that the export does not include Qwen model weights or runtime files.
5. Confirm the source catalogue and profile assets remain unchanged after export. At minimum, reopen the library and confirm the selected profiles and IDs still exist; record any visible asset-integrity warnings.

PowerShell bundle hash:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "C:\path\to\selected-profiles.ryuvoice" |
  Format-List Algorithm, Hash, Path
```

## 5. Transfer integrity and PC-B preflight

1. Copy the `.ryuvoice` file to PC-B using the chosen transfer medium. Do not rename or modify the file during the first transfer.
2. Calculate SHA-256 on PC-B and require an exact match with the PC-A hash before opening/importing the bundle.
3. Record PC-B's installed Qwen runtime/model inventory before import. Open Voice Library → Import and inspect the compatibility/collision preflight. Do not commit an import until the preflight has been reviewed.
4. Confirm the preflight identifies the exact required CustomVoice, VoiceDesign and Base model roles/variants; reports missing or incompatible models explicitly; and does not claim readiness by silently substituting a different size, Design/Base pairing or backend.
5. Where PC-B naturally lacks a required model, record that negative compatibility result. Do not remove an installed model from a working PC to create this condition. Profile data may be transferred only through the supported UI when the preflight permits it; model installation is a separate destination operation.
6. Confirm same-ID/same-revision and same-name/different-ID collision cases are clearly classified. Do not select Replace for a real user profile during this acceptance unless a verified backup has been made and the user explicitly approves it.

## 6. PC-B import, restart and data fidelity

1. Import the selected bundle additively, choosing Import for genuinely new profiles and Skip for any collision that is not part of an explicitly approved replacement test.
2. Require imported profile IDs to match PC-A exactly. No selected profile may be silently skipped, renamed in its identity record, regenerated or assigned a new Qwen profile ID.
3. Inspect each imported profile in Voice Library and compare all voice-defining fields with the PC-A snapshot: mode, speaker/voice ID, language, prompt/instruction, seed, reference/anchor transcript, exact model-role pairing and authorization metadata. Destination-only paths and backend resolution may differ as documented; they must not rewrite the portable identity.
4. Verify SHA-256 equality for every profile-owned audio asset: VoiceDesign anchor, Clone active normalized reference audio and any original source sidecar included in the bundle. Compare hashes, not filenames or durations alone.
5. Close and relaunch the installed app on PC-B. Reopen Voice Library and confirm the same IDs, settings, compatibility report and byte-verified assets reload in a fresh process.
6. Confirm existing PC-B profiles were not overwritten, deleted or modified by the additive import.

For any file path exposed by the app's asset inspection, the hash can be checked with:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "C:\path\to\imported-profile-asset.wav" |
  Format-List Algorithm, Hash, Path
```

Do not assume every PC uses the default Voices root; hash the actual destination asset path reported by the application.

## 7. Controlled audition and identity comparison

Perform the audition only after the destination reports the required compatible model/runtime as ready. For each mode:

- Use the same short neutral text, language, profile settings and seed on both PCs. Record the exact text, model kind/upstream model revision, runtime versions and actual resolved backend.
- Keep VoiceDesign's exact Design model and long-form Base pairing identical. For Clone, use the same authorized profile and reference transcript/audio. For CustomVoice, use the same speaker ID and exact model size.
- Generate a short preview on PC-A and PC-B using the production Voice Studio path. Do not route through a different provider or silently fall back to CPU/another model.
- Listen to both outputs at matched playback volume. Record whether the intended voice identity, pronunciation, language, timbre and delivery remain consistent. Record material differences rather than declaring parity from matching profile names alone.
- Preserve the two preview files locally for the acceptance record if the user is comfortable retaining them. They need not be uploaded to GitHub.

Different GPU backends may produce some waveform variation. D6 is identity/audition parity, not a claim that generated PCM output is byte-identical. The profile-owned input assets are the byte-identical objects; generated audio is reviewed under a recorded, matching configuration.

## 8. Acceptance gates

D6 passes only when all applicable gates have evidence:

| Gate | Pass condition |
|---|---|
| Source preservation | PC-A still has the original profiles and assets after export/transfer |
| Bundle transfer | PC-A and PC-B bundle SHA-256 values match |
| Profile identity | All selected stable IDs and voice-defining fields match after PC-B import and restart |
| Asset integrity | Every included required profile asset SHA-256 matches the source |
| Compatibility | PC-B accurately reports exact model-role readiness or missing/incompatible models before audition; no silent substitution |
| Additive import | Existing destination profiles remain intact; selected new profiles are not silently skipped |
| Fresh-process persistence | Imported identities, settings and asset hashes remain valid after a real app close/relaunch |
| Audition | CustomVoice, VoiceDesign and Clone are auditioned on both PCs with documented model/runtime/backend settings and judged identity-consistent |
| Scope honesty | Any unavailable profile type, model variant, missing-model test or audition is explicitly marked NOT RUN, not passed |

A material failure in identity fields, profile IDs, required asset hashes, collision safety or silent model/backend substitution fails the affected gate and must be corrected before acceptance. Do not weaken the criteria to obtain a pass.

## 9. Evidence worksheet

Fill this table using evidence from the two physical PCs. Keep the original `.ryuvoice` bundle and local test logs.

| Evidence | PC-A (source) | PC-B (destination) |
|---|---|---|
| App version/build/SHA | NOT RUN | NOT RUN |
| Windows version | NOT RUN | NOT RUN |
| CPU/GPU/RAM/VRAM | NOT RUN | NOT RUN |
| Qwen runtime/Python/Torch/Torchaudio/Qwen TTS | NOT RUN | NOT RUN |
| Installed Qwen model kinds/revisions | NOT RUN | NOT RUN |
| Resolved backend for each preview | NOT RUN | NOT RUN |
| Bundle SHA-256 | NOT RUN | NOT RUN |
| Selected profile IDs | NOT RUN | NOT RUN |
| Imported profile IDs after restart | N/A | NOT RUN |
| Required profile asset hashes | NOT RUN | NOT RUN |
| Compatibility/missing-model result | N/A | NOT RUN |
| Additive import/collision result | N/A | NOT RUN |
| CustomVoice audition | NOT RUN | NOT RUN |
| VoiceDesign audition | NOT RUN | NOT RUN |
| Clone audition | NOT RUN | NOT RUN |

For each profile, add its mode, ID, revision, model requirements, field-parity result and the names/hashes of its owned assets. Record exact preview generation settings and brief listening notes. Attach screenshots/log snippets only as supporting evidence; they do not replace bundle and asset hashes.

## 10. D6 result record

**Result:** NOT RUN — awaiting a real PC-A to PC-B transfer and audition.

**Reason:** The user has explicitly scheduled physical checks until after every engineering stage is complete. Builds #3457 and #3458 prove the packaged one-machine path only; they do not establish a separate PC-B transfer, destination compatibility, real restart, or paired voice audition.

When physical testing is complete, replace this status with PASS only after every applicable gate in Section 8 is supported. Preserve any failed/partial attempts and distinguish NOT RUN, BLOCKED, FAIL and PASS for each case.
