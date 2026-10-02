from __future__ import annotations

import os

APP_NAME = "Ryu's Audiobook"
APP_VERSION = "0.3.0"
BUILD_NUMBER = os.environ.get("RYU_BUILD_NUMBER", "dev")
RELEASE_LABEL = f"v{APP_VERSION} • Build {BUILD_NUMBER}"

def full_version() -> str:
    return RELEASE_LABEL
