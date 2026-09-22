from __future__ import annotations

from pathlib import Path
import subprocess

import imageio_ffmpeg

def audio_duration(path: Path) -> float:
    result = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(path)],
        capture_output=True, text=True,
    )
    import re
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
    if not match:
        raise ValueError(f"Could not read audio duration: {path}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

def validate_audio_file(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        return audio_duration(path) > 0
    except (OSError, ValueError):
        return False
