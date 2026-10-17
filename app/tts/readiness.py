from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReadinessItem:
    label: str
    ok: bool
    detail: str
    blocking: bool = True


@dataclass(frozen=True)
class GenerationReadiness:
    items: tuple[ReadinessItem, ...]

    @property
    def blocking_failures(self) -> tuple[ReadinessItem, ...]:
        return tuple(item for item in self.items if item.blocking and not item.ok)

    @property
    def ready(self) -> bool:
        return not self.blocking_failures

    @property
    def attention_count(self) -> int:
        return sum(1 for item in self.items if not item.ok)


def partition_chapters_by_body(chapters):
    """Separate synthesizable chapters from empty records without mutating the project."""
    valid = []
    empty = []
    for chapter in list(chapters or []):
        if str(getattr(chapter, "text", "") or "").strip():
            valid.append(chapter)
        else:
            empty.append(chapter)
    return valid, empty


def build_generation_readiness(
    chapters,
    voice_name: str | None,
    voice_provider: str | None,
    output_path: str | None,
    custom_runtime_ready: bool = True,
    assignments: dict | None = None,
    cover_selected: bool = False,
) -> GenerationReadiness:
    chapters = list(chapters or [])
    valid_chapters, empty_chapters = partition_chapters_by_body(chapters)
    empty_numbers = [getattr(chapter, "number", "?") for chapter in empty_chapters]
    assignments = assignments if isinstance(assignments, dict) else {}

    if not chapters:
        chapter_detail = "No chapters available."
    elif not valid_chapters:
        chapter_detail = "No chapter contains body text. Restore text or repair the source."
    elif empty_chapters:
        chapter_detail = (
            f"{len(valid_chapters)} chapter(s) contain text; empty chapter(s) "
            f"{', '.join(map(str, empty_numbers))} will be skipped if source repair cannot recover them."
        )
    else:
        chapter_detail = f"{len(valid_chapters)} chapter(s) ready."

    items = [
        ReadinessItem(
            "Chapters",
            bool(valid_chapters) and not empty_chapters,
            chapter_detail,
            not bool(valid_chapters),
        ),
        ReadinessItem(
            "Narrator voice",
            bool(voice_name),
            f"Selected: {voice_name}" if voice_name else "Select a voice profile.",
            True,
        ),
        ReadinessItem(
            "Custom voice engine",
            voice_provider != "chatterbox" or custom_runtime_ready,
            (
                "Custom voice engine is ready."
                if voice_provider == "chatterbox"
                else "Not required for the selected narrator."
            ) if voice_provider != "chatterbox" or custom_runtime_ready else
            "Install / repair the Custom Voice Engine before generation.",
            True,
        ),
        ReadinessItem(
            "Output",
            bool(str(output_path or "").strip()),
            f"Output: {output_path}" if output_path else "Choose an M4B output location.",
            True,
        ),
        ReadinessItem(
            "Voice cast",
            True,
            f"{len(assignments)} character assignment(s) saved." if assignments else "Narrator-only generation; no character assignments saved.",
            False,
        ),
        ReadinessItem(
            "Cover",
            True,
            "Cover selected; it will be embedded." if cover_selected else "No cover selected; M4B will be created without embedded artwork.",
            False,
        ),
    ]
    return GenerationReadiness(tuple(items))
