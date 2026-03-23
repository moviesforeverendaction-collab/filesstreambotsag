import asyncio
import json
import redis.asyncio as aioredis
import config

_redis: aioredis.Redis | None = None
_redis_lock = asyncio.Lock()


async def get_redis() -> aioredis.Redis:
    """Return the shared Redis connection, creating it if needed (task-safe)."""
    global _redis
    # Fast path — already connected
    if _redis is not None:
        return _redis
    # Slow path — acquire lock to avoid duplicate connections under concurrent startup
    async with _redis_lock:
        if _redis is None:
            _redis = await aioredis.from_url(
                config.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
            await _redis.ping()
            print("✅ Redis connected")
    return _redis


async def close_redis():
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


# ── token store ───────────────────────────────────────────────────────────────

async def set_token(token: str, data: dict, ttl: int) -> None:
    r = await get_redis()
    # ttl=0 → never expire (10 years in seconds)
    effective_ttl = ttl if ttl > 0 else 315_360_000
    await r.setex(f"token:{token}", effective_ttl, json.dumps(data))


async def get_token(token: str) -> dict | None:
    r = await get_redis()
    raw = await r.get(f"token:{token}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


async def delete_token(token: str) -> None:
    r = await get_redis()
    await r.delete(f"token:{token}")


async def get_token_ttl(token: str) -> int:
    """Returns remaining TTL in seconds. -1 = no expiry, -2 = not found."""
    r = await get_redis()
    return await r.ttl(f"token:{token}")


# ── pending file (awaiting stream/download choice + expiry choice) ────────────

async def set_pending(user_id: int, data: dict, ttl: int = 600) -> None:
    r = await get_redis()
    await r.setex(f"pending:{user_id}", ttl, json.dumps(data))


async def get_pending(user_id: int) -> dict | None:
    r = await get_redis()
    raw = await r.get(f"pending:{user_id}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


async def del_pending(user_id: int) -> None:
    r = await get_redis()
    await r.delete(f"pending:{user_id}")


# ── per-user rate limiting ────────────────────────────────────────────────────

async def check_rate_limit(user_id: int) -> bool:
    """
    Atomically check and increment the rate-limit counter for a user.
    Returns True if the request is within limits, False if throttled.

    Uses a Lua script for true atomicity — the previous WATCH/MULTI/EXEC
    approach was broken because the pipeline context manager's __aexit__
    can call EXEC after an explicit reset(), causing unpredictable behaviour.
    """
    r = await get_redis()
    key = f"rl:{user_id}"

    # Lua script: returns 1 if allowed, 0 if throttled.
    # Atomically: get count, if under limit → incr (set with TTL if new key).
    lua_script = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local current = redis.call('GET', key)
if current == false then
    redis.call('SETEX', key, window, 1)
    return 1
end
current = tonumber(current)
if current >= limit then
    return 0
end
redis.call('INCR', key)
return 1
"""
    result = await r.eval(lua_script, 1, key, config.RATE_LIMIT_MAX, config.RATE_LIMIT_WINDOW)
    return result == 1


async def rate_limit_ttl(user_id: int) -> int:
    r = await get_redis()
    ttl = await r.ttl(f"rl:{user_id}")
    return max(0, ttl)


# ── IP-level rate limiting (for web endpoints, from CF headers) ───────────────

async def check_ip_rate_limit(ip: str, limit: int = 60, window: int = 10) -> bool:
    """
    Atomically check and increment the IP rate-limit counter.
    Uses a Lua script for atomicity (same reasoning as check_rate_limit).
    """
    r = await get_redis()
    key = f"rl:ip:{ip}"

    lua_script = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local current = redis.call('GET', key)
if current == false then
    redis.call('SETEX', key, window, 1)
    return 1
end
current = tonumber(current)
if current >= limit then
    return 0
end
redis.call('INCR', key)
return 1
"""
    result = await r.eval(lua_script, 1, key, limit, window)
    return result == 1
