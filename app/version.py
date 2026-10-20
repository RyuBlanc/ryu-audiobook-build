from __future__ import annotations

from app.build_info import BUILD_NUMBER

APP_NAME = "Ryu's Audiobook"
# Version convention: major stable update.feature/update revision.bug-fix revision.
APP_VERSION = "1.1.1"
RELEASE_LABEL = f"v{APP_VERSION} • Build {BUILD_NUMBER}"


def full_version() -> str:
    """Return the build label baked into this installation at packaging time."""
    return RELEASE_LABEL
