from __future__ import annotations

import hashlib
import json
from pathlib import Path
import wave
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


def _encoding_audio_bitrate(bitrate: int | str | None) -> str:
    """Choose an encoder target that reliably clears the 128 kbps output floor.

    The AAC encoder can report a stream below a 128k target for short/simple
    test audio. Keep the user-facing supported range unchanged, but use a
    160k encoder target for a 128k request so the finished M4B retains margin
    above the required minimum after AAC/container overhead.
    """
    requested = normalize_audio_bitrate(bitrate)
    if requested == "128k":
        return "160k"
    return requested


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


def _concat_audio_files(first: Path, second: Path, output: Path, bitrate: str) -> Path:
    """Join two audio files in order while preserving the chapter timeline."""
    _run([
        "-i", str(first), "-i", str(second),
        "-filter_complex",
        "[0:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo[a0];"
        "[1:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo[a1];"
        "[a0][a1]concat=n=2:v=0:a=1[out]",
        "-map", "[out]", "-vn", "-c:a", "aac", "-b:a", bitrate,
        "-ar", "44100", str(output),
    ])
    if not output.exists() or output.stat().st_size < 1024:
        raise RuntimeError(f"Could not join audio cue into {output.name}.")
    return output


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
    audio_bitrate = _encoding_audio_bitrate(bitrate)

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


def _selected_music_recipe(
    title: str,
    text: str,
    style: str,
    selected_catalogue_id: int | None,
) -> tuple[str, int]:
    """Resolve a 1-based catalogue ID, or choose a stable chapter-matched recipe."""
    from app.audio.sound_design import (
        MUSIC_CATALOGUE_SIZE, MOOD_ORDER, VARIATIONS_PER_MOOD,
        detect_chapter_mood, select_music_variation,
    )
    try:
        selected_id = int(selected_catalogue_id or 0)
    except (TypeError, ValueError):
        selected_id = 0
    if 1 <= selected_id <= MUSIC_CATALOGUE_SIZE:
        mood_index, variation_index = divmod(selected_id - 1, VARIATIONS_PER_MOOD)
        return MOOD_ORDER[mood_index], variation_index
    mood = detect_chapter_mood(title, text, style)
    return mood, select_music_variation(title, text, mood)


def _resolve_cue_audio(
    temp_dir: Path,
    kind: str,
    cue_style: str,
    variation_index: int,
    mood: str,
    custom_path: Path | str | None,
) -> Path | None:
    """Resolve a real imported cue; never synthesize a placeholder."""
    from app.audio.library import resolve_cue_track
    return resolve_cue_track(kind, selected_path=custom_path,
                             seed_text=f"{kind}|{mood}|{int(variation_index)}")


def _mix_chapter_bgm(
    chapter_file: Path,
    track_path: Path | str,
    output_path: Path,
    volume: float,
    fade_in: float = 2.0,
    fade_out: float = 3.0,
    start_offset_ms: int = 0,
    bitrate: str = "192k",
) -> Path:
    """Mix one chapter-specific music bed under narration without changing duration."""
    track = Path(track_path).expanduser()
    if not track.is_file():
        raise FileNotFoundError(f"Chapter background music was not found: {track}")
    duration_ms = _duration_ms(chapter_file)
    duration_seconds = max(0.1, duration_ms / 1000.0)
    gain = max(0.0, min(1.0, float(volume)))
    if gain <= 0.0:
        return chapter_file
    offset_ms = max(0, min(int(start_offset_ms), max(0, duration_ms - 1)))
    offset_seconds = offset_ms / 1000.0
    fade_in_seconds = max(0.0, min(30.0, float(fade_in)))
    fade_out_seconds = max(0.0, min(30.0, float(fade_out), duration_seconds))
    fade_out_start = max(offset_seconds, duration_seconds - fade_out_seconds)
    music_filters = [f"volume={gain:.4f}", "aresample=44100",
                     "aformat=sample_rates=44100:channel_layouts=stereo"]
    if offset_ms:
        music_filters.append(f"adelay={offset_ms}|{offset_ms}")
    if fade_in_seconds > 0:
        music_filters.append(f"afade=t=in:st={offset_seconds:.3f}:d={fade_in_seconds:.3f}")
    if fade_out_seconds > 0:
        music_filters.append(f"afade=t=out:st={fade_out_start:.3f}:d={fade_out_seconds:.3f}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "-i", str(chapter_file), "-stream_loop", "-1", "-i", str(track),
        "-filter_complex",
        "[0:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo[narr];"
        f"[1:a]{','.join(music_filters)}[bed];"
        "[narr][bed]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        "alimiter=limit=0.95[out]",
        "-map", "[out]", "-vn", "-t", f"{duration_seconds:.3f}",
        "-c:a", "aac", "-b:a", bitrate, "-ar", "44100", str(output_path),
    ])
    if not output_path.exists() or output_path.stat().st_size < 1024:
        raise RuntimeError("FFmpeg did not create chapter-specific BGM audio.")
    if abs(_duration_ms(output_path) - duration_ms) > 1500:
        raise RuntimeError("Chapter-specific BGM changed chapter duration unexpectedly.")
    return output_path


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
    auto_music_variation: int | str | Path | None = None,
    chapter_transition_sound: bool = False,
    story_effects_enabled: bool = False,
    story_effect_volume: float = 0.18,
    sound_cue_style: str = "classic-book",
    opening_cue_path: Path | str | None = None,
    page_turn_cue_path: Path | str | None = None,
    ending_cue_path: Path | str | None = None,
    scene_transition_cue_path: Path | str | None = None,
    chapter_bgm_overrides: dict[str, dict] | None = None,
) -> Path:
    """Create one premium M4B containing all chapters and navigation metadata.

    Optional music and ambience tracks are independently gained, looped to
    narration duration, and mixed locally. Both layers are off unless paths
    are supplied.
    """
    if not chapter_dirs:
        raise ValueError("No chapters were supplied.")
    audio_bitrate = _encoding_audio_bitrate(bitrate)

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

    # Actual duration of each inserted cue is used to keep story-effect timing
    # aligned, including user-selected custom opening/page/closing audio.
    cue_offset_by_chapter: dict[int, int] = {}
    with tempfile.TemporaryDirectory(prefix="ryu-m4b-") as temp:
        temp_dir = Path(temp)

        # Real local audio only: no procedural BGM and no fake book cues.
        from app.audio.library import resolve_music_track

        if effective_audio_mode == "auto":
            processed_chapters: list[Path] = []
            for index, (chapter_file, chapter_dir, chapter_title) in enumerate(
                zip(chapters, chapter_dirs, names), start=1
            ):
                narration_text = ""
                try:
                    payload = json.loads((chapter_dir / "narration.json").read_text(encoding="utf-8"))
                    narration_text = str(payload.get("narration_text") or "")
                    chapter_title = str(payload.get("title") or chapter_title)
                except (OSError, ValueError, TypeError):
                    pass
                mood, variation = _selected_music_recipe(
                    chapter_title, narration_text, auto_music_style, None
                )
                current_audio = chapter_file
                cue_offset_by_chapter[index] = 0
                if chapter_transition_sound:
                    cue_kind = "opening" if index == 1 else "page"
                    selected_cue = opening_cue_path if cue_kind == "opening" else page_turn_cue_path
                    cue = _resolve_cue_audio(temp_dir, cue_kind, "library", variation, mood, selected_cue) if selected_cue else None
                    if cue is not None:
                        prefixed = temp_dir / f"auto-real-cue-{index:05d}.m4a"
                        cue_offset_by_chapter[index] = _duration_ms(cue)
                        _concat_audio_files(cue, current_audio, prefixed, audio_bitrate)
                        current_audio = prefixed
                if index > 1 and scene_transition_cue_path:
                    scene_cue = _resolve_cue_audio(temp_dir, "scene", "library", variation, mood, scene_transition_cue_path)
                    if scene_cue is not None:
                        scene_prefixed = temp_dir / f"auto-real-scene-cue-{index:05d}.m4a"
                        _concat_audio_files(scene_cue, current_audio, scene_prefixed, audio_bitrate)
                        current_audio = scene_prefixed

                duration_ms = _duration_ms(current_audio)
                duration_seconds = max(0.1, duration_ms / 1000.0)
                music_gain = max(0.0, min(1.0, float(background_audio_volume)))
                music_path = resolve_music_track(
                    mood, selected_track=auto_music_variation,
                    seed_text=f"{chapter_title}|{narration_text}|{index}",
                )
                if music_path is not None and music_gain > 0.0:
                    fade_in = min(max(0.0, float(background_audio_fade_in)), duration_seconds)
                    fade_out = min(max(0.0, float(background_audio_fade_out)), duration_seconds)
                    mixed = temp_dir / f"auto-real-bgm-{index:05d}.m4a"
                    filters = [
                        "[0:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo[narr]",
                        (f"[1:a]volume={music_gain:.4f},aresample=44100,"
                         "aformat=sample_rates=44100:channel_layouts=stereo,"
                         f"afade=t=in:st=0:d={fade_in:.3f},"
                         f"afade=t=out:st={max(0.0,duration_seconds-fade_out):.3f}:d={fade_out:.3f}[bed]"),
                        "[bed][narr]sidechaincompress=threshold=0.025:ratio=7:attack=22:release=420:makeup=1[ducked]",
                        "[narr][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[out]",
                    ]
                    _run(["-i",str(current_audio),"-stream_loop","-1","-i",str(music_path),
                          "-filter_complex",";".join(filters),"-map","[out]","-vn","-t",f"{duration_seconds:.3f}",
                          "-c:a","aac","-b:a",audio_bitrate,"-ar","44100",str(mixed)])
                    if not mixed.exists() or mixed.stat().st_size==0:
                        raise RuntimeError(f"Could not mix real BGM into chapter {index}.")
                    final_chapter=mixed
                else:
                    # An empty local library must not bring back generated filler.
                    final_chapter=current_audio
                if chapter_transition_sound and index==len(chapters):
                    closing=_resolve_cue_audio(temp_dir,"ending","library",variation,mood,ending_cue_path) if ending_cue_path else None if ending_cue_path else None
                    if closing is not None:
                        ended=temp_dir/f"auto-real-ending-{index:05d}.m4a"
                        _concat_audio_files(final_chapter,closing,ended,audio_bitrate)
                        final_chapter=ended
                processed_chapters.append(final_chapter)
                if progress: progress(index,len(chapters),"automatic-real-audio-design")
            chapters=processed_chapters

        elif effective_audio_mode in {"manual","off"} and chapter_transition_sound:
            cued_chapters: list[Path]=[]
            for index,(chapter_file,chapter_dir,chapter_title) in enumerate(zip(chapters,chapter_dirs,names),start=1):
                narration_text=""
                try:
                    payload=json.loads((chapter_dir/"narration.json").read_text(encoding="utf-8"))
                    narration_text=str(payload.get("narration_text") or "")
                    chapter_title=str(payload.get("title") or chapter_title)
                except (OSError,ValueError,TypeError): pass
                mood,variation=_selected_music_recipe(chapter_title,narration_text,auto_music_style,None)
                current_audio=chapter_file
                cue_offset_by_chapter[index]=0
                kind="opening" if index==1 else "page"
                selected_cue=opening_cue_path if kind=="opening" else page_turn_cue_path
                cue=_resolve_cue_audio(temp_dir,kind,"library",variation,mood,selected_cue) if selected_cue else None
                if cue is not None:
                    prefixed=temp_dir/f"{effective_audio_mode}-real-cue-{index:05d}.m4a"
                    cue_offset_by_chapter[index]=_duration_ms(cue)
                    _concat_audio_files(cue,current_audio,prefixed,audio_bitrate)
                    current_audio=prefixed
                if index > 1 and scene_transition_cue_path:
                    scene_cue = _resolve_cue_audio(temp_dir, "scene", "library", variation, mood, scene_transition_cue_path)
                    if scene_cue is not None:
                        scene_prefixed = temp_dir / f"{effective_audio_mode}-real-scene-cue-{index:05d}.m4a"
                        _concat_audio_files(scene_cue, current_audio, scene_prefixed, audio_bitrate)
                        current_audio = scene_prefixed
                if index==len(chapters):
                    closing=_resolve_cue_audio(temp_dir,"ending","library",variation,mood,ending_cue_path)
                    if closing is not None:
                        ended=temp_dir/f"{effective_audio_mode}-real-ending-{index:05d}.m4a"
                        _concat_audio_files(current_audio,closing,ended,audio_bitrate)
                        current_audio=ended
                cued_chapters.append(current_audio)
            chapters=cued_chapters

        # Story-aware SFX are aligned to the source text inside each generated
        # chunk. Only explicit phrases trigger effects; cues are volume-limited,
        # de-duplicated, and bounded per chapter to avoid an over-produced mix.
        if story_effects_enabled:
            from app.audio.sound_design import TRANSITION_SECONDS
            from app.audio.story_events import (
                EVENT_PROFILES,
                MAX_EVENTS_PER_CHAPTER,
                detect_story_events,
                synthesize_story_effect,
            )

            effect_cache: dict[tuple[str, int], Path] = {}
            mixed_chapters: list[Path] = []
            master_sfx_volume = max(0.0, min(0.50, float(story_effect_volume)))
            for chapter_index, (chapter_file, chapter_dir) in enumerate(
                zip(chapters, chapter_dirs), start=1
            ):
                manifest_path = chapter_dir / "chunk_manifest.json"
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest_chunks = manifest.get("chunks") or []
                except (OSError, ValueError, TypeError):
                    manifest_chunks = []
                if not manifest_chunks or master_sfx_volume <= 0.0:
                    mixed_chapters.append(chapter_file)
                    continue

                # Account for the real selected opening/page audio so effect
                # cues remain aligned when the user chooses longer custom sounds.
                transition_offset_ms = cue_offset_by_chapter.get(chapter_index, 0)
                cursor_ms = 0.0
                chapter_duration_ms = _duration_ms(chapter_file)
                pending: list[tuple[int, object, int]] = []
                last_kind_ms: dict[str, int] = {}
                accepted_starts: list[int] = []
                event_serial = 0
                for chunk_info in manifest_chunks:
                    chunk_text = str(chunk_info.get("text") or "")
                    if not chunk_text.strip():
                        continue
                    chunk_name = str(chunk_info.get("file") or "")
                    chunk_wav = chapter_dir / "chunks" / Path(chunk_name).name
                    try:
                        with wave.open(str(chunk_wav), "rb") as wav_file:
                            # The WAV already reflects the provider's actual
                            # speed setting and pacing silence. Do not scale it
                            # a second time; the observed file duration is the
                            # best cheap timeline basis available offline.
                            chunk_duration_ms = (
                                wav_file.getnframes() * 1000.0
                                / max(1, wav_file.getframerate())
                            )
                    except (OSError, wave.Error):
                        continue

                    for event in detect_story_events(chunk_text):
                        if len(pending) >= MAX_EVENTS_PER_CHAPTER:
                            break
                        fraction = max(0.0, min(1.0, event.char_start / max(1, len(chunk_text))))
                        text_position_ms = cursor_ms + fraction * chunk_duration_ms
                        # Small pre-roll lets an effect lead the written action
                        # slightly, rather than sounding like an afterthought.
                        event_time_ms = max(
                            0,
                            transition_offset_ms + int(text_position_ms) - 110,
                        )
                        if event_time_ms >= chapter_duration_ms:
                            continue

                        previous = last_kind_ms.get(event.kind)
                        cooldown_ms = (
                            6500 if event.category == "ambience"
                            else 3500 if event.category == "body"
                            else 2200
                        )
                        if previous is not None and event_time_ms - previous < cooldown_ms:
                            continue
                        if any(abs(event_time_ms - old) < 480 for old in accepted_starts):
                            continue

                        seed_payload = (
                            f"{chapter_dir.name}|{chapter_index}|{event.kind}|"
                            f"{event_serial}|{chunk_text[:120]}"
                        ).encode("utf-8", errors="replace")
                        seed = int.from_bytes(
                            hashlib.blake2b(seed_payload, digest_size=4).digest(),
                            "big",
                        ) % 8
                        pending.append((event_time_ms, event, seed))
                        last_kind_ms[event.kind] = event_time_ms
                        accepted_starts.append(event_time_ms)
                        event_serial += 1
                    cursor_ms += chunk_duration_ms
                    if len(pending) >= MAX_EVENTS_PER_CHAPTER:
                        break

                if not pending:
                    mixed_chapters.append(chapter_file)
                    if progress:
                        progress(chapter_index, len(chapters), "story-effects-no-matching-cues")
                    continue

                effect_inputs: list[str] = []
                effect_filters: list[str] = [
                    "[0:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo[base]"
                ]
                mix_labels = "[base]"
                for effect_index, (delay_ms, event, seed) in enumerate(pending, start=1):
                    event_kind = str(event.kind)
                    cache_key = (event_kind, seed)
                    if cache_key not in effect_cache:
                        effect_path = temp_dir / f"story-sfx-{event_kind}-{seed}.wav"
                        effect_cache[cache_key] = synthesize_story_effect(
                            effect_path, event_kind, variant_seed=seed
                        )
                    effect_path = effect_cache[cache_key]
                    effect_inputs.extend(["-i", str(effect_path)])
                    gain = max(
                        0.0,
                        min(1.0, master_sfx_volume * float(event.mix_gain)),
                    )
                    label = f"fx{effect_index}"
                    effect_filters.append(
                        f"[{effect_index}:a]aresample=44100,"
                        "aformat=sample_rates=44100:channel_layouts=stereo,"
                        f"volume={gain:.4f},adelay={delay_ms}|{delay_ms}[{label}]"
                    )
                    mix_labels += f"[{label}]"

                effect_filters.append(
                    f"{mix_labels}amix=inputs={len(pending) + 1}:duration=first:"
                    "dropout_transition=0:normalize=0,alimiter=limit=0.93[out]"
                )
                mixed_chapter = temp_dir / f"story-mix-chapter-{chapter_index:05d}.m4a"
                original_duration_ms = _duration_ms(chapter_file)
                _run([
                    "-i", str(chapter_file),
                    *effect_inputs,
                    "-filter_complex", ";".join(effect_filters),
                    "-map", "[out]", "-vn",
                    "-t", f"{original_duration_ms / 1000.0:.3f}",
                    "-c:a", "aac", "-b:a", audio_bitrate, "-ar", "44100",
                    str(mixed_chapter),
                ])
                if not mixed_chapter.exists() or mixed_chapter.stat().st_size == 0:
                    raise RuntimeError(
                        f"Story-aware sound-effect mix failed for chapter {chapter_index}."
                    )
                if abs(_duration_ms(mixed_chapter) - original_duration_ms) > 1500:
                    raise RuntimeError(
                        f"Story effects changed chapter {chapter_index} duration unexpectedly."
                    )
                mixed_chapters.append(mixed_chapter)
                if progress:
                    progress(chapter_index, len(chapters), "story-effects-mixed")
            chapters = mixed_chapters

        # Mix chapter-specific BGM before concatenation. When overrides exist,
        # book music is scoped per chapter so custom/none rules replace the default.
        effective_overrides = chapter_bgm_overrides if isinstance(chapter_bgm_overrides, dict) else {}
        chapter_scoped_bgm = bool(effective_overrides) and effective_audio_mode == "manual"
        if chapter_scoped_bgm:
            chapter_music_files: list[Path] = []
            for chapter_index, (chapter_file, chapter_dir) in enumerate(zip(chapters, chapter_dirs), start=1):
                override = effective_overrides.get(str(chapter_index), {})
                if not isinstance(override, dict):
                    override = {}
                rule = str(override.get("rule") or "default").strip().lower()
                if rule not in {"default", "custom", "none"}:
                    raise ValueError(f"Unsupported BGM rule for chapter {chapter_index}: {rule}")
                selected_track = override.get("path") if rule == "custom" else background_audio_path
                if rule == "none" or not selected_track:
                    chapter_music_files.append(chapter_file)
                    continue
                if rule == "custom" and not Path(str(selected_track)).expanduser().is_file():
                    raise FileNotFoundError(f"Custom BGM for chapter {chapter_index} was not found: {selected_track}")
                volume = override.get("volume", background_audio_volume)
                start_offset = str(override.get("start_offset") or "immediate").strip().lower()
                offset_ms = 0
                if start_offset == "after_10_seconds":
                    offset_ms = 10_000
                elif start_offset == "after_first_paragraph":
                    try:
                        manifest = json.loads((chapter_dir / "chunk_manifest.json").read_text(encoding="utf-8"))
                        first_chunk = (manifest.get("chunks") or [])[0]
                        chunk_path = chapter_dir / "chunks" / str(first_chunk.get("file") or "")
                        if chunk_path.is_file():
                            offset_ms = _duration_ms(chunk_path)
                    except (OSError, ValueError, TypeError, IndexError):
                        offset_ms = 0
                behavior = str(override.get("end_behavior") or "fade_before_end").strip().lower()
                fade_out = float(background_audio_fade_out) if behavior == "fade_before_end" else 0.0
                mixed = temp_dir / f"chapter-bgm-{chapter_index:05d}.m4a"
                chapter_music_files.append(_mix_chapter_bgm(
                    chapter_file, selected_track, mixed, float(volume),
                    fade_in=float(background_audio_fade_in), fade_out=fade_out,
                    start_offset_ms=offset_ms, bitrate=audio_bitrate,
                ))
                if progress:
                    progress(chapter_index, len(chapters), "mixed-chapter-background-audio")
            chapters = chapter_music_files

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
            ("music", None if chapter_scoped_bgm else background_audio_path, background_audio_volume),
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
            split_outputs = "[narr_mix]" + "".join(
                f"[speech_sc{index}]" for index in range(1, len(active_layers) + 1)
            )
            filter_parts.append(
                f"[0:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo,"
                f"asplit={1 + len(active_layers)}{split_outputs}"
            )
            for index, (layer_name, layer_path, layer_volume) in enumerate(active_layers, start=1):
                inputs.extend(["-stream_loop", "-1", "-i", str(layer_path)])
                raw_label = f"bedraw{index}"
                duck_label = f"bed{index}"
                filters = [f"volume={layer_volume:.4f}"]
                if fade_in > 0:
                    filters.append(f"afade=t=in:st=0:d={fade_in:.3f}")
                if fade_out > 0:
                    filters.append(
                        f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f}"
                    )
                filters.append("aresample=44100")
                filter_parts.append(f"[{index}:a]{','.join(filters)}[{raw_label}]")
                filter_parts.append(
                    f"[{raw_label}][speech_sc{index}]sidechaincompress="
                    "threshold=0.025:ratio=7:attack=22:release=420:makeup=1"
                    f"[{duck_label}]"
                )
                bed_labels.append(f"[{duck_label}]")

            input_labels = "[narr_mix]" + "".join(bed_labels)
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
