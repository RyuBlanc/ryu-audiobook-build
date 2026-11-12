from __future__ import annotations

"""Hardware-gated benchmark for Qwen 1.7B VoiceDesign on AMD ROCm / Intel XPU."""

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import wave

from huggingface_hub import snapshot_download


def main() -> None:
    import torch
    from app.chapters.detector import Chapter
    from app.tts.generator import generate_chapter
    from app.tts.qwen_accelerator import best_accelerator
    from app.tts.expression import DEFAULT_VOICE_DESIGN_ANCHOR_TEXT
    from app.tts.preview import build_voice_preview
    from app.tts.profile_provider import provider_from_profile
    from app.tts import profile_provider as profile_provider_module
    from app.tts.qwen_character_runtime import MODEL_IDS
    from app.tts import qwen_character_runtime as runtime
    from app.tts.providers import qwen_character as provider_module
    from app.tts.providers.qwen_character import QwenCharacterProvider
    from app.tts.voice_profile import VoiceProfile, load_saved_profile, save_profiles

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

    # The production VoiceDesign path uses VoiceDesign once to create the
    # identity anchor, then the installed Base model for chapter narration.
    # Benchmark that exact path separately from the one-pass preview model.
    clone_kind = "base-1.7b"
    clone_model_dir = root / clone_kind
    if not (clone_model_dir / "config.json").is_file():
        snapshot_download(
            repo_id=MODEL_IDS[clone_kind],
            local_dir=str(clone_model_dir),
            allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.npz", "*.bin", "tokenizer*", "vocab*"],
        )

    import unittest.mock as mock

    output_root = Path(os.environ.get(
        "RYU_QWEN_GPU_OUTPUT", Path.cwd() / "qwen-non-nvidia-acceptance"
    ))
    output_root.mkdir(parents=True, exist_ok=True)
    saved_root = output_root / "saved-profiles"
    runtime_model_dirs = {key: root / key for key in MODEL_IDS}
    runtime_env = os.environ.copy()
    runtime_env["HF_HOME"] = str(root / "huggingface")
    runtime_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    runtime_env["PYTHONUTF8"] = "1"
    runtime_env["PYTHONIOENCODING"] = "utf-8"
    runtime_env["TOKENIZERS_PARALLELISM"] = "false"
    preview_metrics = {}

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
        mock.patch.object(profile_provider_module, "get_qwen_model_preference", return_value="1.7b"),
        mock.patch.object(profile_provider_module, "get_qwen_backend_preference", return_value="automatic"),
        mock.patch.object(profile_provider_module, "get_qwen_low_memory_mode", return_value=False),
        mock.patch("app.tts.voice_profile.voices_root", return_value=saved_root),
        mock.patch("app.tts.voice_profile.builtin_voice_profiles", return_value=[]),
    ):
        missing = [kind for kind in ("design-1.7b", "base-1.7b") if not runtime.model_installed(kind)]
        if missing:
            raise RuntimeError("Qwen model integrity verification failed: " + ", ".join(missing))
        design_profile = VoiceProfile(
            name=f"Stage 3 {selected.backend.upper()} Saved VoiceDesign",
            provider="qwen-character",
            voice_id="Ryan",
            model_id="design-1.7b",
            backend="automatic",
            language="English",
            notes="Saved AMD/Intel acceptance VoiceDesign identity.",
            authorized=True,
            qwen_mode="design",
            qwen_prompt="A warm, clear audiobook narrator with natural English articulation, restrained emotion and a stable natural timbre.",
            qwen_seed=20261101,
            qwen_anchor_text=DEFAULT_VOICE_DESIGN_ANCHOR_TEXT,
        )
        save_profiles([design_profile])
        reloaded_design = load_saved_profile(design_profile.name)
        if not reloaded_design or not reloaded_design.qwen_profile_id:
            raise RuntimeError("Saved AMD/Intel VoiceDesign profile did not survive reload.")
        provider, voice = provider_from_profile(reloaded_design)
        if provider.qwen_mode != "design" or provider.model_kind != "design-1.7b":
            raise RuntimeError("AMD/Intel benchmark did not resolve the saved VoiceDesign profile.")
        if provider.long_form_model_kind != "base-1.7b":
            raise RuntimeError(f"Expected the selected 1.7B Base identity-lock path; got {provider.long_form_model_kind!r}.")
        provider.set_status_callback(lambda message: None)
        try:
            warm = output_root / "qwen-non-nvidia-warmup.wav"
            started = time.perf_counter()
            provider.synthesize(
                "Hello. This is a short warm-up sample for the selected Qwen narrator.",
                warm,
                voice,
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
                voice,
                preview,
                narration_speed=1.0,
                pacing_profile="off",
                max_chars=1400,
                target_seconds=30.0,
            )
            elapsed = time.perf_counter() - preview_started
            with wave.open(str(result.output_path), "rb") as audio:
                duration = audio.getnframes() / float(audio.getframerate())

            if not provider.execution_backend_verified or provider.execution_backend != selected.backend:
                raise RuntimeError(
                    "Saved-profile preview did not prove the selected accelerator backend; "
                    f"expected={selected.backend!r} actual={provider.execution_backend!r}."
                )
            if provider.last_execution_context.get("task") != "design":
                raise RuntimeError("Qwen preview did not execute the saved identity-locked design task.")
            if provider._worker is None or provider._worker.poll() is not None:
                raise RuntimeError("Qwen saved-profile worker exited during the preview.")
            if not 27.0 <= duration <= 33.0:
                raise RuntimeError(
                    f"Preview duration out of tolerance: {duration:.3f}s."
                )
            if elapsed >= 60.0:
                raise RuntimeError(
                    f"30-second preview took {elapsed:.3f}s; target is under 60s."
                )
            preview_metrics = {
                "backend": provider.execution_backend,
                "device": provider.last_execution_context.get("device"),
                "model_kind": provider.last_execution_context.get("model_kind"),
                "long_form_base_model": provider.long_form_model_kind,
                "profile_id": reloaded_design.qwen_profile_id,
                "profile_saved_and_reloaded": True,
                "identity_locked_design_task": True,
                "elapsed_seconds": round(elapsed, 3),
                "audio_seconds": round(duration, 3),
                "segments": result.segments,
                "warmup_seconds": round(warm_elapsed, 3),
                "pass_under_60_seconds": elapsed < 60.0,
            }
            print(
                f"REAL_QWEN_{selected.backend.upper()}_SAVED_PROFILE_PREVIEW=PASS "
                f"adapter={selected.name} memory_gb={selected.memory_gb:.2f} "
                f"device={provider.last_execution_context.get('device')} "
                f"base_model={provider.long_form_model_kind} "
                f"actual={duration:.3f}s elapsed={elapsed:.3f}s "
                "profile_reload=true identity_locked=true"
            )
        finally:
            provider.close()

        # Exercise real resumable chapter generation through VoiceDesign's
        # stable identity anchor + Base clone path. Two chapters with eight
        # neutral sentences each produce two four-sentence chunks per chapter.
        # The second chapter is the warmed throughput measurement; the first
        # also includes one-time identity/model preparation.
        production_provider = QwenCharacterProvider(
            voice_id="Stage 3 AMD/Intel production narrator",
            language="English",
            instruct="Warm, clear audiobook narration with natural articulation and steady pacing.",
            backend="automatic",
            model_kind="design-1.7b",
            qwen_mode="design",
            qwen_seed=20261101,
            qwen_profile_id=f"stage3-{selected.backend}-longform-throughput",
        )
        batch_sizes: list[int] = []
        original_synthesize_batch = production_provider.synthesize_batch

        def measured_synthesize_batch(items):
            batch_sizes.append(len(items))
            return original_synthesize_batch(items)

        production_provider.synthesize_batch = measured_synthesize_batch
        long_form_root = output_root / "long-form-throughput"
        long_form_root.mkdir(parents=True, exist_ok=True)
        long_form_results = []
        sentence_bank = [
            "The lantern rested beside the quiet road.",
            "The river moved slowly through the valley.",
            "A distant window glowed above the garden.",
            "The wooden bridge crossed the narrow stream.",
            "Morning light reached the old stone wall.",
            "The village remained peaceful after sunset.",
            "A gentle breeze passed through the trees.",
            "The narrow path continued beyond the hill.",
        ]

        def wav_duration(folder: Path) -> float:
            duration = 0.0
            for wav_path in sorted((folder / "chunks").glob("*.wav")):
                with wave.open(str(wav_path), "rb") as audio:
                    duration += audio.getnframes() / float(audio.getframerate())
            return duration

        try:
            for chapter_number in (1, 2):
                chapter_text = " ".join(sentence_bank)
                chapter = Chapter(
                    chapter_number,
                    f"Qwen Throughput Chapter {chapter_number}",
                    chapter_text,
                )
                generation_started = time.perf_counter()
                generated = generate_chapter(
                    chapter,
                    production_provider,
                    production_provider.voice_id,
                    long_form_root,
                    narration_speed=1.0,
                    pacing_profile="off",
                )
                generation_elapsed = time.perf_counter() - generation_started
                audio_duration = wav_duration(generated.output_path)
                if generated.chunks_total != 2 or generated.chunks_completed != 2:
                    raise RuntimeError(
                        "Qwen production throughput fixture did not generate its expected "
                        f"two valid chapter chunks: {generated.chunks_completed}/{generated.chunks_total}."
                    )
                if audio_duration <= 0:
                    raise RuntimeError("Qwen production throughput fixture generated no readable audio.")
                long_form_results.append({
                    "chapter": chapter_number,
                    "elapsed_seconds": round(generation_elapsed, 3),
                    "audio_seconds": round(audio_duration, 3),
                    "real_time_factor": round(generation_elapsed / audio_duration, 4),
                    "chunks": generated.chunks_completed,
                })

            expected_batching = production_provider.recommended_batch_size >= 2
            if expected_batching and batch_sizes != [2, 2]:
                raise RuntimeError(
                    f"Expected two safe 2-chunk production batches on this GPU, got {batch_sizes}."
                )
            if not expected_batching and batch_sizes:
                raise RuntimeError(
                    f"Unexpected production batching below the VRAM threshold: {batch_sizes}."
                )

            warm_rtf = long_form_results[-1]["real_time_factor"]
            benchmark = {
                "backend": selected.backend,
                "adapter": selected.name,
                "memory_gb": selected.memory_gb,
                "torch": torch.__version__,
                "voice_design_model": MODEL_IDS["design-1.7b"],
                "long_form_base_model": MODEL_IDS[clone_kind],
                "preview_30s": {
                    **preview_metrics,
                    "real_time_factor": round(elapsed / duration, 4),
                },
                "long_form_warmed_chapter": long_form_results[-1],
                "long_form_chapters": long_form_results,
                "production_batch_sizes": batch_sizes,
                "estimated_9_hour_book_hours_at_measured_rtf": round(9.0 * warm_rtf, 3),
                "estimated_10_hour_book_hours_at_measured_rtf": round(10.0 * warm_rtf, 3),
                "note": "Estimates use the warmed production chapter RTF; they exclude model startup, analysis, mixing, packaging and hardware contention.",
            }
            (output_root / "qwen-performance.json").write_text(
                json.dumps(benchmark, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(
                f"REAL_QWEN_{selected.backend.upper()}_LONGFORM=PASS "
                f"warm_elapsed={long_form_results[-1]['elapsed_seconds']:.3f}s "
                f"audio={long_form_results[-1]['audio_seconds']:.3f}s "
                f"rtf={warm_rtf:.4f} "
                f"estimated_9h_book={9.0 * warm_rtf:.2f}h "
                f"estimated_10h_book={10.0 * warm_rtf:.2f}h "
                f"batches={batch_sizes}"
            )
        finally:
            production_provider.close()


if __name__ == "__main__":
    main()
