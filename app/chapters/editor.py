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
        chapter = self.chapters[index]
        assignments = _remap_assignments(text, list(getattr(chapter, "dialogue_assignments", [])))
        self.chapters[index] = replace(
            chapter,
            text=text,
            dialogue_assignments=assignments,
        )

    def delete(self, index: int) -> None:
        del self.chapters[index]
        self._renumber()

    def merge_with_next(self, index: int) -> None:
        if index < 0 or index >= len(self.chapters) - 1:
            raise IndexError("There is no next chapter to merge.")
        current = self.chapters[index]
        following = self.chapters[index + 1]
        left = current.text.rstrip()
        right = following.text.lstrip()
        raw_text = left + "\n\n" + right
        leading_trim = len(raw_text) - len(raw_text.lstrip())
        text = raw_text.strip()
        right_offset = len(left) + 2 - leading_trim

        assignments = []
        for item in getattr(current, "dialogue_assignments", []) or []:
            adjusted = dict(item)
            adjusted["start"] = int(item.get("start", 0) or 0) - leading_trim
            adjusted["end"] = int(item.get("end", 0) or 0) - leading_trim
            assignments.append(adjusted)
        for item in getattr(following, "dialogue_assignments", []) or []:
            adjusted = dict(item)
            adjusted["start"] = int(item.get("start", 0) or 0) + right_offset
            adjusted["end"] = int(item.get("end", 0) or 0) + right_offset
            assignments.append(adjusted)

        remapped = _remap_assignments(text, assignments)
        self.chapters[index] = replace(
            current, title=current.title, text=text, dialogue_assignments=remapped
        )
        del self.chapters[index + 1]
        self._renumber()

    def split(self, index: int, paragraph_index: int, new_title: str) -> None:
        chapter = self.chapters[index]
        text = chapter.text
        paragraph_spans = []
        cursor = 0
        for paragraph in text.split("\n\n"):
            start = cursor + len(paragraph) - len(paragraph.lstrip())
            end = cursor + len(paragraph.rstrip())
            if paragraph.strip():
                paragraph_spans.append((start, end))
            cursor += len(paragraph) + 2
        if paragraph_index <= 0 or paragraph_index >= len(paragraph_spans):
            raise ValueError("Split point must be between paragraphs.")

        split_at = paragraph_spans[paragraph_index][0]
        left_raw, right_raw = text[:split_at], text[split_at:]
        first, second = left_raw.strip(), right_raw.strip()
        first_trim = len(left_raw) - len(left_raw.lstrip())
        second_trim = len(right_raw) - len(right_raw.lstrip())
        first_assignments, second_assignments = [], []
        for item in getattr(chapter, "dialogue_assignments", []) or []:
            start = int(item.get("start", 0) or 0)
            end = int(item.get("end", start) or start)
            if end <= split_at:
                adjusted = dict(item)
                adjusted["start"] = start - first_trim
                adjusted["end"] = end - first_trim
                first_assignments.append(adjusted)
            elif start >= split_at:
                adjusted = dict(item)
                adjusted["start"] = start - split_at - second_trim
                adjusted["end"] = end - split_at - second_trim
                second_assignments.append(adjusted)
            # An assignment spanning the split boundary is deliberately dropped.
        first_assignments = _remap_assignments(first, first_assignments)
        second_assignments = _remap_assignments(second, second_assignments)
        self.chapters[index] = replace(
            chapter, text=first, dialogue_assignments=first_assignments
        )
        self.chapters.insert(
            index + 1,
            Chapter(0, new_title.strip() or "New Chapter", second,
                    dialogue_assignments=second_assignments),
        )
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

        cut_at = line_end + 1 if line_end < len(text) else line_end
        before_raw = text[:line_start]
        after_raw = text[cut_at:]
        before = before_raw.strip()
        after = after_raw.strip()
        before_trim = len(before_raw) - len(before_raw.lstrip())
        after_trim = len(after_raw) - len(after_raw.lstrip())
        before_assignments, after_assignments = [], []
        for item in getattr(chapter, "dialogue_assignments", []) or []:
            start_pos = int(item.get("start", 0) or 0)
            end_pos = int(item.get("end", start_pos) or start_pos)
            if end_pos <= line_start:
                adjusted = dict(item)
                adjusted["start"] = start_pos - before_trim
                adjusted["end"] = end_pos - before_trim
                before_assignments.append(adjusted)
            elif start_pos >= cut_at:
                adjusted = dict(item)
                adjusted["start"] = start_pos - cut_at - after_trim
                adjusted["end"] = end_pos - cut_at - after_trim
                after_assignments.append(adjusted)
            # Assignments on the removed heading line are intentionally discarded.
        before_assignments = _remap_assignments(before, before_assignments)
        after_assignments = _remap_assignments(after, after_assignments)

        if not before:
            # The selected heading is at the beginning: simply make it the
            # current chapter title and keep all following story text.
            self.chapters[index] = replace(
                chapter, title=title, text=after, dialogue_assignments=after_assignments
            )
        else:
            self.chapters[index] = replace(
                chapter, text=before, dialogue_assignments=before_assignments
            )
            self.chapters.insert(
                index + 1,
                Chapter(0, title, after, dialogue_assignments=after_assignments),
            )

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


def _remap_assignments(text: str, assignments: list[dict]) -> list[dict]:
    """Keep valid cast metadata attached to its exact dialogue after edits.

    Stale or ambiguous source spans are not guessed. All assignment metadata
    (including multi-speaker mode, confidence, and evidence) is retained when
    the exact text can be located in the new chapter.
    """
    remapped: list[dict] = []
    used: set[int] = set()
    for item in assignments or []:
        snippet = str(item.get("text", "")).strip()
        speaker = str(item.get("speaker", "")).strip()
        speakers = [
            str(value).strip()
            for value in (item.get("speakers") or [])
            if str(value).strip()
        ]
        if not snippet or not (speaker or speakers):
            continue
        try:
            old_start = int(item.get("start", 0) or 0)
        except (TypeError, ValueError):
            old_start = 0
        candidates: list[int] = []
        cursor = 0
        while True:
            position = text.find(snippet, cursor)
            if position < 0:
                break
            if position not in used:
                candidates.append(position)
            cursor = position + 1
        if not candidates:
            # The dialogue text was changed. Do not keep stale offsets.
            continue
        start = min(candidates, key=lambda pos: abs(pos - old_start))
        end = start + len(snippet)
        used.add(start)
        updated = dict(item)
        updated.update({"start": start, "end": end, "text": snippet})
        if speaker:
            updated["speaker"] = speaker
        if speakers:
            updated["speakers"] = speakers
        updated.setdefault("source", "manual")
        remapped.append(updated)
    return remapped
