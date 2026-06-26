"""
One-time migration: JSON files → SQLite

Sources ingested (in order):
  1. backend/data/files.json
  2. backend/data/transcripts.json
  3. backend/data/summaries.json
  4. backend/data/chats.json
  5. backend/uploads/<uuid>/transcript.json  (catches any not in data/)

Run once:
    cd backend
    python database/migrate.py

Safe to re-run — uses INSERT OR IGNORE / ON CONFLICT DO UPDATE.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Allow running directly from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from database.db import init_db, get_db
from database import queries

ROOT = Path(__file__).resolve().parent.parent   # backend/
DATA = ROOT / "data"
UPLOADS = ROOT / "uploads"

# Current machine's upload folder for path normalisation
CURRENT_UPLOADS = str(UPLOADS)


def _fix_path(raw: str) -> str:
    """Normalise hardcoded paths from other machines to the current uploads folder."""
    p = Path(raw)
    # If the file exists as-is, keep it
    if p.exists():
        return str(p)
    # Try to resolve relative to current uploads
    candidate = UPLOADS / p.name
    if candidate.exists():
        return str(candidate)
    # Return as-is — the file may have been lost
    return raw


def _load(filename: str) -> dict | list:
    path = DATA / filename
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [warn] could not read {filename}: {e}")
        return {}


# ── 1. Init schema ────────────────────────────────────────────────────────────

print("Initialising database schema…")
init_db()

# ── 2. files.json ─────────────────────────────────────────────────────────────

print("Migrating files.json…")
files: dict = _load("files.json")
for file_id, meta in files.items():
    queries.upsert_file(
        file_id      = file_id,
        original_name= meta.get("originalName", "unknown"),
        file_path    = _fix_path(meta.get("path", "")),
        file_type    = meta.get("type", "audio"),
        status       = meta.get("status", "uploaded"),
        uploaded_at  = meta.get("uploadedAt"),
        processed_at = meta.get("processed_at"),
        user_id      = meta.get("userId", "demo_user_123"),
    )
print(f"  {len(files)} files migrated")

# ── 3. transcripts.json ───────────────────────────────────────────────────────

print("Migrating transcripts.json…")
transcripts: dict = _load("transcripts.json")
count = 0
for file_id, t in transcripts.items():
    queries.upsert_transcript(
        file_id      = file_id,
        full_text    = t.get("full_text", ""),
        segments     = t.get("segments", []),
        conversation = t.get("conversation", []),
        per_speaker  = t.get("per_speaker", {}),
        speaker_count= t.get("speaker_count", 1),
        duration     = t.get("duration", ""),
        model_info   = t.get("model_info", {}),
        emotion_analysis = t.get("emotion_analysis"),
        created_at   = t.get("createdAt"),
    )
    count += 1
print(f"  {count} transcripts migrated")

# ── 4. summaries.json ─────────────────────────────────────────────────────────

print("Migrating summaries.json…")
summaries: dict = _load("summaries.json")
count = 0
for file_id, s in summaries.items():
    # Make sure the parent file row exists (summaries might predate files.json sync)
    if not queries.get_file(file_id):
        file_meta = files.get(file_id, {})
        queries.upsert_file(
            file_id       = file_id,
            original_name = file_meta.get("originalName", "unknown"),
            file_path     = _fix_path(file_meta.get("path", "")),
            file_type     = "pdf",
            status        = "completed",
            uploaded_at   = file_meta.get("uploadedAt"),
            processed_at  = s.get("createdAt"),
        )
    queries.upsert_summary(
        file_id           = file_id,
        full_text         = s.get("full_text", ""),
        gemma             = s.get("gemma", ""),
        template          = s.get("template", ""),
        original_length   = s.get("original_length", 0),
        summary_length    = s.get("summary_length", s.get("gemma_length", 0)),
        compression_ratio = s.get("compression_ratio", 0.0),
        model_used        = s.get("model_used", "template"),
        created_at        = s.get("createdAt"),
    )
    count += 1
print(f"  {count} summaries migrated")

# ── 5. chats.json ─────────────────────────────────────────────────────────────

print("Migrating chats.json…")
chats = _load("chats.json")
if not isinstance(chats, list):
    chats = []
count = 0
for chat in chats:
    if not chat.get("id"):
        continue
    existing = queries.get_chat(chat["id"])
    if existing:
        continue   # already there from a previous run
    queries.insert_chat(
        chat_id    = chat["id"],
        user_id    = chat.get("userId", "demo_user_123"),
        title      = chat.get("title", "Chat"),
        pinned     = bool(chat.get("pinned", False)),
        messages   = chat.get("messages", []),
        attached   = chat.get("attached", []),
        created_at = chat.get("createdAt"),
    )
    count += 1
print(f"  {count} chats migrated")

# ── 6. uploads/<uuid>/transcript.json (catch extras) ─────────────────────────

print("Scanning uploads/ for extra transcript.json files…")
extra = 0
if UPLOADS.exists():
    for uid_dir in UPLOADS.iterdir():
        if not uid_dir.is_dir():
            continue
        file_id = uid_dir.name
        tj = uid_dir / "transcript.json"
        if not tj.exists():
            continue
        if queries.get_transcript(file_id):
            continue   # already migrated from transcripts.json

        try:
            d = json.loads(tj.read_text(encoding="utf-8"))
        except Exception:
            continue

        # Ensure file row exists
        if not queries.get_file(file_id):
            # Try to find the original media file
            media = next(
                (f for f in UPLOADS.iterdir()
                 if f.is_file() and f.stem == file_id),
                None,
            )
            queries.upsert_file(
                file_id       = file_id,
                original_name = d.get("original_name", file_id),
                file_path     = str(media) if media else str(uid_dir),
                file_type     = "audio",
                status        = "completed",
            )

        queries.upsert_transcript(
            file_id          = file_id,
            full_text        = d.get("full_text", ""),
            segments         = d.get("segments_with_text", d.get("segments", [])),
            conversation     = d.get("conversation", []),
            per_speaker      = d.get("per_speaker", {}),
            speaker_count    = d.get("speaker_count", 1),
            duration         = d.get("duration", ""),
            model_info       = d.get("model_info", {}),
            emotion_analysis = d.get("emotion_analysis"),
        )
        extra += 1

print(f"  {extra} extra transcripts migrated from uploads/")

# ── 7. Summary ────────────────────────────────────────────────────────────────

db = get_db()
n_files  = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
n_tr     = db.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
n_su     = db.execute("SELECT COUNT(*) FROM summaries").fetchone()[0]
n_ch     = db.execute("SELECT COUNT(*) FROM chats").fetchone()[0]

print()
print("Migration complete:")
print(f"  files:       {n_files}")
print(f"  transcripts: {n_tr}")
print(f"  summaries:   {n_su}")
print(f"  chats:       {n_ch}")
print(f"  DB:          {ROOT / 'data' / 'platform.db'}")
