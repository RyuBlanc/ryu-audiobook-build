# Stage D0 — Qwen Voice Bundle Schema Proposal

**Status:** proposed v1 contract for review and test design  
**Branch:** dragon-studio/stage-d-planning-2026-11-14  
**Baseline:** Stage C accepted commit 154bf0e0c1c1fe8334f68655d1629a3a9d1e3691  
**Companion inventory:** STAGE-D0-CURRENT-PROFILE-INVENTORY.md

## 1. Proposed archive

- Container: ZIP archive, with a single manifest at the archive root.
- Proposed user-facing extension: .ryuvoice (provisional until the UI/export acceptance pass).
- Format identifier: ryu.qwen-voice-profile-bundle.
- Initial bundle format version: 1.
- Initial Qwen profile schema version: 1.
- Hash algorithm: SHA-256 for every file payload.
- Compression is for transport only. Audio files must be copied byte-for-byte and never normalized/transcoded during export or import.

The archive is self-contained for the selected Qwen profile records and their owned audio assets. It does not include Qwen model weights, PyTorch, Python, the isolated runtime, or GPU drivers.

## 2. Proposed directory layout

~~~text
<bundle>.ryuvoice
├── manifest.json
└── profiles/
    └── <qwen_profile_id>/
        ├── profile.json
        └── assets/
            ├── clone-reference-normalized.wav
            ├── clone-reference-original.<source-extension>
            └── voicedesign-anchor-neutral.wav
~~~

Only assets applicable to the profile are present. A CustomVoice profile can have no audio assets. A Clone profile has its active normalized reference WAV and, when available, the original user-supplied recording. A VoiceDesign profile includes the generated neutral anchor when it already exists; an anchor that has never been generated is explicitly represented as not-yet-generated rather than silently synthesized during export.

## 3. Manifest contract

The manifest is authoritative for bundle and schema versions, profile identities, model compatibility, asset bindings and integrity. Paths inside the archive are normalized relative paths. Absolute paths, drive letters, parent traversal, symlinks and path escapes are invalid.

Example (illustrative values only):

~~~json
{
  "format": "ryu.qwen-voice-profile-bundle",
  "bundle_format_version": 1,
  "profile_schema_version": 1,
  "export": {
    "application": "Ryu's Audiobook",
    "application_version": "<exporting-app-version>",
    "exported_at": "<UTC-ISO-8601>",
    "profile_count": 1
  },
  "profiles": [
    {
      "profile_id": "<stable-qwen-profile-id>",
      "revision": {
        "revision_id": "<sha256-of-canonical-profile-and-assets>",
        "parent_revision_id": null,
        "created_at": "<original-profile-created-at-or-null>",
        "exported_at": "<UTC-ISO-8601>"
      },
      "profile_record": {
        "name": "Example Japanese Design",
        "provider": "qwen-character",
        "voice_id": "design-example",
        "sample_path": null,
        "model_id": "design-1.7b",
        "backend": "automatic",
        "language": "Japanese",
        "notes": "Qwen VoiceDesign",
        "authorized": true,
        "qwen_mode": "design",
        "qwen_prompt": "<complete-original-design-prompt>",
        "qwen_seed": 17001,
        "reference_text": "",
        "qwen_anchor_path": null,
        "qwen_anchor_text": "<complete-original-anchor-transcript>",
        "qwen_profile_id": "<stable-qwen-profile-id>"
      },
      "model_requirements": {
        "provider": "qwen-character",
        "mode": "design",
        "required": [
          {
            "role": "voice_design",
            "model_kind": "design-1.7b",
            "upstream_model_id": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
          },
          {
            "role": "long_form_base",
            "allowed_model_kinds": ["base-0.6b", "base-1.7b"],
            "upstream_model_ids": [
              "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
              "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
            ]
          }
        ],
        "source_machine_preference": "0.6b",
        "source_resolved_backend": "cuda",
        "source_resolved_base_kind": "base-0.6b",
        "runtime": {
          "qwen_tts": "0.1.1",
          "python": "3.12.10",
          "torch": "2.9.1",
          "torchaudio": "2.9.1",
          "tokenizer_model_id": "Qwen/Qwen3-TTS-Tokenizer-12Hz"
        },
        "model_revision": null,
        "model_revision_status": "not-recorded-by-current-runtime"
      },
      "assets": [
        {
          "asset_id": "voicedesign-anchor-neutral",
          "role": "derived_voice_identity_anchor",
          "binding": "worker-derived-neutral-anchor",
          "archive_path": "profiles/<stable-qwen-profile-id>/assets/voicedesign-anchor-neutral.wav",
          "sha256": "<sha256>",
          "size_bytes": 123456,
          "media_type": "audio/wav",
          "audio": {
            "channels": 1,
            "sample_rate_hz": 24000,
            "sample_format": "source-format-preserved"
          },
          "identity": {
            "expression_bank_version": "v9-language-matched-anchor-direction",
            "style": "neutral"
          }
        }
      ],
      "asset_state": {
        "voice_design_anchor": "present"
      },
      "extensions": {}
    }
  ],
  "integrity": {
    "algorithm": "sha256",
    "files": {
      "profiles/<stable-qwen-profile-id>/profile.json": "<sha256>",
      "profiles/<stable-qwen-profile-id>/assets/voicedesign-anchor-neutral.wav": "<sha256>"
    }
  }
}
~~~

The example is a schema illustration, not a real profile or a statement that those bytes exist. Exporter version, timestamps, profile values, model requirements and hashes must be populated from actual state. The literal sample profile ID and hashes must never be copied into a real export.

## 4. Profile record and asset binding rules

- Preserve every supported VoiceProfile field, including optional fields not currently used by Qwen.
- The serialized profile record keeps the source values for voice-defining metadata and the saved backend field. The backend is informational for provenance; provider creation still resolves the actual backend from the destination machine's global preference.
- Asset path fields inside the bundle are not source-machine absolute paths. Use null in profile_record and explicit assets[].binding entries to associate the archive asset with sample_path or qwen_anchor_path.
- The manifest preserves original basenames as optional display/provenance metadata only. It must not reuse the exporting PC's absolute folder paths.
- On import, the app installs the exact bytes into its managed asset area and resolves the local absolute path for the live VoiceProfile object. Other profile fields remain unchanged.
- The original Clone recording is an optional sidecar asset. The normalized WAV referenced by sample_path is mandatory for a valid Clone profile.
- If a VoiceDesign profile uses an explicit qwen_anchor_path, export that exact file as the profile's anchor asset.
- If VoiceDesign uses the worker-derived neutral anchor, export the already-generated file from the current runtime anchor cache and record its expression-bank version/style. The import process restores it into the destination runtime's deterministic cache location after recomputing the cache key from the imported profile. It does not set qwen_anchor_path merely to point at that derived cache file.
- If no derived anchor exists yet, set asset_state.voice_design_anchor to not-yet-generated. Do not trigger heavy Qwen inference or silently generate new voice audio during export.
- If an expected anchor should exist but is missing, unreadable or inconsistent with the profile identity, stop export with a precise repair message. Do not report a full identity-preserving bundle.

## 5. Model compatibility and destination runtime

Keep three concepts separate:

1. **Profile identity:** mode, voice/speaker ID, language, prompt, seed, reference transcript, stable profile ID and profile-owned audio.
2. **Model compatibility:** model roles and allowed internal model kinds/upstream model IDs required by that mode.
3. **Destination execution:** selected backend, GPU/VRAM, driver, runtime path, low-memory option and current global model-size preference.

Store the exporting machine's resolved values as provenance only. On import, recalculate compatibility against the destination machine and show missing model variants/runtime clearly. Never force the source backend or falsely claim the destination has a matching GPU. Never silently change a profile's language, prompt, speaker, profile ID, model role or anchor.

For VoiceDesign, VoiceDesign 1.7B is the creation model. Long-form narration additionally needs the selected Base model. The source Base choice is shown to the user; an available alternative may be selected only as an explicit user decision and must be recorded as a compatibility choice, not silently substituted.

## 6. Revision identity

- A revision ID is the SHA-256 of a canonical serialization of the profile's complete supported fields plus ordered asset-role/hash pairs. Export timestamps and machine-local paths are excluded from the canonical identity.
- Preserve qwen_profile_id independently of revision_id. The profile ID identifies the voice; revision ID identifies one exact saved state of that voice.
- Saving a modified profile creates a new revision and retains the prior revision snapshot/assets until the user explicitly removes it through a safe retention workflow.
- Export one revision or the current revision. Multi-profile bundles may include more than one revision only when explicitly requested.
- Importing the same profile ID and same revision ID is an identical duplicate. Same profile ID with a different revision ID is a version conflict, not a reason to overwrite.

## 7. Import conflict behaviour

- New profile ID + no display-name collision: add without changing profile fields.
- New profile ID + same display name: present a rename/keep-both choice; preserve the original exported name in bundle provenance if the displayed local name is changed.
- Same profile ID + same revision: report already present; default to skip.
- Same profile ID + newer/different revision: show current and incoming revisions, default to keep both revisions, and require explicit action to make one current.
- Explicit replace/restore: create a verified backup of the current profile and assets first. If backup or commit fails, leave the existing profile unchanged.
- Import of a multi-profile bundle is atomic as a set. If any selected profile fails validation, none of the selected profiles are committed.

## 8. Integrity and archive safety

Before import, validate the full archive in a temporary staging area:
- Recognized format identifier and supported major version.
- Manifest size and profile-count limits.
- No absolute paths, traversal, alternate-stream paths, symlink entries or duplicate normalized archive paths.
- Every listed file exists exactly once; no unlisted payload files unless explicitly permitted by schema.
- Declared and actual file sizes match configured limits.
- SHA-256 for every payload and canonical profile revision calculation match.
- Profile IDs, field types, model roles, mode/asset bindings and authorization values are structurally valid.
- Audio assets can be parsed without transcoding.
- Compression ratio and total expanded size stay within defensive limits.

Only after every check passes may the import transaction write the catalogue and assets. Interrupted imports must clean their staging directory and preserve the previous catalogue.

## 9. Decisions locked for the v1 proposal

- ZIP container; proposed extension .ryuvoice.
- One manifest with explicit bundle/schema versions.
- Relative archive paths plus asset bindings; no source-machine absolute paths.
- Include exact profile-owned assets; include the original Clone source sidecar when found.
- Include existing derived VoiceDesign neutral anchor; represent never-generated separately.
- Model weights and runtime are not bundled by default.
- Destination backend is detected/selected locally.
- Stable profile ID and separate immutable revision ID.
- Additive import and all-or-nothing transaction by default.

The provisional extension and precise size limits may be finalized during implementation review. The manifest shape and preservation rules are the D1 design baseline unless tests or source inspection expose a conflict.

## 10. Next step

D0 inventory and the proposed schema are recorded. Before D1 changes VoiceProfile or persistence, add tests proving the canonical revision calculation, legacy read compatibility, anchor-cache asset discovery and asset-binding round-trip. D1 must preserve existing C1–C4 identity/restart behaviour without rewriting existing saved user profiles.
