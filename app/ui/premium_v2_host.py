from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import shutil
import sys
import threading
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
from app.documents.parser import SUPPORTED_EXTENSIONS, clean_text, extract_text
from app.chapters.detector import detect_chapters
from app.chapters.characters import analyze_book
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
        self._jobs_lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._generators: dict[str, GenerationManager] = {}
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
                "chapter.clean": self._chapter_clean,
                "chapter.add": self._chapter_add,
                "chapter.delete": self._chapter_delete,
                "chapter.reorder": self._chapter_reorder,
                "project.rename": self._project_rename,
                "import.choose_file": self._import_choose_file,
                "import.start": self._import_start,
                "voice.list": self._voice_list,
                "voice.select": self._voice_select,
                "voice.preview": self._voice_preview,
                "character.list": self._character_list,
                "character.analyze": self._character_analyze,
                "character.assign": self._character_assign,
                "pronunciation.list": self._pronunciation_list,
                "pronunciation.save": self._pronunciation_save,
                "pronunciation.delete": self._pronunciation_delete,
                "pronunciation.analyze": self._pronunciation_analyze,
                "production.generate_book": self._production_generate_book,
                "production.preview": self._production_preview,
                "job.list": self._job_list,
                "job.pause": self._job_pause,
                "job.resume": self._job_resume,
                "job.cancel": self._job_cancel,
                "job.clear_completed": self._job_clear_completed,
                "history.list": self._history_list,
                "player.get_active": self._player_get_active,
                "settings.get": self._settings_get,
                "settings.save": self._settings_save,
                "models.list": self._models_list,
                "performance.info": self._performance_info,
                "diagnostics.check": self._diagnostics_check,
                "system.open_output": self._system_open_output,
                "sound.catalog": self._sound_catalog,
                "sound.import": self._sound_import,
                "sound.assign": self._sound_assign,
                "sound.save_manifest": self._sound_save_manifest,
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
            "chapter.clean": True,
            "chapter.add": True,
            "chapter.delete": True,
            "chapter.reorder": True,
            "project.rename": True,
            "import.choose_file": True,
            "import.start": True,
            "voice.list": True,
            "voice.select": True,
            "voice.preview": True,
            "character.list": True,
            "character.analyze": True,
            "character.assign": True,
            "pronunciation.list": True,
            "pronunciation.save": True,
            "pronunciation.delete": True,
            "pronunciation.analyze": True,
            "production.generate_book": True,
            "production.preview": True,
            "job.list": True,
            "job.pause": True,
            "job.resume": True,
            "job.cancel": True,
            "job.clear_completed": True,
            "history.list": True,
            "player.get_active": True,
            "settings.get": True,
            "settings.save": True,
            "models.list": True,
            "performance.info": False,
            "diagnostics.check": True,
            "system.open_output": True,
            "sound.catalog": True,
            "sound.import": True,
            "sound.assign": True,
            "sound.save_manifest": True,
            "reason": "Local import, chapter editing, saved voice selection and preview, character analysis, pronunciation rules, audiobook generation, background jobs, history, playback metadata, and settings are connected. Live hardware telemetry and model installation are not connected yet.",
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
        return {"title": selected.title, "folder": str(selected.folder),
                "chapter_count": len(selected.chapters)}

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
        return {"title": selected.title, "folder": str(selected.folder),
                "chapter_count": len(selected.chapters)}

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
                 "dialogue_assignments": c.dialogue_assignments}
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
        project_state = load_state(project.folder)
        project_state["modified_at"] = self._now()
        save_state(project.folder, project_state)
        return {"number": chapter.number, "title": chapter.title,
                "word_count": len((chapter.text or "").split()),
                "character_count": len(chapter.text or ""),
                "empty": not bool((chapter.text or "").strip()), "saved": True}

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
            if row.get("state") in {"completed", "failed", "cancelled"}:
                row["completed_at"] = row.get("completed_at") or row["updated_at"]
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
        job_id = self._new_job("import", "Import " + title, "Extract text and detect chapters")
        self._job_update(job_id, state="running", started_at=self._now(), stage="Reading source file", progress=5)
        threading.Thread(target=self._import_worker, args=(job_id, path, title), daemon=True).start()
        return {"job_id": job_id, "state": "running", "file_path": str(path)}

    def _import_worker(self, job_id: str, path: Path, title: str) -> None:
        try:
            self._job_update(job_id, stage="Extracting text", progress=20, message="Extracting readable text and metadata")
            book = extract_text(path)
            text = str(book.text or "")
            if not text.strip():
                raise ValueError("No readable text was extracted. A scanned PDF may need OCR.")
            self._job_update(job_id, stage="Detecting chapters", progress=50, message="Detecting chapter boundaries")
            chapters = detect_chapters(text)
            if not chapters:
                raise ValueError("The document contains no readable chapter text.")
            project = create_project(title, path, chapters)
            self.settings.setValue("project/active_folder", str(project.folder.resolve()))
            self.settings.sync()
            state = load_state(project.folder)
            state.update({"status": "imported", "source_path": str(project.source_path or path),
                          "source_title": book.title, "word_count": sum(len((c.text or "").split()) for c in chapters),
                          "imported_at": self._now(), "modified_at": self._now()})
            save_state(project.folder, state)
            self._job_update(job_id, state="completed", stage="Import complete", progress=100,
                             message="Book imported and saved locally", project_title=project.title,
                             project_folder=str(project.folder.resolve()), result={
                                 "title": project.title, "folder": str(project.folder.resolve()),
                                 "chapter_count": len(chapters), "word_count": state["word_count"],
                                 "preview_text": "\n\n".join(c.text for c in chapters[:2])[:4000],
                                 "warnings": [],
                             })
        except Exception as exc:
            log.exception("Premium V2 import failed")
            self._job_update(job_id, state="failed", stage="Import failed", progress=0, message=str(exc),
                             error={"code": "import_failed", "message": str(exc)}, recoverable=True)

    def _chapter_clean(self, payload: dict[str, Any]) -> dict[str, Any]:
        text_value = payload.get("text")
        if not isinstance(text_value, str):
            raise ValueError("Select chapter text before cleaning.")
        cleaned = clean_text(text_value)
        return {"text": cleaned, "changed": cleaned != text_value}

    def _chapter_add(self, payload: dict[str, Any]) -> dict[str, Any]:
        from app.chapters.detector import Chapter
        project = self._active_project()
        title = str(payload.get("title") or "").strip() or f"Chapter {len(project.chapters) + 1}"
        text_value = str(payload.get("text") or "")
        project.chapters.append(Chapter(len(project.chapters) + 1, title[:500], text_value))
        project.save()
        return {"number": project.chapters[-1].number, "title": project.chapters[-1].title}

    def _chapter_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        number = int(payload.get("number") or 0)
        index = next((i for i, c in enumerate(project.chapters) if c.number == number), None)
        if index is None:
            raise ValueError("Select an existing chapter to delete.")
        del project.chapters[index]
        for i, chapter in enumerate(project.chapters, 1):
            chapter.number = i
        project.save()
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
        return {"chapter_count": len(project.chapters), "moved_to": destination}

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
        if seconds not in {10, 30, 60}:
            raise ValueError("Preview duration must be 10, 30, or 60 seconds.")
        job_id = self._new_job("voice-preview", "Preview · " + profile.name,
                               f"Generate up to {seconds} seconds using the selected provider", project)
        self._job_update(job_id, state="running", started_at=self._now(), stage="Preparing preview", progress=2)
        threading.Thread(target=self._preview_worker, args=(job_id, profile, text_value, seconds, state),
                         daemon=True, name="RyuPremiumPreview").start()
        return {"job_id": job_id, "state": "running", "duration_seconds": seconds, "profile_name": profile.name}

    def _preview_worker(self, job_id: str, profile, text_value: str, seconds: int, state: dict[str, Any]) -> None:
        try:
            provider, voice = provider_from_profile(profile)
            folder = app_root() / "Previews"
            folder.mkdir(parents=True, exist_ok=True)
            output = folder / f"preview_{job_id}.wav"
            def progress(stage: str, current: int, total: int) -> None:
                self._job_update(job_id, stage=str(stage), progress=min(95, max(2, 5 + int(90 * current / max(1, total)))))
            result = build_voice_preview(
                text_value, provider, voice, output,
                pronunciation_dictionary=list(state.get("pronunciation_dictionary") or []),
                narration_speed=float(state.get("narration_speed") or 0.90),
                pacing_profile=str(state.get("pacing_profile") or "natural"),
                max_chars=max(1400, seconds * 240), progress_callback=progress,
                target_seconds=seconds,
            )
            duration = None
            try:
                with wave.open(str(result.output_path), "rb") as wav:
                    duration = round(wav.getnframes() / max(1, wav.getframerate()), 2)
            except (wave.Error, OSError):
                pass
            self._job_update(job_id, state="completed", stage="Preview ready", progress=100,
                             message="Audio preview was generated by the selected voice provider",
                             output_path=str(result.output_path), result={
                                 "output_path": str(result.output_path), "file_url": result.output_path.resolve().as_uri(),
                                 "requested_duration_seconds": seconds, "actual_duration_seconds": duration,
                                 "voices_used": list(result.voices_used), "segments": result.segments,
                             })
        except Exception as exc:
            log.exception("Premium V2 voice preview failed")
            self._job_update(job_id, state="failed", stage="Preview failed", progress=0, message=str(exc),
                             error={"code": "preview_failed", "message": str(exc)}, recoverable=True)

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
                items.append({"name": c.name, "role": c.role, "dialogue_count": c.dialogue_count,
                              "examples": list(c.examples or []), "confidence": float(c.confidence),
                              "aliases": list(c.aliases or []), "voice_profile": prior.get("voice_profile"),
                              "chapter_appearances": list(prior.get("chapter_appearances") or [])})
            state["characters"] = items
            state["character_analysis"] = {"dialogue_total": analysis.dialogue_total,
                                           "unassigned_dialogue": analysis.unassigned_dialogue,
                                           "updated_at": self._now()}
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
        save_state(project.folder, state)
        return {"name": name, "voice_profile": item["voice_profile"], "saved": True}

    def _pronunciation_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        entries = load_state(self._active_project().folder).get("pronunciation_dictionary") or []
        return entries if isinstance(entries, list) else []

    def _pronunciation_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        word = str(payload.get("written_form") or payload.get("word") or "").strip()
        spoken = str(payload.get("spoken_form") or payload.get("pronunciation") or "").strip()
        if not word or not spoken:
            raise ValueError("Enter a written term and its intended pronunciation.")
        if len(word) > 500 or len(spoken) > 1000:
            raise ValueError("The term or pronunciation is too long.")
        state = load_state(project.folder)
        entries = list(state.get("pronunciation_dictionary") or [])
        item = next((e for e in entries if str(e.get("written_form") or e.get("word") or "").casefold() == word.casefold()), None)
        value = {"written_form": word, "spoken_form": spoken,
                 "language": str(payload.get("language") or "Auto"),
                 "handling_mode": str(payload.get("handling_mode") or payload.get("mode") or "automatic"),
                 "scope": str(payload.get("scope") or "current_book"), "enabled": bool(payload.get("enabled", True)),
                 "updated_at": self._now()}
        if item is None:
            entries.append(value)
        else:
            item.update(value)
        state["pronunciation_dictionary"] = entries
        save_state(project.folder, state)
        return {"entry": value, "count": len(entries), "saved": True}

    def _pronunciation_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        word = str(payload.get("written_form") or payload.get("word") or "").casefold()
        state = load_state(project.folder)
        entries = list(state.get("pronunciation_dictionary") or [])
        state["pronunciation_dictionary"] = [e for e in entries if str(e.get("written_form") or e.get("word") or "").casefold() != word]
        save_state(project.folder, state)
        return {"count": len(state["pronunciation_dictionary"]), "deleted": len(entries) - len(state["pronunciation_dictionary"])}

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
        chapters = [c for c in project.chapters if (c.text or "").strip()]
        skipped = len(project.chapters) - len(chapters)
        if not chapters:
            raise ValueError("No chapters contain narration text. Restore chapter text before generating.")
        state = load_state(project.folder)
        profile_name = str(payload.get("profile_name") or state.get("voice_profile") or "").strip()
        profile = self._find_profile(profile_name)
        if profile is None:
            raise ValueError("No narrator is saved. Open Voice Studio, select an installed voice, and save it as narrator.")
        provider, voice = provider_from_profile(profile)
        output_text = str(payload.get("output_path") or state.get("output_path") or "").strip()
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
                               f"Render {len(chapters)} non-empty chapter(s)", project)
        state.update({"voice_profile": profile.name, "voice_id": profile.voice_id, "output_path": str(output),
                      "status": "generating", "audio_bitrate": bitrate, "generation_job_id": job_id,
                      "generation_started_at": self._now(), "empty_chapters_skipped": skipped})
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
            pronunciation_dictionary=list(state.get("pronunciation_dictionary") or []),
            narration_speed=float(state.get("narration_speed") or 0.90),
            pacing_profile=str(state.get("pacing_profile") or "natural"),
            metadata=metadata, bitrate=bitrate,
            background_audio_path=Path(state["background_audio_path"]) if state.get("background_audio_path") and Path(state["background_audio_path"]).is_file() else None,
            background_audio_volume=float(state.get("background_audio_volume") or 0.18),
            ambience_audio_path=Path(state["ambience_audio_path"]) if state.get("ambience_audio_path") and Path(state["ambience_audio_path"]).is_file() else None,
            ambience_audio_volume=float(state.get("ambience_audio_volume") or 0.10),
            background_audio_mode=str(state.get("background_audio_mode") or "off"),
            auto_music_style=str(state.get("auto_music_style") or "auto"),
            auto_music_variation=state.get("auto_music_track_path") or None,
            chapter_transition_sound=bool(state.get("chapter_transition_sound", False)),
            story_effects_enabled=bool(state.get("story_effects_enabled", False)),
            story_effect_volume=float(state.get("story_effect_volume") or 0.22),
            sound_cue_style=str(state.get("sound_cue_style") or "classic-book"),
            opening_cue_path=Path(state["opening_cue_path"]) if state.get("opening_cue_path") and Path(state["opening_cue_path"]).is_file() else None,
            page_turn_cue_path=Path(state["page_turn_cue_path"]) if state.get("page_turn_cue_path") and Path(state["page_turn_cue_path"]).is_file() else None,
            ending_cue_path=Path(state["ending_cue_path"]) if state.get("ending_cue_path") and Path(state["ending_cue_path"]).is_file() else None,
        )
        with self._jobs_lock:
            self._generators[job_id] = manager
        self._job_update(job_id, state="running", started_at=self._now(), stage="Preparing generation",
                         progress=1, message=f"Starting with {skipped} empty chapter(s) skipped",
                         result={"output_path": str(output), "chapter_count": len(chapters),
                                 "empty_chapters_skipped": skipped, "voice_profile": profile.name})
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
                "chapter_count": len(chapters), "empty_chapters_skipped": skipped, "voice_profile": profile.name}

    def _generation_progress(self, job_id: str, chapter: int, total: int, done: int, message: str) -> None:
        msg = str(message or "")
        state, stage, progress = "running", "Generating narration", None
        if msg.startswith("paused:"):
            state, stage, msg = "paused", "Paused at chapter checkpoint", msg.split(":", 1)[1]
        elif msg.startswith("plan:"):
            stage, progress = "Preparing generation plan", 2
        elif msg.startswith("provider:"):
            stage, msg = "Voice provider", msg.partition(":")[2]
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
                             output_path=str(actual) if valid else None,
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

    def _player_get_active(self, _payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        state = load_state(project.folder)
        output = Path(str(state.get("output_path") or "")).expanduser()
        if not output.is_file() or output.stat().st_size <= 0:
            raise FileNotFoundError("This project does not have a validated generated audiobook yet.")
        return {"title": project.title, "author": str(state.get("author") or ""),
                "narrator": str(state.get("voice_profile") or ""), "output_path": str(output.resolve()),
                "file_url": output.resolve().as_uri(),
                "chapters": [{"number": c.number, "title": c.title} for c in project.chapters],
                "format": output.suffix.lower(), "file_size": output.stat().st_size}

    def _settings_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {"theme": "ui/theme", "accent": "ui/accent", "interface_scale": "ui/interface_scale",
                   "effects": "ui/effects", "reduce_motion": "ui/reduce_motion",
                   "preview_seconds": "audio/preview_seconds", "bitrate": "production/bitrate",
                   "concurrency": "production/concurrency", "local_first": "privacy/local_first",
                   "output_folder": "paths/output_folder"}
        for key, setting in allowed.items():
            if key not in payload:
                continue
            value = payload[key]
            if key == "theme" and value not in {"dark", "light"}:
                raise ValueError("Theme must be dark or light.")
            if key == "preview_seconds" and int(value) not in {10, 30, 60}:
                raise ValueError("Preview duration must be 10, 30, or 60 seconds.")
            if key == "bitrate" and not 128 <= int(value) <= 320:
                raise ValueError("Bitrate must be from 128 to 320 kbps.")
            if key == "output_folder":
                folder = Path(str(value)).expanduser().resolve()
                folder.mkdir(parents=True, exist_ok=True)
                value = str(folder)
            self.settings.setValue(setting, value)
        self.settings.sync()
        return self._settings_get({})

    def _models_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        from app.tts.model_registry import BUILTIN_CATALOG, installed_models
        installed = {m.model_id for m in installed_models()}
        return [{"model_id": m.model_id, "name": m.display_name, "provider": m.provider,
                 "voice_cloning": m.voice_cloning, "multilingual": m.multilingual,
                 "installed": m.model_id in installed, "preferred_backends": list(m.preferred_backends),
                 "notes": m.notes} for m in BUILTIN_CATALOG]

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
        extensions = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".aiff", ".opus"}
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
                    found[key] = {"id": key, "title": path.stem, "path": key,
                                  "source": source, "format": path.suffix.lower(),
                                  "size_bytes": size, "duration_seconds": None,
                                  "licensing": "Unknown; verify rights before publishing"}
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
        extensions = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".aiff", ".opus"}
        target_root = app_root() / "Audio Library"
        target_root.mkdir(parents=True, exist_ok=True)
        imported = []
        for raw in paths:
            source = Path(str(raw)).expanduser().resolve()
            if not source.is_file() or source.suffix.lower() not in extensions:
                raise ValueError(f"Unsupported or missing audio asset: {source.name}")
            destination = target_root / source.name
            if destination.exists() and destination.resolve() != source:
                destination = target_root / f"{source.stem}-{uuid.uuid4().hex[:8]}{source.suffix.lower()}"
            if source != destination.resolve():
                shutil.copy2(source, destination)
            imported.append({"title": destination.stem, "path": str(destination.resolve()),
                             "source": "Imported locally", "format": destination.suffix.lower(),
                             "size_bytes": destination.stat().st_size})
        return {"cancelled": False, "imported": imported, "catalog": self._sound_catalog({})}

    def _sound_assign(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        raw = str(payload.get("path") or "").strip()
        state = load_state(project.folder)
        if not raw:
            state.update({"background_audio_path": "", "background_audio_mode": "off"})
            save_state(project.folder, state)
            return {"saved": True, "path": None, "mode": "off"}
        selected = Path(raw).expanduser().resolve()
        valid = any(str(row["path"]) == str(selected) for row in self._sound_catalog({}))
        if not selected.is_file() or not valid:
            raise ValueError("Choose an audio file from the local Sound Design catalogue.")
        volume = max(0.0, min(1.0, float(payload.get("volume", 0.18))))
        state.update({"background_audio_path": str(selected), "background_audio_volume": volume,
                      "background_audio_mode": "manual", "modified_at": self._now()})
        save_state(project.folder, state)
        return {"saved": True, "path": str(selected), "title": selected.stem, "volume": volume, "mode": "manual"}

    def _sound_save_manifest(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._active_project()
        state = load_state(project.folder)
        path = str(payload.get("path") or state.get("background_audio_path") or "").strip()
        enabled = bool(payload.get("enabled", bool(path)))
        volume = max(0.0, min(1.0, float(payload.get("volume", state.get("background_audio_volume") or 0.18))))
        if enabled and path:
            selected = Path(path).expanduser().resolve()
            if not selected.is_file() or not any(row["path"] == str(selected) for row in self._sound_catalog({})):
                raise ValueError("Selected BGM is missing from the local sound library.")
            state.update({"background_audio_path": str(selected), "background_audio_mode": "manual",
                          "background_audio_enabled": True, "background_audio_volume": volume})
        else:
            state.update({"background_audio_path": "", "background_audio_mode": "off", "background_audio_enabled": False})
        state["sound_manifest"] = {"bgm_path": state.get("background_audio_path") or None,
                                   "bgm_volume": volume, "enabled": bool(enabled and path),
                                   "updated_at": self._now()}
        save_state(project.folder, state)
        return dict(state["sound_manifest"])

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
