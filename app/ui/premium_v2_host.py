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
from PySide6.QtGui import QDesktopServices, QPixmap

from app.core.paths import app_root, audiobooks_root, ensure_roots, library_root, settings_root
from app.ui.frontend_assets import (
    FrontendAssetError,
    load_premium_v2_adapter,
    premium_v2_logo_candidates,
)
from app.core.project import create_project, list_projects
from app.core.character_library import (
    character_library_path as reusable_character_library_path,
    list_characters as list_reusable_characters,
    list_deleted_characters as list_reusable_deleted_characters,
    restore_character as restore_reusable_character,
    soft_delete_character as soft_delete_reusable_character,
    sync_characters as sync_reusable_characters,
    update_character as update_reusable_character,
)
from app.documents.cover_art import COVER_IMAGE_EXTENSIONS, COVER_SOURCE_EXTENSIONS, extract_embedded_cover, persist_project_cover
from app.documents.parser import (
    SUPPORTED_EXTENSIONS, clean_import_noise, clean_text, detect_repeated_book_noise,
    extract_text, validate_chapter_text_coverage,
)
from app.chapters.detector import detect_chapters
from app.chapters.characters import analyze_book, merge_character_analysis_record
from app.chapters.dialogue_review import retain_current_dialogue_skips
from app.tts.manager import GenerationManager
from app.tts.preview import build_voice_preview
from app.tts.profile_provider import provider_from_profile
from app.tts.pronunciation_suggester import suggest_names_from_text, suggest_pronunciation
from app.tts.voice_profile import load_profiles
from app.core.state import load_state, save_state
from app.version import APP_NAME, full_version

log = logging.getLogger(__name__)

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
        row.update({
            "written_form": written,
            "spoken_form": spoken,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "scope": "Current book" if scope_type == "current_book" else (
                "Global library" if scope_type == "global_library" else f"Series · {scope_id}"
            ),
            "enabled": raw.get("enabled", True) is not False,
        })
        row.pop("written", None)
        row.pop("spoken", None)
        row.pop("word", None)
        row.pop("pronunciation", None)
        clean.append(row)
    return clean


def _effective_pronunciation_dictionary(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Combine synthesis rules in Current book > matching Series > Global order."""
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


class PremiumV2Bridge(QObject):
    """Narrow, allow-listed JSON bridge; renderer content cannot execute shell commands."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        ensure_roots()
        self.settings = QSettings("RyuBlanc", "Ryu's Audiobook")
        self._jobs_lock = threading.RLock()
        # Serialize review-skip writes with the character-analysis worker's final
        # reconciliation so a click during a long analysis cannot be overwritten.
        self._character_review_state_lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._history: dict[str, dict[str, Any]] = {}
        self._load_durable_history()
        self._generators: dict[str, GenerationManager] = {}
        self._import_cancel_events: dict[str, threading.Event] = {}
        self._preview_cancel_events: dict[str, threading.Event] = {}
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
                "voice.preview": self._voice_preview,
                "voice.preview.save": self._voice_preview_save,
                "character.list": self._character_list,
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
                "pronunciation.save": self._pronunciation_save,
                "pronunciation.delete": self._pronunciation_delete,
                "pronunciation.analyze": self._pronunciation_analyze,
                "production.generate_book": self._production_generate_book,
                "production.preview": self._production_preview,
                "sound.preview_book": self._sound_preview_book,
                "job.list": self._job_list,
                "job.pause": self._job_pause,
                "job.resume": self._job_resume,
                "job.cancel": self._job_cancel,
                "job.clear_completed": self._job_clear_completed,
                "history.list": self._history_list,
                "player.get_active": self._player_get_active,
                "player.position.save": self._player_position_save,
                "settings.get": self._settings_get,
                "settings.save": self._settings_save,
                "models.list": self._models_list,
                "models.install": self._models_install,
                "models.repair": self._models_repair,
                "models.uninstall": self._models_uninstall,
                "models.verify": self._models_verify,
                "performance.info": self._performance_info,
                "diagnostics.check": self._diagnostics_check,
                "diagnostics.export_logs": self._diagnostics_export_logs,
                "system.open_output": self._system_open_output,
                "sound.catalog": self._sound_catalog,
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
            "voice.preview": True,
            "voice.preview.save": True,
            "character.list": True,
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
            "pronunciation.save": True,
            "pronunciation.delete": True,
            "pronunciation.analyze": True,
            "production.generate_book": True,
            "production.preview": True,
            "sound.preview_book": True,
            "job.list": True,
            "job.pause": True,
            "job.resume": True,
            "job.cancel": True,
            "job.clear_completed": True,
            "history.list": True,
            "player.get_active": True,
            "player.position.save": True,
            "settings.get": True,
            "settings.save": True,
            "models.list": True,
            "models.install": True,
            "models.repair": True,
            "models.uninstall": True,
            "models.verify": True,
            "performance.info": False,
            "diagnostics.check": True,
            "diagnostics.export_logs": True,
            "system.open_output": True,
            "sound.catalog": True,
            "sound.import": True,
            "sound.assign": True,
            "sound.save_manifest": True,
            "sound.cues.get": True,
            "sound.cues.save": True,
            "sound.cues.clear": True,
            "sound.chapter_bgm.get": True,
            "sound.chapter_bgm.save": True,
            "reason": "Local import, chapter editing, saved voice selection and preview, character analysis and editing, pronunciation rules, audiobook generation, background jobs, history, playback metadata, local model installation, and settings are connected. Live hardware telemetry remains unavailable.",
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
        # Once analysis confirms that a book has no character speakers, there is
        # no missing character assignment to penalize in the preparation score.
        character_voice_ratio = (
            len(assigned_character_names) / len(character_names)
            if character_names else (1.0 if character_analysis_done else 0.0)
        )
        # Narrator is book metadata; readiness requires a selected, saved TTS voice profile.
        narrator_ready = bool(str(state.get("voice_profile") or "").strip())
        output_configured = bool(output_value)
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

        return {
            "title": project.title,
            "series_name": self._project_series_name(project, state),
            "folder": str(project.folder.resolve()),
            "source_path": str(project.source_path) if project.source_path else None,
            "chapter_count": chapter_count,
            "status": str(state.get("status") or "new"),
            "output_path": str(output) if valid_output and output else None,
            "completed": bool(completed),
            "cover_path": str(cover) if cover else None,
            "author": str(state.get("author") or ""),
            "narrator": str(state.get("narrator") or state.get("voice_profile") or ""),
            "voice_profile": str(state.get("voice_profile") or ""),
            "narrator_voice_configured": narrator_ready,
            "character_count": len(character_names),
            "character_voice_count": character_voice_count,
            "character_analysis_done": character_analysis_done,
            "prepared_chapter_count": prepared_chapters,
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

    def _project_open(self, payload: dict[str, Any]) -> dict[str, Any]:
        requested = str(payload.get("folder") or "").strip()
        if not requested:
            raise ValueError("Choose a saved local project first.")
        selected = next((p for p in list_projects()
                         if str(p.folder.resolve()) == str(Path(requested).resolve())), None)
        if selected is None:
            raise ValueError("That project is not present in the local library.")
        self.settings.setValue("project/active_folder", str(selected.folder.resolve()))
        self.settings.sync()
        return self._project_summary(selected)

    def _project_get_active(self, _payload: dict[str, Any]) -> dict[str, Any] | None:
        folder = str(self.settings.value("project/active_folder", "") or "")
        if not folder:
            return None
        selected = next((p for p in list_projects()
                         if str(p.folder.resolve()) == str(Path(folder).resolve())), None)
        if selected is None:
            self.settings.remove("project/active_folder")
            self.settings.sync()
            return None
        return self._project_summary(selected)

    def _active_project(self):
        folder = str(self.settings.value("project/active_folder", "") or "")
        if not folder:
            raise ValueError("Open a local project from the Library first.")
        selected = next((p for p in list_projects()
                         if str(p.folder.resolve()) == str(Path(folder).resolve())), None)
        if selected is None:
            self.settings.remove("project/active_folder")
            self.settings.sync()
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
                        {"start": start, "end": end, "text": exact_text, "source": "manual"})
            base.update({"start": start, "end": end, "text": exact_text, "source": "manual"})
            normalized = normalize_assignment(base, speakers, mode)
            assignment_series = requested_series or default_series
            normalized.update({"source": "manual", "confidence": 1.0, "series": assignment_series})
            chapter.dialogue_assignments = [
                item for item in existing if not (isinstance(item, dict)
                    and item.get("start") == start and item.get("end") == end)
            ] + [normalized]
            chapter.dialogue_assignments.sort(key=lambda item: (int(item.get("start", 0)), int(item.get("end", 0))))
            result = {"chapter_number": chapter.number, "start": start, "end": end,
                      "text": exact_text, "speakers": speakers, "source": "manual",
                      "confidence": 1.0, "series": assignment_series, "saved": True}
        else:
            result = assign_dialogue_to_chapters(project.chapters, dialogue_text, speakers,
                                                 chapter_number=chapter_number, mode=mode)
            assignment_series = requested_series or default_series
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

    def _load_durable_jobs(self) -> None:
        path = self._jobs_path()
        try:
            rows = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        except (OSError, ValueError, TypeError):
            rows = []
        if not isinstance(rows, list):
            rows = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("job_id"):
                continue
            if row.get("state") in {"queued", "running", "pause_requested", "cancel_requested", "retrying"}:
                row.update({"state": "failed", "stage": "Interrupted by application restart",
                            "message": "The application closed before this task finished. Retry from the project to reuse valid checkpoints.",
                            "error": {"code": "interrupted", "message": "Worker did not survive restart."},
                            "recoverable": True, "updated_at": self._now()})
            self._jobs[str(row["job_id"])] = row
            if self._terminal_job_state(row):
                self._record_history_job(row)

    def _new_job(self, job_type: str, title: str, description: str, project=None) -> str:
        job_id = uuid.uuid4().hex
        now = self._now()
        with self._jobs_lock:
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
        # History is independent of queue visibility and survives queue cleanup.
        with self._jobs_lock:
            rows = [dict(row) for row in self._history.values()]
        return sorted(
            rows,
            key=lambda row: str(row.get("completed_at") or row.get("updated_at") or row.get("queued_at") or ""),
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
        chapter.text = left
        new_title = str(payload.get("new_title") or f"{title_value} (continued)").strip()[:500]
        new_chapter = Chapter(number + 1, new_title, right)
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
        if target_existing is not None:
            saved[saved.index(target_existing)] = profile
        else:
            saved.append(profile)
        save_profiles(saved)
        return {"name": profile.name, "provider": profile.provider, "voice_id": profile.voice_id,
                "sample_path": profile.sample_path, "model_id": profile.model_id,
                "backend": profile.backend, "language": profile.language,
                "authorized": profile.authorized, "qwen_mode": profile.qwen_mode, "saved": True,
                "count": len(load_profiles())}

    def _voice_catalog(self, payload: dict[str, Any]) -> dict[str, Any]:
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
        for project in list_projects():
            state = load_state(project.folder)
            if str(state.get("voice_profile") or "").casefold() == name.casefold():
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
                      "narrator": profile.name})
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
                    "voice-preview", "sound-design-preview", "audiobook-generation"
                }
            ]
        if active:
            title = str(active[0].get("title") or "Audio synthesis")
            raise RuntimeError(
                f"Cannot {activity} while {title} is still running. "
                "Wait for the active preview or audiobook generation to finish first."
            )

    def _voice_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_no_active_model_lifecycle("generate a voice preview")
        check_active = getattr(self, "_assert_no_active_audio_synthesis", None)
        if callable(check_active):
            check_active("generate a preview")
        project = self._active_project()
        state = load_state(project.folder)
        profile = PremiumV2Bridge._preview_profile_from_payload(self, payload, state)
        if profile is None:
            raise ValueError("Choose an installed voice or load a saved voice profile before previewing.")
        text_value = str(payload.get("text") or "")
        number = payload.get("chapter_number")
        if not text_value.strip():
            chapter = next((c for c in project.chapters if (c.text or "").strip() and (number is None or c.number == int(number))), None)
            if chapter is None:
                raise ValueError("Select a chapter that contains narration text.")
            text_value = chapter.text
        seconds = int(payload.get("duration_seconds") or payload.get("duration") or 30)
        if seconds not in {10, 30, 60, 90}:
            raise ValueError("Preview duration must be 10, 30, 60, or 90 seconds.")
        include_sound_design = bool(payload.get("include_sound_design"))
        if include_sound_design:
            state["_include_sound_design_preview"] = True
        job_id = self._new_job("sound-design-preview" if include_sound_design else "voice-preview",
                               ("Sound Design mix preview · " if include_sound_design else "Preview · ") + profile.name,
                               f"Generate up to {seconds} seconds using the selected provider", project)
        cancel_event = threading.Event()
        if not hasattr(self, "_preview_cancel_events"):
            self._preview_cancel_events = {}
        with getattr(self, "_jobs_lock", threading.RLock()):
            self._preview_cancel_events[job_id] = cancel_event
        self._job_update(job_id, state="running", started_at=self._now(), stage="Preparing preview", progress=2)
        threading.Thread(target=self._preview_worker, args=(job_id, profile, text_value, seconds, state, cancel_event),
                         daemon=True, name="RyuPremiumPreview").start()
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

    def _sound_preview_book(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Queue a full-book mix preview from saved narration without re-synthesis."""
        from app.ui.full_book_preview import start_full_book_preview
        return start_full_book_preview(self)

    def _render_sound_design_preview(self, source: Path, job_id: str, state: dict[str, Any]) -> Path:
        """Render a short audition using the active book's real music/cue assignments."""
        from app.audio.assembler import _concat_audio_files, _duration_ms, _run
        from app.audio.library import validate_saved_audio_paths
        validate_saved_audio_paths(state)

        preview_root = app_root() / "Previews"
        preview_root.mkdir(parents=True, exist_ok=True)
        audio_source = Path(source).resolve()
        opening = Path(str(state.get("opening_cue_path") or "")).expanduser()
        if opening.is_file():
            with_opening = preview_root / f"sound-preview-opening-{job_id}.m4a"
            _concat_audio_files(opening, audio_source, with_opening, "192k")
            audio_source = with_opening

        music_path = None
        volume = max(0.0, min(0.50, float(state.get("background_audio_volume") if state.get("background_audio_volume") is not None else 0.18)))
        first_override = (state.get("chapter_bgm_overrides") or {}).get("1", {})
        if str(state.get("background_audio_mode") or "off").lower() == "manual" and isinstance(first_override, dict):
            rule = str(first_override.get("rule") or "default").lower()
            if rule == "none":
                music_path = None
            elif rule == "custom":
                music_path = Path(str(first_override.get("path") or "")).expanduser()
                volume = max(0.0, min(0.50, float(first_override.get("volume", volume))))
            else:
                raw_music = str(state.get("background_audio_path") or "")
                music_path = Path(raw_music).expanduser() if raw_music else None
                volume = max(0.0, min(0.50, float(first_override.get("volume", volume))))
        elif str(state.get("background_audio_mode") or "off").lower() == "manual":
            raw_music = str(state.get("background_audio_path") or "")
            music_path = Path(raw_music).expanduser() if raw_music else None

        if music_path and not music_path.is_file():
            raise FileNotFoundError(f"Selected background music is missing: {music_path}")
        output = preview_root / f"sound_mix_preview_{job_id}.m4a"
        duration_ms = _duration_ms(audio_source)
        duration_seconds = max(0.1, duration_ms / 1000.0)
        if music_path and volume > 0:
            fade_in = max(0.0, min(30.0, float(state.get("background_audio_fade_in", 2.0))))
            fade_out = max(0.0, min(30.0, float(state.get("background_audio_fade_out", 3.0)), duration_seconds))
            fade_out_start = max(0.0, duration_seconds - fade_out)
            music_filters = [f"volume={volume:.4f}"]
            if fade_in:
                music_filters.append(f"afade=t=in:st=0:d={min(fade_in, duration_seconds):.3f}")
            if fade_out:
                music_filters.append(f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f}")
            music_filters.extend(["aresample=44100", "aformat=sample_rates=44100:channel_layouts=stereo"])
            _run([
                "-i", str(audio_source), "-stream_loop", "-1", "-i", str(music_path),
                "-filter_complex",
                "[0:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo,asplit=2[narr_mix][narr_sc];"
                f"[1:a]{','.join(music_filters)}[bed];"
                "[bed][narr_sc]sidechaincompress=threshold=0.025:ratio=7:attack=22:release=420:makeup=1[ducked];"
                "[narr_mix][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[out]",
                "-map", "[out]", "-vn", "-t", f"{duration_seconds:.3f}",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", str(output),
            ])
        else:
            _run(["-i", str(audio_source), "-vn", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", str(output)])
        if not output.is_file() or output.stat().st_size < 1024:
            raise RuntimeError("The Sound Design mix preview could not be rendered.")
        if abs(_duration_ms(output) - duration_ms) > 1800:
            raise RuntimeError("The Sound Design mix preview changed duration unexpectedly.")
        if audio_source != Path(source).resolve():
            audio_source.unlink(missing_ok=True)
        return output

    def _preview_worker(self, job_id: str, profile, text_value: str, seconds: int, state: dict[str, Any], cancel_event=None) -> None:
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
        try:
            if cancel_event is not None and cancel_event.is_set():
                raise PreviewCancelledError("Preview cancelled by user.")
            # Keep Voice Studio previews consistent with production: saved
            # character assignments must route quoted dialogue through their
            # selected profiles, while narration continues to use the narrator.
            cast_assignments: dict[str, str] = {}
            cast_profiles: dict[str, Any] = {}
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
                pronunciation_dictionary=_effective_pronunciation_dictionary(state),
                narration_speed=float(state.get("narration_speed") or 0.90),
                pacing_profile=str(state.get("pacing_profile") or "natural"),
                max_chars=max(1400, seconds * 240), progress_callback=progress,
                target_seconds=seconds,
                cancel_check=cancel_event.is_set if cancel_event is not None else None,
            )
            synthesis_finished_at = time.monotonic()
            if cancel_event is not None and cancel_event.is_set():
                raise PreviewCancelledError("Preview cancelled by user.")
            preview_path = Path(result.output_path)
            if state.get("_include_sound_design_preview"):
                preview_path = self._render_sound_design_preview(preview_path, job_id, state)
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
                                 "output_path": str(preview_path), "file_url": preview_path.resolve().as_uri(),
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
                                 "pronunciation_replacements": replacements,
                                 "pronunciation_rule_counts": dict(rule_counts),
                             })
            preview_succeeded = True
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set() or isinstance(exc, PreviewCancelledError):
                for candidate in {output, preview_path,
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
                for candidate in {output, preview_path,
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
        state = load_state(self._active_project().folder)
        rows = state.get("characters") or []
        return rows if isinstance(rows, list) else []

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
        """Return source-backed dialogue suggestions created from the active project's chapters."""
        project = self._active_project()
        state = load_state(project.folder)
        stored = state.get("character_dialogue_suggestions") or []
        if not isinstance(stored, list):
            return []
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
            if source_text[start:end] != str(raw.get("source_text") or ""):
                continue
            row = dict(raw)
            row["chapter_title"] = str(chapter.title or f"Chapter {number}")
            row["text"] = source_text[start:end]
            row["assigned_speakers"] = []
            assignment = next((item for item in (chapter.dialogue_assignments or [])
                               if isinstance(item, dict) and item.get("start") == start
                               and item.get("end") == end and source_text[start:end] == str(item.get("text") or "")), None)
            if assignment:
                row["assigned_speakers"] = (
                    list(assignment.get("speakers") or []) if isinstance(assignment.get("speakers"), list)
                    else ([str(assignment.get("speaker"))] if assignment.get("speaker") else [])
                )
            row["assigned"] = bool(row["assigned_speakers"])
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
        match = next((row for row in characters if
                      str(row.get("name") or "").casefold() == name.casefold()
                      or name.casefold() in {str(alias).casefold() for alias in (row.get("aliases") or [])}), None)
        if match is not None:
            match_series = str(match.get("series") or "").strip()
            if not match_series:
                scope = str(match.get("scope") or "").strip()
                match_series = re.sub(r"(?i)^series\s*[·:-]\s*", "", scope).strip() if re.match(r"(?i)^series\s*[·:-]", scope) else prior_project_series
            if match_series and match_series.casefold() != series.casefold():
                raise ValueError(
                    f"{name} already exists in this project under the series “{match_series}”. "
                    f"Choose that series or use a distinct character name for “{series}”."
                )
        if match is None:
            match = {
                "name": name, "role": str(payload.get("role") or "Character")[:160],
                "dialogue_count": 0, "examples": [], "confidence": 1.0,
                "aliases": aliases, "voice_profile": profile_name or None,
                "series": series, "user_created": True,
                "short_description": str(payload.get("short_description") or "")[:1000],
                "notes": str(payload.get("notes") or "")[:4000], "scope": "Series · " + series,
            }
            characters.append(match)
        else:
            match.update({
                "name": name, "aliases": aliases or list(match.get("aliases") or []),
                "series": series, "scope": "Series · " + series, "user_created": True,
                "short_description": str(payload.get("short_description", match.get("short_description", "")) or "")[:1000],
                "notes": str(payload.get("notes", match.get("notes", "")) or "")[:4000],
            })
            if "voice_profile" in payload:
                match["voice_profile"] = profile_name or None
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
        self._job_update(job_id, state="running", started_at=self._now(), stage="Analyzing dialogue", progress=5)
        threading.Thread(target=self._character_worker, args=(job_id, project), daemon=True).start()
        return {"job_id": job_id, "state": "running"}

    def _character_worker(self, job_id: str, project) -> None:
        try:
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
            from app.chapters.characters import NAME_STOPWORDS, _discover_explicit_speakers
            from app.chapters.character_learning import (
                load_learning_examples, prepare_learning_index, rank_speaker_suggestions,
                source_grounded_speaker_for_continuity,
            )
            explicit_names = {str(name).casefold() for name in _discover_explicit_speakers(raw_text)}
            stopwords = {str(value).casefold() for value in NAME_STOPWORDS}
            trusted_rows = []
            trusted_keys = set()
            for row in [*saved_rows, *library_rows]:
                name = str(row.get("name") or row.get("primary_name") or "").strip()
                aliases = row.get("aliases") or []
                aliases = aliases if isinstance(aliases, (list, tuple)) else []
                # Previously auto-detected labels are not automatically trusted.
                # A saved voice, manual creation/edit, series-level registry entry,
                # or prior confirmed dialogue assignment is user-backed evidence.
                trusted = bool(
                    row.get("user_created") or row.get("manual") or row.get("voice_profile")
                    or row.get("voice_name") or row.get("short_description") or row.get("notes")
                    or (row.get("series") and row.get("primary_name"))
                )
                if trusted and name:
                    trusted_rows.append(row)
                    trusted_keys.add(name.casefold())
                    trusted_keys.update(str(alias).strip().casefold() for alias in aliases if str(alias or "").strip())
            for chapter in project.chapters:
                for assignment in (getattr(chapter, "dialogue_assignments", []) or []):
                    if not isinstance(assignment, dict):
                        continue
                    raw_speakers = assignment.get("speakers")
                    if not isinstance(raw_speakers, (list, tuple)):
                        raw_speakers = [assignment.get("speaker")] if assignment.get("speaker") else []
                    for speaker in raw_speakers:
                        clean_speaker = str(speaker or "").strip()
                        if clean_speaker:
                            trusted_keys.add(clean_speaker.casefold())
                            trusted_rows.append({"name": clean_speaker, "aliases": [],
                                                 "series": str(assignment.get("series") or series_name)})

            analysis = analyze_book(project.chapters)
            # Filter ordinary capitalized words out of the cast unless the text
            # supplies explicit attribution, the name is already trusted, or it
            # appears repeatedly enough in narration to be a credible identity.
            def credible_candidate(candidate) -> bool:
                name = str(getattr(candidate, "name", "") or "").strip()
                key = name.casefold()
                if not name or key in stopwords:
                    return False
                if key in trusted_keys or key in explicit_names:
                    return True
                count = len(re.findall(r"(?<!\w)" + re.escape(name) + r"(?!\w)", raw_text, re.IGNORECASE))
                if len(name.split()) > 1:
                    return count >= 2
                return count >= 4

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
            max_suggestions = 3000
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
            for chapter in project.chapters:
                if len(suggestions) >= max_suggestions:
                    break
                last_speaker = ""
                last_speaker_series = ""
                last_speaker_end = -1
                segments = dialogue_segments(chapter)
                saved_assignments = [
                    row for row in (getattr(chapter, "dialogue_assignments", []) or [])
                    if isinstance(row, dict)
                ]
                for segment in segments:
                    if len(suggestions) >= max_suggestions:
                        break
                    source = str(chapter.text or "")
                    start, end = int(segment.start), int(segment.end)
                    if start < 0 or end <= start or end > len(source):
                        continue
                    exact = source[start:end]
                    detected = [
                        {"name": str(name), "confidence": round(float(confidence), 4), "evidence": str(evidence)}
                        for name, confidence, evidence in (segment.suggestions or [])
                        if str(name).strip()
                    ]
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
                latest_state["characters"] = items
                latest_state["character_dialogue_suggestions"] = suggestions
                latest_state["character_dialogue_skips"] = retain_current_dialogue_skips(
                    latest_dialogue_skips,
                    latest_dialogue_suggestions,
                    suggestions,
                )
                latest_state["character_analysis"] = {"dialogue_total": analysis.dialogue_total,
                                                      "unassigned_dialogue": analysis.unassigned_dialogue,
                                                      "suggestion_count": len(suggestions),
                                                      "updated_at": self._now()}
                latest_state["modified_at"] = self._now()
                save_state(project.folder, latest_state)
                state = latest_state
            self._sync_saved_cast(project, items, state, update_names=False, update_voice=False)
            self._job_update(job_id, state="completed", stage="Analysis complete", progress=100,
                             message=f"Detected {len(items)} character candidate(s) from saved chapter text",
                             result={"characters": items, "dialogue_total": analysis.dialogue_total,
                                     "unassigned_dialogue": analysis.unassigned_dialogue})
        except Exception as exc:
            log.exception("Premium V2 character analysis failed")
            self._job_update(job_id, state="failed", stage="Analysis failed", message=str(exc),
                             error={"code": "character_analysis_failed", "message": str(exc)}, recoverable=True)

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
        item = next((c for c in characters
                     if isinstance(c, dict)
                     and str(c.get("name", "")).casefold() == name.casefold()
                     and (not requested_series
                          or str(c.get("series") or self._project_series_name(project, state)).casefold()
                             == requested_series.casefold())), None)
        if item is None:
            raise ValueError("That character is not in the selected series of the saved project cast. Refresh the list and try again.")
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
        """Persist edits to a character discovered by analysis."""
        project = self._active_project()
        original_name = str(payload.get("original_name") or payload.get("name") or "").strip()
        name = str(payload.get("name") or "").strip()
        if not original_name or not name:
            raise ValueError("A character name is required.")
        if len(name) > 160:
            raise ValueError("Character names must be 160 characters or fewer.")
        state = load_state(project.folder)
        characters = list(state.get("characters") or [])
        item = next((c for c in characters
                     if isinstance(c, dict) and str(c.get("name", "")).casefold() == original_name.casefold()), None)
        if item is None:
            raise ValueError("The selected character is no longer in the saved cast. Refresh and try again.")
        duplicate = next((c for c in characters
                          if isinstance(c, dict) and c is not item
                          and str(c.get("name", "")).casefold() == name.casefold()), None)
        if duplicate is not None:
            raise ValueError("Another character already uses that name.")
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
        current_series = str(item.get("series") or "")
        series_value = payload.get("series") if "series" in payload else item.get("series", "")
        if isinstance(series_value, str):
            series_value = series_value.strip()[:300]
        else:
            series_value = ""
        item.update({
            "name": name,
            "role": str(role_value or "Character").strip()[:160],
            "short_description": str(description_value or "").strip()[:1000],
            "aliases": list(dict.fromkeys(str(alias).strip()[:160] for alias in aliases if str(alias).strip())),
            "notes": str(notes_value or "").strip()[:4000],
            "scope": ("Series · " + series_value) if series_value else str(scope_value or "Current book only").strip()[:80],
            "series": series_value,
            "voice_profile": profile_name or None,
        })
        state["characters"] = characters
        state["modified_at"] = self._now()
        save_state(project.folder, state)
        if series_value:
            try:
                registry_rows = list_reusable_characters()
                old_series = str(current_series or '').casefold()
                active_folder = str(Path(project.folder).resolve())
                library_row = next((row for row in registry_rows
                    if str(row.get("source_project_folder") or "") and
                       str(Path(str(row.get("source_project_folder"))).resolve()) == active_folder and
                       str(row.get("primary_name") or row.get("name") or "").casefold() in
                       {original_name.casefold(), name.casefold()}), None)
                if library_row is None:
                    library_row = next((row for row in registry_rows
                        if str(row.get("series") or "").casefold() == series_value.casefold()
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
        """Remove one character from the active book's saved cast."""
        project = self._active_project()
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("Choose a character to delete.")
        state = load_state(project.folder)
        characters = list(state.get("characters") or [])
        kept = [c for c in characters if not (
            isinstance(c, dict) and str(c.get("name", "")).casefold() == name.casefold()
        )]
        removed = len(characters) - len(kept)
        if not removed:
            raise ValueError("The selected character is no longer in the saved cast.")
        state["characters"] = kept
        state["modified_at"] = self._now()
        save_state(project.folder, state)
        return {"name": name, "deleted": True, "remaining": len(kept)}

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
        if not isinstance(characters, list) or not characters:
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
                registry_path=registry_path,
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
        project = self._active_project()
        state = load_state(project.folder)
        # Legacy scope labels were stored inside project state but were never
        # shared across projects. Keep those rows book-local during migration.
        entries = _clean_pronunciation_entries(
            state.get("pronunciation_dictionary") if isinstance(state.get("pronunciation_dictionary"), list) else [],
            "current_book",
        )
        entries.extend(_clean_pronunciation_entries(
            _read_pronunciation_store(_pronunciation_scope_path("global_library")),
            "global_library",
        ))
        series_dir = settings_root() / "pronunciation_dictionary_series"
        if series_dir.exists():
            for path in sorted(series_dir.glob("*.json")):
                for row in _read_pronunciation_store(path):
                    try:
                        scope_type, scope_id, _label = _parse_pronunciation_scope(
                            row.get("scope") or "series", row.get("scope_id")
                        )
                    except ValueError:
                        continue
                    if scope_type == "series":
                        entries.extend(_clean_pronunciation_entries([row], "series", scope_id))
        return entries

    def _pronunciation_save(self, payload: dict[str, Any]) -> dict[str, Any]:
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
        enabled = payload.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("Enabled must be a boolean.")
        if scope_type == "current_book":
            state = load_state(project.folder)
            raw_entries = state.get("pronunciation_dictionary")
            raw_entries = raw_entries if isinstance(raw_entries, list) else []
            raw_match_count = sum(
                1 for row in raw_entries if isinstance(row, dict) and
                unicodedata.normalize("NFC", str(row.get("written_form") or row.get("written") or row.get("word") or "")).strip().casefold() == word.casefold()
            )
            entries = _clean_pronunciation_entries(raw_entries, "current_book")
        else:
            path = _pronunciation_scope_path(scope_type, scope_id)
            raw_entries = _read_pronunciation_store(path)
            raw_match_count = sum(
                1 for row in raw_entries if
                unicodedata.normalize("NFC", str(row.get("written_form") or row.get("written") or row.get("word") or "")).strip().casefold() == word.casefold()
            )
            entries = _clean_pronunciation_entries(raw_entries, scope_type, scope_id)
        key = word.casefold()
        matching = [row for row in entries if row["written_form"].casefold() == key]
        old_spoken = matching[0]["spoken_form"] if matching else None
        value = {
            "written_form": word,
            "spoken_form": spoken,
            "language": language,
            "handling_mode": handling_mode,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "scope": scope_label,
            "enabled": enabled,
            "updated_at": self._now(),
        }
        entries = [row for row in entries if row["written_form"].casefold() != key]
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
            "updated_existing": bool(matching),
            "conflict_resolved": bool(matching and old_spoken != spoken),
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

    def _pronunciation_analyze(self, _payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        existing = {str(e.get("written_form") or e.get("word") or "").casefold() for e in self._pronunciation_list({})}
        names = set()
        for chapter in project.chapters:
            names.update(n.strip() for n in suggest_names_from_text(chapter.text or "") if len(n.strip()) > 1)
        suggestions = [{"written_form": name, "spoken_form": suggest_pronunciation(name),
                        "language": "Auto-detect", "handling_mode": "automatic",
                        "scope": "current_book", "enabled": False, "review_required": True}
                       for name in sorted(names, key=str.casefold) if name.casefold() not in existing]
        job_id = self._new_job("pronunciation-analysis", "Analyze pronunciation", "Find proper nouns for manual review", project)
        self._job_update(job_id, state="completed", stage="Review suggestions", progress=100,
                         message=f"Found {len(suggestions)} pronunciation suggestion(s); none enabled automatically",
                         result={"suggestions": suggestions, "count": len(suggestions)})
        return {"job_id": job_id, "state": "completed", "suggestions": suggestions, "count": len(suggestions)}

    def _production_generate_book(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_no_active_model_lifecycle("start audiobook generation")
        check_active = getattr(self, "_assert_no_active_audio_synthesis", None)
        if callable(check_active):
            check_active("start audiobook generation")
        close_cache = getattr(self, "close_preview_provider_cache", None)
        if callable(close_cache):
            close_cache()
        project = self._active_project()
        chapters = [c for c in project.chapters if not getattr(c, "skip_for_generation", False) and (c.text or "").strip()]
        skipped = len(project.chapters) - len(chapters)
        empty_skipped = sum(1 for c in project.chapters if not (c.text or "").strip())
        excluded_skipped = sum(1 for c in project.chapters if getattr(c, "skip_for_generation", False) and (c.text or "").strip())
        if not chapters:
            raise ValueError("No chapters are eligible for generation. Restore chapter text or re-include a skipped chapter.")
        state = load_state(project.folder)
        from app.audio.library import validate_saved_audio_paths
        validate_saved_audio_paths(state)
        profile_name = str(payload.get("profile_name") or state.get("voice_profile") or "").strip()
        profile = self._find_profile(profile_name)
        if profile is None:
            raise ValueError("No narrator is saved. Open Voice Studio, select an installed voice, and save it as narrator.")
        provider, voice = provider_from_profile(profile)
        # Include the full selected narrator profile in resumable chunk identity
        # even when this book has no character-specific voice assignments.
        from app.tts.profile_provider import ProfileBoundProvider
        provider = ProfileBoundProvider(provider, profile)
        # Character Studio assignments must affect actual synthesis, not only the
        # roster UI. Wrap the narrator with the existing cast-aware router when
        # at least one saved character has a valid voice assignment.
        cast_assignments: dict[str, str] = {}
        cast_profiles: dict[str, Any] = {}
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
        if cast_assignments:
            from app.tts.cast_provider import CastAwareProvider
            provider = CastAwareProvider(
                provider, voice, cast_profiles, cast_assignments,
                narrating_character=str(state.get("narrating_character") or ""),
                backend_override=str(state.get("backend") or "automatic"),
                narrator_profile=profile,
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
        bitrate = int(payload.get("bitrate") or state.get("audio_bitrate") or 256)
        if not 128 <= bitrate <= 320:
            raise ValueError("Select a bitrate from 128 through 320 kbps.")
        job_id = self._new_job("audiobook-generation", "Generate " + project.title,
                               f"Render {len(chapters)} eligible chapter(s); skip {empty_skipped} empty and {excluded_skipped} excluded chapter(s)", project)
        # While a new generation is running, do not expose a prior file at the
        # same destination as the current audiobook. Keep the intended destination
        # separately; only publish output_path after the final file validates.
        state.update({"voice_profile": profile.name, "voice_id": profile.voice_id,
                      "output_path": None, "generation_target_path": str(output),
                      "status": "generating", "audio_bitrate": bitrate, "generation_job_id": job_id,
                      "generation_started_at": self._now(), "empty_chapters_skipped": empty_skipped,
                      "excluded_chapters_skipped": excluded_skipped, "chapters_skipped_for_generation": skipped})
        save_state(project.folder, state)
        metadata = {"title": str(payload.get("title") or project.title),
                    "author": str(payload.get("author") or state.get("author") or ""),
                    "narrator": profile.name, "publisher": str(state.get("publisher") or ""),
                    "series": str(state.get("series") or ""), "language": str(state.get("language") or ""),
                    "year": str(state.get("year") or ""), "genre": str(state.get("genre") or "")}
        manager = GenerationManager(
            provider, voice, chapters, project.folder / "working_audio",
            on_progress=lambda *args: self._generation_progress(job_id, *args),
            on_finished=lambda summary: self._generation_finished(job_id, project, summary, output, profile.name),
            pronunciation_dictionary=_effective_pronunciation_dictionary(state),
            narration_speed=float(state.get("narration_speed") or 0.90),
            pacing_profile=str(state.get("pacing_profile") or "natural"),
            metadata=metadata, bitrate=bitrate,
            background_audio_path=Path(state["background_audio_path"]) if state.get("background_audio_path") else None,
            background_audio_volume=float(state.get("background_audio_volume") if state.get("background_audio_volume") is not None else 0.18),
            ambience_audio_path=Path(state["ambience_audio_path"]) if state.get("ambience_audio_path") else None,
            ambience_audio_volume=float(state.get("ambience_audio_volume") if state.get("ambience_audio_volume") is not None else 0.10),
            background_audio_fade_in=float(state.get("background_audio_fade_in") if state.get("background_audio_fade_in") is not None else 2.0),
            background_audio_fade_out=float(state.get("background_audio_fade_out") if state.get("background_audio_fade_out") is not None else 3.0),
            background_audio_mode=str(state.get("background_audio_mode") or "off"),
            auto_music_style=str(state.get("auto_music_style") or "auto"),
            auto_music_variation=state.get("auto_music_track_path") or None,
            chapter_transition_sound=bool(state.get("chapter_transition_sound", False)),
            story_effects_enabled=bool(state.get("story_effects_enabled", False)),
            story_effect_volume=float(state.get("story_effect_volume") if state.get("story_effect_volume") is not None else 0.22),
            sound_cue_style=str(state.get("sound_cue_style") or "classic-book"),
            opening_cue_path=Path(state["opening_cue_path"]) if state.get("opening_cue_path") else None,
            page_turn_cue_path=Path(state["page_turn_cue_path"]) if state.get("page_turn_cue_path") else None,
            ending_cue_path=Path(state["ending_cue_path"]) if state.get("ending_cue_path") else None,
            scene_transition_cue_path=Path(state["scene_transition_cue_path"]) if state.get("scene_transition_cue_path") else None,
            chapter_bgm_overrides=state.get("chapter_bgm_overrides") if isinstance(state.get("chapter_bgm_overrides"), dict) else {},
        )
        with self._jobs_lock:
            self._generators[job_id] = manager
        self._job_update(job_id, state="running", started_at=self._now(), stage="Preparing generation",
                         progress=1, message=f"Starting with {empty_skipped} empty and {excluded_skipped} excluded chapter(s) skipped",
                         result={"output_path": str(output), "chapter_count": len(chapters),
                                 "empty_chapters_skipped": empty_skipped,
                                 "excluded_chapters_skipped": excluded_skipped,
                                 "chapters_skipped_for_generation": skipped,
                                 "voice_profile": profile.name})
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
                "chapters_skipped_for_generation": skipped, "voice_profile": profile.name}

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
        actual = Path(summary.output_path) if getattr(summary, "output_path", None) else output
        valid = actual.is_file() and actual.stat().st_size > 0
        success = valid and not summary.cancelled and not summary.packaging_failed and not summary.chapters_failed and summary.chapters_completed == summary.chapters_total
        state = load_state(project.folder)
        if success:
            state.update({"status": "completed", "output_path": str(actual), "voice_profile": voice_name,
                          "completed_chapters": list(summary.chapters_completed_numbers or []),
                          "failed_chapters": [], "generation_completed_at": self._now()})
            save_state(project.folder, state)
            self._job_update(job_id, state="completed", stage="Audiobook ready", progress=100,
                             message="Generator completed and the final output file was validated",
                             output_path=str(actual), result={"output_path": str(actual), "file_url": actual.resolve().as_uri(),
                                 "file_size": actual.stat().st_size, "chapters_total": summary.chapters_total,
                                 "chapters_completed": summary.chapters_completed,
                                 "chapters_failed": list(summary.chapters_failed), "voice_profile": voice_name},
                             error=None, recoverable=False)
        else:
            status = "cancelled" if summary.cancelled else "failed"
            state.update({"status": status, "failed_chapters": list(summary.chapters_failed or []),
                          "completed_chapters": list(summary.chapters_completed_numbers or [])})
            save_state(project.folder, state)
            detail = summary.packaging_error or ("; ".join(str(v) for v in (summary.failure_details or {}).values())
                                                if summary.failure_details else "Generated output did not pass final validation.")
            current = self._jobs.get(job_id, {}).get("progress", 0)
            self._job_update(job_id, state=status, stage="Generation " + status,
                             progress=min(98, int(current or 0)), message=detail,
                             # A previous successful file may still exist at the same
                             # destination. Do not attach it to a failed/cancelled job
                             # as if this attempt produced a complete audiobook.
                             output_path=str(actual) if valid and status != "cancelled"
                                 and not summary.packaging_failed and not summary.chapters_failed else None,
                             error={"code": status, "message": detail,
                                    "failed_chapters": list(summary.chapters_failed or [])},
                             recoverable=not summary.cancelled)
        with self._jobs_lock:
            self._generators.pop(job_id, None)

    def _production_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        name = str(payload.get("profile_name") or load_state(project.folder).get("voice_profile") or "")
        if not name:
            raise ValueError("Select and save a narrator before creating a production preview.")
        return self._voice_preview({**payload, "profile_name": name})

    def _job_pause(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = str(payload.get("job_id") or "")
        with self._jobs_lock:
            manager = self._generators.get(job_id)
        if manager is None:
            raise ValueError("This job has no active pause-capable generation worker.")
        manager.pause()
        return self._job_update(job_id, state="pause_requested", stage="Pause requested",
                                message="The active audio chunk will finish before pausing at the next safe chapter checkpoint.")

    def _job_resume(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = str(payload.get("job_id") or "")
        with self._jobs_lock:
            manager = self._generators.get(job_id)
        if manager is None:
            raise ValueError("No live worker can resume this job. Start generation from the project to reuse compatible checkpoints.")
        manager.resume()
        return self._job_update(job_id, state="running", stage="Resuming generation", message="Resume requested.")

    def _job_cancel(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = str(payload.get("job_id") or "")
        with self._jobs_lock:
            manager = self._generators.get(job_id)
            row = self._jobs.get(job_id)
        if manager is None:
            with self._jobs_lock:
                preview_cancel = self._preview_cancel_events.get(job_id)
                import_cancel = self._import_cancel_events.get(job_id)
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
            if row and row.get("state") in {"queued", "running", "paused"}:
                return self._job_update(job_id, state="cancelled", stage="Cancelled", message="Job cancelled before active processing.")
            raise ValueError("Choose an active background job to cancel.")
        manager.cancel()
        return self._job_update(job_id, state="cancel_requested", stage="Cancellation requested", message="Stopping the provider safely.")

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
            "file_url": output.resolve().as_uri(),
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
                   "concurrency": "production/concurrency", "local_first": "privacy/local_first",
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

    def _models_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the live, provider-aware local model and runtime inventory."""
        from app.core.paths import models_root
        from app.tts.model_registry import mark_installed
        from app.tts.providers.piper import PiperProvider
        from app.tts.providers.kokoro import KokoroProvider
        from app.tts.chatterbox_runtime import RUNTIME_DIR as CHATTERBOX_ROOT, runtime_ready as chatterbox_ready
        from app.tts.qwen_character_runtime import (
            MODEL_IDS, MODEL_DIRS, model_installed as qwen_model_installed,
            runtime_ready as qwen_runtime_ready, RUNTIME_ROOT as QWEN_ROOT,
            VENV_ROOT as QWEN_VENV_ROOT, PYTHON_ROOT as QWEN_PYTHON_ROOT,
            MARKER as QWEN_MARKER, INSTALLER_PATH as QWEN_INSTALLER_PATH,
            INSTALLER_LOG as QWEN_INSTALLER_LOG,
        )
        root = models_root()
        root.mkdir(parents=True, exist_ok=True)
        try:
            disk_free = int(shutil.disk_usage(root).free)
        except OSError:
            disk_free = None

        def byte_size(path: Path, direct_only: bool = False) -> int:
            try:
                if path.is_file():
                    return int(path.stat().st_size)
                if not path.is_dir():
                    return 0
                total = 0
                iterator = path.iterdir() if direct_only else path.rglob("*")
                for candidate in iterator:
                    try:
                        if candidate.is_file():
                            total += candidate.stat().st_size
                    except OSError:
                        continue
                return total
            except OSError:
                return 0

        def row(model_id: str, name: str, provider: str, installed: bool, notes: str, **extra):
            return {
                "model_id": model_id,
                "name": name,
                "provider": provider,
                "installed": bool(installed),
                "status": str(extra.pop("status", "Installed" if installed else "Not installed")),
                "notes": notes,
                "disk_free_bytes": disk_free,
                "storage_root": str(root),
                **extra,
            }

        result: list[dict[str, Any]] = []
        try:
            piper_paths = list(PiperProvider.model_paths())
        except Exception:
            piper_paths = []
        piper_root = (root / "piper").resolve()
        piper_local = []
        for voice_path in piper_paths:
            try:
                if piper_root in voice_path.resolve().parents and voice_path.suffix.casefold() == ".onnx":
                    piper_local.append(voice_path.resolve())
            except OSError:
                continue
        piper_verified = [
            voice_path for voice_path in piper_paths
            if voice_path.is_file()
            and voice_path.stat().st_size > 1024
            and voice_path.with_suffix(voice_path.suffix + ".json").is_file()
        ]
        piper_installed = bool(piper_verified)
        result.append(row(
            "piper", "Piper Offline Neural Voices", "piper", piper_installed,
            "Install individual Piper voice models for offline narration. Installed voice files are listed here; bundled voices are managed by the application installer.",
            status=(f"{len(piper_verified)} voice model(s) verified" if piper_installed else "No verified voice models (not installed or incomplete)"),
            installable=True, repairable=bool(piper_local), uninstallable=bool(piper_local),
            removable_voice_count=len(piper_local),
            installed_voice_names=sorted({item.stem for item in piper_local}, key=str.casefold),
            storage_bytes=sum(byte_size(v) + byte_size(v.with_suffix(v.suffix + ".json")) for v in piper_local),
            requirements="Local model files; no internet required after download.",
            component_type="model",
        ))

        kokoro_root = root / "kokoro"
        kokoro_local = kokoro_root.is_dir() and any(p.is_file() for p in kokoro_root.rglob("*"))
        try:
            kokoro_installed = bool(KokoroProvider.assets_available())
            kokoro_voice_count = len(KokoroProvider().voices()) if kokoro_installed else 0
        except Exception:
            kokoro_installed, kokoro_voice_count = False, 0
        result.append(row(
            "kokoro", "Kokoro 82M Natural Narration", "kokoro", kokoro_installed,
            "Offline natural narration. Requires both the ONNX model and voice pack. Bundled assets cannot be removed separately.",
            status=("Installed locally" if kokoro_local and kokoro_installed else "Bundled with application" if kokoro_installed else "Model or voice pack missing"),
            installable=not kokoro_installed, repairable=bool(kokoro_local or (kokoro_root.exists() and not kokoro_installed)),
            uninstallable=bool(kokoro_local), storage_bytes=byte_size(kokoro_root),
            voice_count=kokoro_voice_count, requirements="About 354 MB download; internet needed only for install/repair.",
            managed_path=str(kokoro_root), bundled=bool(kokoro_installed and not kokoro_local),
        ))

        try:
            chat_installed = bool(chatterbox_ready())
        except Exception:
            chat_installed = False
        chat_present = CHATTERBOX_ROOT.exists()
        chat_installed = bool(chatterbox_ready())
        chat_present = CHATTERBOX_ROOT.exists()
        result.append(row(
            "chatterbox-runtime", "Chatterbox Voice Cloning Runtime", "chatterbox", chat_installed,
            "Shared runtime for English and multilingual reference-based voice cloning. The provider downloads and caches model weights on first use; runtime readiness does not claim those model weights are already present.",
            status=("Runtime ready · English and multilingual modes available" if chat_installed else "Runtime incomplete" if chat_present else "Not installed"),
            installable=not chat_installed, repairable=chat_present or chat_installed,
            uninstallable=chat_present, requirements="Python 3.11 isolated runtime; internet for setup and first-use model weights.",
            storage_bytes=byte_size(CHATTERBOX_ROOT), component_type="runtime",
            managed_path=str(CHATTERBOX_ROOT),
        ))

        try:
            qwen_ready = bool(qwen_runtime_ready())
        except Exception:
            qwen_ready = False
        qwen_runtime_paths = (QWEN_VENV_ROOT, QWEN_PYTHON_ROOT, QWEN_MARKER, QWEN_INSTALLER_PATH, QWEN_INSTALLER_LOG)
        qwen_runtime_present = any(path.exists() for path in qwen_runtime_paths)
        result.append(row(
            "qwen-runtime", "Qwen3-TTS Runtime", "qwen", qwen_ready,
            "Isolated Python, PyTorch, torchaudio and Qwen TTS runtime shared by CustomVoice, VoiceDesign and Voice Clone models.",
            status="Runtime ready" if qwen_ready else "Runtime needs installation or repair",
            installable=not qwen_ready, repairable=qwen_runtime_present or qwen_ready,
            uninstallable=qwen_runtime_present, requirements="Large offline runtime; model weights are managed separately.",
            storage_bytes=sum(byte_size(path) for path in qwen_runtime_paths), managed_path=str(QWEN_ROOT), component_type="runtime",
        ))
        qwen_names = {
            "custom-0.6b": ("Qwen CustomVoice 0.6B", "qwen-customvoice"),
            "custom-1.7b": ("Qwen CustomVoice 1.7B", "qwen-customvoice"),
            "design-1.7b": ("Qwen VoiceDesign 1.7B", "qwen-voicedesign"),
            "base-0.6b": ("Qwen Voice Clone Base 0.6B", "qwen-clone"),
            "base-1.7b": ("Qwen Voice Clone Base 1.7B", "qwen-clone"),
        }
        for kind, repo_id in MODEL_IDS.items():
            try:
                installed = bool(qwen_model_installed(kind))
            except Exception:
                installed = False
            folder_exists = MODEL_DIRS[kind].exists()
            base_ready = False
            if kind == "design-1.7b":
                try:
                    base_ready = bool(qwen_model_installed("base-0.6b") or qwen_model_installed("base-1.7b"))
                except Exception:
                    base_ready = False
            if not installed:
                status = "Model files incomplete · Repair required" if folder_exists else "Not installed"
            elif not qwen_ready:
                status = "Weights installed · Qwen runtime required"
            elif kind == "design-1.7b" and not base_ready:
                status = "VoiceDesign weights installed · Base model dependency missing"
            elif kind == "design-1.7b":
                status = "Installed · VoiceDesign and Base dependencies ready"
            else:
                status = "Installed and file-verified"

            # VoiceDesign needs both the design weights and a Base model to keep
            # a stable reference identity during long-form generation. Its install/
            # repair action therefore installs missing dependencies together.
            install_id = "qwen-voicedesign" if kind == "design-1.7b" else kind
            repair_id = (
                "qwen-runtime" if installed and not qwen_ready else
                "qwen-voicedesign" if kind == "design-1.7b" else kind
            )
            verify_id = "qwen-voicedesign" if kind == "design-1.7b" else kind
            result.append(row(
                kind, qwen_names.get(kind, (repo_id, ""))[0], "qwen", installed,
                f"Local Qwen3-TTS weights from {repo_id}. The matching Qwen3-TTS runtime is also required.",
                status=status,
                installable=not installed and not folder_exists,
                repairable=folder_exists or (installed and (not qwen_ready or (kind == "design-1.7b" and not base_ready))),
                uninstallable=folder_exists,
                install_id=install_id, repair_id=repair_id, verify_id=verify_id,
                feature=qwen_names.get(kind, ("", "qwen"))[1], requirements="Model download can be several GB; requires internet for install/repair.",
                storage_bytes=byte_size(MODEL_DIRS[kind]), managed_path=str(MODEL_DIRS[kind]),
                component_type="model",
            ))

        # This is a status-card refresh, not an installation operation. Do not
        # launch nvidia-smi here just to decide which model to display; inspect
        # the known local candidates directly and let the background installer
        # select hardware-appropriate weights when installation is requested.
        ai_root = root / "audiobook-ai"
        ai_present = ai_root.exists()
        ai_candidates = (
            ("qwen3-4b-q4", "Qwen3-4B-Q4_K_M.gguf"),
            ("qwen3-1.7b-q5", "Qwen3-1.7B-Q5_K_M.gguf"),
        )
        ai_models_on_disk = [
            (model_id, filename, ai_root / filename)
            for model_id, filename in ai_candidates
            if (ai_root / filename).is_file()
        ]
        ai_server_present = (ai_root / "llama-server.exe").is_file()
        ai_installed = bool(ai_server_present and ai_models_on_disk)
        if ai_models_on_disk:
            ai_model_id, ai_filename, ai_model_path = ai_models_on_disk[0]
            try:
                ai_size = int(ai_model_path.stat().st_size)
            except OSError:
                ai_size = 0
        else:
            ai_model_id, ai_filename, ai_size = "auto-selected", "Selected for this PC during installation", 0
        result.append(row(
            "audiobook-ai", "Audiobook AI · Local Book Analysis", "audiobook-ai", ai_installed,
            "Local analysis engine used by book/character analysis. Installer selects a model for detected hardware and runs a real inference self-test.",
            status=("Installed · model files present" if ai_installed else "Runtime/model needs setup" if ai_present else "Not installed"),
            installable=not ai_installed, repairable=ai_present or ai_installed, uninstallable=ai_present,
            model_name=ai_model_id, model_filename=ai_filename, download_bytes=int(ai_size),
            requirements=(f"Installed model file: {ai_size / (1024 ** 3):.1f} GB." if ai_size else
                          "Install downloads a hardware-appropriate local model (typically about 1.2–2.5 GB) and runs a real inference self-test."),
            storage_bytes=byte_size(ai_root, direct_only=True), managed_path=str(ai_root),
            component_type="model",
        ))

        # Avoid constructing a COM speech engine synchronously while the
        # Models page is painting. Windows SAPI voice tokens are registered in
        # the system/user registry; Voice Studio later enumerates the full live
        # provider catalogue when the user opens that library.
        sapi_tokens: set[str] = set()
        try:
            import winreg
            registry_paths = (
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Speech\Voices\Tokens"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Speech\Voices\Tokens"),
            )
            for hive, registry_path in registry_paths:
                try:
                    with winreg.OpenKey(hive, registry_path) as key:
                        count = winreg.QueryInfoKey(key)[0]
                        for index in range(count):
                            try:
                                sapi_tokens.add(str(winreg.EnumKey(key, index)).casefold())
                            except OSError:
                                continue
                except OSError:
                    continue
        except ImportError:
            pass
        sapi_count = len(sapi_tokens)
        result.append(row(
            "windows-sapi", "Windows SAPI System Voices", "windows-sapi", sapi_count > 0,
            "Uses voices installed in Windows. These are managed by Windows settings, not downloaded or removed by Ryu's Audiobook.",
            status=f"{sapi_count} Windows voice(s) detected" if sapi_count else "No Windows SAPI voices detected",
            installable=False, repairable=False, uninstallable=False, voice_count=sapi_count,
            requirements="Windows system component; not a separately managed model.",
            component_type="provider",
        ))

        try:
            from app.tts.providers.edge_tts import EdgeTTSProvider
            edge_ready = bool(EdgeTTSProvider.available())
        except Exception:
            edge_ready = False
        result.append(row(
            "edge-tts", "Microsoft Edge TTS · Online Voices", "edge-tts", edge_ready,
            "Online neural voice service, not a local model download. Voice catalogue and synthesis require network access.",
            status="Client package available · internet required" if edge_ready else "Edge TTS package unavailable",
            installable=False, repairable=False, uninstallable=False, requirements="Internet connection; not an offline model.",
            component_type="provider",
        ))

        try:
            from app.tts.providers.elevenlabs import ElevenLabsProvider
            eleven_key = bool(ElevenLabsProvider.load_api_key())
        except Exception:
            eleven_key = False
        result.append(row(
            "elevenlabs", "ElevenLabs · Premium Online Voices", "elevenlabs", eleven_key,
            "Online provider access is configured when a local API key is present. Voice management and API credentials remain in Voice Studio.",
            status="API key configured" if eleven_key else "API key required",
            installable=False, repairable=False, uninstallable=False, credentials_configured=eleven_key,
            requirements="Internet and your own ElevenLabs API key; no local model to install.",
            component_type="provider",
        ))
        return result

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
                    outcome = self._models_uninstall_component(model_id, details, report_progress)
                else:
                    outcome = self._models_install_component(model_id, details, report_progress, force_repair=action == "repair")
                report_progress("Refreshing actual installed state…")
                latest = self._models_list({})
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
        allowed = {"piper", "kokoro", "chatterbox", "chatterbox-multilingual", "chatterbox-runtime",
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
                job for job in self._jobs.values()
                if str(job.get("state") or "").casefold() in {"queued", "running"}
                and any(token in str(job.get("type") or "").casefold()
                        for token in ("voice-preview", "production", "generation", "character-analyze", "model-install", "model-repair"))
            ]
        if blocking:
            raise RuntimeError("Uninstall is blocked while a voice preview, audiobook generation, analysis, or model installation/repair job is active. Stop or finish that job, then retry.")

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

        if requested in {"chatterbox", "chatterbox-multilingual", "chatterbox-runtime"}:
            from app.tts.chatterbox_runtime import RUNTIME_DIR
            if RUNTIME_DIR.exists():
                report("Removing the shared Chatterbox runtime…")
                self._models_remove_path(RUNTIME_DIR, root)
            mark_installed("chatterbox", False)
            mark_installed("chatterbox-multilingual", False)
            return "Removed the shared Chatterbox runtime. Saved profiles and books were kept."

        if requested == "qwen-model" or requested in {"custom-0.6b", "custom-1.7b", "design-1.7b", "base-0.6b", "base-1.7b"}:
            from app.tts.qwen_character_runtime import MODEL_DIRS, RUNTIME_ROOT
            kind = str(payload.get("model_kind") or requested).strip().casefold()
            if kind not in MODEL_DIRS:
                raise ValueError("Choose the exact installed Qwen model to uninstall.")
            target = MODEL_DIRS[kind]
            if not target.exists():
                raise ValueError(f"Qwen model {kind} is not installed.")
            report(f"Removing Qwen model {kind}…")
            self._models_remove_path(target, RUNTIME_ROOT)
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
        elif requested in {"chatterbox", "chatterbox-multilingual", "chatterbox-runtime"}:
            from app.tts.chatterbox_runtime import runtime_ready
            available = bool(runtime_ready())
            detail = "Chatterbox runtime ready; model weights may still be fetched on first use." if available else "Chatterbox runtime is missing or incomplete."
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
        return {"model_id": requested, "available": available, "detail": detail, "path": path,
                "status": "Ready" if available else "Needs attention", "model": item}

    def _performance_info(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return {"available": False, "reason": "Live CPU, GPU and VRAM telemetry is not connected to Premium V2 yet."}

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
        value = str(state.get("output_path") or "")
        path = Path(value).expanduser() if value else project.folder
        folder = path if path.is_dir() else path.parent
        if not folder.exists():
            raise FileNotFoundError("The output folder does not exist yet.")
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve()))):
            raise RuntimeError("Windows did not open the output folder.")
        return {"opened": True, "path": str(folder.resolve())}

    def _sound_catalog(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        from app.audio.library import AUDIO_EXTENSIONS, metadata_for
        extensions = AUDIO_EXTENSIONS
        roots = [(app_root() / "Audio Library", "Imported locally")]
        bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "assets" / "starter_audio"
        if bundled.is_dir():
            roots.append((bundled, "Bundled with application"))
        found: dict[str, dict[str, Any]] = {}
        for root, source in roots:
            if not root.is_dir():
                continue
            try:
                candidates = root.rglob("*")
                for path in candidates:
                    if not path.is_file() or path.suffix.lower() not in extensions:
                        continue
                    try:
                        resolved = path.resolve()
                        size = resolved.stat().st_size
                    except OSError:
                        continue
                    if size <= 0:
                        continue
                    key = str(resolved)
                    metadata = metadata_for(resolved)
                    license_note = str(metadata.get("license_note") or metadata.get("source_note") or metadata.get("license") or "Unknown; verify rights before publishing")
                    found[key] = {"id": key, "title": str(metadata.get("title") or path.stem), "path": key,
                                  "source": source, "format": path.suffix.lower(),
                                  "size_bytes": size, "duration_seconds": metadata.get("duration_seconds"),
                                  "licensing": license_note, "metadata": metadata}
            except OSError:
                log.exception("Could not scan sound asset folder %s", root)
        return sorted(found.values(), key=lambda row: (row["source"], row["title"].casefold()))

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
        from app.audio.library import AUDIO_EXTENSIONS, probe_audio_duration_seconds
        extensions = AUDIO_EXTENSIONS
        target_root = app_root() / "Audio Library"
        target_root.mkdir(parents=True, exist_ok=True)
        imported = []
        for raw in paths:
            source = Path(str(raw)).expanduser().resolve()
            if not source.is_file() or source.suffix.lower() not in extensions:
                raise ValueError(f"Unsupported or missing audio asset: {source.name}")
            duration_seconds = probe_audio_duration_seconds(source)
            destination = target_root / source.name
            if destination.exists() and destination.resolve() != source:
                destination = target_root / f"{source.stem}-{uuid.uuid4().hex[:8]}{source.suffix.lower()}"
            if source != destination.resolve():
                shutil.copy2(source, destination)
            metadata_path = destination.with_name(destination.name + ".license.json")
            metadata = {"role": "music" if str(payload.get("target_kind") or "").casefold() == "music" else "cue",
                        "category": str(payload.get("category") or "universal"),
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
        return {"cancelled": False, "imported": imported, "catalog": self._sound_catalog({})}

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
            state.update({"background_audio_path": "", "background_audio_mode": "off",
                          "background_audio_enabled": False,
                          "background_audio_fade_in": fade_in, "background_audio_fade_out": fade_out})
            save_state(project.folder, state)
            return {"saved": True, "path": None, "mode": "off",
                    "fade_in_seconds": fade_in, "fade_out_seconds": fade_out}
        selected = Path(raw).expanduser().resolve()
        valid = any(str(row["path"]) == str(selected) for row in self._sound_catalog({}))
        if not selected.is_file() or not valid:
            raise ValueError("Choose an audio file from the local Sound Design catalogue.")
        try:
            volume = max(0.0, min(1.0, float(payload.get("volume", 0.18))))
            fade_in = max(0.0, min(30.0, float(payload.get("fade_in_seconds", state.get("background_audio_fade_in", 2.0)))))
            fade_out = max(0.0, min(30.0, float(payload.get("fade_out_seconds", state.get("background_audio_fade_out", 3.0)))))
        except (TypeError, ValueError):
            raise ValueError("Background volume must be 0–100 percent and fades 0–30 seconds.")
        state.update({"background_audio_path": str(selected), "background_audio_volume": volume,
                      "background_audio_fade_in": fade_in, "background_audio_fade_out": fade_out,
                      "background_audio_mode": "manual", "background_audio_enabled": True,
                      "modified_at": self._now()})
        save_state(project.folder, state)
        return {"saved": True, "path": str(selected), "title": selected.stem, "volume": volume,
                "fade_in_seconds": fade_in, "fade_out_seconds": fade_out, "mode": "manual"}

    def _sound_save_manifest(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        state = load_state(project.folder)
        path = str(payload.get("path") or state.get("background_audio_path") or "").strip()
        enabled = bool(payload.get("enabled", bool(path)))
        try:
            volume = max(0.0, min(1.0, float(payload.get("volume", state.get("background_audio_volume") if state.get("background_audio_volume") is not None else 0.18))))
            fade_in = max(0.0, min(30.0, float(payload.get("fade_in_seconds", state.get("background_audio_fade_in", 2.0)))))
            fade_out = max(0.0, min(30.0, float(payload.get("fade_out_seconds", state.get("background_audio_fade_out", 3.0)))))
        except (TypeError, ValueError):
            raise ValueError("Background volume must be 0–100 percent and fades 0–30 seconds.")
        if enabled and path:
            selected = Path(path).expanduser().resolve()
            if not selected.is_file() or not any(row["path"] == str(selected) for row in self._sound_catalog({})):
                raise ValueError("Selected BGM is missing from the local sound library.")
            state.update({"background_audio_path": str(selected), "background_audio_mode": "manual",
                          "background_audio_enabled": True, "background_audio_volume": volume})
        else:
            state.update({"background_audio_path": "", "background_audio_mode": "off", "background_audio_enabled": False})
        state["background_audio_fade_in"] = fade_in
        state["background_audio_fade_out"] = fade_out
        state["sound_manifest"] = {"bgm_path": state.get("background_audio_path") or None,
                                   "bgm_volume": volume, "fade_in_seconds": fade_in,
                                   "fade_out_seconds": fade_out, "enabled": bool(enabled and path),
                                   "updated_at": self._now()}
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
        overrides: dict[str, dict[str, Any]] = {}
        for key, value in stored.items():
            if not isinstance(value, dict):
                continue
            row = dict(value)
            raw_path = str(row.get("path") or "")
            track = catalog.get(raw_path)
            row["path"] = raw_path if track else None
            row["title"] = track["title"] if track else None
            row["available"] = bool(track) if row.get("rule") == "custom" else True
            overrides[str(key)] = row
        return {
            "strategy": str(state.get("chapter_bgm_strategy") or "same"),
            "default_path": state.get("background_audio_path") or None,
            "default_volume": float(state.get("background_audio_volume") if state.get("background_audio_volume") is not None else 0.18),
            "fade_in_seconds": float(state.get("background_audio_fade_in") if state.get("background_audio_fade_in") is not None else 2.0),
            "fade_out_seconds": float(state.get("background_audio_fade_out") if state.get("background_audio_fade_out") is not None else 3.0),
            "overrides": overrides,
            "chapters": [{"number": chapter.number, "title": chapter.title} for chapter in project.chapters],
        }

    def _sound_chapter_bgm_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist the selected chapter's BGM rule, or change the book-wide strategy."""
        project = self._active_project()
        state = load_state(project.folder)
        strategy = str(payload.get("strategy") or "").strip().lower()
        if strategy:
            if strategy not in {"same", "custom"}:
                raise ValueError("Choose Same BGM or Chapter-based BGM.")
            state["chapter_bgm_strategy"] = strategy
            if strategy == "same":
                state["chapter_bgm_overrides"] = {}
            else:
                # Chapter-specific tracks must be mixed even when the book has
                # no separate default BGM assigned. The assembler gates custom
                # overrides on manual mode, so choosing chapter-based BGM
                # explicitly activates that mode.
                state["background_audio_mode"] = "manual"
            state["modified_at"] = self._now()
            save_state(project.folder, state)
            return self._sound_chapter_bgm_get({})
        try:
            number = int(payload.get("number"))
        except (TypeError, ValueError):
            raise ValueError("Choose a valid chapter before saving its BGM.")
        chapter = next((item for item in project.chapters if item.number == number), None)
        if chapter is None:
            raise ValueError("The selected chapter no longer exists. Refresh Chapter Studio.")
        rule = str(payload.get("rule") or "default").strip().lower()
        if rule not in {"default", "custom", "none"}:
            raise ValueError("Choose book default, custom BGM, or no BGM.")
        path = None
        title = None
        if rule == "custom":
            raw_path = str(payload.get("path") or "").strip()
            selected = Path(raw_path).expanduser().resolve() if raw_path else None
            catalog = {str(row["path"]): row for row in self._sound_catalog({})}
            row = catalog.get(str(selected)) if selected else None
            if selected is None or not selected.is_file() or row is None:
                raise ValueError("Choose a custom track from the local Sound Design catalogue.")
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
        overrides[str(number)] = {
            "rule": rule, "path": path, "volume": volume,
            "start_offset": start_offset, "end_behavior": end_behavior,
        }
        state["chapter_bgm_overrides"] = overrides
        state["chapter_bgm_strategy"] = "custom"
        state["background_audio_mode"] = "manual"
        state["modified_at"] = self._now()
        save_state(project.folder, state)
        return {"saved": True, "number": number, "title": chapter.title,
                "rule": rule, "path": path, "track_title": title,
                "strategy": "custom", "override_count": len(overrides)}

    def _sound_cues_get(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Return persisted book cue assignments, resolving legacy state keys."""
        project = self._active_project()
        state = load_state(project.folder)
        cues = state.get("sound_cues")
        if not isinstance(cues, dict):
            cues = {
                "opening": state.get("opening_cue_path"),
                "chapter": state.get("page_turn_cue_path"),
                "scene": state.get("scene_transition_cue_path"),
                "closing": state.get("ending_cue_path"),
            }
        catalog = {str(row["path"]): row for row in self._sound_catalog({})}
        result = {}
        for slot in ("opening", "chapter", "scene", "closing"):
            raw = cues.get(slot)
            path = str(raw).strip() if raw else ""
            row = catalog.get(path)
            result[slot] = {"path": path if row else None, "title": row["title"] if row else None,
                            "available": bool(row)}
        return result

    def _sound_cues_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist one cue assignment and update the supported generation cue fields."""
        slot = str(payload.get("slot") or "").strip().lower()
        if slot not in {"opening", "chapter", "scene", "closing"}:
            raise ValueError("Choose opening, chapter, scene, or closing cue.")
        raw = str(payload.get("path") or "").strip()
        selected_path = None
        selected_title = None
        if raw:
            selected = Path(raw).expanduser().resolve()
            catalog = {str(row["path"]): row for row in self._sound_catalog({})}
            row = catalog.get(str(selected))
            if not selected.is_file() or row is None:
                raise ValueError("Choose a cue from the local Sound Design catalogue.")
            selected_path, selected_title = str(selected), str(row["title"])
        project = self._active_project()
        state = load_state(project.folder)
        cues = state.get("sound_cues")
        if not isinstance(cues, dict):
            cues = {
                "opening": state.get("opening_cue_path"),
                "chapter": state.get("page_turn_cue_path"),
                "scene": state.get("scene_transition_cue_path"),
                "closing": state.get("ending_cue_path"),
            }
        cues[slot] = selected_path
        state["sound_cues"] = cues
        state["chapter_transition_sound"] = any(cues.get(key) for key in ("opening", "chapter", "closing"))
        # Keep the legacy fields synchronized with the saved cue manifest; the
        # production assembler consumes all four cue paths, including scene transitions.
        if slot == "opening":
            state["opening_cue_path"] = selected_path
        elif slot == "chapter":
            state["page_turn_cue_path"] = selected_path
        elif slot == "closing":
            state["ending_cue_path"] = selected_path
        else:
            # Scene transitions are mixed independently from the
            # opening/chapter/closing cue toggle.
            state["scene_transition_cue_path"] = selected_path
        state["modified_at"] = self._now()
        save_state(project.folder, state)
        return {"saved": True, "slot": slot, "path": selected_path, "title": selected_title,
                "generation_supported": True}

    def _sound_cues_clear(self, _payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        state = load_state(project.folder)
        state["sound_cues"] = {"opening": None, "chapter": None, "scene": None, "closing": None}
        state["opening_cue_path"] = None
        state["page_turn_cue_path"] = None
        state["scene_transition_cue_path"] = None
        state["ending_cue_path"] = None
        state["chapter_transition_sound"] = False
        state["modified_at"] = self._now()
        save_state(project.folder, state)
        return {"saved": True, "cleared": ["opening", "chapter", "scene", "closing"]}

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
        if kind in {"javascript-error", "unhandled-rejection", "adapter-start-failed"}:
            log.error("Premium V2 frontend %s: %s (source=%s, line=%s)%s",
                      kind, message or "(no message)", source or "(inline)", line,
                      ("\\n" + stack) if stack else "")
        else:
            log.warning("Premium V2 frontend %s: %s (source=%s, line=%s)",
                        kind, message or "(no message)", source or "(inline)", line)

        # A top-level adapter failure means essential frontend wiring/hydration
        # did not finish. Show the native recovery surface immediately instead
        # of leaving the user on the loading screen until the watchdog expires.
        if kind == "adapter-start-failed":
            window = self.parent()
            show_failure = getattr(window, "_show_web_failure", None)
            if callable(show_failure) and not getattr(window, "_frontend_ready", False):
                show_failure(
                    "The Premium V2 interface could not complete startup. "
                    "Your local project files have not been deleted. Details: " +
                    (message or "The adapter failed without a diagnostic message.")
                )
        return True

    def _settings_get(self, _payload: dict[str, Any]) -> dict[str, Any]:
        self.settings.sync()
        return {
            "theme": self.settings.value("ui/theme", "dark"),
            "effects": self.settings.value("ui/effects", "high"),
            "reduce_motion": self.settings.value("ui/reduce_motion", False, type=bool),
            "accent": self.settings.value("ui/accent", "crimson"),
            "interface_scale": self.settings.value("ui/interface_scale", 100),
            "text_scale": self.settings.value("ui/text_scale", 100),
            "window_size": self.settings.value("ui/window_size", "auto"),
            "storage_root": str(app_root()),
            "library_root": str(library_root()),
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
        self._loading_progress.setRange(0, 100)
        self._loading_progress.setValue(3)
        self._loading_progress.setFormat("%p%")
        self._loading_progress.setTextVisible(True)
        self._loading_progress.setFixedHeight(22)
        self._loading_progress.setMinimumWidth(300)
        self._loading_progress.setMaximumWidth(480)
        self._loading_progress.setStyleSheet(
            "QProgressBar{background:#19141d;border:1px solid #342634;border-radius:7px;"
            "color:#f7edf2;text-align:center;font-size:10px;font-weight:700;}"
            "QProgressBar::chunk{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #8c1735,stop:1 #e64160);border-radius:6px;}"
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

    def _show_web_failure(self, message: str) -> None:
        self._frontend_failure_shown = True
        log.error("Premium V2 renderer recovery surface shown: %s", message)
        if hasattr(self, "_web_error_message"):
            self._web_error_message.setText(str(message))
        if hasattr(self, "_web_stack") and hasattr(self, "_web_error_page"):
            self._web_stack.setCurrentWidget(self._web_error_page)

    def _set_loading_status(self, message: str) -> None:
        if hasattr(self, "_loading_status"):
            self._loading_status.setText(str(message or "Starting the Windows interface…"))

    def _update_startup_progress(self, message: str, progress: int | None = None) -> None:
        """Show live native loading status from confirmed frontend startup milestones."""
        if self._frontend_ready or self._frontend_failure_shown:
            return
        self._set_loading_status(message)
        if progress is None:
            return
        try:
            value = max(0, min(100, int(progress)))
        except (TypeError, ValueError, OverflowError):
            return
        # Ignore stale/out-of-order status callbacks so the visible meter never
        # moves backwards during one startup attempt.
        self._startup_progress_value = max(self._startup_progress_value, value)
        if hasattr(self, "_loading_progress"):
            self._loading_progress.setValue(self._startup_progress_value)

    def _on_frontend_ready(self) -> None:
        """Reveal the app only after the backend bridge and frontend wiring have finished."""
        self._set_loading_status("Studio ready. Opening your workspace…")
        self._startup_progress_value = 100
        if hasattr(self, "_loading_progress"):
            self._loading_progress.setValue(100)
        self._frontend_ready = True
        self._frontend_failure_shown = False
        self._renderer_restart_attempts = 0
        if hasattr(self, "_web_stack") and hasattr(self, "web"):
            self._web_stack.setCurrentWidget(self.web)
        log.info("Premium V2 frontend and native backend bridge are ready")

    def _retry_web_renderer(self) -> None:
        # Keep the native loading surface visible during reload. Switching to the
        # WebEngine first exposes a blank frame until Chromium paints the page.
        self._frontend_ready = False
        self._frontend_failure_shown = False
        self._startup_progress_value = 0
        self._frontend_generation += 1
        generation = self._frontend_generation
        self._update_startup_progress("Retrying the interface and reconnecting local services…", 5)
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
        if hasattr(self, "_web_stack") and hasattr(self, "_loading_page"):
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
          const setup = () => {
            if (!window.QWebChannel || !window.qt || !qt.webChannelTransport) return false;
            new QWebChannel(qt.webChannelTransport, channel => {
              const native = channel.objects.ryuBackend;
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
        self._update_startup_progress("Starting saved-settings and project checks…", 28)
        self.web.page().runJavaScript(script)
        # Check for a UI that loaded at the HTML level but never finished
        # initializing the backend adapter. This gives the user a native
        # recovery surface instead of an indefinitely blank black window.
        QTimer.singleShot(15000, lambda: self._check_frontend_ready(generation))

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