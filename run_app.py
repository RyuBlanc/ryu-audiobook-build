from __future__ import annotations

import os
import sys

# CI/frozen-build self-test: import the modules that previously caused the
# installed EXE to fail at startup, then terminate the process immediately.
# Avoid importing Qt/UI modules here because Qt can keep native worker threads
# alive even after SystemExit in a windowed frozen process.
if "--self-test" in sys.argv:
    # Frozen-package smoke test. It intentionally uses the bundled offline
    # Piper runtime because that path must work immediately after installation,
    # without cloud access or a separately installed voice engine.
    from pathlib import Path
    import tempfile
    import wave

    import app.tts.chatterbox_runtime  # noqa: F401
    import app.tts.providers.chatterbox  # noqa: F401
    from app.tts.providers.piper import PiperProvider

    models = PiperProvider.model_paths()
    if len(models) < 2:
        raise RuntimeError(
            f"Frozen package is missing bundled Piper voices; found {len(models)}."
        )

    output = Path(tempfile.gettempdir()) / "ryu_audiobook_frozen_self_test.wav"
    try:
        provider = PiperProvider(backend="cpu")
        provider.synthesize(
            "Ryu's Audiobook frozen build self test passed.",
            output,
            models[0].stem,
        )
        if not output.exists() or output.stat().st_size < 1024:
            raise RuntimeError("Bundled Piper synthesis produced no valid audio file.")
        with wave.open(str(output), "rb") as handle:
            if handle.getnframes() <= 0 or handle.getframerate() <= 0:
                raise RuntimeError("Bundled Piper synthesis produced invalid WAV audio.")
    finally:
        output.unlink(missing_ok=True)

    marker = os.environ.get("RYU_FROZEN_SELF_TEST_MARKER")
    if marker:
        Path(marker).write_text("ok", encoding="utf-8")
    os._exit(0)

# Explicit module imports are intentional: PyInstaller must see every UI
# module used by the runtime before freezing the application.
import app.ui.voice_page as _voice_page
import app.ui.generation_page as _generation_page
import app.ui.chapter_editor as _chapter_editor
import app.ui.import_page as _import_page
import app.ui.library as _library
import app.ui.hardware_page as _hardware_page
import app.ui.models_page as _models_page

from app.main import main


if __name__ == "__main__":
    raise SystemExit(main())
