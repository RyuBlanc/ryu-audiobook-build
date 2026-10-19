from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
from typing import Any

from PySide6.QtCore import QObject, QSettings, QUrl, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from app.core.paths import app_root, ensure_roots, library_root
from app.core.project import list_projects
from app.core.state import load_state
from app.version import APP_NAME, full_version

log = logging.getLogger(__name__)

FRONTEND_RELATIVE_PATH = Path("assets") / "frontend" / "ryu_audiobook_premium_v2.html"


def frontend_path() -> Path:
    """Resolve the same self-contained HTML in source and PyInstaller builds."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / FRONTEND_RELATIVE_PATH


def _json_result(*, success: bool, data: Any = None, error: str | None = None,
                 code: str | None = None) -> str:
    payload: dict[str, Any] = {"success": success, "data": data}
    if error:
        payload["error"] = {"code": code or "operation_failed", "message": error}
    return json.dumps(payload, ensure_ascii=False, default=str)


class PremiumV2Bridge(QObject):
    """Narrow, allow-listed JSON bridge; renderer content cannot execute shell commands."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        ensure_roots()
        self.settings = QSettings("RyuBlanc", "Ryu's Audiobook")

    @Slot(str, str, result=str)
    def dispatch(self, command: str, payload_json: str = "{}") -> str:
        try:
            payload = json.loads(payload_json or "{}")
            if not isinstance(payload, dict):
                return _json_result(success=False, code="invalid_payload",
                                    error="Command payload must be a JSON object.")
            handlers = {
                "app.get_info": self._app_info,
                "app.get_capabilities": self._capabilities,
                "project.list": self._project_list,
                "settings.get": self._settings_get,
            }
            handler = handlers.get(command)
            if handler is None:
                log.warning("Premium V2 command not yet connected: %s", command)
                return _json_result(
                    success=False,
                    code="not_connected",
                    error=f"This action is not connected to the desktop backend yet: {command}",
                )
            return _json_result(success=True, data=handler(payload))
        except (ValueError, TypeError, OSError) as exc:
            log.exception("Premium V2 bridge command failed: %s", command)
            return _json_result(success=False, code="backend_error",
                                error=f"The operation could not be completed: {exc}")
        except Exception:
            log.exception("Unexpected Premium V2 bridge error: %s", command)
            return _json_result(success=False, code="internal_error",
                                error="The application encountered an unexpected error. See the local log.")

    @Slot(result=str)
    def bootstrap(self) -> str:
        """Small startup snapshot; capabilities distinguish connected from unavailable actions."""
        return json.dumps({
            "app": self._app_info({}),
            "capabilities": self._capabilities({}),
        }, ensure_ascii=False, default=str)

    def _app_info(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": APP_NAME,
            "version": full_version(),
            "storage_root": str(app_root()),
            "frontend": "Premium V2",
            "offline_first": True,
        }

    def _capabilities(self, _payload: dict[str, Any]) -> dict[str, Any]:
        # Only commands implemented in this bridge are advertised as connected.
        return {
            "app.get_info": True,
            "app.get_capabilities": True,
            "project.list": True,
            "settings.get": True,
            "project.create": False,
            "project.open": False,
            "import.start": False,
            "chapter.update": False,
            "voice.preview": False,
            "production.generate_book": False,
            "job.pause": False,
            "player.play": False,
            "reason": "The HTML host is being integrated screen by screen; unavailable actions must not report success.",
        }

    def _project_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        result = []
        for project in list_projects():
            state = load_state(project.folder)
            output_value = state.get("output_path")
            output = Path(output_value) if output_value else None
            completed = bool(output and output.is_file() and output.stat().st_size > 0
                             and str(state.get("status", "")).lower() == "completed")
            result.append({
                "title": project.title,
                "folder": str(project.folder),
                "source_path": str(project.source_path) if project.source_path else None,
                "chapter_count": len(project.chapters),
                "status": str(state.get("status") or "new"),
                "output_path": str(output) if output else None,
                "completed": completed,
            })
        return result

    def _settings_get(self, _payload: dict[str, Any]) -> dict[str, Any]:
        self.settings.sync()
        return {
            "theme": self.settings.value("ui/theme", "dark"),
            "accent": self.settings.value("ui/accent", "crimson"),
            "interface_scale": self.settings.value("ui/interface_scale", 100),
            "storage_root": str(app_root()),
            "library_root": str(library_root()),
        }


class PremiumV2Window(QMainWindow):
    """Embedded desktop host for the approved HTML; no external browser or dev server."""

    def __init__(self) -> None:
        super().__init__()
        path = frontend_path()
        if not path.is_file():
            raise FileNotFoundError(f"Premium V2 frontend asset is missing: {path}")
        self.setWindowTitle(f"{APP_NAME} • {full_version()}")
        self.resize(1440, 900)

        self.web = QWebEngineView(self)
        self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)

        self.bridge = PremiumV2Bridge(self)
        self.channel = QWebChannel(self.web.page())
        self.channel.registerObject("ryuBackend", self.bridge)
        self.web.page().setWebChannel(self.channel)
        self.web.loadFinished.connect(self._install_bridge)
        self.web.load(QUrl.fromLocalFile(str(path.resolve())))

        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web)
        self.setCentralWidget(root)

    def _install_bridge(self, ok: bool) -> None:
        if not ok:
            log.error("Premium V2 HTML failed to load from %s", frontend_path())
            return
        # The bridge is injected without altering the supplied HTML/CSS rendering.
        script = r"""
        (() => {
          const setup = () => {
            if (!window.QWebChannel || !window.qt || !qt.webChannelTransport) return false;
            new QWebChannel(qt.webChannelTransport, channel => {
              const native = channel.objects.ryuBackend;
              window.ryuBackend = Object.freeze({
                invoke(command, payload = {}) {
                  return new Promise(resolve => {
                    native.dispatch(String(command), JSON.stringify(payload || {}), raw => {
                      try { resolve(JSON.parse(raw)); }
                      catch (_) { resolve({success:false,error:{code:'invalid_response',message:'Invalid backend response.'}}); }
                    });
                  });
                },
                bootstrap() {
                  return new Promise(resolve => native.bootstrap(raw => {
                    try { resolve(JSON.parse(raw)); }
                    catch (_) { resolve({}); }
                  }));
                }
              });
              window.dispatchEvent(new CustomEvent('ryu-backend-ready'));
            });
            return true;
          };
          const load = () => {
            if (setup()) return;
            const script = document.createElement('script');
            script.src = 'qrc:///qtwebchannel/qwebchannel.js';
            script.onload = setup;
            script.onerror = () => console.error('Qt WebChannel unavailable; backend actions are not connected.');
            document.head.appendChild(script);
          };
          load();
        })();
        """
        self.web.page().runJavaScript(script)
