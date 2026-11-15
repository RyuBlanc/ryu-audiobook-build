"""Read-only presentation helpers for the saved voice-profile library.

The existing voices.json catalogue remains the source of truth. This module
normalizes its saved profiles for the Voice Library UI and reports local
compatibility and asset integrity without changing profile settings.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from app.tts.voice_profile import VoiceProfile


_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".wma"}


def profile_library_category(profile: VoiceProfile) -> str:
    """Map an actual saved profile to the existing All/Designed/Cloned/Preset/Cloud tabs."""
    provider = str(profile.provider or "").strip().casefold()
    mode = str(getattr(profile, "qwen_mode", "custom") or "custom").strip().casefold()
    if provider == "qwen-character":
        if mode == "design":
            return "Designed"
        if mode in {"clone", "voiceclone", "voice-clone"}:
            return "Cloned"
        return "Preset"
    if provider == "chatterbox" and profile.sample_path:
        return "Cloned"
    if provider in {"edge-tts", "elevenlabs"}:
        return "Cloud"
    return "Preset"


def _kind_label(kind: str) -> str:
    return {
        "custom-0.6b": "CustomVoice 0.6B",
        "custom-1.7b": "CustomVoice 1.7B",
        "design-1.7b": "VoiceDesign 1.7B",
        "base-0.6b": "Base 0.6B",
        "base-1.7b": "Base 1.7B",
    }.get(kind, kind.replace("-", " ").replace("_", " ").title())


def profile_library_model_group(
    profile: VoiceProfile,
    *,
    model_preference: str | None = None,
) -> str:
    """Return a stable display/filter group without claiming an unprobed model is installed."""
    provider = str(profile.provider or "").strip().casefold()
    model_id = str(profile.model_id or "").strip()
    if provider == "qwen-character":
        from app.tts.qwen_model_preference import get_qwen_model_preference
        from app.tts.qwen_profile_schema import qwen_model_compatibility

        preference = model_preference if model_preference is not None else get_qwen_model_preference()
        try:
            requirements = qwen_model_compatibility(profile, preference)
        except (TypeError, ValueError):
            return "Qwen3-TTS · Unsupported profile mode"
        roles = requirements.get("required_models", [])
        if not isinstance(roles, list):
            roles = []
        labels = []
        for role in roles:
            if not isinstance(role, dict):
                continue
            exact = role.get("required_model_kind") or role.get("selected_source_model_kind")
            allowed = role.get("allowed_model_kinds")
            if exact:
                labels.append(_kind_label(str(exact)))
            elif isinstance(allowed, list):
                labels.append("Auto · " + "/".join(
                    _kind_label(str(item)).replace("CustomVoice ", "").replace("Base ", "")
                    for item in allowed
                ))
        if labels:
            if str(profile.qwen_mode or "custom").casefold() == "design":
                return "Qwen3-TTS · VoiceDesign 1.7B + " + " + ".join(labels[1:])
            return "Qwen3-TTS · " + " + ".join(labels)
        return "Qwen3-TTS · " + (model_id or "Automatic")
    provider_labels = {
        "piper": "Piper",
        "kokoro": "Kokoro ONNX",
        "chatterbox": "Chatterbox",
        "windows-sapi": "Windows SAPI",
        "edge-tts": "Microsoft Edge TTS",
        "elevenlabs": "ElevenLabs",
    }
    family = provider_labels.get(provider, provider or "Unknown provider")
    if model_id and model_id.casefold() not in {"auto", "automatic"}:
        return f"{family} · {model_id}"
    return family


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _asset_record(role: str, raw_path: str | Path | None, *, required: bool) -> dict[str, Any]:
    if not raw_path:
        return {
            "role": role, "name": "", "present": False, "required": required,
            "size_bytes": 0, "sha256": None,
            "status": "missing" if required else "not configured",
        }
    raw = Path(raw_path).expanduser()
    name = raw.name
    try:
        if raw.is_symlink() or not raw.is_file():
            raise FileNotFoundError(name or "asset")
        resolved = raw.resolve(strict=True)
        size = resolved.stat().st_size
        digest = _sha256_file(resolved)
        return {
            "role": role, "name": name, "present": True, "required": required,
            "size_bytes": size, "sha256": digest, "status": "verified",
        }
    except (OSError, ValueError) as exc:
        return {
            "role": role, "name": name, "present": False, "required": required,
            "size_bytes": 0, "sha256": None,
            "status": "missing or unreadable",
            "error": str(exc)[:240],
        }


def profile_asset_integrity(profile: VoiceProfile) -> dict[str, Any]:
    """Inspect the profile's own audio without returning absolute local paths."""
    mode = str(getattr(profile, "qwen_mode", "custom") or "custom").casefold()
    assets = []
    if profile.sample_path:
        assets.append(_asset_record(
            "Clone reference audio" if mode == "clone" else "Profile sample audio",
            profile.sample_path,
            required=(mode == "clone"),
        ))
        if mode == "clone":
            sample = Path(profile.sample_path).expanduser()
            try:
                for original in sorted(sample.parent.iterdir(), key=lambda item: item.name.casefold()):
                    if (
                        original != sample
                        and original.suffix.casefold() in _AUDIO_EXTENSIONS
                        and original.is_file()
                        and not original.is_symlink()
                    ):
                        assets.append(_asset_record(
                            "Original Clone source recording", original, required=False
                        ))
            except OSError:
                pass
    elif mode == "clone":
        assets.append(_asset_record("Clone reference audio", None, required=True))

    if profile.qwen_anchor_path:
        assets.append(_asset_record(
            "Explicit VoiceDesign identity anchor",
            profile.qwen_anchor_path,
            required=True,
        ))
    elif profile.provider == "qwen-character" and mode == "design":
        try:
            from app.core.paths import runtimes_root
            from app.tts.expression import default_voice_design_anchor_text
            from app.tts.qwen_profile_schema import qwen_design_anchor_cache_path

            anchor_text = profile.qwen_anchor_text or default_voice_design_anchor_text(profile.language)
            cache = qwen_design_anchor_cache_path(
                runtimes_root() / "qwen3-tts",
                speaker=profile.voice_id,
                language=profile.language or "English",
                instruct=profile.qwen_prompt or profile.notes,
                seed=profile.qwen_seed,
                anchor_text=anchor_text,
                profile_id=profile.qwen_profile_id,
                style="neutral",
            )
            assets.append(_asset_record(
                "Worker-derived VoiceDesign identity anchor",
                cache if cache.is_file() else None,
                required=False,
            ))
            if not cache.is_file():
                assets[-1]["status"] = "not cached on this PC"
        except Exception as exc:
            assets.append({
                "role": "Worker-derived VoiceDesign identity anchor",
                "name": "", "present": False, "required": False,
                "size_bytes": 0, "sha256": None, "status": "not checked",
                "error": str(exc)[:240],
            })

    required = [item for item in assets if item.get("required")]
    failed_required = [item for item in required if not item.get("present")]
    verified = [item for item in assets if item.get("present") and item.get("sha256")]
    return {
        "assets": assets,
        "asset_count": len(assets),
        "verified_count": len(verified),
        "required_assets_ready": not failed_required,
        "status": "Verified" if assets and len(verified) == len(assets) else (
            "Missing required assets" if failed_required else (
                "Partially available" if assets else "No profile-owned audio assets"
            )
        ),
    }


def profile_revision_history(profile: VoiceProfile) -> dict[str, Any]:
    """Return verified, read-only stored revisions for a Qwen profile."""
    if str(profile.provider or "").casefold() != "qwen-character" or not profile.qwen_profile_id:
        return {"current_revision_id": None, "history": [], "history_count": 0}

    from app.core.paths import voices_root
    from app.tts.qwen_profile_import import _existing_revision_id
    from app.tts.voice_profile import profile_record

    profile_id = str(profile.qwen_profile_id)
    current_revision = _existing_revision_id(profile_record(profile))
    revision_root = voices_root() / "Qwen Profile Revisions" / profile_id
    if not revision_root.is_dir() or revision_root.is_symlink():
        return {"current_revision_id": current_revision, "history": [], "history_count": 0}

    rows: list[dict[str, Any]] = []
    for path in sorted(revision_root.iterdir(), key=lambda item: item.name.casefold()):
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix.casefold() == ".json":
            row: dict[str, Any] = {
                "kind": "Revision snapshot",
                "file_name": path.name,
                "revision_id": None,
                "saved_at": None,
                "asset_count": 0,
                "integrity_valid": False,
                "status": "Unreadable revision snapshot",
                "source_bundle_sha256": None,
            }
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict) or str(payload.get("profile_id") or "") != profile_id:
                    row["status"] = "Profile ID does not match this library entry"
                else:
                    revision_id = str(payload.get("revision_id") or "")
                    row["revision_id"] = revision_id
                    row["saved_at"] = payload.get("saved_at")
                    row["source_bundle_sha256"] = payload.get("source_bundle_sha256")
                    raw_assets = payload.get("assets", [])
                    valid = bool(re.fullmatch(r"[0-9a-f]{64}", revision_id))
                    if not isinstance(raw_assets, list):
                        valid = False
                        raw_assets = []
                    checked = 0
                    root_resolved = revision_root.resolve()
                    for asset in raw_assets:
                        if not isinstance(asset, dict):
                            valid = False
                            continue
                        relative = str(asset.get("snapshot_path") or "")
                        if (
                            not relative
                            or "\\" in relative
                            or relative.startswith("/")
                            or re.match(r"^[A-Za-z]:", relative)
                        ):
                            valid = False
                            continue
                        parts = PurePosixPath(relative).parts
                        if not parts or any(part in {"", ".", ".."} for part in parts):
                            valid = False
                            continue
                        target = revision_root.joinpath(*parts)
                        try:
                            if target.is_symlink() or not target.is_file():
                                valid = False
                                continue
                            resolved = target.resolve(strict=True)
                            resolved.relative_to(root_resolved)
                            digest = _sha256_file(resolved)
                            if digest != str(asset.get("sha256") or ""):
                                valid = False
                                continue
                            expected_size = asset.get("size_bytes")
                            if expected_size is not None and int(expected_size) != resolved.stat().st_size:
                                valid = False
                                continue
                            checked += 1
                        except (OSError, RuntimeError, ValueError, TypeError):
                            valid = False
                    row["asset_count"] = len(raw_assets)
                    row["verified_asset_count"] = checked
                    row["integrity_valid"] = valid
                    row["status"] = "Verified snapshot" if valid else "Missing or corrupt snapshot asset"
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                pass
            rows.append(row)
        elif path.suffix.casefold() == ".ryuvoice":
            row = {
                "kind": "Portable backup bundle",
                "file_name": path.name,
                "revision_id": None,
                "saved_at": None,
                "asset_count": 0,
                "integrity_valid": False,
                "status": "Unreadable backup bundle",
                "source_bundle_sha256": None,
            }
            try:
                from app.tts.qwen_profile_bundle import inspect_qwen_profile_bundle
                inspection = inspect_qwen_profile_bundle(path)
                bundle_profiles = inspection.get("profiles", [])
                if (
                    inspection.get("integrity_verified") is True
                    and len(bundle_profiles) == 1
                    and str(bundle_profiles[0].get("profile_id") or "") == profile_id
                ):
                    row["revision_id"] = bundle_profiles[0].get("revision_id")
                    row["asset_count"] = int(bundle_profiles[0].get("asset_count") or 0)
                    row["integrity_valid"] = True
                    row["status"] = "Verified backup bundle"
                    row["source_bundle_sha256"] = _sha256_file(path)
                else:
                    row["status"] = "Backup bundle does not match this profile or failed integrity checks"
            except (OSError, ValueError, TypeError, RuntimeError):
                pass
            rows.append(row)

    rows.sort(key=lambda item: (
        str(item.get("saved_at") or ""),
        str(item.get("file_name") or ""),
    ), reverse=True)
    return {
        "current_revision_id": current_revision,
        "history": rows,
        "history_count": len(rows),
        "verified_history_count": sum(1 for item in rows if item.get("integrity_valid") is True),
    }


def qwen_profile_compatibility(profile: VoiceProfile) -> dict[str, Any]:
    """Check the current PC's Qwen model/runtime availability, without changing settings."""
    if str(profile.provider or "").casefold() != "qwen-character":
        return {
            "applicable": False, "status": "Provider-specific",
            "runtime_ready": None, "model_roles_ready": None,
            "models": [], "backend_preference": None,
        }

    from app.tts.qwen_model_preference import get_qwen_backend_preference, get_qwen_model_preference
    from app.tts.qwen_profile_schema import qwen_model_compatibility
    from app.tts.qwen_character_runtime import model_installed, runtime_ready

    preference = get_qwen_model_preference()
    backend = get_qwen_backend_preference()
    requirements = qwen_model_compatibility(profile, preference)
    model_rows = []
    role_results = []
    for item in requirements.get("required_models", []):
        if not isinstance(item, dict):
            continue
        exact = item.get("required_model_kind") or item.get("selected_source_model_kind")
        allowed = item.get("allowed_model_kinds")
        candidates = [str(exact)] if exact else [
            str(value) for value in allowed if isinstance(value, str)
        ] if isinstance(allowed, list) else []
        installed = {}
        for kind in candidates:
            try:
                installed[kind] = bool(model_installed(kind))
            except (KeyError, OSError, RuntimeError, TypeError, ValueError):
                installed[kind] = False
        available = [kind for kind, ready in installed.items() if ready]
        selected_ready = bool(installed.get(str(exact), False)) if exact else bool(available)
        role_results.append(selected_ready)
        model_rows.append({
            "role": str(item.get("role") or "model"),
            "required_model_kind": str(item.get("required_model_kind") or "") or None,
            "selected_model_kind": str(exact) if exact else None,
            "allowed_model_kinds": candidates,
            "installed": installed,
            "available_variants": available,
            "ready": selected_ready,
        })
    try:
        runtime_is_ready = bool(runtime_ready())
    except Exception:
        runtime_is_ready = False
    models_ready = bool(role_results) and all(role_results)
    if not runtime_is_ready:
        status = "Runtime missing or not ready"
    elif not models_ready:
        status = "Required model missing"
    else:
        status = "Ready"
    return {
        "applicable": True,
        "status": status,
        "runtime_ready": runtime_is_ready,
        "model_roles_ready": models_ready,
        "model_preference": preference,
        "backend_preference": backend,
        "model_requirements": requirements,
        "models": model_rows,
    }


def profile_library_record(profile: VoiceProfile, *, inspect_assets: bool = False) -> dict[str, Any]:
    """Serialize a saved profile for list/detail UI use; never mutate the record."""
    category = profile_library_category(profile)
    model_group = profile_library_model_group(profile)
    row: dict[str, Any] = {
        "name": str(profile.name or ""),
        "provider": str(profile.provider or ""),
        "voice_id": str(profile.voice_id or ""),
        "model_id": str(profile.model_id or ""),
        "backend": str(profile.backend or ""),
        "language": str(profile.language or ""),
        "notes": str(profile.notes or ""),
        "authorized": bool(profile.authorized),
        "qwen_mode": str(getattr(profile, "qwen_mode", "custom") or "custom"),
        "qwen_prompt": str(getattr(profile, "qwen_prompt", "") or ""),
        "qwen_seed": getattr(profile, "qwen_seed", None),
        "qwen_profile_id": str(getattr(profile, "qwen_profile_id", "") or ""),
        "qwen_profile_schema_version": getattr(profile, "qwen_profile_schema_version", 1),
        "qwen_anchor_text": str(getattr(profile, "qwen_anchor_text", "") or ""),
        "reference_text": str(getattr(profile, "reference_text", "") or ""),
        "style_preset": str(getattr(profile, "style_preset", "Natural") or "Natural"),
        "exaggeration": getattr(profile, "exaggeration", 0.5),
        "cfg_weight": getattr(profile, "cfg_weight", 0.35),
        "profile_kind": category,
        "model_group": model_group,
        "saved": True,
    }
    if profile.provider == "qwen-character":
        row["compatibility"] = qwen_profile_compatibility(profile)
    if inspect_assets:
        row["asset_integrity"] = profile_asset_integrity(profile)
        if profile.provider == "qwen-character":
            row["revision_history"] = profile_revision_history(profile)
    return row
