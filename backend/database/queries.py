"""
All database read/write helpers.

Every function opens with get_db() — no connection is passed by callers.
JSON blobs are automatically serialised/deserialised so callers work with dicts.
Hosting compatible with configurable user_id.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from database.db import get_db

# Default user for single-user mode
DEFAULT_USER = os.getenv('DEFAULT_USER', 'default_user')


# ── helpers ───────────────────────────────────────────────────────────────────

def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)

def _d(s: str | None, default=None) -> Any:
    if not s:
        return default if default is not None else {}
    try:
        return json.loads(s)
    except Exception:
        return default if default is not None else {}

def _now() -> str:
    return datetime.now().isoformat()

def _row(r) -> dict | None:
    return dict(r) if r else None


# ── files ─────────────────────────────────────────────────────────────────────

def upsert_file(
    file_id: str,
    original_name: str,
    file_path: str,
    file_type: str = "audio",
    status: str = "uploaded",
    uploaded_at: str | None = None,
    processed_at: str | None = None,
    user_id: str = None,
) -> None:
    """Insert or update a file record"""
    db = get_db()
    user_id = user_id or DEFAULT_USER
    
    db.execute(
        """
        INSERT INTO files (id, user_id, original_name, file_path, file_type,
                           status, uploaded_at, processed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            status       = excluded.status,
            processed_at = excluded.processed_at,
            file_path    = excluded.file_path,
            original_name = excluded.original_name,
            file_type    = excluded.file_type
        """,
        (file_id, user_id, original_name, file_path, file_type,
         status, uploaded_at or _now(), processed_at),
    )
    db.commit()


def update_file_status(file_id: str, status: str, processed_at: str | None = None) -> None:
    db = get_db()
    db.execute(
        "UPDATE files SET status=?, processed_at=? WHERE id=?",
        (status, processed_at or _now(), file_id),
    )
    db.commit()


def get_file(file_id: str) -> dict | None:
    row = get_db().execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    return _row(row)


def get_all_files(user_id: str = None) -> List[dict]:
    user_id = user_id or DEFAULT_USER
    rows = get_db().execute(
        "SELECT * FROM files WHERE user_id=? ORDER BY uploaded_at DESC", (user_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_file_by_path(file_path: str) -> dict | None:
    """Get file by path (useful for finding existing files)"""
    row = get_db().execute(
        "SELECT * FROM files WHERE file_path=?", (file_path,)
    ).fetchone()
    return _row(row)


def delete_file(file_id: str, user_id: str = None) -> bool:
    """Delete a file record (and any associated results)"""
    user_id = user_id or DEFAULT_USER
    db = get_db()
    
    # Delete from related tables
    db.execute("DELETE FROM transcripts WHERE file_id=?", (file_id,))
    db.execute("DELETE FROM summaries WHERE file_id=?", (file_id,))
    
    # Delete file
    cur = db.execute(
        "DELETE FROM files WHERE id=? AND user_id=?", (file_id, user_id)
    )
    db.commit()
    return cur.rowcount > 0

def delete_all_files(user_id: str = None) -> int:
    """
    Delete ALL files and associated data for a user.
    Returns the number of files deleted.
    """
    user_id = user_id or DEFAULT_USER
    db = get_db()
    
    # Get all file IDs for this user
    rows = db.execute(
        "SELECT id FROM files WHERE user_id=?", (user_id,)
    ).fetchall()
    
    file_ids = [row[0] for row in rows]
    count = len(file_ids)
    
    # Delete all files one by one (triggers cascade)
    for file_id in file_ids:
        delete_file(file_id, user_id)
    
    db.commit()
    return count


def get_storage_stats(user_id: str = None) -> dict:
    """
    Get storage usage statistics for a user.
    """
    user_id = user_id or DEFAULT_USER
    db = get_db()
    
    # Count files
    file_count = db.execute(
        "SELECT COUNT(*) FROM files WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    
    transcript_count = db.execute(
        """
        SELECT COUNT(*) FROM transcripts t
        JOIN files f ON f.id = t.file_id
        WHERE f.user_id=?
        """, (user_id,)
    ).fetchone()[0]
    
    summary_count = db.execute(
        """
        SELECT COUNT(*) FROM summaries s
        JOIN files f ON f.id = s.file_id
        WHERE f.user_id=?
        """, (user_id,)
    ).fetchone()[0]
    
    chat_count = db.execute(
        "SELECT COUNT(*) FROM chats WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    
    return {
        "files": file_count,
        "transcripts": transcript_count,
        "summaries": summary_count,
        "chats": chat_count
    }


# ── transcripts ───────────────────────────────────────────────────────────────

def upsert_transcript(
    file_id: str,
    full_text: str,
    segments: list,
    conversation: list,
    per_speaker: dict,
    speaker_count: int = 1,
    duration: str = "",
    model_info: dict | None = None,
    emotion_analysis: dict | None = None,
    created_at: str | None = None,
) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO transcripts (file_id, full_text, segments, conversation,
            per_speaker, speaker_count, duration, model_info, emotion_analysis, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_id) DO UPDATE SET
            full_text        = excluded.full_text,
            segments         = excluded.segments,
            conversation     = excluded.conversation,
            per_speaker      = excluded.per_speaker,
            speaker_count    = excluded.speaker_count,
            duration         = excluded.duration,
            model_info       = excluded.model_info,
            emotion_analysis = excluded.emotion_analysis
        """,
        (
            file_id, full_text,
            _j(segments), _j(conversation), _j(per_speaker),
            speaker_count, duration,
            _j(model_info or {}),
            _j(emotion_analysis) if emotion_analysis else None,
            created_at or _now(),
        ),
    )
    db.commit()


def update_transcript_emotion(file_id: str, emotion_analysis: dict) -> None:
    get_db().execute(
        "UPDATE transcripts SET emotion_analysis=? WHERE file_id=?",
        (_j(emotion_analysis), file_id),
    )
    get_db().commit()


def get_transcript(file_id: str) -> dict | None:
    row = get_db().execute(
        "SELECT * FROM transcripts WHERE file_id=?", (file_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["segments"]         = _d(d["segments"],  [])
    d["conversation"]     = _d(d["conversation"], [])
    d["per_speaker"]      = _d(d["per_speaker"],  {})
    d["model_info"]       = _d(d["model_info"],   {})
    d["emotion_analysis"] = _d(d.get("emotion_analysis"))
    return d


def get_all_transcripts(user_id: str = None) -> List[dict]:
    user_id = user_id or DEFAULT_USER
    rows = get_db().execute(
        """
        SELECT t.* FROM transcripts t
        JOIN files f ON f.id = t.file_id
        WHERE f.user_id=?
        ORDER BY t.created_at DESC
        """,
        (user_id,),
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["segments"]         = _d(d["segments"],  [])
        d["conversation"]     = _d(d["conversation"], [])
        d["per_speaker"]      = _d(d["per_speaker"],  {})
        d["model_info"]       = _d(d["model_info"],   {})
        d["emotion_analysis"] = _d(d.get("emotion_analysis"))
        result.append(d)
    return result


def delete_transcript(file_id: str) -> bool:
    cur = get_db().execute(
        "DELETE FROM transcripts WHERE file_id=?", (file_id,)
    )
    get_db().commit()
    return cur.rowcount > 0


# ── summaries ─────────────────────────────────────────────────────────────────

def upsert_summary(
    file_id: str,
    full_text: str,
    groq: str = "",
    template: str = "",
    original_length: int = 0,
    summary_length: int = 0,
    compression_ratio: float = 0.0,
    model_used: str = "template",
    created_at: str | None = None,
) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO summaries (file_id, full_text, groq, template,
            original_length, summary_length, compression_ratio, model_used, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_id) DO UPDATE SET
            full_text         = excluded.full_text,
            groq              = excluded.groq,
            template          = excluded.template,
            original_length   = excluded.original_length,
            summary_length    = excluded.summary_length,
            compression_ratio = excluded.compression_ratio,
            model_used        = excluded.model_used
        """,
        (file_id, full_text, groq, template,
         original_length, summary_length, compression_ratio, model_used,
         created_at or _now()),
    )
    db.commit()


def get_summary(file_id: str) -> dict | None:
    row = get_db().execute(
        "SELECT * FROM summaries WHERE file_id=?", (file_id,)
    ).fetchone()
    return _row(row)


def get_all_summaries(user_id: str = None) -> List[dict]:
    user_id = user_id or DEFAULT_USER
    rows = get_db().execute(
        """
        SELECT s.* FROM summaries s
        JOIN files f ON f.id = s.file_id
        WHERE f.user_id=?
        ORDER BY s.created_at DESC
        """,
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_summary(file_id: str) -> bool:
    cur = get_db().execute(
        "DELETE FROM summaries WHERE file_id=?", (file_id,)
    )
    get_db().commit()
    return cur.rowcount > 0


# ── chats ─────────────────────────────────────────────────────────────────────

def insert_chat(
    chat_id: str,
    user_id: str = None,
    title: str = "New Chat",
    pinned: bool = False,
    messages: list | None = None,
    attached: list | None = None,
    processedFiles: dict | None = None,
    summarizedFiles: dict | None = None,
    failedFiles: dict | None = None,
    created_at: str | None = None,
) -> dict:
    db = get_db()
    user_id = user_id or DEFAULT_USER
    now = created_at or _now()
    
    db.execute(
        """
        INSERT INTO chats (
            id, user_id, title, pinned, messages, attached,
            processedFiles, summarizedFiles, failedFiles, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chat_id, user_id, title, int(pinned),
            _j(messages or []),
            _j(attached or []),
            _j(processedFiles or {}),
            _j(summarizedFiles or {}),
            _j(failedFiles or {}),
            now, now
        ),
    )
    db.commit()
    return get_chat(chat_id)


def update_chat(
    chat_id: str, 
    user_id: str = None, 
    fields: dict = None
) -> dict | None:
    user_id = user_id or DEFAULT_USER
    db = get_db()
    
    row = db.execute(
        "SELECT * FROM chats WHERE id=? AND user_id=?", (chat_id, user_id)
    ).fetchone()
    if not row:
        return None

    current = dict(row)
    current["messages"] = _d(current["messages"], [])
    current["attached"] = _d(current["attached"], [])

    allowed = {"title", "pinned", "messages", "attached",
               "processedFiles", "summarizedFiles", "failedFiles"}
    
    fields = fields or {}
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "pinned":
            current["pinned"] = int(bool(v))
        elif k in ("messages", "attached", "processedFiles", "summarizedFiles", "failedFiles"):
            current[k] = v
        else:
            current[k] = v

    db.execute(
        """
        UPDATE chats
        SET title=?, pinned=?, messages=?, attached=?, 
            processedFiles=?, summarizedFiles=?, failedFiles=?, updated_at=?
        WHERE id=? AND user_id=?
        """,
        (
            current.get("title"),
            current["pinned"],
            _j(current["messages"]),
            _j(current["attached"]),
            _j(current.get("processedFiles", {})),
            _j(current.get("summarizedFiles", {})),
            _j(current.get("failedFiles", {})),
            _now(),
            chat_id,
            user_id
        ),
    )
    db.commit()
    return get_chat(chat_id)

def delete_chat(chat_id: str, user_id: str = None) -> bool:
    user_id = user_id or DEFAULT_USER
    db = get_db()
    cur = db.execute(
        "DELETE FROM chats WHERE id=? AND user_id=?", (chat_id, user_id)
    )
    db.commit()
    return cur.rowcount > 0


def get_chat(chat_id: str) -> dict | None:
    row = get_db().execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["messages"] = _d(d["messages"], [])
    d["attached"] = _d(d["attached"],  [])
    d["processedFiles"] = _d(d.get("processedFiles"), {})
    d["summarizedFiles"] = _d(d.get("summarizedFiles"), {})
    d["failedFiles"] = _d(d.get("failedFiles"), {})
    d["pinned"] = bool(d["pinned"])
    return d


def get_user_chats(user_id: str = None) -> List[dict]:
    user_id = user_id or DEFAULT_USER
    rows = get_db().execute(
        "SELECT * FROM chats WHERE user_id=? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["messages"] = _d(d["messages"], [])
        d["attached"] = _d(d["attached"],  [])
        d["pinned"]   = bool(d["pinned"])
        result.append(d)
    return result