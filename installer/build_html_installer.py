from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]
APP_DIST = ROOT / "dist" / "Ryu's Audiobook"
OUTPUT = ROOT / "installer" / "installer-output"
CORE_INSTALLER = OUTPUT / "Ryu's Audiobook Core Setup.exe"
HTML = ROOT / "installer" / "ryu_installer.html"
HTML_JS = ROOT / "installer" / "ryu_installer.js"
LOGO_PNG = ROOT / "assets" / "ryu_audiobook_logo.png"
LOGO_ICO = ROOT / "assets" / "ryu_audiobook_logo.ico"
PAYLOAD_INFO = ROOT / "installer" / "payload_info.generated.json"
APP_EXE = APP_DIST / "Ryu's Audiobook.exe"


def main() -> None:
    for path in (APP_DIST, APP_EXE, CORE_INSTALLER, HTML, HTML_JS, LOGO_PNG, LOGO_ICO):
        if not path.is_file():
            raise RuntimeError(f"Required installer input is missing: {path}")
    package_files = [path for path in APP_DIST.rglob("*") if path.is_file()]
    installed_bytes = sum(path.stat().st_size for path in package_files)
    from app.version import APP_VERSION
    build_number = os.environ.get("RYU_BUILD_NUMBER", "dev")
    version = str(APP_VERSION) + ("+build." + build_number if build_number.isdigit() else "")
    PAYLOAD_INFO.write_text(json.dumps({
        "version": version,
        "installed_size_bytes": installed_bytes,
        "file_count": len(package_files),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    work = ROOT / "build" / "html-installer-work"
    shutil.rmtree(work, ignore_errors=True)
    args = [
        str(ROOT / "installer" / "html_installer.py"),
        "--name=Ryu's Audiobook Setup", "--onefile", "--windowed",
        "--noconfirm", "--clean", f"--distpath={OUTPUT}",
        f"--workpath={work}", f"--specpath={ROOT / 'build' / 'html-installer-spec'}",
        f"--icon={LOGO_ICO}",
        f"--add-data={HTML};installer",
        f"--add-data={HTML_JS};installer",
        f"--add-data={CORE_INSTALLER};installer",
        f"--add-data={LOGO_PNG};assets",
        f"--add-data={LOGO_ICO};assets",
        f"--add-data={PAYLOAD_INFO};installer",
        "--collect-all=PySide6.QtWebEngineCore",
        "--collect-all=PySide6.QtWebEngineWidgets",
        "--collect-all=PySide6.QtWebChannel",
        "--hidden-import=PySide6.QtNetwork",
        "--hidden-import=shiboken6",
    ]
    PyInstaller.__main__.run(args)
    output = OUTPUT / "Ryu's Audiobook Setup.exe"
    if not output.is_file() or output.stat().st_size < CORE_INSTALLER.stat().st_size:
        raise RuntimeError("Functional HTML setup package was not created or is unexpectedly small.")
    print(f"Created HTML installer: {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
