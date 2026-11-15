"""Transactional import and recovery for portable Qwen voice-profile bundles.

The importer validates the complete .ryuvoice archive before writing, stages every
payload, installs profile-owned bytes without transcoding, and replaces voices.json
only after the assets and revision records are ready. Incomplete transactions are
rolled back before the saved profile catalogue is read.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import time
import uuid
import zipfile

from app.core.paths import models_root, runtimes_root, voices_root
from app.tts.qwen_model_preference import get_qwen_backend_preference
from app.tts.qwen_profile_bundle import (
    BUNDLE_FORMAT,
    BUNDLE_FORMAT_VERSION,
    MAX_ASSET_BYTES,
    MAX_TOTAL_UNCOMPRESSED_BYTES,
    _canonical_json_bytes,
    _is_safe_archive_path,
    _profile_from_bundle_record,
    _sha256_file,
    export_qwen_profiles_bundle,
    inspect_qwen_profile_bundle,
)
from app.tts.qwen_profile_schema import (
    CURRENT_QWEN_PROFILE_SCHEMA_VERSION,
    QWEN_EXPRESSION_BANK_VERSION,
    qwen_design_anchor_cache_path,
    qwen_profile_revision_id,
    require_supported_qwen_profile_schema,
)
from app.tts.voice_profile import VoiceProfile, profile_record, profiles_file


_PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".wma"}
_TRANSACTION_ROOT_NAME = ".qwen-profile-import-transactions"
_PROFILE_ASSET_ROOT_NAME = "Qwen Profile Assets"
_REVISION_ROOT_NAME = "Qwen Profile Revisions"


class QwenProfileImportError(RuntimeError):
    """A validated bundle could not be safely imported."""


class QwenProfileImportConflict(QwenProfileImportError):
    """The bundle is valid, but an explicit collision decision is required."""

    def __init__(self, message: str, plan: dict[str, object]):
        super().__init__(message)
        self.plan = plan


@dataclass(frozen=True)
class QwenProfileImportResult:
    imported_profile_ids: tuple[str, ...]
    stored_revision_ids: tuple[str, ...]
    skipped_profile_ids: tuple[str, ...]
    renamed_profiles: dict[str, str]
    warnings: tuple[str, ...]
    compatibility: tuple[dict[str, object], ...]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def voice_profile_catalogue_lock(timeout_seconds: float = 60.0):
    """Return a cross-process lock shared by profile reads, saves and imports."""
    return _catalogue_lock(timeout_seconds)


@contextmanager
def _catalogue_lock(timeout_seconds: float = 60.0):
    root = voices_root()
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".voices-catalogue.lock"
    handle = lock_path.open("a+b")
    locked = False
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + max(1.0, float(timeout_seconds))
        if os.name == "nt":
            import msvcrt

            while not locked:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Timed out waiting for the Qwen voice-profile catalogue lock.")
                    time.sleep(0.05)
        else:
            import fcntl

            while not locked:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Timed out waiting for the Qwen voice-profile catalogue lock.")
                    time.sleep(0.05)
        yield
    finally:
        if locked:
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
        else:
            handle.close()


def _read_catalogue_records() -> list[dict[str, object]]:
    path = profiles_file()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QwenProfileImportError(
            f"The saved voice catalogue cannot be read safely; no import was started: {exc}"
        ) from exc
    if not isinstance(payload, list):
        raise QwenProfileImportError(
            "The saved voice catalogue is not a JSON list; no import was started."
        )
    if any(not isinstance(item, dict) for item in payload):
        raise QwenProfileImportError(
            "The saved voice catalogue contains a malformed entry; no import was started."
        )
    return payload


def _write_catalogue_records(records: list[dict[str, object]]) -> None:
    destination = profiles_file()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(records, ensure_ascii=False, indent=2)
    fd, temporary_name = tempfile.mkstemp(
        prefix=".voices.json.", suffix=".import.tmp", dir=str(destination.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        written = json.loads(temporary.read_text(encoding="utf-8"))
        if written != records:
            raise OSError("The staged voice catalogue did not match the intended records.")
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _safe_child_path(root: Path, relative: str) -> Path:
    if not _is_safe_archive_path(relative):
        raise ValueError(f"Unsafe relative bundle path: {relative!r}")
    root_resolved = root.resolve()
    target = root.joinpath(*PurePosixPath(relative).parts)
    target_resolved = target.resolve(strict=False)
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"Bundle path escapes its staging directory: {relative!r}") from exc
    current = root
    for part in PurePosixPath(relative).parts[:-1]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError(f"Staging path contains a symbolic link: {current}")
    return target


def _ensure_safe_destination(target: Path, allowed_root: Path) -> None:
    root = allowed_root.resolve()
    current = target.parent
    chain = []
    while current != current.parent:
        chain.append(current)
        if current == allowed_root or current == root:
            break
        current = current.parent
    for item in reversed(chain):
        if item.exists() and item.is_symlink():
            raise QwenProfileImportError(f"Refusing to write through a symbolic link: {item}")
    resolved = target.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise QwenProfileImportError(f"Import destination escapes application storage: {target}") from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _existing_asset_hashes(record: dict[str, object]) -> dict[str, str]:
    profile = _profile_from_bundle_record(record)
    hashes: dict[str, str] = {}
    for key in ("sample_path", "qwen_anchor_path"):
        value = getattr(profile, key, None)
        if not value:
            continue
        path = Path(str(value)).expanduser()
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f"Existing profile asset is missing or unsafe: {path}")
        hashes[key] = _sha256_file(path)

    if str(profile.qwen_mode or "custom").casefold() == "clone" and profile.sample_path:
        sample_path = Path(profile.sample_path).expanduser()
        sidecars = sorted(
            (
                path for path in sample_path.parent.iterdir()
                if path != sample_path
                and path.suffix.casefold() in _AUDIO_EXTENSIONS
                and path.is_file()
                and not path.is_symlink()
            ),
            key=lambda item: item.name.casefold(),
        )
        for index, path in enumerate(sidecars, start=1):
            hashes[f"clone_original_{index:03d}"] = _sha256_file(path)

    if (
        str(profile.qwen_mode or "custom").casefold() == "design"
        and not profile.qwen_anchor_path
    ):
        from app.tts.expression import default_voice_design_anchor_text

        anchor_path = qwen_design_anchor_cache_path(
            runtimes_root() / "qwen3-tts",
            speaker=profile.voice_id,
            language=profile.language or "English",
            instruct=profile.qwen_prompt or profile.notes,
            seed=profile.qwen_seed,
            anchor_text=profile.qwen_anchor_text
            or default_voice_design_anchor_text(profile.language),
            profile_id=profile.qwen_profile_id,
            style="neutral",
        )
        if anchor_path.is_file() and not anchor_path.is_symlink():
            hashes["derived_voice_identity_anchor"] = _sha256_file(anchor_path)
    return hashes


def _existing_revision_id(record: dict[str, object]) -> str | None:
    try:
        profile = _profile_from_bundle_record(record)
        if profile.provider != "qwen-character" or not profile.qwen_profile_id:
            return None
        require_supported_qwen_profile_schema(profile)
        return qwen_profile_revision_id(profile, _existing_asset_hashes(record))
    except (OSError, RuntimeError, TypeError, ValueError):
        return None


def _semantic_fingerprint(record: dict[str, object], asset_hashes: dict[str, str]) -> str:
    normalized = dict(record)
    normalized.pop("qwen_profile_id", None)
    normalized.pop("qwen_profile_schema_version", None)
    normalized.pop("sample_path", None)
    normalized.pop("qwen_anchor_path", None)
    payload = {
        "record": normalized,
        "assets": dict(sorted(asset_hashes.items())),
    }
    return _sha256_bytes(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    )


def _bundle_asset_hashes(entry: dict[str, object]) -> dict[str, str]:
    return {
        str(asset["revision_key"]): str(asset["sha256"])
        for asset in entry.get("assets", [])
        if isinstance(asset, dict)
    }


def _destination_compatibility(profile_doc: dict[str, object]) -> dict[str, object]:
    from app.tts.qwen_character_runtime import model_installed, runtime_ready

    requirement_doc = profile_doc.get("model_requirements")
    if not isinstance(requirement_doc, dict):
        raise QwenProfileImportError("The bundle profile has no model-compatibility contract.")

    models: list[dict[str, object]] = []
    role_ready: list[bool] = []
    missing_exact: list[str] = []
    for requirement in requirement_doc.get("required_models", []):
        if not isinstance(requirement, dict):
            raise QwenProfileImportError("The bundle contains malformed model-role requirements.")
        role = str(requirement.get("role") or "unknown")
        exact = requirement.get("required_model_kind") or requirement.get("selected_source_model_kind")
        allowed = requirement.get("allowed_model_kinds")
        candidates = [str(exact)] if exact else [
            str(item) for item in allowed if isinstance(item, str)
        ] if isinstance(allowed, list) else []
        if not candidates:
            raise QwenProfileImportError(f"The bundle has no allowed model variants for role '{role}'.")
        states = {}
        for kind in candidates:
            try:
                states[kind] = bool(model_installed(kind))
            except (KeyError, OSError, RuntimeError):
                states[kind] = False
        available = [kind for kind, ready in states.items() if ready]
        ready = bool(available)
        role_ready.append(ready)
        if exact and not states.get(str(exact), False):
            missing_exact.append(str(exact))
        models.append({
            "role": role,
            "required_model_kind": str(exact) if exact else None,
            "allowed_model_kinds": candidates,
            "installed": states,
            "available_variants": available,
            "ready": ready,
            "exact_source_variant_ready": bool(states.get(str(exact), False)) if exact else None,
        })
    try:
        qwen_runtime_ready = bool(runtime_ready())
    except Exception:
        qwen_runtime_ready = False
    try:
        destination_backend = get_qwen_backend_preference()
    except Exception:
        destination_backend = "automatic"
    return {
        "models": models,
        "model_roles_ready": all(role_ready),
        "missing_exact_source_models": missing_exact,
        "runtime_ready": qwen_runtime_ready,
        "destination_backend_preference": destination_backend,
        "source_backend_is_not_applied": True,
    }


def _read_bundle_documents(bundle_path: str | Path):
    path = Path(bundle_path).expanduser()
    inspection = inspect_qwen_profile_bundle(path)
    with zipfile.ZipFile(path, "r") as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        documents = []
        for entry in manifest["profiles"]:
            profile_doc = json.loads(archive.read(str(entry["profile_path"])).decode("utf-8"))
            documents.append((entry, profile_doc))
    if len(documents) != inspection["profile_count"]:
        raise QwenProfileImportError("The bundle profile count changed after integrity validation.")
    return path, inspection, manifest, documents


def _profile_index(records: list[dict[str, object]]):
    by_id: dict[str, dict[str, object]] = {}
    by_name: dict[str, list[dict[str, object]]] = {}
    semantic: dict[str, list[dict[str, object]]] = {}
    for record in records:
        name = str(record.get("name") or "").strip()
        if name:
            by_name.setdefault(name.casefold(), []).append(record)
        if record.get("provider") != "qwen-character":
            continue
        profile_id = str(record.get("qwen_profile_id") or "").strip()
        if profile_id:
            if profile_id in by_id:
                raise QwenProfileImportError(
                    f"The saved catalogue contains duplicate Qwen profile ID '{profile_id}'. "
                    "Repair the existing catalogue before importing another bundle."
                )
            by_id[profile_id] = record
        try:
            fingerprint = _semantic_fingerprint(record, _existing_asset_hashes(record))
        except (OSError, RuntimeError, TypeError, ValueError):
            continue
        semantic.setdefault(fingerprint, []).append(record)
    return by_id, by_name, semantic


def _build_plan(
    bundle_path: Path,
    inspection: dict[str, object],
    manifest: dict[str, object],
    documents: list[tuple[dict[str, object], dict[str, object]]],
    records: list[dict[str, object]],
) -> dict[str, object]:
    by_id, by_name, semantic = _profile_index(records)
    incoming_names: dict[str, list[str]] = {}
    for incoming_entry, incoming_doc in documents:
        incoming_name = str(incoming_doc["profile_record"].get("name") or "").strip()
        if incoming_name:
            incoming_names.setdefault(incoming_name.casefold(), []).append(str(incoming_entry["profile_id"]))
    profiles = []
    for entry, profile_doc in documents:
        record = profile_doc["profile_record"]
        profile_id = str(entry["profile_id"])
        name = str(record.get("name") or "").strip()
        incoming_revision = str(entry["revision_id"])
        existing = by_id.get(profile_id)
        current_revision = _existing_revision_id(existing) if existing else None
        name_matches = [
            item for item in by_name.get(name.casefold(), [])
            if str(item.get("qwen_profile_id") or "") != profile_id
        ]
        incoming_name_matches = [
            other_id for other_id in incoming_names.get(name.casefold(), [])
            if other_id != profile_id
        ]
        semantic_matches = [
            item for item in semantic.get(
                _semantic_fingerprint(record, _bundle_asset_hashes(entry)), []
            )
            if str(item.get("qwen_profile_id") or "") != profile_id
        ]
        if existing and current_revision == incoming_revision:
            classification = "already_present"
            default_action = "skip"
        elif existing:
            classification = "revision_conflict"
            default_action = "keep_both"
        elif semantic_matches:
            classification = "semantic_duplicate"
            default_action = "requires_choice"
        elif name_matches or incoming_name_matches:
            classification = "name_collision"
            default_action = "requires_choice"
        else:
            classification = "new_profile"
            default_action = "import"

        compatibility = _destination_compatibility(profile_doc)
        asset_state = profile_doc.get("asset_state", {})
        missing_anchor = (
            str(profile_doc.get("profile_record", {}).get("qwen_mode") or "").casefold() == "design"
            and isinstance(asset_state, dict)
            and asset_state.get("voice_design_anchor") == "not_found_in_source_cache"
        )
        warnings = []
        if not compatibility["runtime_ready"]:
            warnings.append("The Qwen runtime is not ready on this PC; importing does not install it.")
        if not compatibility["model_roles_ready"]:
            warnings.append("One or more required Qwen model roles are not installed on this PC.")
        if compatibility["missing_exact_source_models"]:
            warnings.append(
                "The exact source model pairing is not installed. An alternative is reported separately "
                "and will never be selected automatically during import."
            )
        if missing_anchor:
            warnings.append(
                "The source bundle did not contain the VoiceDesign neutral anchor. Its original state is "
                "unknown; import will not generate a replacement."
            )
        if record.get("qwen_mode") == "clone" and record.get("authorized") is not True:
            warnings.append("Clone authorization is not confirmed in the source profile; the saved value is preserved.")
        profiles.append({
            "profile_id": profile_id,
            "name": name,
            "mode": str(record.get("qwen_mode") or "custom"),
            "revision_id": incoming_revision,
            "current_revision_id": current_revision,
            "classification": classification,
            "default_action": default_action,
            "name_collision_profile_ids": [
                str(item.get("qwen_profile_id") or "") for item in name_matches
            ],
            "incoming_name_collision_profile_ids": incoming_name_matches,
            "semantic_duplicate_profile_ids": [
                str(item.get("qwen_profile_id") or "") for item in semantic_matches
            ],
            "asset_count": len(entry.get("assets", [])),
            "asset_state": asset_state,
            "missing_voice_design_anchor_acknowledgement": bool(missing_anchor),
            "compatibility": compatibility,
            "warnings": warnings,
        })
    return {
        "format": BUNDLE_FORMAT,
        "bundle_format_version": BUNDLE_FORMAT_VERSION,
        "profile_schema_version": CURRENT_QWEN_PROFILE_SCHEMA_VERSION,
        "bundle_path": str(bundle_path),
        "integrity_verified": bool(inspection["integrity_verified"]),
        "profile_count": len(profiles),
        "profiles": profiles,
    }


def plan_qwen_profiles_import(bundle_path: str | Path) -> dict[str, object]:
    """Validate a bundle and report collisions and destination model compatibility."""
    recover_interrupted_qwen_profile_imports()
    path, inspection, manifest, documents = _read_bundle_documents(bundle_path)
    with _catalogue_lock():
        records = _read_catalogue_records()
        return _build_plan(path, inspection, manifest, documents, records)


def _resolution_for(profile_id: str, resolutions: dict[str, object] | None) -> dict[str, object]:
    raw = (resolutions or {}).get(profile_id)
    if raw is None:
        return {}
    if isinstance(raw, str):
        return {"action": raw}
    if isinstance(raw, dict):
        return dict(raw)
    raise QwenProfileImportConflict(
        f"Import resolution for profile '{profile_id}' must be an action or an action object.",
        {"profile_id": profile_id},
    )


def _decide(
    profile_plan: dict[str, object],
    resolution: dict[str, object],
) -> tuple[str, str | None]:
    classification = str(profile_plan["classification"])
    action = str(resolution.get("action") or "")
    new_name = str(resolution.get("new_name") or "").strip() or None
    if classification == "already_present":
        return "skip", None
    if classification == "new_profile":
        if action and action not in {"import", "skip"}:
            raise QwenProfileImportConflict(
                f"Invalid action '{action}' for new profile '{profile_plan['name']}'.",
                profile_plan,
            )
        return action or "import", None
    if classification == "revision_conflict":
        action = action or "keep_both"
        if action not in {"keep_both", "replace", "skip"}:
            raise QwenProfileImportConflict(
                f"Profile ID '{profile_plan['profile_id']}' has a different saved revision. "
                "Choose keep_both, replace, or skip.",
                profile_plan,
            )
        return action, None
    if classification == "semantic_duplicate":
        if action not in {"keep_both", "skip"}:
            raise QwenProfileImportConflict(
                f"Profile '{profile_plan['name']}' has the same profile payload as another saved ID. "
                "Choose keep_both or skip explicitly.",
                profile_plan,
            )
        if action == "keep_both" and (
            profile_plan.get("name_collision_profile_ids")
            or profile_plan.get("incoming_name_collision_profile_ids")
        ):
            if not new_name:
                raise QwenProfileImportConflict(
                    f"The duplicate profile name '{profile_plan['name']}' is already in use. "
                    "Provide a new_name to keep both profiles.",
                    profile_plan,
                )
            return "rename", new_name
        return action, None
    if classification == "name_collision":
        if action not in {"keep_both", "rename", "skip"}:
            raise QwenProfileImportConflict(
                f"Profile name '{profile_plan['name']}' already exists under another profile ID. "
                "Choose keep_both/rename with a new_name, or skip.",
                profile_plan,
            )
        if action == "skip":
            return "skip", None
        if not new_name:
            raise QwenProfileImportConflict(
                f"A new display name is required to keep both profiles named '{profile_plan['name']}'.",
                profile_plan,
            )
        return "rename", new_name
    raise QwenProfileImportConflict(
        f"Unknown collision classification '{classification}'.",
        profile_plan,
    )


def _transaction_dir(transaction_id: str) -> Path:
    return voices_root() / _TRANSACTION_ROOT_NAME / transaction_id


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if json.loads(temporary.read_text(encoding="utf-8")) != value:
            raise OSError(f"JSON verification failed for {path.name}.")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _journal_path(transaction_dir: Path) -> Path:
    return transaction_dir / "journal.json"


def _write_journal(transaction_dir: Path, journal: dict[str, object]) -> None:
    _write_json_atomic(_journal_path(transaction_dir), journal)


def _allowed_storage_roots() -> tuple[Path, Path]:
    return voices_root().resolve(), runtimes_root().resolve()


def _path_under_storage_roots(raw_path: str) -> bool:
    candidate = Path(raw_path)
    try:
        resolved = candidate.resolve(strict=False)
    except OSError:
        return False
    for root in _allowed_storage_roots():
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _remove_created_path(raw_path: str) -> None:
    if not _path_under_storage_roots(raw_path):
        raise QwenProfileImportError(
            f"Recovery refused to remove a path outside application storage: {raw_path}"
        )
    path = Path(raw_path)
    if path.is_symlink():
        raise QwenProfileImportError(
            f"Recovery refused to follow a symbolic link: {raw_path}"
        )
    try:
        if path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            path.rmdir()
    except OSError as exc:
        raise QwenProfileImportError(
            f"Could not roll back imported file '{path.name}': {exc}"
        ) from exc


def _restore_catalogue_from_journal(transaction_dir: Path, journal: dict[str, object]) -> None:
    catalogue = profiles_file()
    if journal.get("catalogue_existed") is True:
        backup = transaction_dir / "catalogue.before.json"
        if not backup.is_file():
            raise QwenProfileImportError(
                f"Import recovery is missing its catalogue backup: {backup}"
            )
        try:
            records = json.loads(backup.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise QwenProfileImportError(
                f"Import recovery cannot read its catalogue backup: {exc}"
            ) from exc
        if not isinstance(records, list):
            raise QwenProfileImportError("Import recovery found a malformed catalogue backup.")
        _write_catalogue_records(records)
    else:
        catalogue.unlink(missing_ok=True)


def _recover_transaction_locked(transaction_dir: Path) -> bool:
    journal_path = _journal_path(transaction_dir)
    if not journal_path.is_file():
        shutil.rmtree(transaction_dir, ignore_errors=True)
        return True
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QwenProfileImportError(
            f"An interrupted Qwen profile import has an unreadable journal at {journal_path}: {exc}"
        ) from exc
    if not isinstance(journal, dict):
        raise QwenProfileImportError(f"An interrupted Qwen profile import has a malformed journal: {journal_path}")
    if journal.get("state") == "complete":
        shutil.rmtree(transaction_dir, ignore_errors=True)
        return True
    _restore_catalogue_from_journal(transaction_dir, journal)
    created = journal.get("created_paths", [])
    if not isinstance(created, list):
        raise QwenProfileImportError("Import recovery journal contains an invalid created-path list.")
    for raw_path in reversed(created):
        if isinstance(raw_path, str):
            _remove_created_path(raw_path)
    shutil.rmtree(transaction_dir, ignore_errors=True)
    return True


def _recover_interrupted_locked() -> int:
    root = voices_root() / _TRANSACTION_ROOT_NAME
    if not root.is_dir():
        return 0
    recovered = 0
    for transaction_dir in sorted(root.iterdir(), key=lambda item: item.name):
        if transaction_dir.is_symlink():
            raise QwenProfileImportError(
                f"Import recovery found a symbolic link in its transaction directory: {transaction_dir}"
            )
        if not transaction_dir.is_dir():
            continue
        _recover_transaction_locked(transaction_dir)
        recovered += 1
    try:
        root.rmdir()
    except OSError:
        pass
    return recovered


def recover_interrupted_qwen_profile_imports() -> int:
    """Roll back any incomplete import before the saved catalogue is read."""
    with _catalogue_lock():
        return _recover_interrupted_locked()


def _register_created_path(
    transaction_dir: Path,
    journal: dict[str, object],
    target: Path,
) -> None:
    raw_path = str(target.absolute())
    if not _path_under_storage_roots(raw_path):
        raise QwenProfileImportError(
            f"Import attempted to create a file outside application storage: {target}"
        )
    created = journal.setdefault("created_paths", [])
    if raw_path not in created:
        created.append(raw_path)
        _write_journal(transaction_dir, journal)


def _stage_bundle_payloads(
    archive: zipfile.ZipFile,
    manifest: dict[str, object],
    transaction_dir: Path,
) -> dict[str, Path]:
    stage_root = transaction_dir / "stage"
    stage_root.mkdir(parents=True, exist_ok=True)
    expected_files = manifest["integrity"]["files"]
    staged: dict[str, Path] = {}
    total = 0
    for archive_name, expected_digest in sorted(expected_files.items()):
        target = _safe_child_path(stage_root, str(archive_name))
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        try:
            with archive.open(str(archive_name), "r") as source, target.open("xb") as output:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    size += len(block)
                    total += len(block)
                    if size > MAX_ASSET_BYTES or total > MAX_TOTAL_UNCOMPRESSED_BYTES:
                        raise QwenProfileImportError("The staged bundle exceeds the verified archive size limits.")
                    digest.update(block)
                    output.write(block)
                output.flush()
                os.fsync(output.fileno())
        except OSError as exc:
            raise QwenProfileImportError(f"Could not stage bundle member '{archive_name}': {exc}") from exc
        if digest.hexdigest() != expected_digest:
            raise QwenProfileImportError(f"Bundle member changed after preflight: {archive_name}")
        staged[str(archive_name)] = target
    return staged


def _safe_asset_filename(value: str, fallback: str) -> str:
    name = Path(str(value or "")).name
    if not name or name in {".", ".."} or name != str(value or ""):
        name = fallback
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name or fallback


def _asset_destinations(
    profile: VoiceProfile,
    entry: dict[str, object],
    revision_id: str,
) -> dict[str, Path]:
    profile_id = str(profile.qwen_profile_id or "")
    if not _PROFILE_ID_RE.fullmatch(profile_id):
        raise QwenProfileImportError(f"Imported profile has an invalid stable ID: {profile_id!r}")
    profile_asset_dir = (
        voices_root() / _PROFILE_ASSET_ROOT_NAME / profile_id / revision_id
    )
    destinations: dict[str, Path] = {}
    for index, asset in enumerate(entry.get("assets", []), start=1):
        binding = str(asset.get("binding") or "")
        role = str(asset.get("role") or "")
        archive_name = str(asset.get("archive_path") or "")
        suffix = Path(archive_name).suffix.lower()
        if binding == "sample_path":
            filename = "reference.wav" if profile.qwen_mode == "clone" else f"profile-sample{suffix}"
            destinations[archive_name] = profile_asset_dir / filename
        elif binding == "qwen_anchor_path":
            destinations[archive_name] = profile_asset_dir / "voicedesign-anchor-explicit.wav"
        elif binding == "worker-derived-neutral-anchor":
            identity = asset.get("identity")
            if not isinstance(identity, dict):
                raise QwenProfileImportError("The derived VoiceDesign anchor has no identity metadata.")
            if identity.get("expression_bank_version") != QWEN_EXPRESSION_BANK_VERSION:
                raise QwenProfileImportError(
                    "The VoiceDesign anchor was generated by an unsupported expression-bank version. "
                    "It cannot be installed as the current voice identity."
                )
            from app.tts.expression import default_voice_design_anchor_text

            destinations[archive_name] = qwen_design_anchor_cache_path(
                runtimes_root() / "qwen3-tts",
                speaker=profile.voice_id,
                language=profile.language or "English",
                instruct=profile.qwen_prompt or profile.notes,
                seed=profile.qwen_seed,
                anchor_text=profile.qwen_anchor_text
                or default_voice_design_anchor_text(profile.language),
                profile_id=profile_id,
                style="neutral",
            )
        elif binding == "clone-reference-original-sidecar":
            source_name = str(asset.get("source_filename") or Path(archive_name).name)
            filename = _safe_asset_filename(source_name, f"clone-original-{index:03d}{suffix}")
            if filename.casefold() in {"reference.wav", "profile-sample.wav", "voicedesign-anchor-explicit.wav"}:
                filename = f"original-{index:03d}-{filename}"
            destinations[archive_name] = profile_asset_dir / filename
        else:
            raise QwenProfileImportError(
                f"Unsupported Qwen profile asset binding '{binding}' in the bundle."
            )
    return destinations


def _storage_root_for(destination: Path) -> Path:
    resolved = destination.resolve(strict=False)
    for root in (voices_root(), runtimes_root()):
        try:
            resolved.relative_to(root.resolve())
            return root
        except ValueError:
            continue
    raise QwenProfileImportError(f"Import destination is outside application storage: {destination}")


def _copy_staged_asset(
    archive_name: str,
    staged: dict[str, Path],
    destination: Path,
    expected_digest: str,
    transaction_dir: Path,
    journal: dict[str, object],
) -> Path:
    destination_root = _storage_root_for(destination)
    _ensure_safe_destination(destination, destination_root)
    if not destination.parent.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_symlink() or not destination.is_file():
            raise QwenProfileImportError(f"Import destination already exists and is not a regular file: {destination}")
        if _sha256_file(destination) == expected_digest:
            return destination
        raise QwenProfileImportError(
            f"Import refused to overwrite an existing profile asset with different bytes: {destination.name}"
        )
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.importing")
    _register_created_path(transaction_dir, journal, temporary)
    _register_created_path(transaction_dir, journal, destination)
    digest = hashlib.sha256()
    size = 0
    try:
        with staged[archive_name].open("rb") as source, temporary.open("xb") as output:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
                size += len(block)
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
        if digest.hexdigest() != expected_digest:
            raise QwenProfileImportError(f"Staged asset SHA-256 changed before installation: {archive_name}")
        os.replace(temporary, destination)
        return destination
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _write_incoming_revision_snapshot(
    profile_id: str,
    revision_id: str,
    entry: dict[str, object],
    profile_doc: dict[str, object],
    staged: dict[str, Path],
    asset_destinations: dict[str, Path],
    transaction_dir: Path,
    journal: dict[str, object],
    bundle_sha256: str,
) -> Path:
    revision_dir = voices_root() / _REVISION_ROOT_NAME / profile_id
    revision_path = revision_dir / f"{revision_id}.json"
    if revision_path.exists():
        try:
            existing = json.loads(revision_path.read_text(encoding="utf-8"))
            if existing.get("revision_id") == revision_id:
                for asset in existing.get("assets", []):
                    relative = str(asset.get("snapshot_path") or "")
                    if not _is_safe_archive_path(relative):
                        raise QwenProfileImportError("An existing revision snapshot has an unsafe asset path.")
                    stored = revision_path.parent / PurePosixPath(relative)
                    if (
                        not stored.is_file()
                        or stored.is_symlink()
                        or _sha256_file(stored) != str(asset.get("sha256") or "")
                    ):
                        raise QwenProfileImportError(
                            f"An existing revision snapshot has a missing or corrupt asset: {stored.name}"
                        )
                return revision_path
        except (OSError, json.JSONDecodeError) as exc:
            raise QwenProfileImportError(
                f"An existing revision snapshot cannot be verified: {exc}"
            ) from exc
        raise QwenProfileImportError(
            f"A revision snapshot already exists but does not match '{revision_id}'."
        )
    revision_payload = {
        "profile_id": profile_id,
        "revision_id": revision_id,
        "profile_doc": profile_doc,
        "assets": [
            {
                **dict(asset),
                "snapshot_path": str(Path("assets") / Path(str(asset["archive_path"])).name),
            }
            for asset in entry.get("assets", [])
        ],
        "source_bundle_sha256": bundle_sha256,
        "saved_at": _utc_now(),
        "snapshot_only": True,
    }
    for asset in entry.get("assets", []):
        archive_name = str(asset["archive_path"])
        filename = Path(archive_name).name
        target = revision_dir / "assets" / filename
        if target.exists():
            raise QwenProfileImportError(
                f"Revision snapshot asset already exists: {target.name}"
            )
        _copy_staged_asset(
            archive_name, staged, target, str(asset["sha256"]),
            transaction_dir, journal,
        )
    if not revision_path.parent.exists():
        revision_path.parent.mkdir(parents=True, exist_ok=True)
    _register_created_path(transaction_dir, journal, revision_path)
    _write_json_atomic(revision_path, revision_payload)
    return revision_path


def _snapshot_current_profile(
    current_record: dict[str, object],
    transaction_dir: Path,
    journal: dict[str, object],
) -> Path:
    profile = _profile_from_bundle_record(current_record)
    if profile.provider != "qwen-character" or not profile.qwen_profile_id:
        raise QwenProfileImportError(
            "The current profile cannot be safely replaced because it has no stable Qwen profile ID."
        )
    revision_id = _existing_revision_id(current_record)
    if not revision_id:
        raise QwenProfileImportError(
            f"Cannot replace '{profile.name}': its current profile revision or referenced assets "
            "cannot be verified for backup."
        )
    target_dir = voices_root() / _REVISION_ROOT_NAME / profile.qwen_profile_id
    target = target_dir / f"{revision_id}.ryuvoice"
    if target.exists():
        try:
            inspected = inspect_qwen_profile_bundle(target)
            if inspected.get("profiles", [{}])[0].get("revision_id") == revision_id:
                return target
        except Exception as exc:
            raise QwenProfileImportError(
                f"The existing backup for '{profile.name}' is not valid: {exc}"
            ) from exc
    target_dir.mkdir(parents=True, exist_ok=True)
    _register_created_path(transaction_dir, journal, target)
    try:
        export_qwen_profiles_bundle(
            [profile],
            target,
            source_model_preference="auto",
            overwrite=False,
        )
    except Exception as exc:
        raise QwenProfileImportError(
            f"Could not create a verified backup of '{profile.name}' before replacement: {exc}"
        ) from exc
    inspected = inspect_qwen_profile_bundle(target)
    if inspected.get("profile_count") != 1 or inspected["profiles"][0].get("revision_id") != revision_id:
        raise QwenProfileImportError(
            f"The replacement backup for '{profile.name}' did not preserve its exact revision."
        )
    return target


def _prepare_active_record(
    profile_doc: dict[str, object],
    entry: dict[str, object],
    asset_destinations: dict[str, Path],
    new_name: str | None,
) -> dict[str, object]:
    record = dict(profile_doc["profile_record"])
    record["sample_path"] = None
    record["qwen_anchor_path"] = None
    for asset in entry.get("assets", []):
        archive_name = str(asset["archive_path"])
        binding = str(asset["binding"])
        target = asset_destinations[archive_name]
        if binding == "sample_path":
            record["sample_path"] = str(target)
        elif binding == "qwen_anchor_path":
            record["qwen_anchor_path"] = str(target)
        elif binding == "worker-derived-neutral-anchor":
            # The runtime computes this path from the same saved identity fields;
            # qwen_anchor_path intentionally remains unset for derived anchors.
            pass
    if new_name:
        record["name"] = new_name
    profile = _profile_from_bundle_record(record)
    require_supported_qwen_profile_schema(profile)
    if profile.qwen_profile_id != entry["profile_id"]:
        raise QwenProfileImportError("The imported profile ID changed while mapping its local asset paths.")
    return record


def _write_import_info(
    profile_id: str,
    revision_id: str,
    profile_doc: dict[str, object],
    profile_plan: dict[str, object],
    bundle_sha256: str,
    warnings: list[str],
    transaction_dir: Path,
    journal: dict[str, object],
) -> Path:
    directory = voices_root() / _PROFILE_ASSET_ROOT_NAME / profile_id / revision_id
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "import-info.json"
    payload = {
        "profile_id": profile_id,
        "source_revision_id": revision_id,
        "source_bundle_sha256": bundle_sha256,
        "imported_at": _utc_now(),
        "source_model_requirements": profile_doc.get("model_requirements"),
        "source_asset_state": profile_doc.get("asset_state"),
        "destination_compatibility": profile_plan.get("compatibility"),
        "warnings": list(warnings),
    }
    if destination.exists():
        try:
            existing = json.loads(destination.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise QwenProfileImportError(
                f"Existing import metadata cannot be verified: {destination}"
            ) from exc
        if (
            existing.get("profile_id") == profile_id
            and existing.get("source_revision_id") == revision_id
            and existing.get("source_bundle_sha256") == bundle_sha256
        ):
            return destination
        raise QwenProfileImportError(
            f"Import metadata already exists for a different source revision: {destination}"
        )

    fd, temporary_name = tempfile.mkstemp(
        prefix=".import-info.", suffix=".tmp", dir=str(directory)
    )
    os.close(fd)
    temporary = Path(temporary_name)
    _register_created_path(transaction_dir, journal, temporary)
    _register_created_path(transaction_dir, journal, destination)
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if json.loads(temporary.read_text(encoding="utf-8")) != payload:
            raise OSError("Import metadata verification failed.")
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return destination


def _single_profile_warnings(profile_plan: dict[str, object], allow_missing_anchor: bool) -> list[str]:
    warnings = list(profile_plan.get("warnings", []))
    if profile_plan.get("missing_voice_design_anchor_acknowledgement"):
        if not allow_missing_anchor:
            raise QwenProfileImportConflict(
                "The VoiceDesign bundle has no cached neutral anchor. Confirm the missing-anchor warning "
                "explicitly before importing this profile without its existing acoustic anchor.",
                profile_plan,
            )
        warnings.append(
            "Imported without a cached VoiceDesign anchor by explicit acknowledgement; the app may need "
            "to prepare an anchor during a later preview or generation."
        )
    return warnings


def import_qwen_profiles_bundle(
    bundle_path: str | Path,
    *,
    resolutions: dict[str, object] | None = None,
    allow_missing_voicedesign_anchor: bool = False,
    _fail_after_asset_writes: int | None = None,
    _fail_after_catalogue_commit: bool = False,
) -> QwenProfileImportResult:
    """Import all selected profiles as one recoverable catalogue transaction.

    Resolution objects are keyed by stable profile ID. Supported actions are:
      - revision conflict: keep_both (default), replace, or skip;
      - semantic duplicate: keep_both or skip;
      - same-name collision: keep_both/rename with an explicit new_name, or skip.
    """
    recover_interrupted_qwen_profile_imports()
    path, inspection, manifest, documents = _read_bundle_documents(bundle_path)
    bundle_sha256 = _sha256_file(path)
    transaction_id = uuid.uuid4().hex
    transaction_dir = _transaction_dir(transaction_id)
    compatibility_results: list[dict[str, object]] = []
    imported_ids: list[str] = []
    stored_revisions: list[str] = []
    skipped_ids: list[str] = []
    renamed: dict[str, str] = {}
    warnings: list[str] = []
    writes_done = 0

    with _catalogue_lock():
        _recover_interrupted_locked()
        original_records = _read_catalogue_records()
        plan = _build_plan(path, inspection, manifest, documents, original_records)
        plan_by_id = {str(item["profile_id"]): item for item in plan["profiles"]}
        operations = []
        for entry, profile_doc in documents:
            profile_id = str(entry["profile_id"])
            profile_plan = plan_by_id[profile_id]
            resolution = _resolution_for(profile_id, resolutions)
            action, new_name = _decide(profile_plan, resolution)
            profile_warnings = _single_profile_warnings(
                profile_plan, allow_missing_voicedesign_anchor
            )
            warnings.extend(profile_warnings)
            compatibility_results.append({
                "profile_id": profile_id,
                **profile_plan["compatibility"],
                "warnings": profile_warnings,
            })
            if action == "skip":
                skipped_ids.append(profile_id)
                continue
            if action == "rename":
                if not new_name or len(new_name) > 160:
                    raise QwenProfileImportConflict(
                        f"The replacement display name for '{profile_plan['name']}' is empty or too long.",
                        profile_plan,
                    )
                renamed[profile_id] = new_name
            if action == "replace":
                current = next(
                    item for item in original_records
                    if item.get("provider") == "qwen-character"
                    and str(item.get("qwen_profile_id") or "") == profile_id
                )
            else:
                current = None
            operations.append({
                "entry": entry,
                "profile_doc": profile_doc,
                "action": action,
                "new_name": new_name,
                "current": current,
                "profile_plan": profile_plan,
                "profile_warnings": profile_warnings,
            })

        # Validate all selected display names together, including two profiles
        # from the same bundle, before the staging transaction begins.
        from collections import Counter
        reserved_names = Counter(
            str(item.get("name") or "").strip().casefold()
            for item in original_records
        )
        for operation in operations:
            if operation["action"] == "replace" and operation["current"]:
                old_name = str(operation["current"].get("name") or "").strip().casefold()
                if old_name:
                    reserved_names[old_name] -= 1
            if operation["action"] == "keep_both" and operation["profile_plan"]["classification"] == "revision_conflict":
                continue
            name_to_add = operation["new_name"] or str(operation["profile_plan"]["name"])
            name_key = name_to_add.strip().casefold()
            if reserved_names[name_key] > 0:
                raise QwenProfileImportConflict(
                    f"The selected destination name '{name_to_add}' is already in use. "
                    "Choose a distinct name or skip the incoming profile.",
                    operation["profile_plan"],
                )
            reserved_names[name_key] += 1

        if not operations:
            return QwenProfileImportResult(
                tuple(imported_ids), tuple(stored_revisions), tuple(skipped_ids),
                renamed, tuple(dict.fromkeys(warnings)), tuple(compatibility_results),
            )

        transaction_dir.mkdir(parents=True, exist_ok=False)
        catalogue = profiles_file()
        catalogue_existed = catalogue.is_file()
        if catalogue_existed:
            backup = transaction_dir / "catalogue.before.json"
            shutil.copy2(catalogue, backup)
            with backup.open("rb") as handle:
                os.fsync(handle.fileno())
        journal: dict[str, object] = {
            "transaction_id": transaction_id,
            "state": "prepared",
            "catalogue_path": str(catalogue),
            "catalogue_existed": catalogue_existed,
            "created_paths": [],
            "bundle_sha256": bundle_sha256,
            "started_at": _utc_now(),
        }
        _write_journal(transaction_dir, journal)
        try:
            with zipfile.ZipFile(path, "r") as archive:
                staged = _stage_bundle_payloads(archive, manifest, transaction_dir)
                new_records = list(original_records)
                for operation in operations:
                    entry = operation["entry"]
                    profile_doc = operation["profile_doc"]
                    profile_id = str(entry["profile_id"])
                    revision_id = str(entry["revision_id"])
                    profile = _profile_from_bundle_record(profile_doc["profile_record"])
                    asset_destinations = _asset_destinations(profile, entry, revision_id)

                    if operation["action"] == "keep_both" and operation["profile_plan"]["classification"] == "revision_conflict":
                        stored = _write_incoming_revision_snapshot(
                            profile_id,
                            revision_id,
                            entry,
                            profile_doc,
                            staged,
                            asset_destinations,
                            transaction_dir,
                            journal,
                            bundle_sha256,
                        )
                        stored_revisions.append(f"{profile_id}:{revision_id}")
                        continue

                    if operation["action"] == "replace":
                        current = operation["current"]
                        backup_path = _snapshot_current_profile(current, transaction_dir, journal)
                        stored_revisions.append(
                            f"{profile_id}:{_existing_revision_id(current)}"
                        )
                        new_records = [
                            item for item in new_records
                            if not (
                                item.get("provider") == "qwen-character"
                                and str(item.get("qwen_profile_id") or "") == profile_id
                            )
                        ]

                    record = _prepare_active_record(
                        profile_doc,
                        entry,
                        asset_destinations,
                        operation["new_name"],
                    )
                    for asset in entry.get("assets", []):
                        archive_name = str(asset["archive_path"])
                        target = asset_destinations[archive_name]
                        destination_root = (
                            runtimes_root() if str(target).startswith(str(runtimes_root()))
                            else voices_root()
                        )
                        _ensure_safe_destination(target, destination_root)
                        _copy_staged_asset(
                            archive_name,
                            staged,
                            target,
                            str(asset["sha256"]),
                            transaction_dir,
                            journal,
                        )
                        writes_done += 1
                        if _fail_after_asset_writes is not None and writes_done >= _fail_after_asset_writes:
                            raise OSError("Injected D3 failure after asset installation for rollback testing.")
                    _write_import_info(
                        profile_id,
                        revision_id,
                        profile_doc,
                        operation["profile_plan"],
                        bundle_sha256,
                        operation["profile_warnings"],
                        transaction_dir,
                        journal,
                    )
                    new_records.append(record)
                    imported_ids.append(profile_id)
                    if operation["new_name"]:
                        warnings.append(
                            f"Profile '{operation['profile_plan']['name']}' was imported as '{operation['new_name']}' "
                            "by the selected name-collision resolution."
                        )

                journal["state"] = "catalogue_commit_started"
                journal["target_profile_ids"] = imported_ids
                _write_journal(transaction_dir, journal)
                _write_catalogue_records(new_records)
                journal["state"] = "catalogue_committed"
                _write_journal(transaction_dir, journal)
                if _fail_after_catalogue_commit:
                    raise OSError("Injected D3 failure after catalogue replacement for rollback testing.")
                journal["state"] = "complete"
                journal["completed_at"] = _utc_now()
                _write_journal(transaction_dir, journal)
            shutil.rmtree(transaction_dir, ignore_errors=True)
        except Exception as exc:
            try:
                _recover_transaction_locked(transaction_dir)
            except Exception as rollback_exc:
                raise QwenProfileImportError(
                    f"Qwen profile import failed ({exc}) and automatic rollback also failed ({rollback_exc}). "
                    f"Recovery journal retained at {transaction_dir}."
                ) from rollback_exc
            if isinstance(exc, QwenProfileImportError):
                raise
            raise QwenProfileImportError(
                f"Qwen profile import was rolled back; no partial catalogue update was kept: {exc}"
            ) from exc

    return QwenProfileImportResult(
        tuple(imported_ids),
        tuple(stored_revisions),
        tuple(skipped_ids),
        renamed,
        tuple(dict.fromkeys(warnings)),
        tuple(compatibility_results),
    )
