"""Confine automated Voice Library acceptance paths to a caller-owned temporary root."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


ACCEPTANCE_ROOT_ENV = "RYU_VOICE_LIBRARY_ACCEPTANCE_ROOT"


def _is_link_or_junction(path: Path) -> bool:
    """Reject symbolic links and Windows junctions/reparse-point directories."""
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction()) if callable(is_junction) else False


def resolve_voice_library_acceptance_path(
    payload: dict[str, Any],
    key: str,
    *,
    must_exist: bool = False,
) -> Path | None:
    """Resolve one test-only path without permitting traversal or link escape.

    When the opt-in root is absent, return None so normal desktop sessions keep
    using native file dialogs. Once the root is enabled, missing, invalid, or
    out-of-root payload paths fail closed rather than opening a native dialog.
    """
    root_raw = str(os.environ.get(ACCEPTANCE_ROOT_ENV) or "").strip()
    if not root_raw:
        return None

    raw_path = str(payload.get(key) or "").strip()
    if not raw_path:
        raise ValueError(
            f"A confined Voice Library acceptance path must be supplied as '{key}'."
        )

    root_candidate = Path(root_raw).expanduser()
    if _is_link_or_junction(root_candidate):
        raise ValueError("The Voice Library acceptance root cannot be a symbolic link or junction.")
    root = root_candidate.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("The Voice Library acceptance root must be an existing directory.")

    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.absolute()

    try:
        relative_candidate = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            "Voice Library acceptance paths must stay inside the isolated acceptance directory."
        ) from exc
    if not relative_candidate.parts:
        raise ValueError("A Voice Library acceptance path must identify a file below its root.")

    # Check every existing path component before resolving. This catches a
    # symlink/junction even when its final target would still happen to be in-root.
    current = root
    for part in relative_candidate.parts:
        current = current / part
        if _is_link_or_junction(current):
            raise ValueError(
                "Voice Library acceptance paths cannot contain symbolic links or junctions."
            )

    try:
        resolved = candidate.resolve(strict=must_exist)
    except FileNotFoundError:
        if must_exist:
            raise
        resolved = candidate.resolve(strict=False)

    # Re-check caller-supplied components after canonical resolution so a
    # link introduced during resolution is not silently accepted.
    current = root
    for part in relative_candidate.parts:
        current = current / part
        if _is_link_or_junction(current):
            raise ValueError(
                "Voice Library acceptance paths cannot contain symbolic links or junctions."
            )

    try:
        relative_resolved = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            "Voice Library acceptance paths must resolve inside the isolated acceptance directory."
        ) from exc
    if not relative_resolved.parts:
        raise ValueError("A Voice Library acceptance path must identify a file below its root.")
    if not resolved.parent.is_dir():
        raise ValueError("The Voice Library acceptance destination directory is unavailable.")
    if resolved.exists() and not resolved.is_file():
        raise ValueError("The Voice Library acceptance path must identify a regular file.")
    if must_exist and not resolved.is_file():
        raise ValueError("The Voice Library acceptance bundle must be an existing regular file.")
    return resolved
