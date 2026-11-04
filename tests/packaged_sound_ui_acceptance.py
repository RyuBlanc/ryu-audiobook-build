        json.dumps(full_generation_chapters, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (full_generation_project_folder / "state.json").write_text(json.dumps({
        "status": "new",
        "author": f"Stage 5.3 Author {token}",
        "publisher": f"Stage 5.3 Press {token}",
        "series": f"Stage 5.3 Series {token}",
        "series_volume": "1",
        "language": "en-US",
        "year": "2026",
        "genre": "Acceptance",
        "cover_path": str(generation_cover.resolve()),
        "voice_profile": narrator_profile_name,
        "narrator": narrator_profile_name,
        "narrator_profile_source": "project_override",
        "backend": "automatic",
        "audio_bitrate": 128,
        "output_path": str(full_generation_output_path.resolve()),
        "background_audio_mode": "off",
        "background_audio_enabled": False,
        "background_audio_path": "",
        "background_audio_preferred_path": "",
        "chapter_bgm_strategy": "same",
        "chapter_bgm_overrides": {},
        "sound_cues": {"opening": None, "chapter": None, "closing": None},
        "characters": [],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_generation_project(folder: Path, title: str, output: Path, chapter_id: str, chapter_text: str) -> None:
        folder.mkdir(parents=True, exist_ok=False)
        cover = folder / "assets" / "cover.png"
        write_png_fixture(cover)
        # The generated job-control fixtures must represent real imported
        # projects. Production readiness correctly blocks source-less projects;
        # provide a deterministic local text source instead of bypassing the gate.
        source_path = folder / "source.txt"
        source_path.write_text(chapter_text, encoding="utf-8")
        (folder / "project.json").write_text(json.dumps({
            "title": title, "source_file": str(source_path.resolve()),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "chapters.json").write_text(json.dumps([{
            "number": 1,
            "title": "Long Stage 5.4 Job-Control Chapter",
            "chapter_id": chapter_id,
            "text": chapter_text,
            "dialogue_assignments": [],
            "review_status": "complete",
            "skip_for_generation": False,
        }], ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "state.json").write_text(json.dumps({
            "status": "new",
            "author": f"Stage 5.4 Author {token}",
            "publisher": f"Stage 5.4 Press {token}",
            "series": f"Stage 5.4 Series {token}",
            "series_volume": "1",
            "language": "en-US",
            "year": "2026",
            "genre": "Acceptance",
            "cover_path": str(cover.resolve()),
            "voice_profile": narrator_profile_name,
            "narrator": narrator_profile_name,
            "narrator_profile_source": "project_override",
            "backend": "automatic",
            "audio_bitrate": 128,
            "output_path": str(output.resolve()),
            "background_audio_mode": "off",
            "background_audio_enabled": False,
            "background_audio_path": "",
            "background_audio_preferred_path": "",
            "chapter_bgm_strategy": "same",
            "chapter_bgm_overrides": {},
            "sound_cues": {"opening": None, "chapter": None, "closing": None},
            "characters": [],
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    long_job_sentence = (
        "This Stage 5.4 installed-app acceptance sentence forces real chunked narration. "
        "The saved narrator must synthesize audio, persist a checkpoint, and keep the job cancellable. "
    )
    long_job_text = long_job_sentence * 16
    control_project_folder = app_root / "Library" / f"Stage 5.4 Job Controls {token}"
    control_output_path = temp_root / "stage5.4-job-control-retry.m4b"
    create_generation_project(
        control_project_folder,
        f"Stage 5.4 Job Controls {token}",
        control_output_path,
        f"stage54-{token}-control-chapter",
        long_job_text,
    )
    recovery_project_folder = app_root / "Library" / f"Stage 5.4 Restart Recovery {token}"
    recovery_output_path = temp_root / "stage5.4-restart-recovery.m4b"
    create_generation_project(
        recovery_project_folder,
        f"Stage 5.4 Restart Recovery {token}",
        recovery_output_path,