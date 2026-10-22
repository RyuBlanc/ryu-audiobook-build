from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json
import shutil
import os
import tempfile

from app.chapters.detector import Chapter
from app.core.paths import library_root

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
    projects = []
    root = library_root()
    for folder in sorted(root.iterdir()):
        if folder.is_dir() and (folder / "project.json").exists():
            try:
                projects.append(Project.load(folder))
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
    return projects



def delete_project(project: Project) -> None:
    """Delete one imported book and all Ryu-generated data inside its folder."""
    root = library_root().resolve()
    folder = project.folder.resolve()
    if folder == root or root not in folder.parents:
        raise ValueError("Refusing to delete a folder outside the audiobook library.")
    if not folder.exists():
        return
    shutil.rmtree(folder)
