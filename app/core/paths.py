from __future__ import annotations

from pathlib import Path

APP_NAME = "Ryu's Audiobook"


def app_root() -> Path:
    """Return the local data root used by the application."""
    root = Path.home() / "Ryu's Audiobook"
    root.mkdir(parents=True, exist_ok=True)
    return root


def library_root() -> Path:
    path = app_root() / "Library"
    path.mkdir(parents=True, exist_ok=True)
    return path


def voices_root() -> Path:
    path = app_root() / "Voices"
    path.mkdir(parents=True, exist_ok=True)
    return path


def audiobooks_root() -> Path:
    path = app_root() / "Audiobooks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_root() -> Path:
    path = app_root() / "Settings"
    path.mkdir(parents=True, exist_ok=True)
    return path
