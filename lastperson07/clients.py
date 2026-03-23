import os
from pyrogram import Client
import config

# ── Session directory ─────────────────────────────────────────────────────────
# Railway volume is mounted at /app/sessions — session files persist across
# redeployments so Pyrogram reuses DC auth keys without re-handshaking.
SESSION_DIR = "/app/sessions"
os.makedirs(SESSION_DIR, exist_ok=True)

_stream_path   = os.path.join(SESSION_DIR, "stream_session")
_download_path = os.path.join(SESSION_DIR, "download_session")

# Log where sessions are stored so you can confirm in Railway logs
print(f"📁 Session dir: {SESSION_DIR}")
print(f"   stream   → {_stream_path}.session  exists={os.path.exists(_stream_path + '.session')}")
print(f"   download → {_download_path}.session  exists={os.path.exists(_download_path + '.session')}")

# ── Client 1 : stream ─────────────────────────────────────────────────────────
stream_client = Client(
    name=_stream_path,
    api_id=config.API_ID_1,
    api_hash=config.API_HASH_1,
    bot_token=config.BOT_TOKEN,
    sleep_threshold=60,
    max_concurrent_transmissions=20,
    workers=16,
)

# ── Client 2 : download ───────────────────────────────────────────────────────
download_client = Client(
    name=_download_path,
    api_id=config.API_ID_2,
    api_hash=config.API_HASH_2,
    bot_token=config.BOT_TOKEN,
    sleep_threshold=60,
    max_concurrent_transmissions=20,
    workers=16,
)
