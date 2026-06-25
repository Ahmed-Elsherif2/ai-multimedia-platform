"""File-handling utilities — validation, type detection, safe save."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional, Tuple

AUDIO_EXTENSIONS: frozenset[str] = frozenset({
    ".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma",
})
VIDEO_EXTENSIONS: frozenset[str] = frozenset({
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".flv", ".3gp",
})
PDF_EXTENSIONS: frozenset[str] = frozenset({".pdf"})

MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
ALLOWED_EXTENSIONS = MEDIA_EXTENSIONS | PDF_EXTENSIONS


def is_audio(filename: str) -> bool:
    return Path(filename).suffix.lower() in AUDIO_EXTENSIONS


def is_video(filename: str) -> bool:
    return Path(filename).suffix.lower() in VIDEO_EXTENSIONS


def is_pdf(filename: str) -> bool:
    return Path(filename).suffix.lower() in PDF_EXTENSIONS


def is_media(filename: str) -> bool:
    return Path(filename).suffix.lower() in MEDIA_EXTENSIONS


def allowed_extension(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def media_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in PDF_EXTENSIONS:
        return "pdf"
    return "unknown"


def secure_save(
    file_storage,
    upload_folder: Path,
    file_id: Optional[str] = None,
) -> Tuple[str, Path]:
    """Save a Flask FileStorage object to *upload_folder*.

    Returns
    -------
    (file_id, saved_path)
    """
    if file_id is None:
        file_id = str(uuid.uuid4())
    ext  = Path(file_storage.filename).suffix.lower() or ".bin"
    path = upload_folder / f"{file_id}{ext}"
    upload_folder.mkdir(parents=True, exist_ok=True)
    file_storage.save(path)
    return file_id, path


def extension_hint(group: str = "all") -> str:
    """Comma-separated list of accepted extensions for error messages."""
    if group == "video":
        return ", ".join(sorted(VIDEO_EXTENSIONS))
    if group == "audio":
        return ", ".join(sorted(AUDIO_EXTENSIONS))
    if group == "media":
        return ", ".join(sorted(MEDIA_EXTENSIONS))
    return ", ".join(sorted(ALLOWED_EXTENSIONS))
