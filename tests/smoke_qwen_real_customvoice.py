"""Real Qwen CustomVoice acceptance for both published model sizes.

Runs the production QwenCharacterProvider worker and saved-profile path. WAV
outputs are decoded before acceptance so this is real audio, not a mocked API.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
import wave
from unittest.mock import patch

from huggingface_hub import snapshot_download

from app.tts.preview import build_voice_preview
from app.tts.profile_provider import provider_from_profile
from app.tts.qwen_character_runtime import MODEL_IDS, model_installed
from app.tts.voice_profile import VoiceProfile, load_saved_profile, save_profiles


ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = Path(os.environ["RYU_QWEN_MODEL_ROOT"]).resolve()
OUTPUT_ROOT = Path(os.environ.get("RYU_QWEN_CUSTOM_OUTPUT", ROOT / "qwen-customvoice-artifacts"))
DEFAULT_KINDS = ("custom-0.6b", "custom-1.7b")
KINDS = tuple(
    item.strip().casefold()
    for item in os.environ.get("RYU_QWEN_CUSTOM_KINDS", ",".join(DEFAULT_KINDS)).split(",")
    if item.strip()
)
EXPECTED_BACKEND = str(os.environ.get("RYU_QWEN_EXPECT_BACKEND") or "").strip().casefold()
PREVIEW_SECONDS = max(0.0, float(os.environ.get("RYU_QWEN_CUSTOM_PREVIEW_SECONDS", "0") or 0.0))


def _valid_wav(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        frames, rate = audio.getnframes(), audio.getframerate()
        if frames <= 0 or rate <= 0 or audio.getnchannels() <= 0:
            raise RuntimeError(f"Qwen CustomVoice output is not playable PCM audio: {path}")
        return frames / float(rate)


def _prepare_models() -> None:
    for kind in KINDS:
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
            if not model_installed(kind):
                raise RuntimeError(f"Downloaded Qwen model failed integrity validation: {kind}")


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    _prepare_models()

    from app.core.paths import models_root
    from app.tts import qwen_character_runtime as runtime
    from app.tts.qwen_accelerator import automatic_accelerator
    from app.tts.providers import qwen_character as qwen_provider_module
    from app.tts.voice_profile import voices_root

    model_dirs = {key: MODEL_ROOT / key for key in MODEL_IDS}
    env = os.environ.copy()
    env["HF_HOME"] = os.environ.get("HF_HOME", str(MODEL_ROOT / "huggingface"))
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["TOKENIZERS_PARALLELISM"] = "false"
    env["OMP_NUM_THREADS"] = "2"
    env["MKL_NUM_THREADS"] = "2"

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
        # The saved record below deliberately contains the old CPU backend.
        # A portable profile must follow this machine's current Automatic
        # preference and select an active GPU where one is available.
        patch("app.tts.profile_provider.get_qwen_backend_preference", return_value="automatic"),
        patch("app.tts.providers.qwen_character.ensure_best_runtime_for_gpu", return_value="test-runtime"),
        patch("app.tts.voice_profile.voices_root", return_value=OUTPUT_ROOT / "saved-profiles"),
        patch("app.tts.voice_profile.builtin_voice_profiles", return_value=[]),
    ):
        for kind in KINDS:
            name = f"Stage 3 Qwen {kind} CustomVoice"
            profile = VoiceProfile(
                name=name,
                provider="qwen-character",
                voice_id="Ryan",
                model_id=kind,
                backend="cpu",  # stale per-profile value must not pin this run to CPU
                language="English",
                notes="Real Qwen CustomVoice model acceptance.",
                authorized=True,
                qwen_mode="custom",
                qwen_prompt="Clear natural audiobook delivery with stable identity.",
                qwen_seed=20261101,
            )
            save_profiles([profile])
            reloaded = load_saved_profile(name)
            if reloaded is None or reloaded.model_id != kind or reloaded.voice_id != "Ryan":
                raise RuntimeError(f"CustomVoice profile failed save/reload for {kind}.")
            engine, voice = provider_from_profile(reloaded)
            if engine.backend != "automatic":
                raise RuntimeError(
                    f"Saved {kind} profile retained stale backend {engine.backend!r}; "
                    "the current global Automatic preference must control hardware."
                )
            output = OUTPUT_ROOT / f"{kind}-customvoice.wav"
            preview_metrics = None
            expected, selection_reason = automatic_accelerator(kind)
            try:
                warmup_started = time.perf_counter()
                engine.synthesize(
                    "The road curved beyond the quiet village. Ryan spoke clearly and calmly.",
                    output,
                    voice,
                )
                warmup_elapsed = time.perf_counter() - warmup_started
                duration = _valid_wav(output)
                if output.stat().st_size < 1024:
                    raise RuntimeError(f"Qwen CustomVoice produced an unexpectedly small WAV for {kind}.")
                actual_backend = engine.execution_backend
                actual_device = str(engine.last_execution_context.get("device") or "unverified")
                if not engine.execution_backend_verified or actual_backend not in {"cpu", "cuda", "rocm", "xpu"}:
                    raise RuntimeError(
                        f"Qwen {kind} generated audio without verified execution-device telemetry: "
                        f"{engine.last_execution_context!r}"
                    )
                if kind == "custom-0.6b" and actual_backend != expected.backend:
                    raise RuntimeError(
                        f"Qwen CustomVoice did not run on the backend selected by Automatic: "
                        f"expected={expected.backend}/{expected.device}, "
                        f"actual={actual_backend}/{actual_device}; reason={selection_reason}"
                    )
                if EXPECTED_BACKEND and kind == "custom-0.6b" and actual_backend != EXPECTED_BACKEND:
                    raise RuntimeError(
                        f"Qwen CustomVoice actual backend {actual_backend} did not match "
                        f"required acceptance backend {EXPECTED_BACKEND}."
                    )
                if PREVIEW_SECONDS > 0:
                    preview_source = " ".join([
                        "The lantern glowed softly beside the quiet road.",
                        "Mira listened carefully before she answered.",
                        "Rain moved gently across the distant valley.",
                        "The old wooden door opened into the hall.",
                        "A calm narrator guided the story forward.",
                        "The village lights shimmered beyond the river.",
                    ] * 40)
                    preview_path = OUTPUT_ROOT / f"{kind}-customvoice-{int(PREVIEW_SECONDS)}s-preview.wav"
                    preview_started = time.perf_counter()
                    preview_result = build_voice_preview(
                        preview_source, engine, voice, preview_path,
                        narration_speed=1.0, pacing_profile="off",
                        max_chars=1400, target_seconds=PREVIEW_SECONDS,
                    )
                    preview_elapsed = time.perf_counter() - preview_started
                    preview_duration = _valid_wav(preview_result.output_path)
                    if abs(preview_duration - PREVIEW_SECONDS) > 3.0:
                        raise RuntimeError(
                            f"Qwen {kind} preview duration {preview_duration:.3f}s is outside "
                            f"±3s of requested {PREVIEW_SECONDS:.1f}s."
                        )
                    if PREVIEW_SECONDS >= 30.0 and preview_elapsed >= 60.0:
                        raise RuntimeError(
                            f"Qwen {kind} {PREVIEW_SECONDS:.0f}s preview took {preview_elapsed:.3f}s; "
                            "the accelerator acceptance limit is under 60 seconds."
                        )
                    if not engine.execution_backend_verified or engine.execution_backend != actual_backend:
                        raise RuntimeError("CustomVoice preview lost verified execution-backend identity.")
                    preview_metrics = {
                        "requested_seconds": PREVIEW_SECONDS,
                        "audio_seconds": round(preview_duration, 3),
                        "elapsed_seconds": round(preview_elapsed, 3),
                        "segments": preview_result.segments,
                        "pass_under_60_seconds": preview_elapsed < 60.0,
                        "cpu_fallback": actual_backend == "cpu" and EXPECTED_BACKEND not in {"", "cpu"},
                    }
                benchmark = {
                    "model_kind": kind,
                    "model_id": MODEL_IDS[kind],
                    "backend": actual_backend,
                    "device": actual_device,
                    "backend_verified": engine.execution_backend_verified,
                    "automatic_backend": expected.backend,
                    "automatic_selection_reason": selection_reason,
                    "saved_profile_reload": True,
                    "warmup_seconds": round(warmup_elapsed, 3),
                    "warmup_audio_seconds": round(duration, 3),
                    "preview": preview_metrics,
                }
                (OUTPUT_ROOT / f"{kind}-performance.json").write_text(
                    json.dumps(benchmark, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(
                    f"REAL_QWEN_CUSTOMVOICE=PASS model={MODEL_IDS[kind]} kind={kind} "
                    f"duration={duration:.3f}s bytes={output.stat().st_size} "
                    f"saved_profile_reload=true decoded_audio=true "
                    f"actual_backend={actual_backend} actual_device={actual_device}"
                )
                if preview_metrics is not None:
                    print(
                        f"REAL_QWEN_CUSTOMVOICE_PREVIEW=PASS kind={kind} "
                        f"requested={PREVIEW_SECONDS:.1f}s actual={preview_metrics['audio_seconds']:.3f}s "
                        f"elapsed={preview_metrics['elapsed_seconds']:.3f}s "
                        f"backend={actual_backend} device={actual_device} cpu_fallback=false"
                    )
            finally:
                close = getattr(engine, "close", None)
                if callable(close):
                    close()

    print("REAL_QWEN_CUSTOMVOICE_KINDS=PASS kinds=" + ",".join(KINDS))


if __name__ == "__main__":
    main()
