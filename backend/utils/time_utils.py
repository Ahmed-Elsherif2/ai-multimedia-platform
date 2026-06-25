"""Time formatting helpers shared across services and routes."""
from __future__ import annotations


def seconds_to_hms(seconds: float) -> str:
    """Return HH:MM:SS string from a float number of seconds."""
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_timestamp(seconds: float) -> str:
    """Return HH:MM:SS.mmm string (suitable for SRT / transcript display)."""
    total = int(seconds)
    ms    = int((seconds - total) * 1000)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def seconds_to_readable(seconds: float) -> str:
    """Return a compact human-readable string, e.g. '2h 5m 30s'."""
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    parts: list[str] = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)
