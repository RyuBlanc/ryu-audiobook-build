from pathlib import Path


_SETTINGS_ORGANIZATION = "RyuBlanc"
_SETTINGS_APPLICATION = "Ryu's Audiobook"


def _setting_value(key: str):
    """Read a persisted path without making the core path helpers depend on UI startup."""
    try:
        from PySide6.QtCore import QSettings

        return QSettings(_SETTINGS_ORGANIZATION, _SETTINGS_APPLICATION).value(key, "")
    except Exception:
        # Safe defaults keep core import/list helpers usable if QSettings is unavailable.
        return ""


def _configured_root(key: str, fallback: Path) -> Path:
    value = str(_setting_value(key) or "").strip()
    if not value:
        return fallback
    candidate = Path(value).expanduser()
    # Storage roots are selected using a native folder picker and must be absolute.
    return candidate if candidate.is_absolute() else fallback


def app_root() -> Path:
    return Path.home() / "Ryu's Audiobook"


def default_library_root() -> Path:
    """Original library location, always scanned so existing books remain discoverable."""
    return app_root() / "Library"


def library_root() -> Path:
    """Where new projects are stored; old default-location projects remain visible."""
    return _configured_root("storage/library_root", default_library_root())


def project_library_roots() -> tuple[Path, ...]:
    """Return configured and legacy project roots without scanning the same path twice."""
    roots: list[Path] = []
    seen: set[str] = set()
    for path in (library_root(), default_library_root()):
        try:
            key = str(path.resolve()).casefold()
        except OSError:
            key = str(path.absolute()).casefold()
        if key not in seen:
            roots.append(path)
            seen.add(key)
    return tuple(roots)


def voices_root() -> Path:
    return app_root() / "Voices"


def models_root() -> Path:
    return app_root() / "Models"


def default_audiobooks_root() -> Path:
    return app_root() / "Audiobooks"


def audiobooks_root() -> Path:
    """Configured default destination for new generated audiobook exports."""
    return _configured_root("storage/audio_assets_root", default_audiobooks_root())


def settings_root() -> Path:
    return app_root() / "Settings"


def audio_library_root() -> Path:
    """User-owned/licensed audiobook music and cue files."""
    return app_root() / "Audio Library"


def soundtracks_root() -> Path:
    """Local cache and previews for the generated soundtrack catalogue."""
    return app_root() / "Soundtracks"


def ensure_roots() -> None:
    # Keep support folders on the normal user profile. The original roots remain
    # available even after the user selects an external drive for new content.
    for path in (
        voices_root(),
        models_root(),
        settings_root(),
        soundtracks_root(),
        audio_library_root(),
        default_library_root(),
        default_audiobooks_root(),
    ):
        path.mkdir(parents=True, exist_ok=True)

    # A disconnected external drive must not prevent the app from launching.
    # Import/export operations surface a clear write error; Settings shows its
    # real availability and free-space state so the user can choose another root.
    for path in (library_root(), audiobooks_root()):
        if path in (default_library_root(), default_audiobooks_root()):
            continue
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
