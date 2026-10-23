from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import Any

from PySide6.QtCore import QObject, QEvent, Qt, Slot, Signal, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow

APP_TITLE = "Ryu's Audiobook Setup"
CORE_INSTALLER_NAME = "Ryu's Audiobook Core Setup.exe"
APP_EXE_NAME = "Ryu's Audiobook.exe"
BACKGROUND = "#05060A"
SEE_MASK_NOCLOSEPROCESS = 0x00000040
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102
ERROR_CANCELLED = 1223


def resource_path(relative: str) -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / relative


def _payload_info() -> dict[str, Any]:
    try:
        value = json.loads(resource_path("installer/payload_info.generated.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _existing_parent(path: Path) -> Path:
    while not path.exists() and path != path.parent:
        path = path.parent
    return path


def _free_bytes(path_value: str) -> int:
    try:
        return int(shutil.disk_usage(str(_existing_parent(Path(os.path.abspath(path_value)) ))).free)
    except (OSError, ValueError):
        return 0


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG), ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HANDLE),
        ("dwHotKey", wintypes.DWORD), ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
    ]


class InstallerBridge(QObject):
    statusChanged = Signal(str)
    closeRequested = Signal()

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self.window = window
        self._lock = threading.RLock()
        self._worker: threading.Thread | None = None
        self._payload = _payload_info()
        self._status: dict[str, Any] = {
            "state": "idle", "phase": "Ready to install",
            "message": "Review your destination and shortcut options.",
            "progress": None, "install_path": "", "files_started": False,
            "shortcuts_started": False, "exit_code": None,
        }

    def _set_status(self, **changes: Any) -> None:
        with self._lock:
            self._status.update(changes)
            snapshot = json.dumps(self._status, ensure_ascii=False)
        self.statusChanged.emit(snapshot)

    @staticmethod
    def _default_directory() -> str:
        root = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles") or r"C:\Program Files"
        return str(Path(root) / "Ryu's Audiobook")

    @Slot(result=str)
    def getEnvironment(self) -> str:
        directory = self._default_directory()
        return json.dumps({
            "default_dir": directory, "version": str(self._payload.get("version") or "—"),
            "required_size_bytes": int(self._payload.get("installed_size_bytes") or 0),
            "file_count": int(self._payload.get("file_count") or 0),
            "free_space_bytes": _free_bytes(directory),
        }, ensure_ascii=False)

    @Slot(str, result=str)
    def getEnvironmentForPath(self, path_value: str) -> str:
        path_value = str(path_value or self._default_directory()).strip()
        if not path_value:
            return json.dumps({"error": "Choose an installation folder first."})
        required = int(self._payload.get("installed_size_bytes") or 0)
        free = _free_bytes(path_value)
        return json.dumps({
            "requested_path": path_value, "free_space_bytes": free,
            "required_size_bytes": required, "file_count": int(self._payload.get("file_count") or 0),
            "has_enough_space": bool(free and (not required or free >= required + 512 * 1024 * 1024)),
            "error": "There may not be enough free space here. Choose another drive."
                if free and required and free < required + 512 * 1024 * 1024 else "",
        }, ensure_ascii=False)

    @Slot(str, result=str)
    def selectDirectory(self, current_path: str) -> str:
        return QFileDialog.getExistingDirectory(
            self.window, "Choose Ryu's Audiobook installation folder",
            str(current_path or self._default_directory()),
        ) or ""

    @Slot(result=str)
    def getStatus(self) -> str:
        with self._lock:
            return json.dumps(self._status, ensure_ascii=False)

    @Slot(str, result=bool)
    def startInstall(self, payload_json: str) -> bool:
        with self._lock:
            if self._status.get("state") == "running":
                return False
        try:
            payload = json.loads(payload_json or "{}")
            if not isinstance(payload, dict):
                raise ValueError("Setup options are invalid.")
            destination = os.path.abspath(str(payload.get("install_path") or "").strip())
            if not destination:
                raise ValueError("Choose an installation folder first.")
            drive, tail = os.path.splitdrive(destination)
            if drive and not tail.strip("\\/"):
                raise ValueError("Choose a folder below the drive root, not the drive root itself.")
            core = resource_path("installer/" + CORE_INSTALLER_NAME)
            if not core.is_file():
                raise FileNotFoundError("The bundled core installer is missing. Re-download Setup.")
            required = int(self._payload.get("installed_size_bytes") or 0)
            free = _free_bytes(destination)
            if free and required and free < required + 512 * 1024 * 1024:
                raise ValueError("There may not be enough free space in this destination.")
            tasks = []
            if bool(payload.get("desktop_shortcut")):
                tasks.append("desktopicon")
            if bool(payload.get("start_menu")):
                tasks.append("startmenuicon")
            log_path = Path(tempfile.gettempdir()) / "RyuAudiobook-setup.log"
            params = [
                "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                '/DIR="' + destination + '"', '/LOG="' + str(log_path) + '"',
            ]
            if tasks:
                params.append('/TASKS="' + ",".join(tasks) + '"')
            self._set_status(
                state="running", phase="Requesting administrator permission",
                message="Windows may display a permission prompt before installing files.",
                progress=None, install_path=destination, files_started=False,
                shortcuts_started=False, exit_code=None, log_path=str(log_path),
                launch_after=bool(payload.get("launch_after")),
            )
            self._worker = threading.Thread(
                target=self._run_installer,
                args=(core, " ".join(params), destination, log_path),
                daemon=True, name="RyuHtmlInstallerWorker",
            )
            self._worker.start()
            return True
        except (OSError, ValueError, TypeError) as exc:
            self._set_status(state="failed", phase="Setup validation failed",
                             message=str(exc), progress=None, exit_code=None)
            return False

    def _run_installer(self, executable: Path, parameters: str, destination: str, log_path: Path) -> None:
        if os.name != "nt":
            self._set_status(state="failed", phase="Unsupported platform",
                             message="The packaged installer runs on Windows only.", exit_code=-1)
            return
        info = SHELLEXECUTEINFOW()
        info.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
        info.fMask = SEE_MASK_NOCLOSEPROCESS
        info.lpVerb = "runas"
        info.lpFile = str(executable)
        info.lpParameters = parameters
        info.lpDirectory = str(executable.parent)
        info.nShow = 0
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
        shell32.ShellExecuteExW.restype = wintypes.BOOL
        if not shell32.ShellExecuteExW(ctypes.byref(info)):
            code = ctypes.get_last_error()
            if code == ERROR_CANCELLED:
                self._set_status(state="cancelled", phase="Permission cancelled",
                                 message="Administrator permission was cancelled. Setup did not complete.",
                                 exit_code=code)
            else:
                self._set_status(state="failed", phase="Could not start installer",
                                 message="Windows could not start Setup (error " + str(code) + ").",
                                 exit_code=code)
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        seen_lines, last_phase = 0, ""
        try:
            while True:
                result = kernel32.WaitForSingleObject(info.hProcess, 500)
                if result == WAIT_OBJECT_0:
                    break
                if result != WAIT_TIMEOUT:
                    raise OSError("Could not observe the Windows installer process.")
                try:
                    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines() if log_path.is_file() else []
                except OSError:
                    lines = []
                if len(lines) != seen_lines:
                    seen_lines = len(lines)
                    recent = "\n".join(lines[-100:]).casefold()
                    if "creating shortcuts" in recent:
                        phase, message = "Creating shortcuts", "Finishing shortcut creation and registration."
                    else:
                        phase, message = "Installing application files", "The Windows installer is copying the bundled files."
                    if phase != last_phase:
                        self._set_status(phase=phase, message=message,
                                         files_started=phase == "Installing application files",
                                         shortcuts_started=phase == "Creating shortcuts")
                        last_phase = phase
            exit_code = wintypes.DWORD(1)
            if not kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code)):
                raise ctypes.WinError(ctypes.get_last_error())
            code = int(exit_code.value)
        except Exception as exc:
            self._set_status(state="failed", phase="Could not verify installation",
                             message="Setup ran but its result could not be verified: " + str(exc), exit_code=-1)
            return
        finally:
            if info.hProcess:
                kernel32.CloseHandle(info.hProcess)
        if code == 0:
            self._set_status(state="completed", phase="Installation complete",
                             message="The Windows installer finished successfully.", progress=100,
                             exit_code=0, files_started=True, shortcuts_started=True, install_path=destination)
        else:
            try:
                tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-8:])
            except OSError:
                tail = ""
            message = "The Windows installer exited with code " + str(code) + "."
            if tail:
                message += " Details: " + tail[-700:]
            self._set_status(state="failed", phase="Installation failed",
                             message=message, progress=None, exit_code=code, install_path=destination)

    @Slot()
    def minimize(self) -> None:
        self.window.showMinimized()

    @Slot()
    def exitInstaller(self) -> None:
        with self._lock:
            if self._status.get("state") == "running":
                return
        self.closeRequested.emit()

    @Slot(bool)
    def finish(self, launch_after: bool) -> None:
        with self._lock:
            if self._status.get("state") != "completed":
                return
            destination = str(self._status.get("install_path") or "")
        if launch_after:
            exe = Path(destination) / APP_EXE_NAME
            if exe.is_file():
                try:
                    subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                except OSError:
                    pass
        self.closeRequested.emit()


class InstallerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        page = resource_path("installer/ryu_installer.html")
        if not page.is_file():
            raise FileNotFoundError("The HTML setup page is missing from the package.")
        icon = resource_path("assets/ryu_audiobook_logo.ico")
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))
        self.setWindowTitle(APP_TITLE)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.resize(1180, 760)
        self.setMinimumSize(960, 680)
        self.setStyleSheet("QMainWindow{background:" + BACKGROUND + ";}")
        self.web = QWebEngineView(self)
        settings = self.web.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.setCentralWidget(self.web)
        self.channel = QWebChannel(self.web.page())
        self.bridge = InstallerBridge(self)
        self.channel.registerObject("ryuInstaller", self.bridge)
        self.web.page().setWebChannel(self.channel)
        self.bridge.closeRequested.connect(self.close)
        self.web.installEventFilter(self)
        self.web.load(QUrl.fromLocalFile(str(page.resolve())))
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.x() + (screen.width() - self.width()) // 2,
                  screen.y() + (screen.height() - self.height()) // 2)

    def eventFilter(self, obj, event):
        if obj is self.web and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 46:
                handle = self.windowHandle()
                if handle is not None and handle.startSystemMove():
                    return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event) -> None:
        with self.bridge._lock:
            busy = self.bridge._status.get("state") == "running"
        if busy:
            event.ignore()
        else:
            event.accept()


def main() -> int:
    if os.name != "nt":
        raise RuntimeError("Ryu's Audiobook Setup is a Windows-only installer.")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    window = InstallerWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
