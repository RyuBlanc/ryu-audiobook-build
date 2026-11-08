"""Persisted, revision-aware source-position index shared by character review and production.

The index is derived only from saved chapter text and saved dialogue assignments. It
never invents speakers: unresolved quote/dash spans remain review items, and every
passage retains exact offsets that are validated against the original chapter text.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any

from app.chapters.detector import Chapter
from app.chapters.speaker_segmentation import segment_chapter_speakers


INDEX_SCHEMA_VERSION = 1
INDEX_FILENAME = "dialogue_passage_index.json"

_LOCKS_GUARD = threading.RLock()
_FOLDER_LOCKS: dict[str, threading.RLock] = {}


def _folder_lock(folder: Path) -> threading.RLock:
    key = str(folder.resolve()).casefold()
    with _LOCKS_GUARD:
        return _FOLDER_LOCKS.setdefault(key, threading.RLock())


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _chapter_source_payload(chapter: Chapter) -> dict[str, Any]:
    return {
        "chapter_id": str(getattr(chapter, "chapter_id", "") or ""),
        "number": int(getattr(chapter, "number", 0) or 0),
        "title": str(getattr(chapter, "title", "") or ""),
        "text": str(getattr(chapter, "text", "") or ""),
    }


def _chapter_assignment_payload(chapter: Chapter) -> dict[str, Any]:
    assignments = getattr(chapter, "dialogue_assignments", []) or []
    rows = [dict(item) for item in assignments if isinstance(item, dict)]
    rows.sort(key=lambda item: (
        int(item.get("start", -1)) if str(item.get("start", "")).lstrip("-").isdigit() else -1,
        int(item.get("end", -1)) if str(item.get("end", "")).lstrip("-").isdigit() else -1,
        _stable_json(item),
    ))
    return {
        "chapter_id": str(getattr(chapter, "chapter_id", "") or ""),
        "assignments": rows,
        "skip_for_generation": bool(getattr(chapter, "skip_for_generation", False)),
    }


def passage_index_revisions(
    chapters: list[Chapter],
    suggested_passages: list[dict[str, Any]] | None = None,
) -> tuple[str, str, str]:
    """Return independent source, assignment/review, and combined revisions."""
    source_revision = _digest([_chapter_source_payload(chapter) for chapter in chapters])
    suggestions = [dict(row) for row in (suggested_passages or []) if isinstance(row, dict)]
    suggestions.sort(key=lambda row: (
        int(row.get("chapter_number", -1)) if str(row.get("chapter_number", "")).lstrip("-").isdigit() else -1,
        int(row.get("start", -1)) if str(row.get("start", "")).lstrip("-").isdigit() else -1,
        int(row.get("end", -1)) if str(row.get("end", "")).lstrip("-").isdigit() else -1,
        str(row.get("id") or ""),
    ))
    assignment_revision = _digest({
        "saved_assignments": [_chapter_assignment_payload(chapter) for chapter in chapters],
        "ai_review_suggestions": suggestions,
    })
    index_revision = _digest({
        "schema_version": INDEX_SCHEMA_VERSION,
        "source_revision": source_revision,
        "assignment_revision": assignment_revision,
    })
    return source_revision, assignment_revision, index_revision

def _passage_state(kind: str, source: str, needs_review: bool) -> str:
    if needs_review and source == "conflicting_saved_assignments":
        return "conflict"
    if needs_review:
        return "pending"
    if kind == "character_dialogue":
        return "assigned"
    if kind == "narration":
        return "narrator"
    return "pending"


def _passage_counts(passages: list[dict[str, Any]]) -> dict[str, int]:
    dialogue = [row for row in passages if row.get("kind") != "narration"]
    assigned = [row for row in dialogue if row.get("assignment_state") == "assigned"]
    return {
        "passage_count": len(passages),
        "dialogue_passage_count": len(dialogue),
        "narration_passage_count": sum(row.get("kind") == "narration" for row in passages),
        "assigned_dialogue_count": len(assigned),
        "ai_assigned_dialogue_count": sum(
            row.get("assignment_state") == "assigned" and str(row.get("source") or "").casefold() == "ai"
            for row in dialogue
        ),
        "manual_assigned_dialogue_count": sum(
            row.get("assignment_state") == "assigned" and str(row.get("source") or "").casefold() == "manual"
            for row in dialogue
        ),
        "pending_dialogue_count": sum(row.get("assignment_state") == "pending" for row in dialogue),
        "conflicting_dialogue_count": sum(row.get("assignment_state") == "conflict" for row in dialogue),
        "unassigned_dialogue_count": sum(
            row.get("assignment_state") in {"pending", "conflict"} for row in dialogue
        ),
    }


def build_passage_index(
    chapters: list[Chapter],
    suggested_passages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one canonical passage map from segmentation plus source-validated AI spans."""
    source_revision, assignment_revision, index_revision = passage_index_revisions(chapters, suggested_passages)
    suggestions_by_chapter: dict[int, list[dict[str, Any]]] = {}
    for suggestion in suggested_passages or []:
        if not isinstance(suggestion, dict):
            continue
        try:
            number = int(suggestion.get("chapter_number"))
        except (TypeError, ValueError, OverflowError):
            continue
        suggestions_by_chapter.setdefault(number, []).append(dict(suggestion))

    passages: list[dict[str, Any]] = []
    chapter_rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    for chapter in chapters:
        source_text = str(chapter.text or "")
        chapter_id = str(getattr(chapter, "chapter_id", "") or "")
        chapter_number = int(chapter.number)
        chapter_title = str(chapter.title or "")
        chapter_revision = _digest(_chapter_source_payload(chapter))
        segments = [
            {
                "start": int(segment.start),
                "end": int(segment.end),
                "text": str(segment.text or ""),
                "kind": str(segment.kind),
                "speaker": segment.speaker,
                "speakers": list(segment.speakers or ()),
                "source": str(segment.source or ""),
                "needs_review": bool(segment.needs_review),
                "ai_suggestions": [],
                "suggestion_id": "",
            }
            for segment in segment_chapter_speakers(chapter)
        ]

        # AI analysis may identify a dialogue passage without quotation marks or
        # dash cues. Keep its exact source span in this same review index.
        for suggestion in suggestions_by_chapter.get(chapter_number, []):
            raw_start, raw_end = suggestion.get("start"), suggestion.get("end")
            if isinstance(raw_start, bool) or isinstance(raw_end, bool):
                continue
            try:
                start, end = int(raw_start), int(raw_end)
            except (TypeError, ValueError, OverflowError):
                continue
            if start < 0 or end <= start or end > len(source_text):
                continue
            exact_text = source_text[start:end]
            expected = str(suggestion.get("source_text") or suggestion.get("text") or "")
            if not exact_text.strip() or exact_text != expected:
                continue
            candidate_names = [
                dict(item) for item in (suggestion.get("suggestions") or [])
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            ]
            same_span = next(
                (row for row in segments if row["start"] == start and row["end"] == end),
                None,
            )
            if same_span is not None:
                same_span["ai_suggestions"] = candidate_names
                same_span["suggestion_id"] = str(suggestion.get("id") or "")
                continue
            overlaps = [
                row for row in segments
                if row["end"] > start and row["start"] < end
            ]
            if overlaps:
                issues.append({
                    "chapter_id": chapter_id,
                    "chapter_number": chapter_number,
                    "start": start,
                    "end": end,
                    "text": exact_text,
                    "reason": "ai_suggestion_overlaps_canonical_passage",
                    "suggestion_id": str(suggestion.get("id") or ""),
                })
                continue
            segments.append({
                "start": start,
                "end": end,
                "text": exact_text,
                "kind": "needs_speaker_review",
                "speaker": None,
                "speakers": [],
                "source": "ai_suggestion",
                "needs_review": True,
                "ai_suggestions": candidate_names,
                "suggestion_id": str(suggestion.get("id") or ""),
            })

        segments.sort(key=lambda row: (row["start"], row["end"], row["kind"]))
        assignment_rows = [
            item for item in (getattr(chapter, "dialogue_assignments", []) or [])
            if isinstance(item, dict)
        ]
        chapter_passages: list[dict[str, Any]] = []
        occurrence_by_text: dict[tuple[str, str], int] = {}

        for segment in segments:
            start, end = int(segment["start"]), int(segment["end"])
            if start < 0 or end <= start or end > len(source_text):
                raise ValueError(
                    f"Dialogue segment has invalid offsets in Chapter {chapter_number}: {start}:{end}"
                )
            exact_text = source_text[start:end]
            if exact_text != str(segment["text"] or ""):
                raise ValueError(
                    f"Dialogue segment no longer matches Chapter {chapter_number} source at {start}:{end}"
                )

            family = "narration" if segment["kind"] == "narration" else "dialogue"
            text_hash = sha256(exact_text.encode("utf-8")).hexdigest()
            occurrence_key = (family, text_hash)
            occurrence = occurrence_by_text.get(occurrence_key, 0)
            occurrence_by_text[occurrence_key] = occurrence + 1
            stable_identity = f"{chapter_id}\\0{family}\\0{text_hash}\\0{occurrence}"
            passage_id = "ps_" + sha256(stable_identity.encode("utf-8")).hexdigest()[:32]

            exact_assignments = [
                item for item in assignment_rows
                if item.get("start") == start and item.get("end") == end
                and str(item.get("text") or exact_text) == exact_text
            ]
            series_values = list(dict.fromkeys(
                str(item.get("series") or "").strip()
                for item in exact_assignments if str(item.get("series") or "").strip()
            ))
            confidence_values = []
            for item in exact_assignments:
                try:
                    confidence_values.append(float(item.get("confidence")))
                except (TypeError, ValueError, OverflowError):
                    continue

            source = str(segment["source"] or "")
            needs_review = bool(segment["needs_review"])
            assignment_state = _passage_state(str(segment["kind"]), source, needs_review)
            row = {
                "passage_id": passage_id,
                "chapter_id": chapter_id,
                "chapter_number": chapter_number,
                "chapter_title": chapter_title,
                "chapter_revision": chapter_revision,
                "source_revision": source_revision,
                "start": start,
                "end": end,
                "text": exact_text,
                "kind": str(segment["kind"]),
                "speaker": segment["speaker"],
                "speakers": list(segment["speakers"] or []),
                "source": source,
                "needs_review": needs_review,
                "assignment_state": assignment_state,
                "assignment_series": series_values[0] if len(series_values) == 1 else "",
                "confidence": max(confidence_values) if confidence_values else None,
                "ai_suggestions": list(segment.get("ai_suggestions") or []),
                "suggestion_id": str(segment.get("suggestion_id") or ""),
                "dialogue": family == "dialogue",
                "source_length": end - start,
            }
            chapter_passages.append(row)
            passages.append(row)

        chapter_issues = [row for row in issues if row["chapter_id"] == chapter_id]
        chapter_counts = _passage_counts(chapter_passages)
        chapter_counts["index_issue_count"] = len(chapter_issues)
        chapter_rows.append({
            "chapter_id": chapter_id,
            "chapter_number": chapter_number,
            "chapter_title": chapter_title,
            "chapter_revision": chapter_revision,
            "passage_count": len(chapter_passages),
            "counts": chapter_counts,
            "index_issue_count": len(chapter_issues),
        })

    counts = _passage_counts(passages)
    counts["index_issue_count"] = len(issues)
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "source_revision": source_revision,
        "assignment_revision": assignment_revision,
        "index_revision": index_revision,
        "chapters": chapter_rows,
        "passages": passages,
        "issues": issues,
        "counts": counts,
    }

def _validate_index(
    index: Any,
    chapters: list[Chapter],
    suggested_passages: list[dict[str, Any]] | None = None,
) -> bool:
    if not isinstance(index, dict) or index.get("schema_version") != INDEX_SCHEMA_VERSION:
        return False
    source_revision, assignment_revision, index_revision = passage_index_revisions(chapters, suggested_passages)
    if (
        index.get("source_revision") != source_revision
        or index.get("assignment_revision") != assignment_revision
        or index.get("index_revision") != index_revision
    ):
        return False

    chapters_by_id = {
        str(getattr(chapter, "chapter_id", "") or ""): chapter
        for chapter in chapters
    }
    passages = index.get("passages")
    chapter_rows = index.get("chapters")
    if (
        not isinstance(passages, list)
        or not isinstance(chapter_rows, list)
        or not isinstance(index.get("issues", []), list)
    ):
        return False
    seen_ids: set[str] = set()
    for row in passages:
        if not isinstance(row, dict):
            return False
        passage_id = str(row.get("passage_id") or "")
        chapter_id = str(row.get("chapter_id") or "")
        chapter = chapters_by_id.get(chapter_id)
        if not passage_id or passage_id in seen_ids or chapter is None:
            return False
        seen_ids.add(passage_id)
        try:
            start, end = int(row.get("start")), int(row.get("end"))
        except (TypeError, ValueError, OverflowError):
            return False
        exact = str(chapter.text or "")
        if start < 0 or end <= start or end > len(exact):
            return False
        if exact[start:end] != str(row.get("text") or ""):
            return False
        if row.get("chapter_revision") != _digest(_chapter_source_payload(chapter)):
            return False
    return True

def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent), text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary_name).replace(path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(temporary_name).unlink(missing_ok=True)
        raise


def load_or_build_passage_index(
    project_folder: Path | str,
    chapters: list[Chapter],
    *,
    suggested_passages: list[dict[str, Any]] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Load a verified matching index or atomically rebuild it from a stable snapshot.

    A chapter edit or assignment change alters its revision and forces a rebuild.
    The source slices are validated before a persisted index is ever returned.
    Concurrent edits are detected and retried instead of persisting a mixed index.
    """
    folder = Path(project_folder).expanduser().resolve()
    path = folder / INDEX_FILENAME
    with _folder_lock(folder):
        for _attempt in range(3):
            snapshot = deepcopy(list(chapters))
            if not force and path.is_file():
                try:
                    saved = json.loads(path.read_text(encoding="utf-8"))
                    if _validate_index(saved, snapshot, suggested_passages):
                        return saved
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    pass

            rebuilt = build_passage_index(snapshot, suggested_passages)
            if passage_index_revisions(list(chapters), suggested_passages) != (
                rebuilt["source_revision"],
                rebuilt["assignment_revision"],
                rebuilt["index_revision"],
            ):
                continue
            _atomic_write_json(path, rebuilt)
            return rebuilt
    raise RuntimeError("The project changed while its dialogue index was being rebuilt. Save the chapter and retry.")


def passages_for_chapter(index: dict[str, Any], chapter_id: str) -> list[dict[str, Any]]:
    """Return canonical passages for one stable chapter identity."""
    return [
        dict(row) for row in index.get("passages", [])
        if isinstance(row, dict) and str(row.get("chapter_id") or "") == str(chapter_id)
    ]


def chapter_index_summary(index: dict[str, Any], chapter_number: int) -> dict[str, Any] | None:
    """Return the canonical per-chapter counts from the same saved source revision."""
    return next(
        (
            dict(row) for row in index.get("chapters", [])
            if isinstance(row, dict) and int(row.get("chapter_number") or 0) == int(chapter_number)
        ),
        None,
    )
