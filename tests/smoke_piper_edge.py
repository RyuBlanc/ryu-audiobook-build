from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from app.tts.providers.edge_tts import EdgeTTSProvider
from app.tts.providers.piper import PiperProvider


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    piper_models = PiperProvider.model_paths()
    if not piper_models:
        raise RuntimeError("No Piper model is available for the provider smoke test.")

    with TemporaryDirectory(prefix="ryu-piper-edge-smoke-") as temp:
        root = Path(temp)
        piper_output = root / "piper.wav"
        PiperProvider(model_path=piper_models[0], backend="cpu").synthesize(
            "This is a short Ryu's Audiobook Piper offline voice test.",
            piper_output,
            voice=piper_models[0].stem,
        )
        if not piper_output.is_file() or piper_output.stat().st_size < 1024:
            raise RuntimeError("Piper produced invalid output.")
        print(f"PIPER_SYNTHESIS=PASS bytes={piper_output.stat().st_size}")

        edge = EdgeTTSProvider()
        edge_output = root / "edge.wav"
        voice = "en-US-AriaNeural"
        edge.synthesize(
            "This is a short Ryu's Audiobook Edge online natural voice test.",
            edge_output,
            voice=voice,
        )
        if not edge_output.is_file() or edge_output.stat().st_size < 1024:
            raise RuntimeError("Edge TTS produced invalid output.")
        print(f"EDGE_TTS_SYNTHESIS=PASS voice={voice} bytes={edge_output.stat().st_size}")


if __name__ == "__main__":
    main()
