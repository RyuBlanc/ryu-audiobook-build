from __future__ import annotations

from pathlib import Path
from io import BytesIO
import os
import re
import struct

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import PyInstaller.__main__
from PIL import Image, ImageChops, ImageDraw
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
STARTER_AUDIO = ASSETS / "starter_audio"
LOGO_SVG = ASSETS / "ryu_audiobook_logo.svg"
LOGO_MASTER_PNG = ASSETS / "ryu_audiobook_logo_master.png"
LOGO_PNG = ASSETS / "ryu_audiobook_logo.png"
LOGO_ICO = ASSETS / "ryu_audiobook_logo.ico"
LOGO_BMP = ASSETS / "ryu_audiobook_logo.bmp"
INSTALLER_BRAND_PANEL_PNG = ASSETS / "installer_brand_panel.png"
INSTALLER_BRAND_PANEL_BMP = ASSETS / "installer_brand_panel.bmp"
DRAGON_MASTER_PNG = ASSETS / "dragon_four_winged.png"
DRAGON_CROSS_PNG = ASSETS / "dragon_cross.png"
DRAGON_CURSOR_PNG = ASSETS / "dragon_cursor.png"


def build_logo_assets() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    if not LOGO_MASTER_PNG.is_file() and not LOGO_SVG.exists():
        raise RuntimeError(f"Missing transparent application logo source: {LOGO_MASTER_PNG}")

    qt_app = QGuiApplication.instance() or QGuiApplication([])
    try:
        master = None
        if LOGO_MASTER_PNG.is_file():
            with Image.open(LOGO_MASTER_PNG) as source:
                candidate = source.convert("RGBA")
            # The checked-in HTML mock contains a 760px logo preview. Do not
            # upscale that preview and mistake it for the original high-quality
            # artwork. Only prefer a PNG master when it is genuinely full size.
            if candidate.width >= 1200 and candidate.height >= 1200:
                master = candidate

        if master is not None:
            canvas_size = (1254, 1254)
            scale = min(canvas_size[0] / master.width, canvas_size[1] / master.height)
            resized = master.resize(
                (max(1, round(master.width * scale)), max(1, round(master.height * scale))),
                Image.Resampling.LANCZOS,
            )
            rgba = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
            rgba.alpha_composite(resized, (
                (canvas_size[0] - resized.width) // 2,
                (canvas_size[1] - resized.height) // 2,
            ))
        else:
            # Render the repository's full 1254px logo artwork instead of
            # stretching the embedded 760px design preview. The declared SVG
            # clip path is rasterized below, preserving transparency.
            renderer = QSvgRenderer(str(LOGO_SVG))
            if not renderer.isValid():
                raise RuntimeError(f"Invalid application logo SVG: {LOGO_SVG}")
            source_size = renderer.defaultSize()
            if source_size.width() < 1200 or source_size.height() < 1200:
                raise RuntimeError(
                    f"Application logo source is unexpectedly small: "
                    f"{source_size.width()}x{source_size.height()}"
                )
            image = QImage(source_size, QImage.Format_RGBA8888)
            image.fill(Qt.transparent)
            painter = QPainter(image)
            try:
                renderer.render(painter)
            finally:
                painter.end()
            if not image.save(str(LOGO_PNG), "PNG"):
                raise RuntimeError(f"Could not render application logo: {LOGO_PNG}")
            with Image.open(LOGO_PNG) as source:
                rgba = source.convert("RGBA")
            if rgba.size != (source_size.width(), source_size.height()):
                raise RuntimeError(f"Application logo dimensions changed during rendering: {rgba.size}")
        alpha = rgba.getchannel("A")

        # The source SVG embeds JPEG artwork, so its alpha may be fully opaque
        # when QtSvg renders the image. Reapply the declared rounded tile clip in
        # raster form before verifying corners. This preserves all artwork color
        # and highlights; transparency comes from the geometry, not color-keying.
        svg_text = LOGO_SVG.read_text(encoding="utf-8")
        clip_match = re.search(
            r'<clipPath id="roundedBrandTile">.*?<rect[^>]*rx="([0-9.]+)"[^>]*ry="([0-9.]+)"',
            svg_text,
            re.DOTALL,
        )
        if not clip_match:
            raise RuntimeError("Logo SVG is missing its original roundedBrandTile clip path.")
        radius_x, radius_y = float(clip_match.group(1)), float(clip_match.group(2))
        if abs(radius_x - radius_y) > 0.01:
            raise RuntimeError("Logo SVG clip path must use equal horizontal and vertical radii.")

        mask_scale = 4
        mask_large = Image.new("L", (rgba.width * mask_scale, rgba.height * mask_scale), 0)
        ImageDraw.Draw(mask_large).rounded_rectangle(
            (0, 0, rgba.width * mask_scale - 1, rgba.height * mask_scale - 1),
            radius=round(radius_x * mask_scale),
            fill=255,
        )
        clip_mask = mask_large.resize(rgba.size, Image.Resampling.LANCZOS)
        rgba.putalpha(ImageChops.multiply(alpha, clip_mask))

        alpha = rgba.getchannel("A")
        corner_points = (
            (0, 0),
            (rgba.width - 1, 0),
            (0, rgba.height - 1),
            (rgba.width - 1, rgba.height - 1),
        )
        if any(alpha.getpixel(point) != 0 for point in corner_points):
            raise RuntimeError("Application logo canvas corners must remain fully transparent.")

        # Preserve alpha for the application artwork and shell icon.
        rgba.save(LOGO_PNG, format="PNG", optimize=True)

        # Inno Setup's legacy bitmap slots cannot reliably honor PNG alpha.
        # Prepare separate opaque RGB assets composited onto the exact wizard
        # background. Never flatten the logo PNG/ICO used by the app itself.
        logo_backdrop = Image.new("RGB", rgba.size, (5, 6, 10))
        logo_backdrop.paste(rgba, (0, 0), rgba.getchannel("A"))
        logo_backdrop.save(LOGO_BMP, format="BMP")
        with Image.open(LOGO_BMP) as logo_bitmap:
            if logo_bitmap.mode != "RGB" or logo_bitmap.getpixel((0, 0)) != (5, 6, 10):
                raise RuntimeError("Installer logo BMP must match WizardBackColor.")

        # Build PNG-backed ICO frames directly and reapply a rounded alpha
        # mask at every target size. Pillow's generic ICO resampler can soften
        # every 16px corner into a visible gray pixel, which is especially clear
        # against Windows Explorer's icon tile.
        icon_dimensions = [16, 24, 32, 48, 64, 128, 256]
        ico_frames = []
        for size in icon_dimensions:
            frame = rgba.resize((size, size), Image.Resampling.LANCZOS)
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (0, 0, size - 1, size - 1),
                radius=max(1, round(radius_x * size / rgba.width)),
                fill=255,
            )
            frame.putalpha(ImageChops.multiply(frame.getchannel("A"), mask))
            with BytesIO() as buffer:
                frame.save(buffer, format="PNG", optimize=True)
                ico_frames.append((size, buffer.getvalue()))

        directory = bytearray(struct.pack("<HHH", 0, 1, len(ico_frames)))
        offset = 6 + 16 * len(ico_frames)
        for size, payload in ico_frames:
            dimension_byte = 0 if size == 256 else size
            directory.extend(struct.pack(
                "<BBBBHHII",
                dimension_byte, dimension_byte, 0, 0, 1, 32, len(payload), offset,
            ))
            offset += len(payload)
        with LOGO_ICO.open("wb") as icon_output:
            icon_output.write(directory)
            for _size, payload in ico_frames:
                icon_output.write(payload)

        # Confirm the ICO actually contains every Windows shell size we expect.
        # A non-empty ICO alone can still contain only a single small frame.
        required_ico_sizes = {
            (16, 16), (24, 24), (32, 32), (48, 48),
            (64, 64), (128, 128), (256, 256),
        }
        with Image.open(LOGO_ICO) as icon_file:
            icon_sizes = icon_file.ico.sizes()
            missing_sizes = required_ico_sizes - icon_sizes
            if missing_sizes:
                missing_text = ", ".join(
                    f"{width}x{height}" for width, height in sorted(missing_sizes)
                )
                raise RuntimeError(f"Windows ICO is missing required icon sizes: {missing_text}")
            for icon_size in sorted(required_ico_sizes):
                icon_frame = icon_file.ico.getimage(icon_size).convert("RGBA")
                icon_alpha = icon_frame.getchannel("A")
                alpha_min, alpha_max = icon_alpha.getextrema()
                alpha_histogram = icon_alpha.histogram()
                visible_pixels = sum(alpha_histogram[32:])
                pixel_count = icon_size[0] * icon_size[1]
                # At 16px, anti-aliasing over an intricate logo can mean no
                # pixel reaches exactly 255. Require transparent pixels plus
                # a strong visible alpha range and enough non-transparent
                # artwork, instead of requiring a perfectly opaque pixel.
                if (
                    alpha_min > 16
                    or alpha_max < 128
                    or visible_pixels < pixel_count * 0.20
                ):
                    width, height = icon_size
                    raise RuntimeError(
                        f"Windows ICO {width}x{height} has invalid transparency/artwork: "
                        f"alpha range={alpha_min}..{alpha_max}, "
                        f"visible pixels={visible_pixels}/{pixel_count}."
                    )

        # Inno Setup uses a portrait image slot on the Welcome/Finished pages.
        # Build a transparent composition that places the logo artwork at the
        # top without stretching it or painting a tile behind it.
        panel = Image.new("RGBA", (656, 1256), (0, 0, 0, 0))
        panel_logo = rgba.copy()
        panel_logo.thumbnail((560, 560), Image.Resampling.LANCZOS)
        panel.alpha_composite(
            panel_logo,
            ((panel.width - panel_logo.width) // 2, 52),
        )
        draw = ImageDraw.Draw(panel)
        divider_y = 705
        draw.line(
            (118, divider_y, 538, divider_y),
            fill=(214, 176, 106, 190),
            width=3,
        )
        draw.polygon(
            (
                (328, divider_y - 10),
                (338, divider_y),
                (328, divider_y + 10),
                (318, divider_y),
            ),
            fill=(255, 240, 185, 235),
        )
        panel.save(INSTALLER_BRAND_PANEL_PNG, format="PNG", optimize=True)
        panel_bitmap = Image.new("RGB", panel.size, (5, 6, 10))
        panel_bitmap.paste(panel, (0, 0), panel.getchannel("A"))
        panel_bitmap.save(INSTALLER_BRAND_PANEL_BMP, format="BMP")
        with Image.open(INSTALLER_BRAND_PANEL_BMP) as bitmap_check:
            if bitmap_check.mode != "RGB" or bitmap_check.getpixel((0, 0)) != (5, 6, 10):
                raise RuntimeError("Installer brand BMP must match WizardBackColor.")
        with Image.open(INSTALLER_BRAND_PANEL_PNG) as panel_check:
            panel_alpha = panel_check.getchannel("A")
            if panel_check.size != panel.size or any(
                panel_alpha.getpixel(point) != 0
                for point in ((0, 0), (panel.width - 1, 0),
                              (0, panel.height - 1), (panel.width - 1, panel.height - 1))
            ):
                raise RuntimeError("Installer brand panel must keep a transparent canvas.")
        if LOGO_PNG.stat().st_size < 4096:
            raise RuntimeError("Generated application PNG is unexpectedly small.")
        if LOGO_ICO.stat().st_size < 1024:
            raise RuntimeError("Generated application icon is unexpectedly small.")
        if LOGO_BMP.stat().st_size < 4096 or INSTALLER_BRAND_PANEL_BMP.stat().st_size < 4096:
            raise RuntimeError("Generated Inno Setup bitmaps are unexpectedly small.")

        # Use the supplied four-winged dragon artwork, not a replacement SVG.
        # It is already transparent and cursor-sized; copying it preserves the
        # silhouette and wing outline without redrawing or cropping it.
        if not DRAGON_MASTER_PNG.is_file():
            raise RuntimeError(f"Missing supplied dragon artwork: {DRAGON_MASTER_PNG}")
        for output_png in (DRAGON_CROSS_PNG, DRAGON_CURSOR_PNG):
            with Image.open(DRAGON_MASTER_PNG) as source:
                dragon_image = source.convert("RGBA")
                if dragon_image.width < 24 or dragon_image.height < 24:
                    raise RuntimeError("Supplied four-winged dragon artwork is too small.")
                dragon_image.save(output_png, format="PNG", optimize=True)
            if output_png.stat().st_size < 512:
                raise RuntimeError(f"Generated dragon UI asset is unexpectedly small: {output_png}")
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
    "app.audio.library",
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
    "--collect-all=PySide6.QtWebEngineCore",
    "--collect-all=PySide6.QtWebEngineWidgets",
    "--collect-all=PySide6.QtWebChannel",
    "--collect-all=piper",
    "--collect-all=onnxruntime",
    "--collect-all=kokoro_onnx",
    "--collect-all=espeakng_loader",
    "--hidden-import=PySide6.QtCore",
    "--hidden-import=PySide6.QtGui",
    "--hidden-import=PySide6.QtWidgets",
    "--hidden-import=PySide6.QtMultimedia",
    "--hidden-import=PySide6.QtSvg",
    "--hidden-import=PySide6.QtWebEngineCore",
    "--hidden-import=PySide6.QtWebEngineWidgets",
    "--hidden-import=PySide6.QtWebChannel",
    "--hidden-import=piper",
    "--hidden-import=onnxruntime",
    "--hidden-import=kokoro_onnx",
    *[f"--hidden-import={module}" for module in required_modules],
    "--collect-submodules=app",
    "--paths=.",
    f"--additional-hooks-dir={HOOKS}",
    f"--add-data={ROOT / "requirements-voice-cloning.txt"};.",
    f"--add-data={LOGO_PNG};assets",
    f"--add-data={DRAGON_CROSS_PNG};assets",
    f"--add-data={DRAGON_CURSOR_PNG};assets",
    f"--add-data={ROOT / 'assets' / 'frontend' / 'ryu_audiobook_premium_v2.html'};assets/frontend",
    f"--add-data={ROOT / 'assets' / 'frontend' / 'premium_v2_backend_adapter.js'};assets/frontend",
    f"--add-data={ROOT / "app" / "tts" / "chatterbox_worker.py"};app/tts",
    f"--add-data={ROOT / "app" / "tts" / "expression.py"};app/tts",
    f"--add-data={ROOT / "app" / "tts" / "qwen_character_worker.py"};app/tts",
    *[
        f"--add-data={ROOT / (module.replace('.', '/') + '.py')};{module.rsplit('.', 1)[0].replace('.', '/')}"
        for module in required_modules
    ],
]

if STARTER_AUDIO.is_dir() and (STARTER_AUDIO / "manifest.json").is_file():
    if not any(STARTER_AUDIO.rglob("*.mp3")) and not any(STARTER_AUDIO.rglob("*.wav")) and not any(STARTER_AUDIO.rglob("*.ogg")) and not any(STARTER_AUDIO.rglob("*.flac")):
        raise RuntimeError("Starter audio pack has no downloaded files.")
    args.append(f"--add-data={STARTER_AUDIO};assets/starter_audio")
else:
    raise RuntimeError("Bundled starter audio manifest is missing.")


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
