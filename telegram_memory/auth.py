"""Authentication helpers — config persistence and Telethon client factory."""

import json
from pathlib import Path

import click
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError


CONFIG_DIR = Path.home() / ".telegram-memory"
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSION_FILE = CONFIG_DIR / "telegram-memory"  # Telethon appends .session


def load_config() -> dict | None:
    """Return the stored config dict, or None if it doesn't exist yet."""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return None


def save_config(api_id: int, api_hash: str, phone: str) -> None:
    """Persist API credentials to the config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps({"api_id": api_id, "api_hash": api_hash, "phone": phone}, indent=2)
    )
    # Restrict permissions so only the owner can read the credentials.
    CONFIG_FILE.chmod(0o600)


def get_client(config: dict | None = None) -> TelegramClient:
    """Create a TelegramClient from stored (or provided) config."""
    cfg = config or load_config()
    if not cfg:
        raise click.ClickException(
            "Not authenticated. Run `telegram-memory auth` first."
        )
    return TelegramClient(
        str(SESSION_FILE),
        int(cfg["api_id"]),
        cfg["api_hash"],
    )


async def interactive_auth() -> None:
    """Walk the user through first-time auth and store credentials."""
    click.echo("=== telegram-memory setup ===\n")
    click.echo(
        "You need a Telegram API key. Get one at https://my.telegram.org/apps\n"
    )

    api_id_str = click.prompt("API ID")
    try:
        api_id = int(api_id_str)
    except ValueError:
        raise click.ClickException("API ID must be an integer.")

    api_hash = click.prompt("API Hash")
    phone = click.prompt("Phone number (international format, e.g. +49123456789)")

    save_config(api_id, api_hash, phone)
    click.echo("\nCredentials saved. Connecting to Telegram…")

    client = get_client()
    await client.connect()

    if not await client.is_user_authorized():
        await client.send_code_request(phone)
        code = click.prompt("Enter the code Telegram sent you")
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            # 2FA is enabled on the account.
            password = click.prompt("Two-step verification password", hide_input=True)
            await client.sign_in(password=password)

    me = await client.get_me()
    await client.disconnect()

    click.echo(
        f"\nAuthenticated as {me.first_name} (@{me.username}). "
        "Session saved to ~/.telegram-memory/"
    )
