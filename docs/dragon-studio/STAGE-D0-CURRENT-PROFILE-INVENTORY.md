# Stage D0 — Existing Qwen Profile and Asset Inventory

**Audit date:** 14 November 2026  
**Source baseline:** 154bf0e0c1c1fe8334f68655d1629a3a9d1e3691  
**Planning branch:** dragon-studio/stage-d-planning-2026-11-14  
**Scope:** read-only inventory; no application source or user data changed

## 1. Current persisted profile record

The current domain record is VoiceProfile in app/tts/voice_profile.py.

| Field | Current purpose | Portability classification |
|---|---|---|
| name | User-visible profile name | Portable profile metadata |
| provider | Provider key, e.g. qwen-character | Portable identity/type |
| voice_id | Qwen speaker or Clone/design voice identity | Portable identity |
| sample_path | Absolute path to Clone reference WAV | Machine-local pointer; asset must be bundled and remapped |
| model_id | Current saved model-kind/preference hint | Needs explicit role/model compatibility metadata; not sufficient alone |
| backend | Saved compute preference, normally automatic | Destination-machine runtime setting, not acoustic identity |
| language | Selected profile language | Portable voice-defining metadata |
| notes | Human-readable information | Portable metadata |
| authorized | User permission confirmation | Must be preserved exactly; never inferred or upgraded |
| qwen_mode | custom, design or clone | Portable identity/type |
| qwen_prompt | Custom instruction or VoiceDesign prompt | Portable voice-defining metadata |
| qwen_seed | Synthesis/design seed | Portable voice-defining metadata |
| reference_text | Transcript for Clone conditioning | Portable voice-defining metadata |
| qwen_anchor_path | Optional explicit VoiceDesign anchor path | Machine-local pointer; asset must be bundled and remapped |
| qwen_anchor_text | Canonical VoiceDesign anchor transcript | Portable voice-defining metadata |
| qwen_profile_id | Stable Qwen identity namespace | Preserve exactly across export/import |

Other generic fields (exaggeration, cfg_weight, style_preset) also exist in the shared record. The first Stage D package should preserve every serialized field, including optional fields that are not currently central to Qwen.

Source: app/tts/voice_profile.py, VoiceProfile dataclass (lines 17–42 at the Stage C baseline).

## 2. Catalogue storage and migration

- voices_root() resolves to Path.home() / "Ryu's Audiobook" / "Voices" in the default configuration (app/core/paths.py).
- profiles_file() is voices_root() / "voices.json" (app/tts/voice_profile.py).
- The catalogue is a JSON list of VoiceProfile dictionaries. save_profiles() serializes with dataclasses.asdict, verifies the temporary JSON by reading it back, and atomically replaces voices.json.
- load_saved_profiles() keeps legacy Qwen profiles readable; it normalizes legacy backend values and assigns a qwen_profile_id when one is missing, then atomically persists the migration.
- load_profiles() merges saved records with built-in voices. It can disambiguate display-name collisions by changing a saved profile's display name and persisting that change.
- Current persistence has no dedicated bundle format, import/export API, revision history, or per-profile schema-version field.

**Design consequence:** the Stage D bundle must preserve unknown/optional record fields and profile IDs. Import must not route through a save path that silently changes profile identity, name or machine-specific settings before the imported record is validated.

Sources: app/tts/voice_profile.py (profiles_file, load_saved_profiles, load_profiles, save_profiles); app/core/paths.py (app_root, voices_root).

## 3. Qwen model and runtime identity

The current Qwen model-kind map is:

| Internal model kind | Upstream model identifier | Role |
|---|---|---|
| custom-0.6b | Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice | CustomVoice |
| custom-1.7b | Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice | CustomVoice |
| design-1.7b | Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign | VoiceDesign creation |
| base-0.6b | Qwen/Qwen3-TTS-12Hz-0.6B-Base | Clone / VoiceDesign narration Base |
| base-1.7b | Qwen/Qwen3-TTS-12Hz-1.7B-Base | Clone / VoiceDesign narration Base |

The tokenizer identifier is Qwen/Qwen3-TTS-Tokenizer-12Hz.

Runtime constants currently declare Python 3.12.10, Torch 2.9.1, Torchaudio 2.9.1, and Qwen TTS 0.1.1. The private Qwen runtime is under runtimes_root() / "qwen3-tts"; model directories are under models_root() / "qwen3-tts" / <model-kind>. Those roots can be configured separately.

The app-wide model-size setting accepts auto, 0.6b and 1.7b. VoiceDesign creation remains the 1.7B VoiceDesign model; the global size preference chooses the long-form Base model. Clone resolves to a Base model, and CustomVoice resolves to the selected CustomVoice size.

For Qwen profiles, provider_from_profile() resolves the active backend from the destination PC's global backend preference. The stored backend is not treated as an immutable voice identity. Model selection can also be resolved from global preference and local hardware; a stored model_id such as auto is therefore not a complete compatibility description.

**Design consequence:** the bundle manifest needs explicit model role, internal model kind, upstream model ID and expected Design/Base pairing. It must report missing model assets separately from profile import. The actual CUDA/ROCm/XPU/CPU backend remains local to the destination machine and must not be silently copied as a hardware requirement.

Sources: app/tts/qwen_character_runtime.py; app/tts/qwen_model_preference.py; app/tts/profile_provider.py; app/tts/qwen_character_worker.py.

## 4. Profile-owned and derived audio assets

### Clone reference

import_reference_audio() currently:

1. Builds a directory from a sanitized profile name below Voices/.
2. Copies the original source audio into that directory using the original filename.
3. Converts the source into reference.wav using FFmpeg mono, 24 kHz, PCM16.
4. Validates the normalized WAV and returns its path.
5. The saved Qwen Clone profile's sample_path points to the normalized reference.wav; the original file is a sidecar in the same directory but is not separately listed in VoiceProfile.

This means the Clone profile has at least two relevant files: original source recording and normalized conditioning WAV. The original is not used by the current synthesis path, but it is part of the user's imported reference material and should not be discarded by a transfer/backup workflow.

**D0 requirement:** export both files when the source sidecar is present; always export the exact normalized file referenced by sample_path. Record which asset is the active conditioning audio. Do not normalize or transcode again during import.

### VoiceDesign identity anchor

- The profile record usually stores qwen_anchor_text and qwen_profile_id; the generated identity anchor is not normally saved into qwen_anchor_path.
- The Qwen worker uses one canonical neutral anchor style (ANCHOR_STYLES = ("neutral",)).
- When no explicit anchor path is supplied, _anchor_path() derives a content-addressed file name under <RUNTIME_ROOT>/voice_anchors/.
- The anchor identity key includes expression-bank version, speaker/voice ID, language, prompt/instruction, seed, anchor text, profile ID and style. The current expression-bank version is v9-language-matched-anchor-direction.
- The derived anchor directory is in the configured Qwen runtime root, not in the profile catalogue's Voices/ directory.
- When an explicit qwen_anchor_path exists, the neutral anchor uses that path instead.

**D0 requirement:** VoiceDesign export must discover and include the exact generated neutral anchor that belongs to the selected profile, along with the anchor-generation version/identity metadata. Do not assume that copying only voices.json transfers the saved acoustic identity. If the expected anchor is absent, report it and require a defined repair/rebuild path before claiming a complete bundle.

Sources: app/tts/qwen_character_worker.py (EXPRESSION_BANK_VERSION, ANCHOR_STYLES, _anchor_path); app/tts/qwen_character_runtime.py (RUNTIME_ROOT); app/tts/providers/qwen_character.py (provider request and signature).

## 5. Identity and generation-signature behaviour

- qwen_profile_id is part of the worker's anchor cache key and the Qwen provider generation signature.
- The Qwen provider signature includes voice ID, language, Qwen mode, expression pipeline version for Design, resolved model kind, backend, low-memory mode, long-form Base kind for Design, instruction, reference text, seed, explicit anchor content signature/text, profile ID and Clone reference content signature.
- ProfileBoundProvider.generation_signature() also hashes the referenced sample and anchor files and wraps the engine signature.

**Design consequence:** a valid round-trip must preserve the stable profile ID and every voice-defining field, and verify byte-identical referenced assets. Destination backend and selected hardware are re-evaluated locally; same-audio parity checks must use an explicitly matching compatible model/runtime setup.

Sources: app/tts/providers/qwen_character.py; app/tts/profile_provider.py.

## 6. Current UI and lifecycle observations

- The Voice Studio already offers separate Qwen CustomVoice, VoiceDesign and Voice Clone modes.
- Saving a profile currently operates on the display name. Existing entries with the same name can be replaced through the current Save flow; profile IDs are not the visible collision key.
- The page can load saved profiles and show whether an explicit anchor path is missing. It does not yet expose a complete export/import/compatibility report.
- There is a Qwen model filter and a profile-type grouping requirement in the existing UX direction; Stage D must preserve the existing library filter meanings and avoid mixing remote provider catalogue entries with local Qwen profiles.

**Design consequence:** library collision handling should use profile ID and asset identity, not display name alone. Default import must be additive. Any explicit replace action needs a backup and a recoverable transaction.

## 7. D0 risks and design decisions to settle before D1

1. **Asset ownership:** move toward stable profile-ID-owned asset directories while retaining backward-compatible reads of the current name-based Voices/<name>/ reference folders.
2. **Anchor inventory:** implement a deterministic lookup for the current neutral anchor, detect missing/stale/corrupt anchors, and define when export must block versus offer a user-approved rebuild.
3. **Original reference sidecars:** decide how to record the original user-supplied Clone audio, not just the normalized sample_path.
4. **Model compatibility:** represent CustomVoice, VoiceDesign and Base as different model roles; preserve the exact Design 1.7B + Base size pair. Do not bundle model weights by default.
5. **Identity vs runtime:** preserve model compatibility and identity settings but do not pin the imported profile to the source PC's backend, VRAM, driver, absolute paths or cache directories.
6. **Revisions:** decide whether profile revisions are immutable snapshots inside the library, exported bundle history, or both. The current voices.json record has no revision history.
7. **Schema evolution:** preserve unknown fields from older/newer records; unsupported major bundle versions must fail without altering the catalogue.
8. **Asset limits/security:** define bundle size limits, path validation, audio validation and archive bomb protections before enabling import.

## 8. D0 exit decision

**D0 inventory is complete. D1 must not begin until the profile manifest and asset-ownership design explicitly resolve Sections 4 and 7.**

No application source, existing voices.json, saved profile, model, runtime, anchor WAV or reference recording was changed during this read-only audit.
