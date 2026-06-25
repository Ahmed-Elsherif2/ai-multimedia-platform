"""
Thread-safe atomic JSON file store.
⚠️ DEPRECATED: Use database/queries.py instead.
Kept for backward compatibility with old routes.
"""
from __future__ import annotations

import json
import threading
import warnings
from pathlib import Path
from typing import Any, Callable

from config.settings import settings

# Show deprecation warning once
warnings.warn(
    "json_store is deprecated. Use database/queries.py instead.",
    DeprecationWarning,
    stacklevel=2
)

_locks = {}
_locks_meta = threading.Lock()


def _get_lock(filename: str) -> threading.RLock:
    with _locks_meta:
        if filename not in _locks:
            _locks[filename] = threading.RLock()
        return _locks[filename]


def _read(filepath: Path, filename: str) -> Any:
    if filepath.exists():
        try:
            text = filepath.read_text(encoding="utf-8").strip()
            if text:
                return json.loads(text)
        except json.JSONDecodeError:
            pass
    default = [] if "chats" in filename else {}
    filepath.write_text(json.dumps(default, indent=2), encoding="utf-8")
    return default


def _write(filepath: Path, data: Any) -> None:
    """Atomic write via a temp file."""
    tmp = filepath.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(filepath)


def load_json(filename: str) -> Any:
    """⚠️ DEPRECATED: Use queries.get_*() instead."""
    lock = _get_lock(filename)
    with lock:
        return _read(settings.DATA_FOLDER / filename, filename)


def save_json(filename: str, data: Any) -> None:
    """⚠️ DEPRECATED: Use queries.upsert_*() instead."""
    lock = _get_lock(filename)
    with lock:
        _write(settings.DATA_FOLDER / filename, data)


def update_json(filename: str, fn: Callable) -> Any:
    """⚠️ DEPRECATED: Use queries.upsert_*() instead."""
    lock = _get_lock(filename)
    with lock:
        filepath = settings.DATA_FOLDER / filename
        data = _read(filepath, filename)
        updated = fn(data)
        if updated is not None:
            data = updated
        _write(filepath, data)
        return data