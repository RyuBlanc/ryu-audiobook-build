from __future__ import annotations

"""Hardware-gated benchmark for Qwen 1.7B VoiceDesign on AMD ROCm / Intel XPU."""

import os
from pathlib import Path
import sys
import time
import wave

from huggingface_hub import snapshot_download


def main() -> None:
    import torch
    from app.tts.qwen_accelerator import best_accelerator
    from app.tts.preview import build_voice_preview
    from app.tts.qwen_character_runtime import MODEL_IDS, RUNTIME_ROOT
    from app.tts import qwen_character_runtime as runtime
    from app.tts import providers
    from app.tts.providers import qwen_character as provider_module
    from app.tts.providers.qwen_character import QwenCharacterProvider

    selected = best_accelerator()
    expected = os.environ.get("RYU_QWEN_EXPECT_BACKEND", "").casefold()
    if selected.backend not in {"rocm", "xpu"}:
        raise RuntimeError(f"Expected AMD ROCm or Intel XPU; detected {selected.backend} ({selected.name}).")
    if expected and selected.backend != expected:
        raise RuntimeError(f"Expected {expected}; detected {selected.backend}.")
    if selected.backend == "rocm" and not str(getattr(torch.version, "hip", "") or ""):
        raise RuntimeError("AMD ROCm device detected but PyTorch is not a ROCm build.")
    if selected.backend == "xpu" and not (getattr(torch, "xpu", None) and torch.xpu.is_available()):
        raise RuntimeError("Intel adapter detected but PyTorch XPU is unavailable.")

    root = Path(os.environ["RYU_QWEN_MODEL_ROOT"]).resolve()
    model_dir = root / "design-1.7b"
    if not (model_dir / "config.json").is_file():
        snapshot_download(
            repo_id="Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
            local_dir=str(model_dir),
            allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.npz", "*.bin", "tokenizer*", "vocab*"],
        )
    if selected.memory_gb and selected.memory_gb < 7.0:
        raise RuntimeError(
            f"{selected.backend} memory {selected.memory_gb:.2f} GiB is below the 7 GiB tier used for 1.7B batched acceptance."
        )

    model_dirs = {key: root / key for key in MODEL_IDS}
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
    env["HF_HOME"] = os.environ.get("HF_HOME", str(root / "huggingface"))

    import unittest.mock as mock

    runtime_model_dirs = {key: root / key for key in MODEL_IDS}
    runtime_env = os.environ.copy()
    runtime_env["HF_HOME"] = str(root / "huggingface")
    runtime_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])

    with (
        mock.patch.object(runtime, "RUNTIME_ROOT", root),
        mock.patch.object(runtime, "MODEL_DIRS", runtime_model_dirs),
        mock.patch.object(runtime, "runtime_ready", return_value=True),
        mock.patch.object(runtime, "verify_runtime", return_value="Qwen non-NVIDIA hardware acceptance"),
        mock.patch.object(provider_module, "RUNTIME_ROOT", root),
        mock.patch.object(provider_module, "runtime_ready", return_value=True),
        mock.patch.object(provider_module, "verify_runtime", return_value="Qwen non-NVIDIA hardware acceptance"),
        mock.patch.object(provider_module, "runtime_python", return_value=Path(sys.executable)),
        mock.patch.object(provider_module, "runtime_environment", return_value=runtime_env),
        mock.patch.object(provider_module, "model_installed", side_effect=lambda kind: runtime.model_installed(kind)),
    ):
        provider = QwenCharacterProvider(
            voice_id="Stage 3 AMD/Intel VoiceDesign",
            language="English",
            instruct="Warm, clear audiobook narration with natural articulation and steady pacing.",
            backend="automatic",
            model_kind="design-1.7b",
            qwen_mode="design-preview",
            qwen_seed=20261101,
            qwen_profile_id=f"stage3-{selected.backend}-30s-preview",
        )
        status = []
        provider.set_status_callback(status.append)
        output_root = Path(os.environ.get(
            "RYU_QWEN_GPU_OUTPUT", Path.cwd() / "qwen-non-nvidia-acceptance"
        ))
        output_root.mkdir(parents=True, exist_ok=True)
        try:
            warm = output_root / "qwen-non-nvidia-warmup.wav"
            started = time.perf_counter()
            provider.synthesize(
                "Hello. This is a short warm-up sample for the selected Qwen narrator.",
                warm,
                provider.voice_id,
            )
            warm_elapsed = time.perf_counter() - started
            with wave.open(str(warm), "rb") as audio:
                if audio.getnframes() <= 0:
                    raise RuntimeError("Warm-up audio file is empty.")

            source = " ".join([
                "The lantern glowed softly beside the quiet road.",
                "Mira listened carefully before she answered.",
                "Rain moved gently across the distant valley.",
                "The old wooden door opened into the hall.",
            ] * 60)
            preview = output_root / "qwen-non-nvidia-30-second-preview.wav"
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

            expected_device = "cuda" if selected.backend == "rocm" else "xpu"
            worker_log = (
                Path.home() / "Ryu's Audiobook" / "Settings"
                / "qwen_character_worker.log"
            )
            log_text = worker_log.read_text(
                encoding="utf-8", errors="replace"
            ) if worker_log.is_file() else ""
            if expected_device not in log_text.casefold() and not any(
                expected_device in message.casefold() for message in status
            ):
                raise RuntimeError(
                    f"Worker evidence does not prove Qwen ran on {selected.backend}."
                )
            if not 27.0 <= duration <= 33.0:
                raise RuntimeError(
                    f"Preview duration out of tolerance: {duration:.3f}s."
                )
            if elapsed >= 60.0:
                raise RuntimeError(
                    f"30-second preview took {elapsed:.3f}s; target is under 60s."
                )
            print(
                f"REAL_QWEN_{selected.backend.upper()}_PREVIEW=PASS "
                f"adapter={selected.name} memory_gb={selected.memory_gb:.2f} "
                f"actual={duration:.3f}s elapsed={elapsed:.3f}s "
                f"warmup={warm_elapsed:.3f}s worker_device={expected_device}"
            )
        finally:
            provider.close()


if __name__ == "__main__":
    main()
