import os
from dotenv import load_dotenv

load_dotenv()


# ── helpers ──────────────────────────────────────────────────────────────────

def require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable '{name}' is required but not set.")
    return value

def env_int(name: str, default: int) -> int:
    try:
        v = os.getenv(name)
        return int(v) if v is not None else default
    except ValueError:
        return default

def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower().strip() in ("1", "true", "yes", "on")

def env_list_int(name: str) -> list[int]:
    raw = os.getenv(name, "")
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


# ── Bot ──────────────────────────────────────────────────────────────────────
BOT_TOKEN    = require("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBot")

# ── Telegram API 1 — stream client ───────────────────────────────────────────
API_ID_1   = env_int("API_ID_1", 0)
API_HASH_1 = require("API_HASH_1")

# ── Telegram API 2 — download client ─────────────────────────────────────────
API_ID_2   = env_int("API_ID_2", 0)
API_HASH_2 = require("API_HASH_2")

# ── Storage channel ───────────────────────────────────────────────────────────
STORAGE_CHANNEL = env_int("STORAGE_CHANNEL", 0)

# ── Admins ────────────────────────────────────────────────────────────────────
ADMIN_IDS = env_list_int("ADMIN_IDS")

# ── Force subscribe ───────────────────────────────────────────────────────────
FORCE_SUB_ENABLED = env_bool("FORCE_SUB_ENABLED", False)
FORCE_SUB_CHANNEL = os.getenv("FORCE_SUB_CHANNEL", "")

# ── Databases ─────────────────────────────────────────────────────────────────
MONGO_URI     = require("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "filebot")
REDIS_URL     = require("REDIS_URL")

# ── Web server ────────────────────────────────────────────────────────────────
# Auto-prepend https:// if BASE_URL is missing scheme
_base_url = os.getenv("BASE_URL", "http://localhost:8080").strip().rstrip("/")
if _base_url and not _base_url.startswith(("http://", "https://")):
    _base_url = "https://" + _base_url
BASE_URL = _base_url

PORT = env_int("PORT", 8080)
HOST = os.getenv("HOST", "0.0.0.0")

# ── Link behaviour ────────────────────────────────────────────────────────────
LINK_TTL          = env_int("LINK_TTL", 86400)
RATE_LIMIT_MAX    = env_int("RATE_LIMIT_MAX", 10)
RATE_LIMIT_WINDOW = env_int("RATE_LIMIT_WINDOW", 60)

# ── Streaming / Download ──────────────────────────────────────────────────────
# Telegram yields exactly 1 MiB per chunk from stream_media().
CHUNK_SIZE = 1024 * 1024  # 1 MiB — do NOT change

# How many 1-MiB chunks to fetch from Telegram IN PARALLEL per connection.
#
# Sequential (old):  fetch chunk 1 → wait → fetch chunk 2 → wait ...  SLOW
# Parallel   (new):  fetch chunks 1+2+3+4 simultaneously → yield in order FAST
#
# STREAM_PARALLEL_CHUNKS=4  → 4 MiB fetched at once per stream connection
# DOWNLOAD_PARALLEL_CHUNKS=8 → 8 MiB fetched at once per download connection
#
# Telegram allows up to max_concurrent_transmissions=20 per client.
# With parallel=8 and 10 simultaneous downloads → 80 concurrent DC requests
# which is within the safe 20-per-client limit per connection.
# Raise these numbers if Railway has fast uplink and you want more throughput.
STREAM_PARALLEL_CHUNKS   = env_int("STREAM_PARALLEL_CHUNKS", 4)
DOWNLOAD_PARALLEL_CHUNKS = env_int("DOWNLOAD_PARALLEL_CHUNKS", 8)

# ── Concurrency limits ────────────────────────────────────────────────────────
MAX_STREAM_CONNECTIONS    = env_int("MAX_STREAM_CONNECTIONS", 200)
MAX_DOWNLOAD_CONNECTIONS  = env_int("MAX_DOWNLOAD_CONNECTIONS", 100)
UVICORN_LIMIT_CONCURRENCY = env_int("UVICORN_LIMIT_CONCURRENCY", 500)

# ── Cleanup background task ───────────────────────────────────────────────────
CLEANUP_INTERVAL = env_int("CLEANUP_INTERVAL", 3600)
