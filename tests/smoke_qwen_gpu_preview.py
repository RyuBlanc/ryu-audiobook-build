"""NVIDIA acceptance: warmed, saved-profile Qwen VoiceDesign preview.

This follows Voice Studio's persisted VoiceProfile -> provider_from_profile path.
It measures the identity-locked VoiceDesign + Base engine, not the legacy
one-pass design-preview worker. CPU fallback is a failure, not a GPU pass.
"""
from __future__ import annotations

import json
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
MODEL_ALLOW_PATTERNS = [
    "*.json", "*.safetensors", "*.txt", "*.model", "*.npz",
    "*.bin", "tokenizer*", "vocab*",
]


def main() -> None:
    import torch
    from app.tts.expression import DEFAULT_VOICE_DESIGN_ANCHOR_TEXT
    from app.tts.preview import build_voice_preview
    from app.tts.profile_provider import provider_from_profile
    from app.tts import profile_provider as profile_provider_module
    from app.tts import qwen_character_runtime as runtime
    from app.tts.providers import qwen_character as provider_module
    from app.tts.qwen_character_runtime import MODEL_IDS
    from app.tts.voice_profile import VoiceProfile, load_saved_profile, save_profiles

    if not torch.cuda.is_available() or not torch.version.cuda:
        raise RuntimeError("NVIDIA acceptance requires a CUDA-enabled PyTorch runtime.")
    device_index = torch.cuda.current_device()
    vram_gib = float(torch.cuda.get_device_properties(device_index).total_memory) / (1024 ** 3)
    if vram_gib < 7.0:
        raise RuntimeError(f"Unsupported NVIDIA tier: {vram_gib:.2f} GiB VRAM; >=7 GiB is required.")
    gpu_query = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
    )
    if gpu_query.returncode != 0 or not gpu_query.stdout.strip():
        raise RuntimeError("nvidia-smi could not identify the NVIDIA GPU and driver.")
    gpu_name = torch.cuda.get_device_name(device_index)

    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    for kind in ("design-1.7b", "base-1.7b"):
        model_dir = MODEL_ROOT / kind
        if not (model_dir / "config.json").is_file():
            snapshot_download(repo_id=MODEL_IDS[kind], local_dir=str(model_dir), allow_patterns=MODEL_ALLOW_PATTERNS)

    model_dirs = {key: MODEL_ROOT / key for key in MODEL_IDS}
    output_root = Path(os.environ.get("RYU_QWEN_GPU_OUTPUT", ROOT / "qwen-gpu-acceptance"))
    output_root.mkdir(parents=True, exist_ok=True)
    saved_root = output_root / "saved-profiles"
    env = os.environ.copy()
    env["HF_HOME"] = os.environ.get("HF_HOME", str(MODEL_ROOT / "huggingface"))
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["TOKENIZERS_PARALLELISM"] = "false"

    with (
        patch.object(runtime, "RUNTIME_ROOT", MODEL_ROOT),
        patch.object(runtime, "MODEL_DIRS", model_dirs),
        patch.object(runtime, "runtime_ready", return_value=True),
        patch.object(runtime, "verify_runtime", return_value="NVIDIA Qwen profile acceptance"),
        patch.object(provider_module, "RUNTIME_ROOT", MODEL_ROOT),
        patch.object(provider_module, "runtime_ready", return_value=True),
        patch.object(provider_module, "verify_runtime", return_value="NVIDIA Qwen profile acceptance"),
        patch.object(provider_module, "runtime_python", return_value=Path(sys.executable)),
        patch.object(provider_module, "runtime_environment", return_value=env),
        patch.object(provider_module, "model_installed", side_effect=lambda kind: runtime.model_installed(kind)),
        patch.object(profile_provider_module, "get_qwen_model_preference", return_value="1.7b"),
        patch.object(profile_provider_module, "get_qwen_backend_preference", return_value="automatic"),
        patch.object(profile_provider_module, "get_qwen_low_memory_mode", return_value=False),
        patch("app.tts.voice_profile.voices_root", return_value=saved_root),
        patch("app.tts.voice_profile.builtin_voice_profiles", return_value=[]),
    ):
        missing = [kind for kind in ("design-1.7b", "base-1.7b") if not runtime.model_installed(kind)]
        if missing:
            raise RuntimeError("Qwen model integrity verification failed: " + ", ".join(missing))
        design_profile = VoiceProfile(
            name="Stage 3 NVIDIA Saved VoiceDesign",
            provider="qwen-character",
            voice_id="Ryan",
            model_id="design-1.7b",
            backend="automatic",
            language="English",
            notes="Saved NVIDIA acceptance VoiceDesign identity.",
            authorized=True,
            qwen_mode="design",
            qwen_prompt="A warm, clear audiobook narrator with natural English articulation, restrained emotion and a stable natural timbre.",
            qwen_seed=20261101,
            qwen_anchor_text=DEFAULT_VOICE_DESIGN_ANCHOR_TEXT,
        )
        save_profiles([design_profile])
        reloaded_design = load_saved_profile(design_profile.name)
        if not reloaded_design or not reloaded_design.qwen_profile_id:
            raise RuntimeError("Saved NVIDIA VoiceDesign profile did not survive reload.")
        provider, voice = provider_from_profile(reloaded_design)
        if provider.qwen_mode != "design" or provider.model_kind != "design-1.7b":
            raise RuntimeError("NVIDIA benchmark did not resolve the saved VoiceDesign profile.")
        if provider.long_form_model_kind != "base-1.7b":
            raise RuntimeError(f"Expected the selected 1.7B Base identity-lock path; got {provider.long_form_model_kind!r}.")
        provider.set_status_callback(lambda message: None)
        try:
            warmup = output_root / "qwen-gpu-profile-warmup.wav"
            warmup_started = time.perf_counter()
            provider.synthesize("Hello. This is a short warm-up sample for the saved Qwen narrator.", warmup, voice)
            warmup_elapsed = time.perf_counter() - warmup_started
            with wave.open(str(warmup), "rb") as audio:
                if audio.getnframes() <= 0:
                    raise RuntimeError("Saved-profile Qwen GPU warm-up audio is empty.")
            worker = provider._worker
            if worker is None or worker.poll() is not None:
                raise RuntimeError("Qwen profile worker did not remain alive after warm-up.")
            worker_pid = worker.pid

            lines = (
                "The lantern glowed softly beside the quiet road.",
                "Mira listened carefully before she answered.",
                "Rain moved gently across the distant valley.",
                "The old wooden door opened into the hall.",
                "A calm narrator guided the story forward.",
                "The village lights shimmered beyond the river.",
            )
            source = " ".join(lines[index % len(lines)] for index in range(240))
            preview = output_root / "qwen-gpu-saved-profile-30-second-preview.wav"
            preview_started = time.perf_counter()
            result = build_voice_preview(
                source, provider, voice, preview,
                narration_speed=1.0, pacing_profile="off", max_chars=1400, target_seconds=30.0,
            )
            elapsed = time.perf_counter() - preview_started
            with wave.open(str(result.output_path), "rb") as audio:
                duration = audio.getnframes() / float(audio.getframerate())
            if not 27.0 <= duration <= 33.0:
                raise RuntimeError(f"Saved-profile preview duration is {duration:.3f}s, expected 27–33s.")
            if elapsed >= 60.0:
                raise RuntimeError(f"Saved-profile Qwen GPU preview took {elapsed:.3f}s; target is under 60s.")
            if not provider.execution_backend_verified or provider.execution_backend != "cuda":
                raise RuntimeError(f"Saved-profile preview did not prove CUDA inference: {provider.execution_backend!r}.")
            if provider.last_execution_context.get("task") != "design":
                raise RuntimeError("Qwen preview did not execute the saved identity-locked design task.")
            if provider._worker is None or provider._worker.pid != worker_pid or provider._worker.poll() is not None:
                raise RuntimeError("Qwen preview did not reuse the warmed saved-profile worker.")
            batch_size = provider.recommended_preview_batch_size
            expected_batch_size = 2 if vram_gib >= 12.0 else 1
            if batch_size != expected_batch_size:
                raise RuntimeError(f"Unexpected safe preview batch {batch_size}; expected {expected_batch_size} for {vram_gib:.2f} GiB.")
            benchmark = {
                "backend": provider.execution_backend,
                "device": provider.last_execution_context.get("device"),
                "model_kind": provider.last_execution_context.get("model_kind"),
                "gpu": gpu_name,
                "driver": gpu_query.stdout.strip(),
                "vram_gib": round(vram_gib, 3),
                "torch": torch.__version__,
                "cuda_torch": torch.version.cuda,
                "voice_design_model": MODEL_IDS["design-1.7b"],
                "long_form_base_model": provider.long_form_model_kind,
                "saved_profile_id": reloaded_design.qwen_profile_id,
                "saved_profile_reloaded": True,
                "identity_locked_design_task": True,
                "preview_30s": {
                    "elapsed_seconds": round(elapsed, 3),
                    "audio_seconds": round(duration, 3),
                    "segments": result.segments,
                    "batch_size": batch_size,
                    "pass_under_60_seconds": elapsed < 60.0,
                },
                "warmup_seconds": round(warmup_elapsed, 3),
                "worker_reused": True,
                "cpu_fallback": False,
            }
            (output_root / "qwen-performance.json").write_text(json.dumps(benchmark, ensure_ascii=False, indent=2), encoding="utf-8")
            print(
                "REAL_QWEN_NVIDIA_SAVED_PROFILE_PREVIEW=PASS "
                f"gpu={gpu_name} vram_gib={vram_gib:.2f} device={provider.last_execution_context.get('device')} "
                f"base_model={provider.long_form_model_kind} requested=30s actual={duration:.3f}s "
                f"elapsed={elapsed:.3f}s warmup={warmup_elapsed:.3f}s batch={batch_size} "
                "profile_reload=true identity_locked=true worker_reused=true"
            )
        finally:
            provider.close()


if __name__ == "__main__":
    main()
