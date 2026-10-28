"""Shared rules for global background-audio and fixed-book-cue settings.

The global Voice Only / BGM Off setting overrides the selected BGM strategy and
all fixed Opening, Next Chapter, and Closing cue assignments. Legacy projects
without the explicit enable flag retain their saved auto/manual mode.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _state_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on", "enabled"}


def effective_background_audio_mode(state: Mapping[str, Any]) -> str:
    """Return the persisted mode after applying the global audio-off override."""
    mode = str(state.get("background_audio_mode") or "off").strip().casefold()
    if mode not in {"off", "auto", "manual"}:
        mode = "off"
    if "background_audio_enabled" in state:
        enabled = _state_bool(state.get("background_audio_enabled"))
    else:
        # Older saved projects predate the explicit global-enable flag.
        enabled = mode in {"auto", "manual"}
    return mode if enabled else "off"


def fixed_book_cues_enabled(state: Mapping[str, Any]) -> bool:
    """Fixed book cues are active only when global background audio is active."""
    return effective_background_audio_mode(state) != "off" and _state_bool(
        state.get("chapter_transition_sound", False)
    )
