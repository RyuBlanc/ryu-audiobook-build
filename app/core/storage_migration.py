"""Verified, rollback-capable migration for app-managed storage roots.

This module deliberately never deletes the source tree. Callers own settings/UI
integration and must supply active-job and post-switch validation callbacks.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import uuid
from typing import Callable


class StorageMigrationError(RuntimeError):
    """A storage migration was rejected or could not be completed safely."""


@dataclass(frozen=True)
class MigrationPlan:
    source: Path
    destination: Path
    file_count: int
    total_bytes: int
    free_bytes: int
    staging: Path
    journal: Path


def _resolved(path: Path) -> Path:
    return Path(path).expanduser().resolve(strict=True)


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _walk_files(root: Path) -> list[tuple[Path, str, int]]:
    rows: list[tuple[Path, str, int]] = []
    for folder, dirs, files in os.walk(root, topdown=True, followlinks=False):
        base = Path(folder)
        kept = []
        for name in dirs:
            candidate = base / name
            if candidate.is_symlink():
                raise StorageMigrationError(f"Symbolic link directory is not allowed: {candidate}")
            kept.append(name)
        dirs[:] = kept
        for name in files:
            candidate = base / name
            if candidate.is_symlink():
                raise StorageMigrationError(f"Symbolic link file is not allowed: {candidate}")
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(root).as_posix()
            rows.append((candidate, relative, candidate.stat().st_size))
    rows.sort(key=lambda row: row[1].casefold())
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_journal(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def prepare_migration(
    source: Path,
    destination: Path,
    *,
    reserve_bytes: int = 512 * 1024 * 1024,
    journal_dir: Path | None = None,
    is_busy: Callable[[Path], bool] | None = None,
) -> MigrationPlan:
    """Preflight paths, contents, write access, free space and active-job use."""
    src = _resolved(Path(source))
    if not src.is_dir():
        raise StorageMigrationError("The source storage location is not a directory.")
    dest_input = Path(destination).expanduser()
    if not dest_input.is_absolute():
        raise StorageMigrationError("The destination must be an absolute path.")
    parent = dest_input.parent.resolve(strict=True)
    dest = parent / dest_input.name
    if src == dest or _inside(src, dest) or _inside(dest, src):
        raise StorageMigrationError("Source and destination must not overlap.")
    if dest.exists():
        if dest.is_symlink() or not dest.is_dir():
            raise StorageMigrationError("The destination exists and is not a safe directory.")
        if any(dest.iterdir()):
            raise StorageMigrationError("The destination must be empty before migration.")
    if is_busy and is_busy(src):
        raise StorageMigrationError("An active job is using this storage location.")
    rows = _walk_files(src)
    total = sum(row[2] for row in rows)
    usage = shutil.disk_usage(parent)
    required = total + max(0, int(reserve_bytes))
    if usage.free < required:
        raise StorageMigrationError(
            f"Insufficient destination space: {usage.free} free, {required} required."
        )
    probe = parent / f".ryu-write-probe-{uuid.uuid4().hex}"
    try:
        probe.write_bytes(b"")
    finally:
        probe.unlink(missing_ok=True)
    token = uuid.uuid4().hex
    staging = parent / f".{dest.name}.ryu-migration-{token}.staging"
    journal_root = Path(journal_dir).expanduser() if journal_dir else parent
    journal = journal_root / f"ryu-storage-migration-{token}.json"
    return MigrationPlan(src, dest, len(rows), total, usage.free, staging, journal)


def migrate_storage_root(
    source: Path,
    destination: Path,
    *,
    persist_root: Callable[[Path], None],
    validate_root: Callable[[Path], bool],
    is_busy: Callable[[Path], bool] | None = None,
    progress: Callable[[str, int, int], None] | None = None,
    reserve_bytes: int = 512 * 1024 * 1024,
    journal_dir: Path | None = None,
) -> MigrationPlan:
    """Copy, hash-verify, switch settings, validate, and roll back on any failure.

    The source is intentionally retained for explicit user-confirmed cleanup.
    """
    plan = prepare_migration(
        source, destination, reserve_bytes=reserve_bytes,
        journal_dir=journal_dir, is_busy=is_busy,
    )
    if is_busy and is_busy(plan.source):
        raise StorageMigrationError("An active job started using this storage location.")
    rows = _walk_files(plan.source)
    payload = {
        "schema_version": 1, "state": "copying",
        "source": str(plan.source), "destination": str(plan.destination),
        "staging": str(plan.staging), "file_count": plan.file_count,
        "total_bytes": plan.total_bytes, "verified_files": 0,
        "verified_bytes": 0, "created_at": time.time(),
    }
    _write_journal(plan.journal, payload)
    copied = 0
    try:
        plan.staging.mkdir()
        for index, (source_file, relative, size) in enumerate(rows, 1):
            target = plan.staging.joinpath(*Path(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target)
            if target.stat().st_size != size or _sha256(source_file) != _sha256(target):
                raise StorageMigrationError(f"Integrity verification failed: {relative}")
            copied += size
            payload.update(state="verifying", verified_files=index, verified_bytes=copied)
            _write_journal(plan.journal, payload)
            if progress:
                progress("copying", index, len(rows))
        if len(_walk_files(plan.staging)) != plan.file_count:
            raise StorageMigrationError("Staged file count does not match the source.")
        if sum(row[2] for row in _walk_files(plan.staging)) != plan.total_bytes:
            raise StorageMigrationError("Staged byte count does not match the source.")
        if is_busy and is_busy(plan.source):
            raise StorageMigrationError("An active job started during migration.")
        payload["state"] = "switching"
        _write_journal(plan.journal, payload)
        if plan.destination.exists():
            plan.destination.rmdir()
        os.replace(plan.staging, plan.destination)
        payload["state"] = "validating"
        _write_journal(plan.journal, payload)
        persist_root(plan.destination)
        if not validate_root(plan.destination):
            raise StorageMigrationError("Post-switch inventory validation failed.")
        payload["state"] = "complete_source_retained"
        _write_journal(plan.journal, payload)
        if progress:
            progress("complete", plan.file_count, plan.file_count)
        return plan
    except Exception as exc:
        try:
            persist_root(plan.source)
        except Exception as rollback_exc:
            payload["rollback_error"] = str(rollback_exc)
        payload["state"] = "rollback_required" if payload.get("rollback_error") else "rolled_back"
        payload["error"] = str(exc)
        _write_journal(plan.journal, payload)
        if plan.staging.exists():
            shutil.rmtree(plan.staging, ignore_errors=True)
        raise StorageMigrationError(str(exc)) from exc


def read_migration_journal(path: Path) -> dict:
    """Read a persisted migration journal for UI recovery decisions."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StorageMigrationError(f"Migration journal cannot be read: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise StorageMigrationError("Migration journal has an unsupported format.")
    return value
