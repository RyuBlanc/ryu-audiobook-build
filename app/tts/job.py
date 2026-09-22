from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event
from pathlib import Path

@dataclass
class GenerationJob:
    book_title: str
    output_root: Path
    total_chapters: int
    completed_chapters: int = 0
    failed_chapters: list[int] = field(default_factory=list)
    cancelled: Event = field(default_factory=Event)

    @property
    def progress_percent(self) -> int:
        if self.total_chapters <= 0:
            return 100
        return int(self.completed_chapters * 100 / self.total_chapters)

    def cancel(self) -> None:
        self.cancelled.set()

    def is_cancelled(self) -> bool:
        return self.cancelled.is_set()
