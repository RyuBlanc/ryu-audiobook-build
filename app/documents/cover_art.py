"""Discover and persist locally portable audiobook cover artwork.

EPUB package cover metadata, DOCX package thumbnails, and PDF first-page artwork are
stored inside each project folder so Dashboard cards do not depend on external paths.
"""
from __future__ import annotations

import mimetypes
import posixpath
import shutil
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

MAX_COVER_BYTES = 24 * 1024 * 1024
COVER_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
COVER_SOURCE_EXTENSIONS = {".epub", ".docx", ".pdf"}


def _image_extension(name: str, media_type: str = "") -> str | None:
    extension = Path(name).suffix.casefold()
    if extension == ".jpe":
        extension = ".jpg"
    if extension not in COVER_IMAGE_EXTENSIONS and media_type:
        guessed = mimetypes.guess_extension(media_type.split(";", 1)[0].strip().casefold()) or ""
        extension = ".jpg" if guessed == ".jpe" else guessed.casefold()
    return extension if extension in COVER_IMAGE_EXTENSIONS else None


def _store_cover(project_folder: Path, data: bytes, extension: str) -> Path:
    if not data or len(data) > MAX_COVER_BYTES:
        raise ValueError("Embedded cover is empty or larger than the supported 24 MB limit.")
    extension = _image_extension("cover" + extension)
    if not extension:
        raise ValueError("The embedded cover image format is not supported.")
    assets = Path(project_folder) / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    target = assets / ("cover" + extension)
    temporary = assets / ("." + target.name + ".tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target.resolve()


def persist_project_cover(image_path: Path, project_folder: Path) -> Path:
    """Copy a chosen cover into the project so it remains available on another PC."""
    source = Path(image_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError("The selected cover image no longer exists.")
    extension = _image_extension(source.name)
    if not extension:
        raise ValueError("Choose a JPG, PNG, WebP, GIF, BMP, or TIFF cover image.")
    size = source.stat().st_size
    if size <= 0 or size > MAX_COVER_BYTES:
        raise ValueError("The selected cover image must be between 1 byte and 24 MB.")
    assets = Path(project_folder).resolve() / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    target = (assets / ("cover" + extension)).resolve()
    if source != target:
        shutil.copy2(source, target)
    return target


def _safe_member_path(package_path: str, href: str) -> str | None:
    """Resolve an EPUB manifest href while rejecting external and escaping paths."""
    parsed = urlsplit(str(href or ""))
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    decoded = unquote(parsed.path).replace("\\", "/")
    if decoded.startswith("/"):
        return None
    member = posixpath.normpath(posixpath.join(posixpath.dirname(package_path), decoded))
    if member in {"", ".", ".."} or member.startswith("../") or member.startswith("/"):
        return None
    return member


def _xml_local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1].casefold()


def _epub_cover(source: Path) -> tuple[bytes, str] | None:
    try:
        with zipfile.ZipFile(source) as archive:
            names = set(archive.namelist())
            container_name = next((name for name in names if name.casefold() == "meta-inf/container.xml"), None)
            if not container_name:
                return None
            container = ElementTree.fromstring(archive.read(container_name))
            package_path = next((
                node.attrib.get("full-path", "")
                for node in container.iter()
                if _xml_local_name(node.tag) == "rootfile" and node.attrib.get("full-path")
            ), "")
            if not package_path or package_path not in names:
                return None
            package = ElementTree.fromstring(archive.read(package_path))
            manifest = [
                node for node in package.iter()
                if _xml_local_name(node.tag) == "item" and node.attrib.get("href")
            ]
            by_id = {node.attrib.get("id", ""): node for node in manifest if node.attrib.get("id")}
            cover_ids = [
                node.attrib.get("content", "")
                for node in package.iter()
                if _xml_local_name(node.tag) == "meta"
                and str(node.attrib.get("name", "")).casefold() == "cover"
                and node.attrib.get("content")
            ]
            candidates = []
            candidates.extend(
                node for node in manifest
                if "cover-image" in str(node.attrib.get("properties", "")).casefold().split()
            )
            candidates.extend(by_id[cover_id] for cover_id in cover_ids if cover_id in by_id)
            candidates.extend(
                node for node in manifest
                if "image/" in str(node.attrib.get("media-type", "")).casefold()
                and "cover" in Path(unquote(node.attrib.get("href", ""))).name.casefold()
            )
            seen = set()
            for item in candidates:
                href = item.attrib.get("href", "")
                member = _safe_member_path(package_path, href)
                media_type = str(item.attrib.get("media-type", "")).casefold()
                extension = _image_extension(href, media_type)
                if not member or member in seen or member not in names or not extension:
                    continue
                seen.add(member)
                info = archive.getinfo(member)
                if info.file_size <= 0 or info.file_size > MAX_COVER_BYTES:
                    continue
                data = archive.read(member)
                if data:
                    return data, extension
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        return None
    return None


def _docx_cover(source: Path) -> tuple[bytes, str] | None:
    try:
        with zipfile.ZipFile(source) as archive:
            members = archive.namelist()
            # Word's document thumbnail is the best package-level preview.
            candidates = [
                name for name in members
                if name.casefold().startswith("docprops/thumbnail.")
                or (name.casefold().startswith("word/media/") and "cover" in Path(name).name.casefold())
            ]
            candidates.sort(key=lambda name: (
                0 if name.casefold().startswith("docprops/thumbnail.") else 1,
                name.casefold(),
            ))
            for name in candidates:
                extension = _image_extension(name)
                if not extension:
                    continue
                info = archive.getinfo(name)
                if info.file_size <= 0 or info.file_size > MAX_COVER_BYTES:
                    continue
                data = archive.read(name)
                if data:
                    return data, extension
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        return None
    return None


def _pdf_cover(source: Path) -> tuple[bytes, str] | None:
    try:
        import fitz

        with fitz.open(source) as document:
            if not len(document):
                return None
            page = document[0]
            longest_side = max(float(page.rect.width), float(page.rect.height), 1.0)
            scale = min(1.6, 720.0 / longest_side)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            data = pixmap.tobytes("png")
            if data and len(data) <= MAX_COVER_BYTES:
                return data, ".png"
    except Exception:
        # Cover art is optional; never block an otherwise successful text import
        # because a PDF's first page could not be rendered.
        return None
    return None


def extract_embedded_cover(source_path: Path, project_folder: Path) -> Path | None:
    """Extract known package-level cover art, returning a durable project-local path."""
    source = Path(source_path).expanduser()
    if not source.is_file():
        return None
    suffix = source.suffix.casefold()
    if suffix == ".epub":
        embedded = _epub_cover(source)
    elif suffix == ".docx":
        embedded = _docx_cover(source)
    elif suffix == ".pdf":
        embedded = _pdf_cover(source)
    else:
        return None
    if not embedded:
        return None
    data, extension = embedded
    try:
        return _store_cover(Path(project_folder), data, extension)
    except (OSError, ValueError):
        return None
