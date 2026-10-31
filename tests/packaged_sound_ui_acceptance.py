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
import winreg


_SETTINGS_PROJECT_KEY = r"Software\RyuBlanc\Ryu's Audiobook\project"
_ACTIVE_PROJECT_VALUE = "active_folder"


def get_active_project_setting() -> str | None:
    """Read the app's QSettings active-project value from its Windows registry key."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _SETTINGS_PROJECT_KEY, 0, winreg.KEY_QUERY_VALUE
        ) as key:
            value, _value_type = winreg.QueryValueEx(key, _ACTIVE_PROJECT_VALUE)
    except FileNotFoundError:
        return None
    return str(value).strip() or None


def set_active_project_setting(value: str | None) -> None:
    """Set/remove the same NativeFormat value read by QSettings in the desktop app."""
    if value:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, _SETTINGS_PROJECT_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, _ACTIVE_PROJECT_VALUE, 0, winreg.REG_SZ, str(value))
        return
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _SETTINGS_PROJECT_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            try:
                winreg.DeleteValue(key, _ACTIVE_PROJECT_VALUE)
            except FileNotFoundError:
                pass
    except FileNotFoundError:
        pass


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


def validate_saved_music_state(
    state_path: Path,
    expected_path: Path,
    expected_volume: float = 0.42,
    expected_narration_volume: float = 0.82,
    expected_cue_volume: float = 0.30,
    expected_chapter_paths: list[Path] | None = None,
    expected_cue_paths: list[Path] | None = None,
) -> dict:
    """Verify the complete persisted Stage 2 sound configuration after app restart."""
    data = json.loads(Path(state_path).read_text(encoding="utf-8"))
    expected = Path(expected_path).resolve()
    strategy = str(data.get("chapter_bgm_strategy") or "").strip().lower()
    if strategy not in {"custom", "chapter-based", "chapter_based", "chapter"}:
        raise AssertionError(f"Chapter-Based BGM strategy was not retained: {strategy!r}.")
    active = str(data.get("background_audio_path") or "").strip()
    preferred = str(data.get("background_audio_preferred_path") or "").strip()
    if active:
        raise AssertionError(f"Chapter-Based BGM retained an active book-default fallback: {active!r}.")
    if not preferred or Path(preferred).resolve() != expected:
        raise AssertionError(f"Book-default preference was not retained: expected {expected}; got {preferred!r}.")
    if data.get("background_audio_enabled") is not True or str(data.get("background_audio_mode") or "") != "manual":
        raise AssertionError("Use BGM state was not retained after Chapter-Based BGM was restored.")
    for key, expected_value in (
        ("background_audio_volume", expected_volume),
        ("narration_audio_volume", expected_narration_volume),
        ("sound_cue_volume", expected_cue_volume),
    ):
        value = float(data.get(key, -1))
        if not math.isfinite(value) or abs(value - expected_value) > 0.005:
            raise AssertionError(f"Saved {key} mismatch: expected {expected_value}; got {value!r}.")

    overrides = data.get("chapter_bgm_overrides")
    if not isinstance(overrides, dict):
        raise AssertionError("Chapter BGM overrides were not saved as a mapping.")
    tracks = expected_chapter_paths or []
    if len(tracks) >= 2:
        first = overrides.get("1") or {}
        second = overrides.get("2") or {}
        third = overrides.get("3") or {}
        expected_first = Path(tracks[0]).resolve()
        expected_second = Path(tracks[1]).resolve()
        if first.get("rule") != "custom" or Path(str(first.get("path") or "")).resolve() != expected_first:
            raise AssertionError(f"Chapter One track assignment was not retained: {first!r}.")
        if abs(float(first.get("volume", -1)) - 0.37) > 0.005 or first.get("start_offset") != "after_first_paragraph" or first.get("end_behavior") != "continue_to_transition":
            raise AssertionError(f"Chapter One level/timing/end policy was not retained: {first!r}.")
        if second.get("rule") != "custom" or Path(str(second.get("path") or "")).resolve() != expected_second:
            raise AssertionError(f"Chapter Two track assignment was not retained: {second!r}.")
        if abs(float(second.get("volume", -1)) - 0.29) > 0.005 or second.get("start_offset") != "after_10_seconds" or second.get("end_behavior") != "stop_immediately":
            raise AssertionError(f"Chapter Two level/timing/end policy was not retained: {second!r}.")
        if third.get("rule") != "none":
            raise AssertionError(f"Chapter Three's explicit No BGM rule was not retained: {third!r}.")

    cues = data.get("sound_cues")
    if not isinstance(cues, dict):
        raise AssertionError("The saved three-slot cue configuration is missing.")
    if expected_cue_paths and len(expected_cue_paths) == 2:
        expected_slots = {
            "opening": Path(expected_cue_paths[1]).resolve(),
            "chapter": Path(expected_cue_paths[1]).resolve(),
            "closing": Path(expected_cue_paths[0]).resolve(),
        }
        for slot, wanted in expected_slots.items():
            actual = str(cues.get(slot) or "").strip()
            if not actual or Path(actual).resolve() != wanted:
                raise AssertionError(f"Saved {slot} cue mismatch: expected {wanted}; got {actual!r}.")
    return data


def validate_imported_audio_metadata(
    music_paths: list[Path],
    cue_paths: list[Path],
    expected_categories: dict[str, str] | None = None,
) -> None:
    """Verify every imported Music and cue fixture retains its real catalogue role/category."""
    expected_categories = expected_categories or {}
    for path in music_paths:
        sidecar = path.with_name(path.name + ".license.json")
        if not path.is_file() or not sidecar.is_file():
            raise AssertionError(f"Imported music asset or metadata is missing: {path}")
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        expected_category = expected_categories.get(str(path), "fantasy")
        if metadata.get("role") != "music" or metadata.get("category") != expected_category:
            raise AssertionError(
                f"Imported music metadata mismatch for {path.name}: expected {expected_category!r}; got {metadata!r}"
            )
    for path in cue_paths:
        sidecar = path.with_name(path.name + ".license.json")
        if not path.is_file() or not sidecar.is_file():
            raise AssertionError(f"Imported cue asset or metadata is missing: {path}")
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        expected_cue_metadata = {"role": "cue", "category": "universal"}
        if any(metadata.get(key) != value for key, value in expected_cue_metadata.items()):
            raise AssertionError(f"Imported cue metadata mismatch for {path.name}: {metadata!r}")


def _run(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]

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
    long_cue_source = temp_root / f"RYU_ACCEPTANCE_{token}_CUE_TOO_LONG.wav"
    write_tone_fixture(alpha_source, 440.0)
    write_tone_fixture(beta_source, 660.0)
    write_tone_fixture(cue_alpha_source, 880.0, duration_seconds=4.0)
    write_tone_fixture(cue_beta_source, 990.0, duration_seconds=4.0)
    write_tone_fixture(long_cue_source, 1110.0, duration_seconds=6.0)

    category_specs = [
        ("action", "battle-warfare", 550.0),
        ("mystery", "mystery", 600.0),
        ("horror", "horror", 650.0),
        ("romance", "romance", 700.0),
        ("sci-fi", "sci-fi", 750.0),
        ("calm", "calm-narration", 800.0),
        ("emotional", "others", 850.0),
    ]
    category_sources = []
    for category, filter_name, frequency in category_specs:
        title = f"RYU_ACCEPTANCE_{token}_{category.upper().replace('-', '_')}"
        source = temp_root / f"{title}.wav"
        write_tone_fixture(source, frequency, duration_seconds=4.0)
        category_sources.append({
            "category": category, "filter": filter_name, "title": title, "source": source,
        })

    # Keep test fixtures inside the app's default user-data layout. This
    # hosted Windows profile is clean and has no user-selected storage roots.
    app_root = Path.home() / "Ryu's Audiobook"
    audio_root = app_root / "Audio Library"
    audio_root.mkdir(parents=True, exist_ok=True)
    music_imported_paths = [audio_root / alpha_source.name, audio_root / beta_source.name]
    category_imported_paths = [audio_root / item["source"].name for item in category_sources]
    cue_paths = [audio_root / cue_alpha_source.name, audio_root / cue_beta_source.name]
    imported_paths = music_imported_paths + category_imported_paths + cue_paths
    for path in imported_paths:
        if path.exists() or path.with_name(path.name + ".license.json").exists():
            raise FileExistsError(f"Unique acceptance fixture unexpectedly exists already: {path}")

    project_folder = app_root / "Library" / f"Stage 2 UI Acceptance {token}"
    project_folder.mkdir(parents=True, exist_ok=False)
    project_title = f"Stage 2 UI Acceptance {token}"
    chapter_rows = [
        {
            "number": 1, "title": "Acceptance Chapter One",
            "text": "First paragraph for the opening chapter.\n\nSecond paragraph verifies the saved paragraph boundary.",
            "dialogue_assignments": [], "review_status": "needs_review", "skip_for_generation": False,
        },
        {
            "number": 2, "title": "Acceptance Chapter Two",
            "text": "First paragraph for the middle chapter.\n\nSecond paragraph verifies the ten-second start policy.",
            "dialogue_assignments": [], "review_status": "needs_review", "skip_for_generation": False,
        },
        {
            "number": 3, "title": "Acceptance Chapter Three",
            "text": "This chapter explicitly remains narration only.",
            "dialogue_assignments": [], "review_status": "needs_review", "skip_for_generation": False,
        },
    ]
    (project_folder / "project.json").write_text(json.dumps({
        "title": project_title, "source_file": None,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (project_folder / "chapters.json").write_text(json.dumps(chapter_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (project_folder / "state.json").write_text(json.dumps({
        "status": "new", "background_audio_path": "", "background_audio_preferred_path": "",
        "background_audio_mode": "off", "background_audio_enabled": False,
        "background_audio_volume": 0.18, "narration_audio_volume": 1.0, "sound_cue_volume": 0.25,
        "chapter_bgm_strategy": "same", "chapter_bgm_overrides": {},
        "sound_cues": {"opening": None, "chapter": None, "closing": None},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # Full-book preview uses the production mixer over existing saved narration;
    # these valid paragraph-aligned PCM chunks let the frozen app exercise that
    # same code path without invoking an unrelated TTS provider/model download.
    for chapter in chapter_rows:
        number = int(chapter["number"])
        chapter_dir = project_folder / "working_audio" / f"{number:03d}_Acceptance Chapter {number}"
        chunks_dir = chapter_dir / "chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)
        first_chunk = "0001.wav"
        second_chunk = "0002.wav"
        write_tone_fixture(chunks_dir / first_chunk, 320.0 + number * 30.0, duration_seconds=6.0)
        write_tone_fixture(chunks_dir / second_chunk, 360.0 + number * 30.0, duration_seconds=6.0)
        (chapter_dir / "narration.json").write_text(json.dumps({
            "chapter": number, "title": chapter["title"], "narration_text": chapter["text"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        (chapter_dir / "chunk_manifest.json").write_text(json.dumps({
            "chunks": [
                {"file": first_chunk, "text": chapter["text"].split("\n\n", 1)[0] + "\n\n"},
                {"file": second_chunk, "text": chapter["text"].split("\n\n", 1)[-1]},
            ],
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    secondary_project_folder = app_root / "Library" / f"Stage 2 UI Secondary {token}"
    secondary_project_folder.mkdir(parents=True, exist_ok=False)
    (secondary_project_folder / "project.json").write_text(json.dumps({
        "title": f"Stage 2 UI Secondary {token}", "source_file": None,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (secondary_project_folder / "chapters.json").write_text(json.dumps([{
        "number": 1, "title": "Secondary Acceptance Chapter",
        "text": "A separate book for project-switch persistence validation.",
        "dialogue_assignments": [], "review_status": "needs_review", "skip_for_generation": False,
    }], ensure_ascii=False, indent=2), encoding="utf-8")
    (secondary_project_folder / "state.json").write_text(json.dumps({
        "status": "new", "background_audio_path": "", "background_audio_preferred_path": "",
        "background_audio_mode": "off", "background_audio_enabled": False,
        "background_audio_volume": 0.18, "chapter_bgm_strategy": "same",
        "chapter_bgm_overrides": {}, "sound_cues": {"opening": None, "chapter": None, "closing": None},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    previous_active = get_active_project_setting()
    set_active_project_setting(str(project_folder.resolve()))

    marker = temp_root / "acceptance-result.json"
    config = temp_root / "acceptance-fixtures.json"
    category_imports = [
        {
            "category": item["category"],
            "filter": item["filter"],
            "title": item["title"],
            # The import action must receive the real temporary WAV source.
            # "path" is the native Audio Library destination for assertions.
            "source_path": str(item["source"].resolve()),
            "path": str((audio_root / item["source"].name).resolve()),
        }
        for item in category_sources
    ]
    music_category_map = {
        str(music_imported_paths[0]): "fantasy",
        str(music_imported_paths[1]): "fantasy",
        **{item["path"]: item["category"] for item in category_imports},
    }
    config.write_text(json.dumps({
        "music_paths": [str(alpha_source.resolve()), str(beta_source.resolve())],
        "track_titles": [alpha_title, beta_title],
        "track_paths": [str(music_imported_paths[0].resolve()), str(music_imported_paths[1].resolve())],
        "category_imports": category_imports,
        "music_categories": music_category_map,
        "cue_paths": [str(cue_alpha_source.resolve()), str(cue_beta_source.resolve())],
        "cue_track_titles": [cue_alpha_title, cue_beta_title],
        "long_cue_path": str(long_cue_source.resolve()),
        "cue_alpha_title": cue_alpha_title, "cue_beta_title": cue_beta_title,
        "expected_category": "fantasy", "expected_volume": 0.42,
        "project_folder": str(project_folder.resolve()),
        "secondary_project_folder": str(secondary_project_folder.resolve()),
    }, ensure_ascii=True, indent=2), encoding="utf-8")

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repo_root)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["RYU_SOUND_UI_ACCEPTANCE_SCRIPT"] = str(script)
    environment["RYU_SOUND_UI_ACCEPTANCE_CONFIG"] = str(config)
    environment["RYU_SOUND_UI_ACCEPTANCE_MARKER"] = str(marker)
    environment["RYU_SOUND_UI_ACCEPTANCE_TIMEOUT_SECONDS"] = "840"
    environment.pop("RYU_UI_MODE", None)
    environment.pop("RYU_STARTUP_SMOKE_MARKER", None)
    flags = environment.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    autoplay = "--autoplay-policy=no-user-gesture-required"
    if autoplay not in flags:
        flags = (flags + " " + autoplay).strip()
    environment["QTWEBENGINE_CHROMIUM_FLAGS"] = flags

    process = None
    try:
        def launch_acceptance(label: str, selected_environment: dict[str, str]) -> tuple[subprocess.Popen, str]:
            print(f"Launching packaged Premium V2 executable ({label}): {exe}")
            process = subprocess.Popen(
                [str(exe)], cwd=str(exe.parent), env=selected_environment,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, errors="replace",
            )
            try:
                output, _ = process.communicate(timeout=900)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate(timeout=10)
                raise TimeoutError(f"Packaged Stage 2 {label} acceptance exceeded 900 seconds. " + (output[-6000:] if output else ""))
            return process, output

        print(f"Isolated three-chapter acceptance project: {project_folder}")
        process, output = launch_acceptance("full workflow", environment)
        if not marker.is_file():
            raise RuntimeError(
                f"Packaged app exited {process.returncode} without an acceptance result marker. "
                + (output[-6000:] if output else "")
            )
        first_result = json.loads(marker.read_text(encoding="utf-8"))
        if first_result.get("status") != "passed":
            raise AssertionError(
                "Packaged Stage 2 UI acceptance failed: " + json.dumps(first_result, ensure_ascii=False)
                + ("\nApplication output:\n" + output[-6000:] if output else "")
            )
        if process.returncode != 0:
            raise RuntimeError(f"Packaged app returned exit code {process.returncode} after reporting success.")

        # The UI project-switch sequence must have returned to the primary book;
        # do not repair the registry here, because the second launch must prove the
        # actual app-selected active project survives its process restart.
        active_after_switch = get_active_project_setting()
        if not active_after_switch or Path(active_after_switch).resolve() != project_folder.resolve():
            raise AssertionError(
                f"The app did not leave the primary acceptance project active before restart: {active_after_switch!r}"
            )
        validate_saved_music_state(
            project_folder / "state.json", music_imported_paths[0],
            expected_volume=0.42, expected_narration_volume=0.82, expected_cue_volume=0.30,
            expected_chapter_paths=music_imported_paths,
            expected_cue_paths=cue_paths,
        )
        validate_imported_audio_metadata(music_imported_paths + category_imported_paths, cue_paths, music_category_map)

        # Relaunch the same frozen executable with a read-only restart phase.
        # This is the persistence acceptance, not an in-process refresh.
        restart_marker = temp_root / "acceptance-restart-result.json"
        config_data = json.loads(config.read_text(encoding="utf-8"))
        config_data["phase"] = "restart"
        config.write_text(json.dumps(config_data, ensure_ascii=True, indent=2), encoding="utf-8")
        restart_environment = environment.copy()
        restart_environment["RYU_SOUND_UI_ACCEPTANCE_MARKER"] = str(restart_marker)
        process, restart_output = launch_acceptance("restart persistence", restart_environment)
        if not restart_marker.is_file():
            raise RuntimeError(
                f"Restarted packaged app exited {process.returncode} without an acceptance result marker. "
                + (restart_output[-6000:] if restart_output else "")
            )
        restart_result = json.loads(restart_marker.read_text(encoding="utf-8"))
        if restart_result.get("status") != "passed":
            raise AssertionError(
                "Packaged Stage 2 restart acceptance failed: " + json.dumps(restart_result, ensure_ascii=False)
                + ("\nApplication output:\n" + restart_output[-6000:] if restart_output else "")
            )
        if process.returncode != 0:
            raise RuntimeError(f"Restarted packaged app returned exit code {process.returncode} after reporting success.")

        combined_checks = dict(first_result.get("checks") or {})
        combined_checks.update(restart_result.get("checks") or {})
        print("PACKAGED STAGE 2 SOUND DESIGN ACCEPTANCE PASSED")
        for name, detail in combined_checks.items():
            print(f"[PASS] {name}: {detail}")
        print("[PASS] State JSON retained Chapter-Based strategy, restored book-default preference, chapter tracks/rules, timing, and per-chapter levels.")
        print("[PASS] State JSON retained BGM/narration/cue mix levels and all three fixed cue assignments.")
        print("[PASS] Global Music Library files and category metadata survived a real frozen-app process restart.")
        return 0
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        set_active_project_setting(previous_active)
        for path in imported_paths:
            path.unlink(missing_ok=True)
            path.with_name(path.name + ".license.json").unlink(missing_ok=True)
        shutil.rmtree(project_folder, ignore_errors=True)
        shutil.rmtree(secondary_project_folder, ignore_errors=True)
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
