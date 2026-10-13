from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile

import imageio_ffmpeg

from app.audio.metadata import sanitize_metadata


# Audiobook output is intentionally kept in a premium, listener-friendly
# range. 64k AAC was previously used here and produced visibly low-bitrate
# M4A/M4B files (and could make cloned-voice output appear even worse after
# packaging).  256k is the default premium setting; callers can request any
# value from 128k through 320k.
MIN_AUDIO_BITRATE_KBPS = 128
DEFAULT_AUDIO_BITRATE_KBPS = 256
MAX_AUDIO_BITRATE_KBPS = 320


def normalize_audio_bitrate(bitrate: int | str | None) -> str:
    """Return a validated AAC bitrate in the supported audiobook range."""
    if bitrate is None:
        kbps = DEFAULT_AUDIO_BITRATE_KBPS
    elif isinstance(bitrate, str):
        value = bitrate.strip().lower().replace("kbps", "").replace("k", "")
        try:
            kbps = int(float(value))
        except ValueError as exc:
            raise ValueError(
                f"Invalid audiobook bitrate '{bitrate}'. Choose 128, 160, 192, 224, 256, 288 or 320 kbps."
            ) from exc
    else:
        kbps = int(bitrate)

    if not MIN_AUDIO_BITRATE_KBPS <= kbps <= MAX_AUDIO_BITRATE_KBPS:
        raise ValueError(
            f"Audiobook bitrate must be between {MIN_AUDIO_BITRATE_KBPS} and "
            f"{MAX_AUDIO_BITRATE_KBPS} kbps; received {kbps} kbps."
        )
    return f"{kbps}k"


def ffmpeg_path() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args: list[str]) -> None:
    result = subprocess.run(
        [ffmpeg_path(), "-y", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        command = " ".join(str(x) for x in args)
        detail = result.stderr[-5000:] or result.stdout[-5000:] or "FFmpeg failed."
        raise RuntimeError(f"FFmpeg packaging command failed.\nCommand: {command}\n{detail}")


def sorted_chunks(chapter_dir: Path) -> list[Path]:
    return sorted((chapter_dir / "chunks").glob("*.wav"))


def _ffconcat_path(path: Path) -> str:
    return path.as_posix().replace("'", "'\\''")


def assemble_chapter(
    chapter_dir: Path,
    bitrate: int | str | None = None,
    narration_speed: float = 1.0,
) -> Path:
    chunks = sorted_chunks(chapter_dir)
    if not chunks:
        raise ValueError(f"No audio chunks found for {chapter_dir.name}")
    output = chapter_dir / "chapter.m4a"
    concat_file = chapter_dir / "concat.txt"
    audio_bitrate = normalize_audio_bitrate(bitrate)

    # Reuse a previously assembled chapter only when its WAV chunks are newer
    # than the M4A. Existing chapters from the old 64k encoder are deliberately
    # not trusted: they are rebuilt so a new premium export cannot silently
    # retain the old low-bitrate audio.
    if output.exists() and output.stat().st_size >= 1024:
        newest_chunk = max((chunk.stat().st_mtime for chunk in chunks), default=0.0)
        settings_stamp = chapter_dir / ".audio-settings"
        stored_settings = ""
        try:
            stored_settings = settings_stamp.read_text(encoding="utf-8").strip()
        except OSError:
            pass
        expected_settings = f"{audio_bitrate}|speed={max(0.5, min(2.0, float(narration_speed))):.3f}"
        if output.stat().st_mtime >= newest_chunk and stored_settings == expected_settings:
            return output

    concat_file.write_text(
        "ffconcat version 1.0\n"
        + "\n".join(f"file '{_ffconcat_path(p)}'" for p in chunks)
        + "\n",
        encoding="utf-8",
    )
    speed = max(0.5, min(2.0, float(narration_speed)))
    args = [
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-vn",
    ]
    if abs(speed - 1.0) > 0.001:
        args += ["-filter:a", f"atempo={speed:.3f}"]
    args += ["-c:a", "aac", "-b:a", audio_bitrate, "-ar", "44100", str(output)]
    _run(args)
    if not output.exists() or output.stat().st_size < 1024:
        raise RuntimeError(f"Chapter audio was not created: {output}")
    try:
        (chapter_dir / ".audio-settings").write_text(
            f"{audio_bitrate}|speed={speed:.3f}",
            encoding="utf-8",
        )
    except OSError:
        pass
    return output


def _metadata_value(value: str | None) -> str:
    if value is None:
        return ""
    return (
        str(value).replace("\\", "\\\\").replace(";", "\\;")
        .replace("#", "\\#").replace("=", "\\=")
        .replace("\n", " ").replace("\r", " ")
    )


def _safe_title(value: str | None) -> str:
    value = str(value or "")
    return re.sub(r'[<>:"/\\|?*]+', "_", value).strip() or "Audiobook"


def _duration_ms(path: Path) -> int:
    probe = subprocess.run([ffmpeg_path(), "-i", str(path)], capture_output=True, text=True)
    probe_output = str(probe.stderr or probe.stdout or "")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", probe_output)
    if not match:
        raise RuntimeError(f"Could not determine duration of {path.name}")
    hours, minutes, seconds = match.groups()
    return int((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)


def _probe_audio_bitrate_kbps(path: Path) -> int:
    """Read the encoded primary audio stream bitrate reported by FFmpeg."""
    probe = subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
    )
    probe_text = str(probe.stderr or probe.stdout or "")
    match = re.search(r"Audio:\s.*?(\d+)\s+kb/s", probe_text, re.IGNORECASE | re.DOTALL)
    if not match:
        raise RuntimeError(f"Could not determine audio bitrate of {path.name}")
    return int(match.group(1))


def assemble_m4b(
    chapter_dirs: list[Path],
    output_path: Path,
    title: str,
    author: str = "",
    cover: Path | None = None,
    chapter_titles: list[str] | None = None,
    metadata: dict[str, str] | None = None,
    progress=None,
    bitrate: int | str | None = None,
    narration_speed: float = 1.0,
    background_audio_path: Path | str | None = None,
    background_audio_volume: float = 0.18,
    ambience_audio_path: Path | str | None = None,
    ambience_audio_volume: float = 0.10,
    background_audio_fade_in: float = 2.0,
    background_audio_fade_out: float = 3.0,
    background_audio_mode: str = "manual",
    auto_music_style: str = "auto",
    chapter_transition_sound: bool = False,
) -> Path:
    """Create one premium M4B containing all chapters and navigation metadata.

    Optional music and ambience tracks are independently gained, looped to
    narration duration, and mixed locally. Both layers are off unless paths
    are supplied.
    """
    if not chapter_dirs:
        raise ValueError("No chapters were supplied.")
    audio_bitrate = normalize_audio_bitrate(bitrate)

    chapters: list[Path] = []
    for index, directory in enumerate(chapter_dirs, start=1):
        chapters.append(
            assemble_chapter(
                directory,
                audio_bitrate,
                narration_speed=narration_speed,
            )
        )
        if progress:
            progress(index, len(chapter_dirs), "chapter-audio")
    names = chapter_titles or [
        directory.name.split("_", 1)[1] if "_" in directory.name else directory.name
        for directory in chapter_dirs
    ]
    if len(names) != len(chapters):
        raise ValueError("Chapter title count does not match chapter audio count.")
    names = [
        sanitize_metadata(name, f"Chapter {index + 1}")
        for index, name in enumerate(names)
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path = output_path.with_suffix(".m4b")

    effective_audio_mode = str(background_audio_mode or "manual").strip().casefold()
    if effective_audio_mode not in {"off", "auto", "manual"}:
        raise ValueError(f"Unsupported background audio mode: {background_audio_mode}")

    with tempfile.TemporaryDirectory(prefix="ryu-m4b-") as temp:
        temp_dir = Path(temp)

        # Automatic mode creates small, loopable sound beds offline and applies
        # them chapter-by-chapter. The transition cue is prepended to every
        # chapter file before its chapter marker is written, so chapter skips
        # land on the cue and the bed can change with each chapter's mood.
        if effective_audio_mode == "auto":
            from app.audio.sound_design import (
                detect_chapter_mood,
                synthesize_chapter_transition,
                synthesize_music_bed,
            )

            music_cache: dict[str, Path] = {}
            cue_cache: dict[str, Path] = {}
            processed_chapters: list[Path] = []
            for index, (chapter_file, chapter_dir, chapter_title) in enumerate(
                zip(chapters, chapter_dirs, names), start=1
            ):
                narration_text = ""
                narration_meta = chapter_dir / "narration.json"
                try:
                    payload = json.loads(narration_meta.read_text(encoding="utf-8"))
                    narration_text = str(payload.get("narration_text") or "")
                    chapter_title = str(payload.get("title") or chapter_title)
                except (OSError, ValueError, TypeError):
                    pass

                mood = detect_chapter_mood(chapter_title, narration_text, auto_music_style)
                if mood not in music_cache:
                    music_cache[mood] = synthesize_music_bed(
                        temp_dir / f"auto-music-{mood}.wav", mood
                    )
                bed_path = music_cache[mood]
                cue_path = None
                if chapter_transition_sound:
                    if mood not in cue_cache:
                        cue_cache[mood] = synthesize_chapter_transition(
                            temp_dir / f"chapter-transition-{mood}.wav", mood
                        )
                    cue_path = cue_cache[mood]

                base_duration_ms = _duration_ms(chapter_file)
                duration_seconds = max(0.1, base_duration_ms / 1000.0)
                fade_in = min(30.0, max(0.0, float(background_audio_fade_in)))
                fade_out = min(30.0, max(0.0, float(background_audio_fade_out)))
                fade_in = min(fade_in, duration_seconds)
                fade_out = min(fade_out, duration_seconds)
                fade_out_start = max(0.0, duration_seconds - fade_out)
                music_gain = max(0.0, min(1.0, float(background_audio_volume)))

                mixed_chapter = temp_dir / f"auto-chapter-{index:05d}.m4a"
                if cue_path:
                    inputs = [
                        "-i", str(cue_path),
                        "-i", str(chapter_file),
                        "-stream_loop", "-1", "-i", str(bed_path),
                    ]
                    filters = [
                        "[0:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo,volume=0.22[cue]",
                        "[1:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo[narr]",
                        (
                            f"[2:a]volume={music_gain:.4f},aresample=44100,"
                            "aformat=sample_rates=44100:channel_layouts=stereo,"
                            f"afade=t=in:st=0:d={fade_in:.3f},"
                            f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f}[bed]"
                        ),
                        "[narr][bed]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[mixed]",
                        "[cue][mixed]concat=n=2:v=0:a=1[out]",
                    ]
                    cue_duration_ms = _duration_ms(cue_path)
                else:
                    inputs = [
                        "-i", str(chapter_file),
                        "-stream_loop", "-1", "-i", str(bed_path),
                    ]
                    filters = [
                        "[0:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo[narr]",
                        (
                            f"[1:a]volume={music_gain:.4f},aresample=44100,"
                            "aformat=sample_rates=44100:channel_layouts=stereo,"
                            f"afade=t=in:st=0:d={fade_in:.3f},"
                            f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f}[bed]"
                        ),
                        "[narr][bed]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[out]",
                    ]
                    cue_duration_ms = 0

                _run([
                    *inputs,
                    "-filter_complex", ";".join(filters),
                    "-map", "[out]", "-vn",
                    "-c:a", "aac", "-b:a", audio_bitrate, "-ar", "44100",
                    str(mixed_chapter),
                ])
                if not mixed_chapter.exists() or mixed_chapter.stat().st_size == 0:
                    raise RuntimeError(
                        f"Could not mix automatic background audio for chapter {index}."
                    )
                expected_duration = base_duration_ms + cue_duration_ms
                if abs(_duration_ms(mixed_chapter) - expected_duration) > 1500:
                    raise RuntimeError(
                        f"Automatic sound design changed chapter {index} duration unexpectedly."
                    )
                processed_chapters.append(mixed_chapter)

                if progress:
                    progress(index, len(chapters), "automatic-chapter-sound-design")

            chapters = processed_chapters

        concat = temp_dir / "chapters.txt"
        concat_lines = ["ffconcat version 1.0"]
        durations: list[int] = []
        for chapter_file in chapters:
            duration = _duration_ms(chapter_file)
            durations.append(duration)
            concat_lines.append(f"file '{_ffconcat_path(chapter_file)}'")
            concat_lines.append(f"duration {duration / 1000.0:.6f}")
        concat.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

        metadata_values = metadata or {}
        metadata_path = temp_dir / "metadata.txt"
        clean_title = _safe_title(metadata_values.get("title") or title)
        clean_artist = sanitize_metadata(metadata_values.get("author") or author)
        narrator = sanitize_metadata(metadata_values.get("narrator"))
        publisher = sanitize_metadata(metadata_values.get("publisher"))
        series = sanitize_metadata(metadata_values.get("series"))
        series_number = sanitize_metadata(metadata_values.get("series_number"))
        language = sanitize_metadata(metadata_values.get("language"))
        year = sanitize_metadata(metadata_values.get("year"))
        genre = sanitize_metadata(metadata_values.get("genre"), "Audiobook")
        description = sanitize_metadata(metadata_values.get("description"))

        lines = [
            ";FFMETADATA1",
            f"title={_metadata_value(clean_title)}",
            f"album={_metadata_value(clean_title)}",
            f"genre={_metadata_value(genre)}",
            "comment=Created by Ryu's Audiobook",
        ]
        if clean_artist:
            lines.append(f"artist={_metadata_value(clean_artist)}")
        if narrator:
            lines.append(f"narrator={_metadata_value(narrator)}")
        if publisher:
            lines.append(f"publisher={_metadata_value(publisher)}")
        if series:
            lines.append(f"series={_metadata_value(series)}")
        if series_number:
            lines.append(f"series_number={_metadata_value(series_number)}")
        if language:
            lines.append(f"language={_metadata_value(language)}")
        if year:
            lines.append(f"date={_metadata_value(year)}")
        if description:
            lines.append(f"description={_metadata_value(description)}")

        start = 0
        for duration, chapter_title in zip(durations, names):
            end = start + duration
            lines.extend([
                "[CHAPTER]", "TIMEBASE=1/1000",
                f"START={start}", f"END={end}",
                f"title={_metadata_value(chapter_title)}",
            ])
            start = end
        metadata_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        audio_only = temp_dir / "audiobook-audio.m4a"
        _run([
            "-f", "concat", "-safe", "0", "-i", str(concat),
            "-vn", "-c:a", "copy",
            str(audio_only),
        ])
        if not audio_only.exists() or audio_only.stat().st_size == 0:
            raise RuntimeError("FFmpeg created no intermediate audiobook audio.")
        narration_duration_ms = _duration_ms(audio_only)
        if narration_duration_ms <= 0:
            raise RuntimeError("FFmpeg created an intermediate audiobook with no audio duration.")
        if progress:
            progress(len(chapters), len(chapters), "joined-audio")

        # Stage 1 audio beds: independently mix optional user-owned/licensed
        # music and ambience only after narration has been assembled. Tracks
        # therefore remain continuous across chapter boundaries. FFmpeg/CPU
        # does the work; no GPU memory is needed.
        audio_layers: list[tuple[str, Path | str | None, float]] = [
            ("music", background_audio_path, background_audio_volume),
            ("ambience", ambience_audio_path, ambience_audio_volume),
        ]
        active_layers = [
            (name, Path(path).expanduser(), max(0.0, min(1.0, float(volume))))
            for name, path, volume in audio_layers
            if path
        ]
        if active_layers and effective_audio_mode == "manual":
            for layer_name, layer_path, _layer_volume in active_layers:
                if not layer_path.is_file():
                    raise FileNotFoundError(
                        f"{layer_name.title()} audio file was not found: {layer_path}"
                    )

            fade_in = max(0.0, min(30.0, float(background_audio_fade_in)))
            fade_out = max(0.0, min(30.0, float(background_audio_fade_out)))
            duration_seconds = narration_duration_ms / 1000.0
            fade_out = min(fade_out, duration_seconds)
            fade_out_start = max(0.0, duration_seconds - fade_out)

            inputs = ["-i", str(audio_only)]
            filter_parts = []
            bed_labels = []
            for index, (layer_name, layer_path, layer_volume) in enumerate(active_layers, start=1):
                inputs.extend(["-stream_loop", "-1", "-i", str(layer_path)])
                label = f"bed{index}"
                bed_labels.append(f"[{label}]")
                filters = [f"volume={layer_volume:.4f}"]
                if fade_in > 0:
                    filters.append(f"afade=t=in:st=0:d={fade_in:.3f}")
                if fade_out > 0:
                    filters.append(
                        f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f}"
                    )
                filters.append("aresample=44100")
                filter_parts.append(f"[{index}:a]{','.join(filters)}[{label}]")

            input_labels = "[0:a]" + "".join(bed_labels)
            mix_count = 1 + len(active_layers)
            filter_parts.append(
                f"{input_labels}amix=inputs={mix_count}:duration=first:"
                "dropout_transition=0:normalize=0,alimiter=limit=0.95[out]"
            )
            mixed_audio = temp_dir / "audiobook-mixed.m4a"
            _run([
                *inputs,
                "-filter_complex", ";".join(filter_parts),
                "-map", "[out]", "-vn", "-t", f"{duration_seconds:.3f}",
                "-c:a", "aac", "-b:a", audio_bitrate, "-ar", "44100",
                str(mixed_audio),
            ])
            if not mixed_audio.exists() or mixed_audio.stat().st_size == 0:
                raise RuntimeError("FFmpeg did not create the mixed audiobook audio.")
            if abs(_duration_ms(mixed_audio) - narration_duration_ms) > 1500:
                raise RuntimeError(
                    "Mixed audiobook duration differs from narration by more than 1.5 seconds."
                )
            audio_only = mixed_audio
            if progress:
                progress(len(chapters), len(chapters), "mixed-background-audio")

        base_m4b = temp_dir / "audiobook-base.m4b"
        args = [
            "-i", str(audio_only),
            "-f", "ffmetadata", "-i", str(metadata_path),
            "-map", "0:a:0",
            "-map_metadata", "1",
            "-map_chapters", "1",
            "-c:a", "copy",
            "-movflags", "+faststart+use_metadata_tags",
            "-metadata", f"title={_metadata_value(clean_title)}",
            "-metadata", f"album={_metadata_value(clean_title)}",
            "-metadata", f"comment=Ryu's Audiobook • AAC {audio_bitrate}",
        ]
        if clean_artist:
            args += ["-metadata", f"artist={clean_artist}"]
        if narrator:
            args += ["-metadata", f"narrator={narrator}"]
        if publisher:
            args += ["-metadata", f"publisher={publisher}"]
        if series:
            args += ["-metadata", f"series={series}"]
        if series_number:
            args += ["-metadata", f"series_number={series_number}"]
        if language:
            args += ["-metadata", f"language={language}"]
        if year:
            args += ["-metadata", f"date={year}"]
        if genre:
            args += ["-metadata", f"genre={genre}"]
        if description:
            args += ["-metadata", f"description={description}"]
        args.append(str(base_m4b))
        _run(args)

        if not base_m4b.exists() or base_m4b.stat().st_size == 0:
            raise RuntimeError("FFmpeg created no base M4B before cover embedding.")

        if cover:
            cover_jpg = temp_dir / "cover.jpg"
            _run([
                "-i", str(cover),
                "-frames:v", "1",
                "-c:v", "mjpeg",
                "-q:v", "3",
                str(cover_jpg),
            ])
            if not cover_jpg.exists() or cover_jpg.stat().st_size == 0:
                raise RuntimeError("Cover image could not be converted to JPEG.")

            _run([
                "-i", str(base_m4b),
                "-i", str(cover_jpg),
                "-map", "0:a:0",
                "-map", "1:v:0",
                "-map_chapters", "0",
                "-c", "copy",
                "-disposition:v:0", "attached_pic",
                "-metadata:s:v:0", "title=Cover",
                "-metadata:s:v:0", "comment=Cover Art",
                "-metadata:s:v:0", "mimetype=image/jpeg",
                "-metadata:s:v:0", "filename=cover.jpg",
                "-movflags", "+faststart",
                str(output_path),
            ])
        else:
            import shutil
            shutil.copy2(base_m4b, output_path)

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("FFmpeg completed but the final M4B is missing.")

    # Validate that the final M4B really contains an audio stream. We also
    # inspect the encoded stream bitrate so a future packaging regression
    # cannot silently return another sub-128k audiobook.
    probe = subprocess.run(
        [
            ffmpeg_path(), "-v", "error", "-i", str(output_path),
            "-map", "0:a:0", "-t", "0.25", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout or "").strip()
        raise RuntimeError(
            f"FFmpeg completed but the final M4B audio could not be validated.\n{detail}"
        )

    detected_kbps = _probe_audio_bitrate_kbps(output_path)
    if detected_kbps < MIN_AUDIO_BITRATE_KBPS:
        raise RuntimeError(
            f"Final audiobook bitrate is only {detected_kbps} kbps. "
            f"Ryu's Audiobook requires at least {MIN_AUDIO_BITRATE_KBPS} kbps."
        )

    return output_path
