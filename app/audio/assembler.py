from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile

import imageio_ffmpeg

def ffmpeg_path() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()

def _run(args: list[str]) -> None:
    subprocess.run([ffmpeg_path(), "-y", *args], check=True, capture_output=True, text=True)

def sorted_chunks(chapter_dir: Path) -> list[Path]:
    return sorted((chapter_dir / "chunks").glob("*.wav"))

def assemble_chapter(chapter_dir: Path) -> Path:
    chunks = sorted_chunks(chapter_dir)
    if not chunks:
        raise ValueError(f"No audio chunks found for {chapter_dir.name}")
    output = chapter_dir / "chapter.m4a"
    concat_file = chapter_dir / "concat.txt"
    concat_file.write_text("\n".join(f"file '{p.as_posix().replace(chr(39), chr(39)+chr(39))}'" for p in chunks), encoding="utf-8")
    _run(["-f", "concat", "-safe", "0", "-i", str(concat_file), "-c:a", "aac", "-b:a", "128k", str(output)])
    return output

def _safe_title(value: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "_", value).strip() or "Audiobook"

def assemble_m4b(
    chapter_dirs: list[Path],
    output_path: Path,
    title: str,
    author: str = "",
    cover: Path | None = None,
) -> Path:
    chapters = [assemble_chapter(directory) for directory in chapter_dirs]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp:
        concat = Path(temp) / "chapters.txt"
        concat.write_text("\n".join(f"file '{p.as_posix().replace(chr(39), chr(39)+chr(39))}'" for p in chapters), encoding="utf-8")
        metadata = Path(temp) / "metadata.txt"
        lines = [";FFMETADATA1", f"title={title}", f"album={title}"]
        if author:
            lines.append(f"artist={author}")
        chapter_seconds = []
        for directory in chapter_dirs:
            chapter_file = directory / "chapter.m4a"
            probe = subprocess.run(
                [ffmpeg_path(), "-i", str(chapter_file)],
                capture_output=True, text=True,
            )
            match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe.stderr)
            if match:
                h, m, s = match.groups()
                chapter_seconds.append(int((int(h) * 3600 + int(m) * 60 + float(s)) * 1000))
            else:
                chapter_seconds.append(0)

        start = 0
        for index, directory in enumerate(chapter_dirs):
            duration = chapter_seconds[index]
            end = start + duration
            title_line = directory.name.split("_", 1)[1] if "_" in directory.name else directory.name
            lines.extend([f"[CHAPTER]", "TIMEBASE=1/1000", f"START={start}", f"END={end}", f"title={title_line}"])
            start = end
        metadata.write_text("\n".join(lines) + "\n", encoding="utf-8")

        args = ["-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(metadata)]
        if cover:
            args += ["-i", str(cover), "-map", "0:a", "-map", "2:v", "-c:v", "mjpeg", "-disposition:v:0", "attached_pic"]
        else:
            args += ["-map", "0:a"]
        args += ["-map_metadata", "1", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output_path)]
        _run(args)

    return output_path
