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
from app.version import APP_VERSION

BUILD_NUMBER = os.environ.get("RYU_BUILD_NUMBER", "dev")
INSTALLER_VERSION_FILE = ROOT / "installer" / "version.generated.iss"
VERSION_INFO_FILE = ROOT / "installer" / "version_info.generated.txt"

def _numeric_version() -> tuple[int, int, int]:
    parts = [int(part) for part in APP_VERSION.split(".")]
    if len(parts) != 3:
        raise RuntimeError(f"APP_VERSION must use MAJOR.MINOR.PATCH, got {APP_VERSION!r}")
    return parts[0], parts[1], parts[2]

def write_installer_version() -> None:
    major, minor, patch = _numeric_version()
    numeric_build = BUILD_NUMBER if str(BUILD_NUMBER).isdigit() else "0"
    version_text = f"{major}.{minor}.{patch}.{numeric_build}"
    INSTALLER_VERSION_FILE.write_text(
        f"#define MyAppVersion \"{version_text}\"\n",
        encoding="utf-8",
    )
    VERSION_INFO_FILE.write_text(
        f'''VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, {numeric_build}),
    prodvers=({major}, {minor}, {patch}, {numeric_build}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'RyuBlanc'),
          StringStruct('FileDescription', "Ryu's Audiobook"),
          StringStruct('FileVersion', '{version_text}'),
          StringStruct('InternalName', "Ryu's Audiobook"),
          StringStruct('OriginalFilename', "Ryu's Audiobook.exe"),
          StringStruct('ProductName', "Ryu's Audiobook"),
          StringStruct('ProductVersion', '{version_text}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
''',
        encoding="utf-8",
    )

ENTRY = ROOT / "run_app.py"
HOOKS = ROOT / "hooks"
BUNDLED_PIPER = ROOT / "bundled_models" / "piper"
BUNDLED_KOKORO = ROOT / "bundled_models" / "kokoro"
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
            renderer.render(painter)
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
write_installer_version()

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
    "app.ai.brain",
    "app.ai.model_runtime",
    "app.version",
    "app.tts.cast_provider",
    "app.tts.chatterbox_runtime",
    "app.tts.qwen_character_runtime",
    "app.tts.providers.kokoro",
    "app.tts.providers.qwen_character",
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
    f"--version-file={VERSION_INFO_FILE}",
    "--collect-binaries=imageio_ffmpeg",
    "--collect-data=imageio_ffmpeg",
    "--collect-all=piper",
    "--collect-all=onnxruntime",
    "--collect-all=kokoro_onnx",
    "--collect-all=espeakng_loader",
    "--hidden-import=PySide6.QtCore",
    "--hidden-import=PySide6.QtGui",
    "--hidden-import=PySide6.QtWidgets",
    "--hidden-import=PySide6.QtMultimedia",
    "--hidden-import=piper",
    "--hidden-import=onnxruntime",
    "--hidden-import=kokoro_onnx",
    *[f"--hidden-import={module}" for module in required_modules],
    "--collect-submodules=app",
    "--paths=.",
    f"--additional-hooks-dir={HOOKS}",
    f"--add-data={ROOT / "requirements-voice-cloning.txt"};.",
    f"--add-data={LOGO_PNG};assets",
    f"--add-data={ROOT / "app" / "tts" / "chatterbox_worker.py"};app/tts",
    f"--add-data={ROOT / "app" / "tts" / "qwen_character_worker.py"};app/tts",
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

if BUNDLED_KOKORO.exists() and any(
    (BUNDLED_KOKORO / name).exists()
    for name in ("kokoro-v1.0.onnx", "kokoro-v1.0.fp16.onnx", "kokoro-v1.0.int8.onnx")
) and (BUNDLED_KOKORO / "voices-v1.0.bin").exists():
    args.append(f"--add-data={BUNDLED_KOKORO};bundled_models/kokoro")
else:
    raise RuntimeError(
        "Bundled offline Kokoro Natural voices are missing. "
        "The Windows workflow must download the Kokoro model and voice pack before build.py runs."
    )

PyInstaller.__main__.run(args)
