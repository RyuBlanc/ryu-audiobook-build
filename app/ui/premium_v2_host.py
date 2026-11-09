from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import uuid
import wave
from datetime import datetime, timezone
from typing import Any

from PySide6.QtCore import QObject, QSettings, QTimer, QUrl, Slot, Qt
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMainWindow, QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget
from PySide6.QtGui import QDesktopServices, QImageReader, QPixmap

from app.core.paths import app_root, audiobooks_root, ensure_roots, library_root, settings_root, models_root, runtimes_root
from app.audio.playback import is_iso_bmff_file, prepare_audiobook_playback_source
from app.ui.frontend_assets import (
    FrontendAssetError,
    load_premium_v2_adapter,
    premium_v2_logo_candidates,
    prepare_native_host_html,
)
from app.core.project import Project, create_project, list_projects, resolve_library_project_folder
from app.core.character_identity import character_identity_key
from app.core.character_library import (
    character_library_path as reusable_character_library_path,
    list_characters as list_reusable_characters,
    list_deleted_characters as list_reusable_deleted_characters,
    prune_invalid_character_records,
    restore_character as restore_reusable_character,
    soft_delete_character as soft_delete_reusable_character,
    sync_characters as sync_reusable_characters,
    update_character as update_reusable_character,
)
from app.documents.cover_art import MAX_COVER_BYTES, COVER_IMAGE_EXTENSIONS, COVER_SOURCE_EXTENSIONS, extract_embedded_cover, persist_project_cover
from app.documents.parser import (
    SUPPORTED_EXTENSIONS, clean_import_noise, clean_text, detect_repeated_book_noise,
    extract_text, validate_chapter_text_coverage,
)
from app.chapters.detector import detect_chapters
from app.chapters.characters import (
    analyze_book, merge_character_analysis_record, is_likely_character_name,
    is_user_confirmed_character_record,
)
from app.chapters.dialogue_review import retain_current_dialogue_skips
from app.tts.manager import GenerationManager
from app.tts.preview import build_voice_preview
from app.tts.profile_provider import provider_from_profile
from app.tts.pronunciation_suggester import suggest_names_from_text, suggest_pronunciation
from app.tts.voice_profile import load_profiles
from app.core.state import load_state, save_state
from app.production_metadata import missing_required_metadata_fields, normalize_metadata_text
from app.version import APP_NAME, full_version

log = logging.getLogger(__name__)

def _preview_requires_paragraph_boundary(state: dict[str, Any]) -> bool:
    """Keep the selected Production preview paragraph-aligned only when its saved BGM needs it."""
    if not isinstance(state, dict) or not state.get("_include_sound_design_preview"):
        return False
    from app.audio.library import effective_background_audio_mode
    if effective_background_audio_mode(state) == "off":
        return False
    overrides = state.get("chapter_bgm_overrides")
    if not isinstance(overrides, dict):
        return False
    strategy = str(state.get("chapter_bgm_strategy") or ("custom" if overrides else "same")).strip().casefold()
    if strategy not in {"custom", "chapter-based", "chapter_based", "chapter"}:
        return False
    chapter_id = str(state.get("_preview_chapter_id") or "").strip()
    selected = overrides.get(chapter_id) if chapter_id else None
    if not isinstance(selected, dict):
        number = str(state.get("_preview_chapter_number") or "").strip()
        selected = overrides.get(number, {}) if number else {}
    if not isinstance(selected, dict):
        return False
    rule = str(selected.get("rule") or "none").strip().casefold()
    offset = str(selected.get("start_offset") or "immediate").strip().casefold()
    return rule == "custom" and offset == "after_first_paragraph"




def _generation_worker_is_alive(manager: Any) -> bool:
    thread = getattr(manager, "_thread", None)
    return bool(thread is not None and thread.is_alive())


FRONTEND_RELATIVE_PATH = Path("assets") / "frontend" / "ryu_audiobook_premium_v2.html"


def frontend_path() -> Path:
    """Resolve the same self-contained HTML in source and PyInstaller builds."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / FRONTEND_RELATIVE_PATH


def _parse_audio_chapter_metadata(probe_output: str) -> list[dict[str, Any]]:
    """Parse FFmpeg chapter metadata without inventing chapter boundaries."""
    source = str(probe_output or "")
    header = re.compile(
        r"(?m)^\s*Chapter #\d+:(\d+):\s*start\s+(\d+(?:\.\d+)?),\s*end\s+(\d+(?:\.\d+)?)",
        flags=re.IGNORECASE,
    )
    matches = list(header.finditer(source))
    chapters: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        stop = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        block = source[match.start():stop]
        title_match = re.search(r"(?mi)^\s*title\s*:\s*(.+?)\s*$", block)
        try:
            start_seconds = float(match.group(2))
            end_seconds = float(match.group(3))
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(start_seconds) or not math.isfinite(end_seconds):
            continue
        if start_seconds < 0 or end_seconds <= start_seconds:
            continue
        number = int(match.group(1)) + 1
        title = title_match.group(1).strip() if title_match else f"Chapter {number}"
        chapters.append({
            "number": number,
            "title": title[:500] or f"Chapter {number}",
            "start_seconds": start_seconds,
            "end_seconds": end_seconds,
        })
    return chapters


def _read_audio_chapter_metadata(path: Path) -> list[dict[str, Any]]:
    """Read embedded M4B chapter boundaries quickly; treat missing metadata as optional."""
    try:
        candidate = Path(path)
        if not candidate.is_file() or candidate.stat().st_size < 1024:
            return []
        from app.audio.assembler import ffmpeg_path

        probe = subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-i", str(candidate)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return _parse_audio_chapter_metadata(str(probe.stderr or "") + "\n" + str(probe.stdout or ""))
    except Exception:
        log.debug("Could not read embedded audiobook chapter metadata from %s", path, exc_info=True)
        return []


def _json_result(*, success: bool, data: Any = None, error: str | None = None,
                 code: str | None = None) -> str:
    payload: dict[str, Any] = {"success": success, "data": data}
    if error:
        payload["error"] = {"code": code or "operation_failed", "message": error}
    return json.dumps(payload, ensure_ascii=False, default=str)


def _normalize_pronunciation_text(value: Any, field: str, limit: int) -> str:
    """Validate and NFC-normalize a saved pronunciation field."""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text.")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        raise ValueError(f"{field} is required.")
    if len(normalized) > limit:
        raise ValueError(f"{field} must be {limit} characters or fewer.")
    if any(ord(char) < 32 or ord(char) == 127 for char in normalized):
        raise ValueError(f"{field} cannot contain control characters.")
    return normalized


def _parse_pronunciation_scope(value: Any, scope_id: Any = None) -> tuple[str, str, str]:
    """Return scope type, scope id, and stable UI label; reject unsupported scope text."""
    raw = unicodedata.normalize("NFC", str(value or "current_book")).strip()
    folded = raw.casefold().replace("_", " ").replace("-", " ")
    if folded in {"current book", "book", "current"}:
        return "current_book", "", "Current book"
    if folded in {"global library", "global", "library"}:
        return "global_library", "", "Global library"
    series_name = str(scope_id or "").strip()
    match = re.fullmatch(r"series\s*[·:]\s*(.+)", raw, flags=re.IGNORECASE)
    if match:
        series_name = match.group(1).strip()
    elif folded == "series" and series_name:
        pass
    else:
        raise ValueError("Choose Current book, Global library, or a named Series scope.")
    series_name = _normalize_pronunciation_text(series_name, "Series name", 120)
    return "series", series_name, f"Series · {series_name}"


def _pronunciation_scope_path(scope_type: str, scope_id: str = "") -> Path:
    """Return an app-owned persistent dictionary file for non-project scopes."""
    root = settings_root()
    if scope_type == "global_library":
        return root / "pronunciation_dictionary_global.json"
    if scope_type == "series":
        key = hashlib.sha256(unicodedata.normalize("NFC", scope_id).casefold().encode("utf-8")).hexdigest()
        return root / "pronunciation_dictionary_series" / f"{key}.json"
    raise ValueError("Project-scoped pronunciation entries are stored in the project state.")


def _read_pronunciation_store(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"The saved pronunciation dictionary could not be read: {path.name}. It was not overwritten.") from exc
    if not isinstance(value, list):
        raise ValueError(f"The saved pronunciation dictionary is invalid: {path.name}. It was not overwritten.")
    return [row for row in value if isinstance(row, dict)]


def _write_pronunciation_store(path: Path, entries: list[dict[str, Any]]) -> None:
    """Atomically persist global/series dictionary files without risking a partial JSON write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temp_name).replace(path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(temp_name).unlink(missing_ok=True)
        raise


def _clean_pronunciation_entries(entries: list[dict[str, Any]], scope_type: str, scope_id: str = "") -> list[dict[str, Any]]:
    """Normalize legacy rows and collapse duplicate written forms deterministically."""
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in entries:
        if not isinstance(raw, dict):
            continue
        try:
            written_value = raw.get("written_form") or raw.get("written") or raw.get("word")
            spoken_value = raw.get("spoken_form") or raw.get("spoken") or raw.get("pronunciation")
            written = _normalize_pronunciation_text(written_value, "Written term", 500)
            spoken = _normalize_pronunciation_text(spoken_value, "Pronunciation", 1000)
        except ValueError:
            # Older projects may contain incomplete rows. Ignore them in the
            # editor/runtime view without destroying the original until a save.
            continue
        key = written.casefold()
        if key in seen:
            continue
        seen.add(key)
        row = dict(raw)
        origin = str(raw.get("origin") or raw.get("source") or "manual").strip().casefold()
        if origin not in {"manual", "ai"}:
            origin = "manual"
        row.update({
            "written_form": written,
            "spoken_form": spoken,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "scope": "Current book" if scope_type == "current_book" else (
                "Global library" if scope_type == "global_library" else f"Series · {scope_id}"
            ),
            "enabled": raw.get("enabled", True) is not False,
            "origin": origin,
        })
        row.pop("written", None)
        row.pop("spoken", None)
        row.pop("word", None)
        row.pop("pronunciation", None)
        clean.append(row)
    return clean


def _effective_pronunciation_dictionary(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return no substitutions when the project-level pronunciation master switch is OFF.

    With the master switch ON, preserve Current book > matching Series > Global
    precedence and individually enabled-entry filtering.
    """
    if state.get("pronunciation_enabled", True) is False:
        return []
    scoped: list[list[dict[str, Any]]] = []
    book_rows = state.get("pronunciation_dictionary")
    scoped.append(_clean_pronunciation_entries(
        book_rows if isinstance(book_rows, list) else [], "current_book"
    ))
    series_name = str(state.get("series") or "").strip()
    if series_name:
        scoped.append(_clean_pronunciation_entries(
            _read_pronunciation_store(_pronunciation_scope_path("series", series_name)),
            "series", series_name
        ))
    scoped.append(_clean_pronunciation_entries(
        _read_pronunciation_store(_pronunciation_scope_path("global_library")),
        "global_library"
    ))
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rows in scoped:
        for row in rows:
            key = unicodedata.normalize("NFC", str(row.get("written_form") or "")).casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            if row.get("enabled", True) is not False:
                selected.append(row)
    return selected


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Hash large book files incrementally so duplicate checks do not load them fully into RAM."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cleanup_staged_import_file(path: Path | None) -> None:
    """Remove only temporary drag/drop files under the app-owned incoming directory."""
    if path is None:
        return
    try:
        incoming_root = (app_root() / "incoming_imports").resolve()
        candidate = path.resolve()
        if incoming_root not in candidate.parents:
            return
        candidate.unlink(missing_ok=True)
    except OSError:
        log.warning("Could not remove temporary import staging file: %s", path, exc_info=True)


def _sound_manifest_bgm_paths(state: dict[str, Any], path: str, enabled: bool) -> tuple[str, str]:
    """Return active and preferred book-BGM paths without breaking Chapter-Based exclusivity."""
    preferred = str(
        state.get("background_audio_preferred_path") or state.get("background_audio_path") or ""
    ).strip()
    selected = str(path or "").strip()
    overrides = state.get("chapter_bgm_overrides")
    strategy = str(
        state.get("chapter_bgm_strategy") or
        ("custom" if isinstance(overrides, dict) and overrides else "same")
    ).strip().casefold()
    chapter_based = strategy in {"custom", "chapter-based", "chapter_based", "chapter"}
    if not enabled:
        return "", selected or preferred
    if selected and chapter_based:
        # The chosen book track is retained as the preference for switching
        # back to Same BGM, but never becomes active under Chapter-Based BGM.
        return "", selected
    if selected:
        return selected, selected
    return "", preferred


class PremiumV2Bridge(QObject):
    """Narrow, allow-listed JSON bridge; renderer content cannot execute shell commands."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        ensure_roots()
        self.settings = QSettings("RyuBlanc", "Ryu's Audiobook")
        # Active project resolution is a hot path for chapter, cast, voice,
        # pronunciation, sound and generation commands. Cache the loaded object
        # and invalidate it only when its two authoritative JSON files change.
        self._active_project_cache_lock = threading.RLock()
        self._active_project_cache: tuple[str, tuple[int, int, int, int], Project] | None = None
        self._active_project_migrated_folders: set[str] = set()
        self._jobs_lock = threading.RLock()
        self._catalog_scan_lock = threading.RLock()
        self._catalog_cache_lock = threading.RLock()
        self._catalog_scan_jobs: dict[str, str] = {}
        self._catalog_scan_generation: dict[str, int] = {"models": 0, "sound": 0}
        self._performance_history_lock = threading.RLock()
        # Serialize review-skip writes with the character-analysis worker's final
        # reconciliation so a click during a long analysis cannot be overwritten.
        self._character_review_state_lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._history: dict[str, dict[str, Any]] = {}
        self._performance_history: list[dict[str, Any]] = []
        self._load_durable_history()
        self._load_performance_history()
        self._generators: dict[str, GenerationManager] = {}
        self._import_cancel_events: dict[str, threading.Event] = {}
        self._preview_cancel_events: dict[str, threading.Event] = {}
        self._analysis_cancel_events: dict[str, threading.Event] = {}
        self._preview_provider_cache_lock = threading.RLock()
        self._preview_provider_cache: dict[str, Any] | None = None
        self._preview_provider_cache_timer: threading.Timer | None = None
        self._load_durable_jobs()

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
                "project.delete": self._project_delete,
                "project.trash": self._project_trash,
                "project.trash.list": self._project_trash_list,
                "project.trash.restore": self._project_trash_restore,
                "project.trash.purge": self._project_trash_purge,
                "project.open": self._project_open,
                "project.get_active": self._project_get_active,
                "project.metadata.history": self._project_metadata_history,
                "project.metadata.save": self._project_metadata_save,
                "project.metadata.cover.choose": self._project_metadata_cover_choose,
                "chapter.list": self._chapter_list,
                "chapter.update": self._chapter_update,
                "chapter.dialogue.assign": self._chapter_dialogue_assign,
                "chapter.dialogue.unassign": self._chapter_dialogue_unassign,
                "chapter.review": self._chapter_review,
                "chapter.skip": self._chapter_skip,
                "chapter.clean": self._chapter_clean,
                "chapter.add": self._chapter_add,
                "chapter.delete": self._chapter_delete,
                "chapter.reorder": self._chapter_reorder,
                "chapter.merge": self._chapter_merge,
                "chapter.split": self._chapter_split,
                "project.rename": self._project_rename,
                "import.choose_file": self._import_choose_file,
                "import.start": self._import_start,
                "import.latest.get": self._import_latest_get,
                "voice.list": self._voice_list,
                "voice.catalog": self._voice_catalog,
                "voice.credentials.set": self._voice_credentials_set,
                "elevenlabs.open_web": self._elevenlabs_open_web,
                "voice.elevenlabs.design": self._voice_elevenlabs_design,
                "voice.elevenlabs.create": self._voice_elevenlabs_create,
                "voice.save": self._voice_save,
                "voice.delete": self._voice_delete,
                "voice.import_reference": self._voice_import_reference,
                "voice.select": self._voice_select,
                "narrator.preview": self._narrator_preview,
                "narrator.series.default.get": self._narrator_series_default_get,
                "narrator.series.default.save": self._narrator_series_default_save,
                "narrator.series.default.apply": self._narrator_series_default_apply,
                "narrator.project.reset": self._narrator_project_reset,
                "voice.preview": self._voice_preview,
                "voice.preview.save": self._voice_preview_save,
                "production.preview.save": self._production_preview_save,
                "character.list": self._character_list,
                "character.narration.segments.list": self._character_narration_segments_list,
                "character.dialogue.index.get": self._character_dialogue_index_get,
                "character.create": self._character_create,
                "character.dialogue.suggestions.list": self._character_dialogue_suggestions_list,
                "character.dialogue.suggestion.skip": self._character_dialogue_suggestion_skip,
                "character.analysis.status": self._character_analysis_status,
                "character_library.list": self._character_library_list,
                "character_library.deleted.list": self._character_library_deleted_list,
                "character_library.restore": self._character_library_restore,
                "character_library.save": self._character_library_save,
                "character_library.delete": self._character_library_delete,
                "character_library.import": self._character_library_import,
                "character.analyze": self._character_analyze,
                "character.assign": self._character_assign,
                "character.update": self._character_update,
                "character.delete": self._character_delete,
                "pronunciation.list": self._pronunciation_list,
                "pronunciation.export": self._pronunciation_export,
                "pronunciation.import": self._pronunciation_import,
                "pronunciation.test_results.get": self._pronunciation_test_results_get,
                "pronunciation.test_results.save": self._pronunciation_test_results_save,
                "pronunciation.save": self._pronunciation_save,
                "pronunciation.delete": self._pronunciation_delete,
                "pronunciation.delete_many": self._pronunciation_delete_many,
                "pronunciation.settings.get": self._pronunciation_settings_get,
                "pronunciation.settings.save": self._pronunciation_settings_save,
                "pronunciation.analyze": self._pronunciation_analyze,
                "production.narrator_only.save": self._production_narrator_only_save,
                "production.generate_book": self._production_generate_book,
                "production.preview": self._production_preview,
                "sound.preview_book": self._sound_preview_book,
                "job.list": self._job_list,
                "job.pause": self._job_pause,
                "job.resume": self._job_resume,
                "job.cancel": self._job_cancel,
                "job.retry": self._job_retry,
                "job.recover": self._job_recover,
                "job.clear_completed": self._job_clear_completed,
                "history.list": self._history_list,
                "player.get_active": self._player_get_active,
                "player.position.save": self._player_position_save,
                "settings.get": self._settings_get,
                "settings.save": self._settings_save,
                "storage.get": self._storage_get,
                "storage.choose_root": self._storage_choose_root,
                "storage.open_root": self._storage_open_root,
                "storage.copy_root": self._storage_copy_root,
                "storage.cleanup_source": self._storage_cleanup_source,
                "storage.cleanup_temp": self._storage_cleanup_temp,
                "models.list": self._models_list,
                "models.refresh": self._models_refresh,
                "models.files": self._models_files,
                "models.open_folder": self._models_open_folder,
                "models.copy_path": self._models_copy_path,
                "models.install": self._models_install,
                "models.repair": self._models_repair,
                "models.uninstall": self._models_uninstall,
                "models.verify": self._models_verify,
                "performance.info": self._performance_info,
                "performance.benchmark": self._performance_benchmark,
                "performance.qwen_benchmark": self._performance_qwen_benchmark,
                "performance.history.clear": self._performance_history_clear,
                "performance.history.export": self._performance_history_export,
                "performance.history.import": self._performance_history_import,
                "performance.history.compare": self._performance_history_compare,
                "diagnostics.check": self._diagnostics_check,
                "diagnostics.export_logs": self._diagnostics_export_logs,
                "system.open_output": self._system_open_output,
                "sound.catalog": self._sound_catalog,
                "sound.refresh": self._sound_refresh,
                "sound.import": self._sound_import,
                "sound.assign": self._sound_assign,
                "sound.save_manifest": self._sound_save_manifest,
                "sound.cues.get": self._sound_cues_get,
                "sound.cues.save": self._sound_cues_save,
                "sound.cues.clear": self._sound_cues_clear,
                "sound.chapter_bgm.get": self._sound_chapter_bgm_get,
                "sound.chapter_bgm.save": self._sound_chapter_bgm_save,
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
            "project.create": False,
            "project.list": True,
            "project.delete": True,
            "project.trash": True,
            "project.trash.list": True,
            "project.trash.restore": True,
            "project.trash.purge": True,
            "project.open": True,
            "project.get_active": True,
            "project.metadata.history": True,
            "project.metadata.save": True,
            "project.metadata.cover.choose": True,
            "chapter.list": True,
            "chapter.update": True,
            "chapter.dialogue.assign": True,
            "chapter.dialogue.unassign": True,
            "chapter.review": True,
            "chapter.skip": True,
            "chapter.split": True,
            "chapter.clean": True,
            "chapter.add": True,
            "chapter.delete": True,
            "chapter.reorder": True,
            "chapter.merge": True,
            "project.rename": True,
            "import.choose_file": True,
            "import.start": True,
            "import.latest.get": True,
            "voice.list": True,
            "voice.catalog": True,
            "voice.credentials.set": True,
            "elevenlabs.open_web": True,
            "voice.elevenlabs.design": True,
            "voice.elevenlabs.create": True,
            "voice.save": True,
            "voice.delete": True,
            "voice.import_reference": True,
            "voice.select": True,
            "narrator.preview": True,
            "narrator.series.default.get": True,
            "narrator.series.default.save": True,
            "narrator.series.default.apply": True,
            "narrator.project.reset": True,
            "voice.preview": True,
            "voice.preview.save": True,
            "production.preview.save": True,
            "character.list": True,
            "character.narration.segments.list": True,
            "character.dialogue.index.get": True,
            "character.create": True,
            "character.dialogue.suggestions.list": True,
            "character.dialogue.suggestion.skip": True,
            "character.analysis.status": True,
            "character_library.list": True,
            "character_library.deleted.list": True,
            "character_library.restore": True,
            "character_library.save": True,
            "character_library.delete": True,
            "character_library.import": True,
            "character.analyze": True,
            "character.assign": True,
            "character.update": True,
            "character.delete": True,
            "pronunciation.list": True,
            "pronunciation.export": True,
            "pronunciation.import": True,
            "pronunciation.test_results.get": True,
            "pronunciation.test_results.save": True,
            "pronunciation.save": True,
            "pronunciation.delete": True,
            "pronunciation.delete_many": True,
            "pronunciation.settings.get": True,
            "pronunciation.settings.save": True,
            "pronunciation.analyze": True,
            "production.narrator_only.save": True,
            "production.generate_book": True,
            "production.preview": True,
            "sound.preview_book": True,
            "job.list": True,
            "job.pause": True,
            "job.resume": True,
            "job.cancel": True,
            "job.retry": True,
            "job.recover": True,
            "job.clear_completed": True,
            "history.list": True,
            "player.get_active": True,
            "player.position.save": True,
            "settings.get": True,
            "settings.save": True,
            "storage.get": True,
            "storage.choose_root": True,
            "storage.open_root": True,
            "storage.copy_root": True,
            "storage.cleanup_source": True,
            "storage.cleanup_temp": True,
            "models.list": True,
            "models.refresh": True,
            "models.files": True,
            "models.open_folder": True,
            "models.copy_path": True,
            "models.install": True,
            "models.repair": True,
            "models.uninstall": True,
            "models.verify": True,
            "performance.info": True,
            "performance.benchmark": True,
            "performance.qwen_benchmark": True,
            "performance.history.clear": True,
            "performance.history.export": True,
            "performance.history.import": True,
            "performance.history.compare": True,
            "diagnostics.check": True,
            "diagnostics.export_logs": True,
            "system.open_output": True,
            "sound.catalog": True,
            "sound.refresh": True,
            "sound.import": True,
            "sound.assign": True,
            "sound.save_manifest": True,
            "sound.cues.get": True,
            "sound.cues.save": True,
            "sound.cues.clear": True,
            "sound.chapter_bgm.get": True,
            "sound.chapter_bgm.save": True,
            "reason": "Local import, chapter editing, saved voice selection and preview, character analysis and editing, pronunciation rules, audiobook generation, background jobs, history, playback metadata, local model installation, settings, live hardware telemetry, TTS benchmarks, persistent benchmark history, PC benchmark import and comparable cross-PC reports are connected.",
        }

    def _project_summary(self, project) -> dict[str, Any]:
        """Return display data from saved local project files, never HTML sample values."""
        state = load_state(project.folder)
        output_value = str(state.get("output_path") or "").strip()
        output = Path(output_value).expanduser() if output_value else None
        try:
            output = output.resolve() if output else None
            valid_output = bool(output and output.is_file() and output.stat().st_size > 0)
        except OSError:
            valid_output = False
        completed = valid_output and str(state.get("status") or "").casefold() == "completed"

        # Match Production's displayed destination to the final generation default.
        persisted_target = str(state.get("generation_target_path") or output_value or "").strip()
        safe_output_stem = re.sub(r'[<>:"/\\|?*]+', "_", project.title).strip() or "Audiobook"
        output_target = (
            Path(persisted_target).expanduser()
            if persisted_target else audiobooks_root() / (safe_output_stem + ".m4b")
        )
        try:
            output_target = output_target.resolve()
            output_folder = output_target.parent
            # Generation creates missing output directories before starting the
            # worker. Readiness should therefore check the nearest existing
            # ancestor that must permit those directory creations, rather than
            # requiring a custom destination folder to exist in advance.
            creation_root = output_folder
            while not creation_root.exists() and creation_root != creation_root.parent:
                creation_root = creation_root.parent
            output_folder_ready = creation_root.is_dir() and os.access(creation_root, os.W_OK)
        except (OSError, RuntimeError, ValueError):
            output_folder = output_target.parent
            output_folder_ready = False

        settings_store = getattr(self, "settings", None)
        default_bitrate = 256
        if settings_store is not None:
            try:
                default_bitrate = settings_store.value(
                    "production/bitrate",
                    settings_store.value("audio/default_bitrate", 256),
                )
            except Exception:
                default_bitrate = 256
        try:
            audio_bitrate = int(state.get("audio_bitrate") or default_bitrate or 256)
        except (TypeError, ValueError, OverflowError):
            audio_bitrate = 256
        if not 128 <= audio_bitrate <= 320:
            audio_bitrate = 256
        output_format = output_target.suffix.lstrip(".").upper() or "M4B"
        output_format_supported = output_target.suffix.casefold() == ".m4b"

        cover_value = str(state.get("cover_path") or "").strip()
        candidate_cover = Path(cover_value).expanduser() if cover_value else None
        cover = None
        state_changed = False
        if candidate_cover and candidate_cover.is_file() and candidate_cover.suffix.casefold() in COVER_IMAGE_EXTENSIONS:
            try:
                cover = persist_project_cover(candidate_cover, project.folder)
            except (OSError, ValueError, RuntimeError):
                # Keep showing a valid source image even if the portable copy could
                # not be written (for example, a disk with no free space).
                try:
                    cover = candidate_cover.resolve()
                except (OSError, RuntimeError):
                    cover = None
            if cover and str(state.get("cover_path") or "") != str(cover):
                state["cover_path"] = str(cover)
                state_changed = True
            if cover and not state.get("cover_detection_attempted"):
                state["cover_detection_attempted"] = True
                state_changed = True
        elif cover_value:
            # A moved/deleted source image must not hide a cover embedded in the
            # imported book; discard the stale pointer and search once instead.
            state.pop("cover_path", None)
            state_changed = True

        source_for_cover = project.source_path
        if (cover is None and source_for_cover and source_for_cover.is_file()
                and source_for_cover.suffix.casefold() in COVER_SOURCE_EXTENSIONS
                and not state.get("cover_detection_attempted")):
            state["cover_detection_attempted"] = True
            state_changed = True
            try:
                cover = extract_embedded_cover(source_for_cover, project.folder)
            except Exception:
                log.debug("Could not extract embedded cover from %s", source_for_cover, exc_info=True)
                cover = None
            if cover:
                state["cover_path"] = str(cover)
                state_changed = True

        if state_changed:
            save_state(project.folder, state)

        chapter_count = len(project.chapters)
        prepared_chapters = sum(
            1 for chapter in project.chapters
            if str(getattr(chapter, "text", "") or "").strip()
        )
        eligible_chapters = sum(
            1 for chapter in project.chapters
            if not getattr(chapter, "skip_for_generation", False)
            and str(getattr(chapter, "text", "") or "").strip()
        )
        empty_chapters = sum(
            1 for chapter in project.chapters
            if not str(getattr(chapter, "text", "") or "").strip()
        )
        excluded_chapters = sum(
            1 for chapter in project.chapters
            if getattr(chapter, "skip_for_generation", False)
            and str(getattr(chapter, "text", "") or "").strip()
        )
        chapter_text_ratio = prepared_chapters / chapter_count if chapter_count else 0.0

        character_rows = state.get("characters")
        if not isinstance(character_rows, list):
            character_rows = []
        voice_keys = ("voice_profile", "voice_profile_name", "assigned_voice_profile",
                      "voice_name", "voice_id", "assigned_voice", "voice")
        character_names: set[str] = set()
        assigned_character_names: set[str] = set()
        for index, row in enumerate(character_rows):
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("character_id") or f"character-{index}").strip()
            if not name or name.casefold() == "narrator":
                continue
            character_names.add(name.casefold())
            if any(str(row.get(key) or "").strip() for key in voice_keys):
                assigned_character_names.add(name.casefold())
        # Voice Cast persists manual assignments separately from the Character
        # Studio metadata. Merge both sources so the dashboard count reflects the
        # same actual assignments shown by Voice Cast, without double counting.
        voice_cast = state.get("voice_cast")
        if isinstance(voice_cast, dict):
            for name, profile in voice_cast.items():
                character_name = str(name or "").strip()
                if not character_name or character_name.casefold() == "narrator":
                    continue
                character_names.add(character_name.casefold())
                if str(profile or "").strip():
                    assigned_character_names.add(character_name.casefold())

        character_voice_count = len(assigned_character_names)
        character_analysis_done = bool(state.get("character_analysis")) or bool(character_names)

        # Production and Character Studio must derive cast readiness from the
        # same resolvers: saved profile references are valid only when they map
        # to an available Voice Studio profile, and dialogue counts come from
        # the canonical revision-aware passage index used by generation.
        character_assignment_issues: list[str] = []
        effective_character_rows: list[dict[str, Any]] = []
        profile_catalogue = []
        try:
            profile_catalogue = load_profiles()
            effective_character_rows, character_assignment_issues = (
                self._effective_generation_character_rows(
                    state,
                    self._project_series_name(project, state),
                    available_profiles=profile_catalogue,
                    strict=False,
                )
            )
        except Exception:
            log.exception("Could not resolve saved character voice assignments for Production readiness")
            character_assignment_issues = ["Saved character voice profiles could not be verified."]

        available_character_profile_names = {
            str(getattr(profile, "name", "") or "").strip().casefold()
            for profile in profile_catalogue
            if str(getattr(profile, "name", "") or "").strip()
        }
        configured_character_rows = [
            row for row in effective_character_rows
            if isinstance(row, dict)
            and str(row.get("name") or row.get("primary_name") or "").strip().casefold() != "narrator"
            and str(row.get("voice_profile") or "").strip().casefold() in available_character_profile_names
        ]
        configured_character_voice_profile_count = len(configured_character_rows)

        dialogue_index_ready = False
        dialogue_index_revision = ""
        dialogue_passage_count = 0
        assigned_dialogue_count = 0
        pending_dialogue_count = 0
        conflicting_dialogue_count = 0
        unassigned_dialogue_count = 0
        dialogue_index_issue_count = 0
        try:
            from app.chapters.passage_index import load_or_build_passage_index

            dialogue_index = load_or_build_passage_index(
                project.folder,
                project.chapters,
                suggested_passages=state.get("character_dialogue_suggestions") or [],
            )
            dialogue_counts = dialogue_index.get("counts") or {}
            dialogue_index_revision = str(dialogue_index.get("index_revision") or "")
            dialogue_passage_count = int(dialogue_counts.get("dialogue_passage_count") or 0)
            assigned_dialogue_count = int(dialogue_counts.get("assigned_dialogue_count") or 0)
            pending_dialogue_count = int(dialogue_counts.get("pending_dialogue_count") or 0)
            conflicting_dialogue_count = int(dialogue_counts.get("conflicting_dialogue_count") or 0)
            unassigned_dialogue_count = int(dialogue_counts.get("unassigned_dialogue_count") or 0)
            dialogue_index_issue_count = int(dialogue_counts.get("index_issue_count") or 0)
            dialogue_index_ready = bool(dialogue_index_revision)
        except Exception:
            # Readiness must fail closed if the canonical index cannot be
            # verified. Generation resolves the same index and will also block.
            log.exception("Could not resolve the canonical dialogue passage index for Production readiness")

        narrator_only_user_opt_out = state.get("narrator_only_generation_user_opt_out", False) is True
        try:
            generation_character_voice_profile_count = max(
                0,
                int(state.get(
                    "character_voice_profile_count",
                    configured_character_voice_profile_count,
                ) or 0),
            )
        except (TypeError, ValueError, OverflowError):
            generation_character_voice_profile_count = configured_character_voice_profile_count
        # The existing Dashboard "prepared" percentage remains a project
        # completeness score. Cast/dialogue eligibility is reported separately
        # and is a hard gate on generation; do not silently change the meaning
        # of the historical percentage when the canonical index is pending.
        character_voice_ratio = (
            len(assigned_character_names) / len(character_names)
            if character_names else (1.0 if character_analysis_done else 0.0)
        )
        # Resolve the effective narrator from the saved project override or the live
        # series default. A missing/deleted profile is not considered ready.
        narrator_selection = self._narrator_series_default_read(
            project, state, self._project_series_name(project, state)
        )
        effective_narrator_profile = str(narrator_selection.get("effective_profile_name") or "")
        narrator_ready = bool(
            effective_narrator_profile and narrator_selection.get("profile_available")
        )
        narrator_only_eligible = narrator_ready and configured_character_voice_profile_count == 0
        narrator_only_automatic = narrator_only_eligible and not narrator_only_user_opt_out
        metadata_missing = missing_required_metadata_fields(
            project.title, state, effective_narrator_profile if narrator_ready else ""
        )
        # A configured output means there is a usable M4B destination,
        # not that an audiobook already exists at that path. The latter is
        # reported independently by completed/output_path above.
        output_configured = bool(str(output_target)) and output_folder_ready and output_format_supported
        pronunciation_rules = (
            state.get("pronunciation_dictionary")
            or state.get("pronunciation_rules")
            or state.get("pronunciation_terms")
        )
        pronunciation_ready = bool(pronunciation_rules)
        if isinstance(pronunciation_rules, (dict, list, tuple, set)):
            pronunciation_rule_count = len(pronunciation_rules)
        else:
            pronunciation_rule_count = 1 if pronunciation_ready else 0
        sound_design_ready = bool(
            state.get("background_audio_enabled")
            or state.get("background_audio_path")
            or state.get("auto_music_track_path")
            or state.get("chapter_bgm_overrides")
            or state.get("sound_cues")
        )
        # "Prepared" is a real readiness score, not a prototype number:
        # chapter text (40%), narrator (20%), output (15%), assigned character
        # voices (15%), pronunciation rules (5%), and sound design (5%).
        prepared_percent = round(
            40 * chapter_text_ratio
            + (20 if narrator_ready else 0)
            + (15 if output_configured else 0)
            + round(15 * character_voice_ratio)
            + (5 if pronunciation_ready else 0)
            + (5 if sound_design_ready else 0)
        )
        prepared_percent = max(0, min(100, prepared_percent))

        last_edited = state.get("last_edited_chapter_number")
        try:
            last_edited = int(last_edited) if last_edited is not None else None
        except (TypeError, ValueError):
            last_edited = None
        if last_edited is not None and not 1 <= last_edited <= max(1, chapter_count):
            last_edited = None

        try:
            # project.json and chapters.json are the durable user-edit files.
            # Exclude state.json here because reading/backfilling optional
            # Dashboard metadata (such as an embedded cover) also writes it.
            modified_stamp = max(
                path.stat().st_mtime
                for path in (project.project_file, project.text_file)
                if path.is_file()
            )
            filesystem_modified = datetime.fromtimestamp(modified_stamp, timezone.utc).isoformat(timespec="seconds")
        except (OSError, ValueError):
            filesystem_modified = ""

        modified_candidates = []
        for value in (state.get("modified_at"), filesystem_modified):
            if not value:
                continue
            try:
                timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                modified_candidates.append(timestamp.astimezone(timezone.utc))
            except (TypeError, ValueError, OverflowError):
                continue
        modified_at = max(modified_candidates).isoformat(timespec="seconds") if modified_candidates else ""
        completed_chapters = state.get("completed_chapters")
        completed_chapter_count = len(completed_chapters) if isinstance(completed_chapters, list) else 0

        def saved_count(key: str) -> int:
            try:
                return max(0, int(state.get(key) or 0))
            except (TypeError, ValueError, OverflowError):
                return 0

        empty_chapters_skipped = saved_count("empty_chapters_skipped")
        excluded_chapters_skipped = saved_count("excluded_chapters_skipped")
        chapters_skipped_for_generation = saved_count("chapters_skipped_for_generation")

        return {
            "title": project.title,
            "series_name": self._project_series_name(project, state),
            "series_volume": str(state.get("series_volume") or ""),
            "genre": str(state.get("genre") or ""),
            "metadata_complete": not metadata_missing,
            "metadata_missing_fields": metadata_missing,
            "folder": str(project.folder.resolve()),
            "source_path": str(project.source_path) if project.source_path else None,
            "chapter_count": chapter_count,
            "completed_chapter_count": completed_chapter_count,
            "empty_chapters_skipped": empty_chapters_skipped,
            "excluded_chapters_skipped": excluded_chapters_skipped,
            "chapters_skipped_for_generation": chapters_skipped_for_generation,
            "status": str(state.get("status") or "new"),
            "output_path": str(output) if valid_output and output else None,
            "completed": bool(completed),
            "cover_path": str(cover) if cover else None,
            "author": str(state.get("author") or ""),
            "publisher": str(state.get("publisher") or ""),
            "series": str(state.get("series") or ""),
            "language": str(state.get("language") or ""),
            "year": str(state.get("year") or ""),
            "genre": str(state.get("genre") or ""),
            "narrator": effective_narrator_profile or str(state.get("narrator") or ""),
            "voice_profile": effective_narrator_profile,
            "narrator_profile_source": str(narrator_selection.get("source") or "none"),
            "series_narrator_profile": str(narrator_selection.get("profile_name") or ""),
            "narrator_voice_configured": narrator_ready,
            "narrator_profile_available": bool(narrator_selection.get("profile_available")),
            "narrator_only_generation": narrator_only_automatic,
            "narrator_only_generation_auto": narrator_only_automatic,
            "narrator_only_generation_user_opt_out": narrator_only_user_opt_out,
            # Preserve the last generation's immutable cast snapshot for the
            # active-project readiness/recovery UI. The independently derived
            # configured_character_voice_profile_count below describes the
            # current saved cast and must not replace that historical identity.
            "character_voice_profile_count": generation_character_voice_profile_count,
            "generation_mode": str(
                state.get("generation_mode")
                or ("narrator_only" if narrator_only_automatic else "character_cast")
            ),
            "output_target_path": str(output_target),
            "output_folder": str(output_folder),
            "output_folder_ready": bool(output_folder_ready),
            "output_format": output_format,
            "output_format_supported": bool(output_format_supported),
            "audio_bitrate": audio_bitrate,
            "character_count": len(character_names),
            "character_voice_count": character_voice_count,
            "configured_character_voice_profile_count": configured_character_voice_profile_count,
            "character_assignment_issue_count": len(character_assignment_issues),
            "dialogue_index_ready": dialogue_index_ready,
            "dialogue_index_revision": dialogue_index_revision,
            "dialogue_passage_count": dialogue_passage_count,
            "assigned_dialogue_count": assigned_dialogue_count,
            "pending_dialogue_count": pending_dialogue_count,
            "conflicting_dialogue_count": conflicting_dialogue_count,
            "unassigned_dialogue_count": unassigned_dialogue_count,
            "dialogue_index_issue_count": dialogue_index_issue_count,
            "dialogue_review_complete": (
                dialogue_index_ready
                and len(character_assignment_issues) == 0
                and pending_dialogue_count == 0
                and conflicting_dialogue_count == 0
                and dialogue_index_issue_count == 0
            ),
            "narrator_only_eligible": narrator_only_eligible,
            "character_analysis_done": character_analysis_done,
            "prepared_chapter_count": prepared_chapters,
            "eligible_chapter_count": eligible_chapters,
            "empty_chapter_count": empty_chapters,
            "excluded_chapter_count": excluded_chapters,
            "prepared_percent": prepared_percent,
            "completed_chapter_count": completed_chapter_count,
            "last_edited_chapter_number": last_edited,
            "source_exists": bool(project.source_path and project.source_path.is_file()),
            "output_configured": output_configured,
            "pronunciation_rule_count": pronunciation_rule_count,
            "sound_design_configured": sound_design_ready,
            "modified_at": modified_at,
        }

    def _mark_project_edited(self, project, chapter_number: int | None = None) -> None:
        """Persist real edit timestamps used by Dashboard ordering and last-edited labels."""
        state = load_state(project.folder)
        state["modified_at"] = self._now()
        if chapter_number is not None:
            try:
                number = int(chapter_number)
            except (TypeError, ValueError):
                number = 0
            if 1 <= number <= len(project.chapters):
                state["last_edited_chapter_number"] = number
        save_state(project.folder, state)

    def _project_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        return [self._project_summary(project) for project in list_projects()]

    def _project_trash(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Move a local project to recoverable Trash without destroying its work."""
        from app.core.project_trash import trash_project

        requested = str(payload.get("folder") or "").strip()
        if not requested:
            raise ValueError("Choose a saved project before deleting it.")
        try:
            target = Path(requested).expanduser().resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError("The selected project path is invalid.") from exc
        project = next(
            (item for item in list_projects() if Path(item.folder).resolve() == target),
            None,
        )
        if project is None:
            raise ValueError("That project is no longer present in the active Library.")
        active_folder_value = str(self.settings.value("project/active_folder") or "").strip()
        active_folder = Path(active_folder_value).expanduser().resolve() if active_folder_value else None
        active_states = {"queued", "running", "paused", "cancelling"}
        if active_folder == target:
            with self._jobs_lock:
                has_active_job = any(str(job.get("state") or "").casefold() in active_states
                                     for job in self._jobs.values())
            if has_active_job:
                raise ValueError("This project has an active background job. Cancel or finish it before moving the book to Trash.")
        entry = trash_project(project)
        try:
            from app.core.import_status import clear_latest_import_for_folder

            clear_latest_import_for_folder(target)
        except Exception:
            log.exception("Could not clear latest-import status for trashed project %s", target)
        if active_folder == target:
            self.settings.remove("project/active_folder")
            self.settings.sync()
        manifest_path = entry / "trash-manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            manifest = {}
        return {"id": str(manifest.get("id") or entry.name), "title": project.title,
                "trashed": True, "deleted_at": manifest.get("deleted_at")}

    def _project_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Permanently remove a local project while preserving its History record."""
        from app.core.project import delete_project

        requested = str(payload.get("folder") or "").strip()
        if not requested:
            raise ValueError("Choose a saved project before permanently deleting it.")
        try:
            target = Path(requested).expanduser().resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError("The selected project path is invalid.") from exc
        project = next(
            (item for item in list_projects() if Path(item.folder).resolve() == target),
            None,
        )
        if project is None:
            raise ValueError("That project is no longer present in the active Library.")
        active_folder_value = str(self.settings.value("project/active_folder") or "").strip()
        active_folder = Path(active_folder_value).expanduser().resolve() if active_folder_value else None
        active_states = {"queued", "running", "paused", "pause_requested", "cancel_requested", "cancelling"}

        def job_targets_project(job: dict[str, Any]) -> bool:
            if str(job.get("state") or "").casefold() not in active_states:
                return False
            job_folder_value = str(job.get("project_folder") or "").strip()
            if not job_folder_value:
                return active_folder == target
            try:
                return Path(job_folder_value).expanduser().resolve() == target
            except (OSError, RuntimeError, ValueError):
                return False

        with self._jobs_lock:
            has_active_job = any(job_targets_project(job) for job in self._jobs.values())
        if has_active_job:
            raise ValueError(
                "This project has an active background job. Cancel or finish it before permanently deleting the book."
            )
        # delete_project validates the managed-library path, records a standalone
        # History entry first, preserves shared Character Library/pronunciation
        # data, and removes only the project's saved output file and project tree.
        delete_project(project)
        try:
            from app.core.import_status import clear_latest_import_for_folder

            clear_latest_import_for_folder(target)
        except Exception:
            log.exception("Could not clear latest-import status for deleted project %s", target)
        if active_folder == target:
            self.settings.remove("project/active_folder")
            self.settings.sync()
        return {"deleted": True, "folder": str(target), "title": project.title}

    def _project_trash_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        from app.core.project_trash import list_trashed_projects

        entries = []
        for item in list_trashed_projects():
            entries.append({
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or item.get("original_folder_name") or "Untitled"),
                "deleted_at": str(item.get("deleted_at") or ""),
                "original_folder_name": str(item.get("original_folder_name") or ""),
                "restorable": bool(item.get("restorable")),
            })
        return entries

    def _project_trash_entry(self, payload: dict[str, Any]) -> Path:
        from app.core.project_trash import list_trashed_projects, trash_root

        requested_id = str(payload.get("id") or payload.get("trash_id") or "").strip()
        if not requested_id:
            raise ValueError("Choose a Trash entry first.")
        record = next((item for item in list_trashed_projects()
                       if str(item.get("id") or "") == requested_id), None)
        if record is None:
            raise ValueError("That Trash entry no longer exists. Refresh the recovery list.")
        stored_project = Path(str(record.get("project_folder") or "")).expanduser().resolve()
        root = trash_root().resolve()
        entry = stored_project.parent
        if root not in entry.parents or not (entry / "trash-manifest.json").is_file():
            raise ValueError("The selected recovery record is outside the managed Trash.")
        return entry

    def _project_trash_restore(self, payload: dict[str, Any]) -> dict[str, Any]:
        from app.core.project_trash import restore_project

        entry = self._project_trash_entry(payload)
        restored_folder = restore_project(entry)
        return {"restored": True, "folder": str(restored_folder), "title": restored_folder.name}

    def _project_trash_purge(self, payload: dict[str, Any]) -> dict[str, Any]:
        from app.core.project_trash import purge_trashed_project

        entry = self._project_trash_entry(payload)
        purge_trashed_project(entry)
        return {"purged": True}

    @staticmethod
    def _project_file_signature(folder: Path) -> tuple[int, int, int, int]:
        """Cheap change detector for the authoritative project and chapter files."""
        project_stat = (folder / "project.json").stat()
        chapters_stat = (folder / "chapters.json").stat()
        return (
            int(project_stat.st_mtime_ns), int(project_stat.st_size),
            int(chapters_stat.st_mtime_ns), int(chapters_stat.st_size),
        )

    def _load_library_project(self, folder: str | Path) -> Project | None:
        """Load one known Library child; do not enumerate unrelated projects."""
        target = resolve_library_project_folder(Path(folder))
        if target is None:
            return None
        key = str(target)
        signature = self._project_file_signature(target)
        lock = getattr(self, "_active_project_cache_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._active_project_cache_lock = lock
        with lock:
            cached = getattr(self, "_active_project_cache", None)
            if cached and cached[0] == key and cached[1] == signature:
                return cached[2]

            migrated = getattr(self, "_active_project_migrated_folders", None)
            if migrated is None:
                migrated = set()
                self._active_project_migrated_folders = migrated
            # Do the legacy chapter/narration/BGM ID migration once per project
            # per app session. Later file changes reload only project.json and
            # chapters.json; they do not rescan the narration tree.
            project = Project.load(target, migrate_legacy=key not in migrated)
            migrated.add(key)
            signature = self._project_file_signature(target)
            self._active_project_cache = (key, signature, project)
            return project

    def _project_open(self, payload: dict[str, Any]) -> dict[str, Any]:
        requested = str(payload.get("folder") or "").strip()
        if not requested:
            raise ValueError("Choose a saved local project first.")
        selected = self._load_library_project(requested)
        if selected is None:
            raise ValueError("That project is not present in the local library.")
        self.settings.setValue("project/active_folder", str(selected.folder.resolve()))
        self.settings.sync()
        return self._project_summary(selected)

    def _project_get_active(self, _payload: dict[str, Any]) -> dict[str, Any] | None:
        folder = str(self.settings.value("project/active_folder", "") or "").strip()
        if not folder:
            return None
        selected = self._load_library_project(folder)
        if selected is None:
            self.settings.remove("project/active_folder")
            self.settings.sync()
            return None
        return self._project_summary(selected)

    def _metadata_expected_project(self, project, payload: dict[str, Any]) -> None:
        """Reject delayed metadata requests after the active project changes."""
        expected = str(payload.get("expected_project_folder") or "").strip()
        if not expected:
            raise ValueError("Reload Input Project Details and select the active project before saving.")
        try:
            expected_path = Path(expected).expanduser().resolve()
            active_path = Path(project.folder).expanduser().resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError("The active project identity could not be verified.") from exc
        if expected_path != active_path:
            raise RuntimeError("The active project changed. Reopen Input Project Details before saving to prevent cross-project metadata changes.")

    def _project_metadata_history(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return saved metadata choices from local projects and Character Library."""
        project = self._active_project()
        self._metadata_expected_project(project, payload)
        keys = ("author", "publisher", "series", "series_volume", "language", "year", "genre")
        values: dict[str, list[str]] = {key: [] for key in keys}
        seen: dict[str, set[str]] = {key: set() for key in keys}

        def add(key: str, raw: Any) -> None:
            value = normalize_metadata_text(raw)
            folded = value.casefold()
            if value and folded not in seen[key]:
                values[key].append(value)
                seen[key].add(folded)

        for saved_project in list_projects():
            state = load_state(saved_project.folder)
            for key in keys:
                add(key, state.get(key))
            add("series", self._project_series_name(saved_project, state))
        for character in list_reusable_characters():
            if isinstance(character, dict):
                add("series", character.get("series"))
        return {"project_folder": str(project.folder.resolve()), "values": values}

    def _project_metadata_cover_choose(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Choose, decode-validate and copy cover art into this project's assets."""
        project = self._active_project()
        self._metadata_expected_project(project, payload)
        path, _ = QFileDialog.getOpenFileName(
            None, "Select Audiobook Cover", "",
            "Images (*.jpg *.jpeg *.png *.webp *.gif *.bmp *.tif *.tiff)",
        )
        if not path:
            return {"cancelled": True}
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            detail = reader.errorString() or "The selected image could not be decoded."
            raise ValueError(f"Choose a valid supported cover image. {detail}")
        selected = Path(path).expanduser().resolve()
        return {
            "cancelled": False,
            "cover_path": str(selected),
            "filename": selected.name,
            "project_folder": str(project.folder.resolve()),
        }

    def _project_metadata_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist metadata against the exact project opened in the dialog."""
        project = self._active_project()
        self._metadata_expected_project(project, payload)
        title = normalize_metadata_text(payload.get("title"), max_length=500)
        if not title:
            raise ValueError("Book Title cannot be empty.")
        metadata = {
            "author": normalize_metadata_text(payload.get("author")),
            "publisher": normalize_metadata_text(payload.get("publisher")),
            "series": normalize_metadata_text(payload.get("series")),
            "series_volume": normalize_metadata_text(payload.get("series_volume"), max_length=120),
            "language": normalize_metadata_text(payload.get("language"), max_length=120),
            "year": normalize_metadata_text(payload.get("year"), max_length=10),
            "genre": normalize_metadata_text(payload.get("genre")),
        }
        if metadata["year"] and not re.fullmatch(r"\d{4}", metadata["year"]):
            raise ValueError("Release Year must be a four-digit year, for example 2026.")

        state = load_state(project.folder)
        cover_value = str(payload.get("cover_path") or "").strip()
        cover_path: Path | None = None
        cover_backup: tuple[Path, bytes | None] | None = None
        if cover_value:
            candidate = Path(cover_value).expanduser().resolve()
            if not candidate.is_file():
                raise FileNotFoundError("The selected cover image is no longer available. Choose it again.")
            if candidate.stat().st_size <= 0 or candidate.stat().st_size > MAX_COVER_BYTES:
                raise ValueError("The selected cover image must be between 1 byte and 24 MB.")
            reader = QImageReader(str(candidate))
            reader.setAutoTransform(True)
            image = reader.read()
            if image.isNull():
                raise ValueError("The selected cover image is not a valid supported image.")
            try:
                candidate.relative_to(Path(project.folder).resolve())
                candidate_is_project_local = True
            except ValueError:
                candidate_is_project_local = False

            extension = candidate.suffix.casefold()
            output_cover_extensions = {".jpg", ".jpeg", ".png"}
            if extension in output_cover_extensions:
                if candidate_is_project_local:
                    cover_path = candidate
                else:
                    target = (Path(project.folder).resolve() / "assets" / ("cover" + extension))
                    prior_cover_bytes = target.read_bytes() if target.is_file() else None
                    cover_backup = (target, prior_cover_bytes)
                    cover_path = persist_project_cover(candidate, project.folder)
            else:
                # Production's M4B writer accepts JPG/JPEG/PNG only. Normalize
                # every other supported project-cover input into a durable PNG.
                assets = Path(project.folder).resolve() / "assets"
                assets.mkdir(parents=True, exist_ok=True)
                target = assets / "cover.png"
                prior_cover_bytes = target.read_bytes() if target.is_file() else None
                cover_backup = (target, prior_cover_bytes)
                temporary = assets / ".cover.png.stage5.tmp"
                try:
                    if not image.save(str(temporary), "PNG"):
                        raise ValueError("The selected cover could not be converted to PNG for audiobook embedding.")
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)
                cover_path = target.resolve()
            metadata["cover_path"] = str(cover_path)
            state["cover_detection_attempted"] = True
        else:
            state.pop("cover_path", None)

        selection = self._narrator_series_default_read(
            project, state, self._project_series_name(project, state)
        )
        narrator_profile = normalize_metadata_text(selection.get("effective_profile_name"))
        state.update(metadata)
        state["narrator"] = narrator_profile
        if metadata["series"]:
            state["series_name"] = metadata["series"]
        else:
            state.pop("series_name", None)
        state["modified_at"] = self._now()

        project_payload = {
            "title": title,
            "source_file": project.source_path.name if project.source_path else None,
        }
        project_payload_text = json.dumps(project_payload, ensure_ascii=False, indent=2)
        state_payload_text = json.dumps(state, ensure_ascii=False, indent=2)
        state_file = project.folder / "state.json"
        original_project_text = (
            project.project_file.read_text(encoding="utf-8")
            if project.project_file.is_file() else None
        )
        original_state_text = (
            state_file.read_text(encoding="utf-8") if state_file.is_file() else None
        )
        active_again = self._active_project()
        if Path(active_again.folder).resolve() != Path(project.folder).resolve():
            raise RuntimeError("The active project changed before metadata could be committed.")
        project_file_written = False
        state_file_written = False
        try:
            Project._atomic_write_text(project.project_file, project_payload_text)
            project_file_written = True
            Project._atomic_write_text(state_file, state_payload_text)
            state_file_written = True
            persisted_project = json.loads(project.project_file.read_text(encoding="utf-8"))
            persisted_state = json.loads(state_file.read_text(encoding="utf-8"))
            if persisted_project.get("title") != title:
                raise IOError("Saved book title did not pass read-back verification.")
            for key, value in metadata.items():
                if persisted_state.get(key, "") != value:
                    raise IOError(f"Saved {key} metadata did not pass read-back verification.")
            if persisted_state.get("narrator", "") != narrator_profile:
                raise IOError("Saved narrator profile did not pass read-back verification.")
        except Exception as save_error:
            rollback_errors: list[str] = []
            for path, original_text, was_written in (
                (state_file, original_state_text, state_file_written),
                (project.project_file, original_project_text, project_file_written),
            ):
                if not was_written:
                    continue
                try:
                    if original_text is None:
                        path.unlink(missing_ok=True)
                    else:
                        Project._atomic_write_text(path, original_text)
                except Exception as rollback_error:
                    rollback_errors.append(f"{path.name}: {rollback_error}")
            if cover_backup is not None:
                cover_target, previous_cover_bytes = cover_backup
                try:
                    if previous_cover_bytes is None:
                        cover_target.unlink(missing_ok=True)
                    else:
                        cover_target.parent.mkdir(parents=True, exist_ok=True)
                        temporary = cover_target.with_name("." + cover_target.name + ".rollback")
                        temporary.write_bytes(previous_cover_bytes)
                        temporary.replace(cover_target)
                except Exception as rollback_error:
                    rollback_errors.append(f"{cover_target.name}: {rollback_error}")
            if rollback_errors:
                raise RuntimeError(
                    "Project metadata save failed and the previous values could not be fully restored: "
                    + "; ".join(rollback_errors)
                ) from save_error
            raise OSError(
                "Project metadata could not be saved. The previous project details were restored."
            ) from save_error
        project.title = title
        missing_metadata = missing_required_metadata_fields(title, persisted_state, narrator_profile)
        return {
            "saved": True,
            "project_folder": str(project.folder.resolve()),
            "title": title,
            "author": str(persisted_state.get("author") or ""),
            "publisher": str(persisted_state.get("publisher") or ""),
            "series": str(persisted_state.get("series") or ""),
            "series_name": str(persisted_state.get("series_name") or ""),
            "series_volume": str(persisted_state.get("series_volume") or ""),
            "language": str(persisted_state.get("language") or ""),
            "year": str(persisted_state.get("year") or ""),
            "genre": str(persisted_state.get("genre") or ""),
            "narrator": str(persisted_state.get("narrator") or ""),
            "cover_path": str(cover_path) if cover_path else "",
            "metadata_complete": not missing_metadata,
            "metadata_missing_fields": missing_metadata,
        }

    def _active_project(self):
        folder = str(self.settings.value("project/active_folder", "") or "").strip()
        if not folder:
            raise ValueError("Open a local project from the Library first.")
        try:
            selected = self._load_library_project(folder)
        except FileNotFoundError:
            # Do not erase the saved project path when an external Library drive
            # is disconnected. The user can reconnect it and continue.
            raise
        if selected is None:
            self.settings.remove("project/active_folder")
            self.settings.sync()
            self._active_project_cache = None
            raise ValueError("The active project is no longer available in the local library.")
        return selected

    def _chapter_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        project = self._active_project()
        return [{"number": c.number, "title": c.title, "text": c.text,
                 "word_count": len(c.text.split()),
                 "dialogue_assignments": c.dialogue_assignments,
                 "review_status": getattr(c, "review_status", "needs_review"),
                 "skip_for_generation": getattr(c, "skip_for_generation", False)}
                for c in project.chapters]

    def _chapter_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        try:
            number = int(payload.get("number"))
        except (TypeError, ValueError):
            raise ValueError("Select a valid chapter before saving.")
        chapter = next((c for c in project.chapters if c.number == number), None)
        if chapter is None:
            raise ValueError("The selected chapter no longer exists.")
        text_value = payload.get("text")
        title_value = payload.get("title", chapter.title)
        if not isinstance(text_value, str):
            raise ValueError("Chapter text must be a string. Empty chapters can be saved and reviewed.")
        if len(text_value) > 10_000_000:
            raise ValueError("Chapter text is too large to save in one operation.")
        if not isinstance(title_value, str) or not title_value.strip():
            raise ValueError("Chapter title cannot be empty.")
        chapter.title = title_value.strip()[:500]
        chapter.text = text_value
        project.save()
        self._mark_project_edited(project, chapter.number)
        return {"number": chapter.number, "title": chapter.title,
                "word_count": len((chapter.text or "").split()),
                "character_count": len(chapter.text or ""),
                "empty": not bool((chapter.text or "").strip()), "saved": True}

    def _chapter_dialogue_assign(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist an explicit speaker choice only when its text uniquely matches source."""
        from app.chapters.assignment_utils import assign_dialogue_to_chapters
        project = self._active_project()
        dialogue_text = str(payload.get("dialogue_text") or "")
        raw_speakers = payload.get("speakers")
        if isinstance(raw_speakers, str):
            raw_speakers = [raw_speakers]
        if not isinstance(raw_speakers, list):
            raise ValueError("Choose a saved character before confirming the assignment.")
        state = load_state(project.folder)
        characters = [item for item in (state.get("characters") or []) if isinstance(item, dict)]
        requested_series = str(payload.get("series") or "").strip()
        canonical_by_name: dict[str, str] = {}
        ambiguous_keys: set[str] = set()
        default_series = self._project_series_name(project, state)
        for item in characters:
            item_series = str(item.get("series") or default_series).strip()
            if requested_series and item_series.casefold() != requested_series.casefold():
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            keys = [name, *(item.get("aliases") or [])] if isinstance(item.get("aliases") or [], list) else [name]
            for raw_key in keys:
                key = str(raw_key or "").strip().casefold()
                if not key:
                    continue
                prior_name = canonical_by_name.get(key)
                if prior_name and prior_name.casefold() != name.casefold():
                    ambiguous_keys.add(key)
                else:
                    canonical_by_name[key] = name
        speakers = []
        for raw_name in raw_speakers:
            name = str(raw_name or "").strip()
            key = name.casefold()
            if key in ambiguous_keys:
                raise ValueError(f"'{name}' matches more than one saved character. Select the character in the correct series first.")
            canonical = canonical_by_name.get(key)
            if not canonical:
                raise ValueError(f"'{name or 'Unknown'}' is not in the saved character list for the selected series. Run analysis or select a saved character.")
            if canonical not in speakers:
                speakers.append(canonical)
        if not speakers:
            raise ValueError("Select at least one saved character.")
        chapter_number = payload.get("chapter_number")
        try:
            chapter_number = int(chapter_number) if chapter_number not in (None, "") else None
        except (TypeError, ValueError):
            raise ValueError("Choose a valid chapter number.")
        mode = str(payload.get("mode") or "single").strip().lower()
        if mode not in {"single", "chorus", "alternating"}:
            raise ValueError("Assignment mode must be single, chorus, or alternating.")
        import math
        assignment_source = str(payload.get("source") or "manual").strip().casefold()
        if assignment_source not in {"manual", "ai"}:
            raise ValueError("Dialogue assignment source must be manual or ai.")
        if assignment_source == "ai":
            try:
                assignment_confidence = float(payload.get("confidence", 0.0))
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("AI confidence must be a finite value between 0 and 1.") from exc
            if not math.isfinite(assignment_confidence) or not 0.0 <= assignment_confidence <= 1.0:
                raise ValueError("AI confidence must be a finite value between 0 and 1.")
        else:
            assignment_confidence = 1.0
        has_offsets = "start" in payload or "end" in payload
        if has_offsets:
            try:
                start = int(payload.get("start"))
                end = int(payload.get("end"))
            except (TypeError, ValueError):
                raise ValueError("Refresh the dialogue review and select an exact source passage.")
            if isinstance(payload.get("start"), bool) or isinstance(payload.get("end"), bool):
                raise ValueError("Dialogue offsets must be integer positions.")
            chapter = next((item for item in project.chapters if item.number == chapter_number), None)
            if chapter is None or start < 0 or end <= start or end > len(chapter.text or ""):
                raise ValueError("The selected dialogue span is no longer available. Refresh the chapter and try again.")
            exact_text = str(chapter.text or "")[start:end]
            if exact_text != dialogue_text:
                raise ValueError("The selected passage changed before it could be saved. Refresh the chapter and select it again.")
            passage_id = str(payload.get("passage_id") or "").strip()
            chapter_revision = str(payload.get("chapter_revision") or "").strip()
            if passage_id or chapter_revision:
                from app.chapters.passage_index import load_or_build_passage_index
                passage_index = load_or_build_passage_index(
                    project.folder, project.chapters,
                    suggested_passages=state.get("character_dialogue_suggestions") or [],
                )
                canonical = next(
                    (
                        row for row in passage_index["passages"]
                        if str(row.get("passage_id") or "") == passage_id
                        and str(row.get("chapter_id") or "") == str(chapter.chapter_id)
                    ),
                    None,
                ) if passage_id else next(
                    (
                        row for row in passage_index["passages"]
                        if str(row.get("chapter_id") or "") == str(chapter.chapter_id)
                        and int(row.get("start", -1)) == start
                        and int(row.get("end", -1)) == end
                    ),
                    None,
                )
                if (
                    canonical is None
                    or int(canonical.get("start", -1)) != start
                    or int(canonical.get("end", -1)) != end
                    or str(canonical.get("text") or "") != exact_text
                    or (chapter_revision and str(canonical.get("chapter_revision") or "") != chapter_revision)
                ):
                    raise ValueError("The dialogue passage changed or its canonical passage ID is stale. Refresh Character Studio and select it again.")
            from app.chapters.assignment_utils import normalize_assignment
            existing = list(getattr(chapter, "dialogue_assignments", []) or [])
            overlapping = [item for item in existing if isinstance(item, dict)
                and isinstance(item.get("start"), int) and isinstance(item.get("end"), int)
                and item["start"] < end and item["end"] > start
                and not (item["start"] == start and item["end"] == end)]
            if overlapping:
                raise ValueError("The selected passage overlaps another saved speaker assignment. Edit or remove the existing assignment first.")
            base = next((dict(item) for item in existing if isinstance(item, dict)
                         and item.get("start") == start and item.get("end") == end),
                        {"start": start, "end": end, "text": exact_text, "source": assignment_source})
            base.update({"start": start, "end": end, "text": exact_text, "source": assignment_source})
            normalized = normalize_assignment(base, speakers, mode)
            assignment_series = requested_series or default_series
            normalized.update({"source": assignment_source, "confidence": assignment_confidence, "series": assignment_series})
            chapter.dialogue_assignments = [
                item for item in existing if not (isinstance(item, dict)
                    and item.get("start") == start and item.get("end") == end)
            ] + [normalized]
            chapter.dialogue_assignments.sort(key=lambda item: (int(item.get("start", 0)), int(item.get("end", 0))))
            result = {"chapter_number": chapter.number, "start": start, "end": end,
                      "text": exact_text, "speakers": speakers, "source": assignment_source,
                      "confidence": assignment_confidence, "series": assignment_series, "saved": True}
        else:
            result = assign_dialogue_to_chapters(project.chapters, dialogue_text, speakers,
                                                 chapter_number=chapter_number, mode=mode,
                                                 source=assignment_source, confidence=assignment_confidence)
            assignment_series = requested_series or default_series
            saved_chapter = next(
                (item for item in project.chapters if item.number == result.get("chapter_number")),
                None,
            )
            if saved_chapter is None:
                raise ValueError("The selected chapter is no longer available. Refresh the chapter and try again.")
            assignments = list(getattr(saved_chapter, "dialogue_assignments", []) or [])
            matching = [
                index for index, item in enumerate(assignments)
                if isinstance(item, dict)
                and item.get("start") == result.get("start")
                and item.get("end") == result.get("end")
            ]
            if len(matching) != 1:
                raise ValueError("The saved dialogue assignment could not be uniquely verified. Refresh and try again.")
            saved_assignment = dict(assignments[matching[0]])
            saved_assignment.update({
                "source": assignment_source,
                "confidence": assignment_confidence,
                "series": assignment_series,
            })
            assignments[matching[0]] = saved_assignment
            saved_chapter.dialogue_assignments = assignments
            result["series"] = assignment_series
        project.save()
        project_state = load_state(project.folder)
        project_state["modified_at"] = self._now()
        save_state(project.folder, project_state)
        # A saved speaker choice is explicit user feedback. Store it in that
        # character's selected series so similarly named characters in different
        # series never share training examples by accident.
        if len(speakers) == 1:
            try:
                from app.chapters.character_learning import record_assignment_feedback
                saved_number = int(result["chapter_number"])
                saved_start, saved_end = int(result["start"]), int(result["end"])
                saved_chapter = next((item for item in project.chapters if item.number == saved_number), None)
                saved_character = next((item for item in (project_state.get("characters") or [])
                                         if isinstance(item, dict)
                                         and (str(item.get("name") or "").casefold() == speakers[0].casefold()
                                              or speakers[0].casefold() in {
                                                  str(alias).casefold() for alias in (item.get("aliases") or [])
                                              })
                                         and (not str(result.get("series") or "").strip()
                                              or str(item.get("series") or self._project_series_name(project, project_state)).casefold()
                                                 == str(result.get("series") or "").casefold())), {})
                learning_series = str(result.get("series") or saved_character.get("series") or "").strip()
                if not learning_series:
                    learning_series = self._project_series_name(project, project_state)
                if saved_chapter is not None:
                    record_assignment_feedback(
                        series=learning_series,
                        speaker=speakers[0],
                        aliases=list(saved_character.get("aliases") or []),
                        chapter_text=str(saved_chapter.text or ""),
                        start=saved_start, end=saved_end,
                        source_text=str(result.get("text") or dialogue_text),
                        chapter_title=str(saved_chapter.title or ""),
                    )
            except Exception:
                # The assignment itself has already been saved successfully. A
                # learning-cache failure must be logged, never roll it back.
                log.exception("Could not persist confirmed dialogue-learning feedback")
        return result

    def _chapter_dialogue_unassign(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Remove one assignment only when the original chapter span still matches exactly."""
        from app.chapters.assignment_utils import unassign_dialogue_from_chapters

        project = self._active_project()
        try:
            chapter_number = int(payload.get("chapter_number"))
            start = int(payload.get("start"))
            end = int(payload.get("end"))
        except (TypeError, ValueError):
            raise ValueError("Refresh the dialogue review and select a valid saved passage.")
        if any(isinstance(payload.get(key), bool) for key in ("chapter_number", "start", "end")):
            raise ValueError("Dialogue offsets must be valid integer positions.")
        chapter_before = next((item for item in project.chapters if item.number == chapter_number), None)
        assignment_before = next((row for row in (getattr(chapter_before, "dialogue_assignments", []) or [])
                                   if isinstance(row, dict) and row.get("start") == start
                                   and row.get("end") == end), None)
        assigned_before = (
            list(assignment_before.get("speakers") or [])
            if assignment_before and isinstance(assignment_before.get("speakers"), list)
            else ([str(assignment_before.get("speaker"))] if assignment_before and assignment_before.get("speaker") else [])
        )
        state_before = load_state(project.folder)
        project_state_characters = [item for item in (state_before.get("characters") or []) if isinstance(item, dict)]
        saved_assignment_series = str((assignment_before or {}).get("series") or "").strip()
        assigned_keys = {str(speaker or "").casefold() for speaker in assigned_before}
        learning_character = next((item for item in project_state_characters
            if any(str(candidate or "").casefold() in assigned_keys
                   for candidate in [item.get("name"), *(item.get("aliases") or [])])
            and (not saved_assignment_series
                 or str(item.get("series") or self._project_series_name(project, state_before)).casefold()
                    == saved_assignment_series.casefold())), {})
        learning_series = str(saved_assignment_series or learning_character.get("series") or "").strip()
        if not learning_series:
            learning_series = self._project_series_name(project, state_before)
        result = unassign_dialogue_from_chapters(
            project.chapters, chapter_number, start, end, str(payload.get("dialogue_text") or "")
        )
        project.save()
        project_state = load_state(project.folder)
        project_state["modified_at"] = self._now()
        save_state(project.folder, project_state)
        try:
            from app.chapters.character_learning import remove_assignment_feedback
            remove_assignment_feedback(
                series=learning_series,
                chapter_text=str(next((item.text for item in project.chapters
                                       if item.number == chapter_number), "") or ""),
                start=start, end=end, source_text=str(payload.get("dialogue_text") or ""),
            )
        except Exception:
            log.exception("Could not remove unassigned passage from dialogue-learning feedback")
        return result

    def _chapter_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist the explicit human review state for a chapter."""
        project = self._active_project()
        try:
            number = int(payload.get("number"))
        except (TypeError, ValueError):
            raise ValueError("Select a valid chapter before changing review status.")
        chapter = next((c for c in project.chapters if c.number == number), None)
        if chapter is None:
            raise ValueError("The selected chapter no longer exists.")
        status = str(payload.get("review_status") or "").strip().lower()
        if status not in {"needs_review", "reviewed"}:
            raise ValueError("Review status must be needs_review or reviewed.")
        chapter.review_status = status
        project.save()
        state = load_state(project.folder)
        state["modified_at"] = self._now()
        save_state(project.folder, state)
        return {"number": chapter.number, "review_status": chapter.review_status, "saved": True}

    def _chapter_skip(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist whether a chapter is excluded from audiobook generation."""
        project = self._active_project()
        try:
            number = int(payload.get("number"))
        except (TypeError, ValueError):
            raise ValueError("Select a valid chapter before changing generation inclusion.")
        chapter = next((c for c in project.chapters if c.number == number), None)
        if chapter is None:
            raise ValueError("The selected chapter no longer exists.")
        value = payload.get("skip_for_generation")
        if not isinstance(value, bool):
            raise ValueError("skip_for_generation must be true or false.")
        chapter.skip_for_generation = value
        project.save()
        state = load_state(project.folder)
        state["modified_at"] = self._now()
        save_state(project.folder, state)
        return {
            "number": chapter.number,
            "skip_for_generation": chapter.skip_for_generation,
            "saved": True,
        }
    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _jobs_path(self) -> Path:
        return settings_root() / "premium_v2_jobs.json"

    def _history_path(self) -> Path:
        """Immutable-ish completed-operation journal, independent of queue visibility."""
        return settings_root() / "premium_v2_history.json"

    def _performance_history_path(self) -> Path:
        """Benchmark-only journal, deliberately separate from Background Job history."""
        return settings_root() / "premium_v2_performance_history.json"

    def _load_performance_history(self) -> None:
        path = self._performance_history_path()
        try:
            rows = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        except (OSError, ValueError, TypeError):
            rows = []
        if not isinstance(rows, list):
            rows = []
        with self._performance_history_lock:
            self._performance_history = [
                dict(row) for row in rows
                if isinstance(row, dict) and row.get("benchmark_id")
            ]

    @staticmethod
    def _terminal_job_state(row: dict[str, Any]) -> bool:
        return str(row.get("state") or "").lower() in {"completed", "failed", "cancelled"}

    def _persist_json_rows(self, path: Path, rows: list[dict[str, Any]]) -> None:
        """Atomically persist job/history JSON without sharing a fixed temp filename.

        A unique same-directory temp file prevents concurrent writers or a stale
        temp from colliding, and fsync makes the completed bytes durable before
        replacing the last known-good store.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(path.parent),
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_name = handle.name
                json.dump(rows, handle, ensure_ascii=False, indent=2, default=str)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            Path(temp_name).replace(path)
            temp_name = None
        finally:
            if temp_name:
                try:
                    Path(temp_name).unlink(missing_ok=True)
                except OSError:
                    log.warning("Could not remove temporary persistence file: %s", temp_name, exc_info=True)

    def _persist_performance_history(self) -> None:
        with self._performance_history_lock:
            self._persist_json_rows(
                self._performance_history_path(),
                list(self._performance_history),
            )

    def _record_performance_benchmark(
        self, job_id: str, result: dict[str, Any], state: str
    ) -> None:
        """Persist a benchmark record independently of queue and general History cleanup."""
        record = {
            "benchmark_id": str(job_id),
            "job_id": str(job_id),
            "measured_at": self._now(),
            "state": str(state or "failed"),
            "source_origin": "local",
            "source_hardware": dict(result.get("hardware") or {}),
            "result": dict(result),
        }
        with self._performance_history_lock:
            self._performance_history = [
                row for row in self._performance_history
                if str(row.get("benchmark_id") or "") != str(job_id)
            ]
            self._performance_history.append(record)
            self._persist_json_rows(
                self._performance_history_path(),
                list(self._performance_history),
            )

    def _persist_jobs(self) -> None:
        path = self._jobs_path()
        self._persist_json_rows(path, list(self._jobs.values()))

    def _load_durable_history(self) -> None:
        path = self._history_path()
        try:
            rows = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        except (OSError, ValueError, TypeError):
            rows = []
        if not isinstance(rows, list):
            rows = []
        history: dict[str, dict[str, Any]] = {}
        for row in rows:
            if isinstance(row, dict) and row.get("job_id"):
                history[str(row["job_id"])] = dict(row)
        self._history = history

    def _persist_history(self) -> None:
        self._persist_json_rows(self._history_path(), list(self._history.values()))

    def _record_history_job(self, row: dict[str, Any]) -> None:
        """Store a terminal snapshot without coupling it to the active job queue."""
        if not self._terminal_job_state(row) or not row.get("job_id"):
            return
        snapshot = dict(row)
        snapshot["job_id"] = str(snapshot["job_id"])
        snapshot["id"] = snapshot["job_id"]
        snapshot["history_recorded_at"] = self._now()
        self._history[snapshot["job_id"]] = snapshot
        self._persist_history()

    def _reconcile_interrupted_generation_project(self, row: dict[str, Any]) -> bool:
        """Mark only the project generation owned by an interrupted job as recoverable."""
        if str(row.get("type") or "").strip().casefold() != "audiobook-generation":
            return False
        job_id = str(row.get("job_id") or "").strip()
        folder_value = str(row.get("project_folder") or "").strip()
        if not job_id or not folder_value:
            return False

        try:
            project_folder = Path(folder_value).expanduser().resolve()
            if not project_folder.is_dir():
                return False
            project_state = load_state(project_folder)
            # A stale job must never overwrite the status of a newer generation
            # that has already claimed this project.
            if str(project_state.get("generation_job_id") or "").strip() != job_id:
                return False
            project_status = str(project_state.get("status") or "").strip().casefold()
            if project_status not in {
                "queued", "generating", "running", "paused",
                "pause_requested", "cancel_requested", "retrying",
            }:
                return False

            interrupted_at = self._now()
            project_state.update({
                "status": "failed",
                "generation_recovery_required": True,
                "generation_interrupted_at": interrupted_at,
                "generation_interruption_reason": (
                    "The application closed before this audiobook generation completed. "
                    "Retry from Production Studio to reuse compatible saved checkpoints."
                ),
            })
            save_state(project_folder, project_state)
            return True
        except Exception as exc:
            row["project_recovery_error"] = str(exc)
            log.exception(
                "Could not reconcile project state for interrupted audiobook job %s",
                job_id,
            )
            return False

    def _load_durable_jobs(self) -> None:
        path = self._jobs_path()
        try:
            rows = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        except (OSError, ValueError, TypeError):
            rows = []
        if not isinstance(rows, list):
            rows = []

        interrupted_states = {
            "queued", "running", "paused", "pause_requested",
            "cancel_requested", "retrying",
        }
        jobs_changed = False
        for row in rows:
            if not isinstance(row, dict) or not row.get("job_id"):
                continue
            prior_state = str(row.get("state") or "").strip().casefold()
            if prior_state in interrupted_states:
                interrupted_at = self._now()
                row.update({
                    "state": "failed",
                    "stage": "Interrupted by application restart",
                    "message": (
                        "The application closed before this task finished. "
                        "Retry from the project to reuse valid checkpoints."
                    ),
                    "error": {
                        "code": "interrupted",
                        "message": "Worker did not survive restart.",
                    },
                    "recoverable": True,
                    "eta_seconds": None,
                    "updated_at": interrupted_at,
                    "completed_at": interrupted_at,
                })
                self._reconcile_interrupted_generation_project(row)
                jobs_changed = True

            self._jobs[str(row["job_id"])] = row
            if self._terminal_job_state(row):
                self._record_history_job(row)

        # Persist the normalized rows, otherwise every subsequent restart would
        # rediscover the same running/paused jobs and the queue could disagree
        # with the terminal snapshots already written to History.
        if jobs_changed:
            self._persist_jobs()

    def _new_job(self, job_type: str, title: str, description: str, project=None) -> str:
        job_id = uuid.uuid4().hex
        now = self._now()
        with self._jobs_lock:
            active_storage_migrations = [
                job for job in self._jobs.values()
                if str(job.get("type") or "").casefold() == "storage-migration"
                and str(job.get("state") or "").casefold() in {"queued", "running"}
            ]
            if active_storage_migrations:
                raise RuntimeError("A verified storage migration is running. Wait for it to finish before starting another application job.")
            if str(job_type).casefold() == "storage-migration":
                active_jobs = [job for job in self._jobs.values()
                               if str(job.get("state") or "").casefold() in {"queued", "running"}]
                if active_jobs:
                    raise RuntimeError("Storage migration is blocked while another application job is active.")
            self._jobs[job_id] = {
                "job_id": job_id, "id": job_id, "type": job_type, "title": title,
                "description": description, "project_title": project.title if project else "",
                "project_folder": str(project.folder) if project else "", "state": "queued",
                "progress": 0, "stage": "Queued", "message": "Waiting to start",
                "priority": "Normal", "queued_at": now, "started_at": None,
                "updated_at": now, "completed_at": None, "elapsed_seconds": 0,
                "eta_seconds": None, "retry_count": 0, "output_path": None, "result": None,
                "error": None, "recoverable": False, "hidden": False,
            }
            self._persist_jobs()
        return job_id

    def _job_update(self, job_id: str, **changes) -> dict[str, Any]:
        with self._jobs_lock:
            row = self._jobs.get(str(job_id))
            if row is None:
                raise ValueError("Background job no longer exists.")
            row.update(changes)
            row["updated_at"] = self._now()
            if row.get("state") == "running" and row.get("started_at"):
                try:
                    row["elapsed_seconds"] = max(0, int((datetime.now(timezone.utc) - datetime.fromisoformat(row["started_at"])).total_seconds()))
                except (TypeError, ValueError):
                    pass
                try:
                    progress = max(0.0, min(100.0, float(row.get("progress") or 0)))
                    elapsed = int(row.get("elapsed_seconds") or 0)
                    # Avoid displaying noisy estimates during startup or when
                    # progress has not advanced enough to be meaningful.
                    row["eta_seconds"] = (
                        max(0, int(elapsed * (100.0 - progress) / progress))
                        if elapsed >= 5 and progress >= 5 and progress < 100 else None
                    )
                except (TypeError, ValueError, ZeroDivisionError):
                    row["eta_seconds"] = None
            if row.get("state") in {"completed", "failed", "cancelled"}:
                row["completed_at"] = row.get("completed_at") or row["updated_at"]
                row["eta_seconds"] = 0
                self._record_history_job(row)
            self._persist_jobs()
            return dict(row)

    def _job_list(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        with self._jobs_lock:
            include_hidden = bool(payload.get("include_hidden", False))
            rows = [dict(j) for j in self._jobs.values() if include_hidden or not j.get("hidden")]
        return sorted(rows, key=lambda j: str(j.get("queued_at") or ""), reverse=True)

    def _history_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Return durable terminal history together with current live job snapshots.

        The independent journal remains authoritative for terminal records.
        Active queue rows are merged by stable job_id so Running and Queued
        operations appear in History without coupling retention to queue cleanup.
        """
        with self._jobs_lock:
            rows_by_id = {
                str(row.get("job_id") or row.get("id") or ""): dict(row)
                for row in self._history.values()
                if isinstance(row, dict) and (row.get("job_id") or row.get("id"))
            }
            for current in self._jobs.values():
                if not isinstance(current, dict) or current.get("hidden"):
                    continue
                job_id = str(current.get("job_id") or current.get("id") or "").strip()
                if not job_id or job_id in rows_by_id:
                    continue
                # Include queue-only snapshots as a compatibility fallback.
                # A journaled terminal record always wins over its queue copy.
                rows_by_id[job_id] = dict(current)
            rows = list(rows_by_id.values())
        return sorted(
            rows,
            key=lambda row: str(
                row.get("completed_at") or row.get("updated_at")
                or row.get("started_at") or row.get("queued_at") or ""
            ),
            reverse=True,
        )

    def _project_rename(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError("Project name cannot be blank.")
        project.title = title[:300]
        project.save()
        return {"title": project.title, "folder": str(project.folder)}

    def _import_choose_file(self, _payload: dict[str, Any]) -> dict[str, Any]:
        path, _filter = QFileDialog.getOpenFileName(
            None, "Import a book", str(Path.home()),
            "Supported books (*.epub *.pdf *.txt *.docx);;EPUB (*.epub);;PDF (*.pdf);;Text (*.txt);;Word document (*.docx)",
        )
        return {"cancelled": not bool(path), "path": path or None}

    def _import_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = payload.get("content_base64")
        if encoded is not None:
            file_name = Path(str(payload.get("file_name") or "dropped-book")).name
            suffix = Path(file_name).suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS:
                raise ValueError("Unsupported format. Supported formats: " + ", ".join(sorted(SUPPORTED_EXTENSIONS)))
            if not isinstance(encoded, str) or len(encoded) > 36 * 1024 * 1024:
                raise ValueError("Dropped files are limited to 25 MB. Use Browse files for larger books.")
            try:
                content = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("The dropped file data could not be read. Try Browse files instead.") from exc
            if not content:
                raise ValueError("The selected file is empty.")
            if len(content) > 25 * 1024 * 1024:
                raise ValueError("Dropped files are limited to 25 MB. Use Browse files for larger books.")
            incoming = app_root() / "incoming_imports"
            incoming.mkdir(parents=True, exist_ok=True)
            path = incoming / (uuid.uuid4().hex + suffix)
            try:
                path.write_bytes(content)
            except OSError as exc:
                _cleanup_staged_import_file(path)
                raise ValueError(
                    "The dropped file could not be staged in local storage. Check available disk space and permissions."
                ) from exc
            title = str(payload.get("title") or Path(file_name).stem).strip()[:300] or Path(file_name).stem
        else:
            value = str(payload.get("file_path") or payload.get("path") or "").strip()
            if not value:
                raise ValueError("Select a book file before starting import.")
            path = Path(value).expanduser().resolve()
            if not path.is_file():
                raise FileNotFoundError("The selected book file was not found.")
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                raise ValueError("Unsupported format. Supported formats: " + ", ".join(sorted(SUPPORTED_EXTENSIONS)))
            if path.stat().st_size <= 0:
                raise ValueError("The selected file is empty.")
            if path.stat().st_size > 250 * 1024 * 1024:
                raise ValueError("The selected book exceeds the 250 MB import limit.")
            title = str(payload.get("title") or path.stem).strip()[:300] or path.stem
        # Detect exact-content duplicates before creating a new project/job. Hash in chunks
        # because books can be large; comparing file contents must not duplicate the entire
        # manuscript in RAM. A dropped-file staging copy is removed on every early failure.
        try:
            try:
                source_digest = _sha256_file(path)
            except OSError as exc:
                raise ValueError(
                    "The selected source file could not be read. Check its permissions and try again."
                ) from exc
            for existing_project in list_projects():
                existing_source = existing_project.source_path
                if not existing_source or not existing_source.is_file():
                    continue
                try:
                    existing_digest = _sha256_file(existing_source)
                except OSError:
                    # A missing/unreadable historical source should not block importing a
                    # different book; its integrity is reported by the project itself.
                    continue
                if source_digest == existing_digest:
                    raise ValueError(
                        f"This file is already imported as “{existing_project.title}”. "
                        "Open that project from Audiobook Library instead of importing a duplicate."
                    )
        except Exception:
            if encoded is not None:
                _cleanup_staged_import_file(path)
            raise

        job_id = self._new_job("import", "Import " + title, "Extract text and detect chapters")
        cancel_event = threading.Event()
        with self._jobs_lock:
            self._import_cancel_events[job_id] = cancel_event
        self._job_update(job_id, state="running", started_at=self._now(), stage="Reading source file", progress=5)
        threading.Thread(target=self._import_worker, args=(job_id, path, title, cancel_event), daemon=True).start()
        return {"job_id": job_id, "state": "running", "file_path": str(path)}

    def _import_latest_get(self, _payload: dict[str, Any]) -> dict[str, Any] | None:
        from app.core.import_status import load_latest_import

        return load_latest_import()

    @staticmethod
    def _format_import_error(path: Path, error: Exception, stage: str = "extracting") -> str:
        detail = str(error).strip() or error.__class__.__name__
        if "PDF text extraction appears incomplete" in detail:
            return detail
        if stage != "extracting":
            return detail[:1200]
        kind = {".pdf": "PDF", ".epub": "EPUB", ".docx": "Word document", ".txt": "text file"}.get(path.suffix.lower(), "book file")
        if path.suffix.lower() == ".pdf":
            advice = "Confirm it opens correctly and contains a searchable text layer; scanned pages may require OCR."
        elif path.suffix.lower() == ".epub":
            advice = "Confirm the EPUB is a valid, readable archive; try re-exporting it or importing a TXT/DOCX copy."
        elif path.suffix.lower() == ".docx":
            advice = "Confirm it opens in Word or LibreOffice and is not password-protected or damaged."
        else:
            advice = "Confirm the file is readable and encoded as UTF-8 or a compatible plain-text format."
        return f"Could not extract readable text from this {kind}. {advice} Details: {detail[:700]}"

    def _import_worker(self, job_id: str, path: Path, title: str, cancel_event: threading.Event | None = None) -> None:
        stage = "extracting"
        try:
            self._job_update(job_id, stage="Extracting text", progress=20, message="Extracting readable text and metadata")
            book = extract_text(path)
            if cancel_event and cancel_event.is_set():
                self._job_update(job_id, state="cancelled", stage="Import cancelled", progress=0,
                                 message="Import cancelled before creating a project; the source file was preserved.")
                return
            text = str(book.text or "")
            if not text.strip():
                raise ValueError("No readable text was extracted. A scanned PDF may need OCR.")
            stage = "detecting chapters"
            self._job_update(job_id, stage="Detecting chapters", progress=50, message="Detecting chapter boundaries")
            chapters = detect_chapters(text)
            if not chapters:
                raise ValueError("The document contains no readable chapter text.")
            stage = "validating chapter coverage"
            self._job_update(
                job_id, stage="Validating chapter coverage", progress=56,
                message="Checking that chapter detection retained the source text",
            )
            validate_chapter_text_coverage(text, chapters, minimum=0.90)
            # Clean likely ebook page noise after chapter boundaries are known so
            # repeated boilerplate can be detected across chapters without
            # accidentally treating a single word in normal narration as noise.
            repeated_noise = set(detect_repeated_book_noise([chapter.text for chapter in chapters]))
            removed_noise: list[str] = []
            for chapter in chapters:
                chapter.text, removed = clean_import_noise(chapter.text, repeated_noise)
                removed_noise.extend(removed)
            chapters = [chapter for chapter in chapters if (chapter.text or "").strip()]
            if not chapters:
                raise ValueError("Cleanup removed all chapter text; import was stopped to protect the source book.")
            if cancel_event and cancel_event.is_set():
                self._job_update(job_id, state="cancelled", stage="Import cancelled", progress=0,
                                 message="Import cancelled before creating a project; the source file was preserved.")
                return
            stage = "saving project"
            project = create_project(title, path, chapters)
            self.settings.setValue("project/active_folder", str(project.folder.resolve()))
            self.settings.sync()
            state = load_state(project.folder)
            source_for_cover = project.source_path or path
            if source_for_cover.suffix.casefold() in COVER_SOURCE_EXTENSIONS:
                state["cover_detection_attempted"] = True
                try:
                    embedded_cover = extract_embedded_cover(source_for_cover, project.folder)
                except Exception:
                    log.debug("Could not extract embedded cover from %s", source_for_cover, exc_info=True)
                    embedded_cover = None
                if embedded_cover:
                    state["cover_path"] = str(embedded_cover)
            state.update({"status": "imported", "source_path": str(project.source_path or path),
                          "source_title": book.title, "word_count": sum(len((c.text or "").split()) for c in chapters),
                          "imported_at": self._now(), "modified_at": self._now()})
            save_state(project.folder, state)
            try:
                from app.core.import_status import record_latest_import

                record_latest_import(project)
            except Exception:
                # The import itself is already saved. A recent-import card is
                # auxiliary metadata and must never turn a valid import into a failure.
                log.exception("Could not persist latest-import status for %s", project.folder)
            self._job_update(job_id, state="completed", stage="Import complete", progress=100,
                             message=("Book imported and saved locally" +
                                      (f"; removed {len(removed_noise)} likely page-noise line(s)" if removed_noise else "")),
                             project_title=project.title,
                             project_folder=str(project.folder.resolve()), result={
                                 "title": project.title, "folder": str(project.folder.resolve()),
                                 "chapter_count": len(chapters), "word_count": state["word_count"],
                                 "source_file": str(project.source_path or path),
                                 "preview_text": "\n\n".join(c.text for c in chapters[:2])[:4000],
                                 "removed_noise_count": len(removed_noise),
                                 "warnings": [f"Detected {len(chapters)} chapter(s); review chapter boundaries before production."] +
                                            ([f"Removed {len(removed_noise)} likely page-noise line(s); inspect the preview before production."] if removed_noise else []),
                             })
        except Exception as exc:
            log.exception("Premium V2 import failed")
            detail = self._format_import_error(path, exc, stage)
            self._job_update(job_id, state="failed", stage="Import failed", progress=0, message=detail,
                             error={"code": "import_failed", "message": detail}, recoverable=True)
        finally:
            with self._jobs_lock:
                self._import_cancel_events.pop(job_id, None)
            # Dropped files are staged under incoming_imports. The durable project
            # already owns a copied source on success; always clean this temporary copy.
            try:
                incoming_root = (app_root() / "incoming_imports").resolve()
                if incoming_root in path.resolve().parents:
                    path.unlink(missing_ok=True)
            except OSError:
                log.warning("Could not remove temporary import staging file: %s", path, exc_info=True)

    def _chapter_clean(self, payload: dict[str, Any]) -> dict[str, Any]:
        text_value = payload.get("text")
        if not isinstance(text_value, str):
            raise ValueError("Select chapter text before cleaning.")
        cleaned, removed = clean_import_noise(text_value)
        return {"text": cleaned, "changed": cleaned != text_value, "removed_count": len(removed)}

    def _chapter_add(self, payload: dict[str, Any]) -> dict[str, Any]:
        from app.chapters.detector import Chapter
        project = self._active_project()
        title = str(payload.get("title") or "").strip() or f"Chapter {len(project.chapters) + 1}"
        text_value = str(payload.get("text") or "")
        project.chapters.append(Chapter(len(project.chapters) + 1, title[:500], text_value))
        project.save()
        self._mark_project_edited(project, project.chapters[-1].number)
        return {"number": project.chapters[-1].number, "title": project.chapters[-1].title}

    def _chapter_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        number = int(payload.get("number") or 0)
        index = next((i for i, c in enumerate(project.chapters) if c.number == number), None)
        if index is None:
            raise ValueError("Select an existing chapter to delete.")
        if len(project.chapters) <= 1:
            raise ValueError("A project must keep at least one chapter. Clear the chapter text if you need an empty draft.")
        del project.chapters[index]
        for i, chapter in enumerate(project.chapters, 1):
            chapter.number = i
        project.save()
        self._mark_project_edited(project, min(number, len(project.chapters)))
        return {"deleted": number, "chapter_count": len(project.chapters)}

    def _chapter_reorder(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        source, destination = int(payload.get("number") or 0), int(payload.get("new_number") or 0)
        if not 1 <= source <= len(project.chapters) or not 1 <= destination <= len(project.chapters):
            raise ValueError("Choose a valid source and destination chapter order.")
        chapter = project.chapters.pop(source - 1)
        project.chapters.insert(destination - 1, chapter)
        for i, item in enumerate(project.chapters, 1):
            item.number = i
        project.save()
        self._mark_project_edited(project, destination)
        return {"chapter_count": len(project.chapters), "moved_to": destination}

    def _chapter_merge(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Merge the selected chapter into the immediately preceding chapter."""
        project = self._active_project()
        try:
            number = int(payload.get("number"))
        except (TypeError, ValueError):
            raise ValueError("Select a valid chapter to merge.")
        if number <= 1 or number > len(project.chapters):
            raise ValueError("Choose a chapter after the first; it will be merged into the previous chapter.")
        current = project.chapters[number - 1]
        previous = project.chapters[number - 2]
        previous_text = previous.text.rstrip()
        current_original = current.text or ""
        current_text = current_original.lstrip()
        removed_leading = len(current_original) - len(current_text)
        separator = "\n\n" if previous_text and current_text else ""
        assignment_offset = len(previous_text + separator)
        previous.text = (previous_text + separator + current_text).strip()
        for assignment in current.dialogue_assignments or []:
            shifted = dict(assignment)
            if isinstance(shifted.get("start"), int):
                shifted["start"] = max(0, shifted["start"] - removed_leading) + assignment_offset
            if isinstance(shifted.get("end"), int):
                shifted["end"] = max(0, shifted["end"] - removed_leading) + assignment_offset
            previous.dialogue_assignments.append(shifted)
        del project.chapters[number - 1]
        for index, chapter in enumerate(project.chapters, 1):
            chapter.number = index
        project.save()
        self._mark_project_edited(project, number - 1)
        return {"merged": number, "into": number - 1, "chapter_count": len(project.chapters)}

    def _chapter_split(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist current editor text and split one chapter at the selected cursor."""
        from app.chapters.detector import Chapter

        project = self._active_project()
        try:
            number = int(payload.get("number"))
            split_at = int(payload.get("split_at"))
        except (TypeError, ValueError):
            raise ValueError("Select a chapter and place the cursor where it should split.")
        index = next((i for i, item in enumerate(project.chapters) if item.number == number), None)
        if index is None:
            raise ValueError("The selected chapter no longer exists.")
        chapter = project.chapters[index]
        text_value = payload.get("text", chapter.text or "")
        if not isinstance(text_value, str):
            raise ValueError("Chapter text must be a string before it can be split.")
        if len(text_value) > 10_000_000:
            raise ValueError("Chapter text is too large to split in one operation.")
        if split_at <= 0 or split_at >= len(text_value):
            raise ValueError("Place the cursor inside the chapter text, not at the beginning or end.")
        left, right = text_value[:split_at].rstrip(), text_value[split_at:].lstrip()
        if not left or not right:
            raise ValueError("Both sides of a split must contain text. Move the cursor between two passages.")
        title_value = str(payload.get("title") or chapter.title or f"Chapter {number}").strip()[:500]
        if not title_value:
            raise ValueError("Chapter title cannot be empty.")
        chapter.title = title_value
        original_text = str(chapter.text or "")
        saved_assignments = list(getattr(chapter, "dialogue_assignments", []) or [])
        chapter.text = left
        new_title = str(payload.get("new_title") or f"{title_value} (continued)").strip()[:500]

        # Assignment offsets belong to the exact source text. Preserve and rebase
        # only spans wholly contained on one side of the split. If the editor has
        # changed the source, or a span crosses the split/trimmed whitespace,
        # discard that span rather than attach it to the wrong passage.
        left_assignments = []
        right_assignments = []
        if text_value == original_text:
            right_source = text_value[split_at:]
            removed_right_prefix = len(right_source) - len(right_source.lstrip())
            right_boundary = split_at + removed_right_prefix
            for assignment in saved_assignments:
                if not isinstance(assignment, dict):
                    continue
                start, end = assignment.get("start"), assignment.get("end")
                if (isinstance(start, bool) or not isinstance(start, int)
                        or isinstance(end, bool) or not isinstance(end, int)
                        or start < 0 or end <= start or end > len(text_value)):
                    continue
                assignment_text = str(assignment.get("text") or "")
                if not assignment_text or text_value[start:end] != assignment_text:
                    continue
                if end <= split_at:
                    left_assignments.append(dict(assignment))
                elif start >= right_boundary:
                    shifted = dict(assignment)
                    shifted["start"] = start - right_boundary
                    shifted["end"] = end - right_boundary
                    right_assignments.append(shifted)
                # A crossing span or a span in trimmed whitespace is invalidated.
        chapter.dialogue_assignments = left_assignments
        new_chapter = Chapter(
            number + 1, new_title, right, dialogue_assignments=right_assignments
        )
        project.chapters.insert(index + 1, new_chapter)
        for i, item in enumerate(project.chapters, 1):
            item.number = i
        project.save()
        self._mark_project_edited(project, new_chapter.number)
        return {
            "number": chapter.number,
            "new_number": new_chapter.number,
            "title": chapter.title,
            "new_title": new_chapter.title,
            "left_word_count": len(left.split()),
            "right_word_count": len(right.split()),
            "chapter_count": len(project.chapters),
            "saved": True,
        }

    def _voice_import_reference(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Import a selected reference recording from the file input or native picker."""
        import base64
        import binascii
        from uuid import uuid4
        from app.core.paths import voices_root
        from app.tts.voice_profile import import_reference_audio

        profile_name = str(payload.get("profile_name") or payload.get("name") or "Custom Voice").strip()
        source_text = str(payload.get("source_path") or payload.get("path") or "").strip()
        upload_path: Path | None = None
        if payload.get("content_base64"):
            encoded = str(payload.get("content_base64") or "")
            maximum_upload = 25 * 1024 * 1024
            if len(encoded) > (maximum_upload * 4 // 3) + 16:
                raise ValueError("Reference audio is too large. Choose a file smaller than 25 MB.")
            suffix = Path(str(payload.get("filename") or "reference.wav")).suffix.casefold()
            if suffix not in {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".aiff", ".opus"}:
                raise ValueError("Choose a supported audio file: WAV, MP3, FLAC, OGG, M4A, AAC, AIFF or OPUS.")
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("The selected reference audio could not be read. Choose the file again.") from exc
            if not raw or len(raw) > maximum_upload:
                raise ValueError("Reference audio must be non-empty and smaller than 25 MB.")
            upload_root = voices_root() / "ReferenceUploads"
            upload_root.mkdir(parents=True, exist_ok=True)
            upload_path = upload_root / (uuid4().hex + suffix)
            upload_path.write_bytes(raw)
            source = upload_path.resolve()
        elif source_text:
            source = Path(source_text).expanduser().resolve()
        else:
            selected, _filter = QFileDialog.getOpenFileName(
                None, "Select authorized voice reference audio", str(Path.home()),
                "Audio files (*.wav *.mp3 *.flac *.ogg *.m4a *.aac *.aiff *.opus)",
            )
            if not selected:
                return {"cancelled": True, "sample_path": None}
            source = Path(selected).resolve()

        try:
            normalized = import_reference_audio(source, profile_name)
        finally:
            if upload_path is not None:
                try:
                    upload_path.unlink(missing_ok=True)
                except OSError:
                    pass
        return {"cancelled": False, "sample_path": str(normalized.resolve()),
                "source_path": str(source), "profile_name": profile_name}

    def _voice_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist a custom voice profile atomically in the local voice catalogue."""
        from app.tts.voice_profile import (
            VoiceProfile, import_reference_audio, load_saved_profiles, save_profiles,
        )

        name = str(payload.get("name") or payload.get("profile_name") or "").strip()
        provider_name = str(payload.get("provider") or "chatterbox").strip().lower()
        voice_id = str(payload.get("voice_id") or "").strip()
        # Reference-based Chatterbox profiles do not need a separate provider voice ID;
        # use the saved profile name as a stable local identifier when the UI omits it.
        if provider_name == "chatterbox" and not voice_id:
            voice_id = name
        allowed = {"qwen-character", "chatterbox", "piper", "kokoro",
                   "windows-sapi", "edge-tts", "elevenlabs"}
        if not name:
            raise ValueError("Give the custom voice profile a name before saving.")
        if len(name) > 160:
            raise ValueError("Voice profile names must be 160 characters or fewer.")
        if provider_name not in allowed:
            raise ValueError("Choose a supported voice provider.")
        if not voice_id:
            raise ValueError("A voice ID or speaker identifier is required.")

        saved = load_saved_profiles()
        existing = next((p for p in saved if p.name.casefold() == name.casefold()), None)
        original_name = str(payload.get("original_name") or "").strip()
        source_existing = next(
            (p for p in saved if original_name and p.name.casefold() == original_name.casefold()),
            None,
        )
        if source_existing is not None and existing is not None and source_existing is not existing:
            raise ValueError(f"A saved profile named '{name}' already exists. Choose a different name to rename this profile.")
        target_existing = existing or source_existing
        built_in_collision = next(
            (p for p in load_profiles() if p.name.casefold() == name.casefold()
             and existing is None),
            None,
        )
        if built_in_collision is not None:
            raise ValueError("That name is already used by an installed voice. Choose a distinct profile name.")

        sample_path = str(payload.get("sample_path") or (target_existing.sample_path if target_existing else "")).strip() or None
        reference_path = str(payload.get("reference_path") or "").strip()
        if reference_path:
            sample_path = str(import_reference_audio(Path(reference_path).expanduser().resolve(), name).resolve())
        if sample_path:
            sample = Path(sample_path).expanduser().resolve()
            if not sample.is_file():
                raise FileNotFoundError("The custom voice reference audio is missing.")
            sample_path = str(sample)

        qwen_mode = str(payload.get("qwen_mode") or getattr(target_existing, "qwen_mode", "") or ("clone" if provider_name == "chatterbox" else "custom")).strip().lower()
        authorized = bool(payload.get("authorized", False)) or bool(getattr(target_existing, "authorized", False))
        if provider_name == "chatterbox" and not authorized:
            raise ValueError("Confirm that you have permission to use this voice before saving a cloned voice.")
        if provider_name == "chatterbox" and not sample_path:
            raise ValueError("Import a reference recording before saving a Chatterbox custom voice.")
        if provider_name == "qwen-character" and qwen_mode in {"clone", "voiceclone", "voice-clone"}:
            if not authorized:
                raise ValueError("Confirm that you have permission to clone this voice.")
            if not sample_path:
                raise ValueError("Import reference audio for a Qwen voice-clone profile.")

        profile = VoiceProfile(
            name=name, provider=provider_name, voice_id=voice_id,
            sample_path=sample_path,
            model_id=str(payload.get("model_id") or getattr(target_existing, "model_id", None) or ("chatterbox" if provider_name == "chatterbox" else "auto")),
            backend=str(payload.get("backend") or getattr(target_existing, "backend", None) or "automatic"),
            language=str(payload.get("language") or getattr(target_existing, "language", None) or "English"),
            notes=str(payload.get("notes") or payload.get("description") or getattr(target_existing, "notes", "") or "")[:4000],
            authorized=authorized,
            exaggeration=max(0.0, min(1.0, float(payload.get("exaggeration", getattr(target_existing, "exaggeration", 0.5))))),
            cfg_weight=max(0.0, min(1.0, float(payload.get("cfg_weight", getattr(target_existing, "cfg_weight", 0.35))))),
            style_preset=str(payload.get("style_preset") or getattr(target_existing, "style_preset", None) or "Natural"),
            qwen_mode=qwen_mode,
            qwen_prompt=str(payload.get("qwen_prompt") or payload.get("prompt") or getattr(target_existing, "qwen_prompt", "") or "")[:4000],
            qwen_seed=(int(payload["qwen_seed"]) if payload.get("qwen_seed") not in (None, "") else None) if qwen_mode == "design" else getattr(target_existing, "qwen_seed", None),
            reference_text=str(payload.get("reference_text") or getattr(target_existing, "reference_text", "") or "")[:10000],
            qwen_anchor_path=str(payload.get("qwen_anchor_path") or getattr(target_existing, "qwen_anchor_path", "") or "") or None,
            qwen_anchor_text=str(payload.get("qwen_anchor_text") or getattr(target_existing, "qwen_anchor_text", "") or "")[:10000],
            qwen_profile_id=str(payload.get("qwen_profile_id") or getattr(target_existing, "qwen_profile_id", "") or ""),
        )
        previous_saved = list(saved)
        if target_existing is not None:
            saved[saved.index(target_existing)] = profile
        else:
            saved.append(profile)
        save_profiles(saved)
        if target_existing is not None:
            try:
                self._migrate_saved_voice_profile_references(
                    target_existing, profile, previous_saved
                )
            except Exception:
                # Do not leave the catalogue renamed while project references still
                # point to the removed name. The migration helper restores any state
                # records it already changed; restore the catalogue to its snapshot.
                save_profiles(previous_saved)
                raise
        return {"name": profile.name, "provider": profile.provider, "voice_id": profile.voice_id,
                "sample_path": profile.sample_path, "model_id": profile.model_id,
                "backend": profile.backend, "language": profile.language,
                "authorized": profile.authorized, "qwen_mode": profile.qwen_mode, "saved": True,
                "count": len(load_profiles())}

    def _migrate_saved_voice_profile_references(self, previous_profile, profile, previous_saved) -> None:
        """Migrate narrator, cast and reusable-library references after a saved-profile rename/update."""
        from copy import deepcopy

        old_name = str(getattr(previous_profile, "name", "") or "").strip()
        new_name = str(getattr(profile, "name", "") or "").strip()
        if not old_name or not new_name:
            return
        old_key = old_name.casefold()
        old_voice_id = str(getattr(previous_profile, "voice_id", "") or "").strip()
        new_voice_id = str(getattr(profile, "voice_id", "") or "").strip()
        new_backend = str(getattr(profile, "backend", "") or "automatic")

        project_updates = []
        library_updates = []
        attempted_projects = []
        attempted_library = []
        attempted_series_defaults = []
        try:
            for project in list_projects():
                original_state = load_state(project.folder)
                updated_state = deepcopy(original_state)
                changed = False

                narrator_keys = ("voice_profile", "voice_profile_name", "assigned_voice_profile", "narrator")
                narrator_uses_profile = any(
                    str(updated_state.get(key) or "").strip().casefold() == old_key
                    for key in narrator_keys
                )
                if narrator_uses_profile:
                    for key in narrator_keys:
                        value = updated_state.get(key)
                        if isinstance(value, str) and value.strip().casefold() == old_key:
                            updated_state[key] = new_name
                            changed = True
                    if updated_state.get("voice_id") != new_voice_id:
                        updated_state["voice_id"] = new_voice_id
                        changed = True
                    if updated_state.get("backend") != new_backend:
                        updated_state["backend"] = new_backend
                        changed = True

                characters = updated_state.get("characters")
                if isinstance(characters, list):
                    for character in characters:
                        if not isinstance(character, dict):
                            continue
                        profile_keys = ("voice_profile", "voice_profile_name", "assigned_voice_profile")
                        character_uses_profile = any(
                            str(character.get(key) or "").strip().casefold() == old_key
                            for key in profile_keys
                        )
                        if not character_uses_profile:
                            continue
                        for key in profile_keys:
                            value = character.get(key)
                            if isinstance(value, str) and value.strip().casefold() == old_key:
                                character[key] = new_name
                                changed = True
                        if old_voice_id and str(character.get("voice_id") or "").strip() == old_voice_id:
                            character["voice_id"] = new_voice_id
                            changed = True
                        if "backend" in character and character.get("backend") != new_backend:
                            character["backend"] = new_backend
                            changed = True

                voice_cast = updated_state.get("voice_cast")
                if isinstance(voice_cast, dict):
                    for cast_name, assignment in list(voice_cast.items()):
                        if isinstance(assignment, str) and assignment.strip().casefold() == old_key:
                            voice_cast[cast_name] = new_name
                            changed = True
                        elif isinstance(assignment, dict):
                            for key in ("voice_profile", "voice_profile_name", "assigned_voice_profile", "profile_name"):
                                value = assignment.get(key)
                                if isinstance(value, str) and value.strip().casefold() == old_key:
                                    assignment[key] = new_name
                                    changed = True
                            if old_voice_id and str(assignment.get("voice_id") or "").strip() == old_voice_id:
                                assignment["voice_id"] = new_voice_id
                                changed = True
                            if any(str(assignment.get(key) or "").strip().casefold() == old_key
                                   for key in ("voice_profile", "voice_profile_name", "assigned_voice_profile", "profile_name")):
                                assignment["backend"] = new_backend

                if changed:
                    updated_state["modified_at"] = self._now()
                    project_updates.append((project.folder, original_state, updated_state))

            for row in list_reusable_characters():
                if not isinstance(row, dict):
                    continue
                referenced_name = next((
                    str(row.get(key) or "").strip()
                    for key in ("voice_profile", "voice_name", "voice")
                    if str(row.get(key) or "").strip().casefold() == old_key
                ), "")
                if not referenced_name:
                    continue
                record_id = str(row.get("id") or "").strip()
                if not record_id:
                    raise ValueError("A reusable Character Library voice reference is missing its record ID.")
                library_updates.append((record_id, referenced_name))

            # Series narrator defaults live outside project state. Migrate these
            # references too, so renaming a saved Voice Studio profile cannot
            # silently invalidate every project inheriting that series default.
            series_defaults_root = Path(settings_root()) / "series-narrators"
            if series_defaults_root.is_dir():
                for path in sorted(series_defaults_root.glob("*.json")):
                    original_text = path.read_text(encoding="utf-8")
                    record = json.loads(original_text)
                    if not isinstance(record, dict):
                        raise ValueError(f"Series narrator preference is not a JSON object: {path.name}")
                    if str(record.get("profile_name") or "").strip().casefold() != old_key:
                        continue
                    record["profile_name"] = new_name
                    record["provider"] = str(getattr(profile, "provider", "") or "")
                    record["voice_id"] = new_voice_id
                    record["updated_at"] = self._now()
                    attempted_series_defaults.append((path, original_text))
                    temp_path = path.with_suffix(path.suffix + ".tmp")
                    temp_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                    temp_path.replace(path)

            for folder, original_state, updated_state in project_updates:
                attempted_projects.append((folder, original_state))
                save_state(folder, updated_state)

            for record_id, old_voice_name in library_updates:
                attempted_library.append((record_id, old_voice_name))
                update_reusable_character(record_id, {"voice_name": new_name})

        except Exception as exc:
            rollback_errors = []
            for path, original_text in reversed(attempted_series_defaults):
                try:
                    temp_path = path.with_suffix(path.suffix + ".rollback.tmp")
                    temp_path.write_text(original_text, encoding="utf-8")
                    temp_path.replace(path)
                except Exception as rollback_exc:
                    rollback_errors.append(str(rollback_exc))
            for record_id, old_voice_name in reversed(attempted_library):
                try:
                    update_reusable_character(record_id, {"voice_name": old_voice_name})
                except Exception as rollback_exc:
                    rollback_errors.append(str(rollback_exc))
            for folder, original_state in reversed(attempted_projects):
                try:
                    save_state(folder, original_state)
                except Exception as rollback_exc:
                    rollback_errors.append(str(rollback_exc))
            detail = " Saved-profile catalogue rollback will be applied by the caller."
            if rollback_errors:
                detail += " Some reference rollback operations also failed: " + "; ".join(rollback_errors)
            raise RuntimeError("Voice-profile references could not be migrated." + detail) from exc

    def _voice_catalog_base(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return the real provider catalogue for a Voice Studio library card."""
        from app.tts.voice_profile import load_profiles, load_saved_profiles

        key = str(payload.get("provider") or "").strip().casefold()
        refresh = bool(payload.get("refresh"))
        known = {"offline", "sapi", "customvoice", "voicedesign", "qwenclone", "customref", "edge", "eleven"}
        if key not in known:
            raise ValueError(f"Unknown voice library: {key or '(empty)'}")

        profiles = load_profiles()
        # Loading the combined catalogue may safely disambiguate older custom
        # names that collide with installed voices; read saved names after that
        # migration so row badges match the profile names available to Load.
        saved_profiles = load_saved_profiles()
        saved_names = {profile.name.strip().casefold() for profile in saved_profiles}

        def profile_row(profile):
            return {
                "name": profile.name,
                "voice_id": profile.voice_id,
                "provider": profile.provider,
                "language": profile.language or "",
                "locale": profile.language or "",
                "gender": "Neutral",
                "description": profile.qwen_prompt or profile.notes or "",
                "saved": profile.name.strip().casefold() in saved_names,
                "model_id": profile.model_id or "",
                "sample_path": profile.sample_path,
                "authorized": bool(profile.authorized),
                "qwen_prompt": profile.qwen_prompt, "qwen_seed": profile.qwen_seed,
                "qwen_profile_id": profile.qwen_profile_id,
                "qwen_anchor_path": profile.qwen_anchor_path,
                "qwen_anchor_text": profile.qwen_anchor_text,
                "reference_text": profile.reference_text, "notes": profile.notes,
                "style_preset": profile.style_preset,
                "exaggeration": profile.exaggeration, "cfg_weight": profile.cfg_weight,
                "qwen_mode": getattr(profile, "qwen_mode", "custom"),
            }

        rows: list[dict[str, Any]] = []
        ready = False
        message_text = ""
        source = "local"

        if key == "offline":
            rows = [profile_row(profile) for profile in profiles if profile.provider in {"piper", "kokoro"}]
            for row in rows:
                label = (row.get("name") or "").casefold()
                if "amy" in label:
                    row["gender"] = "Female"
                elif "lessac" in label or "ryan" in label:
                    row["gender"] = "Male"
                row["region"] = str(row.get("language") or "").replace("-", " ")
            ready = bool(rows)
            message_text = f"{len(rows)} installed offline voice(s) discovered." if ready else (
                "No offline neural models are installed. Open Models to install an offline voice."
            )

        elif key == "sapi":
            try:
                import pyttsx3
                engine = pyttsx3.init()
                try:
                    installed = engine.getProperty("voices") or []
                    for voice in installed:
                        voice_id = str(getattr(voice, "id", "") or "").strip()
                        name = str(getattr(voice, "name", "") or voice_id).strip()
                        languages = getattr(voice, "languages", []) or []
                        locale = ""
                        if languages:
                            first = languages[0]
                            locale = first.decode("utf-8", errors="ignore").strip("\x05 ") if isinstance(first, bytes) else str(first).strip()
                        if voice_id:
                            rows.append({
                                "name": name or voice_id, "voice_id": voice_id, "provider": "windows-sapi",
                                "language": locale, "locale": locale, "region": locale,
                                "gender": str(getattr(voice, "gender", "") or "Unknown").title(),
                                "description": "Installed Windows system voice",
                                "saved": False,
                            })
                finally:
                    try:
                        engine.stop()
                    except Exception:
                        pass
                ready = bool(rows)
                message_text = f"{len(rows)} installed Windows SAPI voice(s) discovered." if ready else (
                    "Windows did not report any installed SAPI voices on this PC."
                )
            except Exception as exc:
                message_text = f"Windows SAPI catalogue could not be read: {exc}"

        elif key in {"customvoice", "voicedesign", "qwenclone"}:
            qwen_mode = {"customvoice": "custom", "voicedesign": "design", "qwenclone": "clone"}[key]
            rows = [
                profile_row(profile) for profile in profiles
                if profile.provider == "qwen-character"
                and str(getattr(profile, "qwen_mode", "custom") or "custom").casefold() == qwen_mode
            ]
            try:
                from app.tts.qwen_character_runtime import runtime_ready, model_installed
                runtime_ok = bool(runtime_ready())
                custom_weights = bool(model_installed("custom-0.6b") or model_installed("custom-1.7b"))
                design_weights = bool(model_installed("design-1.7b"))
                base_weights = bool(model_installed("base-0.6b") or model_installed("base-1.7b"))
            except Exception:
                runtime_ok, custom_weights, design_weights, base_weights = False, False, False, False
            if key == "customvoice":
                ready = runtime_ok and custom_weights
                message_text = (
                    f"{len(rows)} saved voice profile(s); CustomVoice runtime and weights are ready."
                    if ready else
                    "Install or repair the Qwen runtime and at least one CustomVoice model in Models Center."
                )
            elif key == "voicedesign":
                ready = runtime_ok and design_weights and base_weights
                if ready:
                    message_text = "VoiceDesign and its Base identity model are ready. Choose a description/preset, then save the profile."
                elif not runtime_ok:
                    message_text = "Install or repair the Qwen3-TTS runtime in Models Center."
                elif not design_weights:
                    message_text = "Install Qwen VoiceDesign 1.7B in Models Center."
                else:
                    message_text = "VoiceDesign weights are installed, but a Qwen Base model is also required for stable long-form voice identity."
            else:
                ready = runtime_ok and base_weights
                message_text = (
                    "Qwen Voice Clone runtime and Base weights are ready. Choose an authorized reference recording."
                    if ready else
                    "Install or repair the Qwen runtime and a Base voice-clone model in Models Center."
                )
            source = "local"

        elif key == "customref":
            rows = [profile_row(profile) for profile in profiles if profile.provider == "chatterbox"]
            try:
                from app.tts.chatterbox_runtime import runtime_ready as chatterbox_runtime_ready
                ready = bool(chatterbox_runtime_ready())
            except Exception:
                ready = False
            saved_reference_count = sum(
                1 for profile in saved_profiles
                if profile.provider == "chatterbox" and profile.sample_path and Path(profile.sample_path).is_file()
            )
            if not ready:
                message_text = "Install or repair the Chatterbox runtime in Models Center before previewing a cloned voice."
            elif saved_reference_count:
                message_text = f"Chatterbox runtime ready · {saved_reference_count} saved reference-voice profile(s)."
            else:
                message_text = "Chatterbox runtime ready. Import an authorized reference recording to create a voice profile."
            source = "local"

        elif key == "edge":
            from app.tts.providers.edge_tts import EdgeTTSProvider, VOICE_CACHE
            had_cache = VOICE_CACHE.is_file()
            try:
                metadata = EdgeTTSProvider.fetch_voice_metadata(refresh=refresh)
                rows = [{
                    "name": str(item.get("friendly_name") or item.get("name") or ""),
                    "voice_id": str(item.get("name") or ""),
                    "provider": "edge-tts",
                    "language": str(item.get("locale") or ""),
                    "locale": str(item.get("locale") or ""),
                    "region": str(item.get("locale") or "").split("-", 1)[-1],
                    "gender": str(item.get("gender") or "Unknown").title(),
                    "categories": list(item.get("categories") or []),
                    "personalities": list(item.get("personalities") or []),
                    "description": ", ".join(item.get("categories") or item.get("personalities") or []),
                    "saved": False,
                } for item in metadata if item.get("name")]
                ready = bool(rows)
                source = "live" if refresh or not had_cache else "cached"
                message_text = (
                    f"{len(rows)} Edge TTS voices loaded from the {source} catalogue."
                    if ready else "Edge TTS catalogue unavailable. Check internet access, then refresh the catalogue."
                )
            except Exception as exc:
                message_text = f"Edge TTS catalogue could not be loaded: {exc}"
                source = "cached" if had_cache else "unavailable"

        elif key == "eleven":
            from app.tts.providers.elevenlabs import ElevenLabsProvider
            api_key_set = bool(ElevenLabsProvider.load_api_key())
            try:
                metadata = ElevenLabsProvider.fetch_voice_metadata(refresh=refresh)
                rows = [{
                    "name": str(item.get("name") or item.get("voice_id") or ""),
                    "voice_id": str(item.get("voice_id") or ""),
                    "provider": "elevenlabs",
                    "language": str(item.get("language") or ""),
                    "locale": str(item.get("language") or ""),
                    "region": str(item.get("accent") or ""),
                    "gender": str(item.get("gender") or "Neutral").title(),
                    "category": str(item.get("category") or item.get("use_case") or ""),
                    "description": str(item.get("description") or item.get("use_case") or ""),
                    "saved": False,
                } for item in metadata if item.get("voice_id")]
                ready = api_key_set and bool(rows)
                source = "live" if api_key_set and (refresh or rows) else "cached"
                message_text = (
                    f"{len(rows)} ElevenLabs voice(s) loaded from your account."
                    if ready else (
                        "ElevenLabs API key is not configured. Choose Set API Key to connect your account."
                        if not api_key_set else "ElevenLabs returned no voices. Check the account/API key and refresh."
                    )
                )
            except Exception as exc:
                message_text = f"ElevenLabs catalogue could not be loaded: {exc}"
                source = "cached"

        # Include profiles saved for this provider separately so the UI can show
        # both installed/catalogue choices and saved profiles without conflating them.
        profile_provider = {
            "offline": {"piper", "kokoro"}, "sapi": {"windows-sapi"},
            "customvoice": {"qwen-character"}, "voicedesign": {"qwen-character"},
            "qwenclone": {"qwen-character"}, "customref": {"chatterbox"},
            "edge": {"edge-tts"}, "eleven": {"elevenlabs"},
        }[key]
        for profile in saved_profiles:
            if profile.provider not in profile_provider:
                continue
            if key.startswith("qwen") or key in {"customvoice", "voicedesign"}:
                expected_mode = {"customvoice": "custom", "voicedesign": "design", "qwenclone": "clone"}.get(key)
                if expected_mode and str(getattr(profile, "qwen_mode", "custom")).casefold() != expected_mode:
                    continue
            row = profile_row(profile)
            row["saved"] = True
            if not any(item.get("name", "").casefold() == row["name"].casefold() and item.get("voice_id") == row["voice_id"] for item in rows):
                rows.append(row)

        return {"provider": key, "ready": ready, "message": message_text, "source": source, "voices": rows, "count": len(rows)}

    def _current_model_inventory(self, force: bool = False) -> list[dict[str, Any]]:
        """Reuse the latest Models Center scan so Voice Studio sees the same registry state."""
        cached = getattr(self, "_model_inventory_cache", None)
        scanned_at = float(getattr(self, "_model_inventory_cache_at", 0.0) or 0.0)
        if not force and isinstance(cached, list) and time.monotonic() - scanned_at < 5.0:
            return cached
        return self._models_list({})

    def _voice_catalog(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Gate Voice Studio provider choices using the authoritative Models Center inventory."""
        result = self._voice_catalog_base(payload)
        if not isinstance(result, dict):
            return result
        provider = str(payload.get("provider") or result.get("provider") or "").strip().casefold()
        try:
            from app.tts.model_registry import voice_model_inventory_status
            inventory = voice_model_inventory_status(provider, self._current_model_inventory())
        except Exception as exc:
            inventory = {
                "provider": provider,
                "status": "Unavailable",
                "selectable": False,
                "message": f"Model inventory could not be verified: {exc}",
                "components": [],
                "available_variants": [],
            }
        result["model_inventory"] = inventory
        result["ready"] = bool(result.get("ready")) and bool(inventory.get("selectable"))
        if not inventory.get("selectable"):
            result["message"] = str(inventory.get("message") or result.get("message") or "Required model components are unavailable.")
        return result

    def _voice_elevenlabs_design(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Generate temporary ElevenLabs Voice Design candidates without saving them."""
        from app.tts.providers.elevenlabs import ElevenLabsProvider

        candidates = ElevenLabsProvider.design_character_voice(
            style=str(payload.get("style") or "anime"),
            gender=str(payload.get("gender") or "female"),
            age=str(payload.get("age") or "young adult"),
            temperament=str(payload.get("temperament") or "expressive"),
            archetype=str(payload.get("archetype") or "heroine"),
            model_id=str(payload.get("model_id") or "eleven_ttv_v3"),
            seed=int(payload["seed"]) if payload.get("seed") not in (None, "") else None,
        )
        return {"candidates": candidates, "count": len(candidates)}

    def _voice_elevenlabs_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create the selected Voice Design candidate in ElevenLabs and save it locally."""
        from app.tts.providers.elevenlabs import ElevenLabsProvider
        from app.tts.voice_profile import load_profiles

        name = str(payload.get("name") or "").strip()
        generated_id = str(payload.get("generated_voice_id") or "").strip()
        description = str(payload.get("voice_description") or "").strip()
        if not name:
            raise ValueError("Enter a name for the selected premium voice.")
        if len(name) > 160:
            raise ValueError("Voice profile names must be 160 characters or fewer.")
        if not generated_id:
            raise ValueError("Select a generated Voice Design candidate first.")
        # Refuse duplicate names before making a paid provider request.
        if any(profile.name.strip().casefold() == name.casefold() for profile in load_profiles()):
            raise ValueError(f"A voice or profile named '{name}' already exists. Choose another name.")

        created = ElevenLabsProvider.create_designed_voice(
            generated_voice_id=generated_id,
            voice_name=name,
            voice_description=description,
            style=str(payload.get("style") or "anime"),
            gender=str(payload.get("gender") or "female"),
            age=str(payload.get("age") or "young adult"),
        )
        voice_id = str(created.get("voice_id") or "").strip()
        if not voice_id:
            raise RuntimeError("ElevenLabs did not return a voice ID for the new voice.")
        saved = self._voice_save({
            "name": name,
            "provider": "elevenlabs",
            "voice_id": voice_id,
            "model_id": "eleven_v4",
            "backend": "elevenlabs",
            "language": "English",
            "notes": description,
            "authorized": True,
        })
        return {"name": saved["name"], "provider": "elevenlabs", "voice_id": voice_id, "profile": saved}

    def _voice_credentials_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Save an ElevenLabs API key locally without echoing it into logs or UI responses."""
        value = str(payload.get("api_key") or "").strip()
        if not value:
            raise ValueError("Enter a valid ElevenLabs API key.")
        from app.tts.providers.elevenlabs import ElevenLabsProvider
        ElevenLabsProvider.save_api_key(value)
        return {"saved": True, "provider": "elevenlabs"}

    def _elevenlabs_open_web(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Open only official ElevenLabs pages in the user's default browser."""
        target = str(payload.get("target") or "").strip().casefold()
        allowed_urls = {
            "studio": "https://elevenlabs.io/text-to-speech",
            "api_keys": "https://elevenlabs.io/app/settings/api-keys",
        }
        url = allowed_urls.get(target)
        if not url:
            raise ValueError("Choose the official ElevenLabs studio or API-key settings page.")
        if not QDesktopServices.openUrl(QUrl(url)):
            raise OSError("Windows could not open the ElevenLabs page in your default browser.")
        return {"opened": True, "target": target, "url": url}

    def _voice_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        # The UI needs to distinguish installed catalogue voices from saved,
        # reusable profiles. It must not infer "saved" from a provider or voice ID:
        # a saved alias may legitimately point at the same installed Amy/David voice.
        from app.tts.voice_profile import load_saved_profiles

        profiles = load_profiles()
        saved_names = {p.name.strip().casefold() for p in load_saved_profiles()}
        rows = []
        for profile in profiles:
            rows.append({
                "name": profile.name, "provider": profile.provider, "voice_id": profile.voice_id,
                "model_id": profile.model_id, "backend": profile.backend, "language": profile.language or "",
                "sample_path": profile.sample_path, "authorized": bool(profile.authorized),
                "qwen_mode": getattr(profile, "qwen_mode", "custom"),
                "qwen_prompt": getattr(profile, "qwen_prompt", ""),
                "qwen_seed": getattr(profile, "qwen_seed", None),
                "qwen_profile_id": getattr(profile, "qwen_profile_id", ""),
                "qwen_anchor_path": getattr(profile, "qwen_anchor_path", None),
                "qwen_anchor_text": getattr(profile, "qwen_anchor_text", ""),
                "reference_text": getattr(profile, "reference_text", ""),
                "notes": getattr(profile, "notes", ""),
                "exaggeration": getattr(profile, "exaggeration", 0.5),
                "cfg_weight": getattr(profile, "cfg_weight", 0.35),
                "style_preset": getattr(profile, "style_preset", "Natural"),
                "saved": profile.name.strip().casefold() in saved_names,
            })
        return rows

    def _find_profile(self, name: str | None):
        wanted = str(name or "").strip().casefold()
        if not wanted:
            return None
        # Prefer the persistent record over a built-in display entry. This retains
        # the user's prompt, reference audio, language, model mode and settings.
        from app.tts.voice_profile import load_saved_profiles
        saved = next(
            (profile for profile in load_saved_profiles()
             if profile.name.strip().casefold() == wanted),
            None,
        )
        if saved is not None:
            return saved
        return next((p for p in load_profiles() if p.name.strip().casefold() == wanted), None)

    def _voice_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Delete a saved custom profile only when no local project depends on it."""
        from app.tts.voice_profile import load_saved_profiles, save_profiles

        name = str(payload.get("profile_name") or payload.get("name") or "").strip()
        if not name:
            raise ValueError("Choose a saved custom voice profile to delete.")
        saved = load_saved_profiles()
        profile = next((item for item in saved if item.name.casefold() == name.casefold()), None)
        if profile is None:
            raise ValueError("Built-in voices cannot be deleted. Choose a saved custom profile.")
        series_defaults_root = Path(settings_root()) / "series-narrators"
        if series_defaults_root.is_dir():
            for path in sorted(series_defaults_root.glob("*.json")):
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError(
                        "A saved series narrator preference could not be verified. "
                        "The profile was not deleted to protect narrator assignments."
                    ) from exc
                if isinstance(record, dict) and str(record.get("profile_name") or "").strip().casefold() == name.casefold():
                    series_name = str(record.get("series") or path.stem)
                    raise ValueError(
                        f"The profile is the saved narrator default for series '{series_name}'. "
                        "Change that series narrator default before deleting this profile."
                    )
        for project in list_projects():
            state = load_state(project.folder)
            narrator_source = str(state.get("narrator_profile_source") or "").strip().casefold()
            if narrator_source not in {"series_default", "none"} and str(state.get("voice_profile") or "").casefold() == name.casefold():
                raise ValueError(f'The profile is the selected narrator for "{project.title}". Select another narrator before deleting it.')
            assigned = state.get("characters") or []
            if any(isinstance(item, dict) and str(item.get("voice_profile") or "").casefold() == name.casefold()
                   for item in assigned):
                raise ValueError(f'The profile is assigned to a character in "{project.title}". Reassign that character before deleting it.')
        save_profiles([item for item in saved if item.name.casefold() != name.casefold()])
        return {"name": name, "deleted": True, "remaining": len(load_saved_profiles())}

    def _voice_select(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        profile = self._find_profile(payload.get("profile_name") or payload.get("name"))
        if profile is None:
            raise ValueError("The selected voice is not in the installed or saved voice catalogue.")
        state = load_state(project.folder)
        state.update({"voice_profile": profile.name, "voice_id": profile.voice_id,
                      "backend": str(payload.get("backend") or profile.backend or "automatic"),
                      "narrator": profile.name, "narrator_profile_source": "project_override"})
        save_state(project.folder, state)
        return {"name": profile.name, "provider": profile.provider, "voice_id": profile.voice_id,
                "backend": state["backend"], "saved": True}

    def _preview_profile_from_payload(self, payload: dict[str, Any], state: dict[str, Any]):
        """Resolve a saved profile or construct an in-memory profile for a live preview.

        Previewing an installed/live catalogue voice must not require saving a profile
        first. These temporary profiles are passed only to the preview worker and are
        never written to the persistent voice catalogue.
        """
        from uuid import uuid4
        from app.tts.voice_profile import VoiceProfile

        profile_name = str(payload.get("profile_name") or "").strip()
        provider = str(payload.get("provider") or "").strip().casefold()
        voice_id = str(payload.get("voice_id") or "").strip()
        allowed = {"piper", "kokoro", "windows-sapi", "qwen-character", "chatterbox", "edge-tts", "elevenlabs"}

        # When the frontend explicitly sends the selected catalogue voice, use
        # that provider/voice ID rather than an unrelated name in the profile box.
        # This is what makes preview match the currently selected voice card.
        if provider not in allowed or not voice_id:
            existing = self._find_profile(profile_name or state.get("voice_profile"))
            if existing is not None:
                return existing
        if provider not in allowed or not voice_id:
            return None

        sample_path = str(payload.get("sample_path") or "").strip() or None
        qwen_mode = str(payload.get("qwen_mode") or ("clone" if provider == "chatterbox" else "custom")).strip().casefold()
        if provider == "chatterbox" and not sample_path:
            raise ValueError("Save the reference-voice profile first so its imported recording can be used for preview.")
        if provider == "qwen-character" and qwen_mode in {"clone", "voiceclone", "voice-clone"} and not sample_path:
            raise ValueError("Save the Qwen Voice Clone profile first so its permitted reference recording can be imported.")

        qwen_profile_id = str(payload.get("qwen_profile_id") or "")
        if provider == "qwen-character" and not qwen_profile_id:
            qwen_profile_id = uuid4().hex
        name = profile_name or ("Preview · " + voice_id)
        return VoiceProfile(
            name=name,
            provider=provider,
            voice_id=voice_id,
            sample_path=sample_path,
            model_id=str(payload.get("model_id") or ("auto" if provider == "qwen-character" else provider)),
            backend=str(payload.get("backend") or ("automatic" if provider in {"piper", "kokoro", "qwen-character"} else provider)),
            language=str(payload.get("language") or "English"),
            notes=str(payload.get("notes") or payload.get("qwen_prompt") or "")[:4000],
            authorized=bool(payload.get("authorized", False)),
            exaggeration=max(0.0, min(1.0, float(payload.get("exaggeration", 0.5)))),
            cfg_weight=max(0.0, min(1.0, float(payload.get("cfg_weight", 0.35)))),
            style_preset=str(payload.get("style_preset") or "Natural"),
            qwen_mode=qwen_mode,
            qwen_prompt=str(payload.get("qwen_prompt") or "")[:4000],
            qwen_seed=int(payload["qwen_seed"]) if payload.get("qwen_seed") not in (None, "") else None,
            reference_text=str(payload.get("reference_text") or "")[:10000],
            qwen_profile_id=qwen_profile_id,
        )


    def _release_preview_provider(self, provider) -> None:
        closer = getattr(self, "_close_provider_quietly", None)
        if callable(closer):
            closer(provider)
            return
        close = getattr(provider, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                log.warning("Could not close a voice-preview provider cleanly.", exc_info=True)

    def _close_provider_quietly(self, provider) -> None:
        close = getattr(provider, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                log.warning("Could not close a voice-preview provider cleanly.", exc_info=True)

    def close_preview_provider_cache(self) -> None:
        """Release an idle warm preview model before app shutdown or full generation."""
        with self._preview_provider_cache_lock:
            entry = self._preview_provider_cache
            timer = self._preview_provider_cache_timer
            self._preview_provider_cache = None
            self._preview_provider_cache_timer = None
        if timer is not None:
            timer.cancel()
        if entry:
            self._close_provider_quietly(entry.get("provider"))

    def _take_preview_provider_cache(self, signature: str):
        with self._preview_provider_cache_lock:
            entry = self._preview_provider_cache
            if not entry or entry.get("signature") != signature:
                return None
            timer = self._preview_provider_cache_timer
            self._preview_provider_cache = None
            self._preview_provider_cache_timer = None
        if timer is not None:
            timer.cancel()
        return entry

    def _expire_preview_provider_cache(self, signature: str) -> None:
        with self._preview_provider_cache_lock:
            entry = self._preview_provider_cache
            if not entry or entry.get("signature") != signature:
                return
            timer = self._preview_provider_cache_timer
            self._preview_provider_cache = None
            self._preview_provider_cache_timer = None
        if timer is not None and timer is not threading.current_thread():
            timer.cancel()
        self._close_provider_quietly(entry.get("provider"))

    def _cache_preview_provider(self, signature: str, provider, voice) -> None:
        """Keep a successful Qwen preview worker warm briefly, without changing model quality."""
        self.close_preview_provider_cache()
        timer = threading.Timer(90.0, self._expire_preview_provider_cache, args=(signature,))
        timer.daemon = True
        with self._preview_provider_cache_lock:
            self._preview_provider_cache = {
                "signature": signature,
                "provider": provider,
                "voice": voice,
            }
            self._preview_provider_cache_timer = timer
        timer.start()

    def _assert_no_active_audio_synthesis(self, activity: str) -> None:
        with self._jobs_lock:
            active = [
                job for job in self._jobs.values()
                if str(job.get("state") or "").casefold() in {"queued", "running", "cancel_requested"}
                and str(job.get("type") or "").casefold() in {
                    "voice-preview", "sound-design-preview", "production-preview", "audiobook-generation"
                }
            ]
        if active:
            title = str(active[0].get("title") or "Audio synthesis")
            raise RuntimeError(
                f"Cannot {activity} while {title} is still running. "
                "Wait for the active preview or audiobook generation to finish first."
            )

    def _narrator_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Preview actual narration with the effective saved narrator profile.

        The only projectless mode is the Create Series setup preview, which uses
        an explicitly selected saved Voice Studio profile and sample narration.
        """
        if payload.get("series_setup_preview") is True:
            profile_name = str(payload.get("profile_name") or "").strip()
            profile = self._find_profile(profile_name)
            if profile is None:
                raise ValueError("Choose an available saved Voice Studio profile for the series narrator.")
            text_value = str(payload.get("text") or "")
            if not text_value.strip():
                raise ValueError("Enter sample narration text before previewing the series narrator.")
            if len(text_value) > 1_000_000:
                raise ValueError("The series narrator preview text is too long.")
            return self._voice_preview({
                "profile_name": profile.name,
                "text": text_value,
                "duration_seconds": payload.get("duration_seconds") or 30,
                "route_character_cast": False,
                "allow_projectless_preview": True,
            })

        project = self._active_project()
        state = load_state(project.folder)
        try:
            chapter_number = int(payload.get("chapter_number"))
            start = int(payload.get("start"))
            end = int(payload.get("end"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Select a narration passage in the active chapter before previewing.") from exc
        chapter = next((item for item in project.chapters if int(item.number) == chapter_number), None)
        if chapter is None:
            raise ValueError("The selected chapter no longer exists. Refresh Chapter Studio and select the passage again.")
        source_text = str(chapter.text or "")
        selected_text = str(payload.get("text") or "")
        if start < 0 or end <= start or end > len(source_text) or source_text[start:end] != selected_text:
            raise ValueError("The selected passage changed or its source positions are stale. Save the chapter and select the narration again.")

        if getattr(project, "folder", None) is None:
            # Unsaved test harnesses retain the pure source segmenter. Installed
            # projects use the persisted index shared with Character Studio/Production.
            from app.chapters.speaker_segmentation import segment_chapter_speakers
            segments = segment_chapter_speakers(chapter)
            intersecting = [
                segment for segment in segments
                if int(segment.end) > start and int(segment.start) < end
            ]
            invalid_narration = any(segment.kind != "narration" for segment in intersecting)
        else:
            from app.chapters.passage_index import load_or_build_passage_index
            passage_index = load_or_build_passage_index(
                project.folder, project.chapters,
                suggested_passages=state.get("character_dialogue_suggestions") or [],
            )
            intersecting = [
                row for row in passage_index["passages"]
                if str(row.get("chapter_id") or "") == str(chapter.chapter_id)
                and int(row.get("end", 0)) > start and int(row.get("start", 0)) < end
            ]
            invalid_narration = any(row.get("kind") != "narration" for row in intersecting)
        if not intersecting or invalid_narration:
            raise ValueError(
                "Narrator Preview accepts narration only. Select text classified as Narrator; "
                "character dialogue and Needs Speaker Review passages cannot be previewed as narration."
            )

        series = self._project_series_name(project, state)
        narrator = self._narrator_series_default_read(project, state, series)
        profile_name = str(narrator.get("effective_profile_name") or "").strip()
        if not profile_name:
            raise ValueError("No narrator voice is configured for this project or its series.")
        if not narrator.get("profile_available"):
            raise ValueError(
                f"The effective narrator profile '{profile_name}' is unavailable. Restore or select a valid saved Voice Studio profile."
            )
        return self._voice_preview({
            "profile_name": profile_name,
            "text": selected_text,
            "chapter_number": chapter_number,
            "duration_seconds": payload.get("duration_seconds") or 30,
            "route_character_cast": False,
        })

    def _voice_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_no_active_model_lifecycle("generate a voice preview")
        check_active = getattr(self, "_assert_no_active_audio_synthesis", None)
        if callable(check_active):
            check_active("generate a preview")
        try:
            project = self._active_project()
            state = load_state(project.folder)
        except ValueError:
            if not payload.get("allow_projectless_preview"):
                raise
            project = None
            state = {}
        profile = PremiumV2Bridge._preview_profile_from_payload(self, payload, state)
        if profile is None:
            raise ValueError("Choose an installed voice or load a saved voice profile before previewing.")
        text_value = str(payload.get("text") or "")
        number = payload.get("chapter_number")
        selected_chapter = None
        if project is not None and number not in (None, ""):
            try:
                requested_chapter_number = int(number)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Choose a valid chapter number for the preview.") from exc
            selected_chapter = next(
                (chapter for chapter in project.chapters
                 if int(chapter.number) == requested_chapter_number),
                None,
            )
            if selected_chapter is None:
                raise ValueError("The selected chapter is no longer available. Refresh the chapter list and try again.")
            if not str(selected_chapter.text or "").strip() and not text_value.strip():
                raise ValueError("The selected chapter contains no narration text.")
            state["_preview_chapter_number"] = int(selected_chapter.number)
            state["_preview_chapter_title"] = str(
                selected_chapter.title or f"Chapter {selected_chapter.number}"
            )
            state["_preview_chapter_id"] = str(getattr(selected_chapter, "chapter_id", "") or getattr(selected_chapter, "id", "") or "")
            state["_preview_chapter_text"] = str(selected_chapter.text or "")
            eligible_preview_chapters = [
                item for item in project.chapters
                if not getattr(item, "skip_for_generation", False) and str(item.text or "").strip()
            ]
            selected_preview_index = next(
                (index for index, item in enumerate(eligible_preview_chapters, start=1)
                 if int(item.number) == int(selected_chapter.number)),
                1,
            )
            state["_preview_chapter_index"] = selected_preview_index
            state["_preview_chapter_is_first"] = selected_preview_index == 1
            state["_preview_chapter_is_last"] = selected_preview_index == len(eligible_preview_chapters)
            state["_preview_chapters_total"] = len(eligible_preview_chapters)
        if not text_value.strip():
            if project is None:
                raise ValueError("Enter preview text or select a chapter with narration.")
            chapter = selected_chapter or next(
                (candidate for candidate in project.chapters if (candidate.text or "").strip()),
                None,
            )
            if chapter is None:
                raise ValueError("Select a chapter that contains narration text.")
            text_value = chapter.text
        seconds = int(payload.get("duration_seconds") or payload.get("duration") or 30)
        if seconds not in {10, 30, 60, 90}:
            raise ValueError("Preview duration must be 10, 30, 60, or 90 seconds.")
        route_character_cast = payload.get("route_character_cast", True)
        if not isinstance(route_character_cast, bool):
            raise ValueError("Character cast routing must be a boolean preview option.")
        apply_pronunciation_rules = payload.get("apply_pronunciation_rules", True)
        if not isinstance(apply_pronunciation_rules, bool):
            raise ValueError("Pronunciation preview handling must be a boolean option.")
        if not apply_pronunciation_rules:
            # Row-level Written vs Pronounce-as comparison must synthesize exactly
            # the text the user selected rather than being transformed by the rule
            # being tested. Ordinary previews keep the saved project/global rules.
            state["_bypass_pronunciation_dictionary"] = True
        include_sound_design = bool(payload.get("include_sound_design"))
        if include_sound_design:
            state["_include_sound_design_preview"] = True
        production_preview = bool(payload.get("_production_preview"))
        job_type = "production-preview" if production_preview else ("sound-design-preview" if include_sound_design else "voice-preview")
        job_title = ("Production preview · " if production_preview else "Sound Design mix preview · " if include_sound_design else "Preview · ") + profile.name
        job_id = self._new_job(job_type, job_title,
                               f"Generate up to {seconds} seconds using the selected provider", project)
        cancel_event = threading.Event()
        if not hasattr(self, "_preview_cancel_events"):
            self._preview_cancel_events = {}
        with getattr(self, "_jobs_lock", threading.RLock()):
            self._preview_cancel_events[job_id] = cancel_event
        self._job_update(job_id, state="running", started_at=self._now(), stage="Preparing preview", progress=2,
                          current_chapter=int(selected_chapter.number) if selected_chapter else 0,
                          current_chapter_title=str(selected_chapter.title or "") if selected_chapter else "",
                          current_chapter_id=str(getattr(selected_chapter, "chapter_id", "") or getattr(selected_chapter, "id", "") or "") if selected_chapter else "",
                          chapters_total=len(project.chapters) if project is not None and selected_chapter else 0)
        threading.Thread(
            target=self._preview_worker,
            args=(job_id, profile, text_value, seconds, state, cancel_event, route_character_cast),
            daemon=True,
            name="RyuPremiumPreview",
        ).start()
        return {"job_id": job_id, "state": "running", "duration_seconds": seconds, "profile_name": profile.name}

    def _voice_preview_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Copy the validated in-app voice preview through a native Save As dialog."""
        source_value = str(payload.get("source_path") or "").strip()
        if not source_value:
            raise ValueError("Generate a validated voice preview before saving it.")
        source = Path(source_value).expanduser().resolve()
        preview_root = (app_root() / "Previews").resolve()
        if source.parent != preview_root or not source.name.startswith("preview_") or source.suffix.casefold() != ".wav":
            raise ValueError("Only a generated Ryu voice-preview WAV can be saved from this action.")
        if not source.is_file() or source.stat().st_size < 1024:
            raise FileNotFoundError("The generated preview file is no longer available. Generate it again.")

        import re as _re
        suggested = str(payload.get("suggested_name") or "Ryu Voice Preview").strip()
        suggested = _re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", suggested).strip(" .-")[:100] or "Ryu Voice Preview"
        default_path = Path.home() / "Downloads" / f"{suggested}.wav"
        selected, _filter = QFileDialog.getSaveFileName(
            None, "Save Voice Preview", str(default_path), "WAV audio (*.wav)"
        )
        if not selected:
            return {"cancelled": True}
        destination = Path(selected).expanduser()
        if destination.suffix.casefold() != ".wav":
            destination = destination.with_suffix(".wav")
        destination = destination.resolve()
        if destination == source:
            raise ValueError("Choose a different destination from the temporary preview file.")
        shutil.copy2(source, destination)
        return {"cancelled": False, "path": str(destination), "bytes": destination.stat().st_size}

    def _production_preview_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Save only the validated output belonging to the active Production preview job."""
        job_id = str(payload.get("job_id") or "").strip()
        project_folder = str(payload.get("project_folder") or "").strip()
        source_value = str(payload.get("source_path") or "").strip()
        try:
            chapter_number = int(payload.get("chapter_number"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("The Production preview chapter identity is invalid.") from exc
        if not job_id or not project_folder or not source_value:
            raise ValueError("A completed Production preview job, project and audio file are required.")
        with self._jobs_lock:
            job = dict(self._jobs.get(job_id) or {})
        if job.get("type") != "production-preview" or job.get("state") != "completed":
            raise ValueError("Only a completed Production preview can be saved.")
        if str(job.get("project_folder") or "") != project_folder:
            raise ValueError("This preview belongs to a different project. Reopen its project before saving.")
        if int(job.get("current_chapter") or 0) != chapter_number:
            raise ValueError("This preview belongs to a different chapter. Generate the selected chapter again.")
        requested_chapter_id = str(payload.get("chapter_id") or "").strip()
        expected_chapter_id = str(job.get("current_chapter_id") or "").strip()
        if expected_chapter_id and requested_chapter_id != expected_chapter_id:
            raise ValueError("This preview belongs to a different saved chapter identity. Generate the selected chapter again.")
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        expected_source = str(result.get("output_path") or "").strip()
        if not expected_source:
            raise ValueError("The completed Production preview has no validated audio output.")
        source = Path(source_value).expanduser().resolve()
        expected = Path(expected_source).expanduser().resolve()
        preview_root = (app_root() / "Previews").resolve()
        if source != expected or source.parent != preview_root or source.suffix.casefold() not in {".wav", ".m4a"}:
            raise ValueError("The selected audio file does not belong to this Production preview job.")
        if not source.is_file() or source.stat().st_size < 1024:
            raise FileNotFoundError("The Production preview file is no longer available. Generate it again.")
        import re as _re
        suggested = str(payload.get("suggested_name") or "Ryu Production Preview").strip()
        suggested = _re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", suggested).strip(" .-")[:100] or "Ryu Production Preview"
        default_suffix = source.suffix.casefold()
        default_path = Path.home() / "Downloads" / f"{suggested}{default_suffix}"

        # The frozen-app acceptance harness can exercise the real Save command
        # without blocking the unattended Windows runner on a native file dialog.
        # This path is enabled only when all three private acceptance variables
        # are present, and the chosen file must remain inside the harness temp
        # directory associated with its result marker. Normal desktop sessions
        # always use the native Save As dialog below.
        acceptance_script = str(os.environ.get("RYU_SOUND_UI_ACCEPTANCE_SCRIPT") or "").strip()
        acceptance_marker = str(os.environ.get("RYU_SOUND_UI_ACCEPTANCE_MARKER") or "").strip()
        acceptance_save_path = str(os.environ.get("RYU_SOUND_UI_ACCEPTANCE_PREVIEW_SAVE_PATH") or "").strip()
        if acceptance_script and acceptance_marker and acceptance_save_path:
            allowed_root = Path(acceptance_marker).expanduser().resolve().parent
            destination = Path(acceptance_save_path).expanduser().resolve()
            try:
                destination.relative_to(allowed_root)
            except ValueError as exc:
                raise ValueError("The packaged preview Save As destination must remain inside its acceptance temp folder.") from exc
            selected = str(destination)
        else:
            selected, _filter = QFileDialog.getSaveFileName(
                None, "Save Production Chapter Preview", str(default_path),
                "Production preview audio (*.wav *.m4a);;WAV audio (*.wav);;M4A audio (*.m4a)"
            )
            if not selected:
                return {"cancelled": True}
            destination = Path(selected).expanduser()
            if destination.suffix.casefold() != default_suffix:
                destination = destination.with_suffix(default_suffix)
            destination = destination.resolve()
        if destination == source:
            raise ValueError("Choose a different destination from the temporary preview file.")
        shutil.copy2(source, destination)
        return {"cancelled": False, "path": str(destination), "bytes": destination.stat().st_size,
                "job_id": job_id, "chapter_number": chapter_number}

    def _sound_preview_book(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Queue a full-book mix preview from saved narration without re-synthesis."""
        from app.ui.full_book_preview import start_full_book_preview
        return start_full_book_preview(self)

    def _render_sound_design_preview(self, source: Path, job_id: str, state: dict[str, Any]) -> Path:
        """Render the selected chapter with saved BGM/cue rules used by final assembly."""
        import json
        from app.audio.assembler import (
            _chapter_bgm_fade_out, _chapter_bgm_override_for, _concat_audio_files,
            _duration_ms, _resolve_cue_audio, _mix_chapter_bgm, _scale_audio_gain,
            _run, _selected_music_recipe,
        )
        from app.audio.library import (
            effective_background_audio_mode, is_chapter_transition_sound_enabled,
            resolve_music_track, validate_saved_audio_paths,
        )

        audio_mode = effective_background_audio_mode(state)
        validate_saved_audio_paths(state)
        sound_enabled = audio_mode != "off"
        transition_enabled = sound_enabled and is_chapter_transition_sound_enabled(state)
        # The preview job owns the chapter/project snapshot captured when it
        # was created. Do not query _active_project() from this worker: the user
        # may have switched projects while synthesis was running, and a late
        # lookup would mix live navigation state into the original job.
        selected_number = int(state.get("_preview_chapter_number") or 1)
        selected_index = int(state.get("_preview_chapter_index") or 1)
        is_first_chapter = bool(state.get("_preview_chapter_is_first", selected_index == 1))
        is_last_chapter = bool(state.get("_preview_chapter_is_last", selected_index == 1))
        chapter_title = str(state.get("_preview_chapter_title") or "Preview")
        chapter_text = str(state.get("_preview_chapter_text") or "")

        preview_root = app_root() / "Previews"
        preview_root.mkdir(parents=True, exist_ok=True)
        original_source = Path(source).resolve()
        output = preview_root / f"sound_mix_preview_{job_id}.m4a"
        cleanup_paths: list[Path] = []
        audio_source = original_source

        def check_cancelled() -> None:
            events = getattr(self, "_preview_cancel_events", {})
            event = events.get(str(job_id)) if isinstance(events, dict) else None
            if event is not None and event.is_set():
                raise RuntimeError("Production sound-design preview cancelled.")

        try:
            source_duration_ms = max(1, _duration_ms(audio_source))
            volume = max(0.0, min(0.50, float(
                state.get("background_audio_volume")
                if state.get("background_audio_volume") is not None else 0.18
            )))
            cue_volume = max(0.0, min(0.50, float(
                state.get("sound_cue_volume")
                if state.get("sound_cue_volume") is not None else 0.25
            )))
            overrides = state.get("chapter_bgm_overrides")
            overrides = overrides if isinstance(overrides, dict) else {}
            raw_strategy = str(
                state.get("chapter_bgm_strategy") or ("custom" if overrides else "same")
            ).strip().casefold()
            if raw_strategy in {"same", "same-bgm", "same_bgm"}:
                strategy = "same"
            elif raw_strategy in {"custom", "chapter-based", "chapter_based", "chapter"}:
                strategy = "chapter-based"
            else:
                raise ValueError(f"Unsupported chapter BGM strategy: {raw_strategy}")

            mood, variation = _selected_music_recipe(
                chapter_title, chapter_text, str(state.get("auto_music_style") or "auto"), None
            )
            cues_mixed = False
            cue_prefix_duration_ms = 0
            if transition_enabled and selected_index:
                cue_kind = "opening" if is_first_chapter else "page"
                cue_value = state.get("opening_cue_path") if cue_kind == "opening" else state.get("page_turn_cue_path")
                if cue_value and cue_volume > 0:
                    cue = _resolve_cue_audio(
                        preview_root, cue_kind, str(state.get("sound_cue_style") or "library"),
                        variation, mood, cue_value
                    )
                    if cue is not None:
                        leveled = _scale_audio_gain(
                            cue, preview_root / f"sound-preview-{job_id}-{cue_kind}-level.m4a",
                            cue_volume, "192k"
                        )
                        cue_prefix_duration_ms = max(0, int(_duration_ms(leveled)))
                        prefixed = preview_root / f"sound-preview-{job_id}-{cue_kind}.m4a"
                        _concat_audio_files(leveled, audio_source, prefixed, "192k")
                        audio_source = prefixed
                        cues_mixed = True
                        cleanup_paths.extend([leveled, prefixed])

            music_path = None
            offset_ms = 0
            fade_out = float(
                state.get("background_audio_fade_out")
                if state.get("background_audio_fade_out") is not None else 3.0
            )
            # Chapter-Based is an explicit-only policy even for legacy projects
            # whose audio source mode still says auto. Never route those projects
            # through mood-selected fallback music.
            if sound_enabled and (audio_mode == "manual" or strategy == "chapter-based"):
                if strategy == "chapter-based":
                    override = {}
                    chapter_number = selected_number or 1
                    metadata = {
                        "chapter": chapter_number,
                        "chapter_id": str(state.get("_preview_chapter_id") or ""),
                    }
                    import tempfile as _tempfile
                    with _tempfile.TemporaryDirectory(prefix="ryu-preview-chapter-key-") as temp:
                        chapter_dir = Path(temp) / f"{chapter_number:03d}_selected"
                        chapter_dir.mkdir(parents=True, exist_ok=True)
                        (chapter_dir / "narration.json").write_text(
                            json.dumps(metadata), encoding="utf-8"
                        )
                        override = _chapter_bgm_override_for(
                            chapter_dir, chapter_number, overrides
                        )
                    rule = str(override.get("rule") or "none").strip().casefold()
                    if rule == "default":
                        rule = "none"
                    if rule == "custom":
                        raw_music = str(override.get("path") or "").strip()
                        if not raw_music:
                            raise ValueError(f"Chapter {selected_number} uses custom BGM but no track is saved.")
                        music_path = Path(raw_music).expanduser()
                        volume = max(0.0, min(0.50, float(override.get("volume", volume))))
                        start_offset = str(override.get("start_offset") or "immediate").strip().casefold()
                        if start_offset == "after_10_seconds":
                            offset_ms = 10_000
                        elif start_offset == "after_first_paragraph":
                            try:
                                paragraph_offset_ms = int(state.get("_preview_first_paragraph_offset_ms") or 0)
                            except (TypeError, ValueError, OverflowError):
                                paragraph_offset_ms = 0
                            if paragraph_offset_ms <= 0:
                                raise ValueError(
                                    "The preview could not verify an exact audio boundary after paragraph one. "
                                    "Increase the preview duration so the complete first paragraph is included, "
                                    "or choose Immediate / After 10 seconds."
                                )
                            if paragraph_offset_ms >= source_duration_ms:
                                raise ValueError(
                                    "The selected preview ends before the first-paragraph boundary. "
                                    "Choose a longer preview duration or use Immediate / After 10 seconds."
                                )
                            offset_ms = cue_prefix_duration_ms + paragraph_offset_ms
                        fade_out = _chapter_bgm_fade_out(
                            str(override.get("end_behavior") or "fade_before_end"), fade_out
                        )
                    elif rule != "none":
                        raise ValueError(f"Unsupported chapter-based BGM rule for chapter {selected_number}: {rule}")
                else:
                    raw_music = str(state.get("background_audio_path") or "").strip()
                    music_path = Path(raw_music).expanduser() if raw_music else None
            elif sound_enabled and audio_mode == "auto":
                music_path = resolve_music_track(
                    mood, selected_track=state.get("auto_music_track_path") or None,
                    seed_text=f"{chapter_title}|{chapter_text}|{selected_number}",
                )

            check_cancelled()
            if music_path is not None and volume > 0:
                mixed = preview_root / f"sound-preview-{job_id}-bgm.m4a"
                audio_source = _mix_chapter_bgm(
                    audio_source, music_path, mixed, volume,
                    fade_in=float(
                        state.get("background_audio_fade_in")
                        if state.get("background_audio_fade_in") is not None else 2.0
                    ),
                    fade_out=fade_out, start_offset_ms=offset_ms, bitrate="192k",
                )
                cleanup_paths.append(Path(mixed))

            if transition_enabled and is_last_chapter:
                closing_value = state.get("ending_cue_path")
                if closing_value and cue_volume > 0:
                    closing = _resolve_cue_audio(
                        preview_root, "ending", str(state.get("sound_cue_style") or "library"),
                        variation, mood, closing_value
                    )
                    if closing is not None:
                        leveled = _scale_audio_gain(
                            closing, preview_root / f"sound-preview-{job_id}-ending-level.m4a",
                            cue_volume, "192k"
                        )
                        ended = preview_root / f"sound-preview-{job_id}-ending.m4a"
                        _concat_audio_files(audio_source, leveled, ended, "192k")
                        audio_source = ended
                        cues_mixed = True
                        cleanup_paths.extend([leveled, ended])

            state["_preview_sound_configuration"] = {
                "background_audio_mode": audio_mode,
                "chapter_bgm_strategy": strategy,
                "chapter_number": selected_number or None,
                "chapter_title": chapter_title,
                "bgm_enabled": bool(sound_enabled and music_path is not None and volume > 0),
                "fixed_cues_enabled": bool(transition_enabled),
                "cues_mixed": bool(cues_mixed),
            }
            check_cancelled()
            if audio_source.suffix.casefold() == ".m4a":
                # Cue concatenation/BGM mixing already produced an AAC M4A.
                # Keep the exact output rather than transcoding it again.
                shutil.copy2(audio_source, output)
            else:
                # Voice Only, Same BGM with no selected track, and Chapter-Based
                # chapters with no override can remain as a synthesized WAV.
                # Encode it as AAC before using the .m4a preview destination;
                # never just rename/copy WAV bytes under an M4A extension.
                _run([
                    "-i", str(audio_source), "-vn", "-c:a", "aac",
                    "-b:a", "192k", "-ar", "44100", str(output),
                ])
            if not output.is_file() or output.stat().st_size < 1024:
                raise RuntimeError("The Production chapter mix preview could not be rendered.")
            if _duration_ms(output) < source_duration_ms - 1500:
                raise RuntimeError("The Production chapter mix preview is missing narration audio.")
            return output
        finally:
            for candidate in cleanup_paths:
                try:
                    Path(candidate).unlink(missing_ok=True)
                except OSError:
                    pass


    def _preview_worker(
        self, job_id: str, profile, text_value: str, seconds: int,
        state: dict[str, Any], cancel_event=None, route_character_cast: bool = True,
    ) -> None:
        from app.tts.preview import PreviewCancelledError
        output = app_root() / "Previews" / f"preview_{job_id}.wav"
        preview_path = output
        provider = None
        voice = None
        cache_signature = None
        cacheable_provider = False
        preview_succeeded = False
        heartbeat_stop = threading.Event()
        heartbeat_thread = None
        request_started_at = time.monotonic()
        provider_setup_seconds = None
        synthesis_finished_at = None
        playback_path: Path = output
        try:
            if cancel_event is not None and cancel_event.is_set():
                raise PreviewCancelledError("Preview cancelled by user.")
            # Cast routing is explicitly disabled for narrator-only Production
            # previews; persisted assignments must not leak into that mode.
            cast_assignments: dict[str, str] = {}
            cast_profiles: dict[str, Any] = {}
            # Character Studio's selected-line audition must use the draft-selected
            # profile directly. Production and ordinary Voice Studio previews keep
            # the saved cast router unless this explicit option is false.
            if route_character_cast:
                available_profiles = {p.name.casefold(): p for p in load_profiles()}
                for character in state.get("characters") or []:
                    if not isinstance(character, dict):
                        continue
                    assigned_name = str(character.get("voice_profile") or "").strip()
                    if not assigned_name:
                        continue
                    assigned_profile = available_profiles.get(assigned_name.casefold())
                    if assigned_profile is None:
                        raise ValueError(
                            f"Character '{character.get('name', 'Unknown')}' uses voice profile "
                            f"'{assigned_name}', which is no longer available. Reassign its voice in Character Studio."
                        )
                    cast_profiles[assigned_profile.name] = assigned_profile
                    character_names = [str(character.get("name") or "").strip()]
                    aliases = character.get("aliases") or []
                    if isinstance(aliases, list):
                        character_names.extend(str(alias).strip() for alias in aliases)
                    for character_name in character_names:
                        if character_name:
                            cast_assignments[character_name] = assigned_profile.name

            cache_signature = json.dumps({
                "profile": getattr(profile, "__dict__", str(profile)),
                "route_character_cast": bool(route_character_cast),
                "cast_profiles": {
                    name: getattr(item, "__dict__", str(item))
                    for name, item in sorted(cast_profiles.items(), key=lambda pair: pair[0].casefold())
                },
                "cast_assignments": dict(sorted(cast_assignments.items(), key=lambda pair: pair[0].casefold())),
                "narrating_character": str(state.get("narrating_character") or ""),
                "backend": str(state.get("backend") or "automatic"),
            }, sort_keys=True, default=str, ensure_ascii=False)
            cacheable_provider = str(getattr(profile, "provider", "") or "").casefold() == "qwen-character"
            cached_entry = self._take_preview_provider_cache(cache_signature) if cacheable_provider else None
            if cached_entry:
                provider = cached_entry["provider"]
                voice = cached_entry["voice"]
            else:
                # Switching providers/signatures releases the previous warm model;
                # otherwise repeated previews would leave heavyweight workers alive.
                close_cache = getattr(self, "close_preview_provider_cache", None)
                if callable(close_cache):
                    close_cache()
                preview_profile = profile
                if (str(getattr(profile, "provider", "") or "").casefold() == "qwen-character"
                        and str(getattr(profile, "qwen_mode", "") or "").casefold() == "design"):
                    # Keep the full-quality VoiceDesign profile/prompt/seed but use
                    # the dedicated one-pass audition path for preview jobs. Production
                    # narration continues to build/reuse the stable Base identity bank.
                    import copy
                    preview_profile = copy.copy(profile)
                    preview_profile.qwen_mode = "design-preview"
                provider, voice = provider_from_profile(preview_profile)
                if cast_assignments:
                    from app.tts.cast_provider import CastAwareProvider
                    provider = CastAwareProvider(
                        provider, voice, cast_profiles, cast_assignments,
                        narrating_character=str(state.get("narrating_character") or ""),
                        backend_override=str(state.get("backend") or "automatic"),
                    )
            def provider_status(detail: str) -> None:
                detail_text = str(detail or "").strip()
                if not detail_text or (cancel_event is not None and cancel_event.is_set()):
                    return
                lower_detail = detail_text.casefold()
                if "loading qwen model" in lower_detail or "loading model" in lower_detail:
                    stage = "Loading model"
                elif "switching to cpu" in lower_detail or "compatibility mode" in lower_detail:
                    stage = "Selecting compatible backend"
                else:
                    stage = "synthesizing"
                lock = getattr(self, "_jobs_lock", None)
                jobs = getattr(self, "_jobs", None)
                if lock is None or not isinstance(jobs, dict):
                    return
                try:
                    with lock:
                        row = jobs.get(str(job_id))
                        if not row or str(row.get("state") or "").casefold() != "running":
                            return
                    self._job_update(job_id, stage=stage, message=detail_text)
                except Exception:
                    log.debug("Could not publish Qwen preview status.", exc_info=True)

            status_setter = getattr(provider, "set_status_callback", None)
            if callable(status_setter):
                status_setter(provider_status)
            elif callable(getattr(provider, "_status", None)):
                try:
                    provider.status_callback = provider_status
                except Exception:
                    pass

            folder = app_root() / "Previews"
            folder.mkdir(parents=True, exist_ok=True)
            output = folder / f"preview_{job_id}.wav"
            preview_started = time.monotonic()
            provider_setup_seconds = round(max(0.0, preview_started - request_started_at), 3)

            def progress(stage: str, current: int, total: int) -> None:
                elapsed = max(0, int(time.monotonic() - preview_started))
                clock = f"{elapsed // 60}:{elapsed % 60:02d}"
                if stage == "synthesizing":
                    detail = f"Generating segment {min(total, max(1, current + 1))}/{max(1, total)} • elapsed {clock}"
                elif stage == "finalizing":
                    detail = f"Finalizing preview • elapsed {clock}"
                else:
                    detail = f"Preparing preview • elapsed {clock}"
                self._job_update(job_id, stage=str(stage), message=detail,
                                 progress=min(95, max(2, 5 + int(90 * current / max(1, total)))))

            def report_elapsed_time() -> None:
                while not heartbeat_stop.wait(5.0):
                    if cancel_event is not None and cancel_event.is_set():
                        return
                    elapsed = max(0, int(time.monotonic() - preview_started))
                    clock = f"{elapsed // 60}:{elapsed % 60:02d}"
                    lock = getattr(self, "_jobs_lock", None)
                    jobs = getattr(self, "_jobs", None)
                    if lock is None or not isinstance(jobs, dict):
                        return
                    try:
                        with lock:
                            row = jobs.get(str(job_id))
                            if not row or str(row.get("state") or "").casefold() != "running":
                                return
                        self._job_update(
                            job_id, stage="synthesizing",
                            message=f"Synthesis is still running • elapsed {clock}",
                        )
                    except Exception:
                        return

            heartbeat_thread = threading.Thread(
                target=report_elapsed_time, name="RyuPreviewHeartbeat", daemon=True
            )
            heartbeat_thread.start()
            result = build_voice_preview(
                text_value, provider, voice, output,
                pronunciation_dictionary=(
                    [] if state.get("_bypass_pronunciation_dictionary")
                    else _effective_pronunciation_dictionary(state)
                ),
                narration_speed=float(state.get("narration_speed") or 0.90),
                pacing_profile=str(state.get("pacing_profile") or "natural"),
                max_chars=max(1400, seconds * 240), progress_callback=progress,
                target_seconds=seconds,
                cancel_check=cancel_event.is_set if cancel_event is not None else None,
                preserve_paragraph_boundaries=_preview_requires_paragraph_boundary(state),
            )
            synthesis_finished_at = time.monotonic()
            measured_paragraph_boundary = getattr(result, "first_paragraph_end_ms", None)
            state["_preview_first_paragraph_offset_ms"] = (
                int(measured_paragraph_boundary)
                if measured_paragraph_boundary is not None and int(measured_paragraph_boundary) > 0
                else None
            )
            if cancel_event is not None and cancel_event.is_set():
                raise PreviewCancelledError("Preview cancelled by user.")
            voice_preview_path = Path(result.output_path)
            preview_path = voice_preview_path
            if state.get("_include_sound_design_preview"):
                preview_path = self._render_sound_design_preview(voice_preview_path, job_id, state)
                # The mixed M4A is the playable result. The source narration WAV
                # is an intermediate owned by this job, not a second saved preview.
                if preview_path.resolve() != voice_preview_path.resolve():
                    try:
                        voice_preview_path.unlink(missing_ok=True)
                    except OSError:
                        log.warning("Could not remove the intermediate voice preview WAV: %s",
                                    voice_preview_path, exc_info=True)
            if cancel_event is not None and cancel_event.is_set():
                raise PreviewCancelledError("Preview cancelled by user.")
            duration = None
            try:
                from app.audio.assembler import _duration_ms
                duration = round(_duration_ms(preview_path) / 1000.0, 2)
            except (RuntimeError, OSError, ValueError):
                try:
                    with wave.open(str(preview_path), "rb") as wav:
                        duration = round(wav.getnframes() / max(1, wav.getframerate()), 2)
                except (wave.Error, OSError):
                    pass
            if duration is None or duration <= 0:
                raise RuntimeError(
                    "The preview audio was generated, but its duration could not be measured. "
                    "The preview is not marked ready; check the audio runtime and retry."
                )

            # Qt WebEngine builds may not include Chromium's AAC decoder. Keep
            # the validated M4A as the downloadable production asset and use a
            # job-owned PCM WAV copy for HTMLAudioElement playback.
            playback_path = preview_path
            if preview_path.suffix.casefold() == ".m4a":
                from app.audio.assembler import _run
                playback_path = folder / f"preview_playback_{job_id}.wav"
                _run([
                    "-hide_banner", "-loglevel", "error",
                    "-i", str(preview_path), "-vn",
                    "-ac", "2", "-ar", "44100",
                    "-c:a", "pcm_s16le", str(playback_path),
                ])
                if not playback_path.is_file() or playback_path.stat().st_size < 1024:
                    raise RuntimeError(
                        "The M4A preview was created, but its browser-compatible playback copy could not be prepared."
                    )
                try:
                    with wave.open(str(playback_path), "rb") as wav:
                        playback_duration = wav.getnframes() / max(1, wav.getframerate())
                    if abs(float(playback_duration) - float(duration)) > 1.5:
                        raise RuntimeError(
                            "The browser-compatible playback copy duration does not match the saved preview audio."
                        )
                except (wave.Error, OSError) as exc:
                    raise RuntimeError(
                        "The browser-compatible preview WAV is not a valid PCM audio file."
                    ) from exc

            rule_counts = getattr(result, "applied_rule_counts", {}) or {}
            replacements = sum(rule_counts.values())
            count_message = f" Pronunciation applied {replacements} replacement(s) across {len(rule_counts)} rule(s)."
            total_seconds = round(max(0.0, time.monotonic() - request_started_at), 3)
            synthesis_seconds = round(max(0.0, (synthesis_finished_at or time.monotonic()) - preview_started), 3)
            real_time_factor = round(synthesis_seconds / max(0.01, float(duration)), 3)
            performance_summary = (
                f"Preview: {float(duration):.1f}s audio in {total_seconds:.1f}s "
                f"(synthesis {synthesis_seconds:.1f}s; {real_time_factor:.2f}× real time)."
            )
            if int(seconds) == 30 and total_seconds > 60:
                performance_summary += " The 30-second/60-second performance target was exceeded; timing has been recorded for diagnosis."
            log.info(
                "Voice preview performance profile=%s provider=%s requested_s=%s actual_s=%.2f "
                "provider_setup_s=%.3f synthesis_s=%.3f total_s=%.3f realtime_factor=%.3f",
                str(getattr(profile, "name", "unknown")), str(getattr(profile, "provider", "unknown")),
                seconds, float(duration), float(provider_setup_seconds or 0.0),
                synthesis_seconds, total_seconds, real_time_factor,
            )
            self._job_update(job_id, state="completed", stage="Preview ready", progress=100,
                             message=performance_summary + count_message,
                             output_path=str(preview_path), result={
                                 "output_path": str(preview_path),
                                 "file_url": playback_path.resolve().as_uri(),
                                 "playback_output_path": str(playback_path),
                                 "playback_format": playback_path.suffix.casefold().lstrip("."),
                                 "requested_duration_seconds": seconds, "actual_duration_seconds": duration,
                                 "provider_setup_seconds": provider_setup_seconds,
                                 "synthesis_seconds": synthesis_seconds,
                                 "total_seconds": total_seconds,
                                 "real_time_factor": real_time_factor,
                                 "performance_target_met": (bool(total_seconds <= 60) if int(seconds) == 30 else None),
                                 "voices_used": list(result.voices_used), "segments": result.segments,
                                 "selected_profile": profile.name,
                                 "selected_provider": str(getattr(profile, "provider", "") or ""),
                                 "selected_voice_id": str(getattr(profile, "voice_id", "") or ""),
                                 "chapter_number": state.get("_preview_chapter_number"),
                                 "chapter_title": str(state.get("_preview_chapter_title") or ""),
                                 "pronunciation_replacements": replacements,
                                 "pronunciation_rule_counts": dict(rule_counts),
                                 "sound_configuration": dict(state.get("_preview_sound_configuration") or {}),
                             })
            preview_succeeded = True
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set() or isinstance(exc, PreviewCancelledError):
                for candidate in {output, preview_path, playback_path,
                                   app_root() / "Previews" / f"preview_playback_{job_id}.wav",
                                   app_root() / "Previews" / f"sound_mix_preview_{job_id}.m4a",
                                   app_root() / "Previews" / f"sound-preview-opening-{job_id}.m4a"}:
                    try:
                        Path(candidate).unlink(missing_ok=True)
                    except OSError:
                        pass
                self._job_update(job_id, state="cancelled", stage="Preview cancelled", progress=0,
                                 message="Preview cancelled at a safe synthesis boundary; temporary audio was discarded.")
            else:
                log.exception("Premium V2 voice preview failed")
                for candidate in {output, preview_path, playback_path,
                                   app_root() / "Previews" / f"preview_playback_{job_id}.wav",
                                   app_root() / "Previews" / f"sound_mix_preview_{job_id}.m4a",
                                   app_root() / "Previews" / f"sound-preview-opening-{job_id}.m4a"}:
                    try:
                        Path(candidate).unlink(missing_ok=True)
                    except OSError:
                        pass
                self._job_update(job_id, state="failed", stage="Preview failed", progress=0, message=str(exc),
                                 error={"code": "preview_failed", "message": str(exc)}, recoverable=True)
        finally:
            heartbeat_stop.set()
            if heartbeat_thread is not None and heartbeat_thread is not threading.current_thread():
                heartbeat_thread.join(timeout=1.0)
            if provider is not None:
                if cacheable_provider and preview_succeeded and not (cancel_event is not None and cancel_event.is_set()):
                    try:
                        self._cache_preview_provider(cache_signature, provider, voice)
                    except Exception:
                        log.warning("Could not retain a warm preview provider; closing it safely.", exc_info=True)
                        release = getattr(self, "_release_preview_provider", None)
                        if callable(release):
                            release(provider)
                        else:
                            close = getattr(provider, "close", None)
                            if callable(close): close()
                else:
                    release = getattr(self, "_release_preview_provider", None)
                    if callable(release):
                        release(provider)
                    else:
                        close = getattr(provider, "close", None)
                        if callable(close): close()
            if cancel_event is not None:
                with self._jobs_lock:
                    self._preview_cancel_events.pop(job_id, None)

    def _character_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Return a clean saved cast and remove legacy false detections on first review."""
        project = self._active_project()
        state = load_state(project.folder)
        rows = state.get("characters") or []
        if not isinstance(rows, list):
            return []
        default_series = self._project_series_name(project, state)
        assignment_names: dict[str, set[str]] = {}
        series_to_prune = {default_series} if default_series else set()
        for chapter in getattr(project, "chapters", []) or []:
            for assignment in (getattr(chapter, "dialogue_assignments", []) or []):
                if not isinstance(assignment, dict):
                    continue
                series = str(assignment.get("series") or default_series).strip()
                if not series:
                    continue
                series_to_prune.add(series)
                speakers = assignment.get("speakers")
                if not isinstance(speakers, (list, tuple)):
                    speakers = [assignment.get("speaker")] if assignment.get("speaker") else []
                assignment_names.setdefault(series.casefold(), set()).update(
                    str(value or "").strip().casefold()
                    for value in speakers if str(value or "").strip()
                )

        cleaned: list[dict[str, Any]] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            name = str(row.get("name") or row.get("primary_name") or "").strip()
            series = str(row.get("series") or "").strip()
            if not series:
                scope = str(row.get("scope") or "").strip()
                series = (
                    re.sub(r"(?i)^\s*series\s*[·:-]\s*", "", scope).strip()
                    if re.match(r"(?i)^\s*series\s*[·:-]", scope) else default_series
                )
            if series:
                series_to_prune.add(series)
            assignment_backed = name.casefold() in assignment_names.get(series.casefold(), set())
            trusted = is_user_confirmed_character_record(row) or assignment_backed
            if not name or not is_likely_character_name(name, trusted=trusted):
                continue
            aliases = row.get("aliases") or []
            if isinstance(aliases, str):
                aliases = [aliases]
            alias_trusted = trusted or bool(row.get("manual_aliases"))
            clean_aliases = list(dict.fromkeys(
                str(alias).strip()
                for alias in aliases if str(alias or "").strip()
                and str(alias).strip().casefold() != name.casefold()
                and is_likely_character_name(str(alias), trusted=alias_trusted)
            )) if isinstance(aliases, (list, tuple)) else []
            if clean_aliases != (aliases if isinstance(aliases, list) else list(aliases or [])):
                row["aliases"] = clean_aliases
            cleaned.append(row)

        if cleaned != rows:
            state["characters"] = cleaned
            state["modified_at"] = self._now()
            save_state(project.folder, state)

        # Shared Library false detections are moved into its Recovery Bin.
        for series in sorted(series_to_prune, key=str.casefold):
            try:
                prune_invalid_character_records(
                    series,
                    protected_names=assignment_names.get(series.casefold(), set()),
                )
            except Exception:
                log.exception("Could not clean legacy Character Library rows for %s", series)
        return cleaned

    def _character_dialogue_index_get(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return the persisted passage index, revision and reconciled chapter counts."""
        from app.chapters.passage_index import load_or_build_passage_index

        project = self._active_project()
        state = load_state(project.folder)
        index = load_or_build_passage_index(
            project.folder, project.chapters,
            suggested_passages=state.get("character_dialogue_suggestions") or [],
        )
        raw_number = payload.get("chapter_number")
        requested_number = None
        if raw_number not in (None, ""):
            try:
                requested_number = int(raw_number)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Choose a valid chapter number for the dialogue index.") from exc

        chapter_rows = index["chapters"]
        passage_rows = index["passages"]
        if requested_number is not None:
            chapter_rows = [
                row for row in chapter_rows
                if int(row.get("chapter_number") or 0) == requested_number
            ]
            chapter_ids = {str(row.get("chapter_id") or "") for row in chapter_rows}
            passage_rows = [
                row for row in passage_rows
                if str(row.get("chapter_id") or "") in chapter_ids
            ]
            counts = dict(chapter_rows[0]["counts"]) if chapter_rows else {
                key: 0 for key in index["counts"]
            }
        else:
            counts = dict(index["counts"])

        offset = max(0, int(payload.get("offset") or 0))
        try:
            limit = max(1, min(500, int(payload.get("limit") or 250)))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Dialogue index page size must be a positive integer.") from exc
        include_passages = payload.get("include_passages", True) is not False
        total = len(passage_rows)
        page = passage_rows[offset:offset + limit] if include_passages else []
        return {
            "schema_version": index["schema_version"],
            "source_revision": index["source_revision"],
            "assignment_revision": index["assignment_revision"],
            "index_revision": index["index_revision"],
            "counts": counts,
            "chapters": chapter_rows,
            "passages": [dict(row) for row in page],
            "offset": offset,
            "limit": limit,
            "total_passages": total,
            "has_more": bool(include_passages and offset + len(page) < total),
        }

    def _character_narration_segments_list(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Return Character Studio rows from the persisted canonical source index."""
        project = self._active_project()
        raw_number = payload.get("chapter_number")
        requested_number = None
        if raw_number not in (None, ""):
            try:
                requested_number = int(raw_number)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Choose a valid chapter number for narrator segmentation.") from exc

        if getattr(project, "folder", None) is None:
            # Unsaved Project-like test harnesses have no durable folder. They
            # retain the deterministic pure segmenter; installed projects use
            # the revision-aware index as their single source of passage truth.
            from dataclasses import asdict
            from app.chapters.speaker_segmentation import segment_chapter_speakers
            results = [
                asdict(segment)
                for chapter in project.chapters
                if requested_number is None or int(chapter.number) == requested_number
                for segment in segment_chapter_speakers(chapter)
            ]
            for chapter in project.chapters:
                if requested_number is not None and int(chapter.number) != requested_number:
                    continue
                chapter.narrator_passages = [
                    {
                        "start": row["start"], "end": row["end"], "text": row["text"],
                        "role": "Narrator", "kind": "narration",
                        "source": row["source"], "automatic": True,
                    }
                    for row in results if row.get("chapter_number") == chapter.number
                    and row.get("kind") == "narration"
                ]
            return results

        from app.chapters.passage_index import load_or_build_passage_index
        state = load_state(project.folder)
        index = load_or_build_passage_index(
            project.folder, project.chapters,
            suggested_passages=state.get("character_dialogue_suggestions") or [],
        )
        results = [
            dict(row) for row in index["passages"]
            if requested_number is None or int(row.get("chapter_number") or 0) == requested_number
        ]
        # Retain the historical in-memory narrator view for legacy callers, but
        # the persisted revision-aware index remains the sole offset authority.
        for chapter in project.chapters:
            if requested_number is not None and int(chapter.number) != requested_number:
                continue
            chapter.narrator_passages = [
                {
                    "start": row["start"], "end": row["end"], "text": row["text"],
                    "role": "Narrator", "kind": "narration",
                    "source": row["source"], "automatic": True,
                    "passage_id": row["passage_id"],
                    "chapter_revision": row["chapter_revision"],
                }
                for row in results
                if row.get("chapter_id") == chapter.chapter_id and row.get("kind") == "narration"
            ]
        return results

    def _character_analysis_status(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Return only analysis status persisted for the active project."""
        state = load_state(self._active_project().folder)
        raw = state.get("character_analysis") or {}
        if not isinstance(raw, dict):
            raw = {}
        updated_at = str(raw.get("updated_at") or "").strip()
        def as_count(value: Any) -> int:
            try:
                return max(0, int(value or 0))
            except (TypeError, ValueError, OverflowError):
                return 0
        return {
            "analyzed": bool(updated_at),
            "updated_at": updated_at or None,
            "dialogue_total": as_count(raw.get("dialogue_total")),
            "unassigned_dialogue": as_count(raw.get("unassigned_dialogue")),
            "suggestion_count": as_count(raw.get("suggestion_count")),
        }

    def _character_dialogue_suggestions_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Return source-backed AI review suggestions with canonical passage identities."""
        from app.chapters.passage_index import load_or_build_passage_index

        project = self._active_project()
        state = load_state(project.folder)
        stored = state.get("character_dialogue_suggestions") or []
        if not isinstance(stored, list):
            return []
        index = load_or_build_passage_index(
            project.folder, project.chapters, suggested_passages=stored
        )
        canonical_by_span = {
            (
                int(row.get("chapter_number") or 0),
                int(row.get("start") or 0),
                int(row.get("end") or 0),
            ): row
            for row in index["passages"]
            if isinstance(row, dict)
        }
        rows = []
        chapters_by_number = {int(chapter.number): chapter for chapter in project.chapters}
        for raw in stored:
            if not isinstance(raw, dict):
                continue
            try:
                number, start, end = int(raw.get("chapter_number")), int(raw.get("start")), int(raw.get("end"))
            except (TypeError, ValueError):
                continue
            chapter = chapters_by_number.get(number)
            if chapter is None or start < 0 or end <= start or end > len(chapter.text or ""):
                continue
            source_text = str(chapter.text or "")
            expected_text = str(raw.get("source_text") or raw.get("text") or "")
            if source_text[start:end] != expected_text:
                continue
            canonical = canonical_by_span.get((number, start, end))
            if canonical is None:
                continue
            row = dict(raw)
            row["chapter_title"] = str(chapter.title or f"Chapter {number}")
            row["text"] = source_text[start:end]
            row["source_text"] = source_text[start:end]
            row["passage_id"] = str(canonical.get("passage_id") or "")
            row["chapter_revision"] = str(canonical.get("chapter_revision") or "")
            row["source_revision"] = str(canonical.get("source_revision") or "")
            row["assignment_state"] = str(canonical.get("assignment_state") or "pending")
            row["needs_review"] = bool(canonical.get("needs_review"))
            row["assigned_speakers"] = list(canonical.get("speakers") or [])
            row["assigned"] = row["assignment_state"] == "assigned"
            row["conflict"] = row["assignment_state"] == "conflict"
            row["ai_suggestions"] = list(canonical.get("ai_suggestions") or row.get("suggestions") or [])
            assignment = next((item for item in (chapter.dialogue_assignments or [])
                               if isinstance(item, dict) and item.get("start") == start
                               and item.get("end") == end and source_text[start:end] == str(item.get("text") or "")), None)
            if assignment:
                row["assigned_speakers"] = (
                    list(assignment.get("speakers") or []) if isinstance(assignment.get("speakers"), list)
                    else ([str(assignment.get("speaker"))] if assignment.get("speaker") else [])
                )
                row["assigned"] = row["assignment_state"] == "assigned"
            skipped = state.get("character_dialogue_skips") or []
            row["skipped"] = str(row.get("id") or "") in {str(value) for value in skipped}
            rows.append(row)
        return rows

    def _character_dialogue_suggestion_skip(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        suggestion_id = str(payload.get("id") or "").strip()
        if not suggestion_id or len(suggestion_id) > 300:
            raise ValueError("Select a dialogue suggestion to skip.")
        # The analysis worker uses this same lock when it re-reads and commits the
        # newly generated suggestions. Whichever operation obtains the lock first,
        # the other will see its latest persisted state before writing.
        with self._character_review_state_lock:
            state = load_state(project.folder)
            rows = state.get("character_dialogue_suggestions") or []
            if not any(isinstance(row, dict) and str(row.get("id") or "") == suggestion_id for row in rows):
                raise ValueError("This dialogue suggestion is no longer available. Re-run analysis and try again.")
            skipped = list(dict.fromkeys(str(value) for value in (state.get("character_dialogue_skips") or []) if str(value)))
            if suggestion_id not in skipped:
                skipped.append(suggestion_id)
            state["character_dialogue_skips"] = skipped
            state["modified_at"] = self._now()
            save_state(project.folder, state)
        return {"id": suggestion_id, "skipped": True}

    def _character_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create/update a real project cast member and synchronize its reusable series record."""
        project = self._active_project()
        name = str(payload.get("name") or "").strip()
        series = str(payload.get("series") or "").strip()[:300]
        if not name:
            raise ValueError("Enter a character name.")
        if not series:
            series = self._project_series_name(project)
        if len(name) > 160:
            raise ValueError("Character names must be 160 characters or fewer.")
        aliases = payload.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [part.strip() for part in aliases.replace("\\n", ",").split(",") if part.strip()]
        if not isinstance(aliases, list):
            raise ValueError("Character aliases must be a list or comma-separated text.")
        aliases = list(dict.fromkeys(str(value).strip()[:160] for value in aliases
                                     if str(value).strip() and str(value).strip().casefold() != name.casefold()))[:5]
        profile_name = str(payload.get("voice_profile") or "").strip()
        if profile_name and self._find_profile(profile_name) is None:
            raise ValueError("Choose a voice profile from the saved Voice Studio catalogue.")
        state = load_state(project.folder)
        prior_project_series = self._project_series_name(project, state)
        if str(payload.get("series") or "").strip():
            # Keep the selected series available as the default for legacy calls;
            # every character row still stores its own explicit series identity.
            state["series_name"] = series
        characters = [dict(row) for row in (state.get("characters") or []) if isinstance(row, dict)]
        def _row_series(row: dict[str, Any]) -> str:
            existing_series = str(row.get("series") or "").strip()
            if existing_series:
                return existing_series
            scope = str(row.get("scope") or "").strip()
            if re.match(r"(?i)^series\s*[·:-]", scope):
                return re.sub(r"(?i)^series\s*[·:-]\s*", "", scope).strip()
            return prior_project_series

        matching_rows = [
            row for row in characters
            if (
                str(row.get("name") or "").casefold() == name.casefold()
                or name.casefold() in {str(alias).casefold() for alias in (row.get("aliases") or [])}
            )
            and _row_series(row).casefold() == series.casefold()
        ]
        if len(matching_rows) > 1:
            raise ValueError(
                f"More than one saved cast entry matches “{name}” in series “{series}”. "
                "Resolve the duplicate entries before assigning dialogue."
            )
        match = matching_rows[0] if matching_rows else None
        if match is None:
            match = {
                "name": name, "role": str(payload.get("role") or "Character")[:160],
                "dialogue_count": 0, "examples": [], "confidence": 1.0,
                "aliases": aliases, "voice_profile": profile_name or None,
                "series": series, "user_created": True, "manual": True, "manual_aliases": True,
                "short_description": str(payload.get("short_description") or "")[:1000],
                "notes": str(payload.get("notes") or "")[:4000], "scope": "Series · " + series,
            }
            characters.append(match)
        else:
            match.update({
                "name": name, "aliases": aliases or list(match.get("aliases") or []),
                "series": series, "scope": "Series · " + series, "user_created": True,
                "manual": True, "manual_aliases": True,
                "short_description": str(payload.get("short_description", match.get("short_description", "")) or "")[:1000],
                "notes": str(payload.get("notes", match.get("notes", "")) or "")[:4000],
            })
            if "voice_profile" in payload:
                match["voice_profile"] = profile_name or None
        # Explicitly adding this identity again from Character Studio/Library
        # is the user's restore action for a previously dismissed detection.
        restored_names = {name.casefold(), *(alias.casefold() for alias in aliases)}
        exclusions = [
            dict(row) for row in (state.get("character_detection_exclusions") or [])
            if isinstance(row, dict)
        ]
        state["character_detection_exclusions"] = [
            row for row in exclusions
            if not (
                str(row.get("series") or "").strip().casefold() == series.casefold()
                and restored_names.intersection({
                    str(value or "").strip().casefold()
                    for value in [row.get("name"), *(row.get("aliases") or [])]
                    if str(value or "").strip()
                })
            )
        ]
        state["characters"] = characters
        state["modified_at"] = self._now()
        save_state(project.folder, state)
        # The reusable library is the source of truth for cross-volume identities.
        library_payload = {
            "id": str(payload.get("library_id") or ""),
            "name": name, "series": series, "scope": "Series · " + series,
            "short": str(payload.get("short") or name.split()[0]),
            "aliases": aliases or list(match.get("aliases") or []),
            "notes": str(match.get("notes") or ""),
            "dialogue_sample": str(payload.get("dialogue_sample") or
                                   ((match.get("examples") or [""])[0] if match.get("examples") else "")),
        }
        if "voice_profile" in payload and profile_name:
            library_payload["voice_profile"] = profile_name
        saved_library = self._character_library_save(library_payload)
        # _character_library_save already wrote this character in the explicitly
        # selected series. Do not bulk-sync every cast member into the book's
        # inferred default series here.
        return {"character": match, "library_character": saved_library.get("character"),
                "saved": True, "series": series}

    def _character_analyze(self, _payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_no_active_model_lifecycle("start character analysis")
        project = self._active_project()
        if not project.chapters:
            raise ValueError("Import a book with chapters before analysing characters.")
        job_id = self._new_job("character-analysis", "Analyze story characters",
                               "Analyze saved chapters and dialogue evidence", project)
        self._analysis_cancel_events[job_id] = threading.Event()
        self._job_update(job_id, state="running", started_at=self._now(), stage="Analyzing dialogue", progress=5)
        try:
            threading.Thread(target=self._character_worker, args=(job_id, project), daemon=True).start()
        except Exception as exc:
            self._analysis_cancel_events.pop(job_id, None)
            self._job_update(job_id, state="failed", stage="Could not start analysis",
                             message=str(exc), error={"code":"character_analysis_start_failed","message":str(exc)},
                             recoverable=True)
            raise
        return {"job_id": job_id, "state": "running"}

    def _character_worker(self, job_id: str, project) -> None:
        cancel_event = self._analysis_cancel_events.get(str(job_id))
        analysis_committed = False

        def check_cancelled() -> None:
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("Character analysis cancellation requested.")

        try:
            check_cancelled()
            state = load_state(project.folder)
            # Re-analysis rebuilds recommendations, but the user’s skip decisions
            # belong to the exact source passages already reviewed. Keep the
            # previous rows and skip IDs so we can retain only still-identical items.
            previous_dialogue_suggestions = state.get("character_dialogue_suggestions") or []
            previous_dialogue_skips = state.get("character_dialogue_skips") or []
            series_name = self._project_series_name(project, state)
            saved_rows = [dict(row) for row in (state.get("characters") or []) if isinstance(row, dict)]
            library_rows = list_reusable_characters(series_name)
            raw_text = "\n\n".join(str(chapter.text or "") for chapter in project.chapters)
            from app.chapters.characters import (
                Character, _discover_explicit_speakers, is_likely_character_name,
                character_detection_exclusion_keys,
            )
            from app.chapters.character_learning import (
                load_learning_examples, prepare_learning_index, rank_speaker_suggestions,
                source_grounded_speaker_for_continuity,
            )
            explicit_names = {str(name).casefold() for name in _discover_explicit_speakers(raw_text)}
            protected_assignment_names = []
            for chapter in project.chapters:
                for assignment in (getattr(chapter, "dialogue_assignments", []) or []):
                    if not isinstance(assignment, dict):
                        continue
                    raw_speakers = assignment.get("speakers")
                    if not isinstance(raw_speakers, (list, tuple)):
                        raw_speakers = [assignment.get("speaker")] if assignment.get("speaker") else []
                    assignment_series = str(assignment.get("series") or series_name).strip()
                    protected_assignment_names.extend(
                        {"name": str(speaker or "").strip(), "series": assignment_series}
                        for speaker in raw_speakers if str(speaker or "").strip()
                    )
            excluded_detection_keys = character_detection_exclusion_keys(
                state.get("character_detection_exclusions") or [],
                series_name,
                protected_names=protected_assignment_names,
            )
            trusted_rows = []
            trusted_keys = set()
            for row in [*saved_rows, *library_rows]:
                name = str(row.get("name") or row.get("primary_name") or "").strip()
                aliases = row.get("aliases") or []
                aliases = aliases if isinstance(aliases, (list, tuple)) else []
                row_identity_names = {name.casefold(), *(
                    str(alias).strip().casefold() for alias in aliases if str(alias or "").strip()
                )}
                # A project dismissal outranks local/shared-library records. A
                # later confirmed dialogue assignment removes the exclusion above.
                if row_identity_names.intersection(excluded_detection_keys):
                    continue
                # Previously auto-detected labels are not automatically trusted.
                # A saved voice, manual creation/edit, series-level registry entry,
                # or prior confirmed dialogue assignment is user-backed evidence.
                trusted = bool(
                    row.get("user_created") or row.get("manual") or row.get("voice_profile")
                    or row.get("voice_name")
                )
                # Re-check rows already saved by earlier analysis. A voice profile
                # must not preserve an English false-positive such as "Oh" or "Any".
                if not name or not is_likely_character_name(
                    name, trusted=trusted, explicit=name.casefold() in explicit_names
                ):
                    continue
                if trusted:
                    clean_aliases = [
                        str(alias).strip() for alias in aliases
                        if str(alias or "").strip()
                        and is_likely_character_name(
                            str(alias),
                            explicit=str(alias).strip().casefold() in explicit_names,
                        )
                    ]
                    row["aliases"] = clean_aliases
                    trusted_rows.append(row)
                    trusted_keys.add(name.casefold())
                    trusted_keys.update(alias.casefold() for alias in clean_aliases)
            for chapter in project.chapters:
                for assignment in (getattr(chapter, "dialogue_assignments", []) or []):
                    if not isinstance(assignment, dict):
                        continue
                    raw_speakers = assignment.get("speakers")
                    if not isinstance(raw_speakers, (list, tuple)):
                        raw_speakers = [assignment.get("speaker")] if assignment.get("speaker") else []
                    assignment_series = str(assignment.get("series") or series_name).strip()
                    if not assignment_series or assignment_series.casefold() != series_name.casefold():
                        continue
                    for speaker in raw_speakers:
                        clean_speaker = str(speaker or "").strip()
                        if clean_speaker and is_likely_character_name(clean_speaker, trusted=True):
                            trusted_keys.add(clean_speaker.casefold())
                            trusted_rows.append({"name": clean_speaker, "aliases": [],
                                                 "series": assignment_series})

            analysis = analyze_book(project.chapters)
            ai_report: dict[str, Any] = {}
            ai_method = "source_grounded_fallback"
            ai_warnings: list[str] = []
            brain = None
            try:
                from app.ai.brain import AudiobookBrain
                initial_cast = [
                    {
                        "name": str(row.get("name") or row.get("primary_name") or "").strip(),
                        "aliases": list(row.get("aliases") or []) if isinstance(row.get("aliases") or [], (list, tuple)) else [],
                        "series": str(row.get("series") or series_name),
                    }
                    for row in trusted_rows
                    if str(row.get("name") or row.get("primary_name") or "").strip()
                ]
                brain = AudiobookBrain(Path(project.folder))

                def update_ai_progress(fraction: float, message: str) -> None:
                    # The brain reports progress between local inference passes.
                    # Raising here stops the worker at a safe model boundary.
                    check_cancelled()
                    percent = max(8, min(68, 8 + int(max(0.0, min(1.0, float(fraction))) * 60)))
                    self._job_update(
                        job_id, state="running", stage="Local AI • " + str(message or "Analyzing book"),
                        progress=percent, message=str(message or "Analyzing the complete book"),
                    )

                ai_report = brain.analyze_book(
                    project.chapters,
                    progress=update_ai_progress,
                    learning_context={"learning_scope": series_name, "characters": initial_cast},
                )
                ai_method = "local_llm"
                for chapter_report in ai_report.get("chapters", []) if isinstance(ai_report, dict) else []:
                    if not isinstance(chapter_report, dict):
                        continue
                    chapter_number = int(chapter_report.get("chapter") or 0)
                    for warning in chapter_report.get("warnings", []) or []:
                        warning_text = str(warning or "").strip()
                        if warning_text:
                            ai_warnings.append(f"Chapter {chapter_number}: {warning_text}")
                if ai_warnings:
                    ai_method = "local_llm_with_fallback_or_warnings"
            except Exception as exc:
                if cancel_event is not None and cancel_event.is_set():
                    raise InterruptedError("Character analysis cancelled during local AI inference.") from exc
                ai_warnings.append(
                    "Local AI analysis was unavailable; source-grounded fallback was used: "
                    f"{type(exc).__name__}: {exc}"
                )
                log.warning("Local Audiobook Brain unavailable for %s: %s", project.title, exc)
                ai_method = "source_grounded_fallback"
            finally:
                if brain is not None:
                    try:
                        brain.close()
                    except Exception:
                        log.exception("Could not close the Local Audiobook Brain runtime")

            ai_dialogue_by_chapter: dict[int, list[dict[str, Any]]] = {}
            ai_candidate_confidence: dict[str, float] = {}
            ai_character_aliases: dict[str, list[str]] = {}
            ai_chapter_reports = ai_report.get("chapters", []) if isinstance(ai_report, dict) else []
            for chapter_report in ai_chapter_reports:
                if not isinstance(chapter_report, dict):
                    continue
                chapter_number = int(chapter_report.get("chapter") or 0)
                ai_dialogue_by_chapter.setdefault(chapter_number, []).extend(
                    row for row in (chapter_report.get("dialogue") or []) if isinstance(row, dict)
                )
                for ai_character in chapter_report.get("characters", []) or []:
                    if not isinstance(ai_character, dict):
                        continue
                    name = str(ai_character.get("name") or "").strip()
                    key = name.casefold()
                    if not name or key in excluded_detection_keys or not is_likely_character_name(
                        name, trusted=key in trusted_keys, explicit=key in explicit_names
                    ):
                        continue
                    occurrence_count = raw_text.casefold().count(key)
                    if occurrence_count < 1:
                        continue
                    try:
                        confidence = max(0.0, min(1.0, float(ai_character.get("confidence") or 0.0)))
                    except (TypeError, ValueError, OverflowError):
                        confidence = 0.0
                    if occurrence_count < 2 and key not in trusted_keys and key not in explicit_names and confidence < 0.90:
                        continue
                    ai_candidate_confidence[key] = max(ai_candidate_confidence.get(key, 0.0), confidence)
                    aliases = ai_character.get("aliases") or []
                    if isinstance(aliases, (list, tuple)):
                        clean_aliases = [
                            str(alias).strip() for alias in aliases
                            if str(alias).strip()
                            and is_likely_character_name(
                                str(alias),
                                explicit=str(alias).strip().casefold() in explicit_names,
                            )
                            and str(alias).strip().casefold() in raw_text.casefold()
                        ]
                        ai_character_aliases[key] = list(dict.fromkeys([
                            *(ai_character_aliases.get(key) or []), *clean_aliases
                        ]))

            existing_candidates = {str(row.name).casefold(): row for row in analysis.characters}
            for key, confidence in ai_candidate_confidence.items():
                candidate = existing_candidates.get(key)
                if candidate is None:
                    ai_name = next((
                        str(item.get("name") or "").strip()
                        for chapter_report in ai_chapter_reports if isinstance(chapter_report, dict)
                        for item in (chapter_report.get("characters") or [])
                        if isinstance(item, dict) and str(item.get("name") or "").strip().casefold() == key
                    ), "")
                    if not ai_name:
                        continue
                    candidate = Character(
                        name=ai_name, role="AI Identified Character",
                        confidence=confidence, aliases=ai_character_aliases.get(key, []),
                    )
                    analysis.characters.append(candidate)
                    existing_candidates[key] = candidate
                else:
                    candidate.confidence = max(float(candidate.confidence or 0.0), confidence)
                    candidate.aliases = list(dict.fromkeys([
                        *(candidate.aliases or []), *(ai_character_aliases.get(key) or [])
                    ]))
            # Filter ordinary capitalized words out of the cast unless the text
            # supplies explicit attribution, the name is already trusted, or it
            # appears repeatedly enough in narration to be a credible identity.
            def credible_candidate(candidate) -> bool:
                name = str(getattr(candidate, "name", "") or "").strip()
                key = name.casefold()
                explicit = key in explicit_names
                trusted = key in trusted_keys
                if not name or key in excluded_detection_keys or not is_likely_character_name(name, trusted=trusted, explicit=explicit):
                    return False
                if trusted or explicit:
                    return True
                count = raw_text.casefold().count(key)
                if ai_candidate_confidence.get(key, 0.0) >= 0.90 and count >= 1:
                    return True
                return count >= (3 if len(name.split()) > 1 else 4)

            analysis.characters = [candidate for candidate in analysis.characters if credible_candidate(candidate)]
            old = {str(c.get("name", "")).casefold(): c for c in saved_rows}
            learning_examples = []
            items = []
            item_names = set()
            for c in analysis.characters:
                prior = old.get(c.name.casefold(), {})
                merged = merge_character_analysis_record(c, prior)
                if prior.get("user_created"):
                    merged["user_created"] = True
                if prior.get("manual"):
                    merged["manual"] = True
                inherited_series = str(merged.get("series") or "").strip()
                if not inherited_series:
                    scope = str(merged.get("scope") or "").strip()
                    inherited_series = (
                        re.sub(r"(?i)^\s*series\s*[·:-]\s*", "", scope).strip()
                        if re.match(r"(?i)^\s*series\s*[·:-]", scope) else ""
                    )
                merged["series"] = inherited_series or series_name
                merged["scope"] = "Series · " + merged["series"]
                items.append(merged)
                item_names.add(str(merged.get("name") or c.name).casefold())
            # Analysis refreshes must not silently discard characters the user
            # manually created or imported from the reusable Character Library.
            for old_name, prior in old.items():
                prior_name = str(prior.get("name") or old_name).strip()
                prior_trusted = is_user_confirmed_character_record(prior)
                if not is_likely_character_name(
                    prior_name, trusted=prior_trusted, explicit=prior_name.casefold() in explicit_names
                ):
                    continue
                if old_name and old_name not in item_names and (
                    old_name in trusted_keys or bool(prior.get("user_created")) or bool(prior.get("voice_profile"))
                ):
                    retained = dict(prior)
                    retained_series = str(retained.get("series") or "").strip()
                    if not retained_series:
                        retained_series = series_name
                        retained["series"] = retained_series
                    retained["scope"] = "Series · " + retained_series
                    items.append(retained)
                    item_names.add(old_name)
            # Store dialogue evidence and ranked, deterministic speaker suggestions with
            # exact source offsets. The UI may recommend a name, but never auto-assigns it.
            from app.chapters.dialogue import dialogue_segments
            suggestions = []
            known_cast = [*trusted_rows, *items]
            # Deduplicate canonical names while preserving every saved alias.
            dedup_known = {}
            for row in known_cast:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or row.get("primary_name") or "").strip()
                if not name:
                    continue
                series = str(row.get("series") or "").strip()
                if not series:
                    scope = str(row.get("scope") or "").strip()
                    series = (
                        re.sub(r"(?i)^\s*series\s*[·:-]\s*", "", scope).strip()
                        if re.match(r"(?i)^\s*series\s*[·:-]", scope) else ""
                    ) or series_name
                key = name.casefold() + "::" + series.casefold()
                current = dedup_known.get(key)
                aliases = row.get("aliases") or []
                aliases = list(aliases) if isinstance(aliases, (list, tuple)) else ([aliases] if aliases else [])
                if current is None:
                    dedup_known[key] = {**row, "name": name, "series": series, "aliases": aliases}
                else:
                    current["aliases"] = list(dict.fromkeys([*(current.get("aliases") or []), *aliases]))
            known_cast = list(dedup_known.values())
            learning_series_names = {series_name}
            learning_series_names.update(
                str(row.get("series") or "").strip()
                for row in known_cast if str(row.get("series") or "").strip()
            )
            for learning_series in sorted(learning_series_names, key=str.casefold):
                learning_examples.extend(load_learning_examples(learning_series))
            learning_index = prepare_learning_index(learning_examples)
            total_dialogue_segments = 0
            invalid_dialogue_segments = 0
            processed_chapters = 0
            total_chapters = len(project.chapters)
            for chapter_index, chapter in enumerate(project.chapters, 1):
                check_cancelled()
                self._job_update(
                    job_id, state="running", stage="Indexing dialogue passages",
                    progress=min(94, 68 + int((chapter_index - 1) / max(1, total_chapters) * 26)),
                    message=f"Mapping source-grounded dialogue in chapter {chapter_index}/{total_chapters}",
                )
                processed_chapters += 1
                last_speaker = ""
                last_speaker_series = ""
                last_speaker_end = -1
                segments = dialogue_segments(chapter)
                total_dialogue_segments += len(segments)
                saved_assignments = [
                    row for row in (getattr(chapter, "dialogue_assignments", []) or [])
                    if isinstance(row, dict)
                ]
                for segment in segments:
                    check_cancelled()
                    source = str(chapter.text or "")
                    start, end = int(segment.start), int(segment.end)
                    if start < 0 or end <= start or end > len(source):
                        invalid_dialogue_segments += 1
                        continue
                    exact = source[start:end]
                    detected = [
                        {"name": str(name), "confidence": round(float(confidence), 4), "evidence": str(evidence)}
                        for name, confidence, evidence in (segment.suggestions or [])
                        if str(name).strip()
                    ]
                    def normalize_dialogue_match(value: str) -> str:
                        # Preserve Unicode letters and digits. The old ASCII-only
                        # [0-9a-z] filter erased Japanese, Chinese, Korean and other
                        # non-Latin quotes, preventing valid local-AI speaker evidence
                        # from being matched back to its exact source passage.
                        normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
                        return "".join(character for character in normalized if character.isalnum())
                    source_key = normalize_dialogue_match(exact)
                    for ai_row in ai_dialogue_by_chapter.get(int(chapter.number), []):
                        quote_key = normalize_dialogue_match(str(ai_row.get("quote") or ""))
                        if not quote_key or len(quote_key) < 5:
                            continue
                        if quote_key not in source_key and not (len(source_key) >= 12 and source_key in quote_key):
                            continue
                        ai_speaker = str(ai_row.get("speaker") or "").strip()
                        if not ai_speaker:
                            continue
                        canonical_speaker = ""
                        for cast_row in known_cast:
                            canonical = str(cast_row.get("name") or "").strip()
                            aliases = cast_row.get("aliases") or []
                            alias_names = aliases if isinstance(aliases, (list, tuple)) else []
                            if ai_speaker.casefold() == canonical.casefold() or any(
                                ai_speaker.casefold() == str(alias).strip().casefold()
                                for alias in alias_names
                            ):
                                canonical_speaker = canonical
                                break
                        if not canonical_speaker:
                            continue
                        try:
                            ai_confidence = max(0.0, min(1.0, float(ai_row.get("confidence") or 0.0)))
                        except (TypeError, ValueError, OverflowError):
                            ai_confidence = 0.0
                        ai_evidence = str(ai_row.get("evidence") or "Book-context speaker analysis")
                        detected.append({
                            "name": canonical_speaker,
                            "confidence": round(ai_confidence, 4),
                            "evidence": "Local AI book-context analysis: " + ai_evidence,
                        })
                    # Pronoun continuity is local: never carry an old speaker anchor
                    # indefinitely through unrelated dialogue in a long chapter.
                    continuity_is_local = bool(last_speaker and 0 <= start - last_speaker_end <= 420)
                    continuity_speaker = last_speaker if continuity_is_local else ""
                    continuity_series = last_speaker_series if continuity_is_local else ""
                    candidates = rank_speaker_suggestions(
                        chapter_text=source, start=start, end=end, detected=detected,
                        known_characters=known_cast, learning_examples=learning_index,
                        last_speaker=continuity_speaker,
                        last_speaker_series=continuity_series,
                    )
                    assigned = next((row for row in saved_assignments
                        if int(row.get("start", -1)) == start and int(row.get("end", -1)) == end
                        and str(row.get("text") or exact) == exact), None)
                    assigned_speakers = (
                        list(assigned.get("speakers") or []) if assigned and isinstance(assigned.get("speakers"), list)
                        else ([str(assigned.get("speaker"))] if assigned and assigned.get("speaker") else [])
                    )
                    if assigned_speakers:
                        # Explicitly saved project assignments are the strongest
                        # continuity signal, and already persisted as user feedback.
                        last_speaker = str(assigned_speakers[0])
                        assigned_series = str(assigned.get("series") or "").strip()
                        assigned_cast = next((row for row in saved_rows if
                            str(row.get("name") or "").casefold() == last_speaker.casefold()
                            or last_speaker.casefold() in {
                                str(alias).casefold() for alias in (row.get("aliases") or [])
                            }), {})
                        last_speaker_series = assigned_series or str(assigned_cast.get("series") or series_name)
                        last_speaker_end = end
                    else:
                        # An unconfirmed model/rule guess must not become ground truth
                        # for the next line's pronouns. Only a directly observed name +
                        # speech-tag pattern may refresh this short-lived anchor.
                        source_speaker = source_grounded_speaker_for_continuity(candidates)
                        if source_speaker:
                            matching_source_candidates = [
                                row for row in candidates
                                if str(row.get("name") or "").casefold() == source_speaker.casefold()
                            ]
                            source_candidate = next((
                                row for row in matching_source_candidates
                                if str(row.get("series") or "").casefold() == series_name.casefold()
                            ), matching_source_candidates[0] if matching_source_candidates else {})
                            last_speaker = source_speaker
                            last_speaker_series = str(source_candidate.get("series") or series_name)
                            last_speaker_end = end
                    best = candidates[0] if candidates else {}
                    best_confidence = float(best.get("confidence") or 0.0)
                    suggestions.append({
                        "id": f"dialogue-{int(chapter.number)}-{start}-{end}",
                        "chapter_number": int(chapter.number), "chapter_title": str(chapter.title or ""),
                        "start": start, "end": end, "source_text": exact, "text": exact,
                        "suggested_speaker": str(best.get("name") or "") if best_confidence >= 0.78 else "",
                        "confidence": round(best_confidence, 4),
                        "suggestions": candidates, "assigned_speakers": assigned_speakers,
                        "assigned": bool(assigned_speakers),
                        "source": "local-dialogue-analysis",
                    })
            with self._character_review_state_lock:
                # Use the last persisted state, not the snapshot captured before the
                # expensive analysis. A user may have skipped a passage or changed a
                # setting while this worker was running.
                latest_state = load_state(project.folder)
                latest_dialogue_suggestions = latest_state.get("character_dialogue_suggestions")
                if not isinstance(latest_dialogue_suggestions, list):
                    latest_dialogue_suggestions = previous_dialogue_suggestions
                latest_dialogue_skips = latest_state.get("character_dialogue_skips")
                if not isinstance(latest_dialogue_skips, list):
                    latest_dialogue_skips = previous_dialogue_skips

                # Keep unrelated latest state keys intact while replacing analysis-owned
                # outputs with results calculated from the source snapshot.
                # A user may dismiss a false detection or add/confirm a cast
                # member while inference is running. Reconcile the latest persisted
                # exclusion/confirmation state before committing stale worker output.
                latest_saved_characters = [
                    dict(row) for row in (latest_state.get("characters") or [])
                    if isinstance(row, dict)
                ]
                latest_protected_names = list(protected_assignment_names)
                for row in latest_saved_characters:
                    if row.get("user_created") or row.get("manual") or row.get("voice_profile"):
                        latest_protected_names.append({
                            "name": str(row.get("name") or "").strip(),
                            "aliases": list(row.get("aliases") or []),
                            "series": str(row.get("series") or series_name).strip(),
                        })
                latest_excluded_keys = character_detection_exclusion_keys(
                    latest_state.get("character_detection_exclusions") or [],
                    series_name,
                    protected_names=latest_protected_names,
                )
                def excluded_row(row: dict[str, Any]) -> bool:
                    names = {
                        str(row.get("name") or row.get("primary_name") or "").strip().casefold(),
                        *(str(alias).strip().casefold() for alias in (row.get("aliases") or [])
                          if str(alias or "").strip()),
                    }
                    return bool(names.intersection(latest_excluded_keys))
                items = [row for row in items if not excluded_row(row)]
                item_keys = {
                    (str(row.get("name") or "").strip().casefold(),
                     str(row.get("series") or series_name).strip().casefold())
                    for row in items
                }
                for row in latest_saved_characters:
                    key = (str(row.get("name") or "").strip().casefold(),
                           str(row.get("series") or series_name).strip().casefold())
                    if (row.get("user_created") or row.get("manual") or row.get("voice_profile")) and key[0] and key not in item_keys and not excluded_row(row):
                        items.append(row)
                        item_keys.add(key)
                for suggestion in suggestions:
                    if not isinstance(suggestion, dict):
                        continue
                    candidates = [
                        candidate for candidate in (suggestion.get("suggestions") or [])
                        if isinstance(candidate, dict)
                        and str(candidate.get("name") or "").strip().casefold() not in latest_excluded_keys
                    ]
                    suggestion["suggestions"] = candidates
                    if str(suggestion.get("suggested_speaker") or "").strip().casefold() in latest_excluded_keys:
                        try:
                            best_confidence = float((candidates[0] if candidates else {}).get("confidence") or 0.0)
                        except (TypeError, ValueError, OverflowError):
                            best_confidence = 0.0
                        suggestion["suggested_speaker"] = (
                            str(candidates[0].get("name") or "") if candidates and best_confidence >= 0.78 else ""
                        )
                        suggestion["confidence"] = round(best_confidence, 4)
                latest_state["characters"] = items
                latest_state["character_dialogue_suggestions"] = suggestions
                latest_state["character_dialogue_skips"] = retain_current_dialogue_skips(
                    latest_dialogue_skips,
                    latest_dialogue_suggestions,
                    suggestions,
                )
                unresolved_count = sum(1 for row in suggestions if not row.get("assigned"))
                latest_state["character_analysis"] = {
                    "dialogue_total": total_dialogue_segments,
                    "unassigned_dialogue": unresolved_count,
                    "suggestion_count": len(suggestions),
                    "processed_chapters": processed_chapters,
                    "total_chapters": total_chapters,
                    "dialogue_segment_total": total_dialogue_segments,
                    "invalid_dialogue_segments": invalid_dialogue_segments,
                    "coverage_percent": 100 if total_chapters == processed_chapters else int(100 * processed_chapters / max(1, total_chapters)),
                    "coverage_complete": processed_chapters == total_chapters and invalid_dialogue_segments == 0 and len(suggestions) == total_dialogue_segments,
                    "truncated": False,
                    "analysis_method": ai_method,
                    "analysis_warnings": ai_warnings[:20],
                    "updated_at": self._now(),
                }
                latest_state["modified_at"] = self._now()
                check_cancelled()
                save_state(project.folder, latest_state)
                analysis_committed = True
                state = latest_state
            self._sync_saved_cast(project, items, state, update_names=False, update_voice=False)
            method_label = (
                "Local AI book-context analysis"
                if ai_method.startswith("local_llm")
                else "Source-grounded fallback; local AI runtime/model unavailable"
            )
            unresolved_count = sum(1 for row in suggestions if not row.get("assigned"))
            self._job_update(
                job_id, state="completed", stage="Analysis complete", progress=100,
                message=f"Analyzed {processed_chapters}/{total_chapters} chapters; indexed {len(suggestions)} dialogue passages • {method_label}",
                result={
                    "characters": items,
                    "dialogue_total": total_dialogue_segments,
                    "unassigned_dialogue": unresolved_count,
                    "processed_chapters": processed_chapters,
                    "total_chapters": total_chapters,
                    "coverage_complete": processed_chapters == total_chapters and invalid_dialogue_segments == 0 and len(suggestions) == total_dialogue_segments,
                    "truncated": False,
                    "analysis_method": ai_method,
                    "analysis_warnings": ai_warnings[:20],
                },
            )
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set() and not analysis_committed:
                self._job_update(
                    job_id, state="cancelled", stage="Analysis cancelled",
                    message="Character analysis was cancelled at a safe boundary. No partial cast or dialogue index was committed.",
                    result={"cancelled": True, "partial_results_committed": False},
                    recoverable=False,
                )
            else:
                log.exception("Premium V2 character analysis failed")
                self._job_update(job_id, state="failed", stage="Analysis failed", message=str(exc),
                                 error={"code": "character_analysis_failed", "message": str(exc)}, recoverable=True)
        finally:
            self._analysis_cancel_events.pop(str(job_id), None)

    def _character_assign(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        name = str(payload.get("name") or "").strip()
        profile_name = str(payload.get("profile_name") or "").strip()
        if not name:
            raise ValueError("Choose a character before assigning a voice.")
        if profile_name and self._find_profile(profile_name) is None:
            raise ValueError("Choose a voice from the saved Voice Studio catalogue.")
        state = load_state(project.folder)
        characters = list(state.get("characters") or [])
        requested_series = str(payload.get("series") or "").strip()
        matches = [
            c for c in characters
            if isinstance(c, dict)
            and str(c.get("name", "")).strip().casefold() == name.casefold()
            and (
                not requested_series
                or str(c.get("series") or self._project_series_name(project, state)).strip().casefold()
                   == requested_series.casefold()
            )
        ]
        if not matches:
            raise ValueError("That character is not in the selected series of the saved project cast. Refresh the list and try again.")
        if len(matches) > 1:
            raise ValueError("This character name exists in more than one series. Select the series before assigning a voice.")
        item = matches[0]
        item["voice_profile"] = profile_name or None
        state["characters"] = characters
        state["modified_at"] = self._now()
        save_state(project.folder, state)
        series = str(item.get("series") or self._project_series_name(project, state)).strip()
        registry_rows = list_reusable_characters()
        matched_registry = next((row for row in registry_rows
            if str(row.get("series") or "").casefold() == series.casefold()
            and (str(row.get("primary_name") or row.get("name") or "").casefold() == name.casefold()
                 or name.casefold() in {str(alias).casefold() for alias in (row.get("aliases") or [])})), None)
        self._character_library_save({
            "id": str((matched_registry or {}).get("id") or ""),
            "name": name, "series": series, "scope": "Series · " + series,
            "short": str(item.get("short_description") or name.split()[0]),
            "aliases": list(item.get("aliases") or []), "notes": str(item.get("notes") or ""),
            "dialogue_sample": str((item.get("examples") or [""])[0] if item.get("examples") else ""),
            "voice_profile": profile_name,
        })
        return {"name": name, "voice_profile": item["voice_profile"], "saved": True}

    def _character_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist edits to one character, selected by name and series identity."""
        project = self._active_project()
        original_name = str(payload.get("original_name") or payload.get("name") or "").strip()
        name = str(payload.get("name") or "").strip()
        if not original_name or not name:
            raise ValueError("A character name is required.")
        if len(name) > 160:
            raise ValueError("Character names must be 160 characters or fewer.")
        state = load_state(project.folder)
        characters = list(state.get("characters") or [])
        default_series = self._project_series_name(project, state)
        requested_original_series = str(payload.get("original_series") or "").strip()
        matches = [
            row for row in characters
            if isinstance(row, dict)
            and str(row.get("name") or "").strip().casefold() == original_name.casefold()
            and (
                not requested_original_series
                or str(row.get("series") or default_series).strip().casefold()
                   == requested_original_series.casefold()
            )
        ]
        if not matches:
            raise ValueError("The selected character is no longer in the saved cast for that series. Refresh and try again.")
        if len(matches) > 1:
            raise ValueError("This character name exists in more than one series. Select the series before editing.")
        item = matches[0]
        current_series = str(item.get("series") or default_series).strip()
        previous_identity_names = {original_name.casefold()}
        previous_identity_names.update(
            str(alias).strip().casefold()
            for alias in (item.get("aliases") or [])
            if str(alias).strip()
        )
        # An alias shared with another character in the same series is ambiguous;
        # never migrate another character's saved dialogue through that alias.
        other_series_names: set[str] = set()
        for other in characters:
            if not isinstance(other, dict) or other is item:
                continue
            other_series = str(other.get("series") or default_series).strip()
            if other_series.casefold() != current_series.casefold():
                continue
            other_series_names.add(str(other.get("name") or "").strip().casefold())
            other_series_names.update(
                str(alias).strip().casefold()
                for alias in (other.get("aliases") or [])
                if str(alias).strip()
            )
        previous_identity_names.difference_update(other_series_names)
        raw_series_value = payload.get("series") if "series" in payload else item.get("series", default_series)
        if isinstance(raw_series_value, str):
            series_value = raw_series_value.strip()[:300]
        else:
            series_value = ""
        target_series = series_value or default_series
        duplicate = next((
            row for row in characters
            if isinstance(row, dict) and row is not item
            and str(row.get("name") or "").strip().casefold() == name.casefold()
            and str(row.get("series") or default_series).strip().casefold() == target_series.casefold()
        ), None)
        if duplicate is not None:
            raise ValueError("Another character already uses that name in the selected series.")
        # Partial updates must not erase saved cast metadata merely because a
        # caller omitted a field. Explicit empty values still allow the UI to
        # clear optional fields intentionally.
        raw_profile_name = payload.get("voice_profile") if "voice_profile" in payload else item.get("voice_profile")
        profile_name = str(raw_profile_name or "").strip()
        if profile_name and self._find_profile(profile_name) is None:
            raise ValueError("Choose a voice from the saved Voice Studio catalogue.")
        aliases = payload.get("aliases")
        if aliases is None:
            aliases = list(item.get("aliases") or [])
        elif isinstance(aliases, str):
            aliases = [part.strip() for part in aliases.replace("\n", ",").split(",") if part.strip()]
        if not isinstance(aliases, list):
            raise ValueError("Character aliases must be a list or comma-separated text.")
        # A renamed character may still appear under the previous name in saved
        # dialogue assignments and older analysis evidence. Keep that name as an
        # alias so cast-aware narration routing continues to resolve the identity.
        if original_name.casefold() != name.casefold():
            aliases = [original_name, *aliases]
        aliases = list(dict.fromkeys(
            str(alias).strip()[:160]
            for alias in aliases
            if str(alias).strip() and str(alias).strip().casefold() != name.casefold()
        ))
        role_value = payload.get("role") if "role" in payload else item.get("role", "Character")
        description_value = payload.get("short_description") if "short_description" in payload else item.get("short_description", "")
        notes_value = payload.get("notes") if "notes" in payload else item.get("notes", "")
        scope_value = payload.get("scope") if "scope" in payload else item.get("scope", "Current book only")
        item.update({
            "name": name,
            "role": str(role_value or "Character").strip()[:160],
            "short_description": str(description_value or "").strip()[:1000],
            "aliases": list(dict.fromkeys(str(alias).strip()[:160] for alias in aliases if str(alias).strip())),
            "notes": str(notes_value or "").strip()[:4000],
            "scope": ("Series · " + series_value) if series_value else str(scope_value or "Current book only").strip()[:80],
            "series": series_value,
            "voice_profile": profile_name or None,
            "manual": True,
            "manual_aliases": True,
        })
        state["characters"] = characters
        state["modified_at"] = self._now()
        save_state(project.folder, state)

        # Keep every saved source span routed to the edited character when its
        # series or aliases change. Preserve source/confidence/offsets; only update
        # the series key and speaker labels that belonged uniquely to this identity.
        new_identity_names = {name.casefold(), *(str(alias).strip().casefold() for alias in aliases if str(alias).strip())}
        assignment_changes = 0
        for chapter in project.chapters:
            for assignment in list(getattr(chapter, "dialogue_assignments", []) or []):
                if not isinstance(assignment, dict):
                    continue
                assignment_series = str(assignment.get("series") or default_series).strip()
                if assignment_series.casefold() != current_series.casefold():
                    continue
                raw_speakers = assignment.get("speakers")
                if not isinstance(raw_speakers, (list, tuple)):
                    raw_speakers = [assignment.get("speaker")] if assignment.get("speaker") else []
                speaker_names = {str(value or "").strip().casefold() for value in raw_speakers if str(value or "").strip()}
                if not speaker_names.intersection(previous_identity_names):
                    continue

                def rehome_speaker(value: Any) -> Any:
                    normalized = str(value or "").strip().casefold()
                    if normalized in previous_identity_names and normalized not in new_identity_names:
                        return name
                    return value

                if isinstance(assignment.get("speakers"), (list, tuple)):
                    assignment["speakers"] = [rehome_speaker(value) for value in assignment["speakers"]]
                if assignment.get("speaker"):
                    assignment["speaker"] = rehome_speaker(assignment["speaker"])
                if current_series.casefold() != target_series.casefold() or not assignment.get("series"):
                    assignment["series"] = target_series
                assignment_changes += 1
        if assignment_changes:
            project.save()

        if series_value:
            try:
                registry_rows = list_reusable_characters()
                old_series = current_series.casefold()
                target_series_key = series_value.casefold()
                active_folder = str(Path(project.folder).resolve())
                library_row = next((row for row in registry_rows
                    if str(row.get("source_project_folder") or "") and
                       str(Path(str(row.get("source_project_folder"))).resolve()) == active_folder and
                       str(row.get("series") or current_series).casefold() in {old_series, target_series_key} and
                       str(row.get("primary_name") or row.get("name") or "").casefold() in
                       {original_name.casefold(), name.casefold()}), None)
                if library_row is None:
                    library_row = next((row for row in registry_rows
                        if str(row.get("series") or "").casefold() == target_series_key
                        and (str(row.get("primary_name") or row.get("name") or "").casefold() == name.casefold()
                             or name.casefold() in {str(alias).casefold() for alias in (row.get("aliases") or [])})), None)
                if library_row is None:
                    library_row = next((row for row in registry_rows
                        if str(row.get("series") or "").casefold() == old_series
                        and (str(row.get("primary_name") or row.get("name") or "").casefold() == original_name.casefold()
                             or original_name.casefold() in {str(alias).casefold() for alias in (row.get("aliases") or [])})), None)
                self._character_library_save({
                    "id": str((library_row or {}).get("id") or ""),
                    "name": name, "series": series_value, "scope": "Series · " + series_value,
                    "short": str(item.get("short_description") or name.split()[0]),
                    "aliases": aliases, "notes": item.get("notes") or "",
                    "dialogue_sample": (item.get("examples") or [""])[0],
                    "voice_profile": profile_name,
                })
            except Exception:
                log.exception("Could not synchronize edited series details to Character Library")
                raise
        return {"character": item, "saved": True}

    def _character_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Dismiss one unreferenced project cast row and persist its re-detection exclusion."""
        project = self._active_project()
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("Choose a character to delete.")
        review_lock = getattr(self, "_character_review_state_lock", threading.RLock())
        with review_lock:
            state = load_state(project.folder)
            characters = list(state.get("characters") or [])
            default_series = self._project_series_name(project, state)
            requested_series = str(payload.get("series") or "").strip()
            matches = [
                row for row in characters
                if isinstance(row, dict)
                and str(row.get("name") or "").strip().casefold() == name.casefold()
                and (
                    not requested_series
                    or str(row.get("series") or default_series).strip().casefold() == requested_series.casefold()
                )
            ]
            if not matches:
                raise ValueError("The selected character is no longer in the saved cast for that series.")
            if len(matches) > 1:
                raise ValueError("This character name exists in more than one series. Select the series before deleting.")
            selected = matches[0]
            selected_series = str(selected.get("series") or default_series).strip()
            if not selected_series:
                raise ValueError("The selected character has no series identity. Assign a series before dismissing it.")
            raw_aliases = selected.get("aliases") or []
            aliases = raw_aliases if isinstance(raw_aliases, (list, tuple)) else ([raw_aliases] if raw_aliases else [])
            aliases = list(dict.fromkeys(
                str(value).strip()[:160] for value in aliases
                if str(value or "").strip() and str(value).strip().casefold() != name.casefold()
            ))[:5]
            identity_names = {name.casefold(), *(value.casefold() for value in aliases)}
            # Do not leave saved dialogue spans pointing at a character that no longer exists.
            for chapter in project.chapters:
                for assignment in list(getattr(chapter, "dialogue_assignments", []) or []):
                    if not isinstance(assignment, dict):
                        continue
                    assignment_series = str(assignment.get("series") or default_series).strip()
                    if assignment_series and selected_series and assignment_series.casefold() != selected_series.casefold():
                        continue
                    raw_speakers = assignment.get("speakers")
                    if not isinstance(raw_speakers, (list, tuple)):
                        raw_speakers = [assignment.get("speaker")] if assignment.get("speaker") else []
                    speakers = {str(value or "").strip().casefold() for value in raw_speakers if str(value or "").strip()}
                    if speakers.intersection(identity_names):
                        raise ValueError(
                            f"Cannot delete/dismiss '{name}' while saved dialogue assignments still refer to this character. "
                            "Unassign or reassign those passages first."
                        )
            exclusions = [
                dict(row) for row in (state.get("character_detection_exclusions") or [])
                if isinstance(row, dict)
            ]
            existing = next((
                row for row in exclusions
                if str(row.get("name") or "").strip().casefold() == name.casefold()
                and str(row.get("series") or "").strip().casefold() == selected_series.casefold()
            ), None)
            if existing is None:
                exclusions.append({
                    "name": name,
                    "aliases": aliases,
                    "series": selected_series,
                    "reason": "user-dismissed-from-project-cast",
                    "created_at": self._now(),
                })
            else:
                existing["aliases"] = list(dict.fromkeys([
                    *(existing.get("aliases") or []), *aliases
                ]))[:5]
                existing["reason"] = "user-dismissed-from-project-cast"
                existing["created_at"] = self._now()
            state["character_detection_exclusions"] = exclusions
            state["characters"] = [row for row in characters if row is not selected]
            state["modified_at"] = self._now()
            save_state(project.folder, state)
        return {
            "name": name, "series": selected_series, "deleted": True,
            "detection_excluded": True, "remaining": len(state["characters"]),
        }

    def _character_library_path(self) -> Path:
        return reusable_character_library_path()

    @staticmethod
    def _character_library_ui_count(value: Any, default: int = 0, maximum: int | None = None) -> int:
        try:
            result = int(value if value is not None else default)
        except (TypeError, ValueError, OverflowError):
            result = default
        result = max(0, result)
        return min(result, maximum) if maximum is not None else result

    @staticmethod
    def _character_library_ui_record(record: dict[str, Any]) -> dict[str, Any]:
        """Translate the persistent registry record into the Premium V2 UI contract."""
        name = str(record.get("primary_name") or record.get("name") or "").strip()
        series = str(record.get("series") or "").strip()
        aliases = record.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = []
        voice = str(record.get("voice_name") or record.get("voice") or "").strip() or "Unassigned"
        return {
            "id": str(record.get("id") or ""),
            "name": name,
            "primary_name": name,
            "short": str(record.get("short") or (name.split()[0] if name else "?")),
            "aliases": [str(alias).strip() for alias in aliases if str(alias).strip()][:5],
            "voice": voice,
            "voice_profile": voice if voice != "Unassigned" else "",
            "scope": ("Series · " + series) if series else "Unassigned series",
            "series": series,
            "notes": str(record.get("notes") or ""),
            "dialogue_sample": str(record.get("dialogue_sample") or ""),
            "pronunciation": str(record.get("pronunciation") or ""),
            "lines": PremiumV2Bridge._character_library_ui_count(record.get("line_count", record.get("lines", 0))),
            "chapters": PremiumV2Bridge._character_library_ui_count(record.get("chapter_count", record.get("chapters", 0))),
            "confidence": PremiumV2Bridge._character_library_ui_count(record.get("confidence", 100), default=100, maximum=100),
            "source_project_folder": str(record.get("source_project_folder") or ""),
            "source_project_title": str(record.get("source_project_title") or ""),
            "updated_at": str(record.get("updated_at") or ""),
        }

    def _project_series_name(self, project, state: dict[str, Any] | None = None) -> str:
        state = state if isinstance(state, dict) else load_state(project.folder)
        for key in ("series_name", "series_title", "novel_series", "series"):
            value = str(state.get(key) or "").strip()
            value = re.sub(r"(?i)^\s*series\s*[·:-]\s*", "", value).strip()
            if value and value.casefold() not in {"global character library", "all series", "unassigned series"}:
                return value[:300]
        title = str(getattr(project, "title", "") or "").strip()
        inferred = re.sub(
            r"(?i)(?:[\s._-]*(?:vol(?:ume)?\.?\s*\d+|book\s*\d+|part\s*\d+))(?:\s*[-–—:|]\s*.*)?\s*$",
            "",
            title,
        ).strip(" \t-–—_.:|")
        return (inferred or title or "Unassigned series")[:300]

    def _narrator_series_default_store_path(self, series: str) -> Path:
        """Return an app-owned file path for one normalized series narrator preference."""
        from app.core.paths import settings_root
        normalized = str(series or "").strip()
        if not normalized or normalized.casefold() in {"unassigned series", "all series"}:
            raise ValueError("Set a series name before saving a series narrator default.")
        safe_key = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")[:80] or "series"
        digest = hashlib.sha256(normalized.casefold().encode("utf-8")).hexdigest()[:16]
        return settings_root() / "series-narrators" / f"{safe_key}-{digest}.json"

    def _narrator_series_default_read(self, project, state: dict[str, Any], series: str) -> dict[str, Any]:
        """Read a series narrator default without requiring that project to be active."""
        series = str(series or self._project_series_name(project, state)).strip()
        path = self._narrator_series_default_store_path(series)
        record: dict[str, Any] = {}
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and str(loaded.get("series") or "").casefold() == series.casefold():
                    record = loaded
            except (OSError, ValueError, json.JSONDecodeError):
                raise ValueError("The saved series narrator preference could not be read. It has not been changed.")
        stored_profile = str(state.get("voice_profile") or "").strip()
        stored_source = str(state.get("narrator_profile_source") or "").strip().casefold()
        default_profile = str(record.get("profile_name") or "").strip()

        # Explicit project overrides win. A profile snapshot saved when a project
        # inherited its series default is not an override: always resolve it from
        # the current series record so later series changes propagate safely.
        if stored_source in {"project_override", "project"}:
            project_profile = stored_profile
        elif stored_source in {"series_default", "none"}:
            project_profile = ""
        else:
            # Older projects predate narrator_profile_source. Preserve their saved
            # narrator profile as a project override rather than silently changing it.
            project_profile = stored_profile

        effective = project_profile or default_profile
        source = (
            "project_override" if project_profile
            else ("series_default" if default_profile else "none")
        )
        profile = self._find_profile(effective) if effective else None
        return {
            "series": series,
            "profile_name": default_profile or None,
            "project_profile_name": project_profile or None,
            "effective_profile_name": effective or None,
            "source": source,
            "profile_available": bool(profile) if effective else False,
            "updated_at": record.get("updated_at"),
            "saved": bool(default_profile),
        }

    def _narrator_series_default_get(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        state = load_state(project.folder)
        series = str(payload.get("series") or self._project_series_name(project, state)).strip()
        return self._narrator_series_default_read(project, state, series)

    def _narrator_series_default_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        requested_series = str(payload.get("series") or "").strip()
        if requested_series:
            series = requested_series
        else:
            project = self._active_project()
            state = load_state(project.folder)
            series = self._project_series_name(project, state)
        series = series.strip()
        profile_name = str(payload.get("profile_name") or "").strip()
        if not profile_name:
            raise ValueError("Select a saved voice profile for the series narrator default.")
        profile = self._find_profile(profile_name)
        if profile is None:
            raise ValueError("The selected series narrator profile is not in the saved voice catalogue.")
        path = self._narrator_series_default_store_path(series)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "schema_version": 1, "series": series, "profile_name": profile.name,
            "provider": profile.provider, "voice_id": profile.voice_id,
            "updated_at": self._now(),
        }
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
        return {"saved": True, "series": series, "profile_name": profile.name, "updated_at": record["updated_at"]}

    def _narrator_project_reset(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Remove the project override and restore live inheritance from its series."""
        project = self._active_project()
        state = load_state(project.folder)
        series = str(payload.get("series") or self._project_series_name(project, state)).strip()
        state.pop("voice_profile", None)
        state.pop("voice_id", None)
        state.pop("backend", None)
        state["narrator_profile_source"] = "series_default"
        resolved = self._narrator_series_default_read(project, state, series)
        state["narrator"] = str(resolved.get("effective_profile_name") or "")
        state["narrator_series_default"] = str(resolved.get("profile_name") or "")
        state["modified_at"] = self._now()
        save_state(project.folder, state)
        return {
            "saved": True,
            "reset": True,
            "series": series,
            "profile_name": resolved.get("effective_profile_name"),
            "source": resolved.get("source") or "none",
            "profile_available": bool(resolved.get("profile_available")),
        }

    def _narrator_series_default_apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Compatibility action: applying the series default now restores inheritance."""
        project = self._active_project()
        state = load_state(project.folder)
        series = str(payload.get("series") or self._project_series_name(project, state)).strip()
        saved = self._narrator_series_default_read(project, state, series)
        profile_name = str(saved.get("profile_name") or "").strip()
        if not profile_name:
            raise ValueError("This series has no saved narrator default. Save a series default first.")
        if not saved.get("profile_available"):
            raise ValueError(
                f"The series narrator profile '{profile_name}' is not currently available. "
                "Restore or install the profile before applying it to this book."
            )
        return self._narrator_project_reset({"series": series})

    def _sync_saved_cast(
        self,
        project,
        characters: list[dict[str, Any]],
        state: dict[str, Any] | None = None,
        *,
        update_names: bool = False,
        update_voice: bool = False,
        registry_path: Path | None = None,
    ) -> None:
        """Merge the real saved cast into its correct series groups in the shared registry."""
        if not isinstance(characters, list):
            return
        state = state if isinstance(state, dict) else load_state(project.folder)
        default_series = self._project_series_name(project, state)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in characters:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("primary_name") or "").strip()
            if not name:
                continue
            series = str(row.get("series") or "").strip()
            if not series:
                scope = str(row.get("scope") or "").strip()
                if re.match(r"(?i)^series\s*[·:-]", scope):
                    series = re.sub(r"(?i)^series\s*[·:-]\s*", "", scope).strip()
            series = (series or default_series or "Unassigned series")[:300]
            examples = row.get("examples") or []
            if not isinstance(examples, list):
                examples = [str(examples)] if str(examples or "").strip() else []
            chapter_rows = row.get("chapter_numbers") or row.get("chapters") or []
            chapter_count = row.get("chapter_count")
            if chapter_count is None:
                chapter_count = len(chapter_rows) if isinstance(chapter_rows, (list, tuple, set)) else 0
            normalized = {
                "name": name,
                "short": row.get("short") or row.get("short_name") or "",
                "aliases": row.get("aliases") or [],
                "voice": row.get("voice_profile") or row.get("voice_name") or row.get("voice") or "",
                "examples": examples,
                "dialogue_sample": row.get("dialogue_sample") or (examples[0] if examples else ""),
                "pronunciation": row.get("pronunciation") or "",
                "notes": row.get("notes") or "",
                "line_count": row.get("dialogue_count", row.get("line_count", row.get("lines", 0))),
                "chapter_count": chapter_count,
                "confidence": row.get("confidence", 100),
                "user_created": bool(row.get("user_created")),
                "manual": bool(row.get("manual")),
                "manual_aliases": bool(row.get("manual_aliases")),
            }
            grouped.setdefault(series, []).append(normalized)
        for series, rows in grouped.items():
            sync_reusable_characters(
                series,
                rows,
                source_project_folder=str(project.folder),
                source_project_title=str(getattr(project, "title", "") or ""),
                update_names=update_names,
                update_voice=update_voice,
                path=registry_path,
            )
        assignment_names: dict[str, set[str]] = {}
        for chapter in getattr(project, "chapters", []) or []:
            for assignment in (getattr(chapter, "dialogue_assignments", []) or []):
                if not isinstance(assignment, dict):
                    continue
                series = str(assignment.get("series") or default_series).strip()
                if not series:
                    continue
                speakers = assignment.get("speakers")
                if not isinstance(speakers, (list, tuple)):
                    speakers = [assignment.get("speaker")] if assignment.get("speaker") else []
                assignment_names.setdefault(series.casefold(), set()).update(
                    str(value or "").strip().casefold()
                    for value in speakers if str(value or "").strip()
                )
        for series in sorted({default_series, *grouped.keys()} - {""}, key=str.casefold):
            prune_invalid_character_records(
                series, path=registry_path,
                protected_names=assignment_names.get(series.casefold(), set()),
            )

    def _character_library_bootstrap(self) -> None:
        """Migrate the old flat file transactionally and import already-saved project casts."""
        if getattr(self, "_character_library_bootstrapped", False):
            return
        path = reusable_character_library_path()
        registry_path = path
        migration_path: Path | None = None
        legacy_rows: list[dict[str, Any]] = []
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    "The saved Character Library file could not be read. It was left untouched; export or back it up before repairing it."
                ) from exc
            is_legacy = isinstance(data, list) or (
                isinstance(data, dict) and "characters" in data
                and "active" not in data and "deleted" not in data
            )
            if is_legacy:
                candidates = data if isinstance(data, list) else data.get("characters", [])
                if isinstance(candidates, list):
                    legacy_rows = [dict(row) for row in candidates if isinstance(row, dict)]
                # Build the migrated registry beside the original. If a disk write
                # or merge fails, the user's original file remains intact.
                migration_path = path.with_suffix(path.suffix + ".migration")
                migration_path.unlink(missing_ok=True)
                registry_path = migration_path

        for row in legacy_rows:
            name = str(row.get("name") or row.get("primary_name") or "").strip()
            if not name:
                continue
            scope = str(row.get("scope") or "").strip()
            series = str(row.get("series") or "").strip()
            if not series and re.match(r"(?i)^series\s*[·:-]", scope):
                series = re.sub(r"(?i)^series\s*[·:-]\s*", "", scope).strip()
            if not series or series.casefold() in {"global character library", "all series"}:
                series = str(row.get("source_project_title") or "Unassigned series").strip()
            aliases = row.get("aliases") or []
            if isinstance(aliases, str):
                aliases = [part.strip() for part in aliases.replace("\n", ",").split(",") if part.strip()]
            examples = row.get("examples") or []
            sample = str(row.get("dialogue_sample") or row.get("sample") or "").strip()
            if not isinstance(examples, list):
                examples = [str(examples)] if str(examples or "").strip() else []
            if sample:
                examples = [sample, *examples]
            normalized = {
                "name": name,
                "short": row.get("short") or row.get("short_name") or "",
                "aliases": aliases,
                "voice": row.get("voice") or row.get("voice_name") or "",
                "examples": examples,
                "dialogue_sample": sample,
                "notes": row.get("notes") or "",
                "pronunciation": row.get("pronunciation") or "",
                "line_count": row.get("lines", row.get("line_count", 0)),
                "chapter_count": row.get("chapters", row.get("chapter_count", 0)),
                "confidence": row.get("confidence", 100),
            }
            sync_reusable_characters(
                series, [normalized],
                source_project_folder=str(row.get("source_project_folder") or ""),
                source_project_title=str(row.get("source_project_title") or ""),
                update_names=True, update_voice=True, path=registry_path,
            )

        # Existing projects can already have saved analysis even if the global
        # registry was never hydrated. Reuse it once on first Character Library load.
        for project in list_projects():
            try:
                state = load_state(project.folder)
                rows = state.get("characters") or []
                if isinstance(rows, list) and rows:
                    self._sync_saved_cast(project, rows, state, registry_path=registry_path)
            except (OSError, ValueError, TypeError):
                log.warning("Could not import the saved cast for %s into Character Library", project.title, exc_info=True)

        if migration_path is not None:
            if not migration_path.is_file():
                migration_path.parent.mkdir(parents=True, exist_ok=True)
                migration_path.write_text(
                    json.dumps({"version": 1, "active": [], "deleted": []}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            # Atomic same-directory replace: a partially migrated file is never
            # exposed as the live registry.
            migration_path.replace(path)
        self._character_library_bootstrapped = True

    def _character_library_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        self._character_library_bootstrap()
        return [self._character_library_ui_record(row) for row in list_reusable_characters()]

    def _character_library_deleted_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        self._character_library_bootstrap()
        return [self._character_library_ui_record(row) for row in list_reusable_deleted_characters()]

    def _character_library_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._character_library_bootstrap()
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("Enter a character name before saving it to the Character Library.")
        aliases = payload.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [part.strip() for part in aliases.replace("\n", ",").split(",") if part.strip()]
        if not isinstance(aliases, list):
            raise ValueError("Character aliases must be a list or comma-separated text.")
        aliases = list(dict.fromkeys(str(item).strip()[:160] for item in aliases if str(item).strip()))[:5]
        voice_profile = str(payload.get("voice_profile") or "").strip()
        if voice_profile and self._find_profile(voice_profile) is None:
            raise ValueError("Choose a saved voice profile before assigning it to a character.")

        series = str(payload.get("series") or "").strip()
        scope = str(payload.get("scope") or "").strip()
        if not series and re.match(r"(?i)^series\s*[·:-]", scope):
            series = re.sub(r"(?i)^series\s*[·:-]\s*", "", scope).strip()
        if not series and scope.casefold() not in {"global character library", "all series"}:
            series = scope
        if not series or series.casefold() in {"global character library", "all series"}:
            active_folder = str(self.settings.value("project/active_folder") or "").strip()
            active_project = next(
                (project for project in list_projects()
                 if active_folder and str(Path(project.folder).resolve()) == str(Path(active_folder).resolve())),
                None,
            )
            if active_project:
                series = self._project_series_name(active_project, load_state(active_project.folder))
            else:
                series = "Unassigned series"
        series = series[:300]

        sample = str(payload.get("dialogue_sample") or "").strip()[:4000]
        notes = str(payload.get("notes") or "").strip()[:4000]
        existing = next(
            (row for row in list_reusable_characters()
             if str(row.get("id") or "") == str(payload.get("id") or "").strip()),
            None,
        )
        if existing:
            changes = {
                "series": series,
                "primary_name": name[:300],
                "short": str(payload.get("short") or "").strip(),
                "aliases": aliases,
                "dialogue_sample": sample,
                "notes": notes,
            }
            if "voice_profile" in payload:
                changes["voice_name"] = voice_profile
            record = update_reusable_character(existing["id"], changes)
        else:
            active_folder = str(self.settings.value("project/active_folder") or "").strip()
            active_project = next(
                (project for project in list_projects()
                 if active_folder and str(Path(project.folder).resolve()) == str(Path(active_folder).resolve())),
                None,
            )
            sync_reusable_characters(
                series,
                [{
                    "name": name[:300],
                    "short": str(payload.get("short") or "").strip(),
                    "aliases": aliases,
                    "dialogue_sample": sample,
                    "examples": [sample] if sample else [],
                    "notes": notes,
                    "confidence": 100,
                    "voice": voice_profile,
                    "user_created": True,
                    "manual": True,
                    "manual_aliases": True,
                }],
                source_project_folder=str(active_project.folder) if active_project else "",
                source_project_title=str(active_project.title) if active_project else "",
                update_names=True,
                update_voice=bool(voice_profile),
            )
            record = next(
                (row for row in list_reusable_characters()
                 if str(row.get("series") or "").casefold() == series.casefold()
                 and (
                     str(row.get("primary_name") or "").casefold() == name.casefold()
                     or name.casefold() in {str(alias).casefold() for alias in (row.get("aliases") or [])}
                 )),
                None,
            )
            if record is None:
                raise RuntimeError("The character could not be saved to the reusable registry.")
        project_updated = False
        if "voice_profile" in payload and voice_profile:
            active_folder = str(self.settings.value("project/active_folder") or "").strip()
            active_project = next(
                (project for project in list_projects()
                 if active_folder and str(Path(project.folder).resolve()) == str(Path(active_folder).resolve())),
                None,
            )
            if active_project is not None:
                state = load_state(active_project.folder)
                cast = state.get("characters") or []
                if isinstance(cast, list):
                    primary_key = str(record.get("primary_name") or name).casefold()
                    aliases_key = {str(value).casefold() for value in (record.get("aliases") or [])}
                    active_series = self._project_series_name(active_project, state)
                    record_series = str(record.get("series") or "").strip()
                    # A same-named character from another series must never inherit
                    # this profile by accident. Resolve project targets by series too.
                    target = next((item for item in cast if isinstance(item, dict) and (
                        str(item.get("name") or "").casefold() == primary_key
                        or str(item.get("name") or "").casefold() in aliases_key
                    ) and (
                        str(item.get("series") or "").casefold() == record_series.casefold()
                        or (not str(item.get("series") or "").strip()
                            and active_series.casefold() == record_series.casefold())
                    )), None)
                    # A primary character newly created from Voice Studio should also
                    # appear in Character Studio when its series is the active book's
                    # series. Do not insert characters from unrelated series into this cast.
                    if target is None and record_series and active_series.casefold() == record_series.casefold():
                        target = {
                            "name": str(record.get("primary_name") or name).strip(),
                            "role": "Character",
                            "short_description": str(record.get("short") or "").strip(),
                            "aliases": list(record.get("aliases") or []),
                            "voice_profile": voice_profile,
                            "notes": str(record.get("notes") or "").strip(),
                        }
                        cast.append(target)
                    if target is not None:
                        target["voice_profile"] = voice_profile
                        state["characters"] = cast
                        state["modified_at"] = self._now()
                        save_state(active_project.folder, state)
                        self._sync_saved_cast(active_project, cast, state, update_names=False, update_voice=True)
                        project_updated = True
                        record = next(
                            (item for item in list_reusable_characters()
                             if str(item.get("id") or "") == str(record.get("id") or "")),
                            record,
                        )
        self._character_library_bootstrapped = True
        public = self._character_library_ui_record(record)
        return {"character": public, "count": len(list_reusable_characters()), "saved": True,
                "project_updated": project_updated}

    def _character_library_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._character_library_bootstrap()
        row_id = str(payload.get("id") or "").strip()
        if not row_id:
            name = str(payload.get("name") or "").strip().casefold()
            record = next((row for row in list_reusable_characters()
                           if str(row.get("primary_name") or "").casefold() == name), None)
            row_id = str(record.get("id") or "") if record else ""
        if not row_id:
            raise ValueError("Choose a character from the reusable Character Library.")
        record = soft_delete_reusable_character(row_id)
        return {"deleted": 1, "count": len(list_reusable_characters()), "character": self._character_library_ui_record(record)}

    def _character_library_restore(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._character_library_bootstrap()
        row_id = str(payload.get("id") or "").strip()
        if not row_id:
            raise ValueError("Choose a deleted character to restore.")
        record = restore_reusable_character(row_id)
        return {"restored": True, "character": self._character_library_ui_record(record),
                "count": len(list_reusable_characters())}

    def _character_library_import(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._character_library_bootstrap()
        incoming = payload.get("characters")
        if isinstance(incoming, dict):
            incoming = incoming.get("characters")
        if not isinstance(incoming, list) or not incoming:
            raise ValueError("Choose a JSON file containing a non-empty character list.")
        imported = 0
        for candidate in incoming:
            if not isinstance(candidate, dict):
                continue
            name = str(candidate.get("name") or candidate.get("primary_name") or "").strip()
            if not name:
                continue
            scope = str(candidate.get("scope") or "").strip()
            series = str(candidate.get("series") or "").strip()
            if not series and re.match(r"(?i)^series\s*[·:-]", scope):
                series = re.sub(r"(?i)^series\s*[·:-]\s*", "", scope).strip()
            if not series or series.casefold() in {"global character library", "all series"}:
                series = str(candidate.get("source_project_title") or "Imported cast").strip()
            aliases = candidate.get("aliases") or []
            if isinstance(aliases, str):
                aliases = [part.strip() for part in aliases.replace("\n", ",").split(",") if part.strip()]
            examples = candidate.get("examples") or []
            sample = str(candidate.get("dialogue_sample") or candidate.get("sample") or "").strip()
            if sample:
                examples = [sample, *(examples if isinstance(examples, list) else [])]
            sync_reusable_characters(
                series,
                [{
                    "name": name,
                    "short": candidate.get("short") or candidate.get("short_name") or "",
                    "aliases": aliases if isinstance(aliases, list) else [],
                    "voice": candidate.get("voice") or candidate.get("voice_name") or "",
                    "dialogue_sample": sample,
                    "examples": examples if isinstance(examples, list) else [],
                    "notes": candidate.get("notes") or "",
                    "pronunciation": candidate.get("pronunciation") or "",
                    "line_count": candidate.get("line_count", candidate.get("lines", 0)),
                    "chapter_count": candidate.get("chapter_count", candidate.get("chapters", 0)),
                    "confidence": candidate.get("confidence", 100),
                }],
                source_project_folder=str(candidate.get("source_project_folder") or ""),
                source_project_title=str(candidate.get("source_project_title") or ""),
                update_names=True,
                update_voice=True,
            )
            imported += 1
        if not imported:
            raise ValueError("The selected JSON file contained no valid named characters.")
        return {"imported": imported, "count": len(list_reusable_characters()), "merged_by_name_and_series": True}

    def _pronunciation_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        """List only this book, its matching series and the shared global library."""
        project = self._active_project()
        state = load_state(project.folder)
        entries = _clean_pronunciation_entries(
            state.get("pronunciation_dictionary") if isinstance(state.get("pronunciation_dictionary"), list) else [],
            "current_book",
        )
        series_name = str(state.get("series") or state.get("series_name") or "").strip()
        if series_name:
            entries.extend(_clean_pronunciation_entries(
                _read_pronunciation_store(_pronunciation_scope_path("series", series_name)),
                "series", series_name,
            ))
        entries.extend(_clean_pronunciation_entries(
            _read_pronunciation_store(_pronunciation_scope_path("global_library")),
            "global_library",
        ))
        return entries

    def _pronunciation_export(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Export the visible book/series/global dictionary without flattening scope."""
        project = self._active_project()
        state = load_state(project.folder)
        entries = PremiumV2Bridge._pronunciation_list(self, {})
        return {
            "schema": "ryu.pronunciation-dictionary",
            "version": 1,
            "exported_at": self._now(),
            "project_title": str(getattr(project, "title", "") or ""),
            "series_name": str(state.get("series") or state.get("series_name") or "").strip(),
            "entries": entries,
        }

    def _pronunciation_import(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate a versioned dictionary, preview conflicts, then apply only on explicit confirmation."""
        payload = payload if isinstance(payload, dict) else {}
        document = payload.get("document")
        if not isinstance(document, dict):
            raise ValueError("Choose a valid versioned pronunciation dictionary JSON file.")
        if document.get("schema") != "ryu.pronunciation-dictionary" or document.get("version") != 1:
            raise ValueError("Unsupported pronunciation dictionary schema or version.")
        raw_entries = document.get("entries")
        if not isinstance(raw_entries, list):
            raise ValueError("The pronunciation dictionary must contain an entries array.")
        if len(raw_entries) > 5000:
            raise ValueError("A pronunciation dictionary import is limited to 5,000 entries.")

        project = self._active_project()
        state = load_state(project.folder)
        active_series = str(state.get("series") or state.get("series_name") or "").strip()
        normalized: list[dict[str, Any]] = []
        imported_identities: dict[tuple[str, str, str], dict[str, Any]] = {}
        for index, raw in enumerate(raw_entries):
            if not isinstance(raw, dict):
                raise ValueError(f"Pronunciation entry {index + 1} must be an object.")
            written = _normalize_pronunciation_text(
                raw.get("written_form") or raw.get("written") or raw.get("word"),
                "Written term", 500,
            )
            spoken = _normalize_pronunciation_text(
                raw.get("spoken_form") or raw.get("spoken") or raw.get("pronunciation"),
                "Pronunciation", 1000,
            )
            scope_value = raw.get("scope_type") or raw.get("scope") or "current_book"
            scope_type, scope_id, scope_label = _parse_pronunciation_scope(scope_value, raw.get("scope_id"))
            if scope_type == "series" and (
                not active_series or scope_id.casefold() != active_series.casefold()
            ):
                raise ValueError(
                    f"Entry '{written}' belongs to Series · {scope_id}, not the active project series. "
                    "Open that series project before importing its entries."
                )
            origin = str(raw.get("origin") or "manual").strip().casefold()
            if origin not in {"manual", "ai"}:
                raise ValueError(f"Entry '{written}' has an unsupported origin.")
            enabled = raw.get("enabled", True)
            if not isinstance(enabled, bool):
                raise ValueError(f"Entry '{written}' enabled value must be true or false.")
            language = _normalize_pronunciation_text(raw.get("language") or "Auto-detect", "Language", 100)
            handling_mode = _normalize_pronunciation_text(
                raw.get("handling_mode") or "automatic", "Handling mode", 100
            )
            row: dict[str, Any] = {
                "written_form": written,
                "spoken_form": spoken,
                "language": language,
                "handling_mode": handling_mode,
                "scope": scope_label,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "origin": origin,
                "enabled": enabled,
            }
            for field, limit in (("ipa", 200), ("script", 80), ("reason", 500)):
                value = str(raw.get(field) or "").strip()
                if value:
                    row[field] = value[:limit]
            if raw.get("confidence") is not None:
                try:
                    confidence = float(raw.get("confidence"))
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError(f"Entry '{written}' has invalid confidence.") from exc
                if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                    raise ValueError(f"Entry '{written}' confidence must be from 0 to 1.")
                row["confidence"] = confidence
            alternatives = raw.get("alternatives", [])
            if not isinstance(alternatives, list):
                raise ValueError(f"Entry '{written}' alternatives must be an array.")
            row["alternatives"] = [
                str(value).strip()[:300] for value in alternatives[:5] if str(value or "").strip()
            ]
            identity = (scope_type, scope_id.casefold(), unicodedata.normalize("NFC", written).casefold())
            prior_import = imported_identities.get(identity)
            if prior_import and prior_import["spoken_form"].casefold() != spoken.casefold():
                raise ValueError(
                    f"The import file contains conflicting readings for '{written}' in {scope_label}."
                )
            imported_identities[identity] = row
            if not prior_import:
                normalized.append(row)

        saved = PremiumV2Bridge._pronunciation_list(self, {})
        saved_by_identity = {
            (
                str(row.get("scope_type") or "current_book"),
                str(row.get("scope_id") or "").casefold(),
                unicodedata.normalize("NFC", str(row.get("written_form") or "")).casefold(),
            ): row
            for row in saved if isinstance(row, dict)
        }
        conflicts: list[dict[str, Any]] = []
        duplicates = 0
        new_count = 0
        for row in normalized:
            identity = (row["scope_type"], row["scope_id"].casefold(), row["written_form"].casefold())
            existing = saved_by_identity.get(identity)
            if not existing:
                new_count += 1
                continue
            if str(existing.get("spoken_form") or "").casefold() == row["spoken_form"].casefold():
                duplicates += 1
                continue
            conflicts.append({
                "written_form": row["written_form"],
                "scope": row["scope"],
                "existing_spoken_form": existing.get("spoken_form"),
                "imported_spoken_form": row["spoken_form"],
                "existing_origin": existing.get("origin", "manual"),
                "imported_origin": row["origin"],
                "protected_manual": existing.get("origin") == "manual" and row["origin"] == "ai",
            })

        replace_conflicts = payload.get("replace_conflicts") is True
        apply_changes = payload.get("apply") is True
        protected = [row for row in conflicts if row["protected_manual"]]
        preview = {
            "schema": "ryu.pronunciation-dictionary",
            "preview": not apply_changes,
            "total_entries": len(raw_entries),
            "unique_entries": len(normalized),
            "new_count": new_count,
            "duplicate_count": duplicates,
            "conflict_count": len(conflicts),
            "protected_manual_count": len(protected),
            "conflicts": conflicts,
            "imported": 0,
        }
        if not apply_changes:
            return preview
        if conflicts and not replace_conflicts:
            raise ValueError("Import conflicts require an explicit replace confirmation.")
        if protected:
            raise ValueError(
                "An imported AI pronunciation cannot overwrite a saved manual pronunciation. "
                "Resolve that entry manually in the active scope."
            )

        imported = 0
        updated = 0
        for row in normalized:
            identity = (row["scope_type"], row["scope_id"].casefold(), row["written_form"].casefold())
            existing = saved_by_identity.get(identity)
            if existing and str(existing.get("spoken_form") or "").casefold() == row["spoken_form"].casefold():
                continue
            result = PremiumV2Bridge._pronunciation_save(self, {
                **row,
                "scope": row["scope"],
                "scope_id": row["scope_id"],
                "origin": row["origin"],
                "enabled": row["enabled"],
                **({"original_written_form": row["written_form"],
                    "original_scope": row["scope"],
                    "original_scope_id": row["scope_id"]} if existing else {}),
            })
            if existing or result.get("updated_existing"):
                updated += 1
            else:
                imported += 1
        return {
            **preview,
            "preview": False,
            "imported": imported,
            "updated": updated,
            "conflicts_replaced": len(conflicts),
        }

    def _pronunciation_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Add or edit a rule in one scope while retaining its manual/AI provenance."""
        project = self._active_project()
        word = _normalize_pronunciation_text(payload.get("written_form", payload.get("word", "")), "Written term", 500)
        spoken = _normalize_pronunciation_text(payload.get("spoken_form", payload.get("pronunciation", "")), "Pronunciation", 1000)
        scope_type, scope_id, scope_label = _parse_pronunciation_scope(
            payload.get("scope") or "current_book", payload.get("scope_id")
        )
        language = _normalize_pronunciation_text(payload.get("language") or "Auto", "Language", 100)
        handling_mode = _normalize_pronunciation_text(
            payload.get("handling_mode") or payload.get("mode") or "automatic", "Handling mode", 100
        )
        original_word = str(payload.get("original_written_form") or "").strip()
        original_key = ""
        if original_word:
            original_word = _normalize_pronunciation_text(original_word, "Original written term", 500)
            original_scope_type, original_scope_id, _ = _parse_pronunciation_scope(
                payload.get("original_scope") or payload.get("scope") or "current_book",
                payload.get("original_scope_id") if payload.get("original_scope_id") is not None else payload.get("scope_id"),
            )
            if (original_scope_type, original_scope_id) != (scope_type, scope_id):
                raise ValueError("Edit the pronunciation entry in its existing scope. Create a new entry to move it to another scope.")
            original_key = original_word.casefold()

        if scope_type == "current_book":
            state = load_state(project.folder)
            raw_entries = state.get("pronunciation_dictionary")
            raw_entries = raw_entries if isinstance(raw_entries, list) else []
        else:
            path = _pronunciation_scope_path(scope_type, scope_id)
            raw_entries = _read_pronunciation_store(path)

        entries = _clean_pronunciation_entries(raw_entries, scope_type, scope_id)
        key = word.casefold()
        new_matches = [row for row in entries if row["written_form"].casefold() == key]
        original_matches = [row for row in entries if original_key and row["written_form"].casefold() == original_key]
        if original_word and not original_matches:
            raise ValueError("The original pronunciation entry no longer exists. Refresh the dictionary before editing.")
        old_match = original_matches[0] if original_matches else (new_matches[0] if new_matches else None)
        previous_spoken = old_match.get("spoken_form") if old_match else None
        requested_origin = str(payload.get("origin") or "").strip().casefold()
        if old_match and old_match.get("origin") == "manual" and requested_origin == "ai":
            raise ValueError(
                "A manual pronunciation entry already exists in this scope. Refresh the dictionary and edit that entry manually; an AI suggestion cannot overwrite or reclassify it."
            )
        origin = str(payload.get("origin") or (old_match or {}).get("origin") or "manual").strip().casefold()
        if origin not in {"manual", "ai"}:
            raise ValueError("Pronunciation entry origin must be manual or ai.")
        enabled_default = (old_match or {}).get("enabled", True)
        enabled = payload.get("enabled", enabled_default)
        if not isinstance(enabled, bool):
            raise ValueError("Enabled must be a boolean.")

        identity_keys = {key}
        if original_key:
            identity_keys.add(original_key)
        raw_match_count = sum(
            1 for row in raw_entries if isinstance(row, dict) and
            unicodedata.normalize("NFC", str(row.get("written_form") or row.get("written") or row.get("word") or ""))
            .strip().casefold() in identity_keys
        )
        value = {
            "written_form": word,
            "spoken_form": spoken,
            "language": language,
            "handling_mode": handling_mode,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "scope": scope_label,
            "enabled": enabled,
            "origin": origin,
            "updated_at": self._now(),
        }
        # AI review evidence remains attached to the saved row so a user can
        # distinguish a reviewed suggestion from a manual pronunciation later.
        for field, limit in (("ipa", 200), ("script", 80), ("reason", 500)):
            if field in payload:
                candidate = str(payload.get(field) or "").strip()
                if candidate:
                    value[field] = candidate[:limit]
            elif old_match and old_match.get(field):
                value[field] = str(old_match[field])[:limit]
        if "confidence" in payload:
            try:
                confidence = float(payload.get("confidence"))
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Pronunciation confidence must be a number from 0 to 1.") from exc
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("Pronunciation confidence must be a number from 0 to 1.")
            value["confidence"] = confidence
        elif old_match and old_match.get("confidence") is not None:
            value["confidence"] = old_match["confidence"]
        if "alternatives" in payload:
            alternatives = payload.get("alternatives")
            if not isinstance(alternatives, list):
                raise ValueError("Pronunciation alternatives must be a list.")
            value["alternatives"] = [
                str(item).strip()[:300] for item in alternatives[:5] if str(item or "").strip()
            ]
        elif old_match and isinstance(old_match.get("alternatives"), list):
            value["alternatives"] = list(old_match["alternatives"][:5])
        # Editing a written term is an upsert, not a second row. Remove both the
        # old identity and any existing destination duplicate in this same scope.
        entries = [row for row in entries if row["written_form"].casefold() not in {key, original_key}]
        entries.append(value)
        if scope_type == "current_book":
            state["pronunciation_dictionary"] = entries
            save_state(project.folder, state)
        else:
            _write_pronunciation_store(_pronunciation_scope_path(scope_type, scope_id), entries)
        return {
            "entry": value,
            "count": len(entries),
            "saved": True,
            "updated_existing": bool(old_match or new_matches),
            "conflict_resolved": bool(old_match and previous_spoken != spoken),
            "duplicate_rows_collapsed": max(0, raw_match_count - 1),
        }

    def _pronunciation_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        word = _normalize_pronunciation_text(payload.get("written_form", payload.get("word", "")), "Written term", 500)
        scope_type, scope_id, _scope_label = _parse_pronunciation_scope(
            payload.get("scope") or "current_book", payload.get("scope_id")
        )
        if scope_type == "current_book":
            state = load_state(project.folder)
            raw_entries = state.get("pronunciation_dictionary")
            entries = _clean_pronunciation_entries(raw_entries if isinstance(raw_entries, list) else [], "current_book")
        else:
            entries = _clean_pronunciation_entries(
                _read_pronunciation_store(_pronunciation_scope_path(scope_type, scope_id)), scope_type, scope_id
            )
        key = word.casefold()
        kept = [row for row in entries if row["written_form"].casefold() != key]
        deleted = len(entries) - len(kept)
        if scope_type == "current_book":
            state["pronunciation_dictionary"] = kept
            save_state(project.folder, state)
        elif deleted:
            _write_pronunciation_store(_pronunciation_scope_path(scope_type, scope_id), kept)
        return {"count": len(kept), "deleted": deleted, "scope_type": scope_type, "scope_id": scope_id}

    def _pronunciation_delete_many(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Delete only the explicitly selected written-term/scope identities."""
        selected = payload.get("entries")
        if not isinstance(selected, list) or not selected:
            raise ValueError("Select at least one pronunciation entry to delete.")
        if len(selected) > 1000:
            raise ValueError("A single bulk delete is limited to 1,000 pronunciation entries.")
        grouped: dict[tuple[str, str], set[str]] = {}
        for item in selected:
            if not isinstance(item, dict):
                raise ValueError("A selected pronunciation entry is invalid.")
            word = _normalize_pronunciation_text(item.get("written_form"), "Written term", 500)
            scope_type, scope_id, _label = _parse_pronunciation_scope(
                item.get("scope") or item.get("scope_type") or "current_book",
                item.get("scope_id"),
            )
            grouped.setdefault((scope_type, scope_id), set()).add(word.casefold())

        project = self._active_project()
        deleted_total = 0
        for (scope_type, scope_id), keys in grouped.items():
            if scope_type == "current_book":
                state = load_state(project.folder)
                raw_entries = state.get("pronunciation_dictionary")
                raw_entries = raw_entries if isinstance(raw_entries, list) else []
                entries = _clean_pronunciation_entries(raw_entries, "current_book")
            else:
                path = _pronunciation_scope_path(scope_type, scope_id)
                entries = _clean_pronunciation_entries(
                    _read_pronunciation_store(path), scope_type, scope_id
                )
            kept = [row for row in entries if row["written_form"].casefold() not in keys]
            deleted_total += len(entries) - len(kept)
            if len(kept) == len(entries):
                continue
            if scope_type == "current_book":
                state["pronunciation_dictionary"] = kept
                save_state(project.folder, state)
            else:
                _write_pronunciation_store(_pronunciation_scope_path(scope_type, scope_id), kept)
        return {"deleted": deleted_total, "scopes_processed": len(grouped)}

    def _pronunciation_settings_get(self, _payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        state = load_state(project.folder)
        return {
            "enabled": state.get("pronunciation_enabled", True) is not False,
            "series_name": str(state.get("series") or state.get("series_name") or "").strip(),
        }

    def _pronunciation_settings_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("Global pronunciation setting must be a boolean.")
        project = self._active_project()
        state = load_state(project.folder)
        state["pronunciation_enabled"] = enabled
        save_state(project.folder, state)
        return {"saved": True, "enabled": enabled}

    def _pronunciation_test_results_get(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return persisted per-profile pronunciation test outcomes for one scoped entry."""
        payload = payload if isinstance(payload, dict) else {}
        written = _normalize_pronunciation_text(payload.get("written_form"), "Written term", 500)
        scope_type, scope_id, _ = _parse_pronunciation_scope(
            payload.get("scope") or payload.get("scope_type") or "current_book",
            payload.get("scope_id"),
        )
        state = load_state(self._active_project().folder)
        stored = state.get("pronunciation_test_results")
        rows = stored if isinstance(stored, list) else []
        key = unicodedata.normalize("NFC", written).casefold()
        results = [
            dict(row) for row in rows if isinstance(row, dict)
            and str(row.get("scope_type") or "current_book") == scope_type
            and str(row.get("scope_id") or "").casefold() == scope_id.casefold()
            and unicodedata.normalize("NFC", str(row.get("written_form") or "")).casefold() == key
        ]
        results.sort(key=lambda row: str(row.get("tested_at") or ""), reverse=True)
        return {"written_form": written, "scope_type": scope_type, "scope_id": scope_id, "results": results}

    def _pronunciation_test_results_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist each saved-profile preview outcome without persisting ephemeral audio URLs."""
        payload = payload if isinstance(payload, dict) else {}
        written = _normalize_pronunciation_text(payload.get("written_form"), "Written term", 500)
        scope_type, scope_id, scope_label = _parse_pronunciation_scope(
            payload.get("scope") or payload.get("scope_type") or "current_book",
            payload.get("scope_id"),
        )
        incoming = payload.get("results")
        if not isinstance(incoming, list) or not incoming or len(incoming) > 50:
            raise ValueError("Provide between 1 and 50 saved-profile test results.")
        state = load_state(self._active_project().folder)
        stored_value = state.get("pronunciation_test_results")
        stored = [dict(row) for row in stored_value if isinstance(row, dict)] if isinstance(stored_value, list) else []
        saved = 0
        key = unicodedata.normalize("NFC", written).casefold()
        for raw in incoming:
            if not isinstance(raw, dict):
                raise ValueError("Each saved-profile test result must be an object.")
            profile_name = _normalize_pronunciation_text(raw.get("profile_name"), "Profile name", 120)
            provider = str(raw.get("provider") or "unknown").strip()[:80] or "unknown"
            status = str(raw.get("status") or "").strip().casefold()
            if status not in {"passed", "failed"}:
                raise ValueError("Profile test status must be passed or failed.")
            row: dict[str, Any] = {
                "test_id": str(uuid.uuid4()),
                "written_form": written,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "scope": scope_label,
                "profile_name": profile_name,
                "provider": provider,
                "status": status,
                "tested_at": self._now(),
            }
            for field in ("actual_duration_seconds", "synthesis_seconds", "total_seconds", "real_time_factor"):
                if raw.get(field) in (None, ""):
                    continue
                try:
                    number = float(raw.get(field))
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError(f"Profile test {field.replace('_', ' ')} must be a non-negative number.") from exc
                if not math.isfinite(number) or number < 0:
                    raise ValueError(f"Profile test {field.replace('_', ' ')} must be a non-negative number.")
                row[field] = round(number, 4)
            if status == "passed" and float(row.get("actual_duration_seconds") or 0) <= 0:
                raise ValueError("A passed profile test must include its measured audio duration.")
            try:
                replacements = int(raw.get("pronunciation_replacements") or 0)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Pronunciation replacement count must be a non-negative integer.") from exc
            if replacements < 0:
                raise ValueError("Pronunciation replacement count must be a non-negative integer.")
            row["pronunciation_replacements"] = replacements
            if raw.get("error"):
                row["error"] = str(raw.get("error"))[:800]
            identity = (scope_type, scope_id.casefold(), key, profile_name.casefold())
            prior = next((
                index for index, existing in enumerate(stored)
                if (
                    str(existing.get("scope_type") or "current_book"),
                    str(existing.get("scope_id") or "").casefold(),
                    unicodedata.normalize("NFC", str(existing.get("written_form") or "")).casefold(),
                    str(existing.get("profile_name") or "").casefold(),
                ) == identity
            ), None)
            if prior is None:
                stored.append(row)
            else:
                stored[prior] = row
            saved += 1
        state["pronunciation_test_results"] = stored[-2000:]
        save_state(self._active_project().folder, state)
        return {"saved": saved, "total_results": len(state["pronunciation_test_results"])}

    def _pronunciation_analyze(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Start the existing local audiobook-AI pronunciation analysis for saved chapters."""
        project = self._active_project()
        project_folder = getattr(project, "folder", None)
        existing = {
            unicodedata.normalize("NFC", str(e.get("written_form") or e.get("word") or "")).casefold()
            for e in self._pronunciation_list({})
        }
        if project_folder:
            if not getattr(project, "chapters", None):
                raise ValueError("Import a book with saved chapters before analysing pronunciation.")
            job_id = self._new_job(
                "pronunciation-analysis", "Analyze book pronunciation",
                "Review multilingual names, foreign-language terms and pronunciation-sensitive terminology",
                project,
            )
            self._job_update(
                job_id, state="running", started_at=self._now(),
                stage="Preparing local AI analysis", progress=2,
                message="Preparing the saved book text for pronunciation analysis.",
            )
            threading.Thread(
                target=self._pronunciation_analysis_worker,
                args=(job_id, project, existing),
                daemon=True,
                name="RyuPronunciationAnalysis",
            ).start()
            return {"job_id":job_id,"state":"running","project_folder":str(Path(project_folder).resolve())}

        # A folderless project is used only by lightweight unit-test harnesses.
        # Keep a conservative deterministic seam there; installed projects always
        # take the real AudiobookBrain path above.
        state = {}
        names: set[str] = set()
        for chapter in getattr(project, "chapters", []) or []:
            source_text = str(chapter.text or "")
            names.update(n.strip() for n in suggest_names_from_text(source_text) if len(n.strip()) > 1)
            for character in state.get("characters") or []:
                if not isinstance(character, dict):
                    continue
                candidates = [character.get("name"), *(character.get("aliases") or [])]
                for candidate in candidates:
                    candidate = str(candidate or "").strip()
                    if len(candidate) > 1 and re.search(
                        r"(?i)(?<![\w])" + re.escape(candidate) + r"(?![\w])", source_text
                    ):
                        names.add(candidate)
        suggestions = [{
            "written_form":name,"spoken_form":suggest_pronunciation(name),
            "language":"Auto-detect","handling_mode":"automatic",
            "scope":"current_book","scope_type":"current_book","scope_id":"",
            "origin":"ai","enabled":False,"review_required":True,
        } for name in sorted(names,key=str.casefold)
          if unicodedata.normalize("NFC",name).casefold() not in existing]
        job_id = self._new_job("pronunciation-analysis","Analyze pronunciation","Lightweight project analysis",project)
        self._job_update(
            job_id,state="completed",stage="Review suggestions",progress=100,
            message=f"Found {len(suggestions)} pronunciation suggestion(s); none enabled automatically",
            result={"suggestions":suggestions,"count":len(suggestions)},
        )
        return {"job_id":job_id,"state":"completed","suggestions":suggestions,"count":len(suggestions)}

    def _pronunciation_analysis_worker(
        self, job_id: str, project, existing: set[str]
    ) -> None:
        """Run the same local audiobook AI used by the Director and return review-only rules."""
        try:
            from app.ai.brain import AudiobookBrain
            from app.ai.learning_context import load_project_learning_context
            from app.tts.pronunciation_suggester import (
                is_pronunciation_override_candidate, is_likely_character_name_candidate,
            )
            from app.chapters.characters import (
                is_likely_character_name, is_user_confirmed_character_record,
            )
            # This worker must not call the UI bridge's _character_list method:
            # the pronunciation worker can run independently of Character Studio,
            # and _character_list performs UI-facing persistence cleanup. Use the
            # saved project cast directly and apply the same authoritative filter.
            state = load_state(project.folder)
            confirmed_character_names: set[str] = set()
            for character in state.get("characters") or []:
                if not isinstance(character, dict):
                    continue
                character_name = str(character.get("name") or "").strip()
                character_trusted = is_user_confirmed_character_record(character)
                if character_name and is_likely_character_name(character_name, trusted=character_trusted):
                    confirmed_character_names.add(character_name.casefold())
                    aliases = character.get("aliases") or []
                    if isinstance(aliases, (list, tuple)):
                        confirmed_character_names.update(
                            str(alias).strip().casefold() for alias in aliases
                            if str(alias or "").strip()
                            and is_likely_character_name(str(alias), trusted=character_trusted)
                        )
            learning_context = load_project_learning_context(Path(project.folder))
            brain = AudiobookBrain(Path(project.folder))
            try:
                analysis = brain.analyze_book(
                    project.chapters,
                    learning_context=learning_context,
                    progress=lambda fraction, detail: self._job_update(
                        job_id,
                        stage=str(detail or "Analyzing book pronunciation"),
                        message=str(detail or "Analyzing saved chapter text"),
                        progress=min(95,max(3,5+int(90*float(fraction or 0)))),
                    ),
                )
            finally:
                brain.close()

            source_text = "\n\n".join(str(chapter.text or "") for chapter in project.chapters)
            # Add AI-discovered identities only when the canonical name/alias
            # passes the same character filter and appears as a whole source token.
            known_pronunciation_names = set(confirmed_character_names)
            for chapter_report in analysis.get("chapters", []) if isinstance(analysis, dict) else []:
                if not isinstance(chapter_report, dict):
                    continue
                for ai_character in chapter_report.get("characters", []) or []:
                    if not isinstance(ai_character, dict):
                        continue
                    for raw_name in [ai_character.get("name"), *(ai_character.get("aliases") or [])]:
                        ai_name = str(raw_name or "").strip()
                        if not ai_name or not is_likely_character_name(ai_name, explicit=True):
                            continue
                        if re.search(
                            r"(?i)(?<![\w])" + re.escape(ai_name) + r"(?![\w])",
                            source_text,
                        ):
                            known_pronunciation_names.add(ai_name.casefold())
            seen = set(existing)
            suggestions = []
            for raw in analysis.get("pronunciation", []) if isinstance(analysis, dict) else []:
                if not isinstance(raw, dict):
                    continue
                try:
                    written = _normalize_pronunciation_text(raw.get("written"), "Written term", 500)
                    spoken = _normalize_pronunciation_text(raw.get("spoken"), "Pronunciation", 1000)
                except ValueError:
                    continue
                native_script = bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]", written))
                present = (
                    written.casefold() in source_text.casefold()
                    if native_script else
                    bool(re.search(r"(?i)(?<![\w])" + re.escape(written) + r"(?![\w])", source_text))
                )
                key = unicodedata.normalize("NFC", written).casefold()
                candidate_is_name = is_likely_character_name_candidate(
                    written, known_names=known_pronunciation_names, script=raw.get("script")
                )
                # Unknown one-token Latin transliterations (for example, Yamato)
                # are not accepted by the generic pronunciation guard on their
                # own. Permit this narrow path only when the authoritative
                # character-name validator accepts the token; it still must be
                # present in the source, carry explicit non-English language
                # evidence, and pass the same common-English rejection below.
                if not candidate_is_name and len(written.split()) == 1:
                    candidate_is_name = is_likely_character_name(written, explicit=True)
                pronunciation_evidence = is_pronunciation_override_candidate(
                    written,
                    source_language=raw.get("source_language"),
                    script=raw.get("script"),
                    known_names=known_pronunciation_names,
                )
                if not present or not candidate_is_name or not pronunciation_evidence:
                    continue
                if key in seen:
                    continue
                try:
                    confidence = float(raw.get("confidence") or 0)
                except (TypeError, ValueError, OverflowError):
                    continue
                if not math.isfinite(confidence) or confidence < 0.80:
                    continue
                ipa = str(raw.get("ipa") or "").strip()
                if spoken.casefold() == written.casefold() and not ipa:
                    continue
                alternatives = raw.get("alternatives")
                alternatives = alternatives if isinstance(alternatives,list) else []
                suggestions.append({
                    "written_form":written,
                    "spoken_form":spoken,
                    "language":str(raw.get("source_language") or "Auto-detect"),
                    "handling_mode":"automatic",
                    "scope":"current_book",
                    "scope_type":"current_book",
                    "scope_id":"",
                    "origin":"ai",
                    "enabled":False,
                    "review_required":True,
                    "confidence":confidence,
                    "ipa":ipa,
                    "script":str(raw.get("script") or ""),
                    "reason":str(raw.get("reason") or ""),
                    "alternatives":[str(item) for item in alternatives[:2] if str(item or "").strip()],
                })
                seen.add(key)

            folder = str(Path(project.folder).resolve())
            title = str(getattr(project,"title","") or "Active project")
            message = (
                f"Found {len(suggestions)} high-confidence AI pronunciation suggestion(s) in {title}; "
                "review and accept each draft before it can affect synthesis."
                if suggestions else
                f"No new high-confidence pronunciation suggestions were found in {title}. Existing dictionary entries were left unchanged."
            )
            self._job_update(
                job_id,state="completed",stage="Pronunciation review ready",progress=100,
                message=message,
                result={"suggestions":suggestions,"count":len(suggestions),"project_folder":folder,"project_title":title},
            )
        except Exception as exc:
            log.exception("Local AI pronunciation analysis failed for job %s",job_id)
            self._job_update(
                job_id,state="failed",stage="Pronunciation analysis failed",
                message="Local AI pronunciation analysis failed. No dictionary entries were saved. Check the local AI runtime and retry.",
                error={"code":"pronunciation_analysis_failed","message":str(exc)},
                recoverable=True,
            )

    @staticmethod
    def _character_series_for_voice_assignment(character: dict[str, Any], default_series: str) -> str:
        series = str(character.get("series") or character.get("series_name") or "").strip()
        if series:
            return series
        scope = str(character.get("scope") or "").strip()
        match = re.match(r"(?i)^series\s*[·:-]\s*(.+)$", scope)
        return match.group(1).strip() if match else str(default_series or "").strip()

    def _effective_generation_character_rows(
        self,
        state: dict[str, Any],
        default_series: str,
        *,
        available_profiles=None,
        strict: bool = True,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Resolve Character Studio and legacy Voice Cast into one production cast.

        Character Studio records remain primary. Legacy Voice Cast entries are
        merged only when their character identity is unambiguous; a name shared
        by multiple series is never routed to the first matching character.
        Every non-empty profile reference must resolve to a currently saved
        Voice Studio profile before it can be treated as configured.
        """
        profiles = list(available_profiles if available_profiles is not None else load_profiles())
        by_name = {
            str(profile.name or "").strip().casefold(): profile
            for profile in profiles if str(getattr(profile, "name", "") or "").strip()
        }
        by_voice_id: dict[str, list[Any]] = {}
        for profile in profiles:
            voice_id = str(getattr(profile, "voice_id", "") or "").strip().casefold()
            if voice_id:
                by_voice_id.setdefault(voice_id, []).append(profile)

        issues: list[str] = []

        def resolve_profile(value: Any, *, allow_voice_id: bool = False):
            key = str(value or "").strip().casefold()
            if not key:
                return None
            match = by_name.get(key)
            if match is not None:
                return match
            if allow_voice_id:
                candidates = by_voice_id.get(key, [])
                if len(candidates) == 1:
                    return candidates[0]
                if len(candidates) > 1:
                    issues.append(
                        f"Voice ID '{str(value).strip()}' matches more than one saved Voice Studio profile."
                    )
            return None

        rows = [
            dict(row) for row in (state.get("characters") or [])
            if isinstance(row, dict)
        ]

        # Normalize older alternate assignment fields on Character Studio rows.
        for row in rows:
            existing = str(row.get("voice_profile") or "").strip()
            if not existing:
                existing = next((
                    str(row.get(key) or "").strip()
                    for key in ("voice_profile_name", "assigned_voice_profile", "profile_name", "voice_name")
                    if str(row.get(key) or "").strip()
                ), "")
            profile = resolve_profile(existing) if existing else None
            if existing and profile is None:
                issues.append(
                    f"Character '{row.get('name') or 'Unknown'}' references unavailable saved voice profile '{existing}'."
                )
            elif profile is not None:
                row["voice_profile"] = str(profile.name)
            elif not str(row.get("voice_profile") or "").strip():
                legacy_voice_id = str(row.get("voice_id") or "").strip()
                if legacy_voice_id:
                    profile = resolve_profile(legacy_voice_id, allow_voice_id=True)
                    if profile is None:
                        issues.append(
                            f"Character '{row.get('name') or 'Unknown'}' has an unresolvable legacy voice ID '{legacy_voice_id}'."
                        )
                    else:
                        row["voice_profile"] = str(profile.name)

        legacy_cast = state.get("voice_cast")
        legacy_cast = legacy_cast if isinstance(legacy_cast, dict) else {}
        for raw_name, raw_assignment in legacy_cast.items():
            name = str(raw_name or "").strip()
            if not name or name.casefold() == "narrator":
                continue

            requested_series = ""
            raw_profile = ""
            allow_voice_id = False
            if isinstance(raw_assignment, dict):
                requested_series = str(raw_assignment.get("series") or "").strip()
                raw_profile = next((
                    str(raw_assignment.get(key) or "").strip()
                    for key in ("voice_profile", "voice_profile_name", "assigned_voice_profile", "profile_name", "voice_name")
                    if str(raw_assignment.get(key) or "").strip()
                ), "")
                if not raw_profile:
                    raw_profile = str(raw_assignment.get("voice_id") or "").strip()
                    allow_voice_id = bool(raw_profile)
            else:
                raw_profile = str(raw_assignment or "").strip()

            if not raw_profile:
                continue
            profile = resolve_profile(raw_profile, allow_voice_id=allow_voice_id)
            if profile is None:
                issues.append(
                    f"Legacy Voice Cast entry '{name}' references unavailable voice profile '{raw_profile}'."
                )
                continue

            name_key = name.casefold()
            matching_rows = []
            for row in rows:
                canonical = str(row.get("name") or row.get("primary_name") or "").strip()
                aliases = row.get("aliases") or []
                aliases = aliases if isinstance(aliases, (list, tuple)) else ([aliases] if aliases else [])
                identity_names = {canonical.casefold()}
                identity_names.update(str(alias or "").strip().casefold() for alias in aliases)
                if name_key not in identity_names:
                    continue
                row_series = self._character_series_for_voice_assignment(row, default_series)
                if requested_series and row_series.casefold() != requested_series.casefold():
                    continue
                matching_rows.append(row)

            if len(matching_rows) > 1:
                issues.append(
                    f"Legacy Voice Cast entry '{name}' matches multiple characters; specify its series in Character Studio."
                )
                continue
            if matching_rows:
                row = matching_rows[0]
                current = str(row.get("voice_profile") or "").strip()
                if current and current.casefold() != str(profile.name).casefold():
                    issues.append(
                        f"Character '{name}' has conflicting Character Studio and legacy Voice Cast profiles."
                    )
                    continue
                row["voice_profile"] = str(profile.name)
                if not str(row.get("series") or row.get("series_name") or "").strip():
                    row["series"] = requested_series or default_series
                continue

            # Older Voice Cast data may not have a Character Studio row at all.
            # Preserve its real profile route in an explicit virtual cast record.
            series = requested_series or default_series
            rows.append({
                "name": name,
                "aliases": [],
                "series": series,
                "scope": ("Series · " + series) if series else "Current book only",
                "voice_profile": str(profile.name),
                "legacy_voice_cast": True,
            })

        if strict and issues:
            raise ValueError(
                "Saved character voice assignments need attention before generation: "
                + " ".join(issues[:3])
            )
        return rows, issues

    def _production_narrator_only_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist a per-book narrator-only choice, including an explicit opt-out."""
        project = self._active_project()
        expected_folder = str(payload.get("expected_project_folder") or "").strip()
        if expected_folder and Path(expected_folder).expanduser().resolve() != project.folder.resolve():
            raise ValueError(
                "The active project changed before Narrator-Only Generation could be saved. "
                "Reopen Production and retry."
            )
        enabled = payload.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ValueError("Narrator-Only Generation must be enabled or disabled explicitly.")
        state = load_state(project.folder)
        series = self._project_series_name(project, state)
        narrator = self._narrator_series_default_read(project, state, series)
        profile_name = str(narrator.get("effective_profile_name") or "").strip()
        narrator_available = bool(profile_name and narrator.get("profile_available"))

        # Count resolved saved profiles, not stale profile names or invalid
        # legacy IDs. Narrator-only is available only for a valid narrator and
        # zero configured character voice profiles.
        saved_profiles = load_profiles()
        saved_profile_names = {
            str(getattr(profile, "name", "") or "").strip().casefold()
            for profile in saved_profiles
            if str(getattr(profile, "name", "") or "").strip()
        }
        character_rows, _issues = self._effective_generation_character_rows(
            state,
            series,
            strict=False,
        )
        configured_profiles = [
            row for row in character_rows
            if str(row.get("voice_profile") or "").strip().casefold() in saved_profile_names
        ]
        if enabled and not narrator_available:
            raise ValueError(
                "Save an available narrator profile for this book or its series before enabling Narrator-Only Generation."
            )
        if enabled and configured_profiles:
            raise ValueError(
                "Narrator-Only Generation is available only when this project has zero "
                "configured character voice profiles. Switch to multi-character production "
                "to use the saved character assignments."
            )
        state["narrator_only_generation"] = enabled
        user_opt_out = bool(not enabled and narrator_available and not configured_profiles)
        if user_opt_out:
            state["narrator_only_generation_user_opt_out"] = True
        else:
            state.pop("narrator_only_generation_user_opt_out", None)
        state["modified_at"] = self._now()
        save_state(project.folder, state)
        return {
            "saved": True,
            "enabled": enabled,
            "user_opt_out": user_opt_out,
            "automatic": bool(narrator_available and not configured_profiles and not user_opt_out),
            "project_folder": str(project.folder),
        }

    def _resolve_narrator_for_generation(self, project, state: dict[str, Any], chapters):
        """Resolve narrator and choose automatic zero-cast or cast-aware routing.

        A valid narrator automatically reads every passage when the project
        has no configured character voice profiles, unless the user explicitly
        opts out. Configured character profiles always return the project to
        normal cast-aware speaker review.
        """
        series = self._project_series_name(project, state)
        selection = self._narrator_series_default_read(project, state, series)
        profile_name = str(selection.get("effective_profile_name") or "").strip()
        if not profile_name:
            raise ValueError(
                "Generation is blocked because this project has no narrator voice. "
                "Choose a series default or save a project narrator override first."
            )
        profile = self._find_profile(profile_name)
        if profile is None or not selection.get("profile_available"):
            raise ValueError(
                f"The effective narrator profile '{profile_name}' is unavailable. "
                "Restore the saved Voice Studio profile or choose another narrator."
            )

        user_opt_out = state.get("narrator_only_generation_user_opt_out", False) is True
        saved_profiles = load_profiles()
        saved_profile_names = {
            str(getattr(saved_profile, "name", "") or "").strip().casefold()
            for saved_profile in saved_profiles
            if str(getattr(saved_profile, "name", "") or "").strip()
        }

        # Resolve non-strictly first so stale references cannot masquerade as
        # configured profiles or prevent automatic narrator-only mode.
        character_rows, cast_mapping_issues = self._effective_generation_character_rows(
            state if isinstance(state, dict) else {},
            series,
            strict=False,
        )
        configured_profiles = [
            row for row in character_rows
            if str(row.get("voice_profile") or "").strip().casefold() in saved_profile_names
        ]

        narrator_only = not configured_profiles and not user_opt_out
        narrator_only_disabled_reason = ""
        if configured_profiles:
            if state.get("narrator_only_generation", False) is True:
                narrator_only_disabled_reason = (
                    "Narrator-Only Generation was switched off because this project now has "
                    "one or more configured character voice profiles. Multi-character speaker "
                    "review and saved character assignments apply."
                )
            state["narrator_only_generation"] = False
            state.pop("narrator_only_generation_user_opt_out", None)
            character_rows, cast_mapping_issues = self._effective_generation_character_rows(
                state if isinstance(state, dict) else {},
                series,
                strict=True,
            )
        elif narrator_only:
            state["narrator_only_generation"] = True
            state.pop("narrator_only_generation_user_opt_out", None)
        else:
            state["narrator_only_generation"] = False

        if getattr(project, "folder", None) is not None and (
            state.get("narrator_only_generation", False) is True
            or narrator_only_disabled_reason
        ):
            state["modified_at"] = self._now()
            save_state(project.folder, state)

        effective_selection = dict(selection)
        effective_selection.update({
            "generation_mode": "narrator_only" if narrator_only else "character_cast",
            "narrator_only": narrator_only,
            "character_voice_profile_count": len(configured_profiles),
            "dialogue_routing": "narrator_for_all_passages" if narrator_only else "saved_character_assignments",
            "effective_character_rows": character_rows,
            "narrator_only_disabled_reason": narrator_only_disabled_reason,
        })
        if narrator_only:
            return profile, effective_selection

        eligible_chapter_ids = {str(getattr(chapter, "chapter_id", "") or "") for chapter in chapters}
        if getattr(project, "folder", None) is None:
            # Projectless tests may use a SimpleNamespace instead of a persisted
            # Project. Keep this small harness on the exact source segmenter.
            from app.chapters.speaker_segmentation import segment_chapter_speakers
            unresolved = [
                (int(chapter.number), str(segment.text or ""))
                for chapter in chapters
                for segment in segment_chapter_speakers(chapter)
                if segment.needs_review or segment.kind in {"needs_speaker_review", "review_required"}
            ]
            passage_index = {"issues": []}
        else:
            from app.chapters.passage_index import load_or_build_passage_index
            passage_index = load_or_build_passage_index(
                project.folder, project.chapters,
                suggested_passages=state.get("character_dialogue_suggestions") or [],
            )
            unresolved = [
                (int(row.get("chapter_number") or 0), str(row.get("text") or ""))
                for row in passage_index["passages"]
                if str(row.get("chapter_id") or "") in eligible_chapter_ids
                and bool(row.get("needs_review"))
            ]
        unresolved.extend(
            (int(issue.get("chapter_number") or 0), str(issue.get("text") or ""))
            for issue in passage_index.get("issues", [])
            if str(issue.get("chapter_id") or "") in eligible_chapter_ids
        )
        if unresolved:
            examples = "; ".join(
                f"Chapter {number}: {text[:64].strip()!r}"
                for number, text in unresolved[:3]
            )
            mode_notice = (
                narrator_only_disabled_reason + " "
                if narrator_only_disabled_reason else ""
            )
            raise ValueError(
                mode_notice
                + f"Generation is blocked: {len(unresolved)} dialogue passage(s) still need speaker review. "
                "Assign a character speaker or correct the narration classification before generating. "
                + examples
            )
        effective_selection.update({
            "generation_mode": "character_cast",
            "narrator_only": False,
            "character_voice_profile_count": len(configured_profiles),
            "dialogue_routing": "saved_character_assignments",
            "effective_character_rows": character_rows,
        })
        return profile, effective_selection

    def _production_generate_book(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_no_active_model_lifecycle("start audiobook generation")
        check_active = getattr(self, "_assert_no_active_audio_synthesis", None)
        if callable(check_active):
            check_active("start audiobook generation")
        close_cache = getattr(self, "close_preview_provider_cache", None)
        if callable(close_cache):
            close_cache()
        requested_project_folder = str(payload.get("_project_folder") or "").strip()
        if requested_project_folder:
            requested_path = Path(requested_project_folder).expanduser().resolve()
            project = next(
                (item for item in list_projects() if str(item.folder.resolve()) == str(requested_path)),
                None,
            )
            if project is None:
                raise ValueError("The project for this generation job is no longer available in the local library.")
        else:
            project = self._active_project()

        active_generation_states = {
            "queued", "running", "paused", "pause_requested", "cancel_requested", "retrying"
        }
        with self._jobs_lock:
            active_generations = [
                row for row in getattr(self, "_jobs", {}).values()
                if str(row.get("type") or "") == "audiobook-generation"
                and str(row.get("state") or "").casefold() in active_generation_states
            ]
            active_for_project = [
                row for row in active_generations
                if str(row.get("project_folder") or "")
                and Path(str(row.get("project_folder"))).expanduser().resolve() == project.folder.resolve()
            ]
            limit_resolver = getattr(self, "_generation_concurrency_limit", None)
            concurrency_limit = limit_resolver() if callable(limit_resolver) else 1
            if len(active_generations) >= concurrency_limit:
                raise ValueError(
                    f"The configured heavy-generation limit is {concurrency_limit}. "
                    "Wait for an active audiobook job to finish, or increase the limit in Performance Center. "
                    "Low-memory mode enforces one heavy job at a time."
                )
        if active_for_project:
            raise ValueError("This project already has an active audiobook generation job. Resume or cancel that job before starting another.")

        chapters = [c for c in project.chapters if not getattr(c, "skip_for_generation", False) and (c.text or "").strip()]
        skipped = len(project.chapters) - len(chapters)
        empty_skipped = sum(1 for c in project.chapters if not (c.text or "").strip())
        excluded_skipped = sum(1 for c in project.chapters if getattr(c, "skip_for_generation", False) and (c.text or "").strip())
        if not chapters:
            raise ValueError("No chapters are eligible for generation. Restore chapter text or re-include a skipped chapter.")
        state = load_state(project.folder)
        from app.audio.library import effective_background_audio_mode, is_chapter_transition_sound_enabled, validate_saved_audio_paths
        background_audio_mode = effective_background_audio_mode(state)
        sound_enabled = background_audio_mode != "off"
        validate_saved_audio_paths(state)
        # The saved series default or explicit project override is authoritative.
        # Never let a transient Voice Studio selection silently replace the narrator
        # that this project will use for production.
        profile, narrator_selection = self._resolve_narrator_for_generation(project, state, chapters)
        narrator_only = bool(narrator_selection.get("narrator_only"))
        profile_name = profile.name
        metadata_missing = missing_required_metadata_fields(project.title, state, profile_name)
        if metadata_missing:
            raise ValueError(
                "Full audiobook generation is blocked until required Input Project Details are saved. "
                "Complete: " + ", ".join(metadata_missing) + "."
            )
        provider, voice = provider_from_profile(profile)
        # Include the full selected narrator profile in resumable chunk identity
        # even when this book has no character-specific voice assignments.
        from app.tts.profile_provider import ProfileBoundProvider
        provider = ProfileBoundProvider(provider, profile)
        # Character Studio assignments must affect actual synthesis, not only the
        # roster UI. Wrap the narrator with the existing cast-aware router when
        # at least one saved character has a valid voice assignment.
        cast_assignments: dict[str, str] = {}
        cast_identity_assignments: dict[str, str] = {}
        cast_profiles: dict[str, Any] = {}
        saved_profiles = load_profiles()
        available_profiles = {p.name.casefold(): p for p in saved_profiles}
        project_series = self._project_series_name(project, state)
        generation_characters = narrator_selection.get("effective_character_rows")
        if not isinstance(generation_characters, list):
            generation_characters, _cast_mapping_issues = self._effective_generation_character_rows(
                state, project_series, available_profiles=saved_profiles, strict=True
            )
        # Narrator-only mode must use exactly the saved narrator profile. Do not
        # even resolve cast profiles in this mode: an unavailable character
        # profile must not block narration-only generation.
        if not narrator_only:
            for character in generation_characters:
                if not isinstance(character, dict):
                    continue
                assigned_name = str(character.get("voice_profile") or "").strip()
                if not assigned_name:
                    continue
                assigned_profile = available_profiles.get(assigned_name.casefold())
                if assigned_profile is None:
                    raise ValueError(
                        f"Character '{character.get('name', 'Unknown')}' uses voice profile "
                        f"'{assigned_name}', which is no longer available. Reassign its voice in Character Studio."
                    )
                cast_profiles[assigned_profile.name] = assigned_profile
                character_series = self._character_series_for_voice_assignment(
                    character, project_series
                )
                character_names = [str(character.get("name") or "").strip()]
                aliases = character.get("aliases") or []
                if isinstance(aliases, list):
                    character_names.extend(str(alias).strip() for alias in aliases)
                for character_name in character_names:
                    if character_name:
                        cast_assignments[character_name] = assigned_profile.name
                        if character_series:
                            cast_identity_assignments[
                                character_identity_key(character_name, character_series)
                            ] = assigned_profile.name
            if cast_assignments or cast_identity_assignments:
                from app.tts.cast_provider import CastAwareProvider
                provider = CastAwareProvider(
                    provider, voice, cast_profiles, cast_assignments,
                    narrating_character=str(state.get("narrating_character") or ""),
                    backend_override=str(state.get("backend") or "automatic"),
                    narrator_profile=profile,
                    identity_assignments=cast_identity_assignments,
                )
        output_text = str(payload.get("output_path") or state.get("output_path") or state.get("generation_target_path") or "").strip()
        if output_text:
            output = Path(output_text).expanduser().resolve()
            if output.suffix.lower() != ".m4b":
                raise ValueError(
                    "This build exports chaptered audiobooks as .m4b only. "
                    "M4A/MP3 export is not implemented yet; choose an .m4b output path."
                )
        else:
            safe = re.sub(r'[<>:"/\\|?*]+', "_", project.title).strip() or "Audiobook"
            output = audiobooks_root() / (safe + ".m4b")
        output.parent.mkdir(parents=True, exist_ok=True)
        if not os.access(output.parent, os.W_OK):
            raise PermissionError("The selected output folder is not writable.")
        try:
            default_bitrate = self.settings.value(
                "production/bitrate",
                self.settings.value("audio/default_bitrate", 256),
            )
        except Exception:
            default_bitrate = 256
        bitrate = int(payload.get("bitrate") or state.get("audio_bitrate") or default_bitrate or 256)
        if not 128 <= bitrate <= 320:
            raise ValueError("Select a bitrate from 128 through 320 kbps.")
        # Recheck under the same lock used to create the durable job row.
        # Two concurrent Generate/Retry requests can both pass the early
        # preflight check; only the first may claim this project's generation.
        with self._jobs_lock:
            active_generations = [
                row for row in getattr(self, "_jobs", {}).values()
                if str(row.get("type") or "") == "audiobook-generation"
                and str(row.get("state") or "").casefold() in active_generation_states
            ]
            active_for_project = [
                row for row in active_generations
                if str(row.get("project_folder") or "")
                and Path(str(row.get("project_folder"))).expanduser().resolve() == project.folder.resolve()
            ]
            limit_resolver = getattr(self, "_generation_concurrency_limit", None)
            concurrency_limit = limit_resolver() if callable(limit_resolver) else 1
            if len(active_generations) >= concurrency_limit:
                raise ValueError(
                    "The heavy-generation concurrency limit was reached before this job could start. "
                    "No project state was changed."
                )
            if active_for_project:
                raise ValueError("This project already has an active audiobook generation job. Resume or cancel that job before starting another.")
            job_id = self._new_job(
                "audiobook-generation",
                "Generate " + project.title,
                f"Render {len(chapters)} eligible chapter(s); skip {empty_skipped} empty and {excluded_skipped} excluded chapter(s)",
                project,
            )
        # While a new generation is running, do not expose a prior file at the
        # same destination as the current audiobook. Keep the intended destination
        # separately; only publish output_path after the final file validates.
        # A new explicit generation attempt consumes any prior interrupted-job
        # marker; the newly issued job ID becomes the sole project owner.
        for recovery_key in (
            "generation_recovery_required",
            "generation_interrupted_at",
            "generation_interruption_reason",
        ):
            state.pop(recovery_key, None)
        generation_mode = str(narrator_selection.get("generation_mode") or "character_cast")
        state.update({"voice_profile": profile.name, "voice_id": profile.voice_id,
                      "narrator": profile.name,
                      "narrator_profile_source": str(narrator_selection.get("source") or "none"),
                      "narrator_series_default": str(narrator_selection.get("profile_name") or ""),
                      "generation_mode": generation_mode,
                      "narrator_only_generation": narrator_only,
                      "character_voice_profile_count": int(narrator_selection.get("character_voice_profile_count") or 0),
                      "output_path": None, "generation_target_path": str(output),
                      "status": "generating", "audio_bitrate": bitrate, "generation_job_id": job_id,
                      "generation_started_at": self._now(), "empty_chapters_skipped": empty_skipped,
                      "excluded_chapters_skipped": excluded_skipped, "chapters_skipped_for_generation": skipped})
        save_state(project.folder, state)
        metadata = {"title": str(payload.get("title") or project.title),
                    "author": str(payload.get("author") or state.get("author") or ""),
                    "narrator": profile.name, "publisher": str(state.get("publisher") or ""),
                    "series": str(state.get("series") or ""),
                    "series_number": str(state.get("series_volume") or ""),
                    "language": str(state.get("language") or ""),
                    "year": str(state.get("year") or ""), "genre": str(state.get("genre") or "")}
        chapter_bgm_strategy = str(
            state.get("chapter_bgm_strategy") or
            ("custom" if state.get("chapter_bgm_overrides") else "same")
        ).strip().casefold()
        chapter_based_bgm = chapter_bgm_strategy in {"custom", "chapter-based", "chapter_based", "chapter"}
        effective_chapter_transition_sound = sound_enabled and is_chapter_transition_sound_enabled(state)
        opening_cue_path = (
            Path(state["opening_cue_path"])
            if effective_chapter_transition_sound and state.get("opening_cue_path") else None
        )
        page_turn_cue_path = (
            Path(state["page_turn_cue_path"])
            if effective_chapter_transition_sound and state.get("page_turn_cue_path") else None
        )
        ending_cue_path = (
            Path(state["ending_cue_path"])
            if effective_chapter_transition_sound and state.get("ending_cue_path") else None
        )
        manager = GenerationManager(
            provider, voice, chapters, project.folder / "working_audio",
            on_progress=lambda *args: self._generation_progress(job_id, *args),
            on_finished=lambda summary: self._generation_finished(job_id, project, summary, output, profile.name),
            pronunciation_dictionary=_effective_pronunciation_dictionary(state),
            narration_speed=float(state.get("narration_speed") or 0.90),
            pacing_profile=str(state.get("pacing_profile") or "natural"),
            metadata=metadata, bitrate=bitrate,
            background_audio_path=(
                Path(state["background_audio_path"])
                if sound_enabled and state.get("background_audio_path") and not chapter_based_bgm else None
            ),
            background_audio_volume=float(state.get("background_audio_volume") if state.get("background_audio_volume") is not None else 0.18),
            narration_volume=float(state.get("narration_audio_volume") if state.get("narration_audio_volume") is not None else 1.0),
            cue_audio_volume=float(state.get("sound_cue_volume") if state.get("sound_cue_volume") is not None else 0.25),
            ambience_audio_path=Path(state["ambience_audio_path"]) if sound_enabled and state.get("ambience_audio_path") else None,
            ambience_audio_volume=float(state.get("ambience_audio_volume") if state.get("ambience_audio_volume") is not None else 0.10),
            background_audio_fade_in=float(state.get("background_audio_fade_in") if state.get("background_audio_fade_in") is not None else 2.0),
            background_audio_fade_out=float(state.get("background_audio_fade_out") if state.get("background_audio_fade_out") is not None else 3.0),
            background_audio_mode=background_audio_mode,
            auto_music_style=str(state.get("auto_music_style") or "auto"),
            auto_music_variation=(state.get("auto_music_track_path") or None) if sound_enabled else None,
            chapter_transition_sound=effective_chapter_transition_sound,
            story_effects_enabled=bool(state.get("story_effects_enabled", False)),
            story_effect_volume=float(state.get("story_effect_volume") if state.get("story_effect_volume") is not None else 0.22),
            sound_cue_style=str(state.get("sound_cue_style") or "classic-book"),
            opening_cue_path=opening_cue_path,
            page_turn_cue_path=page_turn_cue_path,
            ending_cue_path=ending_cue_path,
            chapter_bgm_overrides=(state.get("chapter_bgm_overrides") if sound_enabled and isinstance(state.get("chapter_bgm_overrides"), dict) else {}),
            chapter_bgm_strategy=chapter_bgm_strategy,
        )
        with self._jobs_lock:
            self._generators[job_id] = manager
        start_message = f"Starting with {empty_skipped} empty and {excluded_skipped} excluded chapter(s) skipped"
        mode_notice = str(narrator_selection.get("narrator_only_disabled_reason") or "").strip()
        if mode_notice:
            start_message = mode_notice + " " + start_message
        if narrator_only:
            start_message += " • Narrator-only mode: the saved narrator will read narration and all dialogue"
        self._job_update(job_id, state="running", started_at=self._now(), stage="Preparing generation",
                         progress=1, message=start_message,
                         result={"output_path": str(output), "chapter_count": len(chapters),
                                 "empty_chapters_skipped": empty_skipped,
                                 "excluded_chapters_skipped": excluded_skipped,
                                 "chapters_skipped_for_generation": skipped,
                                 "voice_profile": profile.name,
                                 "generation_mode": generation_mode,
                                 "narrator_only": narrator_only,
                                 "character_voice_profile_count": int(narrator_selection.get("character_voice_profile_count") or 0)})
        try:
            manager.start(output, metadata["title"], metadata["author"],
                          Path(state["cover_path"]) if state.get("cover_path") and Path(state["cover_path"]).is_file() else None,
                          metadata=metadata)
        except Exception as exc:
            with self._jobs_lock:
                self._generators.pop(job_id, None)
            state["status"] = "failed"
            save_state(project.folder, state)
            self._job_update(job_id, state="failed", stage="Could not start generation", message=str(exc),
                             error={"code": "generation_start_failed", "message": str(exc)}, recoverable=True)
            raise
        return {"job_id": job_id, "state": "running", "output_path": str(output),
                "chapter_count": len(chapters), "empty_chapters_skipped": empty_skipped,
                "excluded_chapters_skipped": excluded_skipped,
                "chapters_skipped_for_generation": skipped, "voice_profile": profile.name,
                "generation_mode": generation_mode, "narrator_only": narrator_only,
                "character_voice_profile_count": int(
                    narrator_selection.get("character_voice_profile_count") or 0
                )}

    def _generation_progress(self, job_id: str, chapter: int, total: int, done: int, message: str) -> None:
        msg = str(message or "")
        state, stage, progress = "running", "Generating narration", None
        if msg.startswith("paused:"):
            state, stage, msg = "paused", "Paused at chapter checkpoint", msg.split(":", 1)[1]
        elif msg.startswith("plan:"):
            stage, progress = "Preparing generation plan", 2
        elif msg.startswith("provider:"):
            stage, msg = "Voice provider", msg.partition(":")[2]
        elif msg.startswith("pronunciation:"):
            _prefix, replacements, rules = msg.split(":", 2)
            stage = "Pronunciation rules applied"
            msg = f"Prepared {int(replacements)} pronunciation replacement(s) across {int(rules)} enabled rule(s) for synthesis."
        elif msg.startswith("chunk-start:"):
            stage, progress = "Rendering chapter audio", min(85, max(3, int(85 * max(0, chapter - 1) / max(1, total))))
        elif msg.startswith("chunk:"):
            stage = "Rendering narration chunks"
            match = re.search(r":(\d+)/(\d+):(\d+)/(\d+)", msg)
            if match:
                progress = min(88, max(3, 3 + int(85 * int(match.group(3)) / max(1, int(match.group(4))))))
        elif msg.startswith("m4b-packaging"):
            stage, progress = "Assembling audiobook", 90
        elif msg.startswith("m4b-package:"):
            stage = "Encoding and validating output"
            match = re.match(r"m4b-package:(\d+)/(\d+):(.*)", msg)
            if match:
                progress = min(98, 90 + int(8 * int(match.group(1)) / max(1, int(match.group(2)))))
                msg = match.group(3) or stage
        elif msg.startswith("m4b-complete"):
            stage, progress = "Validating final audiobook", 99
        elif msg.startswith("m4b-failed"):
            stage = "Audiobook assembly failed"
        changes = {"state": state, "stage": stage, "message": msg,
                   "current_chapter": int(chapter or 0), "chapters_total": int(total or 0)}
        if progress is not None:
            changes["progress"] = progress
        self._job_update(job_id, **changes)

    def _generation_finished(self, job_id: str, project, summary, output: Path, voice_name: str) -> None:
        reported_output = getattr(summary, "output_path", None)
        expected_output = Path(output).expanduser().resolve()
        actual = Path(reported_output).expanduser() if reported_output else expected_output
        try:
            reported_output_matches_target = (
                bool(reported_output) and actual.resolve() == expected_output
            )
        except (OSError, RuntimeError):
            reported_output_matches_target = False
        # A previous M4B is intentionally preserved on disk during a new
        # generation. Never infer success from that filename alone: this worker
        # must report the exact output it assembled for this attempt.
        valid = (
            reported_output_matches_target
            and actual.is_file()
            and actual.stat().st_size > 0
        )
        success = valid and not summary.cancelled and not summary.packaging_failed and not summary.chapters_failed and summary.chapters_completed == summary.chapters_total
        playback_output = None
        playback_error = ""
        state = load_state(project.folder)
        current_project_job_id = str(state.get("generation_job_id") or "").strip()
        callback_job_id = str(job_id or "").strip()
        owns_project_state = not current_project_job_id or current_project_job_id == callback_job_id

        # The project state can already belong to a newer generation by the
        # time this worker finishes. Read this job's immutable-at-start mode
        # from its own durable queue snapshot first; only use project state as
        # a compatibility fallback while this callback still owns that state.
        with self._jobs_lock:
            durable_jobs = getattr(self, "_jobs", {})
            job_row = dict(durable_jobs.get(callback_job_id) or {}) if isinstance(durable_jobs, dict) else {}
        prior_result = job_row.get("result")
        prior_result = dict(prior_result) if isinstance(prior_result, dict) else {}
        if "narrator_only" in prior_result:
            narrator_only = prior_result.get("narrator_only") is True
        elif prior_result.get("generation_mode"):
            narrator_only = str(prior_result.get("generation_mode")) == "narrator_only"
        else:
            narrator_only = state.get("narrator_only_generation", False) is True if owns_project_state else False
        generation_mode = "narrator_only" if narrator_only else "character_cast"
        count_value = prior_result.get("character_voice_profile_count")
        if count_value is None and owns_project_state:
            count_value = state.get("character_voice_profile_count", 0)
        try:
            character_voice_profile_count = max(0, int(count_value or 0))
        except (TypeError, ValueError, OverflowError):
            character_voice_profile_count = 0
        terminal_identity = {
            "generation_mode": generation_mode,
            "narrator_only": narrator_only,
            "character_voice_profile_count": character_voice_profile_count,
        }

        if not owns_project_state:
            # A late callback may finish after a newer generation has claimed
            # this project. Keep the old job's terminal record, but never let it
            # overwrite the newer project's status, completed chapters or output.
            newer_job_id = current_project_job_id
            if success:
                self._job_update(
                    job_id,
                    state="completed",
                    stage="Completed; project owned by newer generation",
                    progress=100,
                    message=(
                        "This generation completed, but a newer job now owns the project. "
                        "The older output was not attached to project state."
                    ),
                    output_path=None,
                    result={
                        **terminal_identity,
                        "superseded": True,
                        "superseded_by_job_id": newer_job_id,
                        "chapters_total": summary.chapters_total,
                        "chapters_completed": summary.chapters_completed,
                        "chapters_failed": list(summary.chapters_failed or []),
                        "voice_profile": voice_name,
                    },
                    error=None,
                    recoverable=False,
                )
            else:
                status = "cancelled" if summary.cancelled else "failed"
                detail = summary.packaging_error or (
                    "; ".join(str(v) for v in (summary.failure_details or {}).values())
                    if summary.failure_details else "Generated output did not pass final validation."
                )
                current = self._jobs.get(job_id, {}).get("progress", 0)
                self._job_update(
                    job_id,
                    state=status,
                    stage="Generation " + status + " (superseded)",
                    progress=min(98, int(current or 0)),
                    message=(
                        "A newer generation owns this project; the older job did not change "
                        "project state. " + detail
                    ),
                    output_path=None,
                    result={
                        **terminal_identity,
                        "superseded": True,
                        "superseded_by_job_id": newer_job_id,
                        "chapters_total": summary.chapters_total,
                        "chapters_completed": summary.chapters_completed,
                        "chapters_failed": list(summary.chapters_failed or []),
                        "voice_profile": voice_name,
                    },
                    error={
                        "code": status,
                        "message": detail,
                        "failed_chapters": list(summary.chapters_failed or []),
                        "superseded": True,
                        "superseded_by_job_id": newer_job_id,
                    },
                    recoverable=False,
                )
            with self._jobs_lock:
                self._generators.pop(job_id, None)
            return

        if success and is_iso_bmff_file(actual):
            # This callback runs on GenerationManager's worker thread. Prepare
            # the WebEngine-compatible MP3 before publishing the book as ready;
            # the authoritative chaptered AAC M4B remains untouched.
            self._job_update(
                job_id,
                stage="Preparing Audiobooks playback",
                progress=98,
                message="Preparing a browser-compatible playback copy from the validated M4B.",
            )
            try:
                playback_output = prepare_audiobook_playback_source(actual)
            except Exception as exc:
                playback_error = (
                    "The M4B was assembled, but its browser-compatible playback copy "
                    f"could not be prepared: {exc}"
                )
                log.exception("Could not prepare Audiobooks playback source for %s", actual)
                success = False

        # Persist the same generation identity to project state and the
        # terminal queue/history snapshot. This is deliberately derived from
        # the job's start snapshot above, not a later frontend selection.
        state.update({
            "generation_mode": generation_mode,
            "character_voice_profile_count": character_voice_profile_count,
            "narrator_only_generation": narrator_only,
        })

        if success:
            source_stat = actual.stat()
            state.update({"status": "completed", "output_path": str(actual), "voice_profile": voice_name,
                          "playback_output_path": str(playback_output) if playback_output else None,
                          "playback_source_path": str(actual.resolve()) if playback_output else None,
                          "playback_source_size": int(source_stat.st_size) if playback_output else None,
                          "playback_source_mtime_ns": int(source_stat.st_mtime_ns) if playback_output else None,
                          "playback_error": None,
                          "completed_chapters": list(summary.chapters_completed_numbers or []),
                          "failed_chapters": [], "generation_completed_at": self._now()})
            save_state(project.folder, state)
            self._job_update(job_id, state="completed", stage="Audiobook ready", progress=100,
                             message="Generator completed; the M4B and Audiobooks playback copy are ready",
                             output_path=str(actual), result={**terminal_identity,
                                 "output_path": str(actual), "file_url": actual.resolve().as_uri(),
                                 "playback_output_path": str(playback_output) if playback_output else None,
                                 "playback_format": playback_output.suffix.lower().lstrip(".") if playback_output else None,
                                 "file_size": actual.stat().st_size, "chapters_total": summary.chapters_total,
                                 "chapters_completed": summary.chapters_completed,
                                 "chapter_count": summary.chapters_total,
                                 "empty_chapters_skipped": int(state.get("empty_chapters_skipped") or 0),
                                 "excluded_chapters_skipped": int(state.get("excluded_chapters_skipped") or 0),
                                 "chapters_skipped_for_generation": int(state.get("chapters_skipped_for_generation") or 0),
                                 "chapters_failed": list(summary.chapters_failed), "voice_profile": voice_name},
                             error=None, recoverable=False)
        else:
            status = "cancelled" if summary.cancelled else "failed"
            state.update({"status": status, "failed_chapters": list(summary.chapters_failed or []),
                          "completed_chapters": list(summary.chapters_completed_numbers or [])})
            if playback_error:
                state["playback_error"] = playback_error
            save_state(project.folder, state)
            detail = playback_error or summary.packaging_error or (
                "; ".join(str(v) for v in (summary.failure_details or {}).values())
                if summary.failure_details else (
                    "Generation did not report the expected output file for this attempt."
                    if not reported_output_matches_target
                    else "Generated output did not pass final validation."
                )
            )
            current = self._jobs.get(job_id, {}).get("progress", 0)
            self._job_update(job_id, state=status, stage="Generation " + status,
                             progress=min(98, int(current or 0)), message=detail,
                             # A previous successful file may still exist at the same
                             # destination. Do not attach it to a failed/cancelled job
                             # as if this attempt produced a complete audiobook.
                             output_path=str(actual) if valid and status != "cancelled"
                                 and not summary.packaging_failed and not summary.chapters_failed
                                 and summary.chapters_completed == summary.chapters_total else None,
                             result={**terminal_identity,
                                     "output_path": str(actual) if valid and status != "cancelled"
                                         and not summary.packaging_failed and not summary.chapters_failed
                                         and summary.chapters_completed == summary.chapters_total else None,
                                     "chapters_total": summary.chapters_total,
                                     "chapters_completed": summary.chapters_completed,
                                     "completed_chapters": list(summary.chapters_completed_numbers or []),
                                     "chapters_failed": list(summary.chapters_failed or []),
                                     "chapter_count": summary.chapters_total,
                                     "empty_chapters_skipped": int(state.get("empty_chapters_skipped") or 0),
                                     "excluded_chapters_skipped": int(state.get("excluded_chapters_skipped") or 0),
                                     "chapters_skipped_for_generation": int(state.get("chapters_skipped_for_generation") or 0),
                                     "voice_profile": voice_name},
                             error={"code": status, "message": detail,
                                    "failed_chapters": list(summary.chapters_failed or [])},
                             recoverable=not summary.cancelled)
        with self._jobs_lock:
            self._generators.pop(job_id, None)

    def _production_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        raw_chapter_number = payload.get("chapter_number")
        if raw_chapter_number in (None, ""):
            raise ValueError("Select a chapter saved in Production Studio before creating a chapter-specific preview.")
        try:
            chapter_number = int(raw_chapter_number)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Choose a valid chapter for the production preview.") from exc
        chapter = next(
            (item for item in project.chapters if int(item.number) == chapter_number),
            None,
        )
        if chapter is None:
            raise ValueError("The selected saved chapter is no longer available. Refresh the chapter list and try again.")
        requested_chapter_id = str(payload.get("chapter_id") or "").strip()
        actual_chapter_id = str(getattr(chapter, "chapter_id", "") or getattr(chapter, "id", "") or "").strip()
        if requested_chapter_id and actual_chapter_id and requested_chapter_id != actual_chapter_id:
            raise ValueError("The selected chapter identity changed before preview started. Refresh the saved chapter list and try again.")
        if not str(chapter.text or "").strip():
            raise ValueError("The selected chapter contains no saved narration text to preview.")

        # Production Preview must use the same saved project/series narrator as
        # full-book generation. Never let a transient Voice Studio card selection
        # or an unsaved provider/voice payload silently change production identity.
        state = load_state(project.folder)
        resolver = getattr(self, "_resolve_narrator_for_generation", None)
        if callable(resolver):
            # The real bridge always exposes this shared resolver so Production
            # Preview and full-book generation use the same effective mode.
            profile, narrator_selection = resolver(project, state, [chapter])
            narrator_only = bool(narrator_selection.get("narrator_only"))
        else:
            # Retain compatibility for lightweight bridge adapters that predate
            # the shared resolver. The application bridge never takes this path.
            series = self._project_series_name(project, state)
            narrator = self._narrator_series_default_read(project, state, series)
            narrator_only = state.get("narrator_only_generation", False) is True
            name = str(narrator.get("effective_profile_name") or "").strip()
            if not name:
                raise ValueError(
                    "Select and save this project's narrator profile before creating a Production preview."
                )
            profile = self._find_profile(name)
            if profile is None or not narrator.get("profile_available"):
                raise ValueError(
                    f"The project's saved narrator profile '{name}' is unavailable. Restore or reassign it in Voice Studio."
                )
            narrator_selection = {"narrator_only": narrator_only}

        # Production preview is a saved-project operation, not an arbitrary
        # text/provider audition. Always use the selected chapter's persisted
        # text, effective saved narrator, assigned character voices, project
        # pronunciation switch and the native Sound Design renderer. Reject
        # caller flags that could make preview differ from final generation.
        preview_payload = dict(payload)
        for key in ("provider", "voice_id", "text", "allow_projectless_preview",
                    "_bypass_pronunciation_dictionary"):
            preview_payload.pop(key, None)
        preview_payload.update({
            "profile_name": profile.name,
            "chapter_number": chapter_number,
            "chapter_id": actual_chapter_id,
            "route_character_cast": not narrator_only,
            "apply_pronunciation_rules": True,
            "include_sound_design": True,
            "_production_preview": True,
        })
        return self._voice_preview(preview_payload)

    def _job_pause(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = str(payload.get("job_id") or "")
        with self._jobs_lock:
            manager = self._generators.get(job_id)
            row = self._jobs.get(job_id)
            if row is None:
                raise ValueError("Background job no longer exists.")
            if row.get("state") in {"completed", "failed", "cancelled"}:
                return dict(row)
            if row.get("state") in {"paused", "pause_requested"}:
                return dict(row)
        if manager is None or not _generation_worker_is_alive(manager):
            raise ValueError("This job has no active pause-capable generation worker.")
        manager.pause()
        with self._jobs_lock:
            current = self._jobs.get(job_id)
            if current is None:
                raise ValueError("Background job no longer exists.")
            if (
                current.get("state") in {"completed", "failed", "cancelled", "paused"}
                or self._generators.get(job_id) is not manager
                or not _generation_worker_is_alive(manager)
            ):
                return dict(current)
            return self._job_update(
                job_id,
                state="pause_requested",
                stage="Pause requested",
                message="The current audio chunk/batch will finish and be saved before generation pauses.",
            )

    def _job_resume(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = str(payload.get("job_id") or "")
        with self._jobs_lock:
            manager = self._generators.get(job_id)
            row = self._jobs.get(job_id)
            if row is None:
                raise ValueError("Background job no longer exists.")
            if row.get("state") in {"completed", "failed", "cancelled"}:
                return dict(row)
            if row.get("state") not in {"paused", "pause_requested"}:
                raise ValueError("Only a paused or pause-requested generation job can be resumed.")
        if manager is None or not _generation_worker_is_alive(manager):
            raise ValueError("No live worker can resume this job. Retry from the project to reuse compatible checkpoints.")
        manager.resume()
        with self._jobs_lock:
            current = self._jobs.get(job_id)
            if current is None:
                raise ValueError("Background job no longer exists.")
            if (
                current.get("state") in {"completed", "failed", "cancelled"}
                or self._generators.get(job_id) is not manager
                or not _generation_worker_is_alive(manager)
            ):
                return dict(current)
            return self._job_update(
                job_id, state="running", stage="Resuming generation", message="Resume requested."
            )

    def _job_cancel(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = str(payload.get("job_id") or "")
        with self._jobs_lock:
            manager = self._generators.get(job_id)
            row = self._jobs.get(job_id)
        if manager is None:
            with self._jobs_lock:
                preview_cancel = self._preview_cancel_events.get(job_id)
                import_cancel = self._import_cancel_events.get(job_id)
            if row and row.get("state") in {"completed", "failed", "cancelled"}:
                return dict(row)
            analysis_cancel = self._analysis_cancel_events.get(job_id)
            if row and row.get("type") == "character-analysis" and analysis_cancel is not None and row.get("state") in {"queued", "running", "cancel_requested"}:
                analysis_cancel.set()
                if row.get("state") == "cancel_requested":
                    return dict(row)
                return self._job_update(
                    job_id, state="cancel_requested", stage="Cancellation requested",
                    message="Character analysis will stop at the next safe local-AI inference or chapter boundary; saved cast data will be preserved.",
                )
            if row and preview_cancel is not None and row.get("state") in {"queued", "running", "cancel_requested"}:
                preview_cancel.set()
                return self._job_update(job_id, state="cancel_requested", stage="Cancellation requested",
                                        message="Preview will stop at the next safe synthesis or FFmpeg boundary; partial preview audio will be discarded.")
            with self._jobs_lock:
                import_cancel = self._import_cancel_events.get(job_id)
            if row and row.get("type") == "import" and import_cancel is not None and row.get("state") in {"queued", "running", "cancel_requested"}:
                import_cancel.set()
                return self._job_update(job_id, state="cancel_requested", stage="Cancellation requested",
                                        message="Import will stop at the next safe extraction/chapter boundary; the source file will be preserved.")
            if row and row.get("type") != "audiobook-generation" and row.get("state") == "queued":
                return self._job_update(job_id, state="cancelled", stage="Cancelled", message="Job cancelled before active processing.")
            if row and row.get("type") == "audiobook-generation" and row.get("state") == "queued":
                return self._job_update(job_id, state="cancelled", stage="Cancelled", message="Generation cancelled before a worker started.")
            raise ValueError("Choose an active background job to cancel.")

        with self._jobs_lock:
            current = self._jobs.get(job_id)
            if current is None:
                raise ValueError("Background job no longer exists.")
            if current.get("state") in {"completed", "failed", "cancelled"}:
                return dict(current)
            if current.get("state") == "cancel_requested":
                return dict(current)
            if self._generators.get(job_id) is not manager or not _generation_worker_is_alive(manager):
                return dict(current)
        manager.cancel()
        with self._jobs_lock:
            current = self._jobs.get(job_id)
            if current is None:
                raise ValueError("Background job no longer exists.")
            if (
                current.get("state") in {"completed", "failed", "cancelled"}
                or self._generators.get(job_id) is not manager
                or not _generation_worker_is_alive(manager)
            ):
                return dict(current)
            return self._job_update(
                job_id,
                state="cancel_requested",
                stage="Cancellation requested",
                message="Stopping the provider safely; the current safe checkpoint will be preserved.",
            )

    def _restart_generation_from_job(self, source_row: dict[str, Any], *, recovery: bool = False) -> dict[str, Any]:
        source_job_id = str(source_row.get("job_id") or "").strip()
        project_folder_value = str(source_row.get("project_folder") or "").strip()
        if not source_job_id or not project_folder_value:
            raise ValueError("The original generation job does not contain a saved project reference.")

        requested_path = Path(project_folder_value).expanduser().resolve()
        project = next(
            (item for item in list_projects() if str(item.folder.resolve()) == str(requested_path)),
            None,
        )
        if project is None:
            raise ValueError("The original project is no longer available in the local library.")

        active_states = {"queued", "running", "paused", "pause_requested", "cancel_requested", "retrying"}
        with self._jobs_lock:
            for row in self._jobs.values():
                if (
                    str(row.get("job_id") or "") != source_job_id
                    and str(row.get("type") or "") == "audiobook-generation"
                    and str(row.get("project_folder") or requested_path)
                    and Path(str(row.get("project_folder") or requested_path)).expanduser().resolve() == requested_path
                    and str(row.get("state") or "").casefold() in active_states
                ):
                    raise ValueError("This project already has another active generation job. Finish or cancel it before retrying.")

        project_state = load_state(project.folder)
        owner_job_id = str(project_state.get("generation_job_id") or "").strip()
        if owner_job_id and owner_job_id != source_job_id:
            raise ValueError("A newer generation job now owns this project. The older job cannot be retried over it.")
        if recovery and not bool(project_state.get("generation_recovery_required")):
            raise ValueError("The project is not marked as interrupted/recoverable. Use Retry only for an eligible failed/cancelled generation.")

        result = self._production_generate_book({"_project_folder": str(project.folder)})
        new_job_id = str(result.get("job_id") or "").strip()
        if not new_job_id:
            raise RuntimeError("The generation backend did not return a new job ID.")
        changes = {
            "retry_of_job_id": source_job_id,
            "retry_count": int(source_row.get("retry_count") or 0) + 1,
        }
        if recovery:
            changes["recovery_of_job_id"] = source_job_id
        self._job_update(new_job_id, **changes)
        response = dict(result)
        response["retry_of_job_id"] = source_job_id
        if recovery:
            response["recovery_of_job_id"] = source_job_id
        return response

    def _job_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = str(payload.get("job_id") or "").strip()
        with self._jobs_lock:
            row = dict(self._jobs.get(job_id) or {})
        if not row:
            raise ValueError("The generation job no longer exists.")
        if str(row.get("type") or "") != "audiobook-generation":
            raise ValueError("Only full audiobook generation jobs can be retried here.")
        state = str(row.get("state") or "").casefold()
        if state not in {"failed", "cancelled"}:
            raise ValueError("Retry is available only for a failed or cancelled audiobook generation job.")
        if state == "failed" and not row.get("recoverable"):
            raise ValueError("This failed job is not marked recoverable. Inspect its error before starting another generation.")
        return self._restart_generation_from_job(row, recovery=False)

    def _job_recover(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = str(payload.get("job_id") or "").strip()
        with self._jobs_lock:
            row = dict(self._jobs.get(job_id) or {})
        if not row:
            raise ValueError("The interrupted generation job no longer exists.")
        if str(row.get("type") or "") != "audiobook-generation":
            raise ValueError("Only interrupted full audiobook generation jobs can be recovered here.")
        error = row.get("error") if isinstance(row.get("error"), dict) else {}
        if (
            str(row.get("state") or "").casefold() != "failed"
            or not row.get("recoverable")
            or str(error.get("code") or "").casefold() != "interrupted"
        ):
            raise ValueError("This job is not an interrupted, recoverable generation. Use Retry for an eligible failed/cancelled job.")
        return self._restart_generation_from_job(row, recovery=True)

    def _job_clear_completed(self, _payload: dict[str, Any]) -> dict[str, Any]:
        count = 0
        with self._jobs_lock:
            for row in self._jobs.values():
                if row.get("state") in {"completed", "cancelled"} and not row.get("hidden"):
                    self._record_history_job(row)
                    row["hidden"] = True
                    count += 1
            self._persist_jobs()
        return {"hidden": count, "history_preserved": True}

    def _player_get_active(self, payload: dict[str, Any]) -> dict[str, Any]:
        requested_folder = str(payload.get("folder") or "").strip()
        if requested_folder:
            requested_path = Path(requested_folder).expanduser()
            project = next(
                (item for item in list_projects()
                 if str(item.folder.resolve()) == str(requested_path.resolve())),
                None,
            )
            if project is None:
                raise ValueError("The selected audiobook is no longer available in the local library.")
        else:
            project = self._active_project()

        state = load_state(project.folder)
        output_value = str(state.get("output_path") or "").strip()
        output = Path(output_value).expanduser() if output_value else None
        if not output or not output.is_file() or output.stat().st_size <= 0:
            raise FileNotFoundError("This project does not have a validated generated audiobook yet.")
        summary = self._project_summary(project)
        actual_chapters = _read_audio_chapter_metadata(output)
        playback_path = output
        if is_iso_bmff_file(output):
            try:
                source_stat = output.stat()
                stored_playback = Path(str(state.get("playback_output_path") or "")).expanduser()
                stored_source = str(state.get("playback_source_path") or "")
                stored_size = int(state.get("playback_source_size") or -1)
                stored_mtime = int(state.get("playback_source_mtime_ns") or -1)
                cache_matches = (
                    stored_playback.is_file()
                    and stored_source == str(output.resolve())
                    and stored_size == int(source_stat.st_size)
                    and stored_mtime == int(source_stat.st_mtime_ns)
                )
                if cache_matches:
                    playback_path = stored_playback.resolve()
                else:
                    # Backward compatibility for books created before Stage 5.5:
                    # prepare a playback copy from the authoritative M4B and
                    # persist its source identity for subsequent opens.
                    playback_path = prepare_audiobook_playback_source(output)
                    state["playback_output_path"] = str(playback_path.resolve())
                    state["playback_source_path"] = str(output.resolve())
                    state["playback_source_size"] = int(source_stat.st_size)
                    state["playback_source_mtime_ns"] = int(source_stat.st_mtime_ns)
                    state["playback_error"] = None
                    save_state(project.folder, state)
            except Exception as exc:
                message = (
                    "The finished M4B is safe in the library, but a browser-compatible "
                    f"playback copy could not be prepared: {exc}"
                )
                log.exception("Could not prepare playback for audiobook %s", output)
                raise RuntimeError(message) from exc
        chapters = actual_chapters or [
            {"number": c.number, "title": c.title}
            for c in project.chapters
        ]
        try:
            playback_position = float(state.get("playback_position_seconds") or 0)
        except (TypeError, ValueError, OverflowError):
            playback_position = 0.0
        if not math.isfinite(playback_position) or playback_position < 0:
            playback_position = 0.0
        # QSettings may be updated by a queued UI preference save immediately
        # before this read. Sync before reading so the player response confirms
        # the persisted store rather than a stale in-memory snapshot.
        self.settings.sync()
        try:
            playback_rate = float(self.settings.value("player/playback_rate", 1.0))
        except (TypeError, ValueError, OverflowError):
            playback_rate = 1.0
        if not math.isfinite(playback_rate) or not 0.5 <= playback_rate <= 2.0:
            playback_rate = 1.0
        try:
            playback_volume = float(self.settings.value("player/playback_volume", 0.8))
        except (TypeError, ValueError, OverflowError):
            playback_volume = 0.8
        if not math.isfinite(playback_volume) or not 0.0 <= playback_volume <= 1.0:
            playback_volume = 0.8
        return {
            **summary,
            "title": project.title,
            "author": str(state.get("author") or ""),
            "narrator": str(state.get("narrator") or state.get("voice_profile") or ""),
            "output_path": str(output.resolve()),
            "source_file_url": output.resolve().as_uri(),
            "file_url": playback_path.resolve().as_uri(),
            "playback_output_path": str(playback_path.resolve()),
            "playback_format": playback_path.suffix.lower().lstrip("."),
            "chapters": chapters,
            "format": output.suffix.lower(),
            "file_size": output.stat().st_size,
            "playback_position_seconds": playback_position,
            "playback_rate": playback_rate,
            "playback_volume": playback_volume,
        }

    def _player_position_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Remember listening position inside the selected project's local state."""
        folder_value = str(payload.get("folder") or "").strip()
        if not folder_value:
            raise ValueError("Select an audiobook before saving playback position.")
        requested_folder = Path(folder_value).expanduser().resolve()
        project = next(
            (item for item in list_projects()
             if str(item.folder.resolve()) == str(requested_folder)),
            None,
        )
        if project is None:
            raise ValueError("The selected audiobook is no longer available in the local library.")
        raw_position = payload.get("position_seconds", 0)
        if isinstance(raw_position, bool):
            raise ValueError("Playback position must be a non-negative number.")
        try:
            position = float(raw_position)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Playback position must be a non-negative number.") from exc
        if not math.isfinite(position) or position < 0 or position > 7 * 24 * 60 * 60:
            raise ValueError("Playback position is outside the supported range.")
        state = load_state(project.folder)
        state["playback_position_seconds"] = round(position, 2)
        # Listening progress must not reorder Recent Projects or masquerade as a content edit.
        save_state(project.folder, state)
        return {"saved": True, "folder": str(project.folder.resolve()),
                "position_seconds": state["playback_position_seconds"]}

    def _settings_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {"theme": "ui/theme", "accent": "ui/accent", "interface_scale": "ui/interface_scale",
                   "text_scale": "ui/text_scale", "window_size": "ui/window_size",
                   "effects": "ui/effects", "reduce_motion": "ui/reduce_motion",
                   "preview_seconds": "audio/preview_seconds", "bitrate": "production/bitrate",
                   "concurrency": "production/concurrency", "qwen_backend": "qwen/backend_preference",
                   "qwen_low_memory": "qwen/low_memory_mode", "local_first": "privacy/local_first",
                   "output_folder": "paths/output_folder",
                   "player_rate": "player/playback_rate",
                   "player_volume": "player/playback_volume"}
        for key, setting in allowed.items():
            if key not in payload:
                continue
            value = payload[key]
            if key == "theme" and value not in {"dark", "light"}:
                raise ValueError("Theme must be dark or light.")
            if key == "reduce_motion" and not isinstance(value, bool):
                raise ValueError("Reduce motion must be a boolean preference.")
            if key == "text_scale":
                try:
                    value = int(value)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("UI text size must be one of the supported percentages.") from exc
                if value not in {85, 90, 100, 110, 120, 130, 140}:
                    raise ValueError("UI text size must be 85, 90, 100, 110, 120, 130, or 140 percent.")
            if key == "window_size" and str(value) not in {
                "auto", "1280x720", "1440x900", "1600x900", "1920x1080", "maximized"
            }:
                raise ValueError("Choose a supported window size in Settings.")
            if key == "preview_seconds":
                try:
                    value = int(value)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("Preview duration must be 10, 30, 60, or 90 seconds.") from exc
                if value not in {10, 30, 60, 90}:
                    raise ValueError("Preview duration must be 10, 30, 60, or 90 seconds.")
            if key == "bitrate" and not 128 <= int(value) <= 320:
                raise ValueError("Bitrate must be from 128 to 320 kbps.")
            if key == "concurrency":
                try:
                    value = int(value)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("Maximum concurrent generation jobs must be 1, 2, or 3.") from exc
                if value not in {1, 2, 3}:
                    raise ValueError("Maximum concurrent generation jobs must be 1, 2, or 3.")
                if bool(payload.get("qwen_low_memory", self.settings.value("qwen/low_memory_mode", False, type=bool))):
                    value = 1
            if key == "qwen_backend":
                value = str(value or "automatic").strip().casefold()
                if value not in {"automatic", "cpu", "cuda", "rocm", "xpu"}:
                    raise ValueError("Choose Automatic, CPU, NVIDIA CUDA, AMD ROCm, or Intel XPU.")
                if value in {"cuda", "rocm", "xpu"}:
                    from app.tts.qwen_accelerator import detect_accelerators
                    active = detect_accelerators(refresh=True)
                    if not any(item.backend == value and item.supported for item in active):
                        raise ValueError(f"The {value.upper()} backend is not currently validated on this device.")
            if key == "qwen_low_memory" and not isinstance(value, bool):
                raise ValueError("Low-memory mode must be enabled or disabled.")
            if key == "player_rate":
                try:
                    value = float(value)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("Playback speed must be between 0.5× and 2.0×.") from exc
                if not math.isfinite(value) or not 0.5 <= value <= 2.0:
                    raise ValueError("Playback speed must be between 0.5× and 2.0×.")
            if key == "player_volume":
                try:
                    value = float(value)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("Player volume must be between 0 and 100 percent.") from exc
                if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                    raise ValueError("Player volume must be between 0 and 100 percent.")
            if key == "output_folder":
                folder = Path(str(value)).expanduser().resolve()
                folder.mkdir(parents=True, exist_ok=True)
                value = str(folder)
            self.settings.setValue(setting, value)
        self.settings.sync()
        if "window_size" in payload:
            window = self.parent()
            apply_size = getattr(window, "apply_window_size", None)
            if callable(apply_size):
                apply_size(str(payload["window_size"]))
        return self._settings_get({})

    def _generation_concurrency_limit(self) -> int:
        """Return the enforced heavy-generation cap; low-memory mode is always serial."""
        try:
            if bool(self.settings.value("qwen/low_memory_mode", False, type=bool)):
                return 1
            configured = int(self.settings.value("production/concurrency", 1) or 1)
        except (TypeError, ValueError, OverflowError):
            configured = 1
        return max(1, min(3, configured))

    def _assert_no_active_model_lifecycle(self, activity: str) -> None:
        """Prevent synthesis/analysis from opening a runtime while files are being changed."""
        with self._jobs_lock:
            active = [
                job for job in self._jobs.values()
                if str(job.get("state") or "").casefold() in {"queued", "running"}
                and str(job.get("type") or "").casefold().startswith("model-")
            ]
        if active:
            raise RuntimeError(
                f"Cannot {activity} while a model install, repair or uninstall is running. "
                "Let the model operation finish, then retry."
            )

    def _invalidate_catalog_scan(self, kind: str) -> None:
        """Mark one catalogue dirty without discarding its last-known-good snapshot."""
        if kind not in {"models", "sound"}:
            raise ValueError(f"Unsupported catalogue kind: {kind}")
        with self._catalog_scan_lock:
            self._catalog_scan_generation[kind] = int(self._catalog_scan_generation.get(kind, 0)) + 1
            if kind == "models":
                self._model_inventory_cache_ready = False
            else:
                self._sound_catalog_cache_ready = False

    def _build_model_inventory(self) -> list[dict[str, Any]]:
        """Perform the expensive authoritative model/filesystem scan; call from a worker."""
        from app.tts.model_registry import build_inventory
        return list(build_inventory())

    def _refresh_model_inventory_sync(self) -> list[dict[str, Any]]:
        """Publish a model inventory built by an existing background lifecycle worker."""
        rows = self._build_model_inventory()
        with self._catalog_cache_lock:
            self._model_inventory_cache = rows
            self._model_inventory_cache_at = time.monotonic()
            self._model_inventory_cache_ready = True
        return list(rows)

    def _queue_catalog_scan(self, kind: str) -> str:
        """Queue one durable single-flight scan while preserving the last good snapshot."""
        if kind not in {"models", "sound"}:
            raise ValueError(f"Unsupported catalogue kind: {kind}")
        labels = {
            "models": ("catalog-scan-models", "Refresh installed model inventory",
                       "Inspect local model weights, runtimes, providers and storage."),
            "sound": ("catalog-scan-sound", "Refresh Sound Design library",
                      "Inspect imported and bundled audio assets and their metadata."),
        }
        job_type, title, description = labels[kind]
        with self._catalog_scan_lock:
            current_id = self._catalog_scan_jobs.get(kind)
            if current_id:
                with self._jobs_lock:
                    current = self._jobs.get(current_id)
                if current and str(current.get("state") or "").casefold() in {"queued", "running"}:
                    return current_id
                self._catalog_scan_jobs.pop(kind, None)

            job_id = self._new_job(job_type, title, description)
            self._catalog_scan_jobs[kind] = job_id
            self._job_update(
                job_id, state="running", started_at=self._now(), progress=5,
                stage="Preparing background scan",
                message="The application remains usable while the local catalogue is scanned.",
            )

        def worker() -> None:
            try:
                while True:
                    with self._catalog_scan_lock:
                        generation = int(self._catalog_scan_generation.get(kind, 0))
                    self._job_update(
                        job_id, state="running", progress=15,
                        stage=("Scanning installed models and runtimes" if kind == "models"
                               else "Scanning local and bundled audio assets"),
                        message="Filesystem enumeration is running in a background worker.",
                    )
                    rows = (
                        self._build_model_inventory() if kind == "models"
                        else self._build_sound_catalog()
                    )
                    with self._catalog_scan_lock:
                        if int(self._catalog_scan_generation.get(kind, 0)) != generation:
                            self._job_update(
                                job_id, state="running", progress=80,
                                stage="Source changed · rescanning",
                                message="Files changed during the scan; reconciling against the latest filesystem state.",
                            )
                            continue
                        with self._catalog_cache_lock:
                            if kind == "models":
                                self._model_inventory_cache = rows
                                self._model_inventory_cache_at = time.monotonic()
                                self._model_inventory_cache_ready = True
                            else:
                                self._sound_catalog_cache = rows
                                self._sound_catalog_cache_at = time.monotonic()
                                self._sound_catalog_cache_ready = True
                    self._job_update(
                        job_id, state="completed", progress=100,
                        stage="Catalogue refreshed",
                        message=f"Verified {len(rows)} catalogue entries.",
                        result={"catalogue": kind, "entry_count": len(rows)},
                        error=None, recoverable=False,
                    )
                    break
            except Exception as exc:
                log.exception("Background %s catalogue scan failed", kind)
                self._job_update(
                    job_id, state="failed", progress=100,
                    stage="Catalogue refresh failed",
                    message="The previous catalogue snapshot was preserved.",
                    error={"code": kind + "_catalogue_scan_failed", "message": str(exc)},
                    recoverable=True,
                )
            finally:
                with self._catalog_scan_lock:
                    if self._catalog_scan_jobs.get(kind) == job_id:
                        self._catalog_scan_jobs.pop(kind, None)

        try:
            threading.Thread(
                target=worker, daemon=True,
                name="RyuModelInventoryScan" if kind == "models" else "RyuSoundCatalogueScan",
            ).start()
        except Exception as exc:
            with self._catalog_scan_lock:
                if self._catalog_scan_jobs.get(kind) == job_id:
                    self._catalog_scan_jobs.pop(kind, None)
            self._job_update(
                job_id, state="failed", stage="Could not start catalogue scan",
                message="The previous catalogue snapshot was preserved.",
                error={"code": kind + "_catalogue_scan_start_failed", "message": str(exc)},
                recoverable=True,
            )
        return job_id

    def _models_list(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the last-known inventory immediately and refresh stale data off-thread."""
        cached = getattr(self, "_model_inventory_cache", None)
        scanned_at = float(getattr(self, "_model_inventory_cache_at", 0.0) or 0.0)
        ready = bool(getattr(self, "_model_inventory_cache_ready", False))
        force_refresh = bool((payload or {}).get("force_refresh"))
        if force_refresh or not ready or time.monotonic() - scanned_at >= 5.0:
            try:
                self._queue_catalog_scan("models")
            except RuntimeError as exc:
                log.warning("Model inventory refresh deferred: %s", exc)
        return list(cached) if isinstance(cached, list) else []

    def _models_refresh(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Explicit Refresh Status action; the scan itself never runs on the Qt thread."""
        job_id = self._queue_catalog_scan("models")
        return {"job_id": job_id, "state": "running", "catalogue": "models"}

    def _models_files(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return paginated actual file metadata for one inventory component."""
        from app.tts.model_registry import component_file_inventory

        return component_file_inventory(
            str(payload.get("model_id") or ""),
            offset=payload.get("offset", 0),
            limit=payload.get("limit", 250),
        )

    def _models_open_folder(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Open the exact model or runtime directory reported by the registry."""
        from app.tts.model_registry import component_paths

        model_id = str(payload.get("model_id") or "").strip()
        location = str(payload.get("location") or "model").strip().casefold()
        paths = component_paths(model_id)
        path_keys = {
            "model": "model_path",
            "runtime": "runtime_path",
            "python": "python_path",
            "runtime_executable": "runtime_executable",
        }
        path_key = path_keys.get(location)
        if not path_key:
            raise ValueError(f"Unsupported model location: {location}")
        raw = paths.get(path_key)
        if not raw and location in {"model", "runtime"}:
            raw = paths.get("model_path") or paths.get("runtime_path")
        if not raw:
            raise FileNotFoundError(f"No local {location} path is registered for {model_id}.")
        path = Path(str(raw)).expanduser()
        folder = path if path.is_dir() else path.parent
        if not folder.is_dir():
            raise FileNotFoundError(f"The registered model location is not currently accessible: {path}")
        resolved = folder.resolve()
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved))):
            raise RuntimeError("Windows did not open the selected model folder.")
        return {"opened": True, "model_id": model_id, "location": location, "path": str(resolved)}

    def _models_copy_path(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Copy the exact registered model/runtime path using the desktop clipboard."""
        from app.tts.model_registry import component_paths

        model_id = str(payload.get("model_id") or "").strip()
        location = str(payload.get("location") or "model").strip().casefold()
        paths = component_paths(model_id)
        path_keys = {
            "model": "model_path",
            "runtime": "runtime_path",
            "python": "python_path",
            "runtime_executable": "runtime_executable",
        }
        path_key = path_keys.get(location)
        if not path_key:
            raise ValueError(f"Unsupported model location: {location}")
        raw = paths.get(path_key)
        if not raw and location in {"model", "runtime"}:
            raw = paths.get("model_path") or paths.get("runtime_path")
        if not raw:
            raise FileNotFoundError(f"No local path is registered for {model_id} ({location}).")
        value = str(Path(str(raw)).expanduser())
        QApplication.clipboard().setText(value)
        return {"copied": True, "model_id": model_id, "location": location, "path": value}

    def _models_start_operation(self, action: str, model_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run potentially large model lifecycle work as a durable, cancellable-visible background job."""
        details = dict(payload or {})
        label = str(details.get("voice_name") or model_id)
        verb = {"install": "Install", "repair": "Repair", "uninstall": "Uninstall"}.get(action, action.title())
        with self._jobs_lock:
            active = [
                job for job in self._jobs.values()
                if str(job.get("state") or "").casefold() in {"queued", "running"}
            ]
        active_model_jobs = [job for job in active if str(job.get("type") or "").casefold().startswith("model-")]
        if active_model_jobs:
            raise RuntimeError("Another model installation, repair, or uninstall is already running. Let it finish before starting a second model operation.")
        active_audio_jobs = [
            job for job in active
            if any(token in str(job.get("type") or "").casefold()
                   for token in ("preview", "production", "generation", "character-analysis", "character-analyze", "import"))
        ]
        if active_audio_jobs:
            raise RuntimeError("A preview, import, analysis, or audiobook generation job is active. Stop or finish it before changing installed model files.")
        job_id = self._new_job(
            "model-" + action, f"{verb} {label}",
            f"{verb} app-managed model/runtime component {model_id}",
        )
        self._job_update(job_id, state="running", started_at=self._now(), progress=1,
                         stage=f"Preparing to {action} {label}", message=f"{verb} started.")
        def report_progress(detail: str) -> None:
            value = str(detail or f"{verb} in progress")
            match = re.search(r"(?<!\d)(\d{1,3})%", value)
            changes: dict[str, Any] = {"state": "running", "stage": value, "message": value}
            if match:
                changes["progress"] = min(98, max(1, int(match.group(1))))
            self._job_update(job_id, **changes)
        def worker() -> None:
            try:
                if action == "uninstall":
                    details["_operation_job_id"] = job_id
                    outcome = self._models_uninstall_component(model_id, details, report_progress)
                else:
                    outcome = self._models_install_component(model_id, details, report_progress, force_repair=action == "repair")
                report_progress("Refreshing actual installed state…")
                self._invalidate_catalog_scan("models")
                latest = self._refresh_model_inventory_sync()
                self._job_update(job_id, state="completed", progress=100,
                                 stage=f"{verb} complete", message=str(outcome or f"{verb} completed."),
                                 result={"action": action, "model_id": model_id, "detail": str(outcome or ""),
                                         "models": latest}, error=None, recoverable=False)
            except Exception as exc:
                log.exception("Premium V2 model %s failed for %s", action, model_id)
                self._job_update(job_id, state="failed", stage=f"{verb} failed",
                                 message=f"{verb} failed for {label}.",
                                 error={"code": "model_" + action + "_failed", "message": str(exc)},
                                 recoverable=True)
        threading.Thread(target=worker, daemon=True, name="RyuPremiumModelLifecycle").start()
        return {"job_id": job_id, "model_id": model_id, "action": action, "state": "running"}

    def _models_install(self, payload: dict[str, Any]) -> dict[str, Any]:
        selection = str(payload.get("selection") or "").strip().casefold()
        model_id = str(payload.get("model_id") or "").strip().casefold()
        if not model_id:
            legacy = {
                "customvoice": "qwen-customvoice",
                "voicedesign": "qwen-voicedesign",
                "voiceclone": "qwen-clone",
                "all": "qwen-all",
            }
            model_id = legacy.get(selection, "")
        allowed = {"piper", "kokoro", "chatterbox", "chatterbox-multilingual", "chatterbox-runtime",
                   "qwen-runtime", "qwen-customvoice", "qwen-voicedesign", "qwen-clone", "qwen-all",
                   "custom-0.6b", "custom-1.7b", "design-1.7b", "base-0.6b", "base-1.7b", "audiobook-ai"}
        if model_id not in allowed:
            raise ValueError("Choose a supported local model/runtime. Windows SAPI, Edge TTS and ElevenLabs are system/online providers, not locally installed models.")
        return self._models_start_operation("install", model_id, payload)

    def _models_repair(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_id = str(payload.get("model_id") or "").strip().casefold()
        allowed = {"piper", "kokoro", "chatterbox", "chatterbox-multilingual", "chatterbox-runtime",
                   "qwen-runtime", "qwen-customvoice", "qwen-voicedesign", "qwen-clone",
                   "custom-0.6b", "custom-1.7b", "design-1.7b", "base-0.6b", "base-1.7b", "audiobook-ai"}
        if model_id not in allowed:
            raise ValueError("Choose a supported app-managed model/runtime to repair.")
        return self._models_start_operation("repair", model_id, payload)

    def _models_uninstall(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_id = str(payload.get("model_id") or "").strip().casefold()
        allowed = {"piper", "kokoro", "chatterbox", "chatterbox-multilingual", "chatterbox-runtime", "chatterbox-model-assets",
                   "qwen-runtime", "qwen-model", "audiobook-ai",
                   "custom-0.6b", "custom-1.7b", "design-1.7b", "base-0.6b", "base-1.7b"}
        if model_id not in allowed:
            raise ValueError("Choose a supported app-managed model/runtime to uninstall.")
        return self._models_start_operation("uninstall", model_id, payload)

    @staticmethod
    def _models_remove_path(target: Path, allowed_root: Path) -> None:
        root = Path(allowed_root).resolve()
        candidate = Path(target).resolve()
        if candidate == root or root not in candidate.parents:
            raise RuntimeError(f"Refusing to remove a path outside the selected component root: {target}")
        if candidate.is_dir():
            shutil.rmtree(candidate)
        elif candidate.exists():
            candidate.unlink()

    def _models_install_component(self, model_id: str, payload: dict[str, Any], progress, force_repair: bool = False) -> str:
        from app.core.paths import models_root
        from app.tts.model_registry import mark_installed
        root = models_root()
        model_id = model_id.casefold()

        def report(text: str) -> None:
            if progress:
                progress(text)

        if model_id == "piper":
            import json
            import ssl
            import urllib.request
            from app.tts.providers.piper import PiperProvider
            voice_name = str(payload.get("voice_name") or "en_US-lessac-medium").strip()
            parsed_voice = re.fullmatch(
                r"(?P<locale>[a-z]{2,3}_[A-Z]{2})-(?P<speaker>[A-Za-z0-9][A-Za-z0-9_-]*)-(?P<quality>x_low|x_high|low|medium|high)",
                voice_name,
            )
            if not parsed_voice:
                raise ValueError("Use a valid Piper voice ID such as en_US-lessac-medium.")
            target_root = (root / "piper").resolve()
            target_root.mkdir(parents=True, exist_ok=True)
            existing_local = next((
                item.resolve() for item in PiperProvider.model_paths()
                if item.stem.casefold() == voice_name.casefold()
                and target_root in item.resolve().parents
                and item.suffix.casefold() == ".onnx"
            ), None)
            if existing_local and not force_repair:
                sidecar = existing_local.with_suffix(existing_local.suffix + ".json")
                if sidecar.is_file() and existing_local.stat().st_size > 1024:
                    return f"Piper voice {voice_name} is already installed locally."
            locale = parsed_voice.group("locale")
            family = locale.split("_", 1)[0].lower()
            speaker = parsed_voice.group("speaker")
            quality = parsed_voice.group("quality")
            base_url = (
                "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
                f"{family}/{locale}/{speaker}/{quality}/{voice_name}"
            )
            file_specs = (
                (base_url + ".onnx?download=true", target_root / (voice_name + ".onnx"), 1024, "Piper voice model"),
                (base_url + ".onnx.json?download=true", target_root / (voice_name + ".onnx.json"), 100, "Piper voice configuration"),
            )
            try:
                import certifi
                context = ssl.create_default_context(cafile=certifi.where())
            except Exception:
                context = ssl.create_default_context()
            token = uuid.uuid4().hex
            staged: list[tuple[Path, Path]] = []
            backups: list[tuple[Path, Path]] = []
            backup_root = root / (".piper-repair-backup-" + token)
            operation_published = False
            try:
                for url, target, minimum, label in file_specs:
                    temporary = target.with_name(target.name + "." + token + ".part")
                    request = urllib.request.Request(
                        url,
                        headers={"User-Agent": "Ryu-Audiobook/1.1", "Accept": "application/octet-stream"},
                    )
                    report(f"Downloading {label} for {voice_name}…")
                    try:
                        with urllib.request.urlopen(request, timeout=120, context=context) as response, temporary.open("wb") as handle:
                            total = int(response.headers.get("Content-Length", "0") or 0)
                            received = 0
                            while True:
                                chunk = response.read(1024 * 1024)
                                if not chunk:
                                    break
                                handle.write(chunk)
                                received += len(chunk)
                                if total:
                                    report(f"Downloading {label} for {voice_name}… {min(99, received * 100 // total)}%")
                        if not temporary.is_file() or temporary.stat().st_size < minimum:
                            raise RuntimeError(f"{label} download is incomplete.")
                        if target.name.endswith(".onnx.json"):
                            try:
                                metadata = json.loads(temporary.read_text(encoding="utf-8"))
                            except (OSError, ValueError, TypeError) as exc:
                                raise RuntimeError("Piper voice configuration is not valid JSON.") from exc
                            if not isinstance(metadata, dict) or not metadata:
                                raise RuntimeError("Piper voice configuration is empty or invalid.")
                        staged.append((temporary, target))
                    except Exception:
                        temporary.unlink(missing_ok=True)
                        raise

                # Keep the last known-good pair until both new files have downloaded
                # and validated. The backup is outside Models/piper, so the voice
                # discovery scan cannot accidentally select the backup during repair.
                if existing_local:
                    backup_root.mkdir(parents=True, exist_ok=True)
                    try:
                        for source in (existing_local, existing_local.with_suffix(existing_local.suffix + ".json")):
                            if source.is_file():
                                backup = backup_root / source.name
                                shutil.move(str(source), str(backup))
                                backups.append((backup, source))
                    except Exception:
                        # Restore any piece already moved if preparing the backup pair fails.
                        for backup, original in reversed(backups):
                            if backup.exists():
                                original.parent.mkdir(parents=True, exist_ok=True)
                                shutil.move(str(backup), str(original))
                        raise
                try:
                    for temporary, target in staged:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        temporary.replace(target)
                except Exception:
                    for _temporary, target in staged:
                        target.unlink(missing_ok=True)
                    for backup, original in reversed(backups):
                        if backup.exists():
                            original.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(backup), str(original))
                    raise

                installed = next((
                    item.resolve() for item in PiperProvider.model_paths()
                    if item.stem.casefold() == voice_name.casefold()
                    and target_root in item.resolve().parents
                    and item.suffix.casefold() == ".onnx"
                ), None)
                metadata_path = target_root / (voice_name + ".onnx.json")
                if installed is None or not installed.is_file() or installed.stat().st_size < 1024 or not metadata_path.is_file():
                    for _temporary, target in staged:
                        target.unlink(missing_ok=True)
                    for backup, original in reversed(backups):
                        if backup.exists():
                            original.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(backup), str(original))
                    raise RuntimeError("Piper model download finished, but its local ONNX/config pair did not pass verification.")
                mark_installed("piper", True)
                operation_published = True
                report(f"Piper voice {voice_name} installed and verified.")
                return f"Piper voice {voice_name} is installed and verified."
            finally:
                for temporary, _target in staged:
                    temporary.unlink(missing_ok=True)
                # If restoring a backup itself failed, leave the backup directory
                # in place rather than destroying the user's last known-good model.
                if operation_published or not any(backup.exists() for backup, _original in backups):
                    shutil.rmtree(backup_root, ignore_errors=True)

        if model_id == "kokoro":
            import ssl
            import urllib.request
            try:
                import certifi
                context = ssl.create_default_context(cafile=certifi.where())
            except Exception:
                context = ssl.create_default_context()
            target_root = root / "kokoro"
            target_root.mkdir(parents=True, exist_ok=True)
            assets = (
                ("https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx",
                 target_root / "kokoro-v1.0.onnx", "Kokoro ONNX model", 200 * 1024 * 1024),
                ("https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin",
                 target_root / "voices-v1.0.bin", "Kokoro voice pack", 10 * 1024 * 1024),
            )
            for url, target, label, minimum in assets:
                if force_repair or not target.is_file() or target.stat().st_size < minimum:
                    temporary = target.with_suffix(target.suffix + ".part")
                    try:
                        report(f"Downloading {label}…")
                        request = urllib.request.Request(url, headers={"User-Agent": "Ryu-Audiobook/1.1", "Accept": "application/octet-stream"})
                        with urllib.request.urlopen(request, timeout=90, context=context) as response, temporary.open("wb") as handle:
                            total = int(response.headers.get("Content-Length", "0") or 0)
                            received = 0
                            while True:
                                part = response.read(1024 * 1024)
                                if not part:
                                    break
                                handle.write(part)
                                received += len(part)
                                if total:
                                    report(f"Downloading {label}… {min(99, received * 100 // total)}%")
                        if not temporary.is_file() or temporary.stat().st_size < minimum:
                            raise RuntimeError(f"{label} download is incomplete.")
                        temporary.replace(target)
                    finally:
                        temporary.unlink(missing_ok=True)
            from app.tts.providers.kokoro import KokoroProvider
            if not KokoroProvider.assets_available():
                raise RuntimeError("Kokoro files were downloaded, but the runtime could not verify the model and voice pack.")
            mark_installed("kokoro", True)
            return "Kokoro model and voice pack installed and verified."

        if model_id in {"chatterbox", "chatterbox-multilingual", "chatterbox-runtime"}:
            from app.tts.chatterbox_runtime import RUNTIME_DIR, MARKER, install_runtime
            if force_repair:
                MARKER.unlink(missing_ok=True)
            report("Installing or verifying the isolated Chatterbox runtime…")
            install_runtime(progress)
            if not RUNTIME_DIR.exists() or not MARKER.is_file():
                raise RuntimeError("Chatterbox runtime did not pass its installation marker check.")
            mark_installed("chatterbox", True)
            mark_installed("chatterbox-multilingual", True)
            return "Chatterbox runtime is ready. Provider model weights are downloaded on first use."

        if model_id == "qwen-runtime":
            from app.tts.qwen_character_runtime import install_runtime
            install_runtime(progress, force_repair=force_repair)
            return "Qwen3-TTS runtime repaired and verified." if force_repair else "Qwen3-TTS runtime installed and verified."

        if model_id in {"qwen-customvoice", "qwen-voicedesign", "qwen-clone", "qwen-all"}:
            from app.tts.qwen_character_runtime import (
                install_runtime, install_model, model_installed,
                best_custom_kind, best_clone_kind, best_voice_design_kind,
            )
            install_runtime(progress, force_repair=force_repair and model_id == "qwen-all")
            choices = {
                "qwen-customvoice": [best_custom_kind()],
                # A VoiceDesign reference must also have a Base model available
                # for stable identity across long chapters.
                "qwen-voicedesign": [best_voice_design_kind(), best_clone_kind()],
                "qwen-clone": [best_clone_kind()],
            }
            targets = []
            if model_id == "qwen-all":
                for kind in (best_custom_kind(), best_voice_design_kind(), best_clone_kind()):
                    if kind not in targets:
                        targets.append(kind)
            else:
                targets = choices[model_id]
            missing = [kind for kind in targets if not model_installed(kind)]
            # If a composite feature is incomplete, install only its missing
            # models. A deliberate repair of a fully present feature forces the
            # existing weights to be downloaded and verified again.
            install_targets = targets if force_repair and not missing else missing
            if not install_targets:
                return "Required Qwen3-TTS runtime and model files are already installed: " + ", ".join(targets)
            for kind in install_targets:
                install_model(kind, progress, force_repair=force_repair and not missing)
            return "Qwen3-TTS model(s) installed and file-verified: " + ", ".join(install_targets)

        qwen_model_match = re.fullmatch(r"(?:qwen-model:)?(custom-0\.6b|custom-1\.7b|design-1\.7b|base-0\.6b|base-1\.7b)", model_id)
        if qwen_model_match:
            from app.tts.qwen_character_runtime import install_model
            install_model(qwen_model_match.group(1), progress, force_repair=force_repair)
            return f"Qwen model {qwen_model_match.group(1)} installed and file-verified."

        if model_id == "audiobook-ai":
            from app.ai.model_runtime import install_runtime, self_test
            if not force_repair:
                install_runtime(progress)
                report("Running a real Audiobook AI inference self-test…")
                detail = self_test()
                return "Audiobook AI is installed and self-tested: " + detail

            # A repair uses a sibling backup so an interrupted repair can restore
            # the previous known-good runtime/model files.
            target = root / "audiobook-ai"
            backup = root / (".audiobook-ai-repair-" + uuid.uuid4().hex)
            if target.exists():
                target.rename(backup)
            try:
                install_runtime(progress)
                report("Running a real Audiobook AI inference self-test…")
                detail = self_test()
            except Exception:
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                if backup.exists():
                    backup.rename(target)
                raise
            else:
                shutil.rmtree(backup, ignore_errors=True)
                return "Audiobook AI repaired and self-tested: " + detail

        raise ValueError(f"No installer is registered for component: {model_id}")

    def _models_uninstall_component(self, model_id: str, payload: dict[str, Any], progress) -> str:
        from app.core.paths import models_root
        from app.tts.model_registry import mark_installed
        root = models_root().resolve()
        requested = model_id.casefold()

        with self._jobs_lock:
            blocking = [
                (job_id, job) for job_id, job in self._jobs.items()
                if job_id != str(payload.get("_operation_job_id") or "")
                and str(job.get("state") or "").casefold() in {"queued", "running"}
            ]
        if blocking:
            labels = ", ".join(
                str(job.get("title") or job.get("type") or job_id)
                for job_id, job in blocking[:5]
            )
            raise RuntimeError(
                "Uninstall is blocked while application work is active. Finish or cancel these jobs first: "
                + labels
            )

        def report(text: str) -> None:
            if progress:
                progress(text)

        if requested == "piper":
            from app.tts.providers.piper import PiperProvider
            voice_name = str(payload.get("voice_name") or "").strip()
            if not voice_name:
                raise ValueError("Choose the exact user-installed Piper voice to uninstall.")
            piper_root = (root / "piper").resolve()
            voice = next((item.resolve() for item in PiperProvider.model_paths()
                          if item.stem.casefold() == voice_name.casefold()
                          and piper_root in item.resolve().parents), None)
            if voice is None or voice.suffix.casefold() != ".onnx":
                raise ValueError("That Piper voice is not a user-installed removable model.")
            report(f"Removing Piper voice {voice.stem}…")
            self._models_remove_path(voice, piper_root)
            sidecar = voice.with_suffix(voice.suffix + ".json")
            if sidecar.exists():
                self._models_remove_path(sidecar, piper_root)
            mark_installed("piper", bool(piper_root.exists() and any(piper_root.rglob("*.onnx"))))
            return f"Removed Piper voice model {voice.stem}; other voice models and profiles were kept."

        if requested == "kokoro":
            target = root / "kokoro"
            if not target.is_dir() or not any(p.is_file() for p in target.rglob("*")):
                raise ValueError("There are no user-installed Kokoro files to remove.")
            report("Removing user-installed Kokoro model and voice pack…")
            self._models_remove_path(target, root)
            mark_installed("kokoro", False)
            return "Removed the user-installed Kokoro model and voice pack. Bundled files are untouched."

        if requested == "chatterbox-model-assets":
            from app.tts.model_registry import _chatterbox_cache_root
            cache_root = _chatterbox_cache_root(root).resolve()
            cached_models = [
                path for path in cache_root.glob("models--*")
                if path.is_dir() and "chatterbox" in path.name.casefold()
            ] if cache_root.is_dir() else []
            if not cached_models:
                raise ValueError("No downloaded Chatterbox model assets were found in the configured Model Cache.")
            report("Removing only Chatterbox-owned Hugging Face model cache folders…")
            for target in cached_models:
                self._models_remove_path(target, cache_root)
            return f"Removed {len(cached_models)} Chatterbox model cache folder(s). Other provider caches, the Chatterbox runtime, projects and saved profiles were kept."

        if requested in {"chatterbox", "chatterbox-multilingual", "chatterbox-runtime"}:
            from app.tts.chatterbox_runtime import RUNTIME_DIR
            # Chatterbox runtime belongs to the independently configured Provider Runtime root.
            provider_runtime_root = runtimes_root().resolve()
            if RUNTIME_DIR.exists():
                report("Removing the shared Chatterbox runtime…")
                self._models_remove_path(RUNTIME_DIR, provider_runtime_root)
            mark_installed("chatterbox", False)
            mark_installed("chatterbox-multilingual", False)
            return "Removed the shared Chatterbox runtime. Saved profiles and books were kept."

        if requested == "qwen-model" or requested in {"custom-0.6b", "custom-1.7b", "design-1.7b", "base-0.6b", "base-1.7b"}:
            from app.tts.qwen_character_runtime import MODEL_DIRS
            # Qwen weights are stored under Models; only the Python environment
            # belongs to Provider Runtime. Keep the two deletion roots distinct.
            model_component_root = (models_root() / "qwen3-tts").resolve()
            kind = str(payload.get("model_kind") or requested).strip().casefold()
            if kind not in MODEL_DIRS:
                raise ValueError("Choose the exact installed Qwen model to uninstall.")
            target = MODEL_DIRS[kind]
            if not target.exists():
                raise ValueError(f"Qwen model {kind} is not installed.")
            report(f"Removing Qwen model {kind}…")
            self._models_remove_path(target, model_component_root)
            return f"Removed Qwen model {kind}. The Qwen runtime, other model folders and saved voice profiles were kept."

        if requested == "qwen-runtime":
            from app.tts.qwen_character_runtime import (
                RUNTIME_ROOT, VENV_ROOT, PYTHON_ROOT, MARKER, INSTALLER_PATH, INSTALLER_LOG,
            )
            report("Removing the Qwen Python runtime only; downloaded model weights are preserved…")
            for target in (VENV_ROOT, PYTHON_ROOT, MARKER, INSTALLER_PATH, INSTALLER_LOG):
                if target.exists():
                    self._models_remove_path(target, RUNTIME_ROOT)
            return "Removed the Qwen runtime. Downloaded model weights and saved voice profiles were preserved."

        if requested == "audiobook-ai":
            target = root / "audiobook-ai"
            if target.exists():
                report("Removing the local Audiobook AI runtime and model…")
                self._models_remove_path(target, root)
            return "Removed local Audiobook AI runtime/model. Projects, source books and saved voices were kept."

        raise ValueError(f"Uninstall is not supported for this managed component: {requested}")

    def _models_verify(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Verify real local files and provider prerequisites without fake install claims."""
        requested = str(payload.get("model_id") or "").strip().casefold()
        if not requested:
            raise ValueError("Choose a model or provider to verify.")
        models = self._models_list({})
        item = next((model for model in models if model["model_id"].casefold() == requested), None)
        if item and item.get("status") == "Location unavailable":
            return {
                "model_id": requested, "available": False,
                "detail": "The configured model storage location is unavailable. Reconnect the drive and refresh status.",
                "path": item.get("model_path") or item.get("runtime_path") or "",
                "status": "Location unavailable", "model": item,
            }
        detail = ""
        available = False
        path = ""
        if requested in {"custom-0.6b", "custom-1.7b", "design-1.7b", "base-0.6b", "base-1.7b"}:
            from app.tts.qwen_character_runtime import MODEL_IDS, MODEL_DIRS, model_installed, runtime_ready
            weights_ready = bool(model_installed(requested))
            runtime_ok = bool(runtime_ready())
            available = weights_ready and runtime_ok
            path = str(MODEL_DIRS[requested])
            detail = (
                "Required local model weights and the Qwen runtime are present."
                if available else
                "Model weights are present but the Qwen runtime needs installation/repair."
                if weights_ready else
                "Qwen model files are missing or incomplete; install or repair this model."
            )
        elif requested in {"qwen-runtime", "qwen-customvoice", "qwen-voicedesign", "qwen-clone", "qwen-all"}:
            from app.tts.qwen_character_runtime import runtime_ready, model_installed, MODEL_DIRS
            runtime_ok = bool(runtime_ready())
            custom_ready = bool(model_installed("custom-0.6b") or model_installed("custom-1.7b"))
            base_ready = bool(model_installed("base-0.6b") or model_installed("base-1.7b"))
            design_ready = bool(model_installed("design-1.7b") and base_ready)
            checks = {
                "qwen-customvoice": (["custom-0.6b", "custom-1.7b"], custom_ready),
                "qwen-voicedesign": (["design-1.7b", "base-0.6b", "base-1.7b"], design_ready),
                "qwen-clone": (["base-0.6b", "base-1.7b"], base_ready),
                "qwen-all": (["custom-0.6b", "custom-1.7b", "design-1.7b", "base-0.6b", "base-1.7b"], custom_ready and design_ready),
            }
            if requested == "qwen-runtime":
                available = runtime_ok
                path = ""
            else:
                needed, weights_ready = checks[requested]
                available = runtime_ok and weights_ready
                path = str(MODEL_DIRS.get("design-1.7b") if requested == "qwen-voicedesign" else
                           MODEL_DIRS.get("base-0.6b") if requested == "qwen-clone" else
                           MODEL_DIRS.get("custom-0.6b"))
            detail = (
                "Qwen runtime and all required model files are ready."
                if available else
                "Qwen runtime or one or more required model files are missing; use Install or Repair."
            )
        elif requested == "piper":
            from app.tts.providers.piper import PiperProvider
            paths = list(PiperProvider.model_paths())
            verified = [
                model for model in paths
                if model.is_file() and model.stat().st_size > 1024
                and model.with_suffix(model.suffix + ".json").is_file()
            ]
            available = bool(verified)
            detail = f"{len(verified)} Piper voice model(s) passed the local ONNX/config file check." if available else "No usable Piper ONNX/config pair was found; install or repair a voice model."
        elif requested == "kokoro":
            from app.tts.providers.kokoro import KokoroProvider
            available = bool(KokoroProvider.assets_available())
            detail = "Kokoro model and voice pack are available." if available else "Kokoro model or voice pack is missing/incomplete."
        elif requested == "chatterbox-model-assets":
            from app.tts.model_registry import component_file_inventory
            inventory_files = component_file_inventory(requested)
            available = bool(inventory_files.get("accessible") and inventory_files.get("total_files"))
            path = str(inventory_files.get("model_path") or "")
            detail = (
                f"{inventory_files.get('total_files', 0)} Chatterbox model asset file(s) found in the shared cache."
                if available else
                "No downloaded Chatterbox model assets were found; the runtime may download them on first use."
            )
        elif requested in {"chatterbox", "chatterbox-multilingual", "chatterbox-runtime"}:
            from app.tts.chatterbox_runtime import runtime_ready, RUNTIME_DIR
            available = bool(runtime_ready())
            path = str(RUNTIME_DIR)
            detail = "Chatterbox runtime ready; English and multilingual model weights are inventoried separately." if available else "Chatterbox runtime is missing or incomplete."
        elif requested == "audiobook-ai":
            from app.core.paths import models_root
            ai_root = models_root() / "audiobook-ai"
            server_present = (ai_root / "llama-server.exe").is_file()
            candidates = (
                ai_root / "Qwen3-4B-Q4_K_M.gguf",
                ai_root / "Qwen3-1.7B-Q5_K_M.gguf",
            )
            installed_model = next((candidate for candidate in candidates if candidate.is_file()), None)
            available = bool(server_present and installed_model)
            path = str(installed_model or ai_root)
            detail = "Audiobook AI runtime and a local model file are present; actual inference is checked when the installer completes." if available else "Audiobook AI runtime or local model file is missing. Install or repair the component, then verify again."
        elif requested == "windows-sapi":
            available = bool(item and item.get("installed"))
            detail = str(item.get("status") if item else "Windows SAPI provider was not found.")
        elif requested == "edge-tts":
            available = bool(item and item.get("installed"))
            detail = "Edge TTS client package is available; synthesis still requires internet." if available else "Edge TTS client package is unavailable."
        elif requested == "elevenlabs":
            available = bool(item and item.get("credentials_configured"))
            detail = "ElevenLabs API key is configured; account access is verified on first provider request." if available else "ElevenLabs API key is not configured. Open Voice Studio to connect the account."
        else:
            raise ValueError(f"Unsupported model/provider to verify: {requested}")
        if requested == "windows-sapi" and available:
            status = "Ready"
        elif requested == "elevenlabs" and not available:
            status = "Not configured"
        elif available:
            # File/dependency presence is not a functional inference test.
            status = "Installed"
        elif item and (int(item.get("storage_bytes") or 0) > 0 or
                       (item.get("managed_path") and Path(str(item["managed_path"])).exists())):
            status = "Partially installed"
        elif item and item.get("component_type") == "provider":
            status = "Missing"
        else:
            status = "Missing"

        if item and item.get("component_type") != "provider" and item.get("inventory_fingerprint"):
            try:
                from app.tts.model_registry import record_component_verification
                if available:
                    record_component_verification(
                        requested, True, detail, str(item["inventory_fingerprint"]), level="files"
                    )
            except Exception:
                log.exception("Could not persist model file verification for %s", requested)
        return {"model_id": requested, "available": available, "detail": detail, "path": path,
                "status": status, "model": item}

    @staticmethod
    def _safe_command_output(command: list[str], timeout: float = 3.0) -> str:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    def _performance_qwen_benchmark(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Queue a warmed, real Qwen CustomVoice preview benchmark."""
        payload = payload or {}
        model_kind = str(payload.get("model_kind") or "custom-0.6b").strip()
        if model_kind not in {"custom-0.6b", "custom-1.7b"}:
            raise ValueError("Choose an installed Qwen CustomVoice 0.6B or 1.7B model.")
        if not self._qwen_model_installed(model_kind):
            raise ValueError(
                f"The selected Qwen model is not installed or is incomplete: {model_kind}. "
                "Install and verify it in Models Center before benchmarking."
            )
        voice = str(payload.get("voice") or "Ryan").strip() or "Ryan"
        backend = str(payload.get("backend") or self.settings.value(
            "qwen/backend_preference", "automatic"
        ) or "automatic").strip().casefold()
        low_memory = bool(self.settings.value("qwen/low_memory_mode", False, type=bool))
        with self._jobs_lock:
            active = [
                row for row in self._jobs.values()
                if str(row.get("state") or "").casefold() in {"queued", "running", "paused"}
            ]
        if active:
            raise RuntimeError(
                "The Qwen benchmark is blocked while another application job is active. "
                "Wait for it to finish, then retry."
            )
        job_id = self._new_job(
            "tts-benchmark",
            "Qwen 30-second warm preview benchmark",
            f"Warm Qwen CustomVoice {model_kind} using {voice}, then measure a real ~30-second audio preview.",
        )
        threading.Thread(
            target=self._performance_qwen_benchmark_worker,
            args=(job_id, model_kind, voice, backend, low_memory),
            daemon=True,
            name="RyuQwenPerformanceBenchmark",
        ).start()
        return {"job_id": job_id, "model_kind": model_kind, "voice": voice, "backend": backend, "queued": True}

    def _performance_qwen_benchmark_worker(
        self, job_id: str, model_kind: str, voice: str, backend: str, low_memory: bool
    ) -> None:
        """Warm the Qwen worker first, then measure one real preview synthesis."""
        import tempfile
        from app.tts.benchmark import benchmark_provider
        from app.tts.providers.qwen_character import QwenCharacterProvider

        sample_text = (
            "During this local performance test, the narrator reads a continuous passage at a natural audiobook pace. "
            "The passage includes ordinary sentences, short pauses, and a few longer phrases so the benchmark reflects "
            "a realistic preview rather than a tiny single-line sample. Ryu records the generated audio duration, "
            "warm synthesis time, real-time factor, selected model, actual execution device, CPU use, memory "
            "availability, and accelerator telemetry without changing the saved voice profile or project."
        )
        provider = None
        self._job_update(
            job_id, state="running", stage="Warming Qwen model",
            message=f"Loading {model_kind} and warming the selected Qwen worker before the timed preview.",
            started_at=self._now(), progress=5,
        )
        try:
            def report_progress(message: str) -> None:
                self._job_update(
                    job_id, state="running", stage="Qwen synthesis",
                    message=str(message), progress=25,
                )

            provider = QwenCharacterProvider(
                voice_id=voice,
                language="English",
                model_kind=model_kind,
                qwen_mode="custom",
                backend=backend,
                low_memory=low_memory,
                status_callback=report_progress,
            )
            with tempfile.TemporaryDirectory(prefix="ryu-qwen-bench-warmup-") as temporary:
                warmup_path = Path(temporary) / "warmup.wav"
                warmup_started = time.perf_counter()
                provider.synthesize(
                    "This is a short warm-up for the local Qwen speech model.",
                    warmup_path,
                    voice=voice,
                )
                warmup_seconds = time.perf_counter() - warmup_started
            self._job_update(
                job_id, state="running", stage="Measuring warm preview",
                message="Qwen model is warm. Measuring the real preview synthesis now.",
                progress=45,
            )
            result = benchmark_provider(
                provider, voice=voice, backend=backend, text=sample_text,
            )
            execution = dict(getattr(provider, "last_execution_context", {}) or {})
            target_duration_met = abs(float(result.audio_seconds) - 30.0) <= 3.0
            under_60_seconds = float(result.seconds) < 60.0
            target_met = bool(result.success and target_duration_met and under_60_seconds)
            result_data = {
                "provider": "QwenCharacterProvider",
                "workload_id": "qwen-customvoice-preview-30s-v1",
                "model_kind": model_kind,
                "voice": voice,
                "backend": result.backend,
                "requested_backend": result.requested_backend or backend,
                "execution_providers": list(result.execution_providers),
                "backend_verified": bool(result.backend_verified),
                "execution_device": execution.get("device"),
                "execution_backend": execution.get("backend"),
                "execution_measured_at": execution.get("measured_at"),
                "warmup_seconds": float(warmup_seconds),
                "seconds": float(result.seconds),
                "audio_seconds": float(result.audio_seconds),
                "realtime_factor": float(result.realtime_factor),
                "target_audio_seconds": 30.0,
                "target_duration_tolerance_seconds": 3.0,
                "target_duration_met": target_duration_met,
                "under_60_seconds": under_60_seconds,
                "target_performance_met": target_met,
                "success": bool(result.success),
                "error": str(result.error or ""),
            }
            try:
                telemetry = self._performance_info({"refresh": True})
                result_data["hardware"] = {
                    key: telemetry.get(key) for key in (
                        "platform", "processor", "gpu_name", "backend",
                        "recommended_backend", "backend_active", "accelerators",
                    )
                }
                result_data["resources"] = {
                    key: telemetry.get(key) for key in (
                        "cpu_percent", "memory_total_bytes", "memory_available_bytes",
                        "memory_percent", "gpu_percent", "vram_used_mb",
                        "vram_total_mb", "gpu_temperature_c",
                    )
                }
                result_data["last_inference"] = telemetry.get("last_inference") or execution
                result_data["resource_snapshot_at"] = telemetry.get("measured_at")
            except Exception as telemetry_error:
                result_data["hardware"] = {}
                result_data["resources"] = {}
                result_data["resource_error"] = str(telemetry_error)
                result_data["last_inference"] = execution
            self._record_performance_benchmark(
                job_id, result_data, "completed" if result.success else "failed"
            )
            if not result.success:
                detail = result_data["error"] or "Qwen did not produce valid benchmark audio."
                self._job_update(
                    job_id, state="failed", stage="Qwen benchmark failed", message=detail,
                    error={"code": "qwen_benchmark_failed", "message": detail},
                    result=result_data, progress=100, recoverable=True,
                )
                return
            duration_label = "30-second duration target met" if target_duration_met else "30-second duration target not met"
            speed_label = "under-60-second target met" if under_60_seconds else "under-60-second target not met"
            detail = (
                f"{model_kind} / {result.backend}: {result.seconds:.2f}s warm synthesis for "
                f"{result.audio_seconds:.2f}s audio; RTF {result.realtime_factor:.3f}. "
                f"{duration_label}; {speed_label}."
            )
            self._job_update(
                job_id, state="completed", stage="Qwen benchmark complete", message=detail,
                result=result_data, progress=100, recoverable=False,
            )
        except Exception as exc:
            log.exception("Qwen warm-preview performance benchmark failed")
            detail = str(exc) or type(exc).__name__
            self._record_performance_benchmark(
                job_id,
                {
                    "provider": "QwenCharacterProvider", "model_kind": model_kind,
                    "voice": voice, "backend": "unverified",
                    "requested_backend": backend, "success": False, "error": detail,
                },
                "failed",
            )
            self._job_update(
                job_id, state="failed", stage="Qwen benchmark failed", message=detail,
                error={"code": "qwen_benchmark_failed", "message": detail},
                progress=100, recoverable=True,
            )
        finally:
            if provider is not None:
                try:
                    provider.close()
                except Exception:
                    log.debug("Qwen benchmark provider cleanup failed", exc_info=True)

    def _performance_benchmark(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Queue a real local Piper synthesis benchmark; never block the Qt event thread."""
        from app.tts.providers.piper import PiperProvider

        payload = payload or {}
        voices = [path for path in PiperProvider.model_paths() if path.is_file() and path.suffix.casefold() == ".onnx"]
        requested_voice = str(payload.get("voice") or "").strip()
        voice = next((path for path in voices if path.stem.casefold() == requested_voice.casefold()), None) if requested_voice else None
        if requested_voice and voice is None:
            raise ValueError(f"The selected Piper voice is not installed: {requested_voice}")
        if voice is None and voices:
            voice = voices[0]
        if voice is None:
            raise ValueError("Install a local Piper voice in Models before running a real TTS benchmark.")

        with self._jobs_lock:
            active = [row for row in self._jobs.values()
                      if str(row.get("state") or "").casefold() in {"queued", "running"}]
        if active:
            raise RuntimeError("The TTS benchmark is blocked while another application job is active. Wait for the active job to finish, then retry.")

        job_id = self._new_job(
            "tts-benchmark",
            "Local TTS performance benchmark",
            f"Piper synthesis using {voice.stem}; measures real elapsed time and generated WAV duration.",
        )
        threading.Thread(
            target=self._performance_benchmark_worker,
            args=(job_id, voice.stem),
            daemon=True,
            name="RyuPerformanceBenchmark",
        ).start()
        return {"job_id": job_id, "voice": voice.stem, "queued": True}

    def _performance_benchmark_worker(self, job_id: str, voice: str) -> None:
        """Run one real synthesis benchmark in a background worker and persist its result."""
        from app.tts.benchmark import benchmark_provider
        from app.tts.providers.piper import PiperProvider

        self._job_update(
            job_id,
            state="running",
            stage="Preparing local voice",
            message=f"Preparing Piper voice {voice} for a real synthesis benchmark.",
            started_at=self._now(),
            progress=5,
        )
        try:
            result = benchmark_provider(
                PiperProvider(backend="automatic"),
                voice=voice,
                backend="automatic",
            )
            result_data = {
                "provider": result.provider, "workload_id": "piper-default-preview-v1",
                "backend": result.backend,
                "requested_backend": result.requested_backend or "automatic",
                "execution_providers": list(result.execution_providers),
                "backend_verified": bool(result.backend_verified), "voice": voice,
                "seconds": float(result.seconds), "audio_seconds": float(result.audio_seconds),
                "realtime_factor": float(result.realtime_factor), "success": bool(result.success),
                "error": str(result.error or ""),
            }
            try:
                telemetry = self._performance_info({"refresh": True})
                result_data["hardware"] = {
                    key: telemetry.get(key) for key in (
                        "platform", "processor", "gpu_name", "backend",
                        "recommended_backend", "backend_active", "accelerators",
                    )
                }
                result_data["resources"] = {
                    key: telemetry.get(key) for key in (
                        "cpu_percent", "memory_total_bytes", "memory_available_bytes",
                        "memory_percent", "gpu_percent", "vram_used_mb",
                        "vram_total_mb", "gpu_temperature_c",
                    )
                }
                result_data["resource_snapshot_at"] = telemetry.get("measured_at")
            except Exception as telemetry_error:
                result_data["hardware"] = {}
                result_data["resources"] = {}
                result_data["resource_error"] = str(telemetry_error)
            self._record_performance_benchmark(
                job_id, result_data, "completed" if result.success else "failed"
            )
            if not result.success:
                detail = result_data["error"] or "The local TTS benchmark did not produce valid audio."
                self._job_update(
                    job_id, state="failed", stage="Benchmark failed", message=detail,
                    error={"code": "benchmark_failed", "message": detail},
                    result=result_data, progress=100, recoverable=True,
                )
                return
            verdict = "faster than realtime" if result.realtime_factor < 1.0 else "slower than realtime"
            detail = (
                f"{voice}: {result.seconds:.2f}s synthesis for {result.audio_seconds:.2f}s audio; "
                f"RTF {result.realtime_factor:.2f} ({verdict})."
            )
            self._job_update(
                job_id, state="completed", stage="Benchmark complete", message=detail,
                result=result_data, progress=100, recoverable=False,
            )
        except Exception as exc:
            log.exception("Local TTS performance benchmark failed")
            detail = str(exc) or type(exc).__name__
            self._record_performance_benchmark(
                job_id,
                {
                    "provider": "PiperProvider", "backend": "unverified",
                    "requested_backend": "automatic", "voice": voice,
                    "success": False, "error": detail,
                },
                "failed",
            )
            self._job_update(
                job_id, state="failed", stage="Benchmark failed", message=detail,
                error={"code": "benchmark_failed", "message": detail},
                progress=100, recoverable=True,
            )

    @staticmethod
    def _qwen_model_installed(kind: str) -> bool:
        try:
            from app.tts.qwen_character_runtime import model_installed
            return bool(model_installed(kind))
        except Exception:
            return False

    def _performance_info(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return live host telemetry and Qwen backend discovery without inventing measurements."""
        import platform
        payload = payload or {}
        refresh = bool(payload.get("refresh"))
        cpu_percent = None
        memory_total = memory_available = memory_percent = None
        try:
            import psutil
            cpu_percent = float(psutil.cpu_percent(interval=0.15))
            vm = psutil.virtual_memory()
            memory_total = int(vm.total)
            memory_available = int(vm.available)
            memory_percent = float(vm.percent)
        except Exception:
            if os.name == "nt":
                raw = self._safe_command_output([
                    "powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "$cpu=(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average; "
                    "$os=Get-CimInstance Win32_OperatingSystem; "
                    "[pscustomobject]@{cpu=$cpu;total=$os.TotalVisibleMemorySize;free=$os.FreePhysicalMemory}|ConvertTo-Json -Compress"
                ], timeout=5.0)
                try:
                    snapshot = json.loads(raw) if raw else {}
                    cpu_percent = float(snapshot["cpu"]) if snapshot.get("cpu") is not None else None
                    memory_total = int(snapshot["total"]) * 1024 if snapshot.get("total") else None
                    memory_available = int(snapshot["free"]) * 1024 if snapshot.get("free") else None
                    if memory_total and memory_available is not None:
                        memory_percent = max(0.0, min(100.0, (memory_total-memory_available)*100/memory_total))
                except (ValueError, TypeError, KeyError):
                    pass
        gpu_percent = vram_used_mb = vram_total_mb = gpu_temperature_c = None
        gpu_name = ""
        devices = []
        recommended = None
        accelerator_error = ""
        try:
            from app.tts.qwen_accelerator import detect_accelerators, best_accelerator
            accelerators = detect_accelerators(refresh=refresh)
            recommended = best_accelerator()
            devices = [{
                "backend": item.backend, "device": item.device, "name": item.name,
                "memory_gb": round(float(item.memory_gb), 2),
                "supported": bool(item.supported), "reason": item.reason,
            } for item in accelerators]
            active = next((item for item in accelerators
                           if item.supported and item.backend in {"cuda", "rocm", "xpu"}), None)
            candidate = next((item for item in accelerators
                              if item.backend.endswith("-candidate") or item.backend.endswith("-unsupported")), None)
            chosen = active or candidate
            if chosen:
                gpu_name = chosen.name
            if active and active.backend == "cuda":
                metrics = self._safe_command_output([
                    "nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits"
                ], timeout=2.0)
                if metrics:
                    try:
                        vals=[part.strip() for part in metrics.splitlines()[0].split(",")]
                        gpu_percent=float(vals[0]) if vals[0] not in {"[N/A]",""} else None
                        vram_used_mb=float(vals[1]) if vals[1] not in {"[N/A]",""} else None
                        vram_total_mb=float(vals[2]) if vals[2] not in {"[N/A]",""} else None
                        gpu_temperature_c=float(vals[3]) if len(vals)>3 and vals[3] not in {"[N/A]",""} else None
                    except (ValueError,IndexError):
                        pass
            elif active and active.backend == "xpu":
                try:
                    import torch
                    if hasattr(torch, "xpu") and torch.xpu.is_available():
                        stats=torch.xpu.memory_stats(0)
                        vram_used_mb=float(stats.get("allocated_bytes.all.current",0))/(1024**2)
                        total=float(getattr(torch.xpu.get_device_properties(0),"total_memory",0))
                        vram_total_mb=total/(1024**2) if total else None
                except Exception:
                    pass
            elif active and active.backend == "rocm":
                try:
                    import torch
                    if torch.cuda.is_available():
                        vram_used_mb=float(torch.cuda.memory_allocated(0))/(1024**2)
                        vram_total_mb=float(torch.cuda.get_device_properties(0).total_memory)/(1024**2)
                except Exception:
                    pass
        except Exception as exc:
            accelerator_error = str(exc)
        backend = recommended.backend if recommended else "unavailable"
        backend_active = bool(recommended and recommended.supported and backend in {"cuda","rocm","xpu"})
        reason = recommended.reason if recommended else accelerator_error or "No accelerator discovery result is available."
        if backend == "cpu":
            recommendation = "CPU"
        elif backend_active:
            recommendation = backend.upper()
        elif backend.endswith("-candidate"):
            recommendation = backend.replace("-candidate","").upper() + " candidate — runtime not active"
        elif backend.endswith("-unsupported"):
            recommendation = backend.replace("-unsupported","").upper() + " detected — unsupported runtime"
        else:
            recommendation = "Unavailable"
        with self._performance_history_lock:
            benchmark_history = [
                dict(row) for row in reversed(self._performance_history[-100:])
            ]
        latest_benchmark: dict[str, Any] = {}
        for history_row in benchmark_history:
            history_result = history_row.get("result")
            if isinstance(history_result, dict) and history_result.get("success") is True:
                latest_benchmark = dict(history_result)
                latest_benchmark["measured_at"] = history_row.get("measured_at")
                break
        with self._jobs_lock:
            successful_benchmarks = [
                row for row in self._jobs.values()
                if str(row.get("type") or "").casefold() == "tts-benchmark"
                and str(row.get("state") or "").casefold() == "completed"
                and isinstance(row.get("result"), dict)
                and row["result"].get("success") is True
            ]
            if successful_benchmarks and not latest_benchmark:
                latest_row = max(successful_benchmarks,
                    key=lambda row: str(row.get("completed_at") or row.get("updated_at") or ""))
                latest_benchmark = dict(latest_row.get("result") or {})
                latest_benchmark["measured_at"] = latest_row.get("completed_at") or latest_row.get("updated_at")
        generation_seconds = latest_benchmark.get("seconds")
        last_inference: dict[str, Any] = {}
        try:
            inference_path = settings_root() / "qwen_last_inference.json"
            if inference_path.is_file():
                candidate = json.loads(inference_path.read_text(encoding="utf-8"))
                if isinstance(candidate, dict) and candidate.get("verified_inference") is True:
                    last_inference = candidate
        except (OSError, ValueError, TypeError):
            last_inference = {}
        return {
            "available": cpu_percent is not None or memory_total is not None or bool(devices),
            "cpu_percent": cpu_percent, "memory_total_bytes": memory_total,
            "memory_available_bytes": memory_available, "memory_percent": memory_percent,
            "gpu_percent": gpu_percent, "vram_used_mb": vram_used_mb,
            "vram_total_mb": vram_total_mb, "gpu_temperature_c": gpu_temperature_c,
            "gpu_name": gpu_name, "accelerators": devices,
            "recommended_backend": recommendation, "backend_active": backend_active,
            "backend": backend, "reason": reason,
            "platform": platform.platform(), "processor": platform.processor() or "Not reported",
            "generation_seconds": generation_seconds,
            "benchmark_audio_seconds": latest_benchmark.get("audio_seconds"),
            "benchmark_realtime_factor": latest_benchmark.get("realtime_factor"),
            "benchmark_voice": latest_benchmark.get("voice"),
            "benchmark_provider": latest_benchmark.get("provider"),
            "benchmark_measured_at": latest_benchmark.get("measured_at"),
            "benchmark_history": benchmark_history,
            "last_inference": last_inference,
            "qwen_models_installed": [
                kind for kind in ("custom-0.6b", "custom-1.7b")
                if self._qwen_model_installed(kind)
            ],
            "measured_at": datetime.now(timezone.utc).isoformat(),
        }

    def _performance_history_import(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Import bounded, schema-validated benchmark evidence while preserving source PC provenance."""
        payload = payload or {}
        selected_path = str(payload.get("path") or "").strip()
        if selected_path:
            source = Path(selected_path).expanduser().resolve()
        else:
            target, _filter = QFileDialog.getOpenFileName(
                None, "Import performance benchmark report", str(settings_root()),
                "JSON reports (*.json);;All files (*.*)",
            )
            if not target:
                return {"cancelled": True, "imported": 0}
            source = Path(target).expanduser().resolve()
        if not source.is_file():
            raise ValueError("The selected benchmark report does not exist.")
        if source.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("Benchmark reports larger than 10 MB cannot be imported.")
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError(f"The benchmark report is not valid UTF-8 JSON: {exc}") from exc
        if not isinstance(document, dict) or document.get("schema") != "ryu.performance-benchmark-history.v1":
            raise ValueError("This is not a supported Ryu performance benchmark report.")
        incoming = document.get("records")
        if not isinstance(incoming, list) or not incoming or len(incoming) > 500:
            raise ValueError("The report must contain between 1 and 500 benchmark records.")
        imported: list[dict[str, Any]] = []
        for row in incoming:
            if not isinstance(row, dict) or not isinstance(row.get("result"), dict):
                continue
            result = dict(row["result"])
            try:
                seconds = float(result.get("seconds"))
                audio_seconds = float(result.get("audio_seconds"))
                realtime_factor = float(result.get("realtime_factor"))
            except (TypeError, ValueError, OverflowError):
                continue
            if not all(math.isfinite(value) and value >= 0 for value in (seconds, audio_seconds, realtime_factor)):
                continue
            provider = str(result.get("provider") or "").strip()
            voice = str(result.get("voice") or "").strip()
            workload_id = str(result.get("workload_id") or "").strip()
            if not workload_id:
                # Legacy local Piper exports used the stable built-in benchmark
                # passage before workload IDs were added to the report schema.
                if provider == "PiperProvider":
                    workload_id = "piper-default-preview-v1"
                elif provider == "QwenCharacterProvider" and float(result.get("target_audio_seconds") or 0) == 30.0:
                    workload_id = "qwen-customvoice-preview-30s-v1"
                else:
                    continue
                result["workload_id"] = workload_id
            if not provider or not voice:
                continue
            record = dict(row)
            original_id = str(row.get("benchmark_id") or row.get("job_id") or "")
            record.update({
                "benchmark_id": "imported-" + uuid.uuid4().hex,
                "job_id": "",
                "source_origin": "imported",
                "source_file_name": source.name,
                "source_benchmark_id": original_id,
                "source_hardware": dict(result.get("hardware") or row.get("source_hardware") or {}),
                "result": result,
            })
            if not isinstance(record.get("measured_at"), str) or not record["measured_at"].strip():
                record["measured_at"] = str(document.get("exported_at") or self._now())
            imported.append(record)
        if not imported:
            raise ValueError("The report contains no valid benchmark records with real measurements and workload provenance.")
        with self._performance_history_lock:
            self._performance_history.extend(imported)
            self._persist_json_rows(self._performance_history_path(), list(self._performance_history))
        return {
            "cancelled": False,
            "imported": len(imported),
            "source_file": source.name,
            "source_hardware_preserved": True,
        }

    def _performance_history_compare(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Compare two real runs only when provider, model, voice and workload match."""
        payload = payload or {}
        ids = payload.get("benchmark_ids")
        if not isinstance(ids, list) or len(ids) != 2 or not all(isinstance(value, str) and value for value in ids) or ids[0] == ids[1]:
            raise ValueError("Select exactly two different benchmark records to compare.")
        with self._performance_history_lock:
            by_id = {str(row.get("benchmark_id") or ""): dict(row) for row in self._performance_history}
        rows = [by_id.get(value) for value in ids]
        if any(row is None for row in rows):
            raise ValueError("One of the selected benchmark records is no longer available.")
        first, second = rows
        a, b = first.get("result") or {}, second.get("result") or {}
        if first.get("state") != "completed" or second.get("state") != "completed" or a.get("success") is not True or b.get("success") is not True:
            raise ValueError("Only successful completed benchmark records can be compared.")
        keys = ("provider", "model_kind", "voice", "workload_id")
        mismatches = [key for key in keys if str(a.get(key) or "") != str(b.get(key) or "")]
        if mismatches:
            labels = ", ".join(mismatches)
            raise ValueError("These runs are not comparable because the following workload details differ or are missing: " + labels + ".")
        try:
            seconds_a, seconds_b = float(a["seconds"]), float(b["seconds"])
            audio_a, audio_b = float(a["audio_seconds"]), float(b["audio_seconds"])
            rtf_a, rtf_b = float(a["realtime_factor"]), float(b["realtime_factor"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("The selected benchmark records are missing valid timing measurements.") from exc
        if min(audio_a, audio_b) <= 0 or abs(audio_a - audio_b) > max(3.0, min(audio_a, audio_b) * 0.10):
            raise ValueError("The generated audio durations differ too much for a fair comparison.")
        hardware_a = dict(first.get("source_hardware") or a.get("hardware") or {})
        hardware_b = dict(second.get("source_hardware") or b.get("hardware") or {})
        label_a = " · ".join(str(hardware_a.get(key) or "").strip() for key in ("platform", "processor", "gpu_name") if str(hardware_a.get(key) or "").strip()) or ("Imported PC" if first.get("source_origin") == "imported" else "This PC")
        label_b = " · ".join(str(hardware_b.get(key) or "").strip() for key in ("platform", "processor", "gpu_name") if str(hardware_b.get(key) or "").strip()) or ("Imported PC" if second.get("source_origin") == "imported" else "This PC")
        faster = label_a if seconds_a < seconds_b else label_b if seconds_b < seconds_a else "Equal"
        return {
            "comparable": True,
            "provider": a.get("provider"),
            "model_kind": a.get("model_kind"),
            "voice": a.get("voice"),
            "workload_id": a.get("workload_id"),
            "records": [
                {"benchmark_id": first["benchmark_id"], "label": label_a, "source_origin": first.get("source_origin", "local"), "synthesis_seconds": seconds_a, "audio_seconds": audio_a, "realtime_factor": rtf_a, "backend": a.get("backend"), "hardware": hardware_a},
                {"benchmark_id": second["benchmark_id"], "label": label_b, "source_origin": second.get("source_origin", "local"), "synthesis_seconds": seconds_b, "audio_seconds": audio_b, "realtime_factor": rtf_b, "backend": b.get("backend"), "hardware": hardware_b},
            ],
            "faster": faster,
            "speedup_ratio": (max(seconds_a, seconds_b) / min(seconds_a, seconds_b)) if min(seconds_a, seconds_b) > 0 else None,
            "synthesis_delta_seconds": abs(seconds_a - seconds_b),
            "audio_duration_delta_seconds": abs(audio_a - audio_b),
            "rtf_delta": abs(rtf_a - rtf_b),
        }

    def _performance_history_clear(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Clear only benchmark records; preserve Background Jobs and general History."""
        with self._performance_history_lock:
            cleared = len(self._performance_history)
            self._performance_history = []
            self._persist_json_rows(self._performance_history_path(), [])
        return {
            "cleared": cleared,
            "background_job_history_preserved": True,
        }

    def _performance_history_export(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Export benchmark evidence without modifying job history or model files."""
        with self._performance_history_lock:
            records = [dict(row) for row in self._performance_history]
        if not records:
            return {"cancelled": False, "exported": False, "records": 0}
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        suggested = settings_root() / f"ryu-performance-benchmarks-{timestamp}.json"
        target, _filter = QFileDialog.getSaveFileName(
            None, "Export performance benchmark history", str(suggested),
            "JSON reports (*.json);;All files (*.*)",
        )
        if not target:
            return {"cancelled": True, "exported": False, "records": len(records)}
        destination = Path(target).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "ryu.performance-benchmark-history.v1",
            "exported_at": self._now(),
            "records": records,
        }
        temporary = destination.with_name(destination.name + ".tmp")
        try:
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return {"cancelled": False, "exported": True, "path": str(destination), "records": len(records)}

    def _diagnostics_check(self, _payload: dict[str, Any]) -> dict[str, Any]:
        checks = []
        try:
            ensure_roots()
            checks.append({"name": "Local storage folders", "status": "passed", "detail": str(app_root())})
        except Exception as exc:
            checks.append({"name": "Local storage folders", "status": "failed", "detail": str(exc)})
        try:
            checks.append({"name": "Project library", "status": "passed", "detail": f"{len(list_projects())} valid project(s)"})
        except Exception as exc:
            checks.append({"name": "Project library", "status": "failed", "detail": str(exc)})
        checks.append({"name": "Background-job persistence", "status": "passed" if self._jobs_path().parent.exists() else "warning",
                       "detail": str(self._jobs_path())})
        return {"checks": checks, "passed": all(c["status"] == "passed" for c in checks)}

    @staticmethod
    def _sanitize_diagnostic_text(value: str) -> str:
        """Remove common credentials and user-identifying paths from exported diagnostics."""
        text = str(value or "")
        home = str(Path.home())
        if home:
            text = text.replace(home, "<USER_HOME>")
            text = text.replace(home.replace("\\", "/"), "<USER_HOME>")
        text = re.sub(
            r"""(?i)(["']?(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|passwd|secret|authorization|client_secret)["']?\s*[:=]\s*["']?)[^,\s"']+""",
            r"\1[REDACTED]",
            text,
        )
        text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
        text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[REDACTED_KEY]", text)
        text = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[REDACTED_EMAIL]", text, flags=re.IGNORECASE)
        return "".join(char for char in text if char in "\r\n\t" or ord(char) >= 32)

    def _diagnostics_export_logs(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Export a user-selected, bounded, sanitized diagnostic report and available app logs."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        suggested = settings_root() / f"ryu-audiobook-diagnostics-{timestamp}.txt"
        target, _filter = QFileDialog.getSaveFileName(
            None, "Export sanitized diagnostics", str(suggested),
            "Text reports (*.txt);;All files (*.*)",
        )
        if not target:
            return {"cancelled": True, "files_included": 0}

        roots = (settings_root(), app_root(), app_root() / "logs")
        log_paths: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            if not root.is_dir():
                continue
            try:
                candidates = sorted(root.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
            except OSError:
                continue
            for candidate in candidates:
                key = str(candidate.resolve()).casefold()
                if key not in seen and candidate.is_file():
                    seen.add(key)
                    log_paths.append(candidate)

        sections = [
            "RYU'S AUDIOBOOK — SANITIZED DIAGNOSTIC REPORT",
            f"Generated: {self._now()}",
            f"Application: {APP_NAME} {full_version()}",
            f"Platform: {sys.platform}",
            f"Log files found: {len(log_paths)}",
            "",
            "BACKGROUND JOB SUMMARY",
        ]
        with self._jobs_lock:
            jobs = sorted(self._jobs.values(), key=lambda row: str(row.get("queued_at") or ""), reverse=True)[:100]
            for job in jobs:
                error = job.get("error") if isinstance(job.get("error"), dict) else {}
                sections.append(self._sanitize_diagnostic_text(
                    f"- type={job.get('type','unknown')} state={job.get('state','unknown')} "
                    f"progress={job.get('progress',0)} stage={job.get('stage','')} "
                    f"error_code={error.get('code','')}"
                ))
        if not jobs:
            sections.append("(No background jobs recorded.)")

        total_bytes = 0
        included = 0
        for log_path in log_paths:
            if total_bytes >= 5 * 1024 * 1024:
                sections.append("\n[Remaining log files omitted: 5 MiB export limit reached.]")
                break
            try:
                with log_path.open("rb") as handle:
                    handle.seek(0, os.SEEK_END)
                    size = handle.tell()
                    handle.seek(max(0, size - 1024 * 1024), os.SEEK_SET)
                    raw = handle.read(min(1024 * 1024, 5 * 1024 * 1024 - total_bytes))
                content = raw.decode("utf-8", errors="replace")
            except OSError:
                continue
            included += 1
            total_bytes += len(raw)
            sections.extend(["", f"LOG FILE: {log_path.name} (sanitized; newest portion only)",
                             self._sanitize_diagnostic_text(content)])

        output = "\n".join(sections).rstrip() + "\n"
        destination = Path(target).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        try:
            temporary.write_text(output, encoding="utf-8")
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return {"cancelled": False, "path": str(destination), "files_included": included,
                "bytes_written": destination.stat().st_size, "sanitized": True}

    def _system_open_output(self, _payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        state = load_state(project.folder)
        value = str(state.get("output_path") or state.get("generation_target_path") or "").strip()
        path = Path(value).expanduser() if value else audiobooks_root()
        folder = path if path.is_dir() else path.parent
        if not folder.exists():
            raise FileNotFoundError("The output folder does not exist yet.")
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve()))):
            raise RuntimeError("Windows did not open the output folder.")
        return {"opened": True, "path": str(folder.resolve())}

    def _sound_catalog(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the last-known audio catalogue immediately; cold scans are workers."""
        payload = payload if isinstance(payload, dict) else {}
        cached = getattr(self, "_sound_catalog_cache", None)
        scanned_at = float(getattr(self, "_sound_catalog_cache_at", 0.0) or 0.0)
        ready = bool(getattr(self, "_sound_catalog_cache_ready", False))
        force_refresh = bool(payload.get("force_refresh"))
        if force_refresh or not ready or time.monotonic() - scanned_at >= 20.0:
            try:
                self._queue_catalog_scan("sound")
            except RuntimeError as exc:
                log.warning("Sound catalogue refresh deferred: %s", exc)
        return list(cached) if isinstance(cached, list) else []

    def _sound_refresh(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Explicit Sound Design refresh; filesystem work stays outside the bridge thread."""
        job_id = self._queue_catalog_scan("sound")
        return {"job_id": job_id, "state": "running", "catalogue": "sound"}

    def _build_sound_catalog(self) -> list[dict[str, Any]]:
        """Build the actual audio catalogue; called only by a background worker."""
        from app.audio.library import AUDIO_EXTENSIONS, MUSIC_CATEGORY_LABELS, audio_asset_role, metadata_for
        local_root = app_root() / "Audio Library"
        bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "assets" / "starter_audio"
        roots = [(local_root, "Imported locally")]
        bundle_entries: dict[str, dict[str, Any]] = {}
        bundle_version = ""
        if bundled.is_dir():
            manifest_path = bundled / "manifest.json"
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                bundle_version = str(manifest.get("version") or "")
                for entry in manifest.get("tracks", []):
                    if not isinstance(entry, dict):
                        continue
                    relative = str(entry.get("bundle_path") or "").replace("\\", "/").strip()
                    if not relative:
                        continue
                    candidate = (bundled / relative).resolve()
                    try:
                        candidate.relative_to(bundled.resolve())
                    except ValueError:
                        continue
                    bundle_entries[str(candidate)] = entry
            except (OSError, ValueError, TypeError):
                log.exception("Could not read bundled starter-audio manifest %s", manifest_path)
            roots.append((bundled, "Bundled with application"))

        found: dict[str, dict[str, Any]] = {}
        seeded_starter_ids: set[tuple[str, str, str, str]] = set()
        category_aliases = {
            "fantasy adventure": "fantasy", "fantasy-adventure": "fantasy",
            "battle & warfare": "action", "battle-warfare": "action", "battle warfare": "action",
            "calm narration": "calm", "calm-narration": "calm", "others": "emotional",
        }
        category_display = {
            "fantasy": "Fantasy adventure", "adventure": "Fantasy adventure",
            "action": "Battle & warfare", "mystery": "Mystery", "horror": "Horror",
            "romance": "Romance", "sci-fi": "Sci-fi", "calm": "Calm narration",
            "universal": "Calm narration", "emotional": "Others",
            "slice-of-life": "Others", "comedy": "Others",
        }

        for root, source in roots:
            if not root.is_dir():
                continue
            try:
                candidates = root.rglob("*")
                for path in candidates:
                    if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                        continue
                    try:
                        resolved = path.resolve()
                        size = resolved.stat().st_size
                    except OSError:
                        continue
                    if size <= 0:
                        continue
                    key = str(resolved)
                    try:
                        metadata = metadata_for(resolved)
                    except (OSError, ValueError, TypeError) as exc:
                        # A corrupt sidecar must not take down the entire library.
                        # Keep the source file untouched and omit only this invalid record.
                        log.warning("Skipping audio asset with unreadable metadata %s: %s", resolved, exc)
                        continue
                    bundled_entry = bundle_entries.get(key, {}) if source == "Bundled with application" else {}
                    raw_category = str(
                        metadata.get("category") or bundled_entry.get("category") or ""
                    ).strip().casefold()
                    category = category_aliases.get(raw_category, raw_category)
                    if category not in MUSIC_CATEGORY_LABELS:
                        category = next(
                            (part.casefold() for part in reversed(path.parts)
                             if part.casefold() in MUSIC_CATEGORY_LABELS),
                            "universal",
                        )
                    role_value = str(
                        metadata.get("role") or bundled_entry.get("type") or ""
                    ).strip().casefold()
                    if role_value:
                        role = "cue" if role_value in {"cue", "opening", "page", "ending", "closing", "chapter"} else role_value
                    else:
                        role = audio_asset_role(resolved)
                    if role not in {"music", "cue"}:
                        role = "music"

                    original_filename = str(metadata.get("original_filename") or path.name).strip()
                    starter_version = str(
                        metadata.get("starter_pack_version") or
                        (bundle_version if source == "Bundled with application" else "")
                    ).strip()
                    starter_category = raw_category or category
                    starter_identity = (
                        starter_version,
                        original_filename.casefold(),
                        starter_category.casefold(),
                        role,
                    )
                    if source == "Imported locally" and starter_version and original_filename:
                        # The first-run seeded copy is the persistent user-data
                        # representation of this bundled asset. Mark it Built-in
                        # and remember it so the packaged source is not shown twice.
                        seeded_starter_ids.add(starter_identity)
                    elif source == "Bundled with application" and starter_version and starter_identity in seeded_starter_ids:
                        continue

                    source_label = (
                        "Bundled with application"
                        if source == "Imported locally" and starter_version
                        else source
                    )
                    title = str(
                        metadata.get("title") or bundled_entry.get("title") or path.stem
                    )
                    category_label = category_display.get(category, "Others")
                    license_note = str(
                        metadata.get("license_note") or metadata.get("source_note") or
                        metadata.get("license") or bundled_entry.get("license_note") or
                        bundled_entry.get("license") or
                        "Unknown; verify rights before publishing"
                    )
                    found[key] = {
                        "id": key, "title": title, "path": key, "source": source_label,
                        "format": path.suffix.lower(), "size_bytes": size,
                        "duration_seconds": metadata.get("duration_seconds"),
                        "licensing": license_note, "category": category,
                        "category_label": category_label, "role": role, "metadata": metadata,
                    }
            except OSError:
                log.exception("Could not scan sound asset folder %s", root)
        rows = sorted(found.values(), key=lambda row: (row["source"], row["title"].casefold()))
        return list(rows)

    def _sound_import(self, payload: dict[str, Any]) -> dict[str, Any]:
        paths = payload.get("paths")
        if not isinstance(paths, list) or not paths:
            selected, _filter = QFileDialog.getOpenFileNames(
                None, "Import audio assets", str(Path.home()),
                "Audio files (*.wav *.mp3 *.flac *.ogg *.m4a *.aac *.aiff *.opus)",
            )
            paths = selected
        if not paths:
            return {"cancelled": True, "imported": []}
        from app.audio.library import AUDIO_EXTENSIONS, MUSIC_CATEGORY_LABELS, probe_audio_duration_seconds
        extensions = AUDIO_EXTENSIONS
        target_kind = str(payload.get("target_kind") or "cue").strip().casefold()
        if target_kind not in {"music", "cue"}:
            raise ValueError("Choose either Music Library or Opening & Cues as the import destination.")
        category = str(payload.get("category") or "universal").strip().casefold()
        category_aliases = {
            "fantasy adventure": "fantasy", "fantasy-adventure": "fantasy",
            "battle & warfare": "action", "battle-warfare": "action",
            "calm narration": "calm", "calm-narration": "calm", "others": "emotional",
        }
        category = category_aliases.get(category, category)
        if target_kind == "music" and category not in MUSIC_CATEGORY_LABELS:
            raise ValueError("Choose one of the supported Music Library categories.")
        if target_kind == "cue":
            category = "universal"
        target_root = app_root() / "Audio Library"
        target_root.mkdir(parents=True, exist_ok=True)
        imported = []
        for raw in paths:
            source = Path(str(raw)).expanduser().resolve()
            if not source.is_file() or source.suffix.lower() not in extensions:
                raise ValueError(f"Unsupported or missing audio asset: {source.name}")
            duration_seconds = probe_audio_duration_seconds(source)
            if target_kind != "music" and duration_seconds > 5.0:
                raise ValueError(
                    f"{source.name} is {duration_seconds:.1f} seconds long. "
                    "Opening, next-chapter, and closing cue clips must be 5 seconds or shorter; "
                    "import longer music into the Music Library and assign it as BGM."
                )
            destination = target_root / source.name
            if destination.exists() and destination.resolve() != source:
                destination = target_root / f"{source.stem}-{uuid.uuid4().hex[:8]}{source.suffix.lower()}"
            if source != destination.resolve():
                shutil.copy2(source, destination)
            metadata_path = destination.with_name(destination.name + ".license.json")
            metadata = {"role": "music" if target_kind == "music" else "cue",
                        "category": category,
                        "title": destination.stem, "original_filename": source.name,
                        "license_note": str(payload.get("license_note") or "User-imported; verify license before publishing"),
                        "duration_seconds": duration_seconds, "imported_at": self._now()}
            try:
                metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError as exc:
                if destination.resolve() != source:
                    try: destination.unlink()
                    except OSError: pass
                raise RuntimeError(f"Could not save metadata for imported audio {destination.name}: {exc}") from exc
            imported.append({"title": destination.stem, "path": str(destination.resolve()),
                             "source": "Imported locally", "format": destination.suffix.lower(),
                             "size_bytes": destination.stat().st_size})
        self._invalidate_catalog_scan("sound")
        refresh_job_id = self._queue_catalog_scan("sound")
        return {
            "cancelled": False, "imported": imported,
            "catalog": self._sound_catalog({}),
            "catalog_refresh_job_id": refresh_job_id,
        }

    def _sound_assign(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        raw = str(payload.get("path") or "").strip()
        state = load_state(project.folder)
        try:
            fade_in = max(0.0, min(30.0, float(payload.get("fade_in_seconds", state.get("background_audio_fade_in", 2.0)))))
            fade_out = max(0.0, min(30.0, float(payload.get("fade_out_seconds", state.get("background_audio_fade_out", 3.0)))))
        except (TypeError, ValueError):
            raise ValueError("Background music fade values must be between 0 and 30 seconds.")
        if not raw:
            saved_at = self._now()
            state.update({"background_audio_path": "", "background_audio_preferred_path": "",
                          "background_audio_mode": "off", "background_audio_enabled": False,
                          "background_audio_fade_in": fade_in, "background_audio_fade_out": fade_out,
                          "modified_at": saved_at, "sound_design_saved_at": saved_at})
            save_state(project.folder, state)
            return {"saved": True, "path": None, "mode": "off",
                    "fade_in_seconds": fade_in, "fade_out_seconds": fade_out}
        selected = Path(raw).expanduser().resolve()
        catalog = {str(row["path"]): row for row in self._sound_catalog({})}
        selected_row = catalog.get(str(selected))
        if not selected.is_file() or selected_row is None or str(selected_row.get("role") or "music").casefold() == "cue":
            raise ValueError("Choose a music track from the local Music Library catalogue.")
        try:
            volume = max(0.0, min(0.50, float(payload.get("volume", 0.18))))
            fade_in = max(0.0, min(30.0, float(payload.get("fade_in_seconds", state.get("background_audio_fade_in", 2.0)))))
            fade_out = max(0.0, min(30.0, float(payload.get("fade_out_seconds", state.get("background_audio_fade_out", 3.0)))))
        except (TypeError, ValueError):
            raise ValueError("Background volume must be 0–50 percent and fades 0–30 seconds.")
        saved_at = self._now()
        state.update({"background_audio_path": str(selected), "background_audio_preferred_path": str(selected),
                      "background_audio_volume": volume, "background_audio_fade_in": fade_in,
                      "background_audio_fade_out": fade_out, "background_audio_mode": "manual",
                      "background_audio_enabled": True, "modified_at": saved_at,
                      "sound_design_saved_at": saved_at})
        save_state(project.folder, state)
        return {"saved": True, "path": str(selected), "title": selected.stem, "volume": volume,
                "fade_in_seconds": fade_in, "fade_out_seconds": fade_out, "mode": "manual"}

    def _sound_save_manifest(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        state = load_state(project.folder)
        if "path" in payload:
            path = str(payload.get("path") or "").strip()
        else:
            path = str(state.get("background_audio_path") or state.get("background_audio_preferred_path") or "").strip()
        from app.audio.library import effective_background_audio_mode
        explicit_enabled = "enabled" in payload
        current_mode = effective_background_audio_mode(state)
        # Volume/fade/path saves must not overwrite the global BGM/Voice Only
        # toggle from a possibly stale frontend snapshot. Only the explicit
        # master toggle supplies "enabled" and changes the saved mode.
        enabled = bool(payload.get("enabled")) if explicit_enabled else current_mode != "off"
        try:
            volume = max(0.0, min(0.50, float(payload.get("volume", state.get("background_audio_volume") if state.get("background_audio_volume") is not None else 0.18))))
            narration_volume = max(0.0, min(1.0, float(payload.get("narration_volume", state.get("narration_audio_volume") if state.get("narration_audio_volume") is not None else 1.0))))
            cue_volume = max(0.0, min(0.50, float(payload.get("cue_volume", state.get("sound_cue_volume") if state.get("sound_cue_volume") is not None else 0.25))))
            fade_in = max(0.0, min(30.0, float(payload.get("fade_in_seconds", state.get("background_audio_fade_in", 2.0)))))
            fade_out = max(0.0, min(30.0, float(payload.get("fade_out_seconds", state.get("background_audio_fade_out", 3.0)))))
        except (TypeError, ValueError):
            raise ValueError("Background music and cue volume must be 0–50 percent, narration 0–100 percent, and fades 0–30 seconds.")
        catalog = self._sound_catalog({})
        catalog_paths = {str(row["path"]) for row in catalog}
        manifest_path = path
        if enabled and path:
            selected = Path(path).expanduser().resolve()
            selected_row = next((row for row in catalog if str(row["path"]) == str(selected)), None)
            if not selected.is_file() or selected_row is None or str(selected_row.get("role") or "music").casefold() == "cue":
                raise ValueError("Selected BGM is missing from the local music library.")
            manifest_path = str(selected)
        active_bgm_path, preferred_bgm_path = _sound_manifest_bgm_paths(state, manifest_path, enabled)
        state.update({
            "background_audio_path": active_bgm_path,
            "background_audio_preferred_path": preferred_bgm_path,
            "background_audio_mode": ("manual" if enabled else "off") if explicit_enabled else current_mode,
            "background_audio_enabled": enabled,
            "background_audio_volume": volume,
        })
        state["background_audio_volume"] = volume
        state["background_audio_fade_in"] = fade_in
        state["background_audio_fade_out"] = fade_out
        state["narration_audio_volume"] = narration_volume
        state["sound_cue_volume"] = cue_volume
        chapter_overrides = state.get("chapter_bgm_overrides")
        if not isinstance(chapter_overrides, dict):
            chapter_overrides = {}
        chapter_strategy = str(state.get("chapter_bgm_strategy") or ("custom" if chapter_overrides else "same")).lower()
        is_chapter_based = chapter_strategy in {"custom", "chapter-based", "chapter_based", "chapter"}
        has_valid_chapter_track = any(
            isinstance(item, dict) and item.get("rule") == "custom" and
            str(item.get("path") or "") in catalog_paths and Path(str(item.get("path") or "")).is_file()
            for item in chapter_overrides.values()
        ) if is_chapter_based else False
        saved_at = self._now()
        state["sound_design_saved_at"] = saved_at
        state["sound_manifest"] = {"bgm_path": state.get("background_audio_path") or None,
                                   "bgm_volume": volume, "narration_volume": narration_volume,
                                   "cue_volume": cue_volume, "fade_in_seconds": fade_in,
                                   "fade_out_seconds": fade_out,
                                   "enabled": bool(enabled and (state.get("background_audio_path") or has_valid_chapter_track)),
                                   "updated_at": saved_at}
        state["modified_at"] = saved_at
        save_state(project.folder, state)
        return dict(state["sound_manifest"])

    def _sound_chapter_bgm_get(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Return real chapter records and the persisted BGM policy/overrides."""
        project = self._active_project()
        state = load_state(project.folder)
        catalog = {str(row["path"]): row for row in self._sound_catalog({})}
        stored = state.get("chapter_bgm_overrides")
        if not isinstance(stored, dict):
            stored = {}
        saved_strategy = str(
            state.get("chapter_bgm_strategy") or ("custom" if stored else "same")
        ).strip().lower()
        saved_mode = str(state.get("background_audio_mode") or (
            "manual" if state.get("background_audio_path") or
            (saved_strategy in {"custom", "chapter-based", "chapter_based", "chapter"} and stored)
            else "off"
        )).strip().lower()
        default_path = str(state.get("background_audio_path") or state.get("background_audio_preferred_path") or "").strip()
        bgm_enabled = bool(state.get("background_audio_enabled", saved_mode != "off")) and saved_mode != "off"
        last_manifest = state.get("sound_manifest") if isinstance(state.get("sound_manifest"), dict) else {}
        last_saved_at = state.get("sound_design_saved_at") or last_manifest.get("updated_at")
        chapters_by_number = {str(chapter.number): chapter for chapter in project.chapters}
        migrated = dict(stored)
        # Promote legacy numeric assignments to stable IDs when the project model
        # provides them. Number-only adapters remain supported during migration.
        for number_key, chapter in chapters_by_number.items():
            identity = str(getattr(chapter, "chapter_id", "") or "").strip()
            legacy_value = stored.get(number_key)
            if identity and identity not in migrated and isinstance(legacy_value, dict):
                migrated[identity] = dict(legacy_value)
        if migrated != stored:
            state["chapter_bgm_overrides"] = migrated
            save_state(project.folder, state)
            stored = migrated
        overrides: dict[str, dict[str, Any]] = {}
        for chapter in project.chapters:
            number_key = str(chapter.number)
            identity = str(getattr(chapter, "chapter_id", "") or "").strip()
            key = identity or number_key
            value = stored.get(key)
            if not isinstance(value, dict):
                value = stored.get(number_key, {})
            # Do not manufacture a visible "No BGM" override for chapters
            # with no saved assignment; an empty object is not a saved rule.
            if not isinstance(value, dict) or not value:
                continue
            row = dict(value)
            raw_path = str(row.get("path") or "")
            track = catalog.get(raw_path)
            available = bool(track and str(track.get("role") or "music").casefold() != "cue" and Path(raw_path).is_file())
            row["path"] = raw_path if available else None
            row["title"] = track["title"] if available else None
            row["available"] = available if row.get("rule") == "custom" else True
            overrides[key] = row
            # Preserve the number-key contract for older UI callers. The
            # adapter prefers the stable key whenever it is available.
            overrides[number_key] = row
        default_track = catalog.get(default_path)
        default_available = bool(default_track and str(default_track.get("role") or "music").casefold() != "cue"
                                 and Path(default_path).is_file())
        return {
            "strategy": saved_strategy,
            "default_path": default_path or None,
            "default_available": default_available,
            "background_audio_mode": saved_mode,
            "bgm_enabled": bgm_enabled,
            "last_saved_at": last_saved_at,
            "default_volume": max(0.0, min(0.50, float(state.get("background_audio_volume") if state.get("background_audio_volume") is not None else 0.18))),
            "narration_volume": max(0.0, min(1.0, float(state.get("narration_audio_volume") if state.get("narration_audio_volume") is not None else 1.0))),
            "cue_volume": max(0.0, min(0.50, float(state.get("sound_cue_volume") if state.get("sound_cue_volume") is not None else 0.25))),
            "fade_in_seconds": float(state.get("background_audio_fade_in") if state.get("background_audio_fade_in") is not None else 2.0),
            "fade_out_seconds": float(state.get("background_audio_fade_out") if state.get("background_audio_fade_out") is not None else 3.0),
            "overrides": overrides,
            "explicit_chapter_track_count": len({
                str(value.get("path") or "").strip()
                for value in stored.values()
                if isinstance(value, dict) and value.get("rule") == "custom"
                and str(value.get("path") or "").strip()
            }),
            "chapters": [
                {
                    "number": chapter.number,
                    "title": chapter.title,
                    "chapter_id": getattr(chapter, "chapter_id", None),
                }
                for chapter in project.chapters
            ],
        }

    def _sound_chapter_bgm_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist the selected chapter's BGM rule, or change the book-wide strategy."""
        project = self._active_project()
        state = load_state(project.folder)
        strategy = str(payload.get("strategy") or "").strip().lower()
        prior_overrides = state.get("chapter_bgm_overrides") if isinstance(state.get("chapter_bgm_overrides"), dict) else {}
        prior_strategy = str(state.get("chapter_bgm_strategy") or ("custom" if prior_overrides else "same")).lower()
        prior_mode = str(state.get("background_audio_mode") or (
            "manual" if state.get("background_audio_path") or
            (prior_strategy in {"custom", "chapter-based", "chapter_based", "chapter"} and prior_overrides)
            else "off"
        )).lower()
        master_enabled = bool(state.get("background_audio_enabled", prior_mode != "off")) and prior_mode != "off"
        if strategy:
            if strategy in {"chapter-based", "chapter_based", "chapter"}:
                strategy = "custom"
            if strategy not in {"same", "custom"}:
                raise ValueError("Choose Same BGM or Chapter-Based BGM.")
            state["chapter_bgm_strategy"] = strategy
            # Keep chapter assignments while Same BGM is active. The assembler
            # ignores them in this strategy, but users must get them back when
            # switching to Chapter-Based BGM again.
            # Restore the separately saved book-default track when returning to
            # Same BGM; Chapter-Based mode clears the active path but keeps the preference.
            if strategy == "same":
                preferred = str(state.get("background_audio_preferred_path") or state.get("background_audio_path") or "").strip()
                catalog_paths = {str(row["path"]) for row in self._sound_catalog({})}
                if preferred:
                    state["background_audio_preferred_path"] = preferred
                if master_enabled and preferred and preferred in catalog_paths and Path(preferred).is_file():
                    state["background_audio_path"] = preferred
                else:
                    state["background_audio_path"] = ""
            else:
                # Chapter-Based BGM is mutually exclusive with the book default.
                # Preserve the preference for switching back, but never leave it
                # active in the generation path while chapter-specific BGM is selected.
                preferred = str(state.get("background_audio_preferred_path") or state.get("background_audio_path") or "").strip()
                state["background_audio_preferred_path"] = preferred
                state["background_audio_path"] = ""
            # Strategy changes must respect the global BGM/Voice Only control.
            state["background_audio_enabled"] = master_enabled
            state["background_audio_mode"] = "manual" if master_enabled else "off"
            saved_at = self._now()
            state["modified_at"] = saved_at
            state["sound_design_saved_at"] = saved_at
            save_state(project.folder, state)
            return self._sound_chapter_bgm_get({})
        chapter_id = str(payload.get("chapter_id") or "").strip()
        if chapter_id:
            chapter = next(
                (item for item in project.chapters if str(item.chapter_id) == chapter_id),
                None,
            )
            if chapter is None:
                raise ValueError("The selected chapter has changed. Refresh Chapter Studio before saving BGM.")
            number = chapter.number
        else:
            try:
                number = int(payload.get("number"))
            except (TypeError, ValueError):
                raise ValueError("Choose a valid chapter before saving its BGM.")
            chapter = next((item for item in project.chapters if item.number == number), None)
            if chapter is None:
                raise ValueError("The selected chapter no longer exists. Refresh Chapter Studio.")
        saved_strategy = str(
            state.get("chapter_bgm_strategy") or ("custom" if state.get("chapter_bgm_overrides") else "same")
        ).strip().lower()
        if saved_strategy not in {"custom", "chapter-based", "chapter_based", "chapter"}:
            raise ValueError("Switch to Chapter-Based BGM before saving a chapter assignment.")
        rule = str(payload.get("rule") or "none").strip().lower()
        # Migrate stale legacy "default" selections to silence under
        # Chapter-Based BGM; book-default fallback is not allowed in this mode.
        if rule == "default":
            rule = "none"
        if rule not in {"custom", "none"}:
            raise ValueError("Choose a custom track or No BGM for this chapter.")
        path = None
        title = None
        if rule == "custom":
            raw_path = str(payload.get("path") or "").strip()
            selected = Path(raw_path).expanduser().resolve() if raw_path else None
            catalog = {str(row["path"]): row for row in self._sound_catalog({})}
            row = catalog.get(str(selected)) if selected else None
            if selected is None or not selected.is_file() or row is None or str(row.get("role") or "music").casefold() == "cue":
                raise ValueError("Choose a music track from the local Music Library catalogue.")
            path, title = str(selected), str(row["title"])
        try:
            volume = max(0.0, min(0.50, float(payload.get("volume", 0.18))))
        except (TypeError, ValueError):
            raise ValueError("Chapter BGM volume must be between 0 and 50 percent.")
        start_offset = str(payload.get("start_offset") or "immediate").strip().lower()
        if start_offset not in {"immediate", "after_first_paragraph", "after_10_seconds"}:
            raise ValueError("Choose a supported chapter BGM start offset.")
        end_behavior = str(payload.get("end_behavior") or "fade_before_end").strip().lower()
        if end_behavior not in {"fade_before_end", "continue_to_transition", "stop_immediately"}:
            raise ValueError("Choose a supported chapter BGM end behavior.")
        overrides = state.get("chapter_bgm_overrides")
        if not isinstance(overrides, dict):
            overrides = {}
        else:
            overrides = dict(overrides)
        chapter_identity = str(getattr(chapter, "chapter_id", "") or "").strip()
        identity_key = chapter_identity or str(number)
        if identity_key not in overrides and isinstance(overrides.get(str(number)), dict):
            overrides[identity_key] = dict(overrides[str(number)])
        overrides[identity_key] = {
            "rule": rule, "path": path, "volume": volume,
            "start_offset": start_offset, "end_behavior": end_behavior,
        }
        state["chapter_bgm_overrides"] = overrides
        state["chapter_bgm_strategy"] = "custom"
        current_mode = str(state.get("background_audio_mode") or (
            "manual" if state.get("background_audio_path") or overrides else "off"
        )).lower()
        master_enabled = bool(state.get("background_audio_enabled", current_mode != "off")) and current_mode != "off"
        state["background_audio_enabled"] = master_enabled
        state["background_audio_mode"] = "manual" if master_enabled else "off"
        saved_at = self._now()
        state["modified_at"] = saved_at
        state["sound_design_saved_at"] = saved_at
        save_state(project.folder, state)
        return {"saved": True, "number": number, "chapter_id": getattr(chapter, "chapter_id", None), "title": chapter.title,
                "rule": rule, "path": path, "track_title": title,
                "strategy": "custom", "override_count": len(overrides)}

    def _sound_cues_get(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Rehydrate saved cue assignments even when the catalogue is refreshed after restart."""
        from app.audio.library import audio_asset_role, metadata_for

        project = self._active_project()
        state = load_state(project.folder)
        stored = state.get("sound_cues")
        cues = stored if isinstance(stored, dict) else {}
        legacy_fields = {
            "opening": "opening_cue_path",
            "chapter": "page_turn_cue_path",
            "closing": "ending_cue_path",
        }

        def path_key(value: Any) -> str:
            try:
                return str(Path(str(value)).expanduser().resolve()).casefold()
            except (OSError, RuntimeError, ValueError):
                return str(value or "").strip().replace("\\\\", "/").casefold()

        catalog = {}
        for row in self._sound_catalog({}):
            raw_catalog_path = row.get("path")
            if raw_catalog_path:
                catalog[path_key(raw_catalog_path)] = row

        result = {}
        for slot in ("opening", "chapter", "closing"):
            # Prefer the canonical three-slot map but keep old per-slot projects
            # readable when the map exists but a migrated entry is empty.
            raw = cues.get(slot) or state.get(legacy_fields[slot])
            path = str(raw).strip() if raw else ""
            if not path:
                result[slot] = {
                    "path": None, "title": None, "available": False,
                    "assigned": False, "missing": False,
                }
                continue

            candidate = Path(path).expanduser()
            resolved = candidate.resolve()
            row = catalog.get(path_key(path))
            try:
                metadata = metadata_for(resolved) if resolved.is_file() else {}
                persisted_role = audio_asset_role(resolved) if resolved.is_file() else ""
            except (OSError, ValueError, TypeError, RuntimeError):
                metadata = {}
                persisted_role = ""
            role = str((row or {}).get("role") or persisted_role or "").casefold()
            available = bool(resolved.is_file() and role == "cue")
            title = (
                str(row.get("title") or "") if row and role == "cue" else
                str(metadata.get("title") or resolved.stem)
            )
            # Keep the saved path visible even when its asset is currently
            # missing/unindexed. The UI can show a missing-asset state and let
            # the user reassign it; silently returning null looked like data loss.
            result[slot] = {
                "path": str(resolved) if resolved.is_file() else path,
                "title": title or None,
                "available": available,
                "assigned": True,
                "missing": not available,
            }
        return result

    def _sound_cues_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist one cue assignment and update the supported generation cue fields."""
        slot = str(payload.get("slot") or "").strip().lower()
        if slot not in {"opening", "chapter", "closing"}:
            raise ValueError("Choose Opening, Next Chapter, or Closing audio.")
        raw = str(payload.get("path") or "").strip()
        selected_path = None
        selected_title = None
        if raw:
            selected = Path(raw).expanduser().resolve()
            catalog = {str(row["path"]): row for row in self._sound_catalog({})}
            row = catalog.get(str(selected))
            if not selected.is_file() or row is None or str(row.get("role") or "music").casefold() != "cue":
                raise ValueError("Choose a cue clip from the local Sound Design cue catalogue.")
            from app.audio.library import probe_audio_duration_seconds
            # Metadata can be stale after a file is replaced; check the actual
            # audio selected for this fixed slot before writing the book state.
            duration_seconds = probe_audio_duration_seconds(selected)
            if float(duration_seconds) > 5.0:
                raise ValueError("Opening, next-chapter, and closing cue clips must be 5 seconds or shorter. Import longer tracks into Music Library and assign them as BGM.")
            selected_path, selected_title = str(selected), str(row["title"])
        project = self._active_project()
        state = load_state(project.folder)
        cues = state.get("sound_cues")
        if not isinstance(cues, dict):
            cues = {
                "opening": state.get("opening_cue_path"),
                "chapter": state.get("page_turn_cue_path"),
                "closing": state.get("ending_cue_path"),
            }
        cues[slot] = selected_path
        state["sound_cues"] = {key: cues.get(key) for key in ("opening", "chapter", "closing")}
        state["chapter_transition_sound"] = any(cues.get(key) for key in ("opening", "chapter", "closing"))
        # Retire the historical fourth fixed cue from existing project state.
        state["scene_transition_cue_path"] = None
        if slot == "opening":
            state["opening_cue_path"] = selected_path
        elif slot == "chapter":
            state["page_turn_cue_path"] = selected_path
        elif slot == "closing":
            state["ending_cue_path"] = selected_path
        saved_at = self._now()
        state["modified_at"] = saved_at
        state["sound_design_saved_at"] = saved_at
        save_state(project.folder, state)
        return {"saved": True, "slot": slot, "path": selected_path, "title": selected_title,
                "generation_supported": True}

    def _sound_cues_clear(self, _payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        state = load_state(project.folder)
        state["sound_cues"] = {"opening": None, "chapter": None, "closing": None}
        state["opening_cue_path"] = None
        state["page_turn_cue_path"] = None
        state["scene_transition_cue_path"] = None
        state["ending_cue_path"] = None
        state["chapter_transition_sound"] = False
        saved_at = self._now()
        state["modified_at"] = saved_at
        state["sound_design_saved_at"] = saved_at
        save_state(project.folder, state)
        return {"saved": True, "cleared": ["opening", "chapter", "closing"]}

    @Slot(str, result=bool)
    def report_frontend_diagnostic(self, payload_json: str) -> bool:
        """Write a bounded frontend runtime diagnostic to the local application log."""
        try:
            payload = json.loads(str(payload_json or "{}"))
        except (TypeError, ValueError):
            log.warning("Premium V2 frontend reported an invalid diagnostic payload")
            return False
        if not isinstance(payload, dict):
            return False
        kind = str(payload.get("kind") or "frontend-event")[:40]
        message = str(payload.get("message") or "")[:2500].replace("\\x00", "")
        source = str(payload.get("source") or "")[:600].replace("\\x00", "")
        stack = str(payload.get("stack") or "")[:3000].replace("\\x00", "")
        try:
            line = max(0, min(10_000_000, int(payload.get("line") or 0)))
        except (TypeError, ValueError, OverflowError):
            line = 0
        if kind == "startup-progress":
            raw_progress = payload.get("progress")
            try:
                progress = None if raw_progress is None else max(0, min(100, int(raw_progress)))
            except (TypeError, ValueError, OverflowError):
                progress = None
            window = self.parent()
            update = getattr(window, "_update_startup_progress", None)
            if callable(update):
                update(message or "Preparing the local studio…", progress)
            return True
        if kind == "frontend-ready":
            log.info("Premium V2 frontend initialized successfully")
            window = self.parent()
            reveal = getattr(window, "_on_frontend_ready", None)
            if callable(reveal):
                reveal()
            return True
        if kind in {"javascript-error", "unhandled-rejection", "adapter-start-failed", "backend-bridge-failed"}:
            log.error("Premium V2 frontend %s: %s (source=%s, line=%s)%s",
                      kind, message or "(no message)", source or "(inline)", line,
                      ("\\n" + stack) if stack else "")
        else:
            log.warning("Premium V2 frontend %s: %s (source=%s, line=%s)",
                        kind, message or "(no message)", source or "(inline)", line)

        # A top-level adapter failure means essential frontend wiring/hydration
        # did not finish. Show the native recovery surface immediately instead
        # of leaving the user on the loading screen until the watchdog expires.
        if kind in {"backend-bridge-failed", "adapter-start-failed"}:
            window = self.parent()
            show_failure = getattr(window, "_show_web_failure", None)
            if callable(show_failure) and not getattr(window, "_frontend_ready", False):
                show_failure(
                    (
                        "The local desktop bridge could not connect. "
                        if kind == "backend-bridge-failed"
                        else "The Premium V2 interface could not complete startup. "
                    ) +
                    "Your local project files have not been deleted. Details: " +
                    (message or "Startup failed without a diagnostic message.")
                )
        return True

    def _storage_root_map(self) -> dict[str, tuple[str, Path, Path]]:
        from app.core.paths import (
            library_root, audiobooks_root, models_root, runtimes_root,
            model_cache_root, temporary_root, default_library_root,
            default_audiobooks_root, default_models_root, default_runtimes_root,
            default_model_cache_root, default_temporary_root,
        )
        return {
            "library": ("storage/library_root", library_root(), default_library_root()),
            "audio_assets": ("storage/audio_assets_root", audiobooks_root(), default_audiobooks_root()),
            "models": ("storage/models_root", models_root(), default_models_root()),
            "runtime": ("storage/runtime_root", runtimes_root(), default_runtimes_root()),
            "model_cache": ("storage/model_cache_root", model_cache_root(), default_model_cache_root()),
            "temporary": ("storage/temporary_root", temporary_root(), default_temporary_root()),
        }

    def _storage_get(self, _payload: dict[str, Any]) -> dict[str, Any]:
        from app.core.storage_migration import inventory_storage_root
        rows = []
        for kind, (key, current, default) in self._storage_root_map().items():
            path = Path(current).expanduser()
            info = inventory_storage_root(path, include_hashes=False)
            capacity = {"total_bytes": 0, "used_bytes": 0, "free_bytes": 0}
            if info.get("available"):
                try:
                    usage = shutil.disk_usage(str(path))
                    capacity = {"total_bytes": int(usage.total),
                                "used_bytes": max(0, int(usage.total) - int(usage.free)),
                                "free_bytes": int(usage.free)}
                except OSError:
                    pass
            rows.append({"kind": kind, "settings_key": key, "path": str(path),
                         "default_path": str(default), "available": bool(info.get("available")),
                         "file_count": int(info.get("file_count", 0)),
                         "component_bytes": int(info.get("total_bytes", 0)), **capacity})
        pending_cleanup = []
        journal_root = app_root() / "Settings" / "Storage Migrations"
        if journal_root.is_dir():
            from app.core.storage_migration import read_migration_journal
            for journal_path in sorted(journal_root.glob("ryu-storage-migration-*.json")):
                try:
                    journal = read_migration_journal(journal_path)
                except Exception:
                    continue
                if str(journal.get("state") or "") == "complete_source_retained":
                    pending_cleanup.append({
                        "journal_name": journal_path.name,
                        "source": str(journal.get("source") or ""),
                        "destination": str(journal.get("destination") or ""),
                        "file_count": int(journal.get("file_count") or 0),
                        "total_bytes": int(journal.get("total_bytes") or 0),
                    })
        return {"roots": rows, "pending_cleanup": pending_cleanup, "restart_required": True}

    def _validate_storage_root_separation(
        self, kind: str, destination: Path,
        roots: dict[str, tuple[str, Path, Path]],
    ) -> None:
        def overlaps(left: Path, right: Path) -> bool:
            try:
                a = left.resolve()
                b = right.resolve()
            except OSError:
                a = left.absolute()
                b = right.absolute()
            return a == b or a in b.parents or b in a.parents

        # Validate this first so a cache selected as a parent of Models gets
        # the precise safety error rather than a generic Runtime overlap.
        if kind == "model_cache":
            model_root = Path(roots["models"][1]).expanduser()
            selected_cache = destination.expanduser()
            try:
                model_root = model_root.resolve()
                selected_cache = selected_cache.resolve()
            except OSError:
                model_root = model_root.absolute()
                selected_cache = selected_cache.absolute()
            if selected_cache == model_root or selected_cache in model_root.parents:
                raise ValueError(
                    "Model Cache may be located inside Models, but cannot replace or contain the Models root."
                )

        protected_by_kind = {
            "temporary": {"library", "audio_assets", "models", "runtime", "model_cache"},
            "library": {"audio_assets", "models", "runtime", "model_cache", "temporary"},
            "audio_assets": {"library", "models", "runtime", "model_cache", "temporary"},
            # Model cache may be nested inside Models, but never overlap Runtime.
            "models": {"library", "audio_assets", "runtime", "temporary"},
            "runtime": {"library", "audio_assets", "models", "model_cache", "temporary"},
            "model_cache": {"library", "audio_assets", "runtime", "temporary"},
        }
        conflicts = []
        for other in protected_by_kind.get(kind, set()):
            other_path = Path(roots[other][1]).expanduser()
            try:
                same_root = destination.expanduser().resolve() == other_path.resolve()
                configured_models = Path(roots["models"][1]).expanduser().resolve()
                configured_runtime = Path(roots["runtime"][1]).expanduser().resolve()
                selected_path = destination.expanduser().resolve()
                other_resolved = other_path.resolve()
            except OSError:
                same_root = destination.expanduser().absolute() == other_path.absolute()
                configured_models = Path(roots["models"][1]).expanduser().absolute()
                configured_runtime = Path(roots["runtime"][1]).expanduser().absolute()
                selected_path = destination.expanduser().absolute()
                other_resolved = other_path.absolute()

            # Legacy installs share the Models base directory for separate
            # weight/runtime subdirectories, with HF cache nested under it.
            legacy_shared_base = (
                {kind, other} == {"models", "runtime"}
                and same_root
                and configured_models == configured_runtime
            )
            legacy_shared_cache = (
                configured_models == configured_runtime
                and (
                    (kind == "model_cache" and other == "runtime"
                     and selected_path != configured_models and configured_models in selected_path.parents)
                    or
                    (kind == "runtime" and other == "model_cache"
                     and selected_path == configured_models and other_resolved != configured_models
                     and configured_models in other_resolved.parents)
                )
            )
            if not (legacy_shared_base or legacy_shared_cache) and overlaps(destination, other_path):
                conflicts.append(other)

        if conflicts:
            raise ValueError(
                "Storage roots must remain separate; conflicting roots: "
                + ", ".join(sorted(conflicts))
            )

    def _storage_choose_root(self, payload: dict[str, Any]) -> dict[str, Any]:
        from app.core.storage_migration import migrate_storage_root, inventory_storage_root
        from app.core.paths import app_root
        roots = self._storage_root_map()
        kind = str(payload.get("kind") or "").strip().casefold()
        if kind not in roots:
            raise ValueError("Choose a supported storage location.")
        key, current, default = roots[kind]
        if payload.get("use_default") is True:
            destination = Path(default).expanduser()
            destination.mkdir(parents=True, exist_ok=True)
        else:
            selected = QFileDialog.getExistingDirectory(
                None, "Choose " + kind.replace("_", " ").title() + " Storage Folder", str(current))
            if not selected:
                return {"cancelled": True}
            destination = Path(selected).expanduser()
        if not destination.is_absolute() or not destination.is_dir():
            raise ValueError("The selected storage folder must exist and be an absolute path.")
        probe = destination / (".ryu-storage-probe-" + uuid.uuid4().hex)
        try:
            probe.write_bytes(b"")
        except OSError as exc:
            raise ValueError("The selected storage folder is not writable: " + str(exc)) from exc
        finally:
            probe.unlink(missing_ok=True)
        source = Path(current).expanduser()
        def overlaps(left: Path, right: Path) -> bool:
            try:
                a = left.resolve()
                b = right.resolve()
            except OSError:
                a = left.absolute()
                b = right.absolute()
            return a == b or a in b.parents or b in a.parents
        self._validate_storage_root_separation(kind, destination, roots)
        if not source.is_dir():
            raise RuntimeError("The current storage location is unavailable. Reconnect its drive before changing the configured path; existing inventory must not be silently orphaned.")
        try:
            if source.resolve() == destination.resolve():
                return {"saved": True, "path": str(source), "unchanged": True}
        except OSError:
            pass
        try:
            has_data = source.is_dir() and any(source.iterdir())
        except OSError as exc:
            raise ValueError("The current storage folder cannot be inspected safely: " + str(exc)) from exc
        if not has_data:
            self.settings.setValue(key, str(destination))
            self.settings.sync()
            if self.settings.status() != QSettings.Status.NoError or str(self.settings.value(key, "")) != str(destination):
                raise RuntimeError("Windows did not confirm the storage location setting.")
            return {"saved": True, "path": str(destination), "restart_required": True}
        with self._jobs_lock:
            active = [(job_id, job) for job_id, job in self._jobs.items()
                      if str(job.get("state") or "").casefold() in {"queued", "running"}]
        if active:
            labels = ", ".join(str(job.get("title") or job.get("type") or job_id) for job_id, job in active[:4])
            raise RuntimeError("Storage migration is blocked while active work is running: " + labels)
        from app.core.storage_migration import prepare_migration
        from PySide6.QtWidgets import QMessageBox
        preflight = prepare_migration(
            source, destination, reserve_bytes=512 * 1024 * 1024,
            journal_dir=app_root() / "Settings" / "Storage Migrations",
        )
        gib = 1024 ** 3
        question = (
            "A verified migration will copy " + str(preflight.file_count) + " files ("
            + f"{preflight.total_bytes / gib:.2f} GB) from:\n" + str(source)
            + "\n\nto:\n" + str(destination)
            + f"\n\nDestination free space: {preflight.free_bytes / gib:.2f} GB"
            + "\nA 512 MB safety reserve is required. The original source will be retained after migration.\n\nStart migration?"
        )
        answer = QMessageBox.question(
            None, "Confirm verified storage migration", question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return {"cancelled": True}
        job_id = self._new_job("storage-migration", "Migrate " + kind.replace("_", " ").title() + " storage",
                               "Verified copy, integrity check, root switch and rollback protection")
        self._job_update(job_id, state="running", started_at=self._now(), progress=1,
                         stage="Preparing verified storage migration", message="Migration started.")
        def worker() -> None:
            try:
                def persist(path: Path) -> None:
                    settings = QSettings("RyuBlanc", "Ryu's Audiobook")
                    settings.setValue(key, str(path))
                    settings.sync()
                    if settings.status() != QSettings.Status.NoError or str(settings.value(key, "")) != str(path):
                        raise RuntimeError("Windows did not confirm the storage setting write.")
                def busy(_path: Path) -> bool:
                    with self._jobs_lock:
                        return any(other_id != job_id and
                                   str(job.get("state") or "").casefold() in {"queued", "running"}
                                   for other_id, job in self._jobs.items())
                plan = migrate_storage_root(
                    source, destination, persist_root=persist,
                    validate_root=lambda path: bool(inventory_storage_root(path).get("available")),
                    is_busy=busy, journal_dir=app_root() / "Settings" / "Storage Migrations",
                    settings_key=key,
                    progress=lambda stage, done, total: self._job_update(
                        job_id, state="running", progress=max(1, min(98, int(done * 95 / max(1, total)))),
                        stage=stage.title() + ": " + str(done) + "/" + str(total) + " files",
                        message="Verified " + str(done) + " of " + str(total) + " files"),
                )
                self._job_update(job_id, state="completed", progress=100, stage="Migration complete",
                    message="New storage root verified. Original source retained for explicit cleanup.",
                    result={"source": str(plan.source), "destination": str(plan.destination),
                            "file_count": plan.file_count, "total_bytes": plan.total_bytes,
                            "settings_key": key, "restart_required": True}, error=None, recoverable=False)
            except Exception as exc:
                log.exception("Premium V2 storage migration failed for %s", kind)
                self._job_update(job_id, state="failed", stage="Migration failed",
                    message="Storage migration failed safely; original data was retained.",
                    error={"code": "storage_migration_failed", "message": str(exc)}, recoverable=True)
        threading.Thread(target=worker, daemon=True, name="RyuStorageMigration").start()
        return {"job_id": job_id, "state": "running", "migration": True}

    def _storage_open_root(self, payload: dict[str, Any]) -> dict[str, Any]:
        kind = str(payload.get("kind") or "").strip().casefold()
        roots = self._storage_root_map()
        if kind not in roots:
            raise ValueError("Choose a supported storage location.")
        path = Path(roots[kind][1]).expanduser()
        if not path.is_dir():
            raise FileNotFoundError("Storage location unavailable: " + str(path))
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        return {"opened": True, "path": str(path)}

    def _storage_copy_root(self, payload: dict[str, Any]) -> dict[str, Any]:
        kind = str(payload.get("kind") or "").strip().casefold()
        roots = self._storage_root_map()
        if kind not in roots:
            raise ValueError("Choose a supported storage location.")
        path = str(Path(roots[kind][1]).expanduser())
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("The desktop clipboard is unavailable.")
        app.clipboard().setText(path)
        return {"copied": True, "path": path}

    def _storage_cleanup_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        from app.core.paths import app_root
        from app.core.storage_migration import read_migration_journal, cleanup_migrated_source
        from PySide6.QtWidgets import QMessageBox
        journal_root = (app_root() / "Settings" / "Storage Migrations").resolve()
        name = Path(str(payload.get("journal_name") or "")).name
        if not name or not name.startswith("ryu-storage-migration-") or not name.endswith(".json"):
            raise ValueError("Choose a valid retained migration journal.")
        journal_path = journal_root / name
        if journal_path.is_symlink() or not journal_path.is_file() or journal_path.resolve().parent != journal_root:
            raise FileNotFoundError("The selected migration journal is unavailable.")
        with self._jobs_lock:
            active = [job for job in self._jobs.values()
                      if str(job.get("state") or "").casefold() in {"queued", "running"}]
        if active:
            raise RuntimeError("Retained-source cleanup is blocked while application jobs are active.")
        journal = read_migration_journal(journal_path)
        if str(journal.get("state") or "") != "complete_source_retained":
            raise RuntimeError("This migration is not in a verified source-retained state and cannot be cleaned up.")
        source = str(journal.get("source") or "")
        destination = str(journal.get("destination") or "")
        gib = 1024 ** 3
        answer = QMessageBox.question(
            None, "Confirm retained source cleanup",
            "Delete the retained source copy only after rechecking every file against the active destination?\n\n"
            + "Source: " + source + "\nVerified destination: " + destination
            + "\nFiles: " + str(journal.get("file_count", 0))
            + f" · {int(journal.get('total_bytes') or 0) / gib:.2f} GB"
            + "\n\nIf any path, size or SHA-256 check fails, the source will be preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return {"cancelled": True}
        protected = tuple(Path(item[1]).expanduser() for item in self._storage_root_map().values())
        result = cleanup_migrated_source(journal_path, protected_roots=protected)
        return {"deleted": True, **result}

    def _storage_cleanup_temp(self, _payload: dict[str, Any]) -> dict[str, Any]:
        from app.core.storage_migration import safe_cleanup
        from app.core.paths import (
            models_root, model_cache_root, temporary_root, runtimes_root,
            library_root, audiobooks_root,
        )
        from PySide6.QtWidgets import QMessageBox
        with self._jobs_lock:
            active = [job for job in self._jobs.values()
                      if str(job.get("state") or "").casefold() in {"queued", "running"}]
        if active:
            raise RuntimeError("Temporary/cache cleanup is blocked while application jobs are active.")
        cache = model_cache_root()
        temporary = temporary_root()
        library = library_root()
        exports = audiobooks_root()
        # The cache is intentionally nested under Models in the legacy layout.
        # Do not protect its parent Models/Runtime root while cleaning the
        # explicitly configured cache root; allowlist and root boundaries still
        # keep model weights outside the cache untouched.
        cache_preview = safe_cleanup(
            cache_roots=(cache,), dry_run=True,
            protected_paths=(temporary, library, exports),
        )
        temporary_preview = safe_cleanup(
            temporary_roots=(temporary,), dry_run=True,
            protected_paths=(models_root(), runtimes_root(), cache, library, exports),
        )
        candidates = list(dict.fromkeys(
            list(cache_preview["candidates"]) + list(temporary_preview["candidates"])
        ))
        candidate_bytes = int(cache_preview["candidate_bytes"]) + int(temporary_preview["candidate_bytes"])
        if not candidates:
            return {"cleaned": False, "candidate_count": 0, "candidate_bytes": 0,
                    "candidates": [], "removed": []}
        gib = 1024 ** 3
        target_lines = "\n".join(str(path) for path in candidates)
        answer = QMessageBox.question(
            None, "Review safe cache and temporary cleanup",
            "Dry-run estimate: " + str(len(candidates)) + " eligible app-owned entries · "
            + f"{candidate_bytes / gib:.2f} GB"
            + "\n\nExact targets:\n" + target_lines
            + "\n\nOnly immediate staging/downloads/temporary/tmp entries under the configured cache and temporary roots are eligible. "
            "Model weights, provider runtimes, projects, source books, exports and voice data are not cleanup targets. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return {"cancelled": True, "candidate_count": len(candidates),
                    "candidate_bytes": candidate_bytes, "candidates": candidates, "removed": []}
        cache_result = safe_cleanup(
            cache_roots=(cache,), dry_run=False,
            protected_paths=(temporary, library, exports),
        )
        temporary_result = safe_cleanup(
            temporary_roots=(temporary,), dry_run=False,
            protected_paths=(models_root(), runtimes_root(), cache, library, exports),
        )
        removed = list(dict.fromkeys(
            list(cache_result["removed"]) + list(temporary_result["removed"])
        ))
        return {"cleaned": True, "candidate_count": len(candidates),
                "candidate_bytes": candidate_bytes, "candidates": candidates, "removed": removed}

    def _settings_get(self, _payload: dict[str, Any]) -> dict[str, Any]:
        self.settings.sync()
        try:
            player_rate = float(self.settings.value("player/playback_rate", 1.0))
        except (TypeError, ValueError, OverflowError):
            player_rate = 1.0
        if not math.isfinite(player_rate) or not 0.5 <= player_rate <= 2.0:
            player_rate = 1.0
        try:
            player_volume = float(self.settings.value("player/playback_volume", 0.8))
        except (TypeError, ValueError, OverflowError):
            player_volume = 0.8
        if not math.isfinite(player_volume) or not 0.0 <= player_volume <= 1.0:
            player_volume = 0.8
        return {
            "theme": self.settings.value("ui/theme", "dark"),
            "effects": self.settings.value("ui/effects", "high"),
            "reduce_motion": self.settings.value("ui/reduce_motion", False, type=bool),
            "accent": self.settings.value("ui/accent", "crimson"),
            "interface_scale": self.settings.value("ui/interface_scale", 100),
            "text_scale": self.settings.value("ui/text_scale", 100),
            "window_size": self.settings.value("ui/window_size", "auto"),
            "player_rate": player_rate,
            "player_volume": player_volume,
            "storage_root": str(app_root()),
            "library_root": str(library_root()),
            "output_root": str(audiobooks_root()),
            "bitrate": int(self.settings.value(
                "production/bitrate",
                self.settings.value("audio/default_bitrate", 256),
            ) or 256),
            "concurrency": max(1, min(3, int(self.settings.value("production/concurrency", 1) or 1))),
            "qwen_backend": str(self.settings.value("qwen/backend_preference", "automatic") or "automatic"),
            "qwen_low_memory": bool(self.settings.value("qwen/low_memory_mode", False, type=bool)),
        }


class DiagnosticQWebEnginePage(QWebEnginePage):
    """Capture JavaScript console failures for diagnosis of blank/frozen UI states."""

    def javaScriptConsoleMessage(self, level, message: str, line_number: int, source_id: str) -> None:
        source = str(source_id or "(inline)")
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            log.error("Premium V2 JavaScript console error: %s (source=%s, line=%s)",
                      str(message)[:2000], source[:600], int(line_number))
        elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel:
            log.warning("Premium V2 JavaScript console warning: %s (source=%s, line=%s)",
                        str(message)[:1200], source[:600], int(line_number))
        super().javaScriptConsoleMessage(level, message, line_number, source_id)


class StableQWebEngineView(QWebEngineView):
    """WebEngine surface that blocks browser-style zoom shortcuts and Ctrl-wheel."""

    _ZOOM_KEYS = {
        Qt.Key.Key_Plus, Qt.Key.Key_Equal, Qt.Key.Key_Minus,
        Qt.Key.Key_Underscore, Qt.Key.Key_0,
    }

    def keyPressEvent(self, event) -> None:
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier) and event.key() in self._ZOOM_KEYS:
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            event.accept()
            return
        super().wheelEvent(event)


class PremiumV2Window(QMainWindow):
    """Desktop host for the approved interface, with native window controls and stable sizing."""

    def __init__(self) -> None:
        super().__init__()
        path = frontend_path()
        if not path.is_file():
            raise FileNotFoundError(f"Premium V2 frontend asset is missing: {path}")
        self.setWindowTitle(f"{APP_NAME} • {full_version()}")
        # The minimum is tightened against the active display in apply_window_size().
        # A fixed 960×620 minimum overflows some high-DPI laptop work areas.
        self.setMinimumSize(640, 480)
        self.resize(1440, 900)

        self.web = StableQWebEngineView(self)
        self.web.setPage(DiagnosticQWebEnginePage(self.web))
        self.web.setZoomFactor(1.0)
        self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)

        self.bridge = PremiumV2Bridge(self)
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.bridge.close_preview_provider_cache)
        self.channel = QWebChannel(self.web.page())
        self.channel.registerObject("ryuBackend", self.bridge)
        self.web.page().setWebChannel(self.channel)
        self._renderer_restart_attempts = 0
        self._frontend_generation = 0
        self._frontend_ready = False
        self._frontend_failure_shown = False
        self._startup_progress_value = 0
        self._frontend_watchdog = QTimer(self)
        self._frontend_watchdog.setSingleShot(True)
        self._frontend_watchdog.timeout.connect(
            lambda: self._check_frontend_ready(self._frontend_generation)
        )
        # A separate short watchdog covers the bridge handshake specifically.
        # It is stopped only after the native transport reports progress 26.
        self._bridge_watchdog = QTimer(self)
        self._bridge_watchdog.setSingleShot(True)
        self._bridge_watchdog.timeout.connect(self._bridge_connect_timeout)
        self.web.loadFinished.connect(self._install_bridge)
        self.web.page().renderProcessTerminated.connect(self._handle_renderer_terminated)

        # Keep native startup and recovery surfaces visible until the actual UI
        # plus its backend bridge are ready. Showing an empty WebEngine during load
        # or retry looked like a black/frozen application to the user.
        self._web_stack = QStackedWidget(self)

        self._loading_page = QWidget(self._web_stack)
        self._loading_page.setObjectName("startupLoadingPage")
        self._loading_page.setStyleSheet("background:#080a10;color:#eef0f5;")
        loading_layout = QVBoxLayout(self._loading_page)
        loading_layout.setContentsMargins(36, 34, 36, 30)
        loading_layout.setSpacing(13)
        loading_layout.addStretch(2)

        # Use the actual bundled Ryu logo, not a placeholder drawing. Try the
        # same icon asset first, then the lossless master PNG and vector artwork.
        self._loading_logo = QLabel(self._loading_page)
        self._loading_logo.setObjectName("startupLogo")
        self._loading_logo.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self._loading_logo.setMinimumSize(132, 132)
        self._loading_logo.setMaximumSize(132, 132)
        self._loading_logo.setStyleSheet("background:transparent;border:0;")
        self._loading_logo_source = None
        self._loading_logo_pixmap = QPixmap()
        for logo_path in premium_v2_logo_candidates(path):
            candidate = QPixmap(str(logo_path))
            if not candidate.isNull():
                self._loading_logo_source = logo_path
                self._loading_logo_pixmap = candidate
                self._loading_logo.setPixmap(candidate.scaled(
                    132, 132,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
                break
        if self._loading_logo_pixmap.isNull():
            log.error("No readable Ryu logo asset was found for the startup screen: %s",
                      premium_v2_logo_candidates(path))
            self._loading_logo.setText("RYU")
            self._loading_logo.setStyleSheet(
                "background:transparent;border:0;color:#e64160;font-size:30px;font-weight:800;"
            )
        self._loading_logo.setAccessibleName("Ryu's Audiobook logo")
        loading_layout.addWidget(self._loading_logo, 0, Qt.AlignmentFlag.AlignHCenter)

        self._loading_title = QLabel(APP_NAME.upper(), self._loading_page)
        self._loading_title.setObjectName("startupTitle")
        self._loading_title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._loading_title.setStyleSheet(
            "font-size:23px;font-weight:800;letter-spacing:2px;color:#f5edf3;"
        )
        self._loading_status = QLabel("Starting the Windows interface…", self._loading_page)
        self._loading_status.setObjectName("startupStatus")
        self._loading_status.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._loading_status.setWordWrap(True)
        self._loading_status.setMinimumWidth(300)
        self._loading_status.setMaximumWidth(620)
        self._loading_status.setStyleSheet("font-size:14px;color:#b9b2c0;padding:4px 0;")
        loading_layout.addWidget(self._loading_title, 0, Qt.AlignmentFlag.AlignHCenter)
        loading_layout.addWidget(self._loading_status, 0, Qt.AlignmentFlag.AlignHCenter)

        self._loading_progress = QProgressBar(self._loading_page)
        self._loading_progress.setObjectName("startupProgress")
        # Keep startup feedback quiet: an indeterminate line signals activity
        # without displaying a guessed percentage or a determinate progress value.
        self._loading_progress.setRange(0, 0)
        self._loading_progress.setTextVisible(False)
        self._loading_progress.setFixedHeight(6)
        self._loading_progress.setMinimumWidth(300)
        self._loading_progress.setMaximumWidth(480)
        self._loading_progress.setStyleSheet(
            "QProgressBar{background:#19141d;border:1px solid #342634;border-radius:4px;}"
            "QProgressBar::chunk{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #8c1735,stop:1 #e64160);border-radius:3px;}"
        )
        loading_layout.addWidget(self._loading_progress, 0, Qt.AlignmentFlag.AlignHCenter)
        self._loading_version = QLabel(f"VERSION {full_version()}", self._loading_page)
        self._loading_version.setObjectName("startupVersion")
        self._loading_version.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._loading_version.setStyleSheet("font-size:10px;letter-spacing:1px;color:#77717f;")
        loading_layout.addWidget(self._loading_version, 0, Qt.AlignmentFlag.AlignHCenter)
        loading_layout.addStretch(3)
        self._update_startup_progress("Preparing the local studio…", 5)
        self._web_stack.addWidget(self._loading_page)
        self._web_stack.addWidget(self.web)

        self._web_error_page = QWidget(self._web_stack)
        self._web_error_page.setStyleSheet("background:#080a10;color:#eef0f5;")
        error_layout = QVBoxLayout(self._web_error_page)
        error_layout.setContentsMargins(32, 32, 32, 32)
        error_layout.addStretch(1)
        self._web_error_title = QLabel("Ryu’s Audiobook could not render the interface", self._web_error_page)
        self._web_error_title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._web_error_title.setStyleSheet("font-size:22px;font-weight:700;color:#f0f2f7;")
        self._web_error_message = QLabel("The embedded UI renderer stopped. Your project data has not been deleted. Retry loading the interface; if it repeats, check the local application log.", self._web_error_page)
        self._web_error_message.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._web_error_message.setWordWrap(True)
        self._web_error_message.setStyleSheet("font-size:14px;color:#aeb6c5;max-width:760px;")
        self._web_error_retry = QPushButton("Retry interface", self._web_error_page)
        self._web_error_retry.setStyleSheet("QPushButton{background:#bd234d;color:white;border:0;border-radius:8px;padding:11px 20px;font-weight:700;} QPushButton:hover{background:#d32a5a;}")
        self._web_error_retry.clicked.connect(self._retry_web_renderer)
        error_layout.addWidget(self._web_error_title)
        error_layout.addWidget(self._web_error_message)
        error_layout.addWidget(self._web_error_retry)
        error_layout.addStretch(1)
        self._web_stack.addWidget(self._web_error_page)
        self._web_stack.setCurrentWidget(self._loading_page)
        self.setCentralWidget(self._web_stack)

        # Prefer the approved HTML loader for the packaged desktop launch. Hold its
        # original animation until the native bridge and required data hydration
        # finish; use the native splash only if the HTML contract cannot be prepared.
        self._hosted_html_source: str | None = None
        self._hosted_html_base_url = QUrl.fromLocalFile(str(path.parent.resolve()) + os.sep)
        self._hosted_html_path: Path | None = None
        self._uses_html_startup_loader = False
        try:
            source = path.read_text(encoding="utf-8")
            self._hosted_html_source = prepare_native_host_html(
                source,
                base_url=self._hosted_html_base_url.toString(),
            )
            # Keep the HTML in a real file URL. QWebEngineView.setHtml() routes
            # the entire document through a data URL; this multi-megabyte page
            # can exceed that route's size limit and leave WebChannel unresponsive.
            # A stable per-user cache avoids setHtml()'s large data-URL path
            # and keeps the file URL stable across launches for any remaining
            # browser-local preferences. Always overwrite it from the packaged
            # source so upgrades cannot leave stale HTML behind.
            self._hosted_html_path = settings_root() / "frontend_cache" / path.name
            self._hosted_html_path.parent.mkdir(parents=True, exist_ok=True)
            self._hosted_html_path.write_text(
                self._hosted_html_source, encoding="utf-8"
            )
            self._uses_html_startup_loader = True
            self.web.load(QUrl.fromLocalFile(str(self._hosted_html_path.resolve())))
        except (OSError, FrontendAssetError):
            log.exception("Could not prepare the approved HTML startup loader; retaining native loading fallback")
            self._hosted_html_path = None
            self._hosted_html_source = None
            self._uses_html_startup_loader = False
            self.web.load(QUrl.fromLocalFile(str(path.resolve())))
        self.apply_window_size(str(QSettings("RyuBlanc", "Ryu's Audiobook").value("ui/window_size", "auto")))

    def apply_window_size(self, choice: str) -> None:
        """Apply a persisted native window size; never change WebEngine zoom."""
        choice = str(choice or "auto").strip().lower()
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        if available is not None:
            min_width = max(1, min(960, int(available.width())))
            min_height = max(1, min(620, int(available.height())))
        else:
            min_width, min_height = 960, 620
        self.setMinimumSize(min_width, min_height)
        if choice == "maximized":
            self.showMaximized()
            return
        if self.isMaximized():
            self.showNormal()
        if choice == "auto":
            width = int(available.width() * 0.90) if available is not None else 1440
            height = int(available.height() * 0.90) if available is not None else 900
            width = min(1600, max(min_width, width))
            height = min(1000, max(min_height, height))
        else:
            try:
                width, height = (int(part) for part in choice.split("x", 1))
            except (TypeError, ValueError):
                width, height = 1440, 900
        if available is not None:
            width = min(width, available.width())
            height = min(height, available.height())
        self.resize(max(min_width, width), max(min_height, height))
        self.setZoomFactorForNativeSize()

    def setZoomFactorForNativeSize(self) -> None:
        # Defensive invariant: all sizing is native window geometry or the
        # explicit text-size preference, never Chromium's browser zoom factor.
        if abs(self.web.zoomFactor() - 1.0) > 0.001:
            self.web.setZoomFactor(1.0)

    def _bridge_connect_timeout(self) -> None:
        if self._frontend_ready or self._frontend_failure_shown:
            return
        # The renderer may be alive even when Qt WebChannel has not connected.
        # Inspect it from the native process so a failed qrc script load or
        # missing transport is recorded even though the bridge cannot report it.
        probe = r"""
        (() => {
          const pending = Array.isArray(window.__ryuFrontendPendingDiagnostics)
            ? window.__ryuFrontendPendingDiagnostics.slice(-5).map(item => ({
                kind:String(item?.kind || '').slice(0,40),
                message:String(item?.message || '').slice(0,250)
              }))
            : [];
          const resources = performance.getEntriesByType('resource')
            .filter(entry => /qwebchannel/i.test(String(entry.name || '')))
            .slice(-5)
            .map(entry => ({
              name:String(entry.name || '').slice(0,240),
              duration:Math.round(Number(entry.duration || 0))
            }));
          return {
            url:String(location.href || '').slice(0,300),
            nativeHost:window.__ryuNativeHost === true,
            documentReadyState:String(document.readyState || ''),
            diagnosticsInstalled:Boolean(window.__ryuFrontendDiagnosticsInstalled),
            qWebChannelType:typeof window.QWebChannel,
            qtType:typeof window.qt,
            transportType:typeof window.qt === 'undefined'
              ? 'unavailable' : typeof window.qt.webChannelTransport,
            backendType:typeof window.ryuBackend,
            bridgeFailureReason:String(window.__ryuBridgeFailureReason || '').slice(0,500),
            pendingDiagnostics:pending,
            qwebchannelResources:resources,
            scripts:Array.from(document.scripts || [])
              .map(script => String(script.src || ''))
              .filter(Boolean)
              .slice(-8)
          };
        })()
        """
        self.web.page().runJavaScript(probe, self._finish_bridge_connect_timeout)
        # If the renderer itself is unresponsive, still reveal a recovery surface.
        QTimer.singleShot(2500, lambda: self._finish_bridge_connect_timeout(None))

    def _finish_bridge_connect_timeout(self, result: Any) -> None:
        if self._frontend_ready or self._frontend_failure_shown:
            return
        if isinstance(result, dict):
            try:
                details = json.dumps(result, ensure_ascii=False, default=str)[:900]
            except (TypeError, ValueError):
                details = str(result)[:900]
        else:
            details = "The renderer did not return its WebChannel state probe."
        self._show_web_failure(
            "The local desktop bridge did not connect within 20 seconds. "
            "The HTML page opened, but Qt WebChannel did not become ready. "
            "Your local project files have not been deleted. "
            "Qt WebChannel handshake diagnostics: " + details +
            ". Check the local application log and retry the interface."
        )

    def _show_web_failure(self, message: str) -> None:
        self._frontend_failure_shown = True
        if hasattr(self, "_frontend_watchdog"):
            self._frontend_watchdog.stop()
        if hasattr(self, "_bridge_watchdog"):
            self._bridge_watchdog.stop()
        self._write_startup_smoke_marker("failed", str(message or "Frontend startup failed."))
        log.error("Premium V2 renderer recovery surface shown: %s", message)
        if hasattr(self, "_web_error_message"):
            self._web_error_message.setText(str(message))
        if hasattr(self, "_web_stack") and hasattr(self, "_web_error_page"):
            self._web_stack.setCurrentWidget(self._web_error_page)

    def _write_startup_smoke_marker(self, status: str, detail: str = "") -> None:
        """Expose real frontend readiness to CI; production launches opt out by default."""
        marker_value = str(os.environ.get("RYU_STARTUP_SMOKE_MARKER") or "").strip()
        if not marker_value:
            return
        payload = {
            "status": str(status or "failed"),
            "frontend": "Premium V2",
            "version": full_version(),
            "detail": str(detail or "")[:1200],
        }
        destination = Path(marker_value)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError:
            log.exception("Could not write Premium V2 startup smoke marker to %s", destination)

    def _set_loading_status(self, message: str) -> None:
        if hasattr(self, "_loading_status"):
            self._loading_status.setText(str(message or "Starting the Windows interface…"))

    def _update_startup_progress(self, message: str, progress: int | None = None) -> None:
        """Show live native loading status from confirmed frontend startup milestones."""
        if self._frontend_ready or self._frontend_failure_shown:
            return
        self._set_loading_status(message)
        # This is an inactivity watchdog, not a total-startup deadline. Each
        # actual milestone refreshes it; slow but progressing local reads keep
        # the loading surface alive instead of being mistaken for a frozen UI.
        if self._frontend_generation > 0 and hasattr(self, "_frontend_watchdog"):
            self._frontend_watchdog.start(120000)
        if progress is None:
            # The current step is genuinely in progress; use Qt's busy animation
            # rather than inventing a percentage before the operation completes.
            if hasattr(self, "_loading_progress"):
                self._loading_progress.setRange(0, 0)
            return
        try:
            value = max(0, min(100, int(progress)))
        except (TypeError, ValueError, OverflowError):
            return
        # Ignore stale/out-of-order status callbacks so the visible meter never
        # moves backwards during one startup attempt.
        self._startup_progress_value = max(self._startup_progress_value, value)
        if value >= 26 and hasattr(self, "_bridge_watchdog"):
            self._bridge_watchdog.stop()
        # The progress numbers above are internal startup milestones only.
        # Keep the visible indicator indeterminate; never display a percentage.
        if hasattr(self, "_loading_progress"):
            self._loading_progress.setRange(0, 0)

    def _on_frontend_ready(self) -> None:
        """Reveal the app only after the backend bridge and frontend wiring have finished."""
        self._set_loading_status("Studio ready. Opening your workspace…")
        self._frontend_ready = True
        self._frontend_failure_shown = False
        if hasattr(self, "_frontend_watchdog"):
            self._frontend_watchdog.stop()
        if hasattr(self, "_bridge_watchdog"):
            self._bridge_watchdog.stop()
        self._renderer_restart_attempts = 0
        if hasattr(self, "_web_stack") and hasattr(self, "web"):
            self._web_stack.setCurrentWidget(self.web)
        log.info("Premium V2 frontend and native backend bridge are ready")
        self._write_startup_smoke_marker("ready")
        self._start_sound_ui_acceptance()

    def _start_sound_ui_acceptance(self) -> None:
        """Run an opt-in real WebEngine/desktop-bridge acceptance check in CI only."""
        script_value = str(os.environ.get("RYU_SOUND_UI_ACCEPTANCE_SCRIPT") or "").strip()
        config_value = str(os.environ.get("RYU_SOUND_UI_ACCEPTANCE_CONFIG") or "").strip()
        marker_value = str(os.environ.get("RYU_SOUND_UI_ACCEPTANCE_MARKER") or "").strip()
        if not any((script_value, config_value, marker_value)):
            return
        if getattr(self, "_sound_ui_acceptance_started", False):
            return
        self._sound_ui_acceptance_started = True
        if not all((script_value, config_value, marker_value)):
            self._finish_sound_ui_acceptance({
                "status": "failed",
                "errors": ["All three RYU_SOUND_UI_ACCEPTANCE_* paths must be provided."],
            })
            return
        try:
            script_path = Path(script_value).expanduser().resolve()
            config_path = Path(config_value).expanduser().resolve()
            self._sound_ui_acceptance_marker_path = Path(marker_value).expanduser().resolve()
            if not script_path.is_file() or not config_path.is_file():
                raise FileNotFoundError("The packaged Sound Design acceptance script or fixture configuration is missing.")
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError("The packaged Sound Design acceptance fixture configuration must be a JSON object.")
            script = script_path.read_text(encoding="utf-8")
            if not script.strip():
                raise ValueError("The packaged Sound Design acceptance JavaScript is empty.")
            timeout = float(os.environ.get("RYU_SOUND_UI_ACCEPTANCE_TIMEOUT_SECONDS") or 150)
            self._sound_ui_acceptance_timeout_seconds = max(30.0, min(900.0, timeout))
            self._sound_ui_acceptance_started_at = time.monotonic()
            self._sound_ui_acceptance_poll_in_flight = False
            self._sound_ui_acceptance_finished = False
            prelude = "window.__RYU_SOUND_UI_ACCEPTANCE_CONFIG__ = " + json.dumps(
                config, ensure_ascii=True, separators=(",", ":")
            ) + ";\n"
            self.web.page().runJavaScript(prelude + script)
            self._sound_ui_acceptance_timer = QTimer(self)
            self._sound_ui_acceptance_timer.setInterval(400)
            self._sound_ui_acceptance_timer.timeout.connect(self._poll_sound_ui_acceptance)
            self._sound_ui_acceptance_timer.start()
            log.info("Packaged Sound Design UI acceptance driver injected.")
        except Exception as exc:
            log.exception("Could not start packaged Sound Design UI acceptance.")
            self._finish_sound_ui_acceptance({
                "status": "failed",
                "errors": [f"Could not start the acceptance driver: {exc}"],
            })

    def _poll_sound_ui_acceptance(self) -> None:
        """Collect the browser driver's explicit result without blocking Qt's event loop."""
        if getattr(self, "_sound_ui_acceptance_finished", False):
            return
        started = float(getattr(self, "_sound_ui_acceptance_started_at", time.monotonic()))
        timeout = float(getattr(self, "_sound_ui_acceptance_timeout_seconds", 150.0))
        if time.monotonic() - started > timeout:
            self._finish_sound_ui_acceptance({
                "status": "failed",
                "errors": [f"Browser acceptance did not finish within {timeout:.0f} seconds."],
            })
            return
        if getattr(self, "_sound_ui_acceptance_poll_in_flight", False):
            return
        self._sound_ui_acceptance_poll_in_flight = True

        def received(value: Any) -> None:
            self._sound_ui_acceptance_poll_in_flight = False
            if self._sound_ui_acceptance_finished or value in (None, "", "null"):
                return
            try:
                result = json.loads(value) if isinstance(value, str) else value
                if not isinstance(result, dict) or result.get("status") not in {"passed", "failed"}:
                    return
                self._finish_sound_ui_acceptance(result)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                self._finish_sound_ui_acceptance({
                    "status": "failed",
                    "errors": [f"Browser acceptance returned unreadable result data: {exc}"],
                })

        self.web.page().runJavaScript(
            "JSON.stringify(window.__RYU_SOUND_UI_ACCEPTANCE_RESULT__ || null)",
            received,
        )

    def _finish_sound_ui_acceptance(self, result: dict[str, Any]) -> None:
        """Persist the UI test result and terminate this dedicated CI app process."""
        if getattr(self, "_sound_ui_acceptance_finished", False):
            return
        self._sound_ui_acceptance_finished = True
        payload = dict(result or {})
        payload.setdefault("version", full_version())
        payload.setdefault("frontend", "Premium V2")
        status = "passed" if payload.get("status") == "passed" else "failed"
        payload["status"] = status
        marker_path = getattr(self, "_sound_ui_acceptance_marker_path", None)
        try:
            if marker_path is None:
                marker_value = str(os.environ.get("RYU_SOUND_UI_ACCEPTANCE_MARKER") or "").strip()
                marker_path = Path(marker_value).expanduser().resolve() if marker_value else None
            if marker_path is None:
                raise ValueError("The packaged Sound Design acceptance marker path is not configured.")
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            marker_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            log.exception("Could not persist packaged Sound Design acceptance result.")
            status = "failed"
        timer = getattr(self, "_sound_ui_acceptance_timer", None)
        if timer is not None:
            timer.stop()
        log.info("Packaged Sound Design UI acceptance %s: %s", status, payload)
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(100, lambda: app.exit(0 if status == "passed" else 1))

    def _retry_web_renderer(self) -> None:
        # Keep the native loading surface visible during reload. Switching to the
        # WebEngine first exposes a blank frame until Chromium paints the page.
        self._frontend_ready = False
        self._frontend_failure_shown = False
        self._startup_progress_value = 0
        if hasattr(self, "_loading_progress"):
            self._loading_progress.setRange(0, 0)
        self._frontend_generation += 1
        generation = self._frontend_generation
        self._update_startup_progress("Retrying the interface and reconnecting local services…", 5)
        if (
            self._uses_html_startup_loader
            and self._hosted_html_path is not None
            and self._hosted_html_path.is_file()
        ):
            if hasattr(self, "_web_stack"):
                self._web_stack.setCurrentWidget(self.web)
            self.web.load(QUrl.fromLocalFile(str(self._hosted_html_path.resolve())))
        else:
            if hasattr(self, "_web_stack") and hasattr(self, "_loading_page"):
                self._web_stack.setCurrentWidget(self._loading_page)
            self.web.reload()
        QTimer.singleShot(30000, lambda: self._show_web_failure(
            "The interface retry timed out. Your project data remains on disk. Check the local log and try again."
        ) if generation == self._frontend_generation and not self._frontend_ready else None)

    def _handle_renderer_terminated(self, status, exit_code: int) -> None:
        message = f"Embedded UI renderer terminated (status={status}, exit code={exit_code})."
        log.error("%s", message)
        self._frontend_ready = False
        self._frontend_generation += 1
        self._show_web_failure(
            message + " The project data remains on disk. Retry the interface; diagnostics were written to the local log."
        )
        if self._renderer_restart_attempts < 1:
            self._renderer_restart_attempts += 1
            QTimer.singleShot(500, self._retry_web_renderer)

    def _install_bridge(self, ok: bool) -> None:
        if not ok:
            message = f"Premium V2 HTML failed to load from {frontend_path()}. Check that the application assets are intact, then retry."
            self._show_web_failure(message)
            return
        self._frontend_generation += 1
        self._frontend_ready = False
        generation = self._frontend_generation
        self._update_startup_progress("Premium V2 interface loaded. Connecting to local services…", 18)
        # Never expose the WebEngine during the bridge/hydration gap. Even
        # when the HTML loader is available, Chromium can briefly present a
        # white frame before its first paint. Keep the native splash visible
        # until _on_frontend_ready confirms the actual interactive UI is ready.
        if hasattr(self, "_web_stack"):
            self._web_stack.setCurrentWidget(self._loading_page)
        # Install error handlers before the adapter executes. A page load may
        # succeed while a JavaScript exception leaves the visible interface blank.
        script = r"""
        (() => {
          if (window.__ryuFrontendDiagnosticsInstalled) return;
          window.__ryuFrontendDiagnosticsInstalled = true;
          window.__ryuFrontendPendingDiagnostics = [];
          window.__ryuSendFrontendDiagnostic = null;
          const emit = (kind, details = {}) => {
            const row = {
              kind: String(kind || 'frontend-event').slice(0, 40),
              message: String(details.message || '').slice(0, 2500),
              source: String(details.source || '').slice(0, 600),
              line: Number.isFinite(Number(details.line)) ? Number(details.line) : 0,
              stack: String(details.stack || '').slice(0, 3000),
              progress: details.progress === undefined || details.progress === null ||
                !Number.isFinite(Number(details.progress))
                ? null : Math.max(0, Math.min(100, Math.round(Number(details.progress))))
            };
            try {
              if (typeof window.__ryuSendFrontendDiagnostic === 'function') {
                window.__ryuSendFrontendDiagnostic(row);
              } else if (window.__ryuFrontendPendingDiagnostics.length < 30) {
                window.__ryuFrontendPendingDiagnostics.push(row);
              }
            } catch (_) {}
          };
          window.__ryuEmitFrontendDiagnostic = emit;
          window.addEventListener('error', event => emit('javascript-error', {
            message: event.message || 'Uncaught JavaScript error',
            source: event.filename || '',
            line: event.lineno || 0,
            stack: event.error && event.error.stack || ''
          }), true);
          window.addEventListener('unhandledrejection', event => {
            const reason = event.reason;
            emit('unhandled-rejection', {
              message: reason && reason.message || String(reason || 'Unhandled promise rejection'),
              source: '',
              line: 0,
              stack: reason && reason.stack || ''
            });
          }, true);
        })();
        (() => {
          // This is a separate IIFE from the diagnostic listeners above. Rebind
          // their public emitter here; a block-scoped `emit` does not cross IIFEs.
          const emit = window.__ryuEmitFrontendDiagnostic;
          const bridgeStartedAt = Date.now();
          let channelScriptRequested = false;
          let channelConnecting = false;
          let completed = false;
          const failBridge = reason => {
            if (completed) return;
            completed = true;
            window.__ryuBridgeFailureReason = String(
              reason || 'The local backend bridge could not connect.'
            ).slice(0,1200);
            window.__ryuBridgeFailureAt = Date.now();
            window.clearTimeout(bridgeTimeout);
            emit('backend-bridge-failed', {
              message:window.__ryuBridgeFailureReason
            });
          };
          const bridgeTimeout = window.setTimeout(() => failBridge(
            'Qt WebChannel did not connect within 15 seconds. The HTML interface loaded, but the local desktop bridge is not responding.'
          ), 15000);
          const tryConnect = () => {
            if (completed || channelConnecting) return;
            if (!window.QWebChannel || !window.qt || !qt.webChannelTransport) {
              if (Date.now() - bridgeStartedAt >= 15000) {
                failBridge('Qt WebChannel loaded, but its native transport did not become ready within 15 seconds.');
                return;
              }
              window.setTimeout(waitForTransport, 100);
              return;
            }
            channelConnecting = true;
            try {
              new QWebChannel(qt.webChannelTransport, channel => {
                if (completed) return;
                const native = channel && channel.objects && channel.objects.ryuBackend;
                if (!native || typeof native.dispatch !== 'function' ||
                    typeof native.bootstrap !== 'function' ||
                    typeof native.report_frontend_diagnostic !== 'function') {
                  channelConnecting = false;
                  failBridge('Qt WebChannel connected without the required Ryu desktop bridge methods.');
                  return;
                }
                completed = true;
                window.clearTimeout(bridgeTimeout);
                window.__ryuSendFrontendDiagnostic = payload => {
                  try { native.report_frontend_diagnostic(JSON.stringify(payload || {})); }
                  catch (_) {}
                };
                const pendingDiagnostics = window.__ryuFrontendPendingDiagnostics || [];
                window.__ryuFrontendPendingDiagnostics = [];
                pendingDiagnostics.forEach(payload => window.__ryuSendFrontendDiagnostic(payload));
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
                emit('startup-progress', {
                  message:'Local backend connected. Loading your saved workspace…',
                  progress:26
                });
                window.dispatchEvent(new CustomEvent('ryu-backend-ready'));
              });
            } catch (error) {
              channelConnecting = false;
              failBridge('Qt WebChannel initialization failed: ' + String(error && error.message || error));
            }
          };
          const waitForTransport = () => {
            if (completed) return;
            if (!window.QWebChannel && !channelScriptRequested) {
              channelScriptRequested = true;
              const script = document.createElement('script');
              script.src = 'qrc:///qtwebchannel/qwebchannel.js';
              script.onload = tryConnect;
              script.onerror = () => failBridge(
                'Could not load qrc:///qtwebchannel/qwebchannel.js from the packaged Qt runtime.'
              );
              document.head.appendChild(script);
              return;
            }
            tryConnect();
          };
          waitForTransport();
        })();
        """
        adapter_path = frontend_path().with_name("premium_v2_backend_adapter.js")
        try:
            adapter_source = load_premium_v2_adapter(adapter_path)
        except FrontendAssetError as exc:
            message = (
                "The Premium V2 interface loaded, but its local backend adapter "
                "could not be read. The application will not continue in a "
                "partially connected state. Repair or reinstall the application.\n\n"
                f"{exc}"
            )
            log.error("%s", message)
            self._show_web_failure(message)
            return
        script += "\n" + adapter_source
        self._update_startup_progress("Preparing the local backend bridge…", 22)
        self.web.page().runJavaScript(script)
        # Catch a missing Qt transport quickly. A later, confirmed progress
        # milestone disarms this watchdog and returns to the hydration watchdog.
        self._bridge_watchdog.start(20000)
        # Check for a UI that loaded at the HTML level but never finished
        # initializing the backend adapter. This gives the user a native
        # recovery surface instead of an indefinitely blank black window.
        self._frontend_watchdog.start(120000)

    def _check_frontend_ready(self, generation: int) -> None:
        if generation != self._frontend_generation or self._frontend_ready or self._frontend_failure_shown:
            return
        self.web.page().runJavaScript(
            "({adapter:window.__ryuPremiumAdapterReady===true, body:!!document.body && "
            "document.body.innerText.trim().length>20, "
            "error:String(window.__ryuPremiumAdapterFailure || '').slice(0,1000)})",
            lambda result: self._finish_frontend_health_check(generation, result),
        )

    def _finish_frontend_health_check(self, generation: int, result: Any) -> None:
        if generation != self._frontend_generation or self._frontend_ready or self._frontend_failure_shown:
            return
        if isinstance(result, dict) and result.get("adapter") and result.get("body"):
            self._on_frontend_ready()
            return
        startup_error = (
            str(result.get("error") or "").strip()[:1000]
            if isinstance(result, dict) else ""
        )
        if startup_error:
            log.error("Premium V2 required startup hydration failed: %s", startup_error)
            self._show_web_failure(
                "Ryu's Audiobook could not complete startup. "
                "Your local project files have not been deleted. Details: " + startup_error
            )
            return
        log.error(
            "Premium V2 frontend failed its initialization watchdog (adapter_ready=%s, body_present=%s, generation=%s)",
            bool(result.get("adapter")) if isinstance(result, dict) else False,
            bool(result.get("body")) if isinstance(result, dict) else False,
            generation,
        )
        self._show_web_failure(
            "The application window opened, but its interface did not finish initializing. "
            "Your local project data has not been deleted. Select Retry interface; if the issue repeats, "
            "send the local application log so the JavaScript error and failing file/line can be identified."
        )
