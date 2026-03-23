"""CLI entry point — Click command group wiring all sub-commands together."""

import asyncio
import json
from pathlib import Path

import click

from . import __version__


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(__version__, prog_name="telegram-memory")
def cli() -> None:
    """telegram-memory — sync and search your Telegram history locally.

    Typical workflow:

    \b
      telegram-memory auth          # first-time setup
      telegram-memory sync --all    # pull all chats
      telegram-memory search "foo"  # search messages
    """


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------

@cli.command()
def auth() -> None:
    """Set up Telegram API credentials and authenticate."""
    from .auth import interactive_auth

    asyncio.run(interactive_auth())


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--chat", "chat_filter", default=None, help="Chat name or numeric ID to sync.")
@click.option("--all", "sync_all", is_flag=True, default=False, help="Sync all chats/groups/channels.")
@click.option("--limit", default=None, type=int, help="Maximum number of messages to fetch per chat.")
def sync(chat_filter: str | None, sync_all: bool, limit: int | None) -> None:
    """Sync messages from Telegram into the local SQLite database.

    Examples:

    \b
      telegram-memory sync --all
      telegram-memory sync --chat "My Group" --limit 1000
      telegram-memory sync --chat -1001234567890
    """
    from .sync import run_sync

    asyncio.run(run_sync(chat_filter=chat_filter, sync_all=sync_all, limit=limit))


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("query")
@click.option("--chat", default=None, help="Filter by chat name (substring match).")
@click.option("--from", "sender", default=None, help="Filter by sender name (substring match).")
@click.option("--after", default=None, metavar="DATE", help="Only messages on or after this date (YYYY-MM-DD).")
@click.option("--before", default=None, metavar="DATE", help="Only messages on or before this date (YYYY-MM-DD).")
@click.option("--limit", default=20, show_default=True, help="Maximum number of results.")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output results as JSON.")
def search(
    query: str,
    chat: str | None,
    sender: str | None,
    after: str | None,
    before: str | None,
    limit: int,
    as_json: bool,
) -> None:
    """Full-text search over synced messages.

    QUERY supports FTS5 syntax: phrase "exact phrase", OR, NOT, prefix*.

    Examples:

    \b
      telegram-memory search "project deadline"
      telegram-memory search "invoice" --chat "Finance" --after 2026-01-01
      telegram-memory search "meeting" --from Alice --limit 5 --json
    """
    from .search import run_search

    run_search(
        query=query,
        chat=chat,
        sender=sender,
        after=after,
        before=before,
        limit=limit,
        as_json=as_json,
    )


# ---------------------------------------------------------------------------
# chats
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def chats(as_json: bool) -> None:
    """List all chats that have been synced to the local database."""
    from .db import init_db, list_chats

    db_path = Path.home() / ".telegram-memory" / "messages.db"
    if not db_path.exists():
        raise click.ClickException("No database found. Run `telegram-memory sync` first.")

    conn = init_db(db_path)
    rows = list_chats(conn)
    conn.close()

    if not rows:
        click.echo("No chats synced yet.")
        return

    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    # Human-readable table
    col_id = max(len(str(r["chat_id"])) for r in rows)
    col_name = max(len(r["chat_name"] or "") for r in rows)
    col_count = max(len(str(r["message_count"])) for r in rows)

    header = (
        f"{'ID':<{col_id}}  {'Chat name':<{col_name}}  {'Messages':>{col_count}}  Last sync"
    )
    click.echo(header)
    click.echo("-" * len(header))

    for r in rows:
        last_sync = (r["last_sync"] or "never")[:19].replace("T", " ")
        click.echo(
            f"{str(r['chat_id']):<{col_id}}  "
            f"{(r['chat_name'] or ''):<{col_name}}  "
            f"{str(r['message_count']):>{col_count}}  "
            f"{last_sync}"
        )
