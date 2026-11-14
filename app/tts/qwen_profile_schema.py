"""Versioned Qwen profile metadata and stable revision helpers."""
from __future__ import annotations

import hashlib
import json
import re

from app.tts.qwen_model_preference import normalize_qwen_model_preference

CURRENT_QWEN_PROFILE_SCHEMA_VERSION = 1
QWEN_MODEL_COMPATIBILITY_SCHEMA_VERSION = 1
QWEN_TOKENIZER_MODEL_ID = "Qwen/Qwen3-TTS-Tokenizer-12Hz"
QWEN_MODEL_IDS = {
    "custom-0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    "custom-1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "design-1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "base-0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "base-1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
}


def qwen_model_compatibility(profile, model_preference: object = "auto") -> dict[str, object]:
    """Describe mode-specific model compatibility without probing local hardware.

    The preference is supplied by the caller as a source-machine snapshot. The
    returned metadata describes model roles and allowable variants; it never
    claims that a destination GPU, backend or model installation is available.
    """
    if str(profile.provider or "").casefold() != "qwen-character":
        raise ValueError("Qwen model compatibility requires a Qwen voice profile.")
    mode = str(profile.qwen_mode or "custom").strip().casefold()
    preference = normalize_qwen_model_preference(model_preference)
    model_ids = dict(QWEN_MODEL_IDS)
    allowed = {
        "custom": ["custom-0.6b", "custom-1.7b"],
        "clone": ["base-0.6b", "base-1.7b"],
        "design": ["base-0.6b", "base-1.7b"],
    }
    if mode not in allowed:
        raise ValueError(f"Unsupported Qwen profile mode: {mode}")

    if mode == "design":
        base_kind = f"base-{preference}" if preference in {"0.6b", "1.7b"} else None
        required_models = [
            {
                "role": "voice_design",
                "required_model_kind": "design-1.7b",
                "upstream_model_id": model_ids["design-1.7b"],
            },
            {
                "role": "long_form_base",
                "allowed_model_kinds": allowed["design"],
                "selected_source_model_kind": base_kind,
                "upstream_model_ids": [model_ids[kind] for kind in allowed["design"]],
            },
        ]
    else:
        prefix = "custom" if mode == "custom" else "base"
        allowed_kinds = allowed[mode]
        stored_hint = str(profile.model_id or "").strip().casefold()
        selected_kind = None
        if preference in {"0.6b", "1.7b"}:
            selected_kind = f"{prefix}-{preference}"
        elif stored_hint in allowed_kinds:
            selected_kind = stored_hint
        required_models = [
            {
                "role": "custom_voice" if mode == "custom" else "clone_base",
                "allowed_model_kinds": allowed_kinds,
                "selected_source_model_kind": selected_kind,
                "upstream_model_ids": [model_ids[kind] for kind in allowed_kinds],
            }
        ]

    return {
        "schema_version": QWEN_MODEL_COMPATIBILITY_SCHEMA_VERSION,
        "provider": "qwen-character",
        "mode": mode,
        "source_machine_preference": preference,
        "source_profile_model_hint": str(profile.model_id or ""),
        "required_models": required_models,
        "tokenizer_model_id": QWEN_TOKENIZER_MODEL_ID,
        "runtime": {
            "python": "3.12.10",
            "torch": "2.9.1",
            "torchaudio": "2.9.1",
            "qwen_tts": "0.1.1",
        },
    }


def qwen_profile_revision_id(profile, asset_sha256: dict[str, str] | None = None) -> str:
    """Return a stable revision hash independent of source-machine file paths.

    Absolute path fields are represented by their corresponding caller-supplied
    content digests. This makes the revision stable when the same files move to
    another PC while still changing when profile settings or asset bytes change.
    """
    from app.tts.voice_profile import profile_record

    record = profile_record(profile)
    record.pop("sample_path", None)
    record.pop("qwen_anchor_path", None)
    # A schema migration is not a user edit and must not create a new profile revision.
    record.pop("qwen_profile_schema_version", None)
    supplied_assets = dict(asset_sha256 or {})
    required_asset_keys = []
    if profile.sample_path:
        required_asset_keys.append("sample_path")
    if profile.qwen_anchor_path:
        required_asset_keys.append("qwen_anchor_path")
    missing_assets = [key for key in required_asset_keys if not supplied_assets.get(key)]
    if missing_assets:
        raise ValueError(
            "Profile revision requires SHA-256 for referenced assets: " + ", ".join(missing_assets)
        )
    for key, digest in supplied_assets.items():
        if not re.fullmatch(r"[0-9a-fA-F]{64}", str(digest or "")):
            raise ValueError(f"Asset '{key}' does not have a valid SHA-256 digest.")
    normalized_assets = {
        str(key): str(value).strip().casefold()
        for key, value in sorted(supplied_assets.items(), key=lambda item: str(item[0]))
    }
    payload = {
        "revision_schema_version": 1,
        "profile_record": record,
        "asset_sha256": normalized_assets,
    }
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
