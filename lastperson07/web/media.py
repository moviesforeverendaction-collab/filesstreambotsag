from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from database.redis import get_token, check_ip_rate_limit
import asyncio
import config

router = APIRouter()

# stream_media() yields exactly 1 MiB chunks — never change this constant
CHUNK_SIZE = 1024 * 1024  # 1 MiB

# ── Concurrency caps ──────────────────────────────────────────────────────────
# 32 vCPU / 32 GB: we can safely handle many parallel streams.
# Each stream consumes ~1-2 MB RAM for buffering + a Telegram DC connection.
# 200 concurrent streams × ~2 MB buffer = ~400 MB — well within 32 GB.
# The real bottleneck is Telegram's per-session DC connection limit (~20),
# which is already handled by max_concurrent_transmissions on the clients.
_STREAM_SEMAPHORE   = asyncio.Semaphore(config.MAX_STREAM_CONNECTIONS)
_DOWNLOAD_SEMAPHORE = asyncio.Semaphore(config.MAX_DOWNLOAD_CONNECTIONS)


def get_real_ip(request: Request) -> str:
    return (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )


def parse_range(header: str, file_size: int) -> tuple[int, int]:
    try:
        unit, _, rng = header.partition("=")
        if unit.strip() != "bytes":
            return 0, file_size - 1
        start_s, _, end_s = rng.partition("-")
        start = int(start_s.strip()) if start_s.strip() else 0
        end   = int(end_s.strip())   if end_s.strip()   else file_size - 1
        return max(0, start), min(end, file_size - 1)
    except Exception:
        return 0, file_size - 1


async def yield_bytes(client, file_id: str, byte_start: int, byte_end: int):
    """
    Yield exactly (byte_end - byte_start + 1) bytes from Telegram.

    stream_media(file_id, offset=N) — offset is in 1 MiB CHUNKS, not bytes.
    We calculate which chunk byte_start lives in, then trim leading and
    trailing bytes so the response is byte-exact.
    """
    first_chunk = byte_start // CHUNK_SIZE
    skip        = byte_start % CHUNK_SIZE
    remaining   = byte_end - byte_start + 1

    chunk_idx = 0
    async for chunk in client.stream_media(file_id, offset=first_chunk):
        if remaining <= 0:
            break
        if chunk_idx == 0 and skip:
            chunk = chunk[skip:]
        if len(chunk) > remaining:
            chunk = chunk[:remaining]
        yield chunk
        remaining -= len(chunk)
        chunk_idx += 1


async def _resolve_token(token: str) -> dict:
    data = await get_token(token)
    if not data:
        raise HTTPException(status_code=404, detail="Link expired or not found.")
    if not data.get("file_id"):
        raise HTTPException(status_code=404, detail="File reference missing.")
    return data


# ── /media/{token} — byte-range proxy for browser player (stream_client) ─────
@router.get("/media/{token}")
async def media_endpoint(token: str, request: Request):
    ip = get_real_ip(request)
    # 300 requests per 10s per IP — generous for video buffering
    if not await check_ip_rate_limit(ip, limit=300, window=10):
        raise HTTPException(status_code=429, detail="Too many requests.")

    data      = await _resolve_token(token)
    file_id   = data["file_id"]
    file_size = data.get("file_size", 0)
    mime_type = data.get("mime_type", "application/octet-stream")
    file_name = data.get("file_name", "file")

    from lastperson07.clients import stream_client

    range_hdr = request.headers.get("Range")
    if range_hdr:
        start, end = parse_range(range_hdr, file_size)
        length = end - start + 1

        async def _stream():
            async with _STREAM_SEMAPHORE:
                async for chunk in yield_bytes(stream_client, file_id, start, end):
                    yield chunk

        return StreamingResponse(
            _stream(),
            status_code=206,
            headers={
                "Content-Range":       f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges":       "bytes",
                "Content-Length":      str(length),
                "Content-Disposition": f'inline; filename="{file_name}"',
            },
            media_type=mime_type,
        )

    async def _stream_full():
        async with _STREAM_SEMAPHORE:
            async for chunk in yield_bytes(stream_client, file_id, 0, max(0, file_size - 1)):
                yield chunk

    return StreamingResponse(
        _stream_full(),
        status_code=200,
        headers={
            "Accept-Ranges":       "bytes",
            "Content-Length":      str(file_size),
            "Content-Disposition": f'inline; filename="{file_name}"',
        },
        media_type=mime_type,
    )


# ── /dl/{token} — full-file download (download_client) ───────────────────────
@router.get("/dl/{token}")
async def download_endpoint(token: str, request: Request):
    ip = get_real_ip(request)
    # 60 requests per 10s per IP for downloads
    if not await check_ip_rate_limit(ip, limit=60, window=10):
        raise HTTPException(status_code=429, detail="Too many requests.")

    data      = await _resolve_token(token)
    file_id   = data["file_id"]
    file_size = data.get("file_size", 0)
    mime_type = data.get("mime_type", "application/octet-stream")
    file_name = data.get("file_name", "file")

    from lastperson07.clients import download_client

    async def _download():
        async with _DOWNLOAD_SEMAPHORE:
            async for chunk in yield_bytes(download_client, file_id, 0, max(0, file_size - 1)):
                yield chunk

    return StreamingResponse(
        _download(),
        status_code=200,
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Content-Length":      str(file_size),
            "Accept-Ranges":       "none",
        },
        media_type=mime_type,
    )
