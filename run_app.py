from __future__ import annotations

# Explicit imports are intentional: PyInstaller must see every UI module
# used by the runtime before freezing the application.
from app.ui import voice_page as _voice_page
from app.ui import generation_page as _generation_page
from app.ui import chapter_editor as _chapter_editor
from app.ui import import_page as _import_page
from app.ui import library as _library
from app.ui import hardware_page as _hardware_page
from app.ui import models_page as _models_page

from app.main import main


if __name__ == "__main__":
    raise SystemExit(main())
