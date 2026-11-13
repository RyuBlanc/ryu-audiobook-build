"""Real Qwen Base clone + saved VoiceDesign + Production M4B acceptance.

Exercises authorized-reference import, saved Qwen voice profiles, preview,
canonical identity reuse after reload, assigned character synthesis, and a
real two-chapter M4B with FFmpeg decode/chapter verification.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import wave
from unittest.mock import patch

from huggingface_hub import snapshot_download

from app.chapters.detector import Chapter
from app.core.character_identity import character_identity_key
from app.tts.preview import build_voice_preview
from app.tts.profile_provider import provider_from_profile
from app.tts.qwen_character_runtime import MODEL_IDS, model_installed
from app.tts.voice_profile import (
    VoiceProfile,
    import_reference_audio,
    load_saved_profile,
    load_saved_profiles,
    save_profiles,
)


ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = Path(os.environ["RYU_QWEN_MODEL_ROOT"]).resolve()
OUTPUT_ROOT = Path(os.environ.get("RYU_QWEN_DESIGN_OUTPUT", ROOT / "qwen-design-production-artifacts"))
REQUIRED = ("design-1.7b", "base-0.6b")
SERIES = "Stage 3 Qwen Real Integration"


def _valid_wav(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        frames, rate = audio.getnframes(), audio.getframerate()
        if frames <= 0 or rate <= 0:
            raise RuntimeError(f"Audio output is empty or invalid: {path}")
        return frames / float(rate)


def _assigned(text: str, phrase: str) -> dict:
    start = text.index(phrase)
    return {
        "start": start,
        "end": start + len(phrase),
        "text": phrase,
        "speaker": "Mira",
        "series": SERIES,
        "source": "manual",
    }


def _prepare_models() -> None:
    for kind in REQUIRED:
        destination = MODEL_ROOT / kind
        if not (destination / "config.json").is_file():
            snapshot_download(
                repo_id=MODEL_IDS[kind],
                local_dir=str(destination),
                allow_patterns=[
                    "*.json", "*.safetensors", "*.txt", "*.model", "*.npz",
                    "*.bin", "tokenizer*", "vocab*",
                ],
            )
    with patch("app.tts.qwen_character_runtime.MODEL_DIRS", {
        **{key: MODEL_ROOT / key for key in MODEL_IDS}
    }):
        missing = [kind for kind in REQUIRED if not model_installed(kind)]
    if missing:
        raise RuntimeError("Qwen model integrity check failed: " + ", ".join(missing))


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    _prepare_models()

    import imageio_ffmpeg
    from app.tts import qwen_character_runtime as runtime
    from app.tts.providers import qwen_character as qwen_provider_module
    from app.tts.expression import (
        DEFAULT_VOICE_DESIGN_ANCHOR_TEXT,
        classify_expression,
        default_voice_design_anchor_text,
    )
    from app.tts.providers.piper import PiperProvider
    from app.tts.cast_provider import CastAwareProvider
    from app.tts.manager import GenerationManager

    model_dirs = {key: MODEL_ROOT / key for key in MODEL_IDS}
    env = os.environ.copy()
    env["HF_HOME"] = os.environ.get("HF_HOME", str(MODEL_ROOT / "huggingface"))
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["TOKENIZERS_PARALLELISM"] = "false"
    env["OMP_NUM_THREADS"] = "2"
    env["MKL_NUM_THREADS"] = "2"
    saved_root = OUTPUT_ROOT / "saved-profiles"

    with (
        patch.object(runtime, "RUNTIME_ROOT", MODEL_ROOT),
        patch.object(runtime, "MODEL_DIRS", model_dirs),
        patch.object(runtime, "runtime_ready", return_value=True),
        patch.object(runtime, "verify_runtime", return_value="CI Qwen runtime"),
        patch.object(qwen_provider_module, "RUNTIME_ROOT", MODEL_ROOT),
        patch.object(qwen_provider_module, "runtime_ready", return_value=True),
        patch.object(qwen_provider_module, "verify_runtime", return_value="CI Qwen runtime"),
        patch.object(qwen_provider_module, "runtime_python", return_value=Path(sys.executable)),
        patch.object(qwen_provider_module, "runtime_environment", return_value=env),
        patch.object(qwen_provider_module, "model_installed", side_effect=lambda kind: runtime.model_installed(kind)),
        patch("app.tts.voice_profile.voices_root", return_value=saved_root),
        patch("app.tts.voice_profile.builtin_voice_profiles", return_value=[]),
    ):
        # 1. Build a clean speech reference, import it through the same
        # normalizer as the application, and persist an authorized Base clone.
        piper_path = ROOT / "bundled_models" / "piper" / "en_US-lessac-medium.onnx"
        if not piper_path.is_file():
            raise RuntimeError(f"Reference speech fixture is missing: {piper_path}")
        transcript = (
            "Hello. This is an authorized reference recording created for the "
            "Ryu Audiobook Qwen voice clone acceptance test. The speaker talks "
            "clearly at a steady pace so the cloned character can preserve identity."
        )
        reference_source = OUTPUT_ROOT / "authorized-reference-fixture.wav"
        reference_engine = PiperProvider(model_path=piper_path, backend="cpu")
        reference_engine.synthesize(transcript, reference_source, "en_US-lessac-medium")
        imported_reference = import_reference_audio(
            reference_source,
            "Stage 3 Authorized Qwen Clone",
            minimum_seconds=6.0,
        )
        clone_profile = VoiceProfile(
            name="Stage 3 Qwen Base Clone",
            provider="qwen-character",
            voice_id="Ryan",
            sample_path=str(imported_reference),
            model_id="base-0.6b",
            backend="cpu",
            language="English",
            notes="Authorized generated speech fixture for Base clone acceptance.",
            authorized=True,
            qwen_mode="clone",
            reference_text=transcript,
            qwen_seed=20261101,
        )
        save_profiles([clone_profile])
        reloaded_clone = load_saved_profile(clone_profile.name)
        if not reloaded_clone or not reloaded_clone.authorized or not reloaded_clone.sample_path:
            raise RuntimeError("Authorized Qwen Base clone profile did not survive save/reload.")
        clone_engine, clone_voice = provider_from_profile(reloaded_clone)
        clone_output = OUTPUT_ROOT / "qwen-base-0.6b-cloned-voice.wav"
        try:
            clone_engine.synthesize(
                "The same speaker has returned to tell the next part of the story.",
                clone_output,
                clone_voice,
            )
        finally:
            close = getattr(clone_engine, "close", None)
            if callable(close):
                close()
        clone_duration = _valid_wav(clone_output)
        print(
            f"REAL_QWEN_BASE_CLONE=PASS model={MODEL_IDS['base-0.6b']} "
            f"reference={imported_reference.name} duration={clone_duration:.3f}s "
            f"authorized=true profile_reload=true"
        )

        # 2. Save and reload a designed character. The qwen_profile_id is the
        # stable identity namespace used by the worker's canonical anchor.
        design_profile = VoiceProfile(
            name="Stage 3 Qwen Designed Mira",
            provider="qwen-character",
            voice_id="Ryan",
            model_id="design-1.7b",
            backend="cpu",
            language="English",
            notes="Saved Stage 3 VoiceDesign identity.",
            authorized=True,
            qwen_mode="design",
            qwen_prompt=(
                "A warm young adult male audiobook character, clear English "
                "articulation, restrained emotion, stable natural timbre."
            ),
            qwen_seed=20261101,
            qwen_anchor_text=DEFAULT_VOICE_DESIGN_ANCHOR_TEXT,
        )
        save_profiles([design_profile])
        reloaded_design = load_saved_profile(design_profile.name)
        if not reloaded_design or not reloaded_design.qwen_profile_id:
            raise RuntimeError("VoiceDesign saved profile lost its persistent identity ID.")

        preview_engine, preview_voice = provider_from_profile(reloaded_design)
        preview_output = OUTPUT_ROOT / "qwen-voicedesign-saved-profile-preview.wav"
        try:
            preview_result = build_voice_preview(
                "The lantern glowed beside the quiet road. Mira listened before she answered.",
                preview_engine, preview_voice, preview_output,
                narration_speed=1.0, pacing_profile="off", max_chars=500, target_seconds=3.0,
            )
            preview_duration = _valid_wav(preview_output)
            if preview_result.segments < 1:
                raise RuntimeError("Saved VoiceDesign profile preview did not synthesize any segments.")

            # Measure Voice Studio's real saved-profile route after its stable
            # identity anchor has been initialized by the short preview above.
            sentences = (
                "The lantern glowed softly beside the quiet road.",
                "Mira listened carefully before she answered.",
                "Rain moved gently across the distant valley.",
                "The old wooden door opened into the hall.",
                "A calm narrator guided the story forward.",
                "The village lights shimmered beyond the river.",
            )
            preview_source = " ".join(sentences[index % len(sentences)] for index in range(240))
            saved_profile_preview = OUTPUT_ROOT / "qwen-voicedesign-saved-profile-30-second-preview.wav"
            saved_preview_started = time.perf_counter()
            saved_preview_result = build_voice_preview(
                preview_source, preview_engine, preview_voice, saved_profile_preview,
                narration_speed=1.0, pacing_profile="off", max_chars=1400, target_seconds=30.0,
            )
            saved_preview_elapsed = time.perf_counter() - saved_preview_started
            saved_preview_duration = _valid_wav(saved_profile_preview)
            if not 27.0 <= saved_preview_duration <= 33.0:
                raise RuntimeError(
                    "Saved VoiceDesign 30-second preview duration out of tolerance: "
                    f"{saved_preview_duration:.3f}s."
                )
            if saved_preview_result.segments < 1:
                raise RuntimeError("Saved VoiceDesign 30-second preview generated no segments.")
            if not preview_engine.execution_backend_verified or preview_engine.execution_backend != "cpu":
                raise RuntimeError(
                    "Hosted CPU VoiceDesign benchmark did not prove real CPU inference; "
                    f"backend={preview_engine.execution_backend!r}."
                )
            print(
                "REAL_QWEN_VOICEDESIGN_SAVED_PROFILE_PREVIEW=PASS "
                f"device={preview_engine.last_execution_context.get('device')} "
                f"base_model={preview_engine.long_form_model_kind or 'automatic'} "
                f"requested=30s actual={saved_preview_duration:.3f}s "
                f"warm_preview_elapsed={saved_preview_elapsed:.3f}s "
                f"segments={saved_preview_result.segments} profile_reload=true identity_locked=true"
            )
            (OUTPUT_ROOT / "qwen-saved-profile-performance.json").write_text(
                json.dumps({
                    "backend": preview_engine.execution_backend,
                    "device": preview_engine.last_execution_context.get("device"),
                    "model_kind": preview_engine.last_execution_context.get("model_kind"),
                    "saved_profile_id": reloaded_design.qwen_profile_id,
                    "saved_profile_reloaded": True,
                    "identity_locked_design_task": True,
                    "preview_30s": {
                        "elapsed_seconds": round(saved_preview_elapsed, 3),
                        "audio_seconds": round(saved_preview_duration, 3),
                        "segments": saved_preview_result.segments,
                    },
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        finally:
            close = getattr(preview_engine, "close", None)
            if callable(close):
                close()

        from app.tts.qwen_character_worker import EXPRESSION_BANK_VERSION, _anchor_path
        anchor_request = {
            "speaker": reloaded_design.voice_id,
            "language": reloaded_design.language,
            "instruct": reloaded_design.qwen_prompt or reloaded_design.notes,
            "seed": reloaded_design.qwen_seed,
            "anchor_text": reloaded_design.qwen_anchor_text or DEFAULT_VOICE_DESIGN_ANCHOR_TEXT,
            "profile_id": reloaded_design.qwen_profile_id,
        }
        canonical_anchor = _anchor_path(MODEL_ROOT, anchor_request, "neutral")
        if not canonical_anchor.is_file() or canonical_anchor.stat().st_size < 1024:
            raise RuntimeError("VoiceDesign did not persist a canonical acoustic identity anchor.")
        first_anchor_hash = hashlib.sha256(canonical_anchor.read_bytes()).hexdigest()

        # Re-read the profile from disk and create a new provider/worker. The
        # same profile ID must reuse the exact previously generated anchor.
        reloaded_again = load_saved_profile(design_profile.name)
        if not reloaded_again or reloaded_again.qwen_profile_id != reloaded_design.qwen_profile_id:
            raise RuntimeError("VoiceDesign identity ID changed during reload.")
        reload_engine, reload_voice = provider_from_profile(reloaded_again)
        reload_output = OUTPUT_ROOT / "qwen-voicedesign-reloaded-longform.wav"
        try:
            reload_engine.synthesize(
                "Beyond the river, the village lights shimmered while Mira continued her journey.",
                reload_output,
                reload_voice,
            )
        finally:
            close = getattr(reload_engine, "close", None)
            if callable(close):
                close()
        reload_duration = _valid_wav(reload_output)
        second_anchor_hash = hashlib.sha256(canonical_anchor.read_bytes()).hexdigest()
        if first_anchor_hash != second_anchor_hash:
            raise RuntimeError("Reloading VoiceDesign changed the saved acoustic identity anchor.")
        print(
            f"REAL_QWEN_VOICEDESIGN_SAVE_RELOAD=PASS profile_id={reloaded_design.qwen_profile_id} "
            f"preview={preview_duration:.3f}s longform={reload_duration:.3f}s "
            "same_anchor_sha256=true"
        )

        # 2b. Verify a saved Japanese VoiceDesign profile creates a native
        # one-sentence identity anchor, synthesizes emotional delivery through
        # that same anchor, and reuses its exact bytes after profile reload.
        japanese_profile = VoiceProfile(
            name="Stage C4 Japanese Saved VoiceDesign",
            provider="qwen-character",
            voice_id="Stage C4 Japanese Character",
            model_id="design-1.7b",
            backend="cpu",
            language="Japanese",
            notes="Native Japanese VoiceDesign identity continuity acceptance.",
            authorized=True,
            qwen_mode="design",
            qwen_prompt=(
                "A natural Japanese audiobook character voice. Keep a steady, "
                "clear adult timbre, natural Japanese articulation and consistent pitch."
            ),
            qwen_seed=20261113,
        )
        existing_profiles = [
            item for item in load_saved_profiles()
            if item.name.casefold() != japanese_profile.name.casefold()
        ]
        save_profiles([*existing_profiles, japanese_profile])
        japanese_saved = load_saved_profile(japanese_profile.name)
        if not japanese_saved or not japanese_saved.qwen_profile_id:
            raise RuntimeError("Japanese VoiceDesign profile did not persist its identity ID.")
        if japanese_saved.qwen_anchor_text:
            raise RuntimeError("Japanese test profile unexpectedly persisted an explicit anchor text.")

        with (
            patch("app.tts.profile_provider.get_qwen_model_preference", return_value="0.6b"),
            patch("app.tts.profile_provider.get_qwen_backend_preference", return_value="cpu"),
            patch("app.tts.profile_provider.get_qwen_low_memory_mode", return_value=False),
        ):
            japanese_engine, japanese_voice = provider_from_profile(japanese_saved)
        expected_japanese_anchor = default_voice_design_anchor_text("Japanese")
        if japanese_engine.qwen_anchor_text != expected_japanese_anchor:
            raise RuntimeError("Saved Japanese VoiceDesign did not resolve the native-language identity anchor.")
        if japanese_engine.model_kind != "design-1.7b" or japanese_engine.long_form_model_kind != "base-0.6b":
            raise RuntimeError(
                "Japanese VoiceDesign selected unexpected model kinds: "
                f"design={japanese_engine.model_kind} base={japanese_engine.long_form_model_kind}"
            )

        japanese_neutral_output = OUTPUT_ROOT / "qwen-japanese-voicedesign-neutral.wav"
        japanese_neutral_started = time.perf_counter()
        try:
            japanese_engine.synthesize(
                "今日は静かな町を歩いています。",
                japanese_neutral_output,
                japanese_voice,
            )
            japanese_neutral_elapsed = time.perf_counter() - japanese_neutral_started
            japanese_neutral_duration = _valid_wav(japanese_neutral_output)
            if not japanese_engine.execution_backend_verified or japanese_engine.execution_backend != "cpu":
                raise RuntimeError(
                    "Japanese saved-profile VoiceDesign did not prove real CPU inference: "
                    f"backend={japanese_engine.execution_backend!r}"
                )
            japanese_neutral_device = japanese_engine.last_execution_context.get("device")
        finally:
            japanese_engine.close()

        japanese_anchor_request = {
            "speaker": japanese_saved.voice_id,
            "language": japanese_saved.language,
            "instruct": japanese_saved.qwen_prompt or japanese_saved.notes,
            "seed": japanese_saved.qwen_seed,
            "anchor_text": expected_japanese_anchor,
            "profile_id": japanese_saved.qwen_profile_id,
        }
        japanese_anchor = _anchor_path(MODEL_ROOT, japanese_anchor_request, "neutral")
        if not japanese_anchor.is_file() or japanese_anchor.stat().st_size < 1024:
            raise RuntimeError("Real Japanese VoiceDesign did not persist its canonical native-language anchor.")
        japanese_anchor_sha256 = hashlib.sha256(japanese_anchor.read_bytes()).hexdigest()

        japanese_reloaded = load_saved_profile(japanese_profile.name)
        if not japanese_reloaded or japanese_reloaded.qwen_profile_id != japanese_saved.qwen_profile_id:
            raise RuntimeError("Reloading Japanese VoiceDesign changed the saved profile identity ID.")
        with (
            patch("app.tts.profile_provider.get_qwen_model_preference", return_value="0.6b"),
            patch("app.tts.profile_provider.get_qwen_backend_preference", return_value="cpu"),
            patch("app.tts.profile_provider.get_qwen_low_memory_mode", return_value=False),
        ):
            japanese_reload_engine, japanese_reload_voice = provider_from_profile(japanese_reloaded)
        if japanese_reload_engine.qwen_anchor_text != expected_japanese_anchor:
            raise RuntimeError("Reloaded Japanese profile changed its resolved native anchor text.")

        japanese_emotion_text = "彼女は怒った。"
        japanese_emotion = classify_expression(japanese_emotion_text)
        if japanese_emotion != "angry":
            raise RuntimeError(
                f"Japanese emotional continuity fixture expected angry, got {japanese_emotion!r}."
            )
        japanese_emotion_output = OUTPUT_ROOT / "qwen-japanese-voicedesign-angry.wav"
        try:
            japanese_reload_engine.synthesize(
                japanese_emotion_text,
                japanese_emotion_output,
                japanese_reload_voice,
            )
            japanese_emotion_duration = _valid_wav(japanese_emotion_output)
            if not japanese_reload_engine.execution_backend_verified or japanese_reload_engine.execution_backend != "cpu":
                raise RuntimeError(
                    "Reloaded Japanese emotional synthesis did not prove real CPU inference: "
                    f"backend={japanese_reload_engine.execution_backend!r}"
                )
            japanese_emotion_device = japanese_reload_engine.last_execution_context.get("device")
        finally:
            japanese_reload_engine.close()

        japanese_anchor_after_reload_sha256 = hashlib.sha256(japanese_anchor.read_bytes()).hexdigest()
        if japanese_anchor_sha256 != japanese_anchor_after_reload_sha256:
            raise RuntimeError("Japanese VoiceDesign regenerated or changed its canonical anchor after profile reload.")
        japanese_identity_evidence = {
            "language": japanese_saved.language,
            "saved_profile_id": japanese_saved.qwen_profile_id,
            "saved_profile_reloaded": True,
            "voice_design_model": japanese_engine.model_kind,
            "long_form_base_model": "base-0.6b",
            "anchor_text": expected_japanese_anchor,
            "anchor_instruction_version": EXPRESSION_BANK_VERSION,
            "anchor_path": str(japanese_anchor),
            "anchor_sha256": japanese_anchor_sha256,
            "anchor_sha256_after_reload": japanese_anchor_after_reload_sha256,
            "same_anchor_after_reload": True,
            "neutral_audio": {
                "seconds": round(japanese_neutral_duration, 3),
                "elapsed_seconds": round(japanese_neutral_elapsed, 3),
                "device": japanese_neutral_device,
            },
            "angry_audio": {
                "seconds": round(japanese_emotion_duration, 3),
                "device": japanese_emotion_device,
            },
            "backend": "cpu",
        }
        (OUTPUT_ROOT / "qwen-japanese-voice-identity-continuity.json").write_text(
            json.dumps(japanese_identity_evidence, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            "REAL_QWEN_JAPANESE_SAVED_PROFILE_IDENTITY=PASS "
            f"profile_reload=true model={japanese_engine.model_kind} "
            f"base=base-0.6b device={japanese_neutral_device} "
            f"neutral={japanese_neutral_duration:.3f}s "
            f"angry={japanese_emotion_duration:.3f}s same_anchor_sha256=true "
            f"anchor_version={EXPRESSION_BANK_VERSION}"
        )

        # 3. Exercise assigned Qwen character dialogue through the same
        # CastAwareProvider + GenerationManager production route, then inspect
        # the actual multi-chapter M4B container.
        narrator_profile = VoiceProfile(
            name="Stage 3 Qwen M4B Narrator",
            provider="piper",
            voice_id="en_US-lessac-medium",
            model_id="piper",
            backend="cpu",
            language="en-US",
            authorized=True,
        )
        narrator_engine = PiperProvider(model_path=piper_path, backend="cpu")
        chapter_one_text = "The lantern flickered. Mira said, “Stay close.” The tunnel narrowed."
        chapter_two_text = "Rain fell across the road. Mira whispered, “I will stay.” The village lights appeared."
        chapters = [
            Chapter(
                1, "The Tunnel", chapter_one_text,
                dialogue_assignments=[_assigned(chapter_one_text, "Stay close.")],
                review_status="ready",
            ),
            Chapter(
                2, "The Road", chapter_two_text,
                dialogue_assignments=[_assigned(chapter_two_text, "I will stay.")],
                review_status="ready",
            ),
        ]
        qwen_recorders = []
        real_factory = provider_from_profile

        class RecordingProvider:
            def __init__(self, inner):
                self.inner = inner
                self.calls = []

            def __getattr__(self, attribute):
                return getattr(self.inner, attribute)

            def synthesize(self, text, output_path, voice=None):
                self.calls.append((str(text), voice, Path(output_path)))
                return self.inner.synthesize(text, output_path, voice)

        def recording_factory(profile):
            engine, voice = real_factory(profile)
            if profile.name == reloaded_design.name:
                wrapper = RecordingProvider(engine)
                qwen_recorders.append(wrapper)
                return wrapper, voice
            return engine, voice

        provider = CastAwareProvider(
            narrator_engine,
            narrator_profile.voice_id,
            {reloaded_design.name: reloaded_design},
            {"Mira": reloaded_design.name},
            narrator_profile=narrator_profile,
            identity_assignments={
                character_identity_key("Mira", SERIES): reloaded_design.name,
            },
        )
        output_book = OUTPUT_ROOT / "Ryu-Stage3-Qwen-Character-Integration.m4b"
        completed = []
        with (
            patch("app.tts.cast_provider.provider_from_profile", side_effect=recording_factory),
            patch("app.tts.providers.piper.models_root", return_value=ROOT / "bundled_models"),
        ):
            manager = GenerationManager(
                provider=provider,
                voice=narrator_profile.voice_id,
                chapters=chapters,
                project_audio_root=OUTPUT_ROOT / "chapter-audio",
                on_finished=completed.append,
                narration_speed=1.0,
                pacing_profile="off",
                story_effects_enabled=False,
                metadata={"series": SERIES},
            )
            manager._run_body(
                output_book,
                SERIES,
                "Ryu Audiobook CI",
                None,
                {"title": "Ryu Stage 3 Qwen Character Integration", "narrator": narrator_profile.name},
            )
        provider.close()

        if not output_book.is_file() or output_book.stat().st_size < 10_000:
            raise RuntimeError("Qwen multi-chapter M4B output is missing or too small.")
        if len(completed) != 1 or completed[0].chapters_total != 2 or completed[0].chapters_completed != 2 or completed[0].chapters_failed:
            raise RuntimeError(f"Qwen multi-chapter generation failed: {completed!r}")
        qwen_calls = [call for recorder in qwen_recorders for call in recorder.calls]
        if not any("Stay close." in call[0] for call in qwen_calls):
            raise RuntimeError("First-chapter assigned Mira dialogue did not reach Qwen.")
        if not any("I will stay." in call[0] for call in qwen_calls):
            raise RuntimeError("Second-chapter assigned Mira dialogue did not reach Qwen.")

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        probe = __import__("subprocess").run(
            [ffmpeg, "-hide_banner", "-i", str(output_book), "-map", "0:a:0", "-f", "null", "-"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=240,
        )
        diagnostic = (probe.stdout or "") + "\n" + (probe.stderr or "")
        if probe.returncode != 0:
            raise RuntimeError("FFmpeg could not decode the Qwen M4B: " + diagnostic[-4000:])
        markers = re.findall(r"Chapter #\d+:\d+:", diagnostic)
        if len(markers) < 2 or "The Tunnel" not in diagnostic or "The Road" not in diagnostic:
            raise RuntimeError("The Qwen M4B is missing expected chapter markers: " + diagnostic[-4000:])

        print(
            f"REAL_QWEN_CHARACTER_TO_M4B=PASS chapters=2 qwen_dialogue_calls={len(qwen_calls)} "
            f"bytes={output_book.stat().st_size} chapter_markers={len(markers)} ffmpeg_decode=true"
        )
        print("QWEN_CLONE_DESIGN_PRODUCTION_ACCEPTANCE=PASS")


if __name__ == "__main__":
    main()
