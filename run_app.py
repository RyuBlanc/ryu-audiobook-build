from __future__ import annotations

import sys

# CI/frozen-build self-test: import the modules most likely to be lost by PyInstaller
# before loading the full GUI. This must exit quickly with a non-zero code on failure.
if "--self-test" in sys.argv:
    import app.tts.chatterbox_runtime  # noqa: F401
    import app.tts.providers.chatterbox  # noqa: F401
    import app.ui.voice_page  # noqa: F401
    raise SystemExit(0)

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
