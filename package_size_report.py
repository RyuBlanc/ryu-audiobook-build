from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_TARGET_BYTES = 500_000_000  # 500 MB (decimal)


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _tree_size(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    if path.is_file():
        return _file_size(path), 1
    total = 0
    count = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
                count += 1
            except OSError:
                continue
    return total, count


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return str(path)


def build_report(
    repo_root: Path | str,
    dist_dir: Path | str | None = None,
    target_bytes: int = DEFAULT_TARGET_BYTES,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    dist = Path(dist_dir).resolve() if dist_dir is not None else root / "dist" / "Ryu's Audiobook"
    files = sorted(
        (path for path in dist.rglob("*") if path.is_file()),
        key=lambda path: _file_size(path),
        reverse=True,
    ) if dist.is_dir() else []
    total_bytes = sum(_file_size(path) for path in files)
    top_level = []
    if dist.is_dir():
        for path in sorted(dist.iterdir(), key=lambda item: item.name.lower()):
            size, count = _tree_size(path)
            top_level.append({
                "name": path.name,
                "kind": "directory" if path.is_dir() else "file",
                "size_bytes": size,
                "file_count": count,
            })

    def asset_dir(relative: Path) -> Path:
        candidates = (dist / relative, dist / "_internal" / relative)
        return next((path for path in candidates if path.is_dir()), candidates[0])

    offline_paths = {
        "piper_models": asset_dir(Path("bundled_models") / "piper"),
        "kokoro_models": asset_dir(Path("bundled_models") / "kokoro"),
        "starter_audio": asset_dir(Path("assets") / "starter_audio"),
    }
    offline = {}
    for name, path in offline_paths.items():
        size, count = _tree_size(path)
        offline[name] = {"path": _relative(path, dist), "size_bytes": size, "file_count": count}

    runtime_names = ("PySide6", "onnxruntime", "kokoro_onnx", "piper", "imageio_ffmpeg", "espeakng_loader")
    runtime = {}
    for name in runtime_names:
        matches = [path for path in dist.rglob(name) if path.is_dir()]
        entries = []
        for path in matches:
            size, count = _tree_size(path)
            entries.append({"path": _relative(path, dist), "size_bytes": size, "file_count": count})
        runtime[name] = {
            "total_bytes": sum(item["size_bytes"] for item in entries),
            "paths": entries,
        }

    installer_dir = root / "installer" / "installer-output"
    html_installer = installer_dir / "Ryu's Audiobook Setup.exe"
    core_installer = installer_dir / "Ryu's Audiobook Core Setup.exe"
    app_exe = dist / "Ryu's Audiobook.exe"
    html_bytes = _file_size(html_installer)
    core_bytes = _file_size(core_installer)
    app_exe_bytes = _file_size(app_exe)
    payload_info_path = installer_dir / "payload_info.generated.json"
    payload_info: dict[str, Any] = {}
    if payload_info_path.is_file():
        try:
            payload_info = json.loads(payload_info_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload_info = {"read_error": True}

    return {
        "build": {
            "commit_sha": os.environ.get("GITHUB_SHA", ""),
            "run_number": os.environ.get("GITHUB_RUN_NUMBER", ""),
            "app_version": payload_info.get("version", ""),
        },
        "target_bytes": int(target_bytes),
        "dist": {
            "path": _relative(dist, root),
            "total_bytes": total_bytes,
            "file_count": len(files),
            "target_met": total_bytes <= target_bytes,
            "top_level": top_level,
            "largest_files": [
                {"path": _relative(path, dist), "size_bytes": _file_size(path)}
                for path in files[:50]
            ],
        },
        "offline_assets": offline,
        "runtime_components": runtime,
        "installers": {
            "html_setup_bytes": html_bytes,
            "core_setup_bytes": core_bytes,
            "html_wrapper_overhead_bytes": max(0, html_bytes - core_bytes) if html_bytes and core_bytes else 0,
            "application_exe_bytes": app_exe_bytes,
            "html_setup_target_met": bool(html_bytes and html_bytes <= target_bytes),
            "core_setup_target_met": bool(core_bytes and core_bytes <= target_bytes),
        },
        "payload_info": payload_info,
        "notes": [
            "No assets are removed or excluded by this report.",
            "The dist total is the installed portable payload before GitHub artifact ZIP compression.",
            "The HTML setup wrapper embeds the core installer; HTML-minus-core is a size-delta estimate, not a per-file runtime attribution.",
            "Use largest_files and runtime_components to identify candidates for optional packaging, not as permission to remove required offline assets.",
        ],
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Report Windows package size by component.")
    parser.add_argument("--dist", type=Path, default=None, help="Frozen application directory.")
    parser.add_argument("--output", type=Path, default=Path("package-size-report.json"))
    parser.add_argument("--target-mb", type=int, default=500)
    args = parser.parse_args()
    report = build_report(Path(__file__).resolve().parent, args.dist, args.target_mb * 1_000_000)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "Package size report created: "
        f"dist={report['dist']['total_bytes']} bytes, "
        f"files={report['dist']['file_count']}, "
        f"HTML setup={report['installers']['html_setup_bytes']} bytes, "
        f"core setup={report['installers']['core_setup_bytes']} bytes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
