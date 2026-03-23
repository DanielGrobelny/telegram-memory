"""Database layer — schema creation, upserts, and sync-state management."""

import sqlite3
from pathlib import Path


# DDL -------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY,
    chat_id     INTEGER NOT NULL,
    chat_name   TEXT,
    sender_id   INTEGER,
    sender_name TEXT,
    message_text TEXT,
    date        TEXT NOT NULL,   -- ISO 8601
    reply_to_id INTEGER,
    media_type  TEXT,            -- photo, video, voice, document, null
    raw_json    TEXT             -- full message as JSON for future use
);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    message_text,
    sender_name,
    chat_name,
    content=messages,
    content_rowid=id
);

-- Keep FTS index in sync with the messages table via triggers.
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, message_text, sender_name, chat_name)
    VALUES (new.id, new.message_text, new.sender_name, new.chat_name);
END;

CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, message_text, sender_name, chat_name)
    VALUES ('delete', old.id, old.message_text, old.sender_name, old.chat_name);
END;

CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, message_text, sender_name, chat_name)
    VALUES ('delete', old.id, old.message_text, old.sender_name, old.chat_name);
    INSERT INTO messages_fts(rowid, message_text, sender_name, chat_name)
    VALUES (new.id, new.message_text, new.sender_name, new.chat_name);
END;

CREATE TABLE IF NOT EXISTS sync_state (
    chat_id         INTEGER PRIMARY KEY,
    last_message_id INTEGER,
    last_sync       TEXT   -- ISO 8601
);
"""


# Connection ------------------------------------------------------------------

def get_connection(db_path: Path) -> sqlite3.Connection:
    """Return a connection with WAL mode and foreign-key support enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path) -> sqlite3.Connection:
    """Create (or open) the database and apply the schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


# Messages --------------------------------------------------------------------

def upsert_message(conn: sqlite3.Connection, msg: dict) -> None:
    """Insert or replace a single message row."""
    conn.execute(
        """
        INSERT OR REPLACE INTO messages
            (id, chat_id, chat_name, sender_id, sender_name,
             message_text, date, reply_to_id, media_type, raw_json)
        VALUES
            (:id, :chat_id, :chat_name, :sender_id, :sender_name,
             :message_text, :date, :reply_to_id, :media_type, :raw_json)
        """,
        msg,
    )


def upsert_messages(conn: sqlite3.Connection, messages: list[dict]) -> int:
    """Bulk-insert messages and return the count written."""
    for msg in messages:
        upsert_message(conn, msg)
    conn.commit()
    return len(messages)


# Sync state ------------------------------------------------------------------

def get_sync_state(conn: sqlite3.Connection, chat_id: int) -> dict | None:
    """Return the last known sync state for a chat, or None."""
    row = conn.execute(
        "SELECT chat_id, last_message_id, last_sync FROM sync_state WHERE chat_id = ?",
        (chat_id,),
    ).fetchone()
    return dict(row) if row else None


def set_sync_state(
    conn: sqlite3.Connection, chat_id: int, last_message_id: int, last_sync: str
) -> None:
    """Persist sync state for a chat."""
    conn.execute(
        """
        INSERT OR REPLACE INTO sync_state (chat_id, last_message_id, last_sync)
        VALUES (?, ?, ?)
        """,
        (chat_id, last_message_id, last_sync),
    )
    conn.commit()


# Chats -----------------------------------------------------------------------

def list_chats(conn: sqlite3.Connection) -> list[dict]:
    """Return all chats with message counts and last-sync timestamps."""
    rows = conn.execute(
        """
        SELECT
            m.chat_id,
            m.chat_name,
            COUNT(m.id)  AS message_count,
            s.last_sync
        FROM messages m
        LEFT JOIN sync_state s ON s.chat_id = m.chat_id
        GROUP BY m.chat_id
        ORDER BY message_count DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]
