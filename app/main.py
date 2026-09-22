from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.core.paths import ensure_roots
from app.ui.workflow import ProjectWorkflow


def main() -> int:
    # The Library tab reads the local project directory during startup.
    # Create the local-first data roots before the UI is constructed.
    ensure_roots()

    app = QApplication(sys.argv)
    window = ProjectWorkflow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
