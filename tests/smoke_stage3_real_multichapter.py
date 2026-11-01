"""Real-provider Stage 3 acceptance: previews, cast routing and two-chapter M4B.

This smoke test uses actual Piper neural voice models. It does not use the
recording/deterministic WAV providers from the unit-test integration fixture.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from unittest.mock import patch

import imageio_ffmpeg

from app.audio.story_events import detect_story_events
from app.chapters.detector import Chapter
from app.core.character_identity import character_identity_key
from app.tts.cast_provider import CastAwareProvider
from app.tts.manager import GenerationManager
from app.tts.preview import build_voice_preview
from app.tts.profile_provider import ProfileBoundProvider
from app.tts.providers.piper import PiperProvider
from app.tts.voice_profile import VoiceProfile, load_saved_profiles, save_profiles


ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT / "bundled_models"
PIPER_ROOT = MODEL_ROOT / "piper"
VOICE_IDS = ("en_US-lessac-medium", "en_US-amy-medium", "en_US-ryan-high")


class RecordingPiperProvider(PiperProvider):
    def __init__(self, model_path: Path):
        super().__init__(model_path=model_path, backend="cpu")
        self.calls: list[tuple[str, str | None, Path]] = []

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> Path:
        self.calls.append((str(text), voice, Path(output_path)))
        return super().synthesize(text, output_path, voice=voice)


def _require_models() -> dict[str, Path]:
    paths = {voice: PIPER_ROOT / f"{voice}.onnx" for voice in VOICE_IDS}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise RuntimeError("Required real Piper models are missing: " + ", ".join(missing))
    for voice, model_path in paths.items():
        config = model_path.with_suffix(".onnx.json")
        if not config.is_file():
            raise RuntimeError(f"Piper model configuration is missing for {voice}: {config}")
    return paths


def _duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        if audio.getnframes() <= 0 or audio.getframerate() <= 0:
            raise RuntimeError(f"Invalid or empty preview WAV: {path}")
        return audio.getnframes() / float(audio.getframerate())


def _preview_acceptance(model_path: Path, output_root: Path) -> None:
    """Exercise the actual preview builder at all four supported durations."""
    provider = RecordingPiperProvider(model_path)
    short_sentences = (
        "The lantern glowed.",
        "Mira watched.",
        "Rain fell.",
        "Footsteps echoed.",
        "The door opened.",
        "The valley shimmered.",
    )
    source_text = " ".join(
        short_sentences[index % len(short_sentences)]
        for index in range(2400)
    )
    for requested in (10, 30, 60, 90):
        output = output_root / f"piper-preview-{requested}.wav"
        started = time.perf_counter()
        result = build_voice_preview(
            source_text,
            provider,
            "en_US-lessac-medium",
            output,
            narration_speed=1.0,
            pacing_profile="off",
            max_chars=1400,
            target_seconds=float(requested),
        )
        elapsed = time.perf_counter() - started
        actual = _duration_seconds(result.output_path)
        # Real engines emit complete sentence units. Keep the fixture's
        # sentence boundaries short and require the result to stay within
        # one second of the selected UI target without cutting mid-word.
        if not (requested - 1.0 <= actual <= requested + 1.0):
            raise RuntimeError(
                f"Real Piper preview duration mismatch: requested={requested}s actual={actual:.3f}s"
            )
        if elapsed > 180:
            raise RuntimeError(
                f"Real Piper {requested}s preview exceeded the 180s CI smoke safety limit ({elapsed:.2f}s)."
            )
        print(
            f"REAL_PIPER_PREVIEW=PASS requested={requested}s actual={actual:.3f}s "
            f"elapsed={elapsed:.3f}s segments={result.segments}"
        )


def _assigned_quote(chapter_text: str, dialogue: str, speaker: str) -> dict:
    start = chapter_text.index(dialogue)
    return {
        "start": start,
        "end": start + len(dialogue),
        "text": dialogue,
        "speaker": speaker,
        "series": "Stage 3 Real Provider Acceptance",
        "source": "manual",
    }


def _real_multichapter_acceptance(models: dict[str, Path], output_root: Path) -> None:
    chapter_one_text = (
        "The lantern flickered. Rimuru watched the door. "
        "Mira said, “Stay close.” The door slammed shut. The tunnel narrowed."
    )
    chapter_two_text = (
        "Rain hammered against the window. "
        "Mira whispered, “I will stay.” Ren answered, “We should leave now.” "
        "The crowd roared at the gates. The village lights appeared."
    )
    chapters = [
        Chapter(
            1,
            "The Tunnel",
            chapter_one_text,
            dialogue_assignments=[
                _assigned_quote(chapter_one_text, "Stay close.", "Mira")
            ],
            review_status="ready",
        ),
        Chapter(
            2,
            "The Road",
            chapter_two_text,
            dialogue_assignments=[
                _assigned_quote(chapter_two_text, "I will stay.", "Mira"),
                _assigned_quote(chapter_two_text, "We should leave now.", "Ren"),
            ],
            review_status="ready",
        ),
    ]

    narrator_profile = VoiceProfile(
        name="Stage 3 Real Narrator",
        provider="piper",
        voice_id="en_US-lessac-medium",
        model_id="piper",
        backend="cpu",
        language="en-US",
        authorized=True,
    )
    mira_profile = VoiceProfile(
        name="Stage 3 Real Mira",
        provider="piper",
        voice_id="en_US-amy-medium",
        model_id="piper",
        backend="cpu",
        language="en-US",
        authorized=True,
    )
    ren_profile = VoiceProfile(
        name="Stage 3 Real Ren",
        provider="piper",
        voice_id="en_US-ryan-high",
        model_id="piper",
        backend="cpu",
        language="en-US",
        authorized=True,
    )
    other_profile = VoiceProfile(
        name="Other Series Mira",
        provider="piper",
        voice_id="en_US-ryan-high",
        model_id="piper",
        backend="cpu",
        language="en-US",
        authorized=True,
    )

    # Persist and reload the exact profiles before synthesis. This covers
    # the real on-disk profile catalogue path, not only in-memory profile data.
    profile_root = output_root / "saved-voice-profiles"
    with patch("app.tts.voice_profile.voices_root", return_value=profile_root), patch(
        "app.tts.voice_profile.builtin_voice_profiles", return_value=[]
    ):
        save_profiles([narrator_profile, mira_profile, ren_profile, other_profile])
        reloaded = {item.name: item for item in load_saved_profiles()}

    if set(reloaded) != {
        narrator_profile.name, mira_profile.name, ren_profile.name, other_profile.name
    }:
        raise RuntimeError(f"Saved voice profiles did not round-trip: {sorted(reloaded)}")
    narrator_profile = reloaded[narrator_profile.name]
    mira_profile = reloaded[mira_profile.name]
    ren_profile = reloaded[ren_profile.name]
    other_profile = reloaded[other_profile.name]

    narrator_engine = RecordingPiperProvider(models[narrator_profile.voice_id])
    cast_engines: dict[str, RecordingPiperProvider] = {}

    profiles = {
        mira_profile.name: mira_profile,
        ren_profile.name: ren_profile,
        other_profile.name: other_profile,
    }
    assignments = {
        "Mira": mira_profile.name,
        "Ren": ren_profile.name,
    }
    identity_assignments = {
        character_identity_key("Mira", "Stage 3 Real Provider Acceptance"): mira_profile.name,
        character_identity_key("Mira", "Another Series"): other_profile.name,
        character_identity_key("Ren", "Stage 3 Real Provider Acceptance"): ren_profile.name,
    }

    provider = CastAwareProvider(
        ProfileBoundProvider(narrator_engine, narrator_profile),
        narrator_profile.voice_id,
        profiles,
        assignments,
        narrator_profile=narrator_profile,
        identity_assignments=identity_assignments,
    )

    def provider_for_saved_profile(profile: VoiceProfile):
        engine = RecordingPiperProvider(models[profile.voice_id])
        cast_engines[profile.name] = engine
        return engine, profile.voice_id

    output_path = output_root / "Stage 3 Real Provider Acceptance.m4b"
    completed = []
    with patch("app.tts.providers.piper.models_root", return_value=MODEL_ROOT), patch(
        "app.tts.cast_provider.provider_from_profile",
        side_effect=provider_for_saved_profile,
    ):
        manager = GenerationManager(
            provider=provider,
            voice=narrator_profile.voice_id,
            chapters=chapters,
            project_audio_root=output_root / "chapter-audio",
            on_finished=completed.append,
            pronunciation_dictionary=[
                {"written_form": "Rimuru", "spoken_form": "Ri-mu-ru", "enabled": True}
            ],
            narration_speed=1.0,
            pacing_profile="off",
            story_effects_enabled=True,
            story_effect_volume=0.18,
            metadata={"series": "Stage 3 Real Provider Acceptance"},
        )
        # Invoke the same production body synchronously so this CI smoke can
        # inspect the final M4B before the job exits.
        manager._run_body(
            output_path,
            "Stage 3 Real Provider Acceptance",
            "Ryu Audiobook CI",
            None,
            {"title": "Stage 3 Real Provider Acceptance", "narrator": narrator_profile.name},
        )

    if not output_path.is_file() or output_path.stat().st_size < 10_000:
        raise RuntimeError("The real two-chapter M4B output is missing or unexpectedly small.")
    if len(completed) != 1:
        raise RuntimeError(f"Expected one terminal generation summary, received {len(completed)}.")
    summary = completed[0]
    if summary.chapters_total != 2 or summary.chapters_completed != 2 or summary.chapters_failed:
        raise RuntimeError(f"Real multi-chapter generation did not complete cleanly: {summary!r}")

    narrator_text = [text for text, _voice, _path in narrator_engine.calls]
    mira_text = [
        text for text, _voice, _path in cast_engines[mira_profile.name].calls
    ]
    ren_text = [
        text for text, _voice, _path in cast_engines[ren_profile.name].calls
    ]
    if not any("The lantern flickered." in text for text in narrator_text):
        raise RuntimeError("Narrator profile did not receive the first chapter narration.")
    if not any("The village lights appeared." in text for text in narrator_text):
        raise RuntimeError("Narrator profile did not receive the second chapter narration.")
    if not any("Stay close." in text for text in mira_text):
        raise RuntimeError("Mira's saved character profile did not receive first-chapter dialogue.")
    if not any("I will stay." in text for text in mira_text):
        raise RuntimeError("The same saved Mira profile did not receive second-chapter dialogue.")
    if len(cast_engines[mira_profile.name].calls) < 2:
        raise RuntimeError("Mira's saved voice was not reused across both generated chapters.")
    if any(voice != mira_profile.voice_id for _spoken, voice, _path in cast_engines[mira_profile.name].calls):
        raise RuntimeError("Mira's voice identity changed between chapter synthesis calls.")
    if not any("We should leave now." in text for text in ren_text):
        raise RuntimeError("Ren's saved character profile did not receive Ren's dialogue.")
    if any("Stay close." in text or "We should leave now." in text for text in narrator_text):
        raise RuntimeError("Character dialogue leaked into the narrator synthesis route.")
    if cast_engines[other_profile.name].calls if other_profile.name in cast_engines else False:
        raise RuntimeError("A same-name character from another series was incorrectly routed.")

    # Prove distinct saved profiles invoke different real model files using the
    # exact same text, rather than relying only on labels in routing metadata.
    sample_text = "This is the same identity comparison sentence."
    sample_hashes = {}
    for label, voice_id in (
        ("narrator", narrator_profile.voice_id),
        ("mira", mira_profile.voice_id),
        ("ren", ren_profile.voice_id),
    ):
        sample = output_root / f"identity-{label}.wav"
        engine = RecordingPiperProvider(models[voice_id])
        engine.synthesize(sample_text, sample, voice=voice_id)
        digest = hashlib.sha256(sample.read_bytes()).hexdigest()
        sample_hashes[label] = digest
    if len(set(sample_hashes.values())) != 3:
        raise RuntimeError(f"Distinct saved voice profiles did not produce distinct WAV output: {sample_hashes}")

    event_kinds = {
        event.kind
        for chapter in chapters
        for event in detect_story_events(chapter.text)
    }
    if not {"door_slam", "rain", "crowd"}.issubset(event_kinds):
        raise RuntimeError(f"Story-effect test fixture did not produce expected cues: {event_kinds}")

    # Decode the completed M4B with the same FFmpeg distribution used by the
    # application and verify that both named chapter markers are present.
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    probe = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(output_path), "-map", "0:a:0", "-f", "null", "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    diagnostic = (probe.stdout or "") + "\n" + (probe.stderr or "")
    if probe.returncode != 0:
        raise RuntimeError(f"FFmpeg could not decode the generated M4B:\n{diagnostic[-5000:]}")
    chapter_markers = re.findall(r"Chapter #\d+:\d+:", diagnostic)
    if len(chapter_markers) < 2 or "The Tunnel" not in diagnostic or "The Road" not in diagnostic:
        raise RuntimeError(
            "The generated M4B did not expose both expected chapter markers: "
            + diagnostic[-5000:]
        )

    print(
        "REAL_MULTICHAPTER_M4B=PASS chapters=2 "
        f"bytes={output_path.stat().st_size} "
        f"narrator_calls={len(narrator_engine.calls)} "
        f"mira_calls={len(cast_engines[mira_profile.name].calls)} "
        f"ren_calls={len(cast_engines[ren_profile.name].calls)} "
        f"same_character_chapters=2 "
        f"story_events={','.join(sorted(event_kinds))}"
    )
    print(f"REAL_VOICE_MODEL_OUTPUT_SHA256={sample_hashes}")
    print("REAL_M4B_FFMPEG_DECODE=PASS chapter_markers=2")


def main() -> None:
    models = _require_models()
    persistent_output = os.environ.get("RYU_STAGE3_ACCEPTANCE_OUTPUT", "").strip()
    if persistent_output:
        output_root = Path(persistent_output)
        output_root.mkdir(parents=True, exist_ok=True)
        _preview_acceptance(models["en_US-lessac-medium"], output_root)
        _real_multichapter_acceptance(models, output_root)
    else:
        with tempfile.TemporaryDirectory(prefix="ryu-stage3-real-provider-") as temp:
            output_root = Path(temp)
            _preview_acceptance(models["en_US-lessac-medium"], output_root)
            _real_multichapter_acceptance(models, output_root)
    print("STAGE_3_REAL_PROVIDER_ACCEPTANCE=PASS")


if __name__ == "__main__":
    main()
