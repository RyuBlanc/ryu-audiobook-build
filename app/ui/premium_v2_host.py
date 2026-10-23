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
import unicodedata
import uuid
import wave
from datetime import datetime, timezone
from typing import Any

from PySide6.QtCore import QObject, QSettings, QUrl, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QLabel, QMainWindow, QVBoxLayout, QWidget
from PySide6.QtGui import QDesktopServices

from app.core.paths import app_root, audiobooks_root, ensure_roots, library_root, settings_root
from app.core.project import create_project, list_projects
from app.documents.cover_art import COVER_IMAGE_EXTENSIONS, COVER_SOURCE_EXTENSIONS, extract_embedded_cover, persist_project_cover
from app.documents.parser import SUPPORTED_EXTENSIONS, clean_import_noise, clean_text, detect_repeated_book_noise, extract_text
from app.chapters.detector import detect_chapters
from app.chapters.characters import analyze_book, merge_character_analysis_record
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
        self._jobs: dict[str, dict[str, Any]] = {}
        self._generators: dict[str, GenerationManager] = {}
        self._import_cancel_events: dict[str, threading.Event] = {}
        self._preview_cancel_events: dict[str, threading.Event] = {}
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
                "voice.save": self._voice_save,
                "voice.delete": self._voice_delete,
                "voice.import_reference": self._voice_import_reference,
                "voice.select": self._voice_select,
                "voice.preview": self._voice_preview,
                "character.list": self._character_list,
                "character_library.list": self._character_library_list,
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
            "voice.save": True,
            "voice.delete": True,
            "voice.import_reference": True,
            "voice.select": True,
            "voice.preview": True,
            "character.list": True,
            "character_library.list": True,
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
        canonical_by_name: dict[str, str] = {}
        for item in characters:
            name = str(item.get("name") or "").strip()
            if name:
                canonical_by_name[name.casefold()] = name
            aliases = item.get("aliases") or []
            if isinstance(aliases, list):
                for alias in aliases:
                    alias = str(alias).strip()
                    if alias:
                        canonical_by_name[alias.casefold()] = name
        speakers = []
        for raw_name in raw_speakers:
            name = str(raw_name or "").strip()
            canonical = canonical_by_name.get(name.casefold())
            if not canonical:
                raise ValueError(f"'{name or 'Unknown'}' is not in the saved character list. Run book analysis or select a saved character.")
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
        result = assign_dialogue_to_chapters(project.chapters, dialogue_text, speakers,
                                             chapter_number=chapter_number, mode=mode)
        project.save()
        project_state = load_state(project.folder)
        project_state["modified_at"] = self._now()
        save_state(project.folder, project_state)
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
        result = unassign_dialogue_from_chapters(
            project.chapters, chapter_number, start, end, str(payload.get("dialogue_text") or "")
        )
        project.save()
        project_state = load_state(project.folder)
        project_state["modified_at"] = self._now()
        save_state(project.folder, project_state)
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

    def _persist_jobs(self) -> None:
        path = self._jobs_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(list(self._jobs.values()), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temporary.replace(path)

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
        if rows:
            self._persist_jobs()

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
            self._persist_jobs()
            return dict(row)

    def _job_list(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        with self._jobs_lock:
            include_hidden = bool(payload.get("include_hidden", False))
            rows = [dict(j) for j in self._jobs.values() if include_hidden or not j.get("hidden")]
        return sorted(rows, key=lambda j: str(j.get("queued_at") or ""), reverse=True)

    def _history_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        with self._jobs_lock:
            rows = [dict(j) for j in self._jobs.values()]
        return sorted(rows, key=lambda j: str(j.get("queued_at") or ""), reverse=True)

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
        """Import and normalize an explicitly selected voice-reference recording."""
        profile_name = str(payload.get("profile_name") or payload.get("name") or "Custom Voice").strip()
        source_text = str(payload.get("source_path") or payload.get("path") or "").strip()
        if source_text:
            source = Path(source_text).expanduser().resolve()
        else:
            selected, _filter = QFileDialog.getOpenFileName(
                None, "Select authorized voice reference audio", str(Path.home()),
                "Audio files (*.wav *.mp3 *.flac *.ogg *.m4a *.aac *.aiff *.opus)",
            )
            if not selected:
                return {"cancelled": True, "sample_path": None}
            source = Path(selected).resolve()
        from app.tts.voice_profile import import_reference_audio
        normalized = import_reference_audio(source, profile_name)
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
        built_in_collision = next(
            (p for p in load_profiles() if p.name.casefold() == name.casefold()
             and existing is None),
            None,
        )
        if built_in_collision is not None:
            raise ValueError("That name is already used by a built-in voice. Choose a distinct profile name.")

        sample_path = str(payload.get("sample_path") or "").strip() or None
        reference_path = str(payload.get("reference_path") or "").strip()
        if reference_path:
            sample_path = str(import_reference_audio(Path(reference_path).expanduser().resolve(), name).resolve())
        if sample_path:
            sample = Path(sample_path).expanduser().resolve()
            if not sample.is_file():
                raise FileNotFoundError("The custom voice reference audio is missing.")
            sample_path = str(sample)

        qwen_mode = str(payload.get("qwen_mode") or ("clone" if provider_name == "chatterbox" else "custom")).strip().lower()
        authorized = bool(payload.get("authorized", False))
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
            model_id=str(payload.get("model_id") or ("chatterbox" if provider_name == "chatterbox" else "auto")),
            backend=str(payload.get("backend") or "automatic"),
            language=str(payload.get("language") or "English"),
            notes=str(payload.get("notes") or payload.get("description") or "")[:4000],
            authorized=authorized,
            exaggeration=max(0.0, min(1.0, float(payload.get("exaggeration", 0.5)))),
            cfg_weight=max(0.0, min(1.0, float(payload.get("cfg_weight", 0.35)))),
            style_preset=str(payload.get("style_preset") or "Natural"),
            qwen_mode=qwen_mode,
            qwen_prompt=str(payload.get("qwen_prompt") or payload.get("prompt") or "")[:4000],
            qwen_seed=int(payload["qwen_seed"]) if payload.get("qwen_seed") not in (None, "") else None,
            reference_text=str(payload.get("reference_text") or "")[:10000],
            qwen_anchor_path=str(payload.get("qwen_anchor_path") or "") or None,
            qwen_anchor_text=str(payload.get("qwen_anchor_text") or "")[:10000],
            qwen_profile_id=str(payload.get("qwen_profile_id") or ""),
        )
        if existing is not None:
            saved[saved.index(existing)] = profile
        else:
            saved.append(profile)
        save_profiles(saved)
        return {"name": profile.name, "provider": profile.provider, "voice_id": profile.voice_id,
                "sample_path": profile.sample_path, "model_id": profile.model_id,
                "backend": profile.backend, "language": profile.language,
                "authorized": profile.authorized, "qwen_mode": profile.qwen_mode, "saved": True,
                "count": len(load_profiles())}

    def _voice_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        return [{
            "name": p.name, "provider": p.provider, "voice_id": p.voice_id,
            "model_id": p.model_id, "backend": p.backend, "language": p.language or "",
            "sample_path": p.sample_path, "authorized": bool(p.authorized),
            "qwen_mode": getattr(p, "qwen_mode", "custom"),
        } for p in load_profiles()]

    def _find_profile(self, name: str | None):
        wanted = str(name or "").strip().casefold()
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

    def _voice_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        state = load_state(project.folder)
        profile = self._find_profile(payload.get("profile_name") or state.get("voice_profile"))
        if profile is None:
            raise ValueError("Select an installed or saved voice profile before previewing.")
        text_value = str(payload.get("text") or "")
        number = payload.get("chapter_number")
        if not text_value.strip():
            chapter = next((c for c in project.chapters if (c.text or "").strip() and (number is None or c.number == int(number))), None)
            if chapter is None:
                raise ValueError("Select a chapter that contains narration text.")
            text_value = chapter.text
        seconds = int(payload.get("duration_seconds") or payload.get("duration") or 30)
        if seconds not in {10, 20, 30, 45, 60}:
            raise ValueError("Preview duration must be 10, 20, 30, 45, or 60 seconds.")
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
        try:
            if cancel_event is not None and cancel_event.is_set():
                raise PreviewCancelledError("Preview cancelled by user.")
            provider, voice = provider_from_profile(profile)
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
            if cast_assignments:
                from app.tts.cast_provider import CastAwareProvider
                provider = CastAwareProvider(
                    provider, voice, cast_profiles, cast_assignments,
                    narrating_character=str(state.get("narrating_character") or ""),
                    backend_override=str(state.get("backend") or "automatic"),
                )
            folder = app_root() / "Previews"
            folder.mkdir(parents=True, exist_ok=True)
            output = folder / f"preview_{job_id}.wav"
            def progress(stage: str, current: int, total: int) -> None:
                self._job_update(job_id, stage=str(stage), progress=min(95, max(2, 5 + int(90 * current / max(1, total)))))
            result = build_voice_preview(
                text_value, provider, voice, output,
                pronunciation_dictionary=_effective_pronunciation_dictionary(state),
                narration_speed=float(state.get("narration_speed") or 0.90),
                pacing_profile=str(state.get("pacing_profile") or "natural"),
                max_chars=max(1400, seconds * 240), progress_callback=progress,
                target_seconds=seconds,
                cancel_check=cancel_event.is_set if cancel_event is not None else None,
            )
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
            self._job_update(job_id, state="completed", stage="Preview ready", progress=100,
                             message=("Sound Design mix preview ready." if state.get("_include_sound_design_preview") else "Audio preview generated.") + count_message,
                             output_path=str(preview_path), result={
                                 "output_path": str(preview_path), "file_url": preview_path.resolve().as_uri(),
                                 "requested_duration_seconds": seconds, "actual_duration_seconds": duration,
                                 "voices_used": list(result.voices_used), "segments": result.segments,
                                 "selected_profile": profile.name,
                                 "selected_provider": str(getattr(profile, "provider", "") or ""),
                                 "selected_voice_id": str(getattr(profile, "voice_id", "") or ""),
                                 "pronunciation_replacements": replacements,
                                 "pronunciation_rule_counts": dict(rule_counts),
                             })
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
            if cancel_event is not None:
                with self._jobs_lock:
                    self._preview_cancel_events.pop(job_id, None)

    def _character_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        state = load_state(self._active_project().folder)
        rows = state.get("characters") or []
        return rows if isinstance(rows, list) else []

    def _character_analyze(self, _payload: dict[str, Any]) -> dict[str, Any]:
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
            analysis = analyze_book(project.chapters)
            state = load_state(project.folder)
            old = {str(c.get("name", "")).casefold(): c for c in (state.get("characters") or []) if isinstance(c, dict)}
            items = []
            for c in analysis.characters:
                prior = old.get(c.name.casefold(), {})
                items.append(merge_character_analysis_record(c, prior))
            state["characters"] = items
            state["character_analysis"] = {"dialogue_total": analysis.dialogue_total,
                                           "unassigned_dialogue": analysis.unassigned_dialogue,
                                           "updated_at": self._now()}
            state["modified_at"] = self._now()
            save_state(project.folder, state)
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
        item = next((c for c in characters if str(c.get("name", "")).casefold() == name.casefold()), None)
        if item is None:
            raise ValueError("That character is not in saved analysis. Run analysis again.")
        item["voice_profile"] = profile_name or None
        state["characters"] = characters
        state["modified_at"] = self._now()
        save_state(project.folder, state)
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
        item.update({
            "name": name,
            "role": str(role_value or "Character").strip()[:160],
            "short_description": str(description_value or "").strip()[:1000],
            "aliases": list(dict.fromkeys(str(alias).strip()[:160] for alias in aliases if str(alias).strip())),
            "notes": str(notes_value or "").strip()[:4000],
            "scope": str(scope_value or "Current book only").strip()[:80],
            "voice_profile": profile_name or None,
        })
        state["characters"] = characters
        state["modified_at"] = self._now()
        save_state(project.folder, state)
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
        return settings_root() / "character_library.json"

    def _character_library_read(self) -> list[dict[str, Any]]:
        path = self._character_library_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        except (OSError, ValueError, TypeError):
            raise ValueError("The saved Character Library file is invalid. Import a valid JSON cast file to restore it.")
        rows = data.get("characters", []) if isinstance(data, dict) else data
        if not isinstance(rows, list): raise ValueError("Character Library data must be a list of characters.")
        return [row for row in rows if isinstance(row, dict) and str(row.get("name") or "").strip()]

    def _character_library_write(self, rows: list[dict[str, Any]]) -> None:
        path = self._character_library_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps({"version": 1, "characters": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _character_library_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        return self._character_library_read()

    def _character_library_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if not name: raise ValueError("Enter a character name before saving it to the Character Library.")
        aliases = payload.get("aliases") or []
        if isinstance(aliases, str): aliases = aliases.split(",")
        if not isinstance(aliases, list): raise ValueError("Character aliases must be a list or comma-separated text.")
        row_id = str(payload.get("id") or "").strip() or uuid.uuid4().hex
        scope = str(payload.get("scope") or "Global character library").strip()[:100]
        item = {"id": row_id, "name": name[:300], "short": str(payload.get("short") or name.split()[0]).strip()[:120],
                "aliases": list(dict.fromkeys(str(x).strip()[:160] for x in aliases if str(x).strip())),
                "voice": str(payload.get("voice") or "Unassigned").strip()[:200], "scope": scope,
                "series": str(payload.get("series") or scope).strip()[:100], "notes": str(payload.get("notes") or "").strip()[:4000],
                "lines": max(0, int(payload.get("lines") or 0)), "chapters": max(0, int(payload.get("chapters") or 0)),
                "confidence": max(0, min(100, int(payload.get("confidence", 100)))), "updated_at": self._now()}
        rows = self._character_library_read()
        old = next((i for i, row in enumerate(rows) if str(row.get("id") or "") == row_id or str(row.get("name") or "").casefold() == name.casefold()), None)
        if old is None: rows.append(item)
        else: rows[old] = item
        self._character_library_write(rows)
        return {"character": item, "count": len(rows), "saved": True}

    def _character_library_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        row_id = str(payload.get("id") or "").strip()
        name = str(payload.get("name") or "").strip().casefold()
        rows = self._character_library_read()
        kept = [row for row in rows if not ((row_id and str(row.get("id") or "") == row_id) or (name and str(row.get("name") or "").casefold() == name))]
        if len(kept) == len(rows): raise ValueError("The selected character is no longer in the Character Library.")
        self._character_library_write(kept)
        return {"deleted": len(rows)-len(kept), "count": len(kept)}

    def _character_library_import(self, payload: dict[str, Any]) -> dict[str, Any]:
        incoming = payload.get("characters")
        if isinstance(incoming, dict): incoming = incoming.get("characters")
        if not isinstance(incoming, list) or not incoming: raise ValueError("Choose a JSON file containing a non-empty character list.")
        rows = self._character_library_read()
        by_name = {str(row.get("name") or "").casefold(): i for i, row in enumerate(rows)}
        imported = 0
        for candidate in incoming:
            if not isinstance(candidate, dict) or not str(candidate.get("name") or "").strip(): continue
            item = dict(candidate); item["name"] = str(item["name"]).strip(); item["id"] = str(item.get("id") or uuid.uuid4().hex)
            aliases = item.get("aliases") or []; item["aliases"] = aliases if isinstance(aliases, list) else str(aliases).split(",")
            key = item["name"].casefold()
            if key in by_name: rows[by_name[key]] = {**rows[by_name[key]], **item}
            else: by_name[key] = len(rows); rows.append(item)
            imported += 1
        if not imported: raise ValueError("The selected JSON file contained no valid named characters.")
        self._character_library_write(rows)
        return {"imported": imported, "count": len(rows), "merged_by_name": True}
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
            if output.suffix.lower() not in {".m4b", ".m4a", ".mp3"}:
                raise ValueError("Output must end in .m4b, .m4a, or .mp3.")
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
            if key == "preview_seconds" and int(value) not in {10, 20, 30, 45, 60}:
                raise ValueError("Preview duration must be 10, 20, 30, 45, or 60 seconds.")
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
        return self._settings_get({})

    def _models_install(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Install selected Qwen Voice Studio models as a durable background job."""
        selection_map = {
            "customvoice": "CustomVoice",
            "voicedesign": "VoiceDesign",
            "voiceclone": "Voice Clone",
            "all": "Full Qwen Voice Studio",
        }
        requested = str(payload.get("selection") or "customvoice").strip().lower()
        selection = selection_map.get(requested)
        if selection is None:
            raise ValueError("Choose CustomVoice, VoiceDesign, Voice Clone, or all Qwen capabilities.")

        job_id = self._new_job(
            "model-install", "Install " + selection,
            "Install Qwen3-TTS runtime and selected local voice model(s)",
        )
        self._job_update(
            job_id, state="running", started_at=self._now(), progress=1,
            stage="Preparing installation",
            message="Installing local Qwen3-TTS components. This may take a while.",
        )

        def report_progress(detail: str) -> None:
            detail = str(detail)
            match = re.search(r"(?<!\d)(\d{1,3})%", detail)
            changes: dict[str, Any] = {"state": "running", "stage": detail, "message": detail}
            if match:
                changes["progress"] = min(98, max(1, int(match.group(1))))
            self._job_update(job_id, **changes)

        def install() -> None:
            try:
                from app.tts.qwen_character_runtime import (
                    install_runtime, install_model,
                    best_custom_kind, best_clone_kind, best_voice_design_kind,
                )
                report_progress("Installing isolated Qwen3-TTS runtime…")
                install_runtime(report_progress)
                choices = {
                    "CustomVoice": [best_custom_kind()],
                    "VoiceDesign": [best_voice_design_kind(), best_clone_kind()],
                    "Voice Clone": [best_clone_kind()],
                }
                if selection == "Full Qwen Voice Studio":
                    targets = []
                    for kind in (best_custom_kind(), best_voice_design_kind(), best_clone_kind()):
                        if kind not in targets:
                            targets.append(kind)
                else:
                    targets = choices[selection]
                for kind in targets:
                    report_progress(f"Preparing Qwen3-TTS {selection} model: {kind}…")
                    install_model(kind, report_progress)
                self._job_update(
                    job_id, state="completed", progress=100,
                    stage="Installation complete",
                    message="Qwen Voice Studio installation completed.",
                    result={"selection": selection, "models": targets},
                    error=None, recoverable=False,
                )
            except Exception as exc:
                log.exception("Premium V2 Qwen model installation failed")
                self._job_update(
                    job_id, state="failed", stage="Installation failed",
                    message="Qwen Voice Studio installation failed.",
                    error={"code": "model_install_failed", "message": str(exc)},
                    recoverable=True,
                )

        threading.Thread(
            target=install, daemon=True, name="RyuPremiumModelInstall"
        ).start()
        return {"job_id": job_id, "selection": selection, "state": "running"}

    def _models_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        from app.tts.model_registry import BUILTIN_CATALOG, installed_models
        installed = {m.model_id for m in installed_models()}
        return [{"model_id": m.model_id, "name": m.display_name, "provider": m.provider,
                 "voice_cloning": m.voice_cloning, "multilingual": m.multilingual,
                 "installed": m.model_id in installed, "preferred_backends": list(m.preferred_backends),
                 "notes": m.notes} for m in BUILTIN_CATALOG]

    def _models_verify(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Verify installed Qwen model files from disk without downloading or loading ML runtimes."""
        from app.tts.qwen_character_runtime import MODEL_IDS, MODEL_DIRS, model_installed

        requested = str(payload.get("model_id") or "").strip().lower()
        aliases = {
            "customvoice": ("custom-0.6b", "custom-1.7b"),
            "custom-voice": ("custom-0.6b", "custom-1.7b"),
            "voicedesign": ("design-1.7b", "base-0.6b", "base-1.7b"),
            "voice-design": ("design-1.7b", "base-0.6b", "base-1.7b"),
            "voiceclone": ("base-0.6b", "base-1.7b"),
            "voice-clone": ("base-0.6b", "base-1.7b"),
        }
        if requested in aliases:
            kinds = aliases[requested]
        elif requested in MODEL_IDS:
            kinds = (requested,)
        else:
            raise ValueError("Choose a supported Qwen model ID or CustomVoice, VoiceDesign, or Voice Clone.")

        models = [{
            "model_id": kind,
            "name": MODEL_IDS[kind],
            "path": str(MODEL_DIRS[kind]),
            "installed": bool(model_installed(kind)),
        } for kind in kinds]
        if requested in {"customvoice", "custom-voice"}:
            ready = any(item["installed"] for item in models)
        elif requested in {"voicedesign", "voice-design"}:
            ready = models[0]["installed"] and any(item["installed"] for item in models[1:])
        elif requested in {"voiceclone", "voice-clone"}:
            ready = any(item["installed"] for item in models)
        else:
            ready = models[0]["installed"]
        return {
            "model_id": requested,
            "available": ready,
            "models": models,
            "detail": ("Required model files are present." if ready else
                       "One or more required model files are missing or incomplete. Use the supported Models installer, then verify again."),
        }

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

    def _settings_get(self, _payload: dict[str, Any]) -> dict[str, Any]:
        self.settings.sync()
        return {
            "theme": self.settings.value("ui/theme", "dark"),
            "effects": self.settings.value("ui/effects", "high"),
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
        adapter_path = frontend_path().with_name("premium_v2_backend_adapter.js")
        if adapter_path.is_file():
            try:
                script += "\n" + adapter_path.read_text(encoding="utf-8")
            except OSError:
                log.exception("Could not load Premium V2 backend adapter from %s", adapter_path)
        else:
            log.error("Premium V2 backend adapter is missing: %s", adapter_path)
        self.web.page().runJavaScript(script)