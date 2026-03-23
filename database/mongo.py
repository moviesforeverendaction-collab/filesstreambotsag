from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
import config

_client: AsyncIOMotorClient | None = None
_db = None


def init_mongo():
    global _client, _db
    _client = AsyncIOMotorClient(config.MONGO_URI)
    _db = _client[config.MONGO_DB_NAME]
    print("✅ MongoDB initialised")


def get_db():
    if _db is None:
        init_mongo()
    return _db


async def close_mongo():
    global _client
    if _client:
        _client.close()
        _client = None


def _now():
    return datetime.now(timezone.utc)


# ── users ─────────────────────────────────────────────────────────────────────

async def upsert_user(user_id: int, username: str = None, full_name: str = None):
    db = get_db()
    await db.users.update_one(
        {"user_id": user_id},
        {
            "$set":         {"username": username, "full_name": full_name, "last_seen": _now()},
            "$setOnInsert": {"user_id": user_id, "joined_at": _now(), "is_banned": False, "total_links": 0},
        },
        upsert=True,
    )


async def is_banned(user_id: int) -> bool:
    db = get_db()
    doc = await db.users.find_one({"user_id": user_id}, {"is_banned": 1})
    return bool(doc and doc.get("is_banned"))


async def ban_user(user_id: int):
    db = get_db()
    await db.users.update_one({"user_id": user_id}, {"$set": {"is_banned": True}}, upsert=True)


async def unban_user(user_id: int):
    db = get_db()
    await db.users.update_one({"user_id": user_id}, {"$set": {"is_banned": False}})


async def get_all_user_ids() -> list[int]:
    db = get_db()
    return [d["user_id"] async for d in db.users.find({"is_banned": False}, {"user_id": 1})]


async def count_users() -> int:
    return await get_db().users.count_documents({})


# ── file log ──────────────────────────────────────────────────────────────────

async def log_file(user_id: int, token: str, link_type: str, file_data: dict):
    db = get_db()
    await db.files.insert_one({
        "token":      token,
        "user_id":    user_id,
        "link_type":  link_type,          # "stream" | "download"
        "file_name":  file_data.get("file_name"),
        "file_size":  file_data.get("file_size"),
        "mime_type":  file_data.get("mime_type"),
        "file_id":    file_data.get("file_id"),
        "created_at": _now(),
    })
    await db.users.update_one({"user_id": user_id}, {"$inc": {"total_links": 1}})


async def count_files() -> int:
    return await get_db().files.count_documents({})


async def count_by_type(link_type: str) -> int:
    return await get_db().files.count_documents({"link_type": link_type})
