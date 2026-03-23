import asyncio
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from lastperson07.web.media import router as media_router
from database.redis import get_token
from database.mongo import init_mongo
import uvicorn
import config

app = FastAPI(title="FileLink Bot", docs_url=None, redoc_url=None)

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

app.include_router(media_router)

_SUPPORT_URL  = f"https://t.me/{config.FORCE_SUB_CHANNEL.lstrip('@')}" if config.FORCE_SUB_CHANNEL else "https://t.me/"
_BOT_NAME     = config.BOT_USERNAME
_BOT_USERNAME = config.BOT_USERNAME


# ── FastAPI lifecycle ─────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    from database.redis import get_redis
    from lastperson07.clients import stream_client, download_client
    import lastperson07.handlers  # noqa — triggers all @bot.on_* decorator registrations

    await get_redis()
    init_mongo()

    asyncio.create_task(_start_clients(stream_client, download_client))
    asyncio.create_task(_cleanup_loop())


@app.on_event("shutdown")
async def shutdown():
    from lastperson07.clients import stream_client, download_client
    from database.redis import close_redis
    from database.mongo import close_mongo
    try:
        await stream_client.stop()
        await download_client.stop()
    except Exception:
        pass
    await close_redis()
    await close_mongo()


async def _start_clients(stream_client, download_client):
    try:
        await stream_client.start()
        await download_client.start()
        print("✅ Both Kurigram clients started")
        await asyncio.Event().wait()
    except Exception as e:
        print(f"⚠️ Client start error: {e}")


async def _cleanup_loop():
    from database.redis import get_redis
    while True:
        await asyncio.sleep(config.CLEANUP_INTERVAL)
        try:
            r = await get_redis()
            expired = 0
            async for key in r.scan_iter("token:*"):
                if await r.ttl(key) == -2:
                    expired += 1
            if expired:
                print(f"🧹 Cleanup: {expired} stale token keys found")
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")


# ── Page routes ───────────────────────────────────────────────────────────────

@app.get("/stream/{token}", response_class=HTMLResponse)
async def stream_page(token: str, request: Request):
    data = await get_token(token)
    if not data:
        raise HTTPException(status_code=404, detail="Link expired or not found.")
    return templates.TemplateResponse(
        name="stream.html",
        context={
            "request":      request,
            "file_url":     f"{config.BASE_URL}/media/{token}",
            "dl_url":       f"{config.BASE_URL}/dl/{token}",
            "file_name":    data.get("file_name", "Unknown"),
            "file_size":    data.get("file_size", 0),
            "mime_type":    data.get("mime_type", "video/mp4"),
            "ttl_label":    data.get("ttl_label", ""),
            "bot_name":     _BOT_NAME,
            "bot_username": _BOT_USERNAME,
            "support_url":  _SUPPORT_URL,
        },
    )


@app.get("/download/{token}", response_class=HTMLResponse)
async def download_page(token: str, request: Request):
    data = await get_token(token)
    if not data:
        raise HTTPException(status_code=404, detail="Link expired or not found.")
    from lastperson07.utils.human_size import human_size
    return templates.TemplateResponse(
        name="dl.html",
        context={
            "request":         request,
            "file_url":        f"{config.BASE_URL}/dl/{token}",
            "file_name":       data.get("file_name", "Unknown"),
            "file_size":       data.get("file_size", 0),
            "file_size_human": human_size(data.get("file_size", 0)),
            "mime_type":       data.get("mime_type", "application/octet-stream"),
            "ttl_label":       data.get("ttl_label", ""),
            "stream_url":      "",
            "bot_name":        _BOT_NAME,
            "bot_username":    _BOT_USERNAME,
            "support_url":     _SUPPORT_URL,
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Uvicorn runner ────────────────────────────────────────────────────────────
# 32 vCPU available.
# uvicorn in single-process async mode already saturates I/O-bound workloads.
# We set loop="uvloop" for the fastest async event loop on Linux,
# and limit_concurrency to protect against traffic spikes.

async def start_web():
    cfg = uvicorn.Config(
        app=app,
        host=config.HOST,
        port=config.PORT,
        loop="uvloop",          # fastest async loop on Linux — big win for I/O
        http="httptools",       # fastest HTTP parser
        log_level="info",
        timeout_keep_alive=75,  # keep connections alive longer under load
        limit_concurrency=config.UVICORN_LIMIT_CONCURRENCY,
        limit_max_requests=None,
        workers=1,              # single process — asyncio handles concurrency
    )
    server = uvicorn.Server(cfg)
    await server.serve()
