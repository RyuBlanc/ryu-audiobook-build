from pathlib import Path


_SETTINGS_ORGANIZATION = "RyuBlanc"
_SETTINGS_APPLICATION = "Ryu's Audiobook"


def _setting_value(key: str):
    """Read a persisted path without making the core path helpers depend on UI startup."""
    try:
        from PySide6.QtCore import QSettings

        return QSettings(_SETTINGS_ORGANIZATION, _SETTINGS_APPLICATION).value(key, "")
    except Exception:
        # Safe defaults keep core import/list helpers usable if QSettings is unavailable.
        return ""


def _configured_root(key: str, fallback: Path) -> Path:
    value = str(_setting_value(key) or "").strip()
    if not value:
        return fallback
    candidate = Path(value).expanduser()
    # Storage roots are selected using a native folder picker and must be absolute.
    return candidate if candidate.is_absolute() else fallback


def app_root() -> Path:
    return Path.home() / "Ryu's Audiobook"


def default_library_root() -> Path:
    """Original library location, always scanned so existing books remain discoverable."""
    return app_root() / "Library"


def library_root() -> Path:
    """Where new projects are stored; old default-location projects remain visible."""
    return _configured_root("storage/library_root", default_library_root())


def project_library_roots() -> tuple[Path, ...]:
    """Return configured and legacy project roots without scanning the same path twice."""
    roots: list[Path] = []
    seen: set[str] = set()
    for path in (library_root(), default_library_root()):
        try:
            key = str(path.resolve()).casefold()
        except OSError:
            key = str(path.absolute()).casefold()
        if key not in seen:
            roots.append(path)
            seen.add(key)
    return tuple(roots)


def voices_root() -> Path:
    return app_root() / "Voices"


def default_models_root() -> Path:
    """Original model location, retained as the default for existing installs."""
    return app_root() / "Models"


def models_root() -> Path:
    """Configured root for model weights; defaults to the legacy Models folder."""
    return _configured_root("storage/models_root", default_models_root())


def default_runtimes_root() -> Path:
    """Legacy runtime root, preserving existing Qwen and Chatterbox installations."""
    return models_root()


def runtimes_root() -> Path:
    """Configured provider-runtime root; follows Models unless explicitly separated."""
    return _configured_root("storage/runtime_root", models_root())


def default_model_cache_root() -> Path:
    """Default Hugging Face cache follows the effective Models root."""
    return models_root() / "huggingface"


def model_cache_root() -> Path:
    """Configured model/provider download cache; defaults to the legacy HF cache."""
    return _configured_root("storage/model_cache_root", default_model_cache_root())


def default_temporary_root() -> Path:
    return app_root() / "Temp"


def temporary_root() -> Path:
    """Configured app-owned temporary/staging root."""
    return _configured_root("storage/temporary_root", default_temporary_root())


def default_audiobooks_root() -> Path:
    return app_root() / "Audiobooks"


def audiobooks_root() -> Path:
    """Configured default destination for new generated audiobook exports."""
    return _configured_root("storage/audio_assets_root", default_audiobooks_root())


def settings_root() -> Path:
    return app_root() / "Settings"


def audio_library_root() -> Path:
    """User-owned/licensed audiobook music and cue files."""
    return app_root() / "Audio Library"


def soundtracks_root() -> Path:
    """Local cache and previews for the generated soundtrack catalogue."""
    return app_root() / "Soundtracks"


def _recover_interrupted_storage_migrations() -> None:
    """Restore the old root after an interrupted migration before providers initialize."""
    journal_root = app_root() / "Settings" / "Storage Migrations"
    if not journal_root.is_dir():
        return
    try:
        from PySide6.QtCore import QSettings
        from app.core.storage_migration import read_migration_journal, recover_migration_journal
    except Exception:
        return
    settings = QSettings(_SETTINGS_ORGANIZATION, _SETTINGS_APPLICATION)
    defaults = {
        "storage/models_root": default_models_root,
        "storage/runtime_root": default_runtimes_root,
        "storage/model_cache_root": default_model_cache_root,
        "storage/temporary_root": default_temporary_root,
    }
    for journal_path in sorted(journal_root.glob("ryu-storage-migration-*.json")):
        try:
            journal = read_migration_journal(journal_path)
            if journal.get("state") == "complete_source_retained":
                continue
            source = Path(str(journal.get("source", ""))).expanduser()
            destination = Path(str(journal.get("destination", ""))).expanduser()
            if not source.is_absolute() or not destination.is_absolute() or not source.is_dir():
                continue
            matching_key = None
            journal_key = str(journal.get("settings_key") or "")
            candidate_defaults = (
                {journal_key: defaults[journal_key]}
                if journal_key in defaults else defaults
            )
            for key, default_for_key in candidate_defaults.items():
                configured = str(settings.value(key, "") or default_for_key()).strip()
                try:
                    if Path(configured).expanduser().resolve() in (source.resolve(), destination.resolve()):
                        matching_key = key
                        break
                except OSError:
                    continue
            if matching_key is None:
                continue

            def persist_old_root(path: Path) -> None:
                settings.setValue(matching_key, str(path))
                settings.sync()
                if settings.status() != QSettings.Status.NoError:
                    raise OSError("Could not restore the previous storage setting.")

            recover_migration_journal(journal_path, persist_root=persist_old_root)
        except Exception:
            # Keep the journal for the Settings/Models Center to surface for manual recovery.
            continue


def ensure_roots() -> None:
    _recover_interrupted_storage_migrations()
    # Keep support folders on the normal user profile. The original roots remain
    # available even after the user selects an external drive for new content.
    for path in (
        voices_root(),
        default_models_root(),
        settings_root(),
        soundtracks_root(),
        audio_library_root(),
        default_library_root(),
        default_audiobooks_root(),
        default_temporary_root(),
    ):
        path.mkdir(parents=True, exist_ok=True)

    # A disconnected external drive must not prevent the app from launching.
    # Keep the configured path intact; callers surface Location unavailable and
    # must not silently redirect an existing installation to an empty default.
    selected_roots = (
        library_root(), audiobooks_root(), models_root(), runtimes_root(),
        model_cache_root(), temporary_root(),
    )
    seen: set[str] = set()
    for path in selected_roots:
        try:
            marker = str(path.resolve()).casefold()
        except OSError:
            marker = str(path.absolute()).casefold()
        if marker in seen:
            continue
        seen.add(marker)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
