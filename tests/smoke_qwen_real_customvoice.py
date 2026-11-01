"""Real Qwen CustomVoice acceptance for both published model sizes.

Runs the production QwenCharacterProvider worker and saved-profile path. WAV
outputs are decoded before acceptance so this is real audio, not a mocked API.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import wave
from unittest.mock import patch

from huggingface_hub import snapshot_download

from app.tts.profile_provider import provider_from_profile
from app.tts.qwen_character_runtime import MODEL_IDS, model_installed
from app.tts.voice_profile import VoiceProfile, load_saved_profile, save_profiles


ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = Path(os.environ["RYU_QWEN_MODEL_ROOT"]).resolve()
OUTPUT_ROOT = Path(os.environ.get("RYU_QWEN_CUSTOM_OUTPUT", ROOT / "qwen-customvoice-artifacts"))
KINDS = ("custom-0.6b", "custom-1.7b")


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
                backend="cpu",
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
            output = OUTPUT_ROOT / f"{kind}-customvoice.wav"
            try:
                engine.synthesize(
                    "The road curved beyond the quiet village. Ryan spoke clearly and calmly.",
                    output,
                    voice,
                )
            finally:
                close = getattr(engine, "close", None)
                if callable(close):
                    close()
            duration = _valid_wav(output)
            if output.stat().st_size < 1024:
                raise RuntimeError(f"Qwen CustomVoice produced an unexpectedly small WAV for {kind}.")
            print(
                f"REAL_QWEN_CUSTOMVOICE=PASS model={MODEL_IDS[kind]} kind={kind} "
                f"duration={duration:.3f}s bytes={output.stat().st_size} "
                f"saved_profile_reload=true decoded_audio=true"
            )

    print("REAL_QWEN_CUSTOMVOICE_BOTH_SIZES=PASS")


if __name__ == "__main__":
    main()
