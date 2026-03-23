from pyrogram import Client
import config

# ── Resource profile: 32 vCPU, 32 GB RAM ─────────────────────────────────────
# max_concurrent_transmissions: how many parallel Telegram chunk fetches per client
# Telegram allows up to ~20 parallel DC connections per session safely.
# With 32 vCPU we can saturate both clients simultaneously.
# workers: number of asyncio update-handler workers per client.

# ── Client 1 : stream ─────────────────────────────────────────────────────────
# Handles HTTP byte-range requests — browser seeking + buffering
stream_client = Client(
    name="stream_session",
    api_id=config.API_ID_1,
    api_hash=config.API_HASH_1,
    bot_token=config.BOT_TOKEN,
    in_memory=True,              # no .session files — required for Railway
    sleep_threshold=60,
    max_concurrent_transmissions=20,  # 20 parallel chunk fetches
    workers=16,                       # 16 async handler workers
)

# ── Client 2 : download ───────────────────────────────────────────────────────
# Handles full-file delivery — separate session keeps rate limits independent
download_client = Client(
    name="download_session",
    api_id=config.API_ID_2,
    api_hash=config.API_HASH_2,
    bot_token=config.BOT_TOKEN,
    in_memory=True,
    sleep_threshold=60,
    max_concurrent_transmissions=20,
    workers=16,
)
