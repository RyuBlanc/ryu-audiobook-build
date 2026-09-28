from __future__ import annotations

from pathlib import Path
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import PyInstaller.__main__
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "run_app.py"
HOOKS = ROOT / "hooks"
BUNDLED_PIPER = ROOT / "bundled_models" / "piper"
ASSETS = ROOT / "assets"
LOGO_SVG = ASSETS / "ryu_audiobook_logo.svg"
LOGO_PNG = ASSETS / "ryu_audiobook_logo.png"
LOGO_ICO = ASSETS / "ryu_audiobook_logo.ico"


def build_logo_assets() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    if not LOGO_SVG.exists():
        raise RuntimeError(f"Missing application logo source: {LOGO_SVG}")

    qt_app = QGuiApplication.instance() or QGuiApplication([])
    try:
        renderer = QSvgRenderer(str(LOGO_SVG))
        if not renderer.isValid():
            raise RuntimeError(f"Invalid application logo SVG: {LOGO_SVG}")

        image = QImage(1024, 1024, QImage.Format_RGBA8888)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        try:
            if not renderer.render(painter):
                raise RuntimeError(f"Qt failed to render application logo SVG: {LOGO_SVG}")
        finally:
            painter.end()

        if not image.save(str(LOGO_PNG), "PNG"):
            raise RuntimeError(f"Could not render application logo: {LOGO_PNG}")

        with Image.open(LOGO_PNG) as source:
            source.convert("RGBA").save(
                LOGO_ICO,
                format="ICO",
                sizes=[
                    (16, 16), (24, 24), (32, 32), (48, 48),
                    (64, 64), (128, 128), (256, 256)
                ],
            )
        if LOGO_PNG.stat().st_size < 4096:
            raise RuntimeError("Generated application PNG is unexpectedly small.")
        if LOGO_ICO.stat().st_size < 1024:
            raise RuntimeError("Generated application icon is unexpectedly small.")
    finally:
        if QGuiApplication.instance() is qt_app:
            qt_app.quit()


build_logo_assets()

required_modules = [
    "app.ui.assembly_page",
    "app.ui.chapter_editor",
    "app.ui.generation_page",
    "app.ui.import_page",
    "app.ui.library",
    "app.ui.models_page",
    "app.ui.voice_page",
    "app.ui.voice_cast_page",
    "app.ui.character_review",
    "app.tts.cast_provider",
    "app.tts.chatterbox_runtime",
    "app.ui.workflow",
]

for module in required_modules:
    if not (ROOT / (module.replace(".", "/") + ".py")).exists():
        raise RuntimeError(f"Required source module is missing: {module}")

args = [
    str(ENTRY),
    "--name=Ryu's Audiobook",
    "--windowed",
    f"--icon={LOGO_ICO}",
    "--onedir",
    "--clean",
    "--noconfirm",
    "--collect-binaries=imageio_ffmpeg",
    "--collect-data=imageio_ffmpeg",
    "--collect-all=piper",
    "--collect-all=onnxruntime",
    "--hidden-import=PySide6.QtCore",
    "--hidden-import=PySide6.QtGui",
    "--hidden-import=PySide6.QtWidgets",
    "--hidden-import=PySide6.QtMultimedia",
    "--hidden-import=piper",
    "--hidden-import=onnxruntime",
    *[f"--hidden-import={module}" for module in required_modules],
    "--collect-submodules=app",
    "--paths=.",
    f"--additional-hooks-dir={HOOKS}",
    f"--add-data={ROOT / "requirements-voice-cloning.txt"};.",
    f"--add-data={LOGO_PNG};assets",
    f"--add-data={ROOT / "app" / "tts" / "chatterbox_worker.py"};app/tts",
    *[
        f"--add-data={ROOT / (module.replace('.', '/') + '.py')};{module.rsplit('.', 1)[0].replace('.', '/')}"
        for module in required_modules
    ],
]

if BUNDLED_PIPER.exists() and any(BUNDLED_PIPER.glob("*.onnx")):
    args.append(f"--add-data={BUNDLED_PIPER};bundled_models/piper")
else:
    raise RuntimeError(
        "Bundled offline Piper voices are missing. "
        "The Windows workflow must download them before build.py runs."
    )

PyInstaller.__main__.run(args)
