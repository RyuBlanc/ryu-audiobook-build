from __future__ import annotations

from pathlib import Path

import PyInstaller.__main__


ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "run_app.py"

# Use a root-level launcher so app.main is imported as part of the app package.
# This preserves the relative imports used throughout the package when frozen.
# Keep the base installer small: optional AI runtimes/models are downloaded
# separately by the application. Collect FFmpeg because the core app uses it
# for audiobook assembly.
PyInstaller.__main__.run([
    str(ENTRY),
    "--name=Ryu's Audiobook",
    "--windowed",
    "--onedir",
    "--clean",
    "--noconfirm",
    "--collect-binaries=imageio_ffmpeg",
    "--collect-data=imageio_ffmpeg",
    "--hidden-import=PySide6.QtCore",
    "--hidden-import=PySide6.QtGui",
    "--hidden-import=PySide6.QtWidgets",
])
