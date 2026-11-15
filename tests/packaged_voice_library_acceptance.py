"""Exercise Qwen Voice Library export/import in the frozen Windows application."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import traceback
import uuid
import wave
import zipfile


APP_HOME_NAME = "Ryu's Audiobook"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_wav(path: Path, frequency: int) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = 4800
    # A valid, deterministic 16-bit mono PCM WAV; different fixtures remain distinct.
    sample = int(max(-32767, min(32767, frequency * 17))).to_bytes(2, "little", signed=True)
    frames = sample * frame_count
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(frames)
    return path.read_bytes()


def _build_profiles(source_root: Path, token: str):
    from app.tts.voice_profile import VoiceProfile

    custom06 = VoiceProfile(
        name=f"D5 CustomVoice 0.6B {token}",
        provider="qwen-character",
        voice_id="Ono_Anna",
        model_id="custom-0.6b",
        backend="automatic",
        language="Japanese",
        notes="Packaged Stage D5 CustomVoice 0.6B fidelity fixture.",
        authorized=False,
        exaggeration=0.51,
        cfg_weight=0.31,
        style_preset="Natural",
        qwen_mode="custom",
        qwen_prompt="A calm, precise Japanese audiobook voice.",
        qwen_seed=1709,
        qwen_profile_id=f"d5-custom06-{token}",
    )
    custom17 = VoiceProfile(
        name=f"D5 CustomVoice 1.7B {token}",
        provider="qwen-character",
        voice_id="Serena",
        model_id="custom-1.7b",
        backend="automatic",
        language="Chinese",
        notes="Packaged Stage D5 CustomVoice 1.7B fidelity fixture.",
        authorized=False,
        exaggeration=0.64,
        cfg_weight=0.27,
        style_preset="Expressive",
        qwen_mode="custom",
        qwen_prompt="A warm, clear Chinese audiobook voice.",
        qwen_seed=1409,
        qwen_profile_id=f"d5-custom17-{token}",
        extra_fields={"d5_acceptance_extension": f"preserve-{token}"},
    )

    design_anchor = source_root / "design-anchor.wav"
    _write_wav(design_anchor, 730)
    design = VoiceProfile(
        name=f"D5 VoiceDesign {token}",
        provider="qwen-character",
        voice_id=f"D5-Design-{token}",
        model_id="design-1.7b",
        backend="automatic",
        language="Japanese",
        notes="Packaged Stage D5 explicit VoiceDesign anchor fixture.",
        authorized=False,
        exaggeration=0.72,
        cfg_weight=0.22,
        style_preset="Expressive",
        qwen_mode="design",
        qwen_prompt="A naturally expressive Japanese narrator with a warm mid-range tone.",
        qwen_seed=9021,
        qwen_anchor_path=str(design_anchor),
        qwen_anchor_text="これは保存された日本語の音声アンカーです。",
        qwen_profile_id=f"d5-design-{token}",
    )

    clone_dir = source_root / "clone-source"
    clone_reference = clone_dir / "reference.wav"
    clone_sidecar = clone_dir / "original-recording.wav"
    _write_wav(clone_reference, 910)
    _write_wav(clone_sidecar, 1110)
    clone = VoiceProfile(
        name=f"D5 VoiceClone {token}",
        provider="qwen-character",
        voice_id=f"D5-Clone-{token}",
        model_id="base-1.7b",
        backend="automatic",
        language="English",
        notes="Packaged Stage D5 Clone identity and reference fixture.",
        authorized=False,
        exaggeration=0.48,
        cfg_weight=0.35,
        style_preset="Natural",
        qwen_mode="clone",
        qwen_prompt="Preserve the supplied reference identity.",
        qwen_seed=811,
        sample_path=str(clone_reference),
        reference_text="This is the exact reference transcript for the D5 Clone transfer test.",
        qwen_profile_id=f"d5-clone-{token}",
    )

    profiles = [custom06, custom17, design, clone]
    source_assets = {
        str(design_anchor): _sha256(design_anchor),
        str(clone_reference): _sha256(clone_reference),
        str(clone_sidecar): _sha256(clone_sidecar),
    }
    return profiles, source_assets


def _environment_for_app(home: Path, repo_root: Path, script: Path, config: Path, marker: Path, acceptance_root: Path):
    environment = os.environ.copy()
    home.mkdir(parents=True, exist_ok=True)
    (home / "AppData" / "Roaming").mkdir(parents=True, exist_ok=True)
    (home / "AppData" / "Local").mkdir(parents=True, exist_ok=True)
    environment.update({
        "USERPROFILE": str(home),
        "HOME": str(home),
        "APPDATA": str(home / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "PYTHONPATH": str(repo_root),
        "PYTHONDONTWRITEBYTECODE": "1",
        "RYU_VOICE_LIBRARY_ACCEPTANCE_ROOT": str(acceptance_root),
        "RYU_SOUND_UI_ACCEPTANCE_SCRIPT": str(script),
        "RYU_SOUND_UI_ACCEPTANCE_CONFIG": str(config),
        "RYU_SOUND_UI_ACCEPTANCE_MARKER": str(marker),
        "RYU_SOUND_UI_ACCEPTANCE_TIMEOUT_SECONDS": "360",
    })
    environment.pop("RYU_UI_MODE", None)
    environment.pop("RYU_STARTUP_SMOKE_MARKER", None)
    environment.pop("RYU_FROZEN_SELF_TEST_MARKER", None)
    flags = environment.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    autoplay = "--autoplay-policy=no-user-gesture-required"
    if autoplay not in flags:
        flags = (flags + " " + autoplay).strip()
    environment["QTWEBENGINE_CHROMIUM_FLAGS"] = flags
    return environment


def _run_phase(
    *,
    phase: str,
    exe: Path,
    script: Path,
    output_dir: Path,
    acceptance_root: Path,
    home: Path,
    repo_root: Path,
    common_config: dict,
    timeout_seconds: int = 480,
) -> dict:
    config_path = output_dir.parent / f"voice-library-{phase}-config.json"
    marker_path = output_dir.parent / f"voice-library-{phase}-result.json"
    config = dict(common_config)
    config["phase"] = phase
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    marker_path.unlink(missing_ok=True)
    environment = _environment_for_app(
        home, repo_root, script, config_path, marker_path, acceptance_root
    )

    process = subprocess.Popen(
        [str(exe)],
        cwd=str(exe.parent),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        output, _ = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        output, _ = process.communicate(timeout=15)
        raise TimeoutError(
            f"Packaged Stage D5 {phase} phase exceeded {timeout_seconds} seconds.\n"
            + (output[-10000:] if output else "")
        )

    if not marker_path.is_file():
        raise RuntimeError(
            f"Packaged Stage D5 {phase} phase exited {process.returncode} without a result marker.\n"
            + (output[-10000:] if output else "")
        )
    result = json.loads(marker_path.read_text(encoding="utf-8"))
    if result.get("status") != "passed" or process.returncode != 0:
        raise AssertionError(
            f"Packaged Stage D5 {phase} phase failed: {json.dumps(result, ensure_ascii=False)}\n"
            + (output[-10000:] if output else "")
        )
    return {
        "phase": phase,
        "process_exit_code": process.returncode,
        "checks": result.get("checks") or {},
        "log_tail": output[-3000:] if output else "",
    }


def _validate_imported_records(profiles, manifest_profiles, source_assets, voices_root: Path):
    catalogue = voices_root / "voices.json"
    if not catalogue.is_file():
        raise AssertionError("The packaged transactional import did not create voices.json.")
    records = json.loads(catalogue.read_text(encoding="utf-8"))
    by_id = {
        str(record.get("qwen_profile_id") or ""): record
        for record in records if isinstance(record, dict)
    }
    verified_assets = []
    manifest_by_id = {
        str(entry.get("profile_id") or ""): entry for entry in manifest_profiles
    }
    fields = (
        "name", "provider", "voice_id", "model_id", "backend", "language",
        "notes", "authorized", "exaggeration", "cfg_weight", "style_preset",
        "qwen_mode", "qwen_prompt", "qwen_seed", "reference_text",
        "qwen_anchor_text",
    )

    for profile in profiles:
        profile_id = str(profile.qwen_profile_id)
        record = by_id.get(profile_id)
        if record is None:
            raise AssertionError(f"Stable Qwen profile ID was not present after import: {profile_id}")
        for field in fields:
            expected = getattr(profile, field)
            if record.get(field) != expected:
                raise AssertionError(
                    f"Imported {field} changed for {profile_id}: expected {expected!r}, got {record.get(field)!r}"
                )
        if profile.extra_fields:
            for key, value in profile.extra_fields.items():
                if record.get(key) != value:
                    raise AssertionError(f"Imported extension field {key!r} was not preserved for {profile_id}.")

        manifest_entry = manifest_by_id.get(profile_id)
        if manifest_entry is None:
            raise AssertionError(f"Exported manifest is missing profile {profile_id}.")
        for asset in manifest_entry.get("assets", []):
            binding = str(asset.get("binding") or "")
            if binding == "sample_path":
                source_asset = Path(str(profile.sample_path or ""))
            elif binding == "qwen_anchor_path":
                source_asset = Path(str(profile.qwen_anchor_path or ""))
            elif binding == "clone-reference-original-sidecar":
                source_asset = Path(str(profile.sample_path or "")).parent / str(asset.get("source_filename") or "")
            else:
                raise AssertionError(f"Unexpected D5 packaged asset binding: {binding!r}")
            source_digest = source_assets.get(str(source_asset))
            if source_digest is None or str(asset.get("sha256") or "") != source_digest:
                raise AssertionError(
                    f"Exported manifest asset hash does not match its original source bytes: {source_asset}"
                )
            if binding == "sample_path":
                destination = Path(str(record.get("sample_path") or ""))
            elif binding == "qwen_anchor_path":
                destination = Path(str(record.get("qwen_anchor_path") or ""))
            elif binding == "clone-reference-original-sidecar":
                sample = Path(str(record.get("sample_path") or ""))
                filename = str(asset.get("source_filename") or "")
                safe_name = "".join(
                    character if character.isalnum() or character in "._-" else "_"
                    for character in Path(filename).name
                ).strip("._")
                destination = sample.parent / (safe_name or "original-recording.wav")
            else:
                raise AssertionError(f"Unexpected D5 packaged asset binding: {binding!r}")

            if not destination.is_file():
                raise AssertionError(
                    f"Imported asset is missing for {profile_id} ({binding}): {destination}"
                )
            actual_digest = _sha256(destination)
            expected_digest = str(asset.get("sha256") or "")
            if actual_digest != expected_digest:
                raise AssertionError(
                    f"Imported asset hash changed for {profile_id} ({binding}): "
                    f"expected {expected_digest}, got {actual_digest}"
                )
            if not destination.resolve().is_relative_to(voices_root.resolve()) and binding != "worker-derived-neutral-anchor":
                raise AssertionError(f"Imported profile asset escaped the Voices storage root: {destination}")
            verified_assets.append({
                "profile_id": profile_id,
                "binding": binding,
                "path_name": destination.name,
                "sha256": actual_digest,
                "size_bytes": destination.stat().st_size,
            })

    if len(by_id) != len(profiles):
        raise AssertionError(
            f"Isolated destination catalogue contains {len(by_id)} profiles; expected exactly {len(profiles)}."
        )
    for raw_path, expected_digest in source_assets.items():
        source = Path(raw_path)
        if not source.is_file() or _sha256(source) != expected_digest:
            raise AssertionError(f"Export/import modified the source-PC fixture asset: {source}")
    return verified_assets


def _run(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    exe = Path(args.exe).expanduser().resolve()
    script = Path(args.script).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    if not exe.is_file():
        raise FileNotFoundError(f"Frozen Windows executable does not exist: {exe}")
    if not script.is_file():
        raise FileNotFoundError(f"Browser acceptance script does not exist: {script}")

    output_dir.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="ryu-stage-d5-voice-library-", dir=str(output_dir.parent)))
    original_environment = {
        key: os.environ.get(key)
        for key in ("USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA")
    }
    report = {
        "status": "running",
        "stage": "D5",
        "acceptance": "packaged Voice Library export/import/fresh-process round-trip",
        "phases": [],
    }

    try:
        home = workspace / "isolated-user"
        for key, suffix in (
            ("USERPROFILE", ""),
            ("HOME", ""),
            ("APPDATA", "AppData/Roaming"),
            ("LOCALAPPDATA", "AppData/Local"),
        ):
            value = home if not suffix else home / suffix
            os.environ[key] = str(value)
        home.mkdir(parents=True, exist_ok=True)

        source_root = workspace / "source-assets"
        source_root.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex[:10].lower()
        profiles, source_assets = _build_profiles(source_root, token)

        # Save only synthetic acceptance profiles below a fresh, isolated USERPROFILE.
        from app.tts.voice_profile import save_profiles, profiles_file
        from app.core.paths import voices_root

        save_profiles(profiles)
        catalogue = profiles_file()
        if not catalogue.is_file():
            raise AssertionError("Could not seed the isolated Qwen Voice Library fixture catalogue.")

        acceptance_root = output_dir / "acceptance-root"
        acceptance_root.mkdir(parents=True, exist_ok=True)
        bundle_path = acceptance_root / f"qwen-voice-library-{token}.ryuvoice"
        if bundle_path.exists():
            raise FileExistsError(f"Unexpected pre-existing acceptance bundle: {bundle_path}")

        common_profiles = [{
            "name": profile.name,
            "qwen_profile_id": profile.qwen_profile_id,
            "qwen_mode": profile.qwen_mode,
            "model_id": profile.model_id,
            "voice_id": profile.voice_id,
            "language": profile.language,
            "qwen_prompt": profile.qwen_prompt,
            "qwen_seed": profile.qwen_seed,
            "reference_text": profile.reference_text,
            "qwen_anchor_text": profile.qwen_anchor_text,
            "authorized": profile.authorized,
            "style_preset": profile.style_preset,
            "exaggeration": profile.exaggeration,
            "cfg_weight": profile.cfg_weight,
            "d5_acceptance_extension": profile.extra_fields.get("d5_acceptance_extension"),
        } for profile in profiles]
        common_config = {
            "bundle_path": str(bundle_path),
            "profiles": common_profiles,
        }

        report["phases"].append(_run_phase(
            phase="export",
            exe=exe, script=script, output_dir=output_dir,
            acceptance_root=acceptance_root, home=home, repo_root=repo_root,
            common_config=common_config,
        ))

        if not bundle_path.is_file() or bundle_path.stat().st_size <= 0:
            raise AssertionError("The packaged Voice Library did not create its .ryuvoice export.")
        from app.tts.qwen_profile_bundle import inspect_qwen_profile_bundle
        inspection = inspect_qwen_profile_bundle(bundle_path)
        if inspection.get("integrity_verified") is not True:
            raise AssertionError("The exported D5 .ryuvoice failed the application bundle inspector.")
        with zipfile.ZipFile(bundle_path, "r") as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        manifest_profiles = manifest.get("profiles", [])
        if len(manifest_profiles) != len(profiles):
            raise AssertionError("The exported manifest does not contain every selected profile.")
        expected_asset_hashes = {
            str(entry.get("profile_id") or ""): [
                str(asset.get("sha256") or "")
                for asset in entry.get("assets", [])
            ]
            for entry in manifest_profiles
        }
        report["export"] = {
            "bundle_name": bundle_path.name,
            "bundle_sha256": _sha256(bundle_path),
            "bundle_size_bytes": bundle_path.stat().st_size,
            "profile_count": len(manifest_profiles),
            "asset_count": sum(len(entry.get("assets", [])) for entry in manifest_profiles),
        }
        common_config["expected_asset_hashes"] = expected_asset_hashes

        # The isolated target starts with no profiles. This is a clean destination,
        # not the user's catalogue; the exported source bundle remains untouched.
        catalogue.parent.mkdir(parents=True, exist_ok=True)
        catalogue.write_text("[]\n", encoding="utf-8")
        report["phases"].append(_run_phase(
            phase="import",
            exe=exe, script=script, output_dir=output_dir,
            acceptance_root=acceptance_root, home=home, repo_root=repo_root,
            common_config=common_config,
        ))
        report["phases"].append(_run_phase(
            phase="verify",
            exe=exe, script=script, output_dir=output_dir,
            acceptance_root=acceptance_root, home=home, repo_root=repo_root,
            common_config=common_config,
        ))

        verified_assets = _validate_imported_records(
            profiles, manifest_profiles, source_assets, voices_root()
        )
        report["status"] = "passed"
        report["exact_source_sha_required"] = True
        report["profiles"] = [
            {
                "name": profile.name,
                "qwen_profile_id": profile.qwen_profile_id,
                "qwen_mode": profile.qwen_mode,
                "model_id": profile.model_id,
            }
            for profile in profiles
        ]
        report["verified_assets"] = verified_assets
        report["destination_model_policy"] = (
            "All Qwen models/runtime intentionally absent from the isolated destination; "
            "the packaged UI must report this state and must not substitute a different model."
        )
        report["source_assets_unchanged"] = True
        report_path = output_dir / "acceptance-report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("PACKAGED STAGE D5 VOICE LIBRARY ACCEPTANCE PASSED")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        (output_dir / "acceptance-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        raise
    finally:
        for key, value in original_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(workspace, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True, help="Frozen Windows application executable.")
    parser.add_argument("--script", required=True, help="Browser-side Stage D5 acceptance JavaScript.")
    parser.add_argument("--output", required=True, help="Directory for the .ryuvoice and acceptance report.")
    args = parser.parse_args()
    try:
        return _run(args)
    except Exception as exc:
        print(f"Packaged Stage D5 Voice Library acceptance FAILED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
