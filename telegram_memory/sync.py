"""Sync logic — fetch messages from Telegram and store them in SQLite."""

import json
from datetime import datetime, timezone
from pathlib import Path

import click
from telethon import TelegramClient
from telethon.tl.types import (
    MessageMediaDocument,
    MessageMediaPhoto,
    MessageMediaWebPage,
    User,
    Chat,
    Channel,
)

from .db import init_db, upsert_messages, get_sync_state, set_sync_state, list_chats


DB_PATH = Path.home() / ".telegram-memory" / "messages.db"


def _media_type(media) -> str | None:
    """Classify media attached to a message into a short type string."""
    if media is None or isinstance(media, MessageMediaWebPage):
        return None
    if isinstance(media, MessageMediaPhoto):
        return "photo"
    if isinstance(media, MessageMediaDocument):
        doc = media.document
        if hasattr(doc, "mime_type"):
            mime = doc.mime_type
            if mime.startswith("video/"):
                return "video"
            if mime.startswith("audio/"):
                return "voice"
        return "document"
    return "other"


def _entity_name(entity) -> str:
    """Return a human-readable name for a Telegram entity."""
    if isinstance(entity, User):
        parts = [entity.first_name or "", entity.last_name or ""]
        name = " ".join(p for p in parts if p).strip()
        return name or str(entity.id)
    if isinstance(entity, (Chat, Channel)):
        return entity.title or str(entity.id)
    return str(entity.id) if entity else "Unknown"


async def sync_chat(
    client: TelegramClient,
    entity,
    chat_id: int,
    chat_name: str,
    limit: int | None,
    conn,
) -> int:
    """Sync one chat and return the number of new messages stored."""
    state = get_sync_state(conn, chat_id)
    min_id = state["last_message_id"] if state else 0

    batch: list[dict] = []
    last_msg_id = min_id

    click.echo(
        f"  Syncing '{chat_name}' (id={chat_id}, since msg_id={min_id})…",
        nl=False,
    )

    async for msg in client.iter_messages(
        entity,
        limit=limit,
        min_id=min_id,
        reverse=True,   # oldest first so last_message_id advances correctly
    ):
        if not msg.text and not msg.media:
            continue  # skip service messages with no content

        # Sender name
        sender_name: str | None = None
        sender_id: int | None = None
        if msg.sender:
            sender_name = _entity_name(msg.sender)
            sender_id = msg.sender_id

        date_iso = msg.date.astimezone(timezone.utc).isoformat()

        # Serialize the full message to JSON for future use, but skip
        # unserializable objects gracefully.
        try:
            raw = json.dumps(msg.to_dict(), default=str)
        except Exception:
            raw = None

        batch.append(
            {
                "id": msg.id,
                "chat_id": chat_id,
                "chat_name": chat_name,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "message_text": msg.text,
                "date": date_iso,
                "reply_to_id": msg.reply_to_msg_id,
                "media_type": _media_type(msg.media),
                "raw_json": raw,
            }
        )

        if msg.id > last_msg_id:
            last_msg_id = msg.id

        # Flush in batches of 500 to keep memory usage low.
        if len(batch) >= 500:
            upsert_messages(conn, batch)
            batch.clear()

    if batch:
        upsert_messages(conn, batch)

    if last_msg_id > min_id:
        set_sync_state(
            conn,
            chat_id,
            last_msg_id,
            datetime.now(timezone.utc).isoformat(),
        )

    total = last_msg_id - min_id  # approximate; fine for progress display
    click.echo(f" done ({total} new msg ids processed)")
    return total


async def run_sync(
    chat_filter: str | None,
    sync_all: bool,
    limit: int | None,
) -> None:
    """Entry point called by the CLI sync command."""
    from .auth import get_client

    conn = init_db(DB_PATH)
    client = get_client()

    await client.connect()

    if not await client.is_user_authorized():
        await client.disconnect()
        raise click.ClickException("Not authenticated. Run `telegram-memory auth` first.")

    try:
        if sync_all:
            # Collect all dialogs (chats/groups/channels) the user is part of.
            click.echo("Fetching dialog list…")
            async for dialog in client.iter_dialogs():
                await sync_chat(
                    client,
                    dialog.entity,
                    dialog.id,
                    dialog.name,
                    limit,
                    conn,
                )
        elif chat_filter:
            # Resolve by name or numeric ID.
            try:
                entity = await client.get_entity(
                    int(chat_filter) if chat_filter.lstrip("-").isdigit() else chat_filter
                )
            except Exception as exc:
                raise click.ClickException(f"Could not resolve chat '{chat_filter}': {exc}")

            chat_id = entity.id
            chat_name = _entity_name(entity)
            await sync_chat(client, entity, chat_id, chat_name, limit, conn)
        else:
            raise click.ClickException(
                "Specify --chat <name/id> or use --all to sync everything."
            )
    finally:
        await client.disconnect()
        conn.close()
