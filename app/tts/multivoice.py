from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile

import imageio_ffmpeg


def synthesize_voice_set(provider, text: str, voices, output: Path) -> Path:
    """Synthesize one chunk with one or several voices.

    A multi-speaker dialogue is rendered as a short voice blend so two or more
    characters can speak the same line together without duplicating the line in
    the audiobook timeline.
    """
    names = [str(voice) for voice in (voices or []) if str(voice).strip()]
    if not names:
        raise ValueError("No voice was supplied for multi-speaker synthesis.")
    if len(names) == 1:
        return provider.synthesize(text, output, names[0])

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ryu-multivoice-") as temp_dir:
        root = Path(temp_dir)
        inputs: list[Path] = []
        for index, voice in enumerate(names):
            path = root / f"voice-{index:02d}.wav"
            provider.synthesize(text, path, voice)
            if not path.exists() or path.stat().st_size < 1024:
                raise RuntimeError(f"Multi-speaker voice '{voice}' produced no usable audio.")
            inputs.append(path)

        args = [imageio_ffmpeg.get_ffmpeg_exe(), "-y"]
        for path in inputs:
            args.extend(["-i", str(path)])
        filters = (
            f"amix=inputs={len(inputs)}:duration=longest:dropout_transition=0:normalize=1,"
            "aformat=sample_fmts=s16:channel_layouts=mono"
        )
        args.extend([
            "-filter_complex", f"[{']['.join(f'{i}:a' for i in range(len(inputs)))}]{filters}",
            "-ar", "44100",
            "-c:a", "pcm_s16le",
            str(output),
        ])
        result = subprocess.run(args, capture_output=True, text=True, check=False)
        if result.returncode != 0 or not output.exists() or output.stat().st_size < 1024:
            detail = (result.stderr or result.stdout or "").strip()[-3000:]
            raise RuntimeError(f"Could not blend multiple character voices. {detail}")

    return output
