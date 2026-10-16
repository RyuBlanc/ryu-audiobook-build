from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import wave

import imageio_ffmpeg


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip()[-3000:]
        raise RuntimeError(f"Preview sound-design mix failed. {detail}")


def _duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as reader:
        return reader.getnframes() / max(1, reader.getframerate())


def _join_audio(first: Path, second: Path, output: Path) -> Path:
    _run_ffmpeg([
        "-i", str(first), "-i", str(second),
        "-filter_complex",
        "[0:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo[a0];"
        "[1:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo[a1];"
        "[a0][a1]concat=n=2:v=0:a=1[out]",
        "-map", "[out]", "-vn", "-c:a", "pcm_s16le", "-ar", "44100", str(output),
    ])
    if not output.exists() or output.stat().st_size < 1024:
        raise RuntimeError(f"Could not append the preview sound cue to {output.name}.")
    return output


def mix_voice_preview(
    voice_path: Path | str,
    output_path: Path | str,
    source_text: str,
    *,
    background_enabled: bool = True,
    background_mode: str = "auto",
    music_style: str = "auto",
    music_variation_id: int | None = None,
    background_audio_path: str | Path | None = None,
    ambience_audio_path: str | Path | None = None,
    music_volume: float = 0.12,
    ambience_volume: float = 0.06,
    story_effects_enabled: bool = True,
    story_effect_volume: float = 0.12,
    chapter_transition_sound: bool = True,
    is_first_chapter: bool = True,
    is_last_chapter: bool = False,
    sound_cue_style: str = "classic-book",
    opening_cue_path: str | Path | None = None,
    page_turn_cue_path: str | Path | None = None,
    ending_cue_path: str | Path | None = None,
) -> Path:
    """Mix the selected preview voice with the same offline sound design used by M4B export.

    The preview uses the selected/automatically generated BGM recipe, ducks beds under
    narration, places a few explicit story-event cues, and adds a page-turn/end cue
    when the selected chapter's position warrants one. All work is local.
    """
    from app.audio.sound_design import (
        ENDING_SECONDS,
        MOOD_ORDER,
        MUSIC_CATALOGUE_SIZE,
        VARIATIONS_PER_MOOD,
        detect_chapter_mood,
        select_music_variation,
        normalize_cue_style,
        synthesize_audiobook_ending,
        synthesize_music_bed,
        synthesize_opening_cue,
        synthesize_page_turn,
    )
    from app.audio.story_events import (
        MAX_EVENTS_PER_CHUNK,
        detect_story_events,
        synthesize_story_effect,
    )

    voice_path = Path(voice_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()
    if not voice_path.is_file():
        raise FileNotFoundError(f"Voice preview audio was not found: {voice_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = str(source_text or "").strip()
    mode = str(background_mode or "auto").strip().casefold()
    title = "Voice preview"
    mood = detect_chapter_mood(title, text, music_style)

    selected_variation = None
    if music_variation_id is not None:
        try:
            selected_id = int(music_variation_id)
        except (TypeError, ValueError):
            selected_id = 0
        if 1 <= selected_id <= MUSIC_CATALOGUE_SIZE:
            mood_index, selected_variation = divmod(selected_id - 1, VARIATIONS_PER_MOOD)
            mood = MOOD_ORDER[mood_index]

    if selected_variation is None:
        selected_variation = select_music_variation(title, text, mood)

    music_volume = max(0.0, min(1.0, float(music_volume)))
    ambience_volume = max(0.0, min(1.0, float(ambience_volume)))
    story_effect_volume = max(0.0, min(0.5, float(story_effect_volume)))

    with tempfile.TemporaryDirectory(prefix="ryu-preview-mix-") as tmp:
        temp = Path(tmp)
        voice_for_mix = voice_path
        prefix_seconds = 0.0
        cue_style = normalize_cue_style(sound_cue_style)

        def selected_cue(kind: str, custom_path: str | Path | None) -> Path:
            candidate = Path(custom_path).expanduser() if custom_path else None
            if cue_style == "custom" and candidate and candidate.is_file():
                return candidate.resolve()
            generated_style = "classic-book" if cue_style == "custom" else cue_style
            if kind == "opening":
                return synthesize_opening_cue(
                    temp / "preview-opening-cue.wav",
                    variation_index=selected_variation,
                    cue_style=generated_style,
                )
            if kind == "page":
                return synthesize_page_turn(
                    temp / "preview-page-turn.wav",
                    variation_index=selected_variation,
                    cue_style=generated_style,
                )
            if kind == "ending":
                return synthesize_audiobook_ending(
                    temp / "preview-book-ending.wav",
                    mood,
                    variation_index=selected_variation,
                    cue_style=generated_style,
                    duration_seconds=ENDING_SECONDS,
                )
            raise ValueError(f"Unknown book cue type: {kind}")

        if chapter_transition_sound:
            if is_first_chapter:
                cue = selected_cue("opening", opening_cue_path)
                prefixed_voice = temp / "preview-with-book-opening.wav"
            else:
                cue = selected_cue("page", page_turn_cue_path)
                prefixed_voice = temp / "preview-with-page-turn.wav"
            _join_audio(cue, voice_for_mix, prefixed_voice)
            voice_for_mix = prefixed_voice
            prefix_seconds = _duration_seconds(cue)

        voice_duration = max(0.05, _duration_seconds(voice_for_mix))
        layers: list[tuple[Path, float, str]] = []
        if background_enabled and mode == "auto" and music_volume > 0:
            music = synthesize_music_bed(
                temp / f"preview-music-{mood}-{selected_variation:03d}.wav",
                mood,
                variation_index=selected_variation,
            )
            layers.append((music, music_volume, "music"))
        elif background_enabled and mode == "manual":
            for layer_path, gain, label in (
                (background_audio_path, music_volume, "music"),
                (ambience_audio_path, ambience_volume, "ambience"),
            ):
                if layer_path and gain > 0:
                    candidate = Path(layer_path).expanduser()
                    if candidate.is_file():
                        layers.append((candidate.resolve(), gain, label))

        effect_entries: list[tuple[int, str, int]] = []
        if story_effects_enabled and text and story_effect_volume > 0:
            events = detect_story_events(text, max_events=min(3, MAX_EVENTS_PER_CHUNK))
            seen_kinds: set[str] = set()
            for event_number, event in enumerate(events):
                # Avoid cluttering a short preview with repeated or almost
                # simultaneous synthetic effects.
                if event.kind in seen_kinds:
                    continue
                seen_kinds.add(event.kind)
                fraction = max(0.0, min(1.0, event.char_start / max(1, len(text))))
                delay_ms = max(0, int(prefix_seconds * 1000 + fraction * voice_duration * 1000 - 80))
                effect_entries.append((delay_ms, event.kind, (selected_variation + event_number) % 8))

        effect_paths: list[tuple[Path, int, float]] = []
        for number, (delay, event_kind, seed) in enumerate(effect_entries):
            path = synthesize_story_effect(
                temp / f"preview-effect-{number:02d}-{event_kind}.wav",
                event_kind,
                variant_seed=seed,
            )
            effect_paths.append((path, delay, story_effect_volume))

        mixed_path = temp / "preview-mixed.wav"
        args: list[str] = ["-i", str(voice_for_mix)]
        for layer_path, _gain, _label in layers:
            args.extend(["-stream_loop", "-1", "-i", str(layer_path)])
        for effect_path, _delay, _gain in effect_paths:
            args.extend(["-i", str(effect_path)])

        filters: list[str] = []
        bed_labels: list[str] = []
        if layers:
            split_labels = "[voice]" + "".join(
                f"[speech_sc{index}]" for index in range(1, len(layers) + 1)
            )
            filters.append(
                "[0:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo,"
                f"asplit={len(layers) + 1}{split_labels}"
            )
        else:
            filters.append(
                "[0:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo[voice]"
            )

        for index, (layer_path, gain, label_name) in enumerate(layers, start=1):
            raw_label = f"bedraw{index}"
            bed_label = f"bed{index}"
            filters.append(
                f"[{index}:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo,"
                f"volume={gain:.4f},afade=t=in:st=0:d=0.6[ {raw_label}]".replace("[ ", "[")
            )
            filters.append(
                f"[{raw_label}][speech_sc{index}]sidechaincompress="
                "threshold=0.025:ratio=7:attack=22:release=420:makeup=1"
                f"[{bed_label}]"
            )
            bed_labels.append(f"[{bed_label}]")

        effect_labels: list[str] = []
        effect_input_start = 1 + len(layers)
        for offset, (effect_path, delay, gain) in enumerate(effect_paths):
            input_index = effect_input_start + offset
            label = f"fx{offset + 1}"
            filters.append(
                f"[{input_index}:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo,"
                f"volume={gain:.4f},adelay={delay}|{delay}[{label}]"
            )
            effect_labels.append(f"[{label}]")

        labels = "[voice]" + "".join(bed_labels) + "".join(effect_labels)
        input_count = 1 + len(layers) + len(effect_paths)
        filters.append(
            f"{labels}amix=inputs={input_count}:duration=first:dropout_transition=0:"
            "normalize=0,alimiter=limit=0.93[out]"
        )
        _run_ffmpeg([
            *args, "-filter_complex", ";".join(filters), "-map", "[out]", "-vn",
            "-c:a", "pcm_s16le", "-ar", "44100", str(mixed_path),
        ])
        if not mixed_path.is_file() or mixed_path.stat().st_size < 1024:
            raise RuntimeError("The voice-plus-sound-design preview was not produced.")

        final_path = mixed_path
        if chapter_transition_sound and is_last_chapter:
            ending = selected_cue("ending", ending_cue_path)
            closed_path = temp / "preview-with-book-ending.wav"
            _join_audio(final_path, ending, closed_path)
            final_path = closed_path

        shutil.copy2(final_path, output_path)

    return output_path
