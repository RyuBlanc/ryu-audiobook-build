from __future__ import annotations

from pathlib import Path

import PyInstaller.__main__


ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "run_app.py"
HOOKS = ROOT / "hooks"

# The application UI is packaged with a dedicated PyInstaller hook. The hook
# explicitly names every UI module and keeps source copies alongside the PYZ
# archive as a deterministic runtime fallback.
required_modules = [
    "app.ui.assembly_page",
    "app.ui.chapter_editor",
    "app.ui.generation_page",
    "app.ui.hardware_page",
    "app.ui.import_page",
    "app.ui.library",
    "app.ui.models_page",
    "app.ui.voice_page",
    "app.ui.voice_cast_page",
    "app.ui.character_review",
    "app.ui.workflow",
]

for module in required_modules:
    if not (ROOT / (module.replace(".", "/") + ".py")).exists():
        raise RuntimeError(f"Required source module is missing: {module}")

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
    # Explicitly force every UI module into the frozen import graph. The
    # application imports these modules at runtime through the workflow, but
    # keeping them explicit makes the Windows build deterministic.
    *[f"--hidden-import={module}" for module in required_modules],
    "--collect-submodules=app",
    "--paths=.",
    f"--additional-hooks-dir={HOOKS}",
    # Also keep source copies in the onedir bundle. This is an intentional
    # fallback for environments where the embedded PYZ import graph differs
    # from the source tree.
    *[
        f"--add-data={ROOT / (module.replace('.', '/') + '.py')};{module.rsplit('.', 1)[0].replace('.', '/')}"
        for module in required_modules
    ],
])
