"""Load saved, project-scoped user feedback for offline novel analysis."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unicodedata
from typing import Any

from app.core.paths import settings_root
from app.core.state import load_state
from app.chapters.character_learning import (
    learning_scope_for_project,
    load_learning_examples,
)


def _read_rows(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("entries", payload.get("pronunciation_dictionary", []))
    else:
        rows = []
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _series_store_path(root: Path, series_name: str) -> Path:
    key = hashlib.sha256(
        unicodedata.normalize("NFC", series_name).casefold().encode("utf-8")
    ).hexdigest()
    return root / "pronunciation_dictionary_series" / f"{key}.json"


def _clean_pronunciation_rows(
    rows: list[dict[str, Any]],
    *,
    scope: str,
    scope_id: str,
    seen: set[str],
) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for row in rows:
        if row.get("enabled", True) is False:
            continue
        written = unicodedata.normalize("NFC", str(
            row.get("written_form") or row.get("written") or ""
        )).strip()
        spoken = unicodedata.normalize("NFC", str(
            row.get("spoken_form") or row.get("spoken") or ""
        )).strip()
        if not written or not spoken:
            continue
        if len(written) > 500 or len(spoken) > 1000:
            continue
        if any(ord(value) < 32 or ord(value) == 127 for value in written + spoken):
            continue
        key = written.casefold()
        if key in seen:
            continue
        seen.add(key)
        clean.append({
            "written_form": written,
            "spoken_form": spoken,
            "language": str(row.get("language") or row.get("source_language") or "Auto-detect"),
            "origin": str(row.get("origin") or "saved"),
            "scope": scope,
            "scope_id": scope_id,
        })
    return clean


def load_project_learning_context(project_folder: Path | str | None) -> dict[str, Any]:
    """Return only active-project/series/global saved preferences and confirmed speakers.

    The active book wins pronunciation conflicts, then its matching Series, then
    the Global Library. Disabled rows and unconfirmed speaker guesses are excluded.
    """
    if project_folder is None:
        return {
            "version": 1,
            "learning_scope": "",
            "pronunciation_memory": [],
            "speaker_learning_examples": [],
        }

    folder = Path(project_folder).expanduser()
    try:
        folder = folder.resolve()
    except OSError:
        folder = folder.absolute()

    try:
        state = load_state(folder)
    except (OSError, ValueError, TypeError):
        state = {}

    series_name = str(
        state.get("series") or state.get("series_name") or state.get("series_title") or ""
    ).strip()
    scope = learning_scope_for_project(folder)
    memory: list[dict[str, Any]] = []
    seen: set[str] = set()

    book_rows = state.get("pronunciation_dictionary")
    memory.extend(_clean_pronunciation_rows(
        book_rows if isinstance(book_rows, list) else [],
        scope="current_book",
        scope_id="",
        seen=seen,
    ))

    try:
        root = settings_root()
    except (OSError, ValueError, TypeError):
        root = None

    if root is not None:
        if series_name:
            memory.extend(_clean_pronunciation_rows(
                _read_rows(_series_store_path(root, series_name)),
                scope="series",
                scope_id=series_name,
                seen=seen,
            ))
        memory.extend(_clean_pronunciation_rows(
            _read_rows(root / "pronunciation_dictionary_global.json"),
            scope="global_library",
            scope_id="",
            seen=seen,
        ))

    speaker_examples: list[dict[str, Any]] = []
    if scope:
        try:
            examples = load_learning_examples(scope)
        except (OSError, ValueError, TypeError):
            examples = []
        for row in examples:
            if not isinstance(row, dict):
                continue
            # Only an explicit user-confirmed assignment is positive learning.
            if str(row.get("source") or "").casefold() != "explicit-user-confirmation":
                continue
            speaker = str(row.get("speaker") or "").strip()
            dialogue = str(row.get("dialogue_text") or "").strip()
            if not speaker or not dialogue:
                continue
            speaker_examples.append({
                "speaker": speaker,
                "aliases": [
                    str(value).strip()
                    for value in (row.get("aliases") or [])
                    if str(value or "").strip()
                ][:6] if isinstance(row.get("aliases") or [], list) else [],
                "dialogue_text": dialogue[:280],
                "context": str(row.get("context") or "")[:420],
                "chapter_title": str(row.get("chapter_title") or "")[:120],
                "source": "explicit-user-confirmation",
            })
        speaker_examples = speaker_examples[-16:]

    return {
        "version": 1,
        "learning_scope": scope,
        "pronunciation_memory": memory[:40],
        "speaker_learning_examples": speaker_examples,
    }
