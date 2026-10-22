"""Full-book Sound Design preview worker built from existing chapter narration."""
from __future__ import annotations

import re
import threading
import uuid
from pathlib import Path
from typing import Any


def start_full_book_preview(host) -> dict[str, Any]:
    project = host._active_project()
    from app.core.state import load_state
    state = load_state(project.folder)
    from app.audio.library import validate_saved_audio_paths
    validate_saved_audio_paths(state)
    chapters = sorted(project.chapters, key=lambda chapter: chapter.number)
    if not chapters:
        raise ValueError("Add chapters to this book before previewing its mix.")

    audio_root = project.folder / "working_audio"
    chapter_dirs: list[Path] = []
    missing: list[str] = []
    for chapter in chapters:
        prefix = f"{int(chapter.number):03d}_"
        candidates = sorted(
            path for path in audio_root.glob(prefix + "*")
            if path.is_dir() and (path / "chunks").is_dir()
            and any((path / "chunks").glob("*.wav"))
        ) if audio_root.is_dir() else []
        if not candidates:
            missing.append(str(chapter.title or f"Chapter {chapter.number}"))
        else:
            chapter_dirs.append(candidates[0])
    if missing:
        detail = ", ".join(missing[:4])
        if len(missing) > 4:
            detail += f", and {len(missing) - 4} more"
        raise ValueError(
            "A full-book mix preview needs saved narration audio for every chapter. "
            f"Generate or recover these chapters first: {detail}."
        )

    safe_title = re.sub(r'[<>:"/\\|?*]+', "_", project.title).strip() or "Audiobook"
    from app.core.paths import app_root
    preview_root = app_root() / "Previews"
    preview_root.mkdir(parents=True, exist_ok=True)
    output = preview_root / f"{safe_title}-mix-preview-{uuid.uuid4().hex[:10]}.m4b"
    title = str(state.get("title") or project.title)
    author = str(state.get("author") or "")
    metadata = {
        "title": title, "author": author,
        "narrator": str(state.get("narrator") or state.get("voice_profile") or ""),
        "publisher": str(state.get("publisher") or ""), "series": str(state.get("series") or ""),
        "language": str(state.get("language") or ""), "year": str(state.get("year") or ""),
        "genre": str(state.get("genre") or "Audiobook"),
        "description": str(state.get("description") or ""),
    }
    bitrate = int(state.get("audio_bitrate") or 256)
    if not 128 <= bitrate <= 320:
        raise ValueError("Saved audio quality must be between 128 and 320 kbps.")

    job_id = host._new_job(
        "sound-design-book-preview", "Preview full-book sound design",
        f"Mix {len(chapters)} saved chapter(s) without re-synthesizing narration", project,
    )
    host._job_update(job_id, state="running", started_at=host._now(),
                     stage="Preparing full-book mix", progress=2,
                     message="Using saved chapter narration; no voice synthesis is required.")
    thread = threading.Thread(
        target=_render_full_book_preview,
        args=(host, job_id, project, chapter_dirs, [c.title for c in chapters],
              output, title, author, metadata, bitrate, state),
        daemon=True, name="RyuFullBookSoundPreview",
    )
    thread.start()
    return {"job_id": job_id, "state": "running", "output_path": str(output),
            "chapter_count": len(chapters), "reuses_saved_narration": True}


def _render_full_book_preview(host, job_id, project, chapter_dirs, chapter_titles,
                              output, title, author, metadata, bitrate, state) -> None:
    try:
        from app.audio.assembler import assemble_m4b, _duration_ms

        def report(done: int, total: int, stage: str) -> None:
            progress = min(96, max(4, int((done / max(1, total)) * 90) + 4))
            host._job_update(job_id, state="running", stage=str(stage), progress=progress,
                             message="Rendering full-book sound design preview.")

        cover_value = state.get("cover_path")
        cover = Path(str(cover_value)).expanduser() if cover_value else None
        if cover is not None and not cover.is_file():
            cover = None
        output_path = assemble_m4b(
            chapter_dirs, output, title, author, cover, chapter_titles,
            metadata=metadata, progress=report, bitrate=bitrate,
            narration_speed=float(state.get("narration_speed") or 1.0),
            background_audio_path=Path(str(state["background_audio_path"]))
                if state.get("background_audio_path") and Path(str(state["background_audio_path"])).is_file() else None,
            background_audio_volume=float(state.get("background_audio_volume") if state.get("background_audio_volume") is not None else 0.18),
            ambience_audio_path=Path(str(state["ambience_audio_path"]))
                if state.get("ambience_audio_path") and Path(str(state["ambience_audio_path"])).is_file() else None,
            ambience_audio_volume=float(state.get("ambience_audio_volume") if state.get("ambience_audio_volume") is not None else 0.10),
            background_audio_mode=str(state.get("background_audio_mode") or "off"),
            auto_music_style=str(state.get("auto_music_style") or "auto"),
            auto_music_variation=state.get("auto_music_track_path") or None,
            chapter_transition_sound=bool(state.get("chapter_transition_sound", False)),
            story_effects_enabled=bool(state.get("story_effects_enabled", False)),
            story_effect_volume=float(state.get("story_effect_volume") if state.get("story_effect_volume") is not None else 0.22),
            sound_cue_style=str(state.get("sound_cue_style") or "classic-book"),
            opening_cue_path=Path(str(state["opening_cue_path"]))
                if state.get("opening_cue_path") and Path(str(state["opening_cue_path"])).is_file() else None,
            page_turn_cue_path=Path(str(state["page_turn_cue_path"]))
                if state.get("page_turn_cue_path") and Path(str(state["page_turn_cue_path"])).is_file() else None,
            ending_cue_path=Path(str(state["ending_cue_path"]))
                if state.get("ending_cue_path") and Path(str(state["ending_cue_path"])).is_file() else None,
            scene_transition_cue_path=Path(str(state["scene_transition_cue_path"]))
                if state.get("scene_transition_cue_path") and Path(str(state["scene_transition_cue_path"])).is_file() else None,
            chapter_bgm_overrides=state.get("chapter_bgm_overrides")
                if isinstance(state.get("chapter_bgm_overrides"), dict) else {},
        )
        duration_ms = _duration_ms(output_path)
        if duration_ms <= 0:
            raise RuntimeError("Sound-design preview was rendered but has no measurable audio duration.")
        host._job_update(
            job_id, state="completed", stage="Full-book mix preview ready", progress=100,
            message="Full-book mix preview rendered from saved narration.",
            output_path=str(output_path),
            result={"output_path": str(output_path), "file_url": output_path.resolve().as_uri(),
                    "duration_seconds": round(duration_ms / 1000.0, 3),
                    "chapter_count": len(chapter_dirs), "reuses_saved_narration": True},
            recoverable=False,
        )
    except Exception as exc:
        # This worker owns a unique preview-only path. Remove partial output on
        # FFmpeg/probe failure so it cannot be mistaken for a usable preview.
        try:
            output.unlink(missing_ok=True)
        except OSError:
            pass
        host._job_update(
            job_id, state="failed", stage="Full-book mix preview failed", progress=0,
            message=str(exc), error={"code": "sound_design_preview_failed", "message": str(exc)},
            recoverable=True,
        )
