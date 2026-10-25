"""Stable skip-state reconciliation for source-backed dialogue analysis."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def _suggestion_index(
    rows: Iterable[Mapping[str, Any]] | None,
) -> dict[str, tuple[int, int, int, str]]:
    """Map suggestion IDs to exact source identity, rejecting malformed records."""
    indexed: dict[str, tuple[int, int, int, str]] = {}
    if rows is None:
        return indexed
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        suggestion_id = str(row.get("id") or "").strip()
        try:
            chapter_number = int(row.get("chapter_number"))
            start = int(row.get("start"))
            end = int(row.get("end"))
        except (TypeError, ValueError):
            continue
        raw_text = row.get("source_text")
        if raw_text is None:
            raw_text = row.get("text")
        source_text = str(raw_text or "")
        if not suggestion_id or start < 0 or end <= start or not source_text:
            continue
        identity = (chapter_number, start, end, source_text)
        previous = indexed.get(suggestion_id)
        # A duplicated ID with inconsistent source records is ambiguous; remove
        # it from eligibility rather than accidentally preserving the wrong skip.
        if previous is not None and previous != identity:
            indexed.pop(suggestion_id, None)
            indexed[suggestion_id] = (-1, -1, -1, "")
        elif suggestion_id not in indexed:
            indexed[suggestion_id] = identity
    return indexed


def retain_current_dialogue_skips(
    previous_skips: Iterable[object] | None,
    previous_suggestions: Iterable[Mapping[str, Any]] | None,
    current_suggestions: Iterable[Mapping[str, Any]] | None,
) -> list[str]:
    """Retain skips only when the same suggestion still points at the same text.

    Premium V2 IDs encode chapter and source offsets. Offsets alone are not enough:
    edited text can occupy the same span. Comparing chapter, offsets, and exact source
    text prevents an old skip from hiding a different passage after re-analysis.
    """
    previous_index = _suggestion_index(previous_suggestions)
    current_index = _suggestion_index(current_suggestions)
    if previous_skips is None:
        return []
    if isinstance(previous_skips, (str, bytes)):
        values: Iterable[object] = [previous_skips]
    else:
        values = previous_skips

    kept: list[str] = []
    seen: set[str] = set()
    for raw_id in values:
        suggestion_id = str(raw_id or "").strip()
        if not suggestion_id or suggestion_id in seen:
            continue
        old_identity = previous_index.get(suggestion_id)
        new_identity = current_index.get(suggestion_id)
        if old_identity is None or new_identity is None or old_identity != new_identity:
            continue
        # Sentinel identities indicate duplicate IDs with conflicting source rows.
        if old_identity == (-1, -1, -1, ""):
            continue
        kept.append(suggestion_id)
        seen.add(suggestion_id)
    return kept
