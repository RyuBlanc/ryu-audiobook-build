from __future__ import annotations

from pathlib import Path

import PyInstaller.__main__
from PyInstaller.utils.hooks import collect_submodules


ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "run_app.py"

# Keep UI discovery deterministic.  PyInstaller can miss modules that are
# imported indirectly from a package, so collect the complete UI package and
# fail the build if a required page cannot be discovered.
UI_HIDDEN_IMPORTS = collect_submodules("app.ui", on_error="raise")
REQUIRED_UI_MODULES = {
    "app.ui.voice_page",
    "app.ui.generation_page",
    "app.ui.chapter_editor",
    "app.ui.import_page",
    "app.ui.library",
    "app.ui.hardware_page",
    "app.ui.models_page",
}
missing = REQUIRED_UI_MODULES.difference(UI_HIDDEN_IMPORTS)
if missing:
    raise RuntimeError(
        "PyInstaller could not discover required UI modules: "
        + ", ".join(sorted(missing))
    )

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
    "--collect-submodules=app",
    "--collect-submodules=app.ui",
    "--paths=.",
    *[f"--hidden-import={module}" for module in UI_HIDDEN_IMPORTS],
])
