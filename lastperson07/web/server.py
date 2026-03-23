import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from lastperson07.web.media import router as media_router
from database.redis import get_token, get_redis
from database.mongo import init_mongo
import uvicorn
import config

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

_SUPPORT_URL  = f"https://t.me/{config.FORCE_SUB_CHANNEL.lstrip('@')}" if config.FORCE_SUB_CHANNEL else "https://t.me/"
_BOT_NAME     = config.BOT_USERNAME
_BOT_USERNAME = config.BOT_USERNAME

# ── Background tasks storage ──────────────────────────────────────────────────
_bg_tasks: set = set()


def _spawn(coro):
    """Create a tracked background task that won't be silently GC'd."""
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task


# ── FastAPI lifespan (replaces deprecated on_event) ──────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    from lastperson07.clients import stream_client, download_client
    import lastperson07.handlers  # noqa — registers all @bot.on_* handlers

    # Connect Redis first (blocks until ready)
    await get_redis()
    # Init MongoDB (synchronous driver setup)
    init_mongo()

    # Start Telegram clients as a tracked background task
    _spawn(_start_clients(stream_client, download_client))
    _spawn(_cleanup_loop())

    yield  # ── Application runs here ─────────────────────────────────────────

    # ── Shutdown ──────────────────────────────────────────────────────────────
    tasks = list(_bg_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    from database.redis import close_redis
    from database.mongo import close_mongo
    try:
        await stream_client.stop()
    except Exception:
        pass
    try:
        await download_client.stop()
    except Exception:
        pass
    await close_redis()
    await close_mongo()


app = FastAPI(title="FileLink Bot", docs_url=None, redoc_url=None, lifespan=lifespan)
app.include_router(media_router)


async def _start_clients(stream_client, download_client):
    """Start both Pyrogram clients and keep them running."""
    try:
        await stream_client.start()
        await download_client.start()
        print("✅ Both Kurigram clients started")
        # Keep this coroutine alive until cancelled
        await asyncio.Future()  # runs forever; cancelled on shutdown
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"⚠️ Client start error: {e}")


async def _cleanup_loop():
    """Periodically log the count of active token keys."""
    try:
        while True:
            await asyncio.sleep(config.CLEANUP_INTERVAL)
            try:
                r = await get_redis()
                active = 0
                async for _ in r.scan_iter("token:*"):
                    active += 1
                print(f"🧹 Cleanup check: {active} active token keys in Redis")
            except Exception as e:
                print(f"⚠️ Cleanup error: {e}")
    except asyncio.CancelledError:
        pass


# ── Page routes ───────────────────────────────────────────────────────────────

@app.get("/stream/{token}", response_class=HTMLResponse)
async def stream_page(token: str, request: Request):
    data = await get_token(token)
    if not data:
        raise HTTPException(status_code=404, detail="Link expired or not found.")
    # Guard: file_size must be a positive integer
    file_size = int(data.get("file_size") or 0)
    return templates.TemplateResponse(
        request=request,
        name="stream.html",
        context={
            "file_url":     f"{config.BASE_URL}/media/{token}",
            "dl_url":       f"{config.BASE_URL}/dl/{token}",
            "file_name":    data.get("file_name", "Unknown"),
            "file_size":    file_size,
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
    file_size = int(data.get("file_size") or 0)
    mime_type = data.get("mime_type", "application/octet-stream")
    # Provide stream_url only for streamable content
    stream_url_val = (
        f"{config.BASE_URL}/stream/{token}"
        if mime_type.startswith(("video/", "audio/"))
        else ""
    )
    return templates.TemplateResponse(
        request=request,
        name="dl.html",
        context={
            "file_url":        f"{config.BASE_URL}/dl/{token}",
            "file_name":       data.get("file_name", "Unknown"),
            "file_size":       file_size,
            "file_size_human": human_size(file_size),
            "mime_type":       mime_type,
            "ttl_label":       data.get("ttl_label", ""),
            "stream_url":      stream_url_val,
            "bot_name":        _BOT_NAME,
            "bot_username":    _BOT_USERNAME,
            "support_url":     _SUPPORT_URL,
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Uvicorn runner ────────────────────────────────────────────────────────────

async def start_web():
    cfg = uvicorn.Config(
        app=app,
        host=config.HOST,
        port=config.PORT,
        loop="uvloop",
        http="httptools",
        log_level="info",
        timeout_keep_alive=75,
        limit_concurrency=config.UVICORN_LIMIT_CONCURRENCY,
        limit_max_requests=None,
        workers=1,
    )
    server = uvicorn.Server(cfg)
    await server.serve()
