"""Strict loading helpers for the installed Premium V2 frontend assets.

Keep these checks independent of Qt so missing, unreadable and empty adapter files
can be regression-tested without launching a WebEngine window.
"""
from __future__ import annotations

from pathlib import Path


class FrontendAssetError(RuntimeError):
    """Raised when an essential packaged frontend asset cannot be loaded."""


def load_premium_v2_adapter(path: Path) -> str:
    """Read a non-empty UTF-8 adapter or fail closed with an actionable error."""
    target = Path(path)
    if not target.is_file():
        raise FrontendAssetError(f"Premium V2 backend adapter is missing: {target}")

    try:
        source = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise FrontendAssetError(
            f"Premium V2 backend adapter could not be read from {target}: {exc}"
        ) from exc

    if not source.strip():
        raise FrontendAssetError(f"Premium V2 backend adapter is empty: {target}")

    return source



def premium_v2_logo_candidates(frontend_file: Path) -> tuple[Path, ...]:
    """Return packaged logo paths in the application's existing icon priority order."""
    assets_directory = Path(frontend_file).parent.parent
    return tuple(
        assets_directory / name
        for name in (
            "ryu_audiobook_logo.png",
            "ryu_audiobook_logo_master.png",
            "ryu_audiobook_logo.svg",
            "ryu_audiobook_logo.jpg",
        )
    )
