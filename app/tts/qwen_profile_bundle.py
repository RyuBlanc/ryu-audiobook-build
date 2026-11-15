"""Portable, integrity-checked Qwen voice-profile bundle export.

Import/installation is deliberately not implemented here; Stage D3 owns the
transactional import path. This module packages saved profile data and
validates a completed archive before it is exposed to the user.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import wave
import zipfile

from app.core.paths import runtimes_root
from app.tts.expression import default_voice_design_anchor_text
from app.tts.qwen_model_preference import get_qwen_model_preference
from app.tts.qwen_profile_schema import (
    CURRENT_QWEN_PROFILE_SCHEMA_VERSION,
    QWEN_EXPRESSION_BANK_VERSION,
    qwen_design_anchor_cache_path,
    qwen_model_compatibility,
    qwen_profile_revision_id,
    require_supported_qwen_profile_schema,
)
from app.tts.voice_profile import VoiceProfile, profile_record
from app.version import APP_NAME, APP_VERSION

BUNDLE_FORMAT = "ryu.qwen-voice-profile-bundle"
BUNDLE_FORMAT_VERSION = 1
MAX_PROFILES = 100
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_PROFILE_BYTES = 2 * 1024 * 1024
MAX_ASSET_BYTES = 512 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".wma"}
_PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class QwenBundleExportResult:
    path: Path
    profile_count: int
    asset_count: int
    sha256: str
    revision_ids: tuple[str, ...]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n").encode("utf-8")


def _safe_profile_id(profile: VoiceProfile) -> str:
    profile_id = str(profile.qwen_profile_id or "").strip()
    if not _PROFILE_ID_RE.fullmatch(profile_id) or profile_id in {".", ".."}:
        raise ValueError(f"Qwen profile '{profile.name}' has no safe stable profile ID; save/migrate it before export.")
    return profile_id


def _resolve_regular_file(raw_path: str | Path, label: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"{label} is missing: {path.name}")
    current = path
    while True:
        if current.is_symlink():
            raise ValueError(f"{label} cannot be a symbolic link.")
        if current.parent == current:
            break
        current = current.parent
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"{label} must be a regular file.")
    size = resolved.stat().st_size
    if size <= 0:
        raise ValueError(f"{label} is empty.")
    if size > MAX_ASSET_BYTES:
        raise ValueError(f"{label} exceeds the {MAX_ASSET_BYTES:,}-byte export limit.")
    return resolved


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _wav_metadata(path: Path, label: str) -> dict[str, int]:
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_rate = handle.getframerate()
            sample_width = handle.getsampwidth()
            frames = handle.getnframes()
            if channels < 1 or sample_rate < 1 or sample_width not in {1, 2, 3, 4} or frames < 1:
                raise ValueError("invalid WAV stream parameters")
            return {"channels": channels, "sample_rate_hz": sample_rate,
                    "sample_width_bytes": sample_width, "frames": frames}
    except (OSError, EOFError, wave.Error, ValueError) as exc:
        raise ValueError(f"{label} is not a readable WAV audio file: {exc}") from exc


def _audio_media_type(path: Path) -> str:
    # Python's system MIME registry varies between platforms (e.g. audio/x-wav
    # on Linux and audio/wav elsewhere). Use one portable label in manifests.
    if path.suffix.casefold() == ".wav":
        return "audio/wav"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or f"audio/{path.suffix.lower().lstrip('.') or 'unknown'}"


def _asset_entry(
    *, profile_id: str, path: Path, archive_name: str, role: str,
    binding: str, revision_key: str, required: bool,
    source_filename: str | None = None, identity: dict[str, object] | None = None,
    validate_wav: bool = False,
) -> tuple[dict[str, object], Path]:
    resolved = _resolve_regular_file(path, role.replace("_", " "))
    metadata = _wav_metadata(resolved, role) if validate_wav else None
    entry: dict[str, object] = {
        "role": role, "binding": binding, "revision_key": revision_key,
        "archive_path": f"profiles/{profile_id}/assets/{archive_name}",
        "sha256": _sha256_file(resolved), "size_bytes": resolved.stat().st_size,
        "media_type": _audio_media_type(resolved), "required": bool(required),
    }
    if source_filename:
        entry["source_filename"] = source_filename
    if identity:
        entry["identity"] = identity
    if metadata is not None:
        entry["audio"] = metadata
    return entry, resolved


def _clone_original_sidecars(sample_path: Path) -> list[Path]:
    candidates: list[Path] = []
    try:
        siblings = list(sample_path.parent.iterdir())
    except OSError:
        return candidates
    for candidate in siblings:
        if candidate == sample_path or candidate.name.casefold() == sample_path.name.casefold():
            continue
        if candidate.suffix.casefold() not in _AUDIO_EXTENSIONS:
            continue
        if candidate.is_symlink() or not candidate.is_file():
            continue
        candidates.append(candidate.resolve())
    return sorted(candidates, key=lambda item: item.name.casefold())


def _profile_asset_entries(profile: VoiceProfile, profile_id: str):
    mode = str(profile.qwen_mode or "custom").strip().casefold()
    entries: list[dict[str, object]] = []
    sources: list[tuple[dict[str, object], Path]] = []
    revision_hashes: dict[str, str] = {}
    state = {
        "clone_reference": "not_required",
        "clone_originals": "not_found",
        "voice_design_anchor": "not_required",
    }

    if profile.sample_path:
        sample = Path(profile.sample_path).expanduser()
        role = "clone_reference_conditioning" if mode == "clone" else "profile_sample_audio"
        entry, resolved = _asset_entry(
            profile_id=profile_id, path=sample,
            archive_name="clone-reference-normalized.wav" if mode == "clone" else "profile-sample" + sample.suffix.lower(),
            role=role, binding="sample_path", revision_key="sample_path",
            required=(mode == "clone"), validate_wav=True,
        )
        entries.append(entry)
        sources.append((entry, resolved))
        revision_hashes["sample_path"] = str(entry["sha256"])
        if mode == "clone":
            state["clone_reference"] = "present"
            originals = _clone_original_sidecars(resolved)
            if originals:
                state["clone_originals"] = "present"
            for index, original in enumerate(originals, start=1):
                key = f"clone_original_{index:03d}"
                original_entry, original_path = _asset_entry(
                    profile_id=profile_id, path=original,
                    archive_name=f"clone-reference-original-{index:03d}{original.suffix.lower()}",
                    role="clone_reference_original", binding="clone-reference-original-sidecar",
                    revision_key=key, required=False, source_filename=original.name,
                )
                entries.append(original_entry)
                sources.append((original_entry, original_path))
                revision_hashes[key] = str(original_entry["sha256"])
    elif mode == "clone":
        raise ValueError(f"Qwen Clone profile '{profile.name}' has no saved conditioning reference audio.")

    if mode == "design":
        if profile.qwen_anchor_path:
            anchor = Path(profile.qwen_anchor_path).expanduser()
            entry, resolved = _asset_entry(
                profile_id=profile_id, path=anchor,
                archive_name="voicedesign-anchor-neutral.wav",
                role="voicedesign_identity_anchor_explicit", binding="qwen_anchor_path",
                revision_key="qwen_anchor_path", required=True,
                identity={"style": "neutral", "origin": "explicit-profile-anchor"},
                validate_wav=True,
            )
            entries.append(entry)
            sources.append((entry, resolved))
            revision_hashes["qwen_anchor_path"] = str(entry["sha256"])
            state["voice_design_anchor"] = "present_explicit"
        else:
            runtime_root = runtimes_root() / "qwen3-tts"
            effective_anchor_text = profile.qwen_anchor_text or default_voice_design_anchor_text(profile.language)
            anchor_path = qwen_design_anchor_cache_path(
                runtime_root, speaker=profile.voice_id,
                language=profile.language or "English",
                instruct=profile.qwen_prompt or profile.notes,
                seed=profile.qwen_seed, anchor_text=effective_anchor_text,
                profile_id=profile.qwen_profile_id, style="neutral",
            )
            if anchor_path.exists():
                entry, resolved = _asset_entry(
                    profile_id=profile_id, path=anchor_path,
                    archive_name="voicedesign-anchor-neutral.wav",
                    role="voicedesign_identity_anchor_derived",
                    binding="worker-derived-neutral-anchor",
                    revision_key="derived_voice_identity_anchor", required=False,
                    identity={"style": "neutral", "expression_bank_version": QWEN_EXPRESSION_BANK_VERSION},
                    validate_wav=True,
                )
                entries.append(entry)
                sources.append((entry, resolved))
                revision_hashes["derived_voice_identity_anchor"] = str(entry["sha256"])
                state["voice_design_anchor"] = "present_derived"
            else:
                state["voice_design_anchor"] = "not_found_in_source_cache"
    return entries, sources, revision_hashes, state


def _profile_from_bundle_record(record: dict[str, object]) -> VoiceProfile:
    known = {item.name for item in fields(VoiceProfile) if item.name != "extra_fields"}
    extra = {key: value for key, value in record.items() if key not in known and key != "extra_fields"}
    raw_extra = record.get("extra_fields")
    if isinstance(raw_extra, dict):
        extra.update(raw_extra)
    values = {key: value for key, value in record.items() if key in known}
    values["extra_fields"] = extra
    return VoiceProfile(**values)


def _zip_write_bytes(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    archive.writestr(info, payload)


def _is_safe_archive_path(value: str) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        return False
    if re.match(r"^[A-Za-z]:", value):
        return False
    path = PurePosixPath(value)
    return (not path.is_absolute() and bool(path.parts)
            and all(part not in {"", ".", ".."} for part in path.parts)
            and str(path) == value)


def _hash_zip_member(archive: zipfile.ZipFile, name: str) -> str:
    digest = hashlib.sha256()
    with archive.open(name, "r") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_wav_member(archive: zipfile.ZipFile, name: str) -> None:
    try:
        with archive.open(name, "r") as stream:
            with wave.open(stream, "rb") as audio:
                if audio.getnchannels() < 1 or audio.getframerate() < 1 or audio.getnframes() < 1:
                    raise ValueError("invalid WAV stream parameters")
    except (OSError, EOFError, wave.Error, ValueError) as exc:
        raise ValueError(f"Bundle audio member '{name}' is not a readable WAV: {exc}") from exc


def inspect_qwen_profile_bundle(bundle_path: str | Path) -> dict[str, object]:
    """Validate structure, schemas, all payload hashes and conditioning audio headers."""
    path = Path(bundle_path).expanduser()
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError("Qwen voice-profile bundle does not exist as a regular file.")
    if path.stat().st_size <= 0:
        raise ValueError("Qwen voice-profile bundle is empty.")
    try:
        archive = zipfile.ZipFile(path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Qwen voice-profile bundle is not a valid ZIP archive: {exc}") from exc

    with archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)):
            raise ValueError("Bundle contains duplicate archive paths.")
        for item in infos:
            if item.is_dir() or not _is_safe_archive_path(item.filename):
                raise ValueError(f"Bundle contains an unsafe archive path: {item.filename!r}")
            mode = (item.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise ValueError(f"Bundle contains a symbolic-link entry: {item.filename}")
            if item.file_size < 0 or item.file_size > MAX_ASSET_BYTES:
                raise ValueError(f"Bundle member exceeds the allowed size: {item.filename}")
            if item.compress_size > 0 and item.file_size > 1024 * 1024:
                if item.file_size / item.compress_size > 200:
                    raise ValueError(f"Bundle member has an unsafe compression ratio: {item.filename}")
        if sum(item.file_size for item in infos) > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise ValueError("Bundle expands beyond the total permitted size.")
        if "manifest.json" not in names:
            raise ValueError("Bundle is missing manifest.json.")
        if archive.getinfo("manifest.json").file_size > MAX_MANIFEST_BYTES:
            raise ValueError("Bundle manifest exceeds the allowed size.")
        try:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Bundle manifest is not valid UTF-8 JSON: {exc}") from exc
        if not isinstance(manifest, dict) or manifest.get("format") != BUNDLE_FORMAT:
            raise ValueError("Bundle format identifier is not recognized.")
        if manifest.get("bundle_format_version") != BUNDLE_FORMAT_VERSION:
            raise ValueError("Bundle uses an unsupported bundle-format version.")
        if manifest.get("profile_schema_version") != CURRENT_QWEN_PROFILE_SCHEMA_VERSION:
            raise ValueError("Bundle uses an unsupported Qwen profile schema version.")
        profiles = manifest.get("profiles")
        if not isinstance(profiles, list) or not profiles or len(profiles) > MAX_PROFILES:
            raise ValueError("Bundle profile list is missing or exceeds the supported count.")
        integrity = manifest.get("integrity")
        if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
            raise ValueError("Bundle SHA-256 integrity manifest is missing.")
        expected_files = integrity.get("files")
        if not isinstance(expected_files, dict) or set(expected_files) != set(names) - {"manifest.json"}:
            raise ValueError("Bundle contains unlisted or missing payload files.")

        seen_ids: set[str] = set()
        validated_profiles = []
        for entry in profiles:
            if not isinstance(entry, dict):
                raise ValueError("Bundle contains an invalid profile entry.")
            profile_id = str(entry.get("profile_id") or "")
            if not _PROFILE_ID_RE.fullmatch(profile_id) or profile_id in seen_ids:
                raise ValueError("Bundle contains an invalid or duplicate profile ID.")
            seen_ids.add(profile_id)
            profile_path = entry.get("profile_path")
            if profile_path != f"profiles/{profile_id}/profile.json" or not _is_safe_archive_path(profile_path):
                raise ValueError("Bundle profile record path does not match its stable profile ID.")
            if profile_path not in expected_files or archive.getinfo(profile_path).file_size > MAX_PROFILE_BYTES:
                raise ValueError("Bundle profile record is missing or too large.")
            try:
                profile_doc = json.loads(archive.read(profile_path).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"Profile record is not valid UTF-8 JSON: {exc}") from exc
            if not isinstance(profile_doc, dict) or not isinstance(profile_doc.get("profile_record"), dict):
                raise ValueError("Profile record payload is malformed.")
            record = profile_doc["profile_record"]
            if record.get("provider") != "qwen-character":
                raise ValueError("Bundle contains a non-Qwen profile.")
            profile = _profile_from_bundle_record(record)
            if profile.qwen_profile_id != profile_id or profile_doc.get("profile_id") != profile_id:
                raise ValueError("Profile ID does not match its serialized Qwen identity.")
            require_supported_qwen_profile_schema(profile)
            if profile_doc.get("profile_schema_version") != CURRENT_QWEN_PROFILE_SCHEMA_VERSION:
                raise ValueError("Profile record uses an unsupported schema version.")
            if record.get("sample_path") not in (None, "") or record.get("qwen_anchor_path") not in (None, ""):
                raise ValueError("Portable profile records must not contain source-machine asset paths.")
            requirements = profile_doc.get("model_requirements")
            if not isinstance(requirements, dict) or requirements.get("provider") != "qwen-character":
                raise ValueError("Profile model-compatibility metadata is missing.")
            assets = entry.get("assets")
            if not isinstance(assets, list):
                raise ValueError("Profile asset list is malformed.")
            revision_assets: dict[str, str] = {}
            for asset in assets:
                if not isinstance(asset, dict):
                    raise ValueError("Profile contains an invalid asset descriptor.")
                asset_path = asset.get("archive_path")
                if not _is_safe_archive_path(asset_path) or not asset_path.startswith(f"profiles/{profile_id}/assets/"):
                    raise ValueError("Profile asset path is unsafe or outside its profile directory.")
                if asset_path not in expected_files or asset.get("size_bytes") != archive.getinfo(asset_path).file_size:
                    raise ValueError("Profile asset is missing or has an incorrect size.")
                digest = str(asset.get("sha256") or "")
                if not _SHA256_RE.fullmatch(digest) or expected_files[asset_path] != digest:
                    raise ValueError("Profile asset SHA-256 metadata is malformed or inconsistent.")
                revision_key = str(asset.get("revision_key") or "")
                if not revision_key or revision_key in revision_assets:
                    raise ValueError("Profile asset revision keys must be unique and non-empty.")
                revision_assets[revision_key] = digest
                if asset.get("binding") in {"sample_path", "qwen_anchor_path"}:
                    if asset.get("media_type") != "audio/wav":
                        raise ValueError("Qwen conditioning and anchor bindings must be WAV audio.")
                    _validate_wav_member(archive, asset_path)
            if profile.qwen_mode == "clone" and not any(
                asset.get("binding") == "sample_path" and asset.get("required") is True for asset in assets
            ):
                raise ValueError("Qwen Clone bundle is missing its required conditioning reference.")
            calculated = qwen_profile_revision_id(profile, revision_assets)
            if calculated != entry.get("revision_id") or calculated != profile_doc.get("revision_id"):
                raise ValueError("Profile revision fingerprint does not match its record/assets.")
            validated_profiles.append({
                "profile_id": profile_id,
                "revision_id": calculated,
                "profile_path": profile_path,
                "asset_count": len(assets),
            })

        for name, expected_digest in expected_files.items():
            if not _is_safe_archive_path(name) or not _SHA256_RE.fullmatch(str(expected_digest or "")):
                raise ValueError("Bundle integrity map contains an invalid path or SHA-256.")
            if _hash_zip_member(archive, name) != expected_digest:
                raise ValueError(f"Bundle payload SHA-256 mismatch: {name}")
        return {
            "format": BUNDLE_FORMAT, "bundle_format_version": BUNDLE_FORMAT_VERSION,
            "profile_schema_version": CURRENT_QWEN_PROFILE_SCHEMA_VERSION,
            "profile_count": len(validated_profiles), "profiles": validated_profiles,
            "integrity_verified": True,
        }


def export_qwen_profiles_bundle(
    profiles: list[VoiceProfile], destination: str | Path, *,
    source_model_preference: str | None = None, overwrite: bool = False,
) -> QwenBundleExportResult:
    """Export Qwen profile settings and assets without altering source data."""
    if not isinstance(profiles, list) or not profiles or len(profiles) > MAX_PROFILES:
        raise ValueError(f"Select between 1 and {MAX_PROFILES} Qwen profiles to export.")
    preference = get_qwen_model_preference() if source_model_preference is None else source_model_preference
    destination_path = Path(destination).expanduser()
    if destination_path.suffix.casefold() != ".ryuvoice":
        raise ValueError("Qwen profile bundles must use the .ryuvoice extension.")
    if destination_path.is_symlink():
        raise ValueError("The export destination cannot be a symbolic link.")
    if destination_path.exists() and not overwrite:
        raise FileExistsError("The export file already exists; choose a new name or explicitly confirm overwrite.")
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    seen_ids: set[str] = set()
    payloads: dict[str, bytes | Path] = {}
    integrity_files: dict[str, str] = {}
    manifest_profiles = []
    revision_ids = []
    asset_count = 0

    for profile in profiles:
        if not isinstance(profile, VoiceProfile) or profile.provider != "qwen-character":
            raise ValueError("Only saved Qwen3-TTS profiles can be exported in this bundle format.")
        require_supported_qwen_profile_schema(profile)
        profile_id = _safe_profile_id(profile)
        if profile_id in seen_ids:
            raise ValueError(f"Duplicate Qwen profile ID selected for export: {profile_id}")
        seen_ids.add(profile_id)
        mode = str(profile.qwen_mode or "custom").strip().casefold()
        if mode not in {"custom", "design", "clone"}:
            raise ValueError(f"Qwen profile '{profile.name}' has unsupported mode '{mode}'.")
        assets, asset_sources, revision_hashes, asset_state = _profile_asset_entries(profile, profile_id)
        if len(assets) > 25:
            raise ValueError(f"Qwen profile '{profile.name}' has too many associated audio assets.")
        revision_id = qwen_profile_revision_id(profile, revision_hashes)
        revision_ids.append(revision_id)
        profile_path = f"profiles/{profile_id}/profile.json"
        portable_record = profile_record(profile)
        portable_record["sample_path"] = None
        portable_record["qwen_anchor_path"] = None
        profile_doc = {
            "profile_schema_version": CURRENT_QWEN_PROFILE_SCHEMA_VERSION,
            "profile_id": profile_id,
            "revision_id": revision_id,
            "profile_record": portable_record,
            "model_requirements": qwen_model_compatibility(profile, preference),
            "asset_state": asset_state,
        }
        profile_bytes = _canonical_json_bytes(profile_doc)
        if len(profile_bytes) > MAX_PROFILE_BYTES:
            raise ValueError(f"Qwen profile '{profile.name}' serialized record is too large.")
        payloads[profile_path] = profile_bytes
        integrity_files[profile_path] = hashlib.sha256(profile_bytes).hexdigest()
        for asset_entry, source_path in asset_sources:
            name = str(asset_entry["archive_path"])
            if name in payloads:
                raise ValueError(f"Duplicate profile asset archive path: {name}")
            payloads[name] = source_path
            integrity_files[name] = str(asset_entry["sha256"])
        asset_count += len(assets)
        manifest_profiles.append({
            "profile_id": profile_id, "revision_id": revision_id,
            "profile_path": profile_path, "assets": assets,
        })

    manifest = {
        "format": BUNDLE_FORMAT,
        "bundle_format_version": BUNDLE_FORMAT_VERSION,
        "profile_schema_version": CURRENT_QWEN_PROFILE_SCHEMA_VERSION,
        "export": {
            "application": APP_NAME, "application_version": APP_VERSION,
            "exported_at": _utc_now(), "profile_count": len(manifest_profiles),
            "model_weights_included": False, "runtime_included": False,
        },
        "profiles": manifest_profiles,
        "integrity": {"algorithm": "sha256", "files": dict(sorted(integrity_files.items()))},
    }
    manifest_bytes = _canonical_json_bytes(manifest)

    fd, temp_name = tempfile.mkstemp(prefix=f".{destination_path.name}.", suffix=".tmp",
                                     dir=str(destination_path.parent))
    os.close(fd)
    temporary_path = Path(temp_name)
    try:
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            _zip_write_bytes(archive, "manifest.json", manifest_bytes)
            for name in sorted(payloads):
                value = payloads[name]
                if isinstance(value, bytes):
                    _zip_write_bytes(archive, name, value)
                    continue
                info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                with value.open("rb") as source, archive.open(info, "w") as output:
                    digest = hashlib.sha256()
                    size = 0
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        output.write(block)
                        digest.update(block)
                        size += len(block)
                if digest.hexdigest() != integrity_files[name] or size != value.stat().st_size:
                    raise IOError(f"Profile asset changed while being exported: {value.name}")
        inspect_qwen_profile_bundle(temporary_path)
        if destination_path.exists() and not overwrite:
            raise FileExistsError("The export file appeared during export; the existing file was not replaced.")
        os.replace(temporary_path, destination_path)
        return QwenBundleExportResult(
            path=destination_path, profile_count=len(profiles), asset_count=asset_count,
            sha256=_sha256_file(destination_path), revision_ids=tuple(revision_ids),
        )
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
