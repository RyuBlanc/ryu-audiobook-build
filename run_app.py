from __future__ import annotations

import os
import sys

# CI/frozen-build self-test. Keep this deliberately minimal: importing the
# provider package also imports every TTS backend and can initialize native
# libraries/Qt that keep a windowed process alive. The original frozen crash
# was a missing chatterbox_runtime module, so verify that module directly.
if "--self-test" in sys.argv:
    import app.tts.chatterbox_runtime as _runtime

    if not hasattr(_runtime, "runtime_ready") or not hasattr(_runtime, "worker_script"):
        os._exit(2)
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
