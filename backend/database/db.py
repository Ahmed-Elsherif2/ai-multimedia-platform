"""
SQLite database layer — connection management and schema creation.

One connection per thread (thread-local) with WAL mode for concurrent reads.
Hosting compatible with configurable data directory.
"""
from __future__ import annotations

import sqlite3
import threading
import os
from pathlib import Path

# Thread-local storage
_local = threading.local()


def get_data_folder() -> Path:
    """Get data folder from environment or default"""
    data_dir = os.getenv('DATA_DIR', 'data')
    return Path(data_dir)


def get_db_path() -> Path:
    """Get database path from environment or default"""
    data_folder = get_data_folder()
    db_name = os.getenv('DB_NAME', 'platform.db')
    return data_folder / db_name


def get_db() -> sqlite3.Connection:
    """Return the thread-local SQLite connection, opening it if needed."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        db_path = get_db_path()
        
        # Ensure directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")  # Good balance for hosting
        
        _local.conn = conn
    return conn


def close_db() -> None:
    """Close the current thread's database connection."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def init_db() -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS users (
            id         TEXT PRIMARY KEY,
            username   TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS files (
            id           TEXT PRIMARY KEY,
            user_id      TEXT    NOT NULL DEFAULT 'default_user',
            original_name TEXT   NOT NULL,
            file_path    TEXT    NOT NULL,
            file_type    TEXT    NOT NULL DEFAULT 'audio',
            status       TEXT    NOT NULL DEFAULT 'uploaded',
            uploaded_at  TEXT,
            processed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS transcripts (
            file_id       TEXT PRIMARY KEY,
            full_text     TEXT    NOT NULL DEFAULT '',
            segments      TEXT    NOT NULL DEFAULT '[]',
            conversation  TEXT    NOT NULL DEFAULT '[]',
            per_speaker   TEXT    NOT NULL DEFAULT '{}',
            speaker_count INTEGER NOT NULL DEFAULT 1,
            duration      TEXT             DEFAULT '',
            model_info    TEXT             DEFAULT '{}',
            emotion_analysis TEXT          DEFAULT NULL,
            created_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS summaries (
            file_id          TEXT PRIMARY KEY,
            full_text        TEXT    NOT NULL DEFAULT '',
            groq             TEXT    NOT NULL DEFAULT '',
            template         TEXT    NOT NULL DEFAULT '',
            original_length  INTEGER NOT NULL DEFAULT 0,
            summary_length   INTEGER NOT NULL DEFAULT 0,
            compression_ratio REAL   NOT NULL DEFAULT 0.0,
            model_used       TEXT    NOT NULL DEFAULT 'template',
            created_at       TEXT
        );

        CREATE TABLE IF NOT EXISTS chats (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL DEFAULT 'default_user',
            title      TEXT NOT NULL DEFAULT 'New Chat',
            pinned     INTEGER NOT NULL DEFAULT 0,
            messages   TEXT    NOT NULL DEFAULT '[]',
            attached   TEXT    NOT NULL DEFAULT '[]',
            processedFiles   TEXT NOT NULL DEFAULT '{}',
            summarizedFiles  TEXT NOT NULL DEFAULT '{}',
            failedFiles      TEXT NOT NULL DEFAULT '{}',
            created_at TEXT,
            updated_at TEXT
        );

        -- Indexes for performance
        CREATE INDEX IF NOT EXISTS idx_files_user_id ON files(user_id);
        CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
        CREATE INDEX IF NOT EXISTS idx_transcripts_file_id ON transcripts(file_id);
        CREATE INDEX IF NOT EXISTS idx_summaries_file_id ON summaries(file_id);
        CREATE INDEX IF NOT EXISTS idx_chats_user_id ON chats(user_id);
    """)
    conn.commit()
    conn.close()
    print(f"[db] SQLite ready: {db_path}")