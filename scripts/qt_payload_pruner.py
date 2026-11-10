from __future__ import annotations

from pathlib import Path


OPTIONAL_RELEASE_RESOURCES = ("qtwebengine_devtools_resources.debug.pak",)


def prune_optional_qt_assets(dist_root: Path | str) -> list[str]:
    """Remove only optional QtWebEngine DevTools debug payloads from a release build.

    Production UI rendering does not use Chromium DevTools. Required WebEngine
    resources, Qt runtime DLLs, voice models and starter audio are never touched.
    """
    root = Path(dist_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Frozen application directory does not exist: {root}")
    removed: list[str] = []
    for resource_name in OPTIONAL_RELEASE_RESOURCES:
        for path in root.rglob(resource_name):
            if not path.is_file():
                continue
            path.unlink()
            removed.append(path.relative_to(root).as_posix())
    return removed
