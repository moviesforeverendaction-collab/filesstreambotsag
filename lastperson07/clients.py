import os
from pyrogram import Client
import config

# ── Session directory ─────────────────────────────────────────────────────────
# Store .session files on disk so Pyrogram reuses DC auth keys across restarts.
# This eliminates the ~2s re-auth delay when streaming/downloading files that
# live on a different Telegram DC (e.g. DC1 while bot is on DC2).
SESSION_DIR = os.getenv("SESSION_DIR", "/app/sessions")
os.makedirs(SESSION_DIR, exist_ok=True)

# ── Client 1 : stream ─────────────────────────────────────────────────────────
stream_client = Client(
    name=os.path.join(SESSION_DIR, "stream_session"),
    api_id=config.API_ID_1,
    api_hash=config.API_HASH_1,
    bot_token=config.BOT_TOKEN,
    sleep_threshold=60,
    max_concurrent_transmissions=20,
    workers=16,
)

# ── Client 2 : download ───────────────────────────────────────────────────────
download_client = Client(
    name=os.path.join(SESSION_DIR, "download_session"),
    api_id=config.API_ID_2,
    api_hash=config.API_HASH_2,
    bot_token=config.BOT_TOKEN,
    sleep_threshold=60,
    max_concurrent_transmissions=20,
    workers=16,
)
