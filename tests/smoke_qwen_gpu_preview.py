"""NVIDIA acceptance: warmed real Qwen 1.7B 30-second VoiceDesign preview.

This is deliberately hardware-gated. It must run on an NVIDIA Windows runner
with a CUDA-enabled PyTorch build and >=7 GiB VRAM. CPU fallback is a failure,
not a misleading performance pass.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
import wave
from unittest.mock import patch

from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = Path(os.environ["RYU_QWEN_MODEL_ROOT"]).resolve()
MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"


def main() -> None:
    import torch
    from app.tts.preview import build_voice_preview
    from app.tts.qwen_character_runtime import MODEL_IDS
    from app.tts import qwen_character_runtime as runtime
    from app.tts.providers import qwen_character as provider_module
    from app.tts.providers.qwen_character import QwenCharacterProvider

    if not torch.cuda.is_available():
        raise RuntimeError("NVIDIA acceptance requires torch.cuda.is_available() == True.")
    gpu_query = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
    )
    if gpu_query.returncode != 0 or not gpu_query.stdout.strip():
        raise RuntimeError("nvidia-smi could not identify the NVIDIA GPU.")
    memory_mib = int(gpu_query.stdout.splitlines()[0].split(",")[1].strip().split()[0])
    vram_gib = memory_mib / 1024.0
    if vram_gib < 7.0:
        raise RuntimeError(
            f"Unsupported performance tier for the 1.7B batch preview gate: {vram_gib:.2f} GiB VRAM; >=7 GiB is required."
        )

    model_dir = MODEL_ROOT / "design-1.7b"
    if not (model_dir / "config.json").is_file():
        snapshot_download(
            repo_id=MODEL_ID,
            local_dir=str(model_dir),
            allow_patterns=[
                "*.json", "*.safetensors", "*.txt", "*.model", "*.npz",
                "*.bin", "tokenizer*", "vocab*",
            ],
        )
    with patch.object(runtime, "MODEL_DIRS", {
        **{key: MODEL_ROOT / key for key in MODEL_IDS}
    }):
        if not runtime.model_installed("design-1.7b"):
            raise RuntimeError("Qwen VoiceDesign model failed local integrity verification.")

    env = os.environ.copy()
    env["HF_HOME"] = os.environ.get("HF_HOME", str(MODEL_ROOT / "huggingface"))
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["TOKENIZERS_PARALLELISM"] = "false"

    model_dirs = {key: MODEL_ROOT / key for key in MODEL_IDS}
    status_messages = []
    with (
        patch.object(runtime, "RUNTIME_ROOT", MODEL_ROOT),
        patch.object(runtime, "MODEL_DIRS", model_dirs),
        patch.object(runtime, "runtime_ready", return_value=True),
        patch.object(runtime, "verify_runtime", return_value="NVIDIA CI Qwen runtime"),
        patch.object(provider_module, "RUNTIME_ROOT", MODEL_ROOT),
        patch.object(provider_module, "runtime_ready", return_value=True),
        patch.object(provider_module, "verify_runtime", return_value="NVIDIA CI Qwen runtime"),
        patch.object(provider_module, "runtime_python", return_value=Path(sys.executable)),
        patch.object(provider_module, "runtime_environment", return_value=env),
        patch.object(provider_module, "model_installed", side_effect=lambda kind: runtime.model_installed(kind)),
    ):
        provider = QwenCharacterProvider(
            voice_id="Stage 3 NVIDIA VoiceDesign",
            language="English",
            instruct="Warm, clear audiobook narration with natural articulation and steady pacing.",
            backend="automatic",
            model_kind="design-1.7b",
            qwen_mode="design-preview",
            qwen_seed=20261101,
            qwen_profile_id="stage3-nvidia-30s-preview",
        )
        provider.set_status_callback(status_messages.append)
        try:
            OUTPUT_ROOT = Path(os.environ.get("RYU_QWEN_GPU_OUTPUT", ROOT / "qwen-gpu-acceptance"))
            OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
            warmup = OUTPUT_ROOT / "qwen-gpu-warmup.wav"
            started = time.perf_counter()
            provider.synthesize(
                "Hello. This is a short warm-up sample for the selected Qwen narrator.",
                warmup,
                provider.voice_id,
            )
            cold_elapsed = time.perf_counter() - started
            with wave.open(str(warmup), "rb") as audio:
                if audio.getnframes() <= 0:
                    raise RuntimeError("Qwen GPU warm-up WAV is empty.")

            lines = (
                "The lantern glowed softly beside the quiet road.",
                "Mira listened carefully before she answered.",
                "Rain moved gently across the distant valley.",
                "The old wooden door opened into the hall.",
                "A calm narrator guided the story forward.",
                "The village lights shimmered beyond the river.",
            )
            source = " ".join(lines[index % len(lines)] for index in range(240))
            preview = OUTPUT_ROOT / "qwen-gpu-30-second-preview.wav"
            preview_started = time.perf_counter()
            result = build_voice_preview(
                source,
                provider,
                provider.voice_id,
                preview,
                narration_speed=1.0,
                pacing_profile="off",
                max_chars=1400,
                target_seconds=30.0,
            )
            elapsed = time.perf_counter() - preview_started
            with wave.open(str(result.output_path), "rb") as audio:
                duration = audio.getnframes() / float(audio.getframerate())
            if not 27.0 <= duration <= 33.0:
                raise RuntimeError(f"30-second Qwen GPU preview duration out of tolerance: {duration:.3f}s.")
            if elapsed >= 60.0:
                raise RuntimeError(
                    f"Qwen GPU 30-second preview took {elapsed:.3f}s; the required target is under 60s."
                )
            if not any("cuda" in message.casefold() for message in status_messages):
                raise RuntimeError("Qwen silently fell back to CPU; GPU timing cannot be accepted.")
            if any("cpu" in message.casefold() for message in status_messages[-4:]):
                raise RuntimeError("Qwen preview ended on CPU after a GPU fallback.")
            if provider.recommended_preview_batch_size < 2:
                raise RuntimeError("Qwen GPU preview did not enable the VRAM-qualified batch path.")
            print(
                "REAL_QWEN_GPU_PREVIEW=PASS "
                f"gpu={gpu_query.stdout.strip()} vram_gib={vram_gib:.2f} "
                f"cuda_torch={torch.version.cuda} torch={torch.__version__} "
                f"requested=30s actual={duration:.3f}s elapsed={elapsed:.3f}s "
                f"cold_start_warmup={cold_elapsed:.3f}s batch={provider.recommended_preview_batch_size} "
                "worker_reused=true cpu_fallback=false"
            )
        finally:
            provider.close()


if __name__ == "__main__":
    main()
