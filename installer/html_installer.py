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

from PySide6.QtCore import QObject, QEvent, Qt, Slot, Signal, QUrl, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QWidget

APP_TITLE = "Ryu's Audiobook Setup"
CORE_INSTALLER_NAME = "Ryu's Audiobook Core Setup.exe"
APP_EXE_NAME = "Ryu's Audiobook.exe"
BACKGROUND = "#05060A"

# Fit the visible wizard surface to the actual WebEngine viewport. The page is
# authored as a card; on some Windows DPI/display combinations Chromium lays it
# out much smaller than the host window, while on others it overflows and adds
# browser scrollbars. Fit the card itself instead of changing the UI workflow.
INSTALLER_VIEWPORT_FIT_JS = r"""
(() => {
  const html = document.documentElement;
  const body = document.body;
  if (!html || !body) return;

  // Keep the document itself inside the native window. The HTML/CSS layout
  // sizes the wizard, keeps the footer visible and scrolls only overflowing
  // content panes; do not scale the whole card and shrink its text.
  html.style.width = "100%";
  html.style.height = "100%";
  html.style.margin = "0";
  html.style.overflow = "hidden";
  body.style.width = "100%";
  body.style.height = "100vh";
  body.style.minHeight = "0";
  body.style.margin = "0";
  body.style.padding = "8px";
  body.style.overflow = "hidden";

  const style = document.getElementById("__ryuInstallerViewportFitStyle") ||
    document.createElement("style");
  style.id = "__ryuInstallerViewportFitStyle";
  style.textContent =
    "html,body{overflow:hidden!important}" +
    ".sidebar,.screens{scrollbar-width:none}" +
    ".sidebar::-webkit-scrollbar,.screens::-webkit-scrollbar," +
    "::-webkit-scrollbar{width:0!important;height:0!important}";
  if (!style.parentNode) document.head.appendChild(style);

  const wizard = body.querySelector(".installer");
  if (wizard) {
    wizard.style.minHeight = "0";
    wizard.style.maxHeight = "100%";
  }
  window.__ryuInstallerFitApplied = true;
})();
"""

SEE_MASK_NOCLOSEPROCESS = 0x00000040
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102
ERROR_CANCELLED = 1223


def _installer_window_geometry(
    available_bounds: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    """Return a compact, centered setup window with a small visible screen margin."""
    screen_x, screen_y, screen_width, screen_height = (int(value) for value in available_bounds)
    if screen_width <= 0 or screen_height <= 0:
        return screen_x, screen_y, 1180, 760
    width = min(1180, max(720, int(screen_width * 0.96)))
    height = min(760, max(540, int(screen_height * 0.94)))
    width = min(width, screen_width)
    height = min(height, screen_height)
    return (
        screen_x + (screen_width - width) // 2,
        screen_y + (screen_height - height) // 2,
        width,
        height,
    )

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
        reserve = 512 * 1024 * 1024
        enough = bool(free > 0 and required > 0 and free >= required + reserve)
        error = ""
        if free <= 0:
            error = "Windows could not determine free space for this location. Choose an existing folder or drive."
        elif required <= 0:
            error = "The installed package size could not be read. Re-download Setup."
        elif not enough:
            error = "There may not be enough free space here for the application plus a 512 MB safety reserve. Choose another drive."
        return json.dumps({
            "requested_path": path_value, "free_space_bytes": free,
            "required_size_bytes": required, "file_count": int(self._payload.get("file_count") or 0),
            "has_enough_space": enough, "safety_reserve_bytes": reserve,
            "error": error,
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
        primary_screen = QApplication.primaryScreen()
        available = primary_screen.availableGeometry() if primary_screen else None
        screen_bounds = (
            (available.x(), available.y(), available.width(), available.height())
            if available is not None else (0, 0, 1180, 760)
        )
        window_x, window_y, window_width, window_height = _installer_window_geometry(screen_bounds)
        self.setMinimumSize(min(900, window_width), min(560, window_height))
        self.resize(window_width, window_height)
        self.setStyleSheet("QMainWindow{background:" + BACKGROUND + ";}")
        self.web = QWebEngineView(self)
        # The setup UI is fitted by the host below; browser-style zoom changes
        # otherwise make the page too small or introduce page-level scrollbars.
        self.web.setZoomFactor(1.0)
        settings = self.web.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        pinch_to_zoom = getattr(QWebEngineSettings.WebAttribute, "PinchToZoomEnabled", None)
        if pinch_to_zoom is not None:
            settings.setAttribute(pinch_to_zoom, False)
        self.setCentralWidget(self.web)
        self.channel = QWebChannel(self.web.page())
        self.bridge = InstallerBridge(self)
        self.channel.registerObject("ryuInstaller", self.bridge)
        self.web.page().setWebChannel(self.channel)
        self.bridge.closeRequested.connect(self.close)
        self.web.loadFinished.connect(self._fit_page_to_viewport)
        self._drag_offset = None
        self._startup_smoke_marker = os.environ.get("RYU_INSTALLER_STARTUP_SMOKE_MARKER", "").strip()
        self._startup_smoke_attempts = 0
        if self._startup_smoke_marker:
            self.web.loadFinished.connect(self._on_startup_smoke_page_loaded)
        self.web.load(QUrl.fromLocalFile(str(page.resolve())))
        self.move(window_x, window_y)

    def _fit_page_to_viewport(self, loaded: bool = True) -> None:
        if not loaded or not hasattr(self, "web"):
            return
        self.web.setZoomFactor(1.0)
        self.web.page().runJavaScript(INSTALLER_VIEWPORT_FIT_JS)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "web"):
            QTimer.singleShot(60, self._fit_page_to_viewport)

    def _write_startup_smoke_marker(self, status: str, detail: str) -> None:
        marker_value = getattr(self, "_startup_smoke_marker", "")
        if not marker_value:
            return
        try:
            marker = Path(marker_value)
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps({"status": status, "detail": detail, "window_title": self.windowTitle()}, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            print(f"Could not write HTML installer startup marker: {exc}", file=sys.stderr)

    def _on_startup_smoke_page_loaded(self, loaded: bool) -> None:
        if not loaded:
            self._write_startup_smoke_marker("failed", "The HTML installer page did not load.")
            return
        self._probe_startup_smoke_bridge()

    def _probe_startup_smoke_bridge(self) -> None:
        self.web.page().runJavaScript("Boolean(window.__ryuInstallerBridgeReady === true)", self._on_startup_smoke_bridge_probe)

    def _on_startup_smoke_bridge_probe(self, ready: bool) -> None:
        if ready:
            self._write_startup_smoke_marker("ready", "The HTML installer page and native QWebChannel bridge are ready.")
            return
        self._startup_smoke_attempts += 1
        if self._startup_smoke_attempts >= 50:
            self._write_startup_smoke_marker("failed", "The HTML installer page loaded, but its native QWebChannel bridge did not become ready.")
            return
        QTimer.singleShot(100, self._probe_startup_smoke_bridge)

    @staticmethod
    def _resize_edges_at(x: int, y: int, width: int, height: int, margin: int = 9) -> Qt.Edge:
        edges = Qt.Edge(0)
        if x <= margin:
            edges |= Qt.Edge.LeftEdge
        elif x >= width - margin:
            edges |= Qt.Edge.RightEdge
        if y <= margin:
            edges |= Qt.Edge.TopEdge
        elif y >= height - margin:
            edges |= Qt.Edge.BottomEdge
        return edges

    def eventFilter(self, obj, event):
        # WebEngine sends mouse events to Chromium child widgets, not reliably
        # to QWebEngineView itself. Filter at QApplication level (installed in
        # main()) for window dragging and native resize gestures.
        if isinstance(obj, QWidget) and obj.window() is self:
            event_type = event.type()
            if event_type == QEvent.Type.Wheel:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    return True
            elif event_type == QEvent.Type.KeyPress:
                zoom_keys = {
                    Qt.Key.Key_Plus, Qt.Key.Key_Equal, Qt.Key.Key_Minus,
                    Qt.Key.Key_Underscore, Qt.Key.Key_0,
                }
                if (
                    event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and event.key() in zoom_keys
                ):
                    return True
            elif event_type == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                point = self.mapFromGlobal(event.globalPosition().toPoint())
                edges = self._resize_edges_at(point.x(), point.y(), self.width(), self.height())
                if edges:
                    handle = self.windowHandle()
                    if handle is not None:
                        handle.startSystemResize(edges)
                    self._drag_offset = None
                    return True
                in_drag_strip = 0 <= point.y() <= 46 and 285 <= point.x() < self.width() - 112
                if in_drag_strip:
                    handle = self.windowHandle()
                    if handle is not None and handle.startSystemMove():
                        self._drag_offset = None
                        return True
                    self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    return True
            elif event_type == QEvent.Type.MouseMove:
                point = self.mapFromGlobal(event.globalPosition().toPoint())
                edges = self._resize_edges_at(point.x(), point.y(), self.width(), self.height())
                if edges and self._drag_offset is None:
                    left = bool(edges & Qt.Edge.LeftEdge)
                    right = bool(edges & Qt.Edge.RightEdge)
                    top = bool(edges & Qt.Edge.TopEdge)
                    bottom = bool(edges & Qt.Edge.BottomEdge)
                    if (left and top) or (right and bottom):
                        cursor = Qt.CursorShape.SizeFDiagCursor
                    elif (right and top) or (left and bottom):
                        cursor = Qt.CursorShape.SizeBDiagCursor
                    elif left or right:
                        cursor = Qt.CursorShape.SizeHorCursor
                    else:
                        cursor = Qt.CursorShape.SizeVerCursor
                    self.setCursor(cursor)
                    return True
                elif self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
                    self.move(event.globalPosition().toPoint() - self._drag_offset)
                    return True
                elif not edges:
                    self.unsetCursor()
            elif event_type == QEvent.Type.MouseButtonRelease:
                self._drag_offset = None
                self.unsetCursor()
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
    # Filter mouse events for the WebEngine's internal child widgets too.
    # This keeps the custom frameless installer draggable from its top strip.
    app.installEventFilter(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
