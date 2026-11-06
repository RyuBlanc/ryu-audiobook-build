from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import shutil
import threading

from app.core.paths import model_cache_root, models_root, settings_root


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    display_name: str
    provider: str
    voice_cloning: bool
    multilingual: bool
    preferred_backends: tuple[str, ...]
    notes: str = ""


BUILTIN_CATALOG = (
    ModelSpec(
        "piper",
        "Piper",
        "piper",
        False,
        True,
        ("cpu", "cuda"),
        "Fast local neural TTS. Individual voice models are downloaded separately."
    ),
    ModelSpec(
        "kokoro",
        "Kokoro 82M",
        "kokoro",
        False,
        True,
        ("cuda", "directml", "cpu"),
        "Natural offline TTS with a broad voice catalogue. Model and voice pack are downloaded separately."
    ),
    ModelSpec(
        "chatterbox",
        "Chatterbox",
        "chatterbox",
        True,
        False,
        ("cuda", "cpu"),
        "English voice cloning from a reference recording."
    ),
    ModelSpec(
        "chatterbox-multilingual",
        "Chatterbox Multilingual",
        "chatterbox",
        True,
        True,
        ("cuda", "cpu"),
        "Multilingual zero-shot voice cloning from a reference recording."
    ),
)


def _manifest_path() -> Path:
    return settings_root() / "models.json"


def installed_model_ids() -> set[str]:
    path = _manifest_path()
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(x) for x in data.get("installed", [])}
    except (OSError, ValueError, TypeError):
        return set()


def _has_kokoro_assets() -> bool:
    root = models_root() / "kokoro"
    model = any((root / name).exists() for name in ("kokoro-v1.0.onnx", "model.onnx", "model_q8f16.onnx", "model_quantized.onnx"))
    voices = any((root / name).exists() for name in ("voices-v1.0.bin", "voices.bin"))
    return model and voices


def installed_models() -> list[ModelSpec]:
    ids = installed_model_ids()
    result = [m for m in BUILTIN_CATALOG if m.model_id in ids]
    if (models_root() / "piper").exists() and any((models_root() / "piper").rglob("*.onnx")):
        if not any(m.model_id == "piper" for m in result):
            result.append(get_model("piper"))
    if _has_kokoro_assets() and not any(m.model_id == "kokoro" for m in result):
        result.append(get_model("kokoro"))
    return [m for m in result if m is not None]


def get_model(model_id: str) -> ModelSpec | None:
    return next((m for m in BUILTIN_CATALOG if m.model_id == model_id), None)


def mark_installed(model_id: str, installed: bool = True) -> None:
    if get_model(model_id) is None:
        raise ValueError(f"Unknown TTS model: {model_id}")

    path = _manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    ids = installed_model_ids()
    if installed:
        ids.add(model_id)
    else:
        ids.discard(model_id)
    path.write_text(json.dumps({"installed": sorted(ids)}, indent=2), encoding="utf-8")


# The inventory below is the single read-only source for Models Center,
# native compatibility views and model-file detail requests. Installer
# implementations remain provider-owned and are deliberately not replaced.
INVENTORY_SCHEMA_VERSION = 1
INVENTORY_FILE_PAGE_SIZE = 250
_INVENTORY_LOCK = threading.RLock()

COMPONENT_METADATA: dict[str, dict[str, Any]] = {
    "piper": {"capability": "Offline Neural TTS", "dependencies": ["Piper runtime", "ONNX Runtime", "ONNX voice file", "voice JSON configuration"]},
    "kokoro": {"capability": "Natural offline narration", "dependencies": ["Kokoro ONNX runtime", "Kokoro ONNX model", "voice pack"]},
    "chatterbox-runtime": {"capability": "Voice cloning runtime", "dependencies": ["Isolated Python 3.11", "PyTorch", "Chatterbox", "Perth"]},
    "chatterbox-model-assets": {"capability": "Chatterbox English and multilingual voice cloning weights", "dependencies": ["Chatterbox model snapshot in the Hugging Face cache", "Chatterbox runtime"]},
    "qwen-runtime": {"capability": "Shared Qwen3-TTS runtime", "dependencies": ["Private Python 3.12", "PyTorch", "torchaudio", "qwen-tts"]},
    "custom-0.6b": {"capability": "Qwen CustomVoice synthesis", "dependencies": ["Qwen3-TTS runtime", "CustomVoice 0.6B weights"]},
    "custom-1.7b": {"capability": "Qwen CustomVoice synthesis", "dependencies": ["Qwen3-TTS runtime", "CustomVoice 1.7B weights"]},
    "design-1.7b": {"capability": "Prompt-based voice design", "dependencies": ["Qwen3-TTS runtime", "VoiceDesign 1.7B weights", "Qwen Base weights"]},
    "base-0.6b": {"capability": "Reference-based voice cloning", "dependencies": ["Qwen3-TTS runtime", "Base 0.6B weights"]},
    "base-1.7b": {"capability": "Reference-based voice cloning", "dependencies": ["Qwen3-TTS runtime", "Base 1.7B weights"]},
    "audiobook-ai": {"capability": "Local book and character analysis", "dependencies": ["llama-server.exe", "GGUF model", "runtime DLLs"]},
    "windows-sapi": {"capability": "Windows system speech", "dependencies": ["Windows Speech API", "registered system voices"]},
    "edge-tts": {"capability": "Online neural speech", "dependencies": ["edge-tts client package", "internet connection"]},
    "elevenlabs": {"capability": "Premium online speech", "dependencies": ["ElevenLabs client", "API credentials", "internet connection"]},
}


def _storage_location_available(path: Path) -> bool:
    """Distinguish an absent folder on an available drive from a disconnected drive."""
    try:
        candidate = Path(path)
        if os.name == "nt":
            drive = candidate.drive
            if drive:
                anchor = Path(drive) if drive.startswith("\\\\") else Path(drive + "\\")
                if not anchor.exists():
                    return False
        return True
    except (OSError, ValueError):
        return False

def normalize_inventory_status(
    model_id: str,
    installed: bool,
    component_type: str,
    status_detail: str = "",
    *,
    location_available: bool = True,
    has_partial_files: bool = False,
    verification: dict[str, Any] | None = None,
    current_fingerprint: str = "",
) -> str:
    """Normalize legacy labels; only a matching functional check can produce Ready."""
    detail = str(status_detail or "").casefold()
    if component_type == "provider":
        if model_id == "elevenlabs" and not installed:
            return "Not configured"
        if installed:
            return "Ready" if model_id == "windows-sapi" else "Installed"
        return "Missing" if model_id != "elevenlabs" else "Not configured"

    if not location_available:
        return "Location unavailable"

    if installed and verification and current_fingerprint and verification.get("fingerprint") == current_fingerprint:
        if verification.get("success") is True:
            return "Ready" if str(verification.get("level") or "functional") == "functional" else "Installed"
        if verification.get("success") is False:
            return "Unhealthy"

    incomplete_markers = (
        "incomplete", "needs installation", "needs repair",
        "runtime required", "runtime missing", "dependency missing",
        "needs setup", "not installed", "not ready",
        "dependency unavailable", "server missing",
    )
    if installed:
        if any(marker in detail for marker in incomplete_markers):
            return "Partially installed"
        return "Installed"

    return "Partially installed" if has_partial_files else "Missing"

def _inventory_snapshot_path() -> Path:
    return settings_root() / "model_inventory.json"


def load_inventory_snapshot() -> dict[str, Any]:
    try:
        value = json.loads(_inventory_snapshot_path().read_text(encoding="utf-8"))
        return value if isinstance(value, dict) and value.get("schema_version") == INVENTORY_SCHEMA_VERSION else {}
    except (OSError, ValueError, TypeError):
        return {}


def persist_inventory_snapshot(rows: list[dict[str, Any]]) -> None:
    """Persist non-secret inventory metadata atomically; live files remain authoritative."""
    path = _inventory_snapshot_path()
    components: dict[str, Any] = {}
    previous = load_inventory_snapshot().get("components", {})
    if not isinstance(previous, dict):
        previous = {}
    for row in rows:
        model_id = str(row.get("model_id") or "")
        if not model_id:
            continue
        old = previous.get(model_id, {})
        if not isinstance(old, dict):
            old = {}
        components[model_id] = {
            "model_id": model_id,
            "name": str(row.get("name") or ""),
            "provider": str(row.get("provider") or ""),
            "component_type": str(row.get("component_type") or "model"),
            "model_path": row.get("model_path"),
            "runtime_path": row.get("runtime_path"),
            "python_path": row.get("python_path"),
            "runtime_executable": row.get("runtime_executable"),
            "version": row.get("version"),
            "runtime_version": row.get("runtime_version"),
            "capability": row.get("capability"),
            "dependencies": list(row.get("dependencies") or []),
            "storage_bytes": int(row.get("storage_bytes") or 0),
            "status": str(row.get("status") or ""),
            "status_detail": str(row.get("status_detail") or ""),
            "health": row.get("health"),
            "hardware_compatibility": row.get("hardware_compatibility"),
            "last_verified": old.get("last_verified"),
            "verification": old.get("verification"),
        }
    payload = {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "components": components,
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    with _INVENTORY_LOCK:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".tmp")
            temporary.write_text(encoded, encoding="utf-8")
            temporary.replace(path)
        except OSError:
            return


def _module_directory(module_name: str) -> str | None:
    try:
        spec = importlib.util.find_spec(module_name)
        if spec and spec.origin:
            return str(Path(spec.origin).resolve().parent)
        if spec and spec.submodule_search_locations:
            return str(Path(next(iter(spec.submodule_search_locations))).resolve())
    except (ImportError, ValueError, OSError, AttributeError):
        return None
    return None


def _chatterbox_cache_root(root: Path) -> Path:
    cache = os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE")
    if cache:
        return Path(cache).expanduser()
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(hf_home).expanduser() / "hub"
    return model_cache_root() / "hub"

def component_paths(model_id: str) -> dict[str, Any]:
    """Resolve actual model/runtime/Python locations and exact component-owned paths."""
    root = models_root()
    model_path: str | None = None
    runtime_path: str | None = None
    python_path: str | None = None
    runtime_executable: str | None = None
    path_error: str | None = None
    owned_paths: list[Path] = []
    key = str(model_id or "").casefold()

    try:
        if key == "piper":
            from app.tts.providers.piper import PiperProvider
            local = root / "piper"
            bundled = PiperProvider._bundled_root()
            local_has_models = local.is_dir() and any(local.rglob("*.onnx"))
            selected = local if local_has_models else (bundled if bundled and bundled.exists() else local)
            model_path = str(selected.resolve())
            if local.exists():
                owned_paths.append(local)
            if bundled and bundled.exists():
                owned_paths.append(bundled)
            runtime_path = _module_directory("piper")
        elif key == "kokoro":
            from app.tts.providers.kokoro import KokoroProvider
            model = KokoroProvider._find_model()
            voices = KokoroProvider._find_voices()
            model_path = str(model.resolve()) if model else str((root / "kokoro").resolve())
            for path in (root / "kokoro", model, voices):
                if path and path.exists() and path not in owned_paths:
                    owned_paths.append(path)
            runtime_path = _module_directory("kokoro_onnx")
        elif key == "chatterbox-runtime":
            from app.tts.chatterbox_runtime import RUNTIME_DIR, runtime_python
            runtime_path = str(RUNTIME_DIR.resolve())
            owned_paths.append(RUNTIME_DIR)
            python_executable = runtime_python()
            python_path = str(python_executable.resolve()) if python_executable else str((RUNTIME_DIR / "Scripts" / "python.exe").resolve())
        elif key == "chatterbox-model-assets":
            cache = _chatterbox_cache_root(root)
            matches = [
                path for path in cache.glob("models--*")
                if path.is_dir() and "chatterbox" in path.name.casefold()
            ] if cache.is_dir() else []
            model_path = str(matches[0].resolve()) if matches else str(cache.resolve())
            owned_paths.extend(matches)
        elif key == "qwen-runtime":
            from app.tts.qwen_character_runtime import (
                VENV_ROOT, PYTHON_ROOT, PYTHON, MARKER, INSTALLER_PATH, INSTALLER_LOG,
            )
            runtime_path = str(VENV_ROOT.resolve())
            python_path = str(PYTHON.resolve())
            owned_paths.extend([VENV_ROOT, PYTHON_ROOT, MARKER, INSTALLER_PATH, INSTALLER_LOG])
        elif key in {"custom-0.6b", "custom-1.7b", "design-1.7b", "base-0.6b", "base-1.7b"}:
            from app.tts.qwen_character_runtime import MODEL_DIRS, VENV_ROOT, PYTHON
            model_path = str(MODEL_DIRS[key].resolve())
            runtime_path = str(VENV_ROOT.resolve())
            python_path = str(PYTHON.resolve())
            owned_paths.append(MODEL_DIRS[key])
        elif key == "audiobook-ai":
            ai_root = root / "audiobook-ai"
            candidates = (
                ai_root / "Qwen3-4B-Q4_K_M.gguf",
                ai_root / "Qwen3-1.7B-Q5_K_M.gguf",
            )
            model = next((path for path in candidates if path.is_file()), None)
            server = ai_root / "llama-server.exe"
            model_path = str(model.resolve()) if model else str(ai_root.resolve())
            runtime_path = str(ai_root.resolve())
            runtime_executable = str(server.resolve()) if server.is_file() else None
            owned_paths.append(ai_root)
        elif key == "edge-tts":
            runtime_path = _module_directory("edge_tts")
        elif key == "elevenlabs":
            runtime_path = _module_directory("elevenlabs")
    except Exception as exc:
        path_error = f"{type(exc).__name__}: {exc}"

    unique: list[Path] = []
    seen: set[str] = set()
    for path in owned_paths:
        try:
            marker = str(path.resolve()).casefold()
        except OSError:
            marker = str(path.absolute()).casefold()
        if marker not in seen:
            unique.append(path)
            seen.add(marker)
    return {
        "model_path": model_path,
        "runtime_path": runtime_path,
        "python_path": python_path,
        "runtime_executable": runtime_executable,
        "owned_paths": unique,
        "path_error": path_error,
    }

def _component_file_records(paths: list[Path], model_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in paths:
        try:
            if root.is_symlink() or not root.exists():
                continue
            candidates: list[Path] = []
            if root.is_file():
                candidates = [root]
            elif root.is_dir():
                for current, directories, filenames in os.walk(root, followlinks=False):
                    directories[:] = [
                        name for name in directories
                        if not (Path(current) / name).is_symlink()
                    ]
                    for filename in filenames:
                        candidates.append(Path(current) / filename)
            for candidate in candidates:
                try:
                    if candidate.is_symlink() or not candidate.is_file():
                        continue
                    if candidate.name.casefold().endswith((".part", ".tmp", ".download")):
                        continue
                    stat = candidate.stat()
                    resolved = str(candidate.resolve())
                    key = resolved.casefold()
                    if key in seen:
                        continue
                    seen.add(key)
                    suffix = candidate.suffix.casefold()
                    role = "runtime"
                    if model_id == "piper":
                        role = "model" if suffix == ".onnx" else "configuration"
                    elif model_id == "kokoro":
                        role = "voice pack" if suffix == ".bin" else "model" if suffix == ".onnx" else "asset"
                    elif model_id.startswith(("custom-", "design-", "base-")):
                        role = "model"
                    elif model_id == "audiobook-ai":
                        role = "model" if suffix == ".gguf" else "runtime"
                    records.append({
                        "path": resolved,
                        "name": candidate.name,
                        "size_bytes": int(stat.st_size),
                        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
                        "role": role,
                        "checksum": None,
                    })
                except OSError:
                    continue
        except OSError:
            continue
    records.sort(key=lambda item: str(item["path"]).casefold())
    return records


def component_file_inventory(model_id: str, offset: int = 0, limit: int = INVENTORY_FILE_PAGE_SIZE) -> dict[str, Any]:
    """Return a safe, paginated list of actual files owned by one inventory component."""
    key = str(model_id or "").strip().casefold()
    if not key:
        raise ValueError("Choose a model component to inspect.")
    try:
        offset = max(0, int(offset))
        limit = min(500, max(1, int(limit)))
    except (TypeError, ValueError):
        raise ValueError("Invalid model-file page request.")
    paths = component_paths(key)
    records = _component_file_records(paths["owned_paths"], key)
    owned_paths = paths["owned_paths"]
    accessible = (
        all(_storage_location_available(path) for path in owned_paths)
        if owned_paths else _storage_location_available(models_root())
    )
    return {
        "model_id": key,
        "model_path": paths["model_path"],
        "runtime_path": paths["runtime_path"],
        "python_path": paths["python_path"],
        "runtime_executable": paths["runtime_executable"],
        "path_error": paths["path_error"],
        "accessible": accessible,
        "status": "Accessible" if accessible else "Location unavailable",
        "total_files": len(records),
        "total_bytes": sum(int(item["size_bytes"]) for item in records),
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < len(records),
        "files": records[offset:offset + limit],
    }

def _component_fingerprint(row: dict[str, Any]) -> str:
    payload = {
        "model_id": row.get("model_id"),
        "installed": bool(row.get("installed")),
        "status_detail": str(row.get("status_detail") or row.get("status") or ""),
        "storage_bytes": int(row.get("storage_bytes") or 0),
        "model_path": row.get("model_path"),
        "runtime_path": row.get("runtime_path"),
        "python_path": row.get("python_path"),
        "runtime_executable": row.get("runtime_executable"),
        "version": row.get("version"),
        "runtime_version": row.get("runtime_version"),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def record_component_verification(
    model_id: str,
    success: bool,
    detail: str,
    fingerprint: str,
    level: str = "functional",
) -> None:
    """Persist a verification result; file-only checks never promote a model to Ready."""
    path = _inventory_snapshot_path()
    with _INVENTORY_LOCK:
        snapshot = load_inventory_snapshot()
        components = snapshot.setdefault("components", {})
        component = components.setdefault(str(model_id), {"model_id": str(model_id)})
        component["last_verified"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        component["verification"] = {
            "success": bool(success),
            "detail": str(detail or ""),
            "fingerprint": str(fingerprint or ""),
            "level": "functional" if str(level).casefold() == "functional" else "files",
        }
        snapshot["schema_version"] = INVENTORY_SCHEMA_VERSION
        snapshot["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".tmp")
            temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            temporary.replace(path)
        except OSError:
            return

def _distribution_version(distribution: str | None) -> str | None:
    if not distribution:
        return None
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None
    except Exception:
        return None


def _runtime_version(model_id: str) -> str | None:
    try:
        if model_id == "qwen-runtime" or model_id.startswith(("custom-", "design-", "base-")):
            from app.tts.qwen_character_runtime import (
                QWEN_TTS_VERSION, TORCH_VERSION, TORCHAUDIO_VERSION, PYTHON_VERSION,
            )
            return f"Qwen TTS {QWEN_TTS_VERSION} · PyTorch {TORCH_VERSION} · torchaudio {TORCHAUDIO_VERSION} · Python {PYTHON_VERSION}"
        if model_id.startswith("chatterbox-"):
            from app.tts.chatterbox_runtime import CHATTERBOX_SOURCE_REVISION, PERTH_SOURCE_REVISION
            return f"Chatterbox {str(CHATTERBOX_SOURCE_REVISION)[:12]} · Perth {str(PERTH_SOURCE_REVISION)[:12]}"
    except Exception:
        return None
    return None


def enrich_inventory_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshot = load_inventory_snapshot()
    previous = snapshot.get("components", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(previous, dict):
        previous = {}
    root = models_root()
    location_available = _storage_location_available(root)
    package_versions = {
        "piper": "piper-tts",
        "kokoro": "kokoro-onnx",
        "chatterbox-runtime": "chatterbox-tts",
        "edge-tts": "edge-tts",
        "elevenlabs": "elevenlabs",
    }
    for row in rows:
        model_id = str(row.get("model_id") or "")
        metadata = COMPONENT_METADATA.get(model_id, {})
        paths = component_paths(model_id)
        row["model_path"] = paths["model_path"]
        row["runtime_path"] = paths["runtime_path"]
        row["python_path"] = paths["python_path"]
        row["runtime_executable"] = paths["runtime_executable"]
        row["path_error"] = paths["path_error"]
        row["capability"] = metadata.get("capability", row.get("capability") or "")
        row["dependencies"] = list(metadata.get("dependencies", []))
        row["version"] = (
            row.get("version") or row.get("repo_id") or
            _distribution_version(package_versions.get(model_id))
        )
        row["runtime_version"] = row.get("runtime_version") or _runtime_version(model_id)
        row["supported_devices"] = list(row.get("supported_devices") or [])
        row["hardware_compatibility"] = row.get("hardware_compatibility") or "Not assessed"
        prior = previous.get(model_id, {})
        if isinstance(prior, dict):
            row["last_verified"] = prior.get("last_verified")
            verification = prior.get("verification")
        else:
            row["last_verified"] = None
            verification = None
        fingerprint = _component_fingerprint(row)
        row["inventory_fingerprint"] = fingerprint
        row["status"] = normalize_inventory_status(
            model_id,
            bool(row.get("installed")),
            str(row.get("component_type") or "model"),
            str(row.get("status_detail") or row.get("status") or ""),
            location_available=bool(row.get("location_available", location_available)),
            has_partial_files=bool(any(path.exists() for path in paths["owned_paths"])),
            verification=verification if isinstance(verification, dict) else None,
            current_fingerprint=fingerprint,
        )
        row["runtime_status"] = (
            "Ready" if row.get("runtime_ready") is True else
            "Not ready" if row.get("runtime_ready") is False else
            "Available" if row.get("component_type") == "provider" and row.get("installed") else
            "Not configured" if row.get("component_type") == "provider" else
            "Installed" if paths["runtime_path"] and Path(paths["runtime_path"]).exists() else
            "Not detected" if paths["runtime_path"] else
            "Not applicable"
        )
        if row["status"] == "Ready":
            row["health"] = "Functionally verified"
        elif row["status"] == "Unhealthy":
            row["health"] = "Verification failed"
        elif row["status"] == "Partially installed":
            row["health"] = "Incomplete"
        elif row["status"] == "Location unavailable":
            row["health"] = "Location unavailable"
        elif isinstance(verification, dict) and verification.get("success") is True and verification.get("fingerprint") == fingerprint:
            row["health"] = "Files verified · functional check pending"
        else:
            row["health"] = "Not verified" if row.get("installed") else "Missing"
        row["file_inventory_available"] = bool(paths["owned_paths"])
        row["files_endpoint"] = "models.files" if paths["owned_paths"] else None
    persist_inventory_snapshot(rows)
    return rows

def voice_model_inventory_status(provider_key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Project the authoritative inventory into the availability contract used by Voice Studio."""
    key = str(provider_key or "").strip().casefold()
    by_id = {str(row.get("model_id") or ""): row for row in rows}
    groups: list[list[str]]
    optional: list[str] = []
    if key == "offline":
        groups = [["piper", "kokoro"]]
    elif key == "sapi":
        groups = [["windows-sapi"]]
    elif key == "customvoice":
        groups = [["qwen-runtime"], ["custom-0.6b", "custom-1.7b"]]
    elif key == "voicedesign":
        groups = [["qwen-runtime"], ["design-1.7b"], ["base-0.6b", "base-1.7b"]]
    elif key == "qwenclone":
        groups = [["qwen-runtime"], ["base-0.6b", "base-1.7b"]]
    elif key == "customref":
        groups = [["chatterbox-runtime"]]
        optional = ["chatterbox-model-assets"]
    elif key == "edge":
        groups = [["edge-tts"]]
    elif key == "eleven":
        groups = [["elevenlabs"]]
    else:
        return {
            "provider": key, "status": "Not assessed", "selectable": False,
            "message": "No authoritative model-inventory mapping exists for this provider.",
            "components": [], "available_variants": [],
        }

    available_statuses = {"Ready", "Installed"}
    def status_for(model_id: str) -> str:
        row = by_id.get(model_id)
        return str(row.get("status") or "Missing") if row else "Missing"

    selected: list[str] = []
    missing_groups: list[list[str]] = []
    for group in groups:
        candidates = [model_id for model_id in group if status_for(model_id) in available_statuses]
        if candidates:
            candidates.sort(key=lambda model_id: status_for(model_id) == "Ready", reverse=True)
            selected.append(candidates[0])
        else:
            missing_groups.append(group)

    selectable = not missing_groups
    required_ids = list(dict.fromkeys(model_id for group in groups for model_id in group))
    all_ids = list(dict.fromkeys(required_ids + optional))
    component_rows = [
        {
            "model_id": model_id,
            "name": str(by_id.get(model_id, {}).get("name") or model_id),
            "status": status_for(model_id),
            "status_detail": str(by_id.get(model_id, {}).get("status_detail") or "Component not detected"),
        }
        for model_id in all_ids
    ]
    if selectable:
        status = "Ready" if selected and all(status_for(model_id) == "Ready" for model_id in selected) else "Installed"
        message = (
            "Required model and runtime components are functionally verified."
            if status == "Ready" else
            "Required model files and runtime are installed; functional inference verification is still pending."
        )
        if key == "customref" and status_for("chatterbox-model-assets") == "Missing":
            message += " Chatterbox weights may be downloaded on first use."
    else:
        failed = []
        for group in missing_groups:
            failed.append(" or ".join(group))
        component_statuses = [status_for(model_id) for group in missing_groups for model_id in group]
        if "Location unavailable" in component_statuses:
            status = "Location unavailable"
        elif "Unhealthy" in component_statuses:
            status = "Unhealthy"
        elif "Partially installed" in component_statuses:
            status = "Partially installed"
        elif "Not configured" in component_statuses:
            status = "Not configured"
        else:
            status = "Missing"
        message = "Unavailable components: " + "; ".join(failed) + ". Install or repair them in Models Center."

    available_variants = [
        model_id for model_id in required_ids
        if model_id.startswith(("custom-", "design-", "base-")) and status_for(model_id) in available_statuses
    ]
    return {
        "provider": key,
        "status": status,
        "selectable": selectable,
        "message": message,
        "components": component_rows,
        "available_variants": available_variants,
    }


def build_inventory() -> list[dict[str, Any]]:
    """Return the live, provider-aware local model and runtime inventory."""
    from app.core.paths import models_root
    from app.tts.providers.piper import PiperProvider
    from app.tts.providers.kokoro import KokoroProvider
    from app.tts.chatterbox_runtime import RUNTIME_DIR as CHATTERBOX_ROOT, runtime_ready as chatterbox_ready
    from app.tts.qwen_character_runtime import (
        MODEL_IDS, MODEL_DIRS, model_installed as qwen_model_installed,
        runtime_ready as qwen_runtime_ready, RUNTIME_ROOT as QWEN_ROOT,
        VENV_ROOT as QWEN_VENV_ROOT, PYTHON_ROOT as QWEN_PYTHON_ROOT,
        MARKER as QWEN_MARKER, INSTALLER_PATH as QWEN_INSTALLER_PATH,
        INSTALLER_LOG as QWEN_INSTALLER_LOG,
    )
    root = models_root()
    location_available = _storage_location_available(root)
    try:
        probe = root if root.exists() else root.parent
        disk_free = int(shutil.disk_usage(probe).free) if location_available else None
    except OSError:
        disk_free = None

    def byte_size(path: Path, direct_only: bool = False) -> int:
        try:
            if path.is_file():
                return int(path.stat().st_size)
            if not path.is_dir():
                return 0
            total = 0
            iterator = path.iterdir() if direct_only else path.rglob("*")
            for candidate in iterator:
                try:
                    if candidate.is_file():
                        total += candidate.stat().st_size
                except OSError:
                    continue
            return total
        except OSError:
            return 0

    def unique_byte_size(paths) -> int:
        """Count each physical file path once even when roots overlap."""
        seen: set[str] = set()
        total = 0
        for raw_path in paths:
            if not raw_path:
                continue
            path = Path(raw_path)
            try:
                candidates = [path] if path.is_file() else path.rglob("*") if path.is_dir() else []
            except OSError:
                continue
            for candidate in candidates:
                try:
                    if not candidate.is_file():
                        continue
                    try:
                        marker = str(candidate.resolve()).casefold()
                    except OSError:
                        marker = str(candidate.absolute()).casefold()
                    if marker in seen:
                        continue
                    seen.add(marker)
                    total += int(candidate.stat().st_size)
                except OSError:
                    continue
        return total

    def row(model_id: str, name: str, provider: str, installed: bool, notes: str, **extra):
        raw_status = str(extra.pop("status", "Installed" if installed else "Not installed"))
        return {
            "model_id": model_id,
            "name": name,
            "provider": provider,
            "installed": bool(installed),
            "status": raw_status,
            "status_detail": raw_status,
            "notes": notes,
            "disk_free_bytes": disk_free,
            "storage_root": str(root),
            "location_available": location_available,
            **extra,
        }

    result: list[dict[str, Any]] = []
    try:
        piper_paths = list(PiperProvider.model_paths())
    except Exception:
        piper_paths = []
    piper_root = (root / "piper").resolve()
    piper_local = []
    for voice_path in piper_paths:
        try:
            if piper_root in voice_path.resolve().parents and voice_path.suffix.casefold() == ".onnx":
                piper_local.append(voice_path.resolve())
        except OSError:
            continue
    def piper_voice_is_valid(voice_path: Path) -> bool:
        try:
            return (
                voice_path.is_file()
                and voice_path.stat().st_size > 1024
                and voice_path.with_suffix(voice_path.suffix + ".json").is_file()
            )
        except OSError:
            return False

    piper_verified = [voice_path for voice_path in piper_paths if piper_voice_is_valid(voice_path)]
    piper_installed = bool(piper_verified)
    piper_runtime_ready = bool(_module_directory("piper"))
    try:
        piper_bundled_root = PiperProvider._bundled_root()
    except Exception:
        piper_bundled_root = None
    piper_storage_bytes = unique_byte_size([root / "piper", piper_bundled_root])
    piper_status = (
        f"{len(piper_verified)} voice model(s) installed"
        if piper_installed and piper_runtime_ready else
        "Voice files installed · Piper runtime missing"
        if piper_installed else
        "No verified voice models (not installed or incomplete)"
    )
    result.append(row(
        "piper", "Piper Offline Neural Voices", "piper", piper_installed,
        "Install individual Piper voice models for offline narration. Installed voice files are listed here; bundled voices are managed by the application installer.",
        status=piper_status,
        installable=True, repairable=bool(piper_local), uninstallable=bool(piper_local),
        removable_voice_count=len(piper_local),
        installed_voice_names=sorted({item.stem for item in piper_local}, key=str.casefold),
        storage_bytes=piper_storage_bytes, runtime_ready=piper_runtime_ready,
        requirements="Local model files; no internet required after download.",
        component_type="model",
    ))

    kokoro_root = root / "kokoro"
    kokoro_local = kokoro_root.is_dir() and any(p.is_file() for p in kokoro_root.rglob("*"))
    try:
        kokoro_installed = bool(KokoroProvider.assets_available())
        kokoro_voice_count = len(KokoroProvider().voices()) if kokoro_installed else 0
        kokoro_model = KokoroProvider._find_model()
        kokoro_voices = KokoroProvider._find_voices()
    except Exception:
        kokoro_installed, kokoro_voice_count = False, 0
        kokoro_model, kokoro_voices = None, None
    kokoro_runtime_ready = bool(_module_directory("kokoro_onnx"))
    kokoro_storage_bytes = unique_byte_size([kokoro_root, kokoro_model, kokoro_voices])
    kokoro_status = (
        "Installed locally" if kokoro_local and kokoro_installed and kokoro_runtime_ready else
        "Bundled with application" if kokoro_installed and kokoro_runtime_ready else
        "Model assets installed · Kokoro runtime missing" if kokoro_installed else
        "Model or voice pack missing"
    )
    result.append(row(
        "kokoro", "Kokoro 82M Natural Narration", "kokoro", kokoro_installed,
        "Offline natural narration. Requires both the ONNX model and voice pack. Bundled assets cannot be removed separately.",
        status=kokoro_status,
        installable=not kokoro_installed, repairable=bool(kokoro_local or (kokoro_root.exists() and not kokoro_installed)),
        uninstallable=bool(kokoro_local), storage_bytes=kokoro_storage_bytes,
        runtime_ready=kokoro_runtime_ready,
        voice_count=kokoro_voice_count, requirements="About 354 MB download; internet needed only for install/repair.",
        managed_path=str(kokoro_root), bundled=bool(kokoro_installed and not kokoro_local),
    ))

    try:
        chat_installed = bool(chatterbox_ready())
    except Exception:
        chat_installed = False
    chat_present = CHATTERBOX_ROOT.exists()
    chat_runtime_bytes = unique_byte_size([CHATTERBOX_ROOT])
    result.append(row(
        "chatterbox-runtime", "Chatterbox Voice Cloning Runtime", "chatterbox", chat_installed,
        "Shared runtime for English and multilingual reference-based voice cloning. Model weights are inventoried separately in the Hugging Face cache.",
        status=("Runtime ready · English and multilingual modes available" if chat_installed else "Runtime incomplete" if chat_present else "Not installed"),
        installable=not chat_installed, repairable=chat_present or chat_installed,
        uninstallable=chat_present, requirements="Python 3.11 isolated runtime; internet for setup and first-use model weights.",
        storage_bytes=chat_runtime_bytes, runtime_ready=chat_installed, component_type="runtime",
        managed_path=str(CHATTERBOX_ROOT),
    ))
    chatterbox_cache_root = _chatterbox_cache_root(root)
    chatterbox_model_dirs = [
        path for path in chatterbox_cache_root.glob("models--*")
        if path.is_dir() and "chatterbox" in path.name.casefold()
    ] if chatterbox_cache_root.is_dir() else []
    chatterbox_assets_bytes = unique_byte_size(chatterbox_model_dirs)
    chatterbox_assets_installed = bool(chatterbox_model_dirs and chatterbox_assets_bytes > 0)
    result.append(row(
        "chatterbox-model-assets", "Chatterbox Model Assets · English & Multilingual", "chatterbox",
        chatterbox_assets_installed,
        "Shared Hugging Face model weights used by Chatterbox English and multilingual synthesis. The runtime may download these weights on first use.",
        status=(f"{len(chatterbox_model_dirs)} cached model snapshot(s) found" if chatterbox_assets_installed else "No downloaded Chatterbox model assets found · first-use download may be required"),
        installable=False, repairable=False, uninstallable=False,
        storage_bytes=chatterbox_assets_bytes, managed_path=str(chatterbox_cache_root),
        component_type="model", shared_cache=True,
    ))

    try:
        qwen_ready = bool(qwen_runtime_ready())
    except Exception:
        qwen_ready = False
    qwen_runtime_paths = (QWEN_VENV_ROOT, QWEN_PYTHON_ROOT, QWEN_MARKER, QWEN_INSTALLER_PATH, QWEN_INSTALLER_LOG)
    qwen_runtime_present = any(path.exists() for path in qwen_runtime_paths)
    result.append(row(
        "qwen-runtime", "Qwen3-TTS Runtime", "qwen", qwen_ready,
        "Isolated Python, PyTorch, torchaudio and Qwen TTS runtime shared by CustomVoice, VoiceDesign and Voice Clone models.",
        status="Runtime ready" if qwen_ready else "Runtime needs installation or repair",
        installable=not qwen_ready, repairable=qwen_runtime_present or qwen_ready,
        uninstallable=qwen_runtime_present, requirements="Large offline runtime; model weights are managed separately.",
        storage_bytes=unique_byte_size(qwen_runtime_paths), runtime_ready=qwen_ready,
        managed_path=str(QWEN_ROOT), component_type="runtime",
    ))
    qwen_names = {
        "custom-0.6b": ("Qwen CustomVoice 0.6B", "qwen-customvoice"),
        "custom-1.7b": ("Qwen CustomVoice 1.7B", "qwen-customvoice"),
        "design-1.7b": ("Qwen VoiceDesign 1.7B", "qwen-voicedesign"),
        "base-0.6b": ("Qwen Voice Clone Base 0.6B", "qwen-clone"),
        "base-1.7b": ("Qwen Voice Clone Base 1.7B", "qwen-clone"),
    }
    for kind, repo_id in MODEL_IDS.items():
        try:
            installed = bool(qwen_model_installed(kind))
        except Exception:
            installed = False
        folder_exists = MODEL_DIRS[kind].exists()
        base_ready = False
        if kind == "design-1.7b":
            try:
                base_ready = bool(qwen_model_installed("base-0.6b") or qwen_model_installed("base-1.7b"))
            except Exception:
                base_ready = False
        if not installed:
            status = "Model files incomplete · Repair required" if folder_exists else "Not installed"
        elif not qwen_ready:
            status = "Weights installed · Qwen runtime required"
        elif kind == "design-1.7b" and not base_ready:
            status = "VoiceDesign weights installed · Base model dependency missing"
        elif kind == "design-1.7b":
            status = "Installed · VoiceDesign and Base dependencies ready"
        else:
            status = "Installed and file-verified"

        # VoiceDesign needs both the design weights and a Base model to keep
        # a stable reference identity during long-form generation. Its install/
        # repair action therefore installs missing dependencies together.
        install_id = "qwen-voicedesign" if kind == "design-1.7b" else kind
        repair_id = (
            "qwen-runtime" if installed and not qwen_ready else
            "qwen-voicedesign" if kind == "design-1.7b" else kind
        )
        verify_id = "qwen-voicedesign" if kind == "design-1.7b" else kind
        result.append(row(
            kind, qwen_names.get(kind, (repo_id, ""))[0], "qwen", installed,
            f"Local Qwen3-TTS weights from {repo_id}. The matching Qwen3-TTS runtime is also required.",
            status=status,
            installable=not installed and not folder_exists,
            repairable=folder_exists or (installed and (not qwen_ready or (kind == "design-1.7b" and not base_ready))),
            uninstallable=folder_exists,
            install_id=install_id, repair_id=repair_id, verify_id=verify_id,
            feature=qwen_names.get(kind, ("", "qwen"))[1], requirements="Model download can be several GB; requires internet for install/repair.",
            storage_bytes=unique_byte_size([MODEL_DIRS[kind]]), runtime_ready=qwen_ready,
            version=repo_id, managed_path=str(MODEL_DIRS[kind]), component_type="model",
        ))

    # This is a status-card refresh, not an installation operation. Do not
    # launch nvidia-smi here just to decide which model to display; inspect
    # the known local candidates directly and let the background installer
    # select hardware-appropriate weights when installation is requested.
    ai_root = root / "audiobook-ai"
    ai_present = ai_root.exists()
    ai_candidates = (
        ("qwen3-4b-q4", "Qwen3-4B-Q4_K_M.gguf"),
        ("qwen3-1.7b-q5", "Qwen3-1.7B-Q5_K_M.gguf"),
    )
    ai_models_on_disk = [
        (model_id, filename, ai_root / filename)
        for model_id, filename in ai_candidates
        if (ai_root / filename).is_file()
    ]
    ai_server_present = (ai_root / "llama-server.exe").is_file()
    ai_installed = bool(ai_server_present and ai_models_on_disk)
    if ai_models_on_disk:
        ai_model_id, ai_filename, ai_model_path = ai_models_on_disk[0]
        try:
            ai_size = int(ai_model_path.stat().st_size)
        except OSError:
            ai_size = 0
    else:
        ai_model_id, ai_filename, ai_size = "auto-selected", "Selected for this PC during installation", 0
    result.append(row(
        "audiobook-ai", "Audiobook AI · Local Book Analysis", "audiobook-ai", ai_installed,
        "Local analysis engine used by book/character analysis. Installer selects a model for detected hardware and runs a real inference self-test.",
        status=("Installed · model files present" if ai_installed else "Runtime/model needs setup" if ai_present else "Not installed"),
        installable=not ai_installed, repairable=ai_present or ai_installed, uninstallable=ai_present,
        model_name=ai_model_id, model_filename=ai_filename, download_bytes=int(ai_size),
        requirements=(f"Installed model file: {ai_size / (1024 ** 3):.1f} GB." if ai_size else
                      "Install downloads a hardware-appropriate local model (typically about 1.2–2.5 GB) and runs a real inference self-test."),
        storage_bytes=unique_byte_size([ai_root]), runtime_ready=ai_server_present,
        managed_path=str(ai_root), component_type="model",
    ))

    # Avoid constructing a COM speech engine synchronously while the
    # Models page is painting. Windows SAPI voice tokens are registered in
    # the system/user registry; Voice Studio later enumerates the full live
    # provider catalogue when the user opens that library.
    sapi_tokens: set[str] = set()
    try:
        import winreg
        registry_paths = (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Speech\Voices\Tokens"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Speech\Voices\Tokens"),
        )
        for hive, registry_path in registry_paths:
            try:
                with winreg.OpenKey(hive, registry_path) as key:
                    count = winreg.QueryInfoKey(key)[0]
                    for index in range(count):
                        try:
                            sapi_tokens.add(str(winreg.EnumKey(key, index)).casefold())
                        except OSError:
                            continue
            except OSError:
                continue
    except ImportError:
        pass
    sapi_count = len(sapi_tokens)
    result.append(row(
        "windows-sapi", "Windows SAPI System Voices", "windows-sapi", sapi_count > 0,
        "Uses voices installed in Windows. These are managed by Windows settings, not downloaded or removed by Ryu's Audiobook.",
        status=f"{sapi_count} Windows voice(s) detected" if sapi_count else "No Windows SAPI voices detected",
        installable=False, repairable=False, uninstallable=False, voice_count=sapi_count,
        requirements="Windows system component; not a separately managed model.",
        component_type="provider", runtime_ready=sapi_count > 0,
    ))

    try:
        from app.tts.providers.edge_tts import EdgeTTSProvider
        edge_ready = bool(EdgeTTSProvider.available())
    except Exception:
        edge_ready = False
    result.append(row(
        "edge-tts", "Microsoft Edge TTS · Online Voices", "edge-tts", edge_ready,
        "Online neural voice service, not a local model download. Voice catalogue and synthesis require network access.",
        status="Client package available · internet required" if edge_ready else "Edge TTS package unavailable",
        installable=False, repairable=False, uninstallable=False, requirements="Internet connection; not an offline model.",
        component_type="provider", runtime_ready=edge_ready,
    ))

    try:
        from app.tts.providers.elevenlabs import ElevenLabsProvider
        eleven_key = bool(ElevenLabsProvider.load_api_key())
    except Exception:
        eleven_key = False
    result.append(row(
        "elevenlabs", "ElevenLabs · Premium Online Voices", "elevenlabs", eleven_key,
        "Online provider access is configured when a local API key is present. Voice management and API credentials remain in Voice Studio.",
        status="API key configured" if eleven_key else "API key required",
        installable=False, repairable=False, uninstallable=False, credentials_configured=eleven_key,
        requirements="Internet and your own ElevenLabs API key; no local model to install.",
        component_type="provider", runtime_ready=eleven_key,
    ))
    return enrich_inventory_rows(result)

