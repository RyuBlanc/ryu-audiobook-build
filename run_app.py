from __future__ import annotations

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
