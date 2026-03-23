"""Full-text search over synced messages using SQLite FTS5."""

import json
import sqlite3
from pathlib import Path

import click

from .db import get_connection


DB_PATH = Path.home() / ".telegram-memory" / "messages.db"


def _build_query(
    query: str,
    chat: str | None,
    sender: str | None,
    after: str | None,
    before: str | None,
    limit: int,
) -> tuple[str, list]:
    """Build the SQL query and parameter list for a search request."""
    # FTS5 match against the virtual table; then join back to get full row data.
    sql = """
        SELECT
            m.id,
            m.chat_id,
            m.chat_name,
            m.sender_id,
            m.sender_name,
            m.message_text,
            m.date,
            m.reply_to_id,
            m.media_type
        FROM messages_fts fts
        JOIN messages m ON m.id = fts.rowid
        WHERE messages_fts MATCH ?
    """
    params: list = [query]

    if chat:
        sql += " AND m.chat_name LIKE ?"
        params.append(f"%{chat}%")

    if sender:
        sql += " AND m.sender_name LIKE ?"
        params.append(f"%{sender}%")

    if after:
        sql += " AND m.date >= ?"
        params.append(after)

    if before:
        sql += " AND m.date <= ?"
        params.append(before)

    sql += " ORDER BY m.date DESC LIMIT ?"
    params.append(limit)

    return sql, params


def run_search(
    query: str,
    chat: str | None,
    sender: str | None,
    after: str | None,
    before: str | None,
    limit: int,
    as_json: bool,
) -> None:
    """Execute a search and print results to stdout."""
    if not DB_PATH.exists():
        raise click.ClickException(
            "No database found. Run `telegram-memory sync` first."
        )

    conn = get_connection(DB_PATH)

    try:
        sql, params = _build_query(query, chat, sender, after, before, limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        raise click.ClickException(f"Search failed: {exc}")
    finally:
        conn.close()

    if not rows:
        click.echo("No results found.")
        return

    if as_json:
        click.echo(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
        return

    # Human-readable output
    click.echo(f"Found {len(rows)} result(s):\n")
    for row in rows:
        date = row["date"][:19].replace("T", " ")  # trim timezone, pretty-print
        sender_name = row["sender_name"] or "Unknown"
        chat_name = row["chat_name"] or str(row["chat_id"])
        text = (row["message_text"] or "[media]").replace("\n", " ")

        # Truncate long messages in the listing view
        if len(text) > 200:
            text = text[:197] + "…"

        click.echo(
            f"[{date}] {click.style(chat_name, fg='cyan')} | "
            f"{click.style(sender_name, fg='green')}\n"
            f"  {text}\n"
        )
