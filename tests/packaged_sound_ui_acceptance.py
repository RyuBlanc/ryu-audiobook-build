"""Launch the frozen Windows app and exercise its real Sound Design UI."""

from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid
import wave


def write_tone_fixture(path: Path, frequency_hz: float, duration_seconds: float = 12.0) -> None:
    """Create valid PCM WAV fixtures understood by both FFmpeg and Chromium."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 22050
    frames = bytearray()
    for index in range(int(sample_rate * duration_seconds)):
        sample = int(0.22 * 32767 * math.sin(2.0 * math.pi * frequency_hz * index / sample_rate))
        frames.extend(struct.pack("<h", sample))
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(frames)


def validate_saved_music_state(state_path: Path, expected_path: Path, expected_volume: float = 0.42) -> dict:
    """Verify the selected default and level reached the project's actual state file."""
    data = json.loads(Path(state_path).read_text(encoding="utf-8"))
    saved = str(data.get("background_audio_path") or "").strip()
    preferred = str(data.get("background_audio_preferred_path") or "").strip()
    expected = Path(expected_path).resolve()
    if not saved or Path(saved).resolve() != expected:
        raise AssertionError(f"Saved default mismatch: expected {expected}; got {saved!r}.")
    if preferred and Path(preferred).resolve() != expected:
        raise AssertionError(f"Preferred default mismatch: expected {expected}; got {preferred!r}.")
    volume = float(data.get("background_audio_volume", -1))
    if not math.isfinite(volume) or abs(volume - expected_volume) > 0.005:
        raise AssertionError(f"Saved BGM volume mismatch: expected {expected_volume}; got {volume!r}.")
    return data


def validate_imported_audio_metadata(music_paths: list[Path], cue_paths: list[Path]) -> None:
    """Verify imported Music and cue assets retain their distinct catalogue roles."""
    for path in music_paths:
        sidecar = path.with_name(path.name + ".license.json")
        if not path.is_file() or not sidecar.is_file():
            raise AssertionError(f"Imported music asset or metadata is missing: {path}")
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        if metadata.get("role") != "music" or metadata.get("category") != "fantasy":
            raise AssertionError(f"Imported music metadata mismatch for {path.name}: {metadata!r}")
    for path in cue_paths:
        sidecar = path.with_name(path.name + ".license.json")
        if not path.is_file() or not sidecar.is_file():
            raise AssertionError(f"Imported cue asset or metadata is missing: {path}")
        expected = {"role": "cue", "category": "universal"}
        if metadata := json.loads(sidecar.read_text(encoding="utf-8")):
            if metadata.get("role") != expected["role"] or metadata.get("category") != expected["category"]:
                raise AssertionError(f"Imported cue metadata mismatch for {path.name}: {metadata!r}")


def _run(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    from PySide6.QtCore import QSettings
    from app.chapters.detector import Chapter
    from app.core.paths import audio_library_root, library_root
    from app.core.project import Project
    from app.core.state import save_state

    exe = Path(args.exe).expanduser().resolve()
    script = Path(args.script).expanduser().resolve()
    if not exe.is_file():
        raise FileNotFoundError(f"Frozen Windows executable does not exist: {exe}")
    if not script.is_file():
        raise FileNotFoundError(f"Browser acceptance script does not exist: {script}")

    temp_root = Path(tempfile.mkdtemp(prefix="ryu-stage2-sound-ui-acceptance-"))
    token = uuid.uuid4().hex[:12].upper()
    alpha_title = f"RYU_ACCEPTANCE_{token}_ALPHA"
    beta_title = f"RYU_ACCEPTANCE_{token}_BETA"
    cue_alpha_title = f"RYU_ACCEPTANCE_{token}_CUE_ALPHA"
    cue_beta_title = f"RYU_ACCEPTANCE_{token}_CUE_BETA"
    alpha_source = temp_root / f"{alpha_title}.wav"
    beta_source = temp_root / f"{beta_title}.wav"
    cue_alpha_source = temp_root / f"{cue_alpha_title}.wav"
    cue_beta_source = temp_root / f"{cue_beta_title}.wav"
    write_tone_fixture(alpha_source, 440.0)
    write_tone_fixture(beta_source, 660.0)
    write_tone_fixture(cue_alpha_source, 880.0, duration_seconds=4.0)
    write_tone_fixture(cue_beta_source, 990.0, duration_seconds=4.0)

    audio_root = audio_library_root()
    music_imported_paths = [audio_root / alpha_source.name, audio_root / beta_source.name]
    cue_paths = [audio_root / cue_alpha_source.name, audio_root / cue_beta_source.name]
    imported_paths = music_imported_paths + cue_paths
    for path in imported_paths:
        if path.exists() or path.with_name(path.name + ".license.json").exists():
            raise FileExistsError(f"Unique acceptance fixture unexpectedly exists already: {path}")

    project_folder = library_root() / f"Stage 2 UI Acceptance {token}"
    Project(
        f"Stage 2 UI Acceptance {token}",
        project_folder,
        None,
        [
            Chapter(1, "Acceptance Chapter One", "A short test passage for the packaged Music Library acceptance."),
            Chapter(2, "Acceptance Chapter Two", "A second passage verifies that the project has real chapter context."),
        ],
    ).save()
    save_state(project_folder, {
        "status": "new",
        "background_audio_path": "",
        "background_audio_preferred_path": "",
        "background_audio_mode": "off",
        "background_audio_enabled": False,
        "background_audio_volume": 0.18,
        "chapter_bgm_strategy": "same",
    })

    settings = QSettings("RyuBlanc", "Ryu's Audiobook")
    previous_active = settings.value("project/active_folder", None)
    settings.setValue("project/active_folder", str(project_folder.resolve()))
    settings.sync()

    marker = temp_root / "acceptance-result.json"
    config = temp_root / "acceptance-fixtures.json"
    config.write_text(json.dumps({
        "music_paths": [str(alpha_source.resolve()), str(beta_source.resolve())],
        "track_titles": [alpha_title, beta_title],
        "cue_paths": [str(cue_alpha_source.resolve()), str(cue_beta_source.resolve())],
        "cue_track_titles": [cue_alpha_title, cue_beta_title],
        "expected_category": "fantasy",
        "expected_volume": 0.42,
    }, ensure_ascii=True, indent=2), encoding="utf-8")

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repo_root)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["RYU_SOUND_UI_ACCEPTANCE_SCRIPT"] = str(script)
    environment["RYU_SOUND_UI_ACCEPTANCE_CONFIG"] = str(config)
    environment["RYU_SOUND_UI_ACCEPTANCE_MARKER"] = str(marker)
    environment["RYU_SOUND_UI_ACCEPTANCE_TIMEOUT_SECONDS"] = "150"
    environment.pop("RYU_UI_MODE", None)
    environment.pop("RYU_STARTUP_SMOKE_MARKER", None)
    flags = environment.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    autoplay = "--autoplay-policy=no-user-gesture-required"
    if autoplay not in flags:
        flags = (flags + " " + autoplay).strip()
    environment["QTWEBENGINE_CHROMIUM_FLAGS"] = flags

    process = None
    try:
        print(f"Launching packaged Premium V2 executable: {exe}")
        print(f"Isolated acceptance project: {project_folder}")
        process = subprocess.Popen(
            [str(exe)], cwd=str(exe.parent), env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, errors="replace",
        )
        try:
            output, _ = process.communicate(timeout=190)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate(timeout=10)
            raise TimeoutError("Packaged Music Library acceptance exceeded 190 seconds. " + (output[-6000:] if output else ""))

        if not marker.is_file():
            raise RuntimeError(
                f"Packaged app exited {process.returncode} without an acceptance result marker. "
                + (output[-6000:] if output else "")
            )
        result = json.loads(marker.read_text(encoding="utf-8"))
        if result.get("status") != "passed":
            raise AssertionError(
                "Packaged UI acceptance failed: " + json.dumps(result, ensure_ascii=False)
                + ("\nApplication output:\n" + output[-6000:] if output else "")
            )
        if process.returncode != 0:
            raise RuntimeError(f"Packaged app returned exit code {process.returncode} after reporting success.")

        validate_saved_music_state(project_folder / "state.json", music_imported_paths[0], expected_volume=0.42)
        validate_imported_audio_metadata(music_imported_paths, cue_paths)

        print("PACKAGED SOUND DESIGN UI ACCEPTANCE PASSED")
        for name, detail in (result.get("checks") or {}).items():
            print(f"[PASS] {name}: {detail}")
        print("[PASS] The project state retained Alpha as default after Beta was selected.")
        print("[PASS] The project state retained the 42% BGM level.")
        print("[PASS] Both music fixtures retained Music role and Fantasy category metadata.")
        print("[PASS] Both cue fixtures retained Cue role and Universal category metadata.")
        return 0
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        if previous_active:
            settings.setValue("project/active_folder", previous_active)
        else:
            settings.remove("project/active_folder")
        settings.sync()
        for path in imported_paths:
            path.unlink(missing_ok=True)
            path.with_name(path.name + ".license.json").unlink(missing_ok=True)
        shutil.rmtree(project_folder, ignore_errors=True)
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True, help="Frozen Windows app executable.")
    parser.add_argument("--script", required=True, help="Browser-side acceptance script.")
    try:
        return _run(parser.parse_args())
    except Exception as exc:
        print(f"PACKAGED SOUND DESIGN UI ACCEPTANCE FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
