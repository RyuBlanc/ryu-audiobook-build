from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json
import shutil
import os
import tempfile

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

    @classmethod
    def load(cls, folder: Path) -> "Project":
        project_file = folder / "project.json"
        chapters_file = folder / "chapters.json"
        if not project_file.exists() or not chapters_file.exists():
            raise ValueError("Invalid Ryu's Audiobook project.")
        metadata = json.loads(project_file.read_text(encoding="utf-8"))
        chapter_data = json.loads(chapters_file.read_text(encoding="utf-8"))
        chapters = [Chapter(**item) for item in chapter_data]
        source_name = metadata.get("source_file")
        source = folder / "source" / source_name if source_name else None
        return cls(metadata["title"], folder, source, chapters)

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

def list_projects() -> list[Project]:
    projects: list[Project] = []
    seen_folders: set[str] = set()
    # Scan the chosen root first, then the original root. Existing projects are
    # not moved or hidden just because the user changes the destination for new imports.
    for root in project_library_roots():
        if not root.is_dir():
            continue
        try:
            folders = sorted(root.iterdir())
        except OSError:
            # An external library drive can be disconnected while the app is open.
            continue
        for folder in folders:
            # Import staging folders may briefly contain verified JSON while the
            # import worker is preparing its atomic publish. Never expose these.
            if folder.name.startswith(".import-staging-"):
                continue
            if not folder.is_dir() or not (folder / "project.json").exists():
                continue
            try:
                key = str(folder.resolve()).casefold()
            except OSError:
                key = str(folder.absolute()).casefold()
            if key in seen_folders:
                continue
            try:
                project = Project.load(folder)
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
            projects.append(project)
            seen_folders.add(key)
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
