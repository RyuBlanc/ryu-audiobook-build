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


VALID_QWEN_BACKEND_PREFERENCES = {"automatic", "cpu", "cuda", "rocm", "xpu"}
QWEN_BACKEND_PREFERENCE_KEY = "qwen/backend_preference"
QWEN_LOW_MEMORY_KEY = "qwen/low_memory_mode"


def normalize_qwen_backend_preference(value: object) -> str:
    selected = str(value or "automatic").strip().casefold()
    return selected if selected in VALID_QWEN_BACKEND_PREFERENCES else "automatic"


def get_qwen_backend_preference() -> str:
    try:
        from PySide6.QtCore import QSettings
        settings = QSettings(QWEN_SETTINGS_ORGANIZATION, QWEN_SETTINGS_APPLICATION)
        return normalize_qwen_backend_preference(
            settings.value(QWEN_BACKEND_PREFERENCE_KEY, "automatic")
        )
    except Exception:
        return "automatic"


def set_qwen_backend_preference(value: object) -> str:
    selected = normalize_qwen_backend_preference(value)
    from PySide6.QtCore import QSettings
    settings = QSettings(QWEN_SETTINGS_ORGANIZATION, QWEN_SETTINGS_APPLICATION)
    settings.setValue(QWEN_BACKEND_PREFERENCE_KEY, selected)
    settings.sync()
    if settings.status() != QSettings.Status.NoError:
        raise OSError("Ryu could not save the Qwen hardware backend preference.")
    return selected


def get_qwen_low_memory_mode() -> bool:
    try:
        from PySide6.QtCore import QSettings
        settings = QSettings(QWEN_SETTINGS_ORGANIZATION, QWEN_SETTINGS_APPLICATION)
        return bool(settings.value(QWEN_LOW_MEMORY_KEY, False, type=bool))
    except Exception:
        return False


def set_qwen_low_memory_mode(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("Low-memory mode must be a boolean preference.")
    from PySide6.QtCore import QSettings
    settings = QSettings(QWEN_SETTINGS_ORGANIZATION, QWEN_SETTINGS_APPLICATION)
    settings.setValue(QWEN_LOW_MEMORY_KEY, value)
    settings.sync()
    if settings.status() != QSettings.Status.NoError:
        raise OSError("Ryu could not save the Qwen low-memory preference.")
    return value
