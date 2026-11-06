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
    switched = False
    rollback_ok = False
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

        source_after_copy = _walk_files(plan.source)
        staged_after_copy = _walk_files(plan.staging)
        if len(source_after_copy) != plan.file_count or len(staged_after_copy) != plan.file_count:
            raise StorageMigrationError("Source or staged file count changed during migration.")
        if sum(row[2] for row in source_after_copy) != plan.total_bytes:
            raise StorageMigrationError("Source files changed size during migration.")
        if sum(row[2] for row in staged_after_copy) != plan.total_bytes:
            raise StorageMigrationError("Staged byte count does not match the source.")
        for source_row, staged_row in zip(source_after_copy, staged_after_copy):
            source_file, source_relative, source_size = source_row
            staged_file, staged_relative, staged_size = staged_row
            if source_relative != staged_relative or source_size != staged_size:
                raise StorageMigrationError(f"Source and staged paths differ: {source_relative}")
            if _sha256(source_file) != _sha256(staged_file):
                raise StorageMigrationError(f"Source changed during migration: {source_relative}")
        if is_busy and is_busy(plan.source):
            raise StorageMigrationError("An active job started during migration.")

        payload["state"] = "switching"
        _write_journal(plan.journal, payload)
        if plan.destination.exists():
            plan.destination.rmdir()
        os.replace(plan.staging, plan.destination)
        switched = True
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
            rollback_ok = True
        except Exception as rollback_exc:
            payload["rollback_error"] = str(rollback_exc)
        payload["state"] = "rolled_back" if rollback_ok else "rollback_required"
        payload["error"] = str(exc)
        _write_journal(plan.journal, payload)
        if plan.staging.exists():
            shutil.rmtree(plan.staging, ignore_errors=True)
        # Delete only the destination created by this migration, and only after
        # the old root has been restored successfully.
        if rollback_ok and switched and plan.destination.exists():
            shutil.rmtree(plan.destination, ignore_errors=True)
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



def recover_migration_journal(path: Path, *, persist_root: Callable[[Path], None]) -> dict:
    """Recover interrupted migrations conservatively; never delete the source.

    A completed journal is left untouched. Any incomplete journal restores the
    source root setting and removes only its uniquely named staging directory.
    A destination is retained for manual inspection if a crash occurred after
    the directory switch, because the journal cannot prove it is safe to delete.
    """
    payload = read_migration_journal(path)
    state = str(payload.get("state", ""))
    if state == "complete_source_retained":
        return payload
    source = Path(str(payload.get("source", ""))).expanduser()
    staging = Path(str(payload.get("staging", ""))).expanduser()
    destination = Path(str(payload.get("destination", ""))).expanduser()
    if not source.is_absolute() or not destination.is_absolute() or not staging.is_absolute():
        raise StorageMigrationError("Migration journal contains invalid paths.")
    if not source.is_dir():
        payload["state"] = "recovery_required"
        payload["recovery_error"] = "Original source is unavailable; no paths were changed."
        _write_journal(Path(path), payload)
        return payload
    persist_root(source)
    if staging.name.startswith(f".{destination.name}.ryu-migration-") and staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    payload["state"] = "recovered_source_restored"
    _write_journal(Path(path), payload)
    return payload


def safe_cleanup(
    *,
    cache_roots: tuple[Path, ...] = (),
    temporary_roots: tuple[Path, ...] = (),
    dry_run: bool = True,
    protected_paths: tuple[Path, ...] = (),
) -> dict:
    """Clean only app-owned cache/temp contents; never traverse protected paths.

    Cleanup targets are limited to immediate children of explicitly supplied
    app-owned cache/temp roots. Model roots, project folders, source books,
    exports, voice references and profiles must never be passed as targets.
    """
    allowed_roots = tuple(Path(p).expanduser().resolve() for p in (*cache_roots, *temporary_roots))
    protected = tuple(Path(p).expanduser().resolve() for p in protected_paths)
    candidates: list[Path] = []
    total_bytes = 0
    for root in allowed_roots:
        if not root.exists() or not root.is_dir() or root.is_symlink():
            continue
        for child in root.iterdir():
            resolved = child.resolve()
            if resolved == root or not _inside(resolved, root):
                continue
            if any(resolved == item or _inside(resolved, item) or _inside(item, resolved) for item in protected):
                continue
            if child.is_symlink():
                continue
            candidates.append(child)
            if child.is_file():
                total_bytes += child.stat().st_size
            elif child.is_dir():
                for folder, _dirs, files in os.walk(child, followlinks=False):
                    for name in files:
                        file_path = Path(folder) / name
                        if not file_path.is_symlink():
                            try:
                                total_bytes += file_path.stat().st_size
                            except OSError:
                                pass
    removed = []
    if not dry_run:
        for target in candidates:
            try:
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.is_file():
                    target.unlink()
                removed.append(str(target))
            except OSError:
                continue
    return {
        "dry_run": bool(dry_run),
        "candidate_count": len(candidates),
        "candidate_bytes": total_bytes,
        "candidates": [str(p) for p in candidates],
        "removed": removed,
    }
