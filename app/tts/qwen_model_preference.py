"""Persistent global Qwen model-size preference.

The preference is intentionally application-wide: it is resolved whenever a
saved or newly-created Qwen voice profile is turned into a synthesis provider.
"""
from __future__ import annotations

VALID_QWEN_MODEL_PREFERENCES = {"auto", "0.6b", "1.7b"}
QWEN_MODEL_PREFERENCE_KEY = "qwen/model_size_preference"
QWEN_SETTINGS_ORGANIZATION = "RyuBlanc"
QWEN_SETTINGS_APPLICATION = "Ryu's Audiobook"


def normalize_qwen_model_preference(value: object) -> str:
    selected = str(value or "auto").strip().casefold()
    return selected if selected in VALID_QWEN_MODEL_PREFERENCES else "auto"


def get_qwen_model_preference() -> str:
    """Return the persisted global preference; Auto preserves existing selection."""
    try:
        from PySide6.QtCore import QSettings
        settings = QSettings(QWEN_SETTINGS_ORGANIZATION, QWEN_SETTINGS_APPLICATION)
        return normalize_qwen_model_preference(
            settings.value(QWEN_MODEL_PREFERENCE_KEY, "auto")
        )
    except Exception:
        return "auto"


def set_qwen_model_preference(value: object) -> str:
    """Persist Auto, 0.6B, or 1.7B and return the normalized selection."""
    selected = normalize_qwen_model_preference(value)
    from PySide6.QtCore import QSettings
    settings = QSettings(QWEN_SETTINGS_ORGANIZATION, QWEN_SETTINGS_APPLICATION)
    settings.setValue(QWEN_MODEL_PREFERENCE_KEY, selected)
    settings.sync()
    status = settings.status()
    if status != QSettings.Status.NoError:
        raise OSError("Ryu could not save the global Qwen model preference.")
    return selected


def qwen_model_kinds_for_preference(
    mode: str, preference: object | None = None
) -> tuple[str | None, str | None]:
    """Return (active model kind, VoiceDesign long-form Base kind).

    VoiceDesign creation/audition is intrinsically the 1.7B VoiceDesign model.
    The global size preference chooses its Base narration model instead.
    """
    selected = normalize_qwen_model_preference(
        get_qwen_model_preference() if preference is None else preference
    )
    if selected == "auto":
        return None, None

    phase = str(mode or "custom").strip().casefold()
    suffix = selected
    if phase in {"design", "design-preview"}:
        return "design-1.7b", (f"base-{suffix}" if phase == "design" else None)
    if phase == "clone":
        return f"base-{suffix}", None
    return f"custom-{suffix}", None


def qwen_model_preference_label(value: object | None = None) -> str:
    selected = normalize_qwen_model_preference(
        get_qwen_model_preference() if value is None else value
    )
    return {
        "auto": "Automatic (hardware-aware)",
        "0.6b": "0.6B (lighter, lower memory)",
        "1.7b": "1.7B (larger model)",
    }[selected]
