"""Strict loading helpers for the installed Premium V2 frontend assets.

Keep these checks independent of Qt so missing, unreadable and empty adapter files
can be regression-tested without launching a WebEngine window.
"""
from __future__ import annotations

import html
import re
from pathlib import Path


class FrontendAssetError(RuntimeError):
    """Raised when an essential packaged frontend asset cannot be loaded."""


def load_premium_v2_adapter(path: Path) -> str:
    """Read a non-empty UTF-8 adapter or fail closed with an actionable error."""
    target = Path(path)
    if not target.is_file():
        raise FrontendAssetError(f"Premium V2 backend adapter is missing: {target}")

    try:
        source = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise FrontendAssetError(
            f"Premium V2 backend adapter could not be read from {target}: {exc}"
        ) from exc

    if not source.strip():
        raise FrontendAssetError(f"Premium V2 backend adapter is empty: {target}")

    return source


def premium_v2_logo_candidates(frontend_file: Path) -> tuple[Path, ...]:
    """Return packaged logo paths in the application's existing icon priority order."""
    assets_directory = Path(frontend_file).parent.parent
    return tuple(
        assets_directory / name
        for name in (
            "ryu_audiobook_logo.png",
            "ryu_audiobook_logo.svg",
            "ryu_audiobook_logo.jpg",
            "ryu_audiobook_logo_master.png",
        )
    )


def prepare_native_host_html(source: str, base_url: str | None = None) -> str:
    """Prepare the approved loader for file-backed desktop startup.

    The packaged host writes this transformed source to a temporary HTML file
    rather than QWebEngineView.setHtml(), whose data-URL path can reject large
    documents. The explicit base URL keeps relative assets resolved against the
    original frontend asset directory.
    """
    if not isinstance(source, str) or not source.strip():
        raise FrontendAssetError("Premium V2 HTML is empty or unreadable.")

    source, timer_count = re.subn(
        r"setTimeout\s*\(\s*finish\s*,\s*1700\s*\)",
        "if (!window.__ryuNativeHost) setTimeout(finish,1700)",
        source,
        count=1,
    )
    if timer_count != 1:
        raise FrontendAssetError(
            "The approved HTML loader auto-dismiss contract was not found; "
            "the native host will not silently substitute a different loading UI."
        )

    base_markup = ""
    if base_url:
        escaped_base = html.escape(str(base_url).strip(), quote=True)
        if not escaped_base:
            raise FrontendAssetError("The Premium V2 asset base URL is empty.")
        base_markup = f'<base href="{escaped_base}">\n'

    def inject_native_setup(match: re.Match[str]) -> str:
        return (
            match.group(1)
            + "\n"
            + base_markup
            + "<script>window.__ryuNativeHost = true;</script>"
        )

    source, head_count = re.subn(
        r"(<head\b[^>]*>)",
        inject_native_setup,
        source,
        count=1,
        flags=re.IGNORECASE,
    )
    if head_count != 1:
        raise FrontendAssetError(
            "The Premium V2 HTML does not contain a head element for native startup setup."
        )

    return source
