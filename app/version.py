from __future__ import annotations

from app.build_info import BUILD_NUMBER

APP_NAME = "Ryu's Audiobook"
APP_VERSION = "0.3.7"
RELEASE_LABEL = f"v{APP_VERSION} • Build {BUILD_NUMBER}"


def full_version() -> str:
    """Return the build label baked into this installation at packaging time."""
    return RELEASE_LABEL
