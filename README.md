# telegram-memory

Sync your Telegram chat history to a local SQLite database and search it instantly — from the terminal or from an AI agent.

## Why this exists

Telegram's official clients don't expose a searchable, machine-readable local copy of your history. AI coding assistants and personal automation tools often need to query past conversations ("what did we decide about X last month?"). This tool bridges that gap: one sync command, then full-text search forever — no cloud service, no third-party storage.

## Requirements

- Python 3.10+
- A [Telegram API key](https://my.telegram.org/apps) (free, takes 30 seconds)

## Installation

```bash
pip install .
```

Or in editable mode for development:

```bash
pip install -e .
```

## Quick start

```bash
# 1. Authenticate (one-time)
telegram-memory auth

# 2. Sync a specific chat
telegram-memory sync --chat "My Team"

# 3. Or sync everything
telegram-memory sync --all

# 4. Search
telegram-memory search "project deadline"
```

## Commands

### `telegram-memory auth`

Interactive first-time setup. Asks for your API ID, API Hash, and phone number, then completes the Telegram login flow (including 2FA if enabled). Credentials are stored in `~/.telegram-memory/config.json` (mode 600).

### `telegram-memory sync`

Pull messages from Telegram into `~/.telegram-memory/messages.db`. Incremental by default — only fetches messages newer than the last sync.

| Flag | Description |
|------|-------------|
| `--chat "Name or ID"` | Sync a single chat (name substring or numeric ID) |
| `--all` | Sync every dialog |
| `--limit N` | Cap messages fetched per chat |

```bash
telegram-memory sync --chat "Family"
telegram-memory sync --chat -1001234567890
telegram-memory sync --all --limit 5000
```

### `telegram-memory search <query>`

Full-text search over all synced messages. Uses SQLite FTS5 so queries are fast even on millions of rows.

| Flag | Description |
|------|-------------|
| `--chat "name"` | Filter to chats matching this substring |
| `--from "name"` | Filter to messages from this sender |
| `--after YYYY-MM-DD` | Only messages on or after this date |
| `--before YYYY-MM-DD` | Only messages on or before this date |
| `--limit N` | Max results (default: 20) |
| `--json` | Machine-readable JSON output |

```bash
telegram-memory search "invoice"
telegram-memory search "meeting notes" --chat "Work" --after 2026-01-01
telegram-memory search "deploy" --from "Alice" --limit 5
telegram-memory search "budget" --json | jq '.[].message_text'
```

FTS5 query syntax is supported: `"exact phrase"`, `term1 OR term2`, `NOT term`, `prefix*`.

### `telegram-memory chats`

List all synced chats with their IDs, message counts, and last sync time.

```bash
telegram-memory chats
telegram-memory chats --json
```

## File layout

```
~/.telegram-memory/
├── config.json          # API credentials (chmod 600)
├── telegram-memory.session  # Telethon session (never share this)
└── messages.db          # SQLite database with your history
```

All files stay on your machine. Nothing is sent anywhere.

## Database schema

```sql
messages (message_pk, id, chat_id, chat_name, sender_id, sender_name,
          message_text, date, reply_to_id, media_type, raw_json)

messages_fts  -- FTS5 virtual table over message_text, sender_name, chat_name

sync_state (chat_id, last_message_id, last_sync)
```

`raw_json` stores the full Telethon message dict so you can extract any field not covered by the fixed columns.

## Using with AI agents (Claude, etc.)

The `--json` flag on `search` and `chats` produces clean, structured output that agents can parse directly:

```bash
# Give an agent recent context from a channel
telegram-memory search "sprint planning" --chat "Engineering" --limit 10 --json
```

You can also query the SQLite file directly with any tool that speaks SQL.

## Security notes

- Your session file (`*.session`) grants full access to your Telegram account. Keep it private and never commit it.
- `config.json` contains your API credentials. It is created with `chmod 600` but also excluded from git via `.gitignore`.
- This tool uses the official MTProto API via [Telethon](https://github.com/LonamiWebs/Telethon) — no unofficial scraping.

## License

MIT
