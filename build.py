from __future__ import annotations

from pathlib import Path

import PyInstaller.__main__


ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "run_app.py"

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
    "--hidden-import=PySide6.QtMultimedia",
    "--hidden-import=app.ui.voice_page",
    "--hidden-import=app.ui.generation_page",
    "--hidden-import=app.ui.chapter_editor",
    "--hidden-import=app.ui.import_page",
    "--hidden-import=app.ui.library",
    "--hidden-import=app.ui.hardware_page",
    "--hidden-import=app.ui.models_page",
    "--collect-submodules=app.ui",
])
