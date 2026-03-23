import json
import redis.asyncio as aioredis
import config

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
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
    return json.loads(raw)


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
    return json.loads(raw)


async def del_pending(user_id: int) -> None:
    r = await get_redis()
    await r.delete(f"pending:{user_id}")


# ── per-user rate limiting ────────────────────────────────────────────────────

async def check_rate_limit(user_id: int) -> bool:
    """True = within limit.  False = throttled."""
    r = await get_redis()
    key = f"rl:{user_id}"
    count = await r.get(key)
    if count is None:
        await r.setex(key, config.RATE_LIMIT_WINDOW, 1)
        return True
    if int(count) >= config.RATE_LIMIT_MAX:
        return False
    await r.incr(key)
    return True


async def rate_limit_ttl(user_id: int) -> int:
    r = await get_redis()
    return await r.ttl(f"rl:{user_id}")


# ── IP-level rate limiting (for web endpoints, from CF headers) ───────────────

async def check_ip_rate_limit(ip: str, limit: int = 60, window: int = 10) -> bool:
    r = await get_redis()
    key = f"rl:ip:{ip}"
    count = await r.get(key)
    if count is None:
        await r.setex(key, window, 1)
        return True
    if int(count) >= limit:
        return False
    await r.incr(key)
    return True
