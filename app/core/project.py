from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json
import shutil

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

    def save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        source = self.source_path.name if self.source_path else None
        self.project_file.write_text(
            json.dumps({"title": self.title, "source_file": source}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        chapter_data = [asdict(chapter) for chapter in self.chapters]
        self.text_file.write_text(json.dumps(chapter_data, ensure_ascii=False, indent=2), encoding="utf-8")

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
    safe_title = "".join(c for c in title if c not in '<>:"/\\|?*').strip() or "Untitled Book"
    folder = library_root() / safe_title
    folder.mkdir(parents=True, exist_ok=True)
    source_dir = folder / "source"
    source_dir.mkdir(exist_ok=True)
    destination = source_dir / source_path.name
    if source_path.resolve() != destination.resolve():
        shutil.copy2(source_path, destination)
    project = Project(safe_title, folder, destination, chapters)
    project.save()
    return project

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
