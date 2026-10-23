from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QMainWindow
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings


PRODUCT_NAME = "Ryu's Audiobook"
SETUP_TITLE = "Ryu's Audiobook Setup"
APP_EXE_NAME = "Ryu's Audiobook.exe"


def resource_path(relative: str) -> Path:
    """Resolve a frozen PyInstaller resource or a source-tree file."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return root / relative


def _size_text(size: int) -> str:
    amount = max(0, int(size))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.0f} {unit}" if unit in {"B", "KB"} else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TB"


class InstallerBridge(QObject):
    """Small, allow-listed bridge between the styled HTML wizard and Inno Setup."""

    progressChanged = Signal(int, str, str)
    installationFinished = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self.window: InstallerWindow | None = None
        self._process: subprocess.Popen | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(450)
        self._timer.timeout.connect(self._poll_install)
        self._install_path: Path | None = None
        self._log_path: Path | None = None
        self._started = False
        self._last_elapsed_message = 0
        self._child_launch_after = True
        self._payload = resource_path("payload/Ryu's Audiobook Setup Payload.exe")
        self._manifest_path = resource_path("installer/installer_manifest.json")
        self._manifest: dict[str, Any] = {}
        try:
            value = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                self._manifest = value
        except (OSError, ValueError):
            self._manifest = {}

    @property
    def installing(self) -> bool:
        return bool(self._process and self._process.poll() is None)

    def attach_window(self, window: "InstallerWindow") -> None:
        self.window = window

    def _default_path(self) -> str:
        base = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles") or r"C:\Program Files"
        return str(Path(base) / PRODUCT_NAME)

    def _required_bytes(self) -> int:
        try:
            return max(0, int(self._manifest.get("required_install_bytes", 0)))
        except (TypeError, ValueError):
            return 0

    def _payload_ready(self) -> bool:
        return (
            self._payload.is_file()
            and self._payload.stat().st_size > 1_000_000
            and self._required_bytes() > 0
        )

    @Slot(result=str)
    def initialState(self) -> str:
        result = {
            "default_path": self._default_path(),
            "required_bytes": self._required_bytes(),
            "payload_bytes": self._payload.stat().st_size if self._payload.is_file() else 0,
            "payload_ready": self._payload_ready(),
            "error": "" if self._payload_ready() else
                "The bundled setup payload or installation manifest is missing. Re-download the complete setup package.",
        }
        return json.dumps(result)

    @staticmethod
    def _existing_drive_path(destination: Path) -> Path:
        current = destination.expanduser()
        while not current.exists() and current.parent != current:
            current = current.parent
        if not current.exists():
            raise OSError("The selected destination is not on an available drive.")
        return current

    @Slot(str, result=str)
    def checkSpace(self, destination_value: str) -> str:
        if not self._payload_ready():
            return json.dumps({
                "valid": False, "required_bytes": self._required_bytes(), "free_bytes": 0,
                "error": "The setup package is incomplete. Download the complete installer again.",
            })
        value = str(destination_value or "").strip()
        if not value:
            return json.dumps({
                "valid": False, "required_bytes": self._required_bytes(), "free_bytes": 0,
                "error": "Choose an installation folder.",
            })
        try:
            destination = Path(value).expanduser()
            drive_path = self._existing_drive_path(destination)
            disk = shutil.disk_usage(drive_path)
            required = self._required_bytes()
            enough = disk.free >= required
            return json.dumps({
                "valid": enough, "drive": str(drive_path.anchor or drive_path),
                "free_bytes": disk.free, "required_bytes": required,
                "error": "" if enough else
                    f"Not enough free disk space. Required: {_size_text(required)}; available: {_size_text(disk.free)}.",
            })
        except (OSError, ValueError, RuntimeError) as exc:
            return json.dumps({
                "valid": False, "required_bytes": self._required_bytes(), "free_bytes": 0,
                "error": f"Could not check the selected drive: {exc}",
            })

    @Slot(str, result=str)
    def chooseInstallDirectory(self, current_value: str) -> str:
        current = str(current_value or self._default_path())
        existing = Path(current).expanduser()
        if not existing.exists():
            try:
                existing = self._existing_drive_path(existing)
            except OSError:
                existing = Path(self._default_path()).parent
        selected = QFileDialog.getExistingDirectory(
            self.window,
            "Choose Ryu's Audiobook installation folder",
            str(existing),
            QFileDialog.Option.ShowDirsOnly,
        )
        return selected or ""

    @Slot(str)
    def startInstall(self, options_json: str) -> None:
        if self.installing:
            return
        try:
            options = json.loads(options_json or "{}")
            if not isinstance(options, dict):
                raise ValueError("The setup choices could not be read.")
            if options.get("accepted") is not True:
                raise ValueError("Accept the agreement before installing.")
            if not self._payload_ready():
                raise ValueError("The bundled setup payload or its manifest is missing.")
            destination_value = str(options.get("path") or "").strip()
            space = json.loads(self.checkSpace(destination_value))
            if not space.get("valid"):
                raise ValueError(space.get("error") or "Choose a valid install folder with enough free space.")
            self._install_path = Path(destination_value).expanduser().resolve()
            self._child_launch_after = bool(options.get("launchAfter", True))
            tasks: list[str] = []
            if bool(options.get("startMenu", True)):
                tasks.append("startmenuicon")
            if bool(options.get("desktopShortcut", True)):
                tasks.append("desktopicon")
            task_argument = "/TASKS=" + ",".join(tasks)
            self._log_path = Path(tempfile.gettempdir()) / "RyuAudiobook-Setup.log"
            args = [
                str(self._payload),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                f"/DIR={self._install_path}",
                task_argument,
                f"/LOG={self._log_path}",
            ]
            self.progressChanged.emit(
                -1,
                "Installing application files",
                "Windows Setup is copying the packaged application and configuring your selected shortcuts. "
                "Progress is indeterminate while the Windows installer performs its own file operations.",
            )
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self._process = subprocess.Popen(
                args,
                cwd=str(self._payload.parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
                shell=False,
            )
            self._started = True
            self._timer.start()
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self._process = None
            self._timer.stop()
            self.installationFinished.emit(False, json.dumps({"message": str(exc)}))

    def _poll_install(self) -> None:
        process = self._process
        if process is None:
            self._timer.stop()
            return
        code = process.poll()
        if code is None:
            # This status is factual; do not animate a fabricated 0–100% completion value.
            return
        self._timer.stop()
        self._process = None
        if code != 0:
            detail = f"Windows Setup exited with code {code}."
            if self._log_path and self._log_path.is_file():
                try:
                    lines = self._log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    tail = "\n".join(lines[-8:]).strip()
                    if tail:
                        detail += "\n\nInstaller log (last lines):\n" + tail[-1800:]
                except OSError:
                    pass
            self.installationFinished.emit(False, json.dumps({"message": detail}))
            return
        try:
            if self._install_path is None:
                raise OSError("The installation path was not saved.")
            app_exe = self._install_path / APP_EXE_NAME
            logo_png = self._install_path / "assets" / "ryu_audiobook_logo.png"
            if not app_exe.is_file() or app_exe.stat().st_size < 1_000_000:
                raise OSError("Windows Setup exited successfully, but the installed application executable was not found.")
            if not logo_png.is_file() or logo_png.stat().st_size < 4096:
                raise OSError("The application was installed, but its branded PNG asset is missing.")
            result = {
                "install_path": str(self._install_path),
                "app_exe": str(app_exe),
                "launch_after": self._child_launch_after,
                "verified": True,
            }
            self.progressChanged.emit(100, "Installation complete", "The application executable and transparent logo asset were verified.")
            self.installationFinished.emit(True, json.dumps(result))
        except OSError as exc:
            self.installationFinished.emit(False, json.dumps({"message": str(exc)}))

    @Slot(bool)
    def finishSetup(self, launch_after: bool) -> None:
        if launch_after and self._install_path is not None:
            app_exe = self._install_path / APP_EXE_NAME
            if app_exe.is_file():
                try:
                    subprocess.Popen([str(app_exe)], cwd=str(self._install_path), shell=False)
                except OSError as exc:
                    QMessageBox.warning(self.window, SETUP_TITLE, f"Installation succeeded, but the app could not be launched automatically:\n{exc}")
        QApplication.instance().quit()

    @Slot()
    def minimizeWindow(self) -> None:
        if self.window is not None:
            self.window.showMinimized()

    @Slot()
    def exitSetup(self) -> None:
        if self.installing:
            return
        QApplication.instance().quit()


class InstallerWindow(QMainWindow):
    def __init__(self, bridge: InstallerBridge) -> None:
        super().__init__()
        self.bridge = bridge
        bridge.attach_window(self)
        self.setWindowTitle(SETUP_TITLE)
        self.setMinimumSize(760, 560)
        self.resize(1180, 720)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        logo = resource_path("assets/ryu_audiobook_logo.png")
        if logo.is_file():
            self.setWindowIcon(QIcon(str(logo)))
        self.view = QWebEngineView(self)
        self.view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        self.view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
        )
        channel = QWebChannel(self.view.page())
        channel.registerObject("installerBridge", bridge)
        self.view.page().setWebChannel(channel)
        self.setCentralWidget(self.view)
        html_path = resource_path("installer/launcher.html")
        if not html_path.is_file():
            raise FileNotFoundError(f"Installer UI is missing: {html_path}")
        self.view.load(QUrl.fromLocalFile(str(html_path.resolve())))

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.bridge.installing:
            event.ignore()
            return
        event.accept()


def main() -> int:
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    app = QApplication(sys.argv)
    app.setApplicationName(SETUP_TITLE)
    app.setQuitOnLastWindowClosed(True)
    bridge = InstallerBridge()
    window = InstallerWindow(bridge)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
