from pathlib import Path


def app_root() -> Path:
    return Path.home() / "Ryu's Audiobook"


def library_root() -> Path:
    return app_root() / "Library"


def voices_root() -> Path:
    return app_root() / "Voices"


def models_root() -> Path:
    return app_root() / "Models"


def audiobooks_root() -> Path:
    return app_root() / "Audiobooks"


def settings_root() -> Path:
    return app_root() / "Settings"


def ensure_roots() -> None:
    for path in (
        library_root(),
        voices_root(),
        models_root(),
        audiobooks_root(),
        settings_root(),
    ):
        path.mkdir(parents=True, exist_ok=True)
