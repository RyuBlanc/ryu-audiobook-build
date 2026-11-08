from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json
import shutil
import os
import tempfile
import threading
from typing import Any

from app.chapters.detector import Chapter
from app.core.paths import library_root, project_library_roots

class Project:
    def __init__(self, title: str, folder: Path, source_path: Path | None = None, chapters: list[Chapter] | None = None):
        self.title = title
        self.folder = folder
        self.source_path = source_path
        self.chapters = chapters or []

    @property
    def project_file(self) -> Path:
        return self.folder / "project.json"

    @property
    def text_file(self) -> Path:
        return self.folder / "chapters.json"

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            Path(temp_name).replace(path)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            Path(temp_name).unlink(missing_ok=True)
            raise

    def save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)

        # Normalize chapter numbering to the current editor order before writing.
        for number, chapter in enumerate(self.chapters, start=1):
            chapter.number = number

        source = self.source_path.name if self.source_path else None
        project_payload = json.dumps(
            {"title": self.title, "source_file": source},
            ensure_ascii=False,
            indent=2,
        )
        chapters_payload = json.dumps(
            [asdict(chapter) for chapter in self.chapters],
            ensure_ascii=False,
            indent=2,
        )

        # Write atomically so a Save cannot leave a partially-written chapters.json.
        self._atomic_write_text(self.project_file, project_payload)
        self._atomic_write_text(self.text_file, chapters_payload)

        # Verify the exact chapter data we intended to persist.
        persisted = json.loads(self.text_file.read_text(encoding="utf-8"))
        if persisted != json.loads(chapters_payload):
            raise IOError("Saved chapter data could not be verified.")
        invalidate_project_list_cache(self.folder)

    @classmethod
    def load(cls, folder: Path, *, migrate_legacy: bool = True) -> "Project":
        """Load project metadata and chapters.

        Legacy chapter/narration/BGM identity migration is intentionally optional.
        Library refreshes and cache invalidation may need to reread the two small
        project files repeatedly; those reads must not rescan every narration
        directory or rerun migration work. A project is migrated on its first
        authoritative open in the desktop session.
        """
        folder = Path(folder)
        project_file = folder / "project.json"
        chapters_file = folder / "chapters.json"
        if not project_file.exists() or not chapters_file.exists():
            raise ValueError("Invalid Ryu's Audiobook project.")
        metadata = json.loads(project_file.read_text(encoding="utf-8"))
        chapter_data = json.loads(chapters_file.read_text(encoding="utf-8"))
        if not isinstance(chapter_data, list):
            raise ValueError("Invalid Ryu's Audiobook chapter data.")
        chapters = [Chapter(**item) for item in chapter_data]

        if migrate_legacy:
            seen_ids: set[str] = set()
            identity_changed = False
            for item, chapter in zip(chapter_data, chapters):
                if not isinstance(item, dict) or not str(item.get("chapter_id") or "").strip():
                    identity_changed = True
                if chapter.chapter_id in seen_ids:
                    from uuid import uuid4
                    chapter.chapter_id = uuid4().hex
                    identity_changed = True
                seen_ids.add(chapter.chapter_id)
            if identity_changed:
                cls._atomic_write_text(
                    chapters_file,
                    json.dumps([asdict(chapter) for chapter in chapters], ensure_ascii=False, indent=2),
                )

            # Attach IDs to legacy narration only when both number and title match exactly.
            working_audio = folder / "working_audio"
            by_number_title = {
                (chapter.number, chapter.title.strip().casefold()): chapter.chapter_id
                for chapter in chapters
            }
            if working_audio.is_dir():
                for chapter_dir in working_audio.iterdir():
                    manifest = chapter_dir / "narration.json"
                    if not chapter_dir.is_dir() or not manifest.is_file():
                        continue
                    try:
                        narration = json.loads(manifest.read_text(encoding="utf-8"))
                        key = (int(narration.get("chapter") or 0), str(narration.get("title") or "").strip().casefold())
                        chapter_id = by_number_title.get(key)
                        if chapter_id and not str(narration.get("chapter_id") or "").strip():
                            narration["chapter_id"] = chapter_id
                            cls._atomic_write_text(
                                manifest, json.dumps(narration, ensure_ascii=False, indent=2)
                            )
                    except (OSError, ValueError, TypeError, json.JSONDecodeError):
                        continue

            # Bind legacy number-keyed BGM assignments to stable chapter IDs.
            state_file = folder / "state.json"
            if state_file.is_file():
                from app.core.state import load_state, save_state
                state = load_state(folder)
                stored_overrides = state.get("chapter_bgm_overrides")
                if isinstance(stored_overrides, dict):
                    migrated_overrides = dict(stored_overrides)
                    for chapter in chapters:
                        identity_key = str(chapter.chapter_id)
                        legacy_value = stored_overrides.get(str(chapter.number))
                        if identity_key not in migrated_overrides and isinstance(legacy_value, dict):
                            migrated_overrides[identity_key] = dict(legacy_value)
                    if migrated_overrides != stored_overrides:
                        state["chapter_bgm_overrides"] = migrated_overrides
                        try:
                            save_state(folder, state)
                        except OSError as exc:
                            raise RuntimeError(
                                "Could not safely migrate this project's chapter BGM assignments. "
                                "Make the project folder writable and reopen it before editing chapters."
                            ) from exc

        source_name = metadata.get("source_file")
        source = folder / "source" / source_name if source_name else None
        return cls(metadata["title"], folder, source, chapters)


def resolve_library_project_folder(folder: Path) -> Path | None:
    """Resolve a direct child project folder without enumerating the whole Library.

    The resolved parent check also rejects symlinks that escape the selected or
    legacy Library roots. A disconnected configured Library is distinguished
    from a missing project so the active-project setting is never silently lost.
    """
    target = Path(folder).expanduser().resolve()
    for root in project_library_roots():
        root = Path(root).expanduser().resolve()
        if target.parent != root:
            continue
        if not root.is_dir():
            raise FileNotFoundError(
                "The Library location is unavailable. Reconnect the selected drive "
                "before opening or editing this project."
            )
        if (
            not target.is_dir()
            or not (target / "project.json").is_file()
            or not (target / "chapters.json").is_file()
        ):
            return None
        return target
    return None


def create_project(title: str, source_path: Path, chapters: list[Chapter]) -> Project:
    """Create a project transactionally so failed imports never appear as partial books.

    All writes happen in a private staging directory under the library root. The
    completed folder is renamed into place only after the source copy and both
    project JSON files have been written and verified.
    """
    source_path = Path(source_path)
    if not source_path.is_file():
        raise FileNotFoundError(f"Import source does not exist: {source_path}")

    root = library_root()
    root.mkdir(parents=True, exist_ok=True)
    safe_title = "".join(c for c in title if c not in '<>:"/\\|?*').strip() or "Untitled Book"

    # Reserve a unique final name. The final rename is atomic on the same
    # filesystem; if another importer wins the name in the meantime, retry.
    suffix = 1
    while True:
        candidate_title = safe_title if suffix == 1 else f"{safe_title} ({suffix})"
        final_folder = root / candidate_title
        if not final_folder.exists():
            break
        suffix += 1

    staging_folder = Path(tempfile.mkdtemp(prefix=".import-staging-", dir=str(root)))
    try:
        source_dir = staging_folder / "source"
        source_dir.mkdir()
        staged_source = source_dir / source_path.name
        if source_path.resolve() != staged_source.resolve():
            shutil.copy2(source_path, staged_source)

        staged_project = Project(candidate_title, staging_folder, staged_source, chapters)
        staged_project.save()

        # Verify the staged project can be loaded before it becomes visible in
        # the user's library. This catches malformed or incomplete JSON writes.
        verified = Project.load(staging_folder)
        if len(verified.chapters) != len(chapters):
            raise IOError("Imported chapter count changed while saving the project.")

        while True:
            try:
                staging_folder.rename(final_folder)
                break
            except FileExistsError:
                suffix += 1
                candidate_title = f"{safe_title} ({suffix})"
                final_folder = root / candidate_title

        final_source = final_folder / "source" / source_path.name
        return Project(candidate_title, final_folder, final_source, verified.chapters)
    except Exception:
        shutil.rmtree(staging_folder, ignore_errors=True)
        raise

# list_projects() is called by Dashboard, Library, Trash and generation lookups.
# Reuse parsed Project objects while the durable project metadata and chapter file
# fingerprints are unchanged. This avoids reparsing multi-megabyte chapters.json
# (and, importantly, rerunning legacy narration/BGM migration) on every UI refresh.
_PROJECT_LIST_CACHE_LOCK = threading.RLock()
_PROJECT_LIST_CACHE: dict[str, tuple[tuple[Any, ...], "Project"]] = {}


def _project_list_fingerprint(folder: Path) -> tuple[Any, ...] | None:
    """Fingerprint only the two files that determine the loaded Project object."""
    result: list[Any] = []
    for name in ("project.json", "chapters.json"):
        try:
            stat = (folder / name).stat()
        except OSError:
            return None
        result.extend((stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, getattr(stat, "st_ino", 0)))
    return tuple(result)


def invalidate_project_list_cache(folder: Path | str | None = None) -> None:
    """Invalidate one saved project after a durable edit, or clear the full list."""
    with _PROJECT_LIST_CACHE_LOCK:
        if folder is None:
            _PROJECT_LIST_CACHE.clear()
            return
        try:
            key = str(Path(folder).expanduser().resolve()).casefold()
        except (OSError, RuntimeError, ValueError):
            key = str(Path(folder).expanduser().absolute()).casefold()
        _PROJECT_LIST_CACHE.pop(key, None)


def list_projects() -> list[Project]:
    projects: list[Project] = []
    seen_folders: set[str] = set()
    scanned_roots: list[str] = []

    # Scan the selected root first, then the original root. Existing projects
    # remain visible when the user changes the destination for new imports.
    for root_value in project_library_roots():
        root = Path(root_value).expanduser()
        try:
            if not root.is_dir():
                # A disconnected external drive must not erase its cached rows.
                continue
            root_key = str(root.resolve()).casefold()
            scanned_roots.append(root_key)
            folders = sorted(root.iterdir())
        except OSError:
            continue

        for folder in folders:
            if folder.name.startswith(".import-staging-") or not folder.is_dir():
                continue
            try:
                resolved_folder = folder.resolve()
                key = str(resolved_folder).casefold()
            except (OSError, RuntimeError, ValueError):
                resolved_folder = folder.absolute()
                key = str(resolved_folder).casefold()
            if key in seen_folders:
                continue

            fingerprint = _project_list_fingerprint(folder)
            if fingerprint is None:
                continue
            with _PROJECT_LIST_CACHE_LOCK:
                cached = _PROJECT_LIST_CACHE.get(key)
            if cached is not None and cached[0] == fingerprint:
                project = cached[1]
            else:
                try:
                    # Listing is observational only. Legacy chapter IDs, narration
                    # manifests and BGM keys are migrated on authoritative open,
                    # never during every Dashboard/Library search refresh.
                    project = Project.load(folder, migrate_legacy=False)
                except (OSError, ValueError, KeyError, json.JSONDecodeError):
                    continue

                after_load = _project_list_fingerprint(folder)
                if after_load is None:
                    continue
                if after_load != fingerprint:
                    # A concurrent Save replaced files while the snapshot was read.
                    # Re-read once so we do not expose mixed project/chapter data.
                    try:
                        project = Project.load(folder, migrate_legacy=False)
                    except (OSError, ValueError, KeyError, json.JSONDecodeError):
                        continue
                    after_load = _project_list_fingerprint(folder)
                    if after_load is None:
                        continue
                with _PROJECT_LIST_CACHE_LOCK:
                    _PROJECT_LIST_CACHE[key] = (after_load, project)

            projects.append(project)
            seen_folders.add(key)

    # Remove deleted/renamed entries from roots that were successfully scanned.
    # Keep entries under unavailable external roots for reconnect/recovery.
    with _PROJECT_LIST_CACHE_LOCK:
        for key in list(_PROJECT_LIST_CACHE):
            try:
                parent = str(Path(key).parent).casefold()
            except (OSError, ValueError):
                continue
            if parent in scanned_roots and key not in seen_folders:
                _PROJECT_LIST_CACHE.pop(key, None)

    return projects


def _preserve_project_pronunciations(state: dict) -> None:
    """Promote book-specific pronunciation overrides before their project is removed."""
    try:
        from PySide6.QtCore import QSettings

        settings = QSettings("RyuBlanc", "Ryu's Audiobook")
        raw = settings.value("pronunciation/global_dictionary", "[]")
        try:
            global_entries = json.loads(str(raw)) if isinstance(raw, str) else raw
        except (TypeError, ValueError, json.JSONDecodeError):
            global_entries = []
        if not isinstance(global_entries, list):
            global_entries = []
        by_written = {
            str(item.get("written") or "").strip().casefold(): dict(item)
            for item in global_entries
            if isinstance(item, dict) and str(item.get("written") or "").strip()
        }
        for item in state.get("pronunciation_dictionary", []) or []:
            if not isinstance(item, dict):
                continue
            written = str(item.get("written") or "").strip()
            spoken = str(item.get("spoken") or "").strip()
            if not written or not spoken:
                continue
            key = written.casefold()
            # Existing global pronunciations win; a book-only pronunciation is
            # promoted only when it would not overwrite another explicit global rule.
            if key not in by_written:
                by_written[key] = {
                    "written": written,
                    "spoken": spoken,
                    "enabled": item.get("enabled", True) is not False,
                    "source": str(item.get("source") or "preserved-from-deleted-book"),
                }
        settings.setValue(
            "pronunciation/global_dictionary",
            json.dumps(list(by_written.values()), ensure_ascii=False),
        )
        settings.sync()
    except Exception as exc:
        raise RuntimeError(f"Could not preserve this book's pronunciation dictionary: {exc}") from exc


def delete_project(project: Project) -> None:
    """Remove one project's files while retaining a standalone History record.

    The recorded output file is removed only at its exact saved path. The shared
    Character Library and global pronunciation dictionary live outside the project
    folder and are retained.
    """
    from app.core.paths import project_library_roots
    from app.core.state import load_state
    from app.core.character_library import sync_characters
    from app.core.project_history import record_project_deletion, update_project_deletion

    folder = project.folder.resolve()
    allowed_roots = []
    for root_path in project_library_roots():
        try:
            allowed_roots.append(root_path.resolve())
        except OSError:
            continue
    if not any(folder != root and root in folder.parents for root in allowed_roots):
        raise ValueError("Refusing to delete a folder outside the audiobook library.")
    if not folder.exists():
        return

    state = load_state(folder)
    output_value = str(state.get("output_path") or "").strip()
    output_path = Path(output_value).expanduser() if output_value else None
    if output_path is not None and not output_path.is_absolute():
        output_path = folder / output_path
    output_removed = False

    # Write the history record before destructive work, so a crash during deletion
    # cannot erase the fact that a project and its output existed.
    history_id = record_project_deletion(
        project,
        state,
        output_path=str(output_path or ""),
        output_removed=False,
    )
    try:
        # Last-chance sync protects names, aliases, and assigned voices even if
        # Character Studio was not opened after the last cast edit.
        roster = state.get("voice_cast_character_roster", [])
        assignments = state.get("voice_cast", {})
        assignments = assignments if isinstance(assignments, dict) else {}
        if isinstance(roster, list) and roster:
            cast_rows = []
            for row in roster:
                if not isinstance(row, dict):
                    continue
                item = dict(row)
                voice = assignments.get(str(item.get("name") or ""))
                if voice:
                    item["voice"] = voice
                cast_rows.append(item)
            series = str(state.get("series_name") or state.get("series") or project.title).strip()
            sync_characters(
                series,
                cast_rows,
                source_project_folder=str(folder),
                source_project_title=project.title,
            )

        _preserve_project_pronunciations(state)

        if output_path is not None:
            try:
                resolved_output = output_path.resolve()
                project_resolved = folder.resolve()
                is_inside_project = resolved_output == project_resolved or project_resolved in resolved_output.parents
            except OSError:
                is_inside_project = False
            if output_path.is_file() and not is_inside_project:
                # The output_path is a specific generated-file reference from
                # this project's saved state; don't recurse into its parent folder.
                output_path.unlink()
                output_removed = True
            elif is_inside_project and output_path.is_file():
                output_removed = True

        shutil.rmtree(folder)
        update_project_deletion(
            history_id,
            deletion_state="deleted",
            output_removed=output_removed,
        )
    except Exception:
        try:
            update_project_deletion(
                history_id,
                deletion_state="failed",
                output_removed=output_removed,
            )
        except Exception:
            pass
        raise
