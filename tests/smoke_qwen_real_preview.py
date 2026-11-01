"""Actual Qwen3-TTS VoiceDesign worker + warm 30-second preview acceptance.

The hosted runner is CPU-only; the test records (rather than disguises) its
runtime. It exercises the application's actual QwenCharacterProvider worker,
VoiceDesign preview task and build_voice_preview duration controller.
"""
from __future__ import annotations

import os
import json
import sys
import time
import wave
from pathlib import Path
from unittest.mock import patch

from huggingface_hub import snapshot_download

from app.tts.expression import classify_expression
from app.tts.narration import apply_pronunciation_dictionary_with_counts
from app.tts.preview import build_voice_preview
from app.tts.providers.qwen_character import QwenCharacterProvider


ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = Path(os.environ["RYU_QWEN_MODEL_ROOT"]).resolve()
MODEL_DIR = MODEL_ROOT / "design-1.7b"
OUTPUT_ROOT = Path(os.environ.get("RYU_QWEN_ACCEPTANCE_OUTPUT", ROOT / "qwen-real-provider-artifacts"))
MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"


def _duration(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        if audio.getnframes() <= 0:
            raise RuntimeError(f"Qwen returned an empty audio file: {path}")
        return audio.getnframes() / float(audio.getframerate())


def _verify_model() -> None:
    if not (MODEL_DIR / "config.json").is_file():
        raise RuntimeError(f"The actual Qwen VoiceDesign config is missing: {MODEL_DIR}")
    weights = list(MODEL_DIR.glob("*.safetensors"))
    if not weights or any(path.stat().st_size < 1024 for path in weights):
        raise RuntimeError("The actual Qwen VoiceDesign model weights are missing or incomplete.")


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Download the same official Qwen VoiceDesign model ID used by the app.
    if not (MODEL_DIR / "config.json").is_file():
        snapshot_download(
            repo_id=MODEL_ID,
            local_dir=str(MODEL_DIR),
            allow_patterns=[
                "*.json", "*.safetensors", "*.txt", "*.model", "*.npz", "*.bin",
                "tokenizer*", "vocab*",
            ],
        )
    _verify_model()

    # Run the real app worker under the CI Python interpreter. Only the
    # app-private runtime installation/path checks are redirected to the
    # downloaded test model; the worker, model loader and synthesis engine
    # are the production source files.
    worker_env = os.environ.copy()
    worker_env["HF_HOME"] = os.environ.get("HF_HOME") or str(MODEL_ROOT / "huggingface")
    worker_env["PYTHONPATH"] = str(ROOT) + os.pathsep + worker_env.get("PYTHONPATH", "")
    worker_env["PYTHONUTF8"] = "1"
    worker_env["PYTHONIOENCODING"] = "utf-8"
    worker_env["OMP_NUM_THREADS"] = "2"
    worker_env["MKL_NUM_THREADS"] = "2"
    worker_env["OPENBLAS_NUM_THREADS"] = "2"
    worker_env["TOKENIZERS_PARALLELISM"] = "false"

    provider = QwenCharacterProvider(
        voice_id="Stage 3 Qwen VoiceDesign",
        language="English",
        instruct="A warm, clear audiobook narrator with measured pacing and natural articulation.",
        backend="cpu",
        model_kind="design-1.7b",
        qwen_mode="design-preview",
        qwen_seed=20261101,
        qwen_profile_id="stage3-real-qwen-voice-design-preview",
    )

    try:
        with (
            patch("app.tts.providers.qwen_character.runtime_ready", return_value=True),
            patch("app.tts.providers.qwen_character.verify_runtime", return_value="CI Qwen runtime"),
            patch("app.tts.providers.qwen_character.model_installed", side_effect=lambda kind: (MODEL_ROOT / kind / "config.json").is_file()),
            patch("app.tts.providers.qwen_character.runtime_python", return_value=Path(sys.executable)),
            patch("app.tts.providers.qwen_character.RUNTIME_ROOT", MODEL_ROOT),
            patch("app.tts.providers.qwen_character.runtime_environment", return_value=worker_env),
        ):
            # Warm the actual persistent worker before measuring the preview
            # click path. Cold load/startup is reported separately.
            warmup_path = OUTPUT_ROOT / "qwen-voicedesign-warmup.wav"
            cold_started = time.perf_counter()
            provider.synthesize(
                "Hello. This is a short warm-up sample for the selected narrator.",
                warmup_path,
                voice="Stage 3 Qwen VoiceDesign",
            )
            cold_elapsed = time.perf_counter() - cold_started
            if not warmup_path.is_file() or warmup_path.stat().st_size < 1024:
                raise RuntimeError("The actual Qwen VoiceDesign worker did not produce warm-up audio.")
            worker = provider._worker
            if worker is None or worker.poll() is not None:
                raise RuntimeError("The Qwen worker did not remain available after warm-up.")
            worker_pid = worker.pid

            sentences = (
                "The lantern glowed softly beside the quiet road.",
                "Mira listened carefully before she answered.",
                "Rain moved gently across the distant valley.",
                "The old wooden door opened into the hall.",
                "A calm narrator guided the story forward.",
                "The village lights shimmered beyond the river.",
            )
            source_text = " ".join(sentences[index % len(sentences)] for index in range(240))
            preview_path = OUTPUT_ROOT / "qwen-voicedesign-preview-30s.wav"
            started = time.perf_counter()
            result = build_voice_preview(
                source_text,
                provider,
                "Stage 3 Qwen VoiceDesign",
                preview_path,
                narration_speed=1.0,
                pacing_profile="off",
                max_chars=1400,
                target_seconds=30.0,
            )
            elapsed = time.perf_counter() - started
            actual = _duration(result.output_path)
            if not 27.0 <= actual <= 33.0:
                raise RuntimeError(
                    f"Actual Qwen VoiceDesign preview duration is outside tolerance: {actual:.3f}s"
                )
            if provider._worker is None or provider._worker.pid != worker_pid or provider._worker.poll() is not None:
                raise RuntimeError("The actual Qwen worker was not reused for the 30-second preview.")

            emotion_texts = (
                ("warm", "She felt delighted and happy."),
                ("angry", "He was angry and furious."),
            )
            for style, text in emotion_texts:
                detected = classify_expression(text)
                if detected != style:
                    raise RuntimeError(
                        f"Emotion fixture mismatch: text={text!r} expected={style} detected={detected}"
                    )
                output = OUTPUT_ROOT / f"qwen-voicedesign-{style}.wav"
                provider.synthesize(text, output, voice="Stage 3 Qwen VoiceDesign")
                if not output.is_file() or output.stat().st_size < 1024:
                    raise RuntimeError(f"Qwen did not produce real {style} expression audio.")

            print(
                "REAL_QWEN_VOICEDESIGN_PREVIEW=PASS "
                f"model={MODEL_ID} device=cpu requested=30s actual={actual:.3f}s "
                f"warm_preview_elapsed={elapsed:.3f}s cold_start_plus_warmup={cold_elapsed:.3f}s "
                f"segments={result.segments} worker_reused=true"
            )
            print(
                "REAL_QWEN_EXPRESSION_AUDIO=PASS "
                "styles=warm,angry model=Qwen-VoiceDesign"
            )

            japanese_preview_path = OUTPUT_ROOT / "qwen-voicedesign-japanese-pronunciation.wav"
            japanese_result = build_voice_preview(
                "Rimuruが来た。",
                provider,
                "Stage 3 Qwen VoiceDesign",
                japanese_preview_path,
                pronunciation_dictionary=[
                    {
                        "written_form": "Rimuru",
                        "spoken_form": "リムル",
                        "enabled": True,
                    }
                ],
                narration_speed=1.0,
                pacing_profile="off",
                max_chars=100,
                target_seconds=2.0,
            )
            expected_spoken, expected_counts = apply_pronunciation_dictionary_with_counts(
                "Rimuruが来た。",
                [{"written_form": "Rimuru", "spoken_form": "リムル", "enabled": True}],
            )
            actual_spoken = "".join(str(japanese_result.source_text or "").split())
            expected_compact = "".join(expected_spoken.split())
            actual_rule_count = sum(
                int(count)
                for written, count in (japanese_result.applied_rule_counts or {}).items()
                if str(written).casefold() == "rimuru"
            )
            japanese_diagnostics = {
                "expected_source_text": expected_spoken,
                "actual_source_text": japanese_result.source_text,
                "expected_rule_counts": expected_counts,
                "actual_rule_counts": japanese_result.applied_rule_counts,
                "actual_rule_count": actual_rule_count,
                "audio_bytes": japanese_preview_path.stat().st_size if japanese_preview_path.is_file() else 0,
            }
            (OUTPUT_ROOT / "qwen-japanese-preview-result.json").write_text(
                json.dumps(japanese_diagnostics, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print("QWEN_JAPANESE_PREVIEW_DIAGNOSTICS=" + json.dumps(japanese_diagnostics, ensure_ascii=False))
            if actual_spoken != expected_compact:
                raise RuntimeError(
                    "Qwen Japanese preview source text did not match the normalized saved pronunciation: "
                    + json.dumps(japanese_diagnostics, ensure_ascii=False)
                )
            if actual_rule_count != int(expected_counts.get("Rimuru", 0)) or actual_rule_count != 1:
                raise RuntimeError(
                    "Qwen Japanese preview did not apply the saved pronunciation rule exactly once: "
                    + json.dumps(japanese_diagnostics, ensure_ascii=False)
                )
            if not japanese_preview_path.is_file() or japanese_preview_path.stat().st_size < 1024:
                raise RuntimeError("Qwen did not produce Japanese pronunciation preview audio.")
            print(
                "REAL_QWEN_JAPANESE_PRONUNCIATION=PASS "
                f"actual={_duration(japanese_preview_path):.3f}s "
                "language=Auto spoken_form=リムル"
            )
            print(
                "QWEN_VS01_CPU_60S_TARGET="
                + ("MET" if elapsed < 60.0 else "NOT_MET_ON_HOSTED_CPU")
            )
    finally:
        try:
            provider.close()
        except Exception as exc:
            diagnostic = {"provider_close_error": repr(exc), "worker_pid": getattr(getattr(provider, "_worker", None), "pid", None)}
            (OUTPUT_ROOT / "qwen-provider-close-error.json").write_text(
                json.dumps(diagnostic, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print("QWEN_PROVIDER_CLOSE_ERROR=" + json.dumps(diagnostic, ensure_ascii=False))
            raise


if __name__ == "__main__":
    main()
