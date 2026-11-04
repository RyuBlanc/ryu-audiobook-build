from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import time
import uuid


def is_iso_bmff_file(path: Path) -> bool:
    """Return whether a finished file has the ISO Base Media File Format signature."""
    candidate = Path(path)
    try:
        if not candidate.is_file() or candidate.stat().st_size < 16:
            return False
        with candidate.open("rb") as stream:
            stream.seek(4)
            return stream.read(4) == b"ftyp"
    except OSError:
        return False


def prepare_audiobook_playback_source(
    source_path: Path,
    *,
    cache_root: Path | None = None,
) -> Path:
    """Create/reuse a compact browser-compatible MP3 copy of a validated M4B.

    Qt WebEngine packages may omit Chromium's AAC decoder. Keep the original
    chaptered AAC M4B as the authoritative library/download file and prepare a
    cached MP3 solely for HTMLAudioElement playback. Chapter markers are always
    read from the original M4B by the player bridge.
    """
    from app.audio.assembler import _duration_ms, ffmpeg_path

    source = Path(source_path).expanduser().resolve()
    if not source.is_file() or source.stat().st_size <= 0:
        raise FileNotFoundError(f"Finished audiobook output is not available: {source}")
    if source.suffix.casefold() in {".mp3", ".wav", ".ogg"}:
        return source
    if source.suffix.casefold() not in {".m4b", ".m4a"} or not is_iso_bmff_file(source):
        raise ValueError("Audiobooks playback requires a valid MP4/M4B source with an audio stream.")

    stat = source.stat()
    identity = f"{source}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()[:24]
    if cache_root is None:
        from app.core.paths import app_root
        cache = app_root() / "Previews" / "AudiobookPlayback"
    else:
        cache = Path(cache_root).expanduser()
    cache.mkdir(parents=True, exist_ok=True)
    destination = cache / f"audiobook_playback_{digest}.mp3"

    if destination.is_file() and destination.stat().st_size > 1024:
        try:
            if abs(_duration_ms(destination) - _duration_ms(source)) <= 1500:
                try:
                    destination.touch()
                except OSError:
                    pass
                return destination.resolve()
        except (OSError, RuntimeError, ValueError):
            destination.unlink(missing_ok=True)

    temporary = cache / f".audiobook_playback_{digest}.{uuid.uuid4().hex}.mp3"
    try:
        encode = subprocess.run(
            [
                ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(source), "-map", "0:a:0", "-vn", "-sn", "-dn",
                "-map_metadata", "-1",
                "-c:a", "libmp3lame", "-b:a", "160k",
                "-ar", "44100", "-ac", "2",
                str(temporary),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=7200,
            check=False,
        )
        if encode.returncode != 0:
            detail = (encode.stderr or encode.stdout or "").strip()[-3000:]
            raise RuntimeError("FFmpeg could not prepare browser-compatible audiobook playback. " + detail)
        if not temporary.is_file() or temporary.stat().st_size <= 1024:
            raise RuntimeError("FFmpeg produced an empty audiobook playback copy.")

        source_duration = _duration_ms(source)
        playback_duration = _duration_ms(temporary)
        if abs(playback_duration - source_duration) > 1500:
            raise RuntimeError(
                "The browser-compatible playback copy duration does not match the source M4B. "
                f"Source={source_duration}ms; playback={playback_duration}ms."
            )

        decode = subprocess.run(
            [
                ffmpeg_path(), "-hide_banner", "-loglevel", "error",
                "-i", str(temporary), "-map", "0:a:0", "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=7200,
            check=False,
        )
        if decode.returncode != 0:
            detail = (decode.stderr or decode.stdout or "").strip()[-3000:]
            raise RuntimeError("The browser-compatible audiobook playback copy failed full audio decode. " + detail)

        temporary.replace(destination)
        return destination.resolve()
    finally:
        temporary.unlink(missing_ok=True)
