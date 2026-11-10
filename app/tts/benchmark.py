from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import time
import wave

from app.tts.base import TTSProvider


@dataclass(frozen=True)
class BenchmarkResult:
    provider: str
    backend: str
    seconds: float
    audio_seconds: float
    realtime_factor: float
    success: bool
    error: str = ""
    requested_backend: str = ""
    execution_providers: tuple[str, ...] = ()
    backend_verified: bool = False


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        return frames / rate if rate else 0.0


def benchmark_provider(
    provider: TTSProvider,
    voice: str | None = None,
    backend: str = "cpu",
    text: str = (
        "This is a short Ryu's Audiobook performance test. "
        "The result measures actual local synthesis speed on this computer."
    ),
) -> BenchmarkResult:
    started = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="ryu-tts-bench-") as tmp:
            output = Path(tmp) / "benchmark.wav"
            provider.synthesize(text, output, voice=voice)
            elapsed = time.perf_counter() - started
            duration = _wav_duration(output)
            rtf = elapsed / duration if duration > 0 else 0.0
            requested_backend = str(backend or "automatic")
            verified = bool(getattr(provider, "execution_backend_verified", False))
            actual_backend = str(getattr(provider, "execution_backend", "") or "")
            execution_providers = tuple(
                str(item) for item in (getattr(provider, "execution_providers", ()) or ())
            )
            reported_backend = actual_backend if verified and actual_backend else (
                "unverified" if hasattr(provider, "execution_backend") else requested_backend
            )
            return BenchmarkResult(
                provider=provider.__class__.__name__,
                backend=reported_backend,
                seconds=elapsed,
                audio_seconds=duration,
                realtime_factor=rtf,
                success=True,
                requested_backend=requested_backend,
                execution_providers=execution_providers,
                backend_verified=verified,
            )
    except Exception as exc:
        return BenchmarkResult(
            provider=provider.__class__.__name__,
            backend=backend,
            seconds=time.perf_counter() - started,
            audio_seconds=0.0,
            realtime_factor=0.0,
            success=False,
            error=str(exc),
            requested_backend=str(backend or "automatic"),
            execution_providers=tuple(
                str(item) for item in (getattr(provider, "execution_providers", ()) or ())
            ),
            backend_verified=bool(getattr(provider, "execution_backend_verified", False)),
        )
