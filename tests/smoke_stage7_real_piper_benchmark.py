from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _resource_snapshot() -> dict:
    snapshot = {"cpu_percent": None, "process_cpu_percent": None,
                "ram_total_bytes": None, "ram_available_bytes": None,
                "process_rss_bytes": None}
    try:
        import psutil
        process = psutil.Process()
        snapshot["process_cpu_percent"] = float(process.cpu_percent(interval=None))
        snapshot["process_rss_bytes"] = int(process.memory_info().rss)
        vm = psutil.virtual_memory()
        snapshot["cpu_percent"] = float(psutil.cpu_percent(interval=None))
        snapshot["ram_total_bytes"] = int(vm.total)
        snapshot["ram_available_bytes"] = int(vm.available)
    except Exception as exc:
        snapshot["resource_error"] = f"{type(exc).__name__}: {exc}"
    return snapshot


def _gpu_snapshot() -> dict:
    result = {"name": None, "utilization_percent": None,
              "memory_used_mb": None, "memory_total_mb": None,
              "source": None}
    executable = None
    for candidate in ("nvidia-smi", "rocm-smi"):
        from shutil import which
        executable = which(candidate)
        if executable:
            result["source"] = candidate
            break
    if executable and result["source"] == "nvidia-smi":
        try:
            completed = subprocess.run(
                [executable, "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5, check=True,
            )
            fields = [item.strip() for item in completed.stdout.strip().splitlines()[0].split(",")]
            result.update({
                "name": fields[0],
                "utilization_percent": float(fields[1]),
                "memory_used_mb": float(fields[2]),
                "memory_total_mb": float(fields[3]),
            })
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
    elif executable:
        try:
            completed = subprocess.run(
                [executable, "--showuse", "--showmeminfo", "vram"],
                capture_output=True, text=True, timeout=5, check=True,
            )
            result["raw_summary"] = (completed.stdout or completed.stderr).strip()[-2000:]
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _capture_onnx_providers():
    import onnxruntime as ort
    original = ort.InferenceSession
    sessions = []

    def tracked_session(*args, **kwargs):
        session = original(*args, **kwargs)
        sessions.append(session)
        return session

    ort.InferenceSession = tracked_session
    return ort, original, sessions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="stage7-piper-benchmark.json")
    args = parser.parse_args()

    from app.tts.benchmark import benchmark_provider
    from app.tts.providers.piper import PiperProvider

    bundled_root = ROOT / "bundled_models" / "piper"
    voices = sorted(path for path in bundled_root.glob("*.onnx") if path.is_file())
    if not voices:
        raise RuntimeError(f"No bundled Piper ONNX voices were found under {bundled_root}.")
    voice = voices[0]
    if not voice.with_suffix(voice.suffix + ".json").is_file():
        raise RuntimeError(f"The bundled Piper voice configuration is missing for {voice.name}.")

    provider = PiperProvider(model_path=voice, backend="automatic")
    before = _resource_snapshot()
    gpu_before = _gpu_snapshot()
    ort, original_session, sessions = _capture_onnx_providers()
    started = time.perf_counter()
    try:
        measured = benchmark_provider(
            provider,
            voice=voice.stem,
            backend="automatic",
            text=(
                "This is the Ryu Audiobook local performance verification. "
                "The application measures real synthesis time, generated audio duration, "
                "and resource usage using the bundled offline voice."
            ),
        )
    finally:
        ort.InferenceSession = original_session
    wall_seconds = time.perf_counter() - started
    after = _resource_snapshot()
    gpu_after = _gpu_snapshot()

    if not measured.success or measured.audio_seconds <= 0:
        raise RuntimeError(
            "Real bundled Piper synthesis did not produce valid audio: "
            + (measured.error or "audio duration was zero")
        )

    provider_sets = []
    for session in sessions:
        try:
            provider_sets.append(list(session.get_providers()))
        except Exception:
            continue
    providers = provider_sets[-1] if provider_sets else []
    if not providers:
        raise RuntimeError(
            "Piper generated audio, but the ONNX Runtime session did not expose its "
            "actual execution providers; refusing to claim a verified inference backend."
        )
    if "CUDAExecutionProvider" in providers:
        inference_backend = "cuda"
    elif "DmlExecutionProvider" in providers:
        inference_backend = "directml"
    elif "CPUExecutionProvider" in providers:
        inference_backend = "cpu"
    else:
        inference_backend = "other"

    try:
        from app.tts.qwen_accelerator import detect_accelerators
        accelerators = [
            {
                "backend": item.backend,
                "name": item.name,
                "device": item.device,
                "memory_gb": round(float(item.memory_gb), 2),
                "supported": bool(item.supported),
                "reason": item.reason,
            }
            for item in detect_accelerators(refresh=True)
        ]
    except Exception as exc:
        accelerators = [{"error": f"{type(exc).__name__}: {exc}"}]

    report = {
        "schema": "ryu.stage7.piper-benchmark.v1",
        "benchmark_type": "real-local-piper-synthesis",
        "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": {
            "platform": platform.platform(),
            "processor": platform.processor() or platform.machine(),
            "python": platform.python_version(),
        },
        "voice": voice.stem,
        "model_file": voice.name,
        "model_size_bytes": voice.stat().st_size,
        "synthesis_seconds": float(measured.seconds),
        "audio_seconds": float(measured.audio_seconds),
        "realtime_factor": float(measured.realtime_factor),
        "wall_seconds": wall_seconds,
        "inference_backend": inference_backend,
        "inference_backend_verified": True,
        "onnxruntime_execution_providers": providers,
        "onnxruntime_provider_chain": provider_sets,
        "resources_before": before,
        "resources_after": after,
        "gpu_before": gpu_before,
        "gpu_after": gpu_after,
        "qwen_accelerator_inventory": accelerators,
        "success": True,
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        summary = (
            "## Stage 7 — Real bundled Piper benchmark\n\n"
            f"- Voice: {voice.stem}\n"
            f"- Synthesis: {measured.seconds:.3f}s\n"
            f"- Generated audio: {measured.audio_seconds:.3f}s\n"
            f"- RTF: {measured.realtime_factor:.3f}\n"
            f"- Actual ONNX execution backend: {inference_backend}\n"
            f"- ONNX providers: {', '.join(providers)}\n"
            f"- Process RSS after synthesis: {after.get('process_rss_bytes')} bytes\n"
            f"- System RAM available after synthesis: {after.get('ram_available_bytes')} bytes\n"
        )
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write(summary)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"STAGE7_PIPER_BENCHMARK_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
