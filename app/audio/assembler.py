from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile

import imageio_ffmpeg


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


def assemble_chapter(chapter_dir: Path) -> Path:
    chunks = sorted_chunks(chapter_dir)
    if not chunks:
        raise ValueError(f"No audio chunks found for {chapter_dir.name}")
    output = chapter_dir / "chapter.m4a"
    concat_file = chapter_dir / "concat.txt"
    concat_file.write_text(
        "ffconcat version 1.0\n"
        + "\n".join(f"file '{_ffconcat_path(p)}'" for p in chunks)
        + "\n",
        encoding="utf-8",
    )
    _run([
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-vn", "-c:a", "aac", "-b:a", "64k", "-ar", "44100", str(output),
    ])
    if not output.exists() or output.stat().st_size < 1024:
        raise RuntimeError(f"Chapter audio was not created: {output}")
    return output


def _metadata_value(value: str) -> str:
    return (
        str(value).replace("\\", "\\\\").replace(";", "\\;")
        .replace("#", "\\#").replace("=", "\\=")
        .replace("\n", " ").replace("\r", " ")
    )


def _safe_title(value: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "_", value).strip() or "Audiobook"


def _duration_ms(path: Path) -> int:
    probe = subprocess.run([ffmpeg_path(), "-i", str(path)], capture_output=True, text=True)
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", probe.stderr)
    if not match:
        raise RuntimeError(f"Could not determine duration of {path.name}")
    hours, minutes, seconds = match.groups()
    return int((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)


def assemble_m4b(
    chapter_dirs: list[Path],
    output_path: Path,
    title: str,
    author: str = "",
    cover: Path | None = None,
    chapter_titles: list[str] | None = None,
) -> Path:
    """Create one M4B containing all chapters, navigation markers, metadata and cover."""
    if not chapter_dirs:
        raise ValueError("No chapters were supplied.")

    chapters = [assemble_chapter(directory) for directory in chapter_dirs]
    names = chapter_titles or [
        directory.name.split("_", 1)[1] if "_" in directory.name else directory.name
        for directory in chapter_dirs
    ]
    if len(names) != len(chapters):
        raise ValueError("Chapter title count does not match chapter audio count.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path = output_path.with_suffix(".m4b")

    with tempfile.TemporaryDirectory(prefix="ryu-m4b-") as temp:
        temp_dir = Path(temp)

        # Give the concat demuxer explicit durations. This avoids the
        # "Duration: N/A" timing ambiguity seen with some generated M4A files.
        concat = temp_dir / "chapters.txt"
        concat_lines = ["ffconcat version 1.0"]
        durations: list[int] = []
        for chapter_file in chapters:
            duration = _duration_ms(chapter_file)
            durations.append(duration)
            concat_lines.append(f"file '{_ffconcat_path(chapter_file)}'")
            concat_lines.append(f"duration {duration / 1000.0:.6f}")
        concat.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

        metadata = temp_dir / "metadata.txt"
        lines = [
            ";FFMETADATA1",
            f"title={_metadata_value(_safe_title(title))}",
            f"album={_metadata_value(_safe_title(title))}",
            "genre=Audiobook",
            "comment=Created by Ryu's Audiobook",
        ]
        if author:
            lines.append(f"artist={_metadata_value(author)}")

        start = 0
        for duration, chapter_title in zip(durations, names):
            end = start + duration
            lines.extend([
                "[CHAPTER]", "TIMEBASE=1/1000",
                f"START={start}", f"END={end}",
                f"title={_metadata_value(chapter_title)}",
            ])
            start = end
        metadata.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # First make one stable AAC audio stream. Then mux metadata/chapters
        # and cover in a separate pass. Keeping concat and MP4 chapter/cover
        # muxing separate makes failures much easier to diagnose and avoids
        # fragile multi-input timestamp interactions.
        audio_only = temp_dir / "audiobook-audio.m4a"
        _run([
            "-f", "concat", "-safe", "0", "-i", str(concat),
            "-vn", "-c:a", "aac", "-b:a", "96k", "-ar", "44100",
            str(audio_only),
        ])
        if not audio_only.exists() or audio_only.stat().st_size < 4096:
            raise RuntimeError("FFmpeg created no usable intermediate audiobook audio.")

        args = [
            "-i", str(audio_only),
            "-f", "ffmetadata", "-i", str(metadata),
            "-map", "0:a:0",
            "-map_metadata", "1",
            "-map_chapters", "1",
            "-c:a", "copy",
            "-movflags", "+faststart",
        ]
        if cover:
            args += [
                "-i", str(cover), "-map", "2:v:0",
                "-c:v", "mjpeg",
                "-disposition:v:0", "attached_pic",
                "-metadata:s:v:0", "title=Cover",
                "-metadata:s:v:0", "comment=Cover Art",
                "-metadata:s:v:0", "mimetype=image/jpeg",
                "-metadata:s:v:0", "filename=cover.jpg",
            ]
        args += [
            "-metadata", f"title={_safe_title(title)}",
            "-metadata", f"album={_safe_title(title)}",
        ]
        if author:
            args += ["-metadata", f"artist={author}"]
        args.append(str(output_path))
        _run(args)

    if not output_path.exists() or output_path.stat().st_size < 4096:
        raise RuntimeError("FFmpeg completed but the final M4B is missing or invalid.")
    return output_path
