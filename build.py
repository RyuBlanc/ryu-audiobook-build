from __future__ import annotations

import PyInstaller.__main__


PyInstaller.__main__.run([
    "app/main.py",
    "--name=Ryu's Audiobook",
    "--windowed",
    "--onedir",
    "--clean",
])
