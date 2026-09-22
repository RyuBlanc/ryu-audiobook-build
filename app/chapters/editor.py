from __future__ import annotations

from dataclasses import replace
from .detector import Chapter


class ChapterEditor:
    def __init__(self, chapters: list[Chapter]) -> None:
        self.chapters = chapters

    def rename(self, index: int, title: str) -> None:
        self.chapters[index] = replace(
            self.chapters[index],
            title=title.strip() or self.chapters[index].title,
        )

    def edit_text(self, index: int, text: str) -> None:
        self.chapters[index] = replace(self.chapters[index], text=text)

    def delete(self, index: int) -> None:
        del self.chapters[index]
        self._renumber()

    def merge_with_next(self, index: int) -> None:
        if index < 0 or index >= len(self.chapters) - 1:
            raise IndexError("There is no next chapter to merge.")
        current = self.chapters[index]
        following = self.chapters[index + 1]
        title = current.title
        text = (current.text.rstrip() + "\n\n" + following.text.lstrip()).strip()
        self.chapters[index] = replace(current, title=title, text=text)
        del self.chapters[index + 1]
        self._renumber()

    def split(self, index: int, paragraph_index: int, new_title: str) -> None:
        chapter = self.chapters[index]
        paragraphs = [p.strip() for p in chapter.text.split("\n\n") if p.strip()]
        if paragraph_index <= 0 or paragraph_index >= len(paragraphs):
            raise ValueError("Split point must be between paragraphs.")
        first = "\n\n".join(paragraphs[:paragraph_index])
        second = "\n\n".join(paragraphs[paragraph_index:])
        self.chapters[index] = replace(chapter, text=first)
        self.chapters.insert(index + 1, Chapter(0, new_title.strip() or "New Chapter", second))
        self._renumber()

    def split_at_selection(
        self,
        index: int,
        selection_start: int,
        selection_end: int,
        new_title: str,
    ) -> None:
        """Create a chapter from a selected heading without losing other text."""
        chapter = self.chapters[index]
        text = chapter.text
        start = max(0, min(selection_start, len(text)))
        end = max(start, min(selection_end, len(text)))

        # Expand to the whole line so a selected heading is not left in the
        # generated narration.
        line_start = text.rfind("\n", 0, start) + 1
        newline_after = text.find("\n", end)
        line_end = len(text) if newline_after < 0 else newline_after

        title = new_title.strip()
        if not title:
            raise ValueError("Select a chapter title first.")

        before = text[:line_start].strip()
        after = text[line_end + 1 :].strip() if line_end < len(text) else ""

        if not before:
            # The selected heading is at the beginning: simply make it the
            # current chapter title and keep all following story text.
            self.chapters[index] = replace(chapter, title=title, text=after)
        else:
            self.chapters[index] = replace(chapter, text=before)
            self.chapters.insert(index + 1, Chapter(0, title, after))

        self._renumber()

    def move(self, index: int, direction: int) -> None:
        target = index + direction
        if target < 0 or target >= len(self.chapters):
            return
        self.chapters[index], self.chapters[target] = (
            self.chapters[target],
            self.chapters[index],
        )
        self._renumber()

    def _renumber(self) -> None:
        for number, chapter in enumerate(self.chapters, 1):
            self.chapters[number - 1] = replace(chapter, number=number)
