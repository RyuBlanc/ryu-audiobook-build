from __future__ import annotations

from pathlib import Path

import PyInstaller.__main__


ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "app" / "main.py"

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
