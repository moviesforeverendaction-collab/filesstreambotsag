from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from database.redis import get_token, check_ip_rate_limit
from urllib.parse import quote
import asyncio
import config

router = APIRouter()

CHUNK_SIZE = config.CHUNK_SIZE  # 1 MiB

# ── Concurrency caps (lazy init — must be inside running event loop) ──────────
_stream_semaphore: asyncio.Semaphore | None = None
_download_semaphore: asyncio.Semaphore | None = None

def _get_stream_semaphore() -> asyncio.Semaphore:
    global _stream_semaphore
    if _stream_semaphore is None:
        _stream_semaphore = asyncio.Semaphore(config.MAX_STREAM_CONNECTIONS)
    return _stream_semaphore

def _get_download_semaphore() -> asyncio.Semaphore:
    global _download_semaphore
    if _download_semaphore is None:
        _download_semaphore = asyncio.Semaphore(config.MAX_DOWNLOAD_CONNECTIONS)
    return _download_semaphore


def _content_disposition(disposition: str, filename: str) -> str:
    """RFC 5987 Content-Disposition with full Unicode filename support."""
    ascii_name   = filename.encode("ascii", errors="replace").decode("ascii")
    encoded_name = quote(filename, safe=" !#$&'()*+,-./:;<=>?@[]^_`{|}~")
    return f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'


def get_real_ip(request: Request) -> str:
    return (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )


def parse_range(header: str, file_size: int) -> tuple[int, int]:
    """Parse Range header → (start, end) inclusive byte positions."""
    try:
        unit, _, rng = header.partition("=")
        if unit.strip() != "bytes":
            return 0, file_size - 1
        start_s, _, end_s = rng.partition("-")
        start = int(start_s.strip()) if start_s.strip() else 0
        end   = int(end_s.strip())   if end_s.strip()   else file_size - 1
        start = max(0, min(start, file_size - 1))
        end   = max(start, min(end, file_size - 1))
        return start, end
    except Exception:
        return 0, file_size - 1


async def _fetch_to_queue(
    client,
    file_id: str,
    byte_start: int,
    byte_end: int,
    queue: asyncio.Queue,
) -> None:
    """
    Background task: pull chunks from Telegram and push into queue.
    Sends None sentinel when finished or on error.

    By decoupling Telegram fetch latency from HTTP write latency, the browser
    always has data ready to consume — no buffering pauses caused by Telegram
    DC round-trip jitter.
    """
    if byte_end < byte_start:
        await queue.put(None)
        return

    first_chunk = byte_start // CHUNK_SIZE
    skip        = byte_start % CHUNK_SIZE
    remaining   = byte_end - byte_start + 1
    chunk_idx   = 0

    try:
        async for chunk in client.stream_media(file_id, offset=first_chunk):
            if remaining <= 0:
                break
            if chunk_idx == 0 and skip:
                chunk = chunk[skip:]
            if len(chunk) > remaining:
                chunk = chunk[:remaining]
            remaining -= len(chunk)
            chunk_idx += 1
            await queue.put(chunk)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"⚠️ _fetch_to_queue error (file_id={file_id}): {e}")
    finally:
        await queue.put(None)  # always signal completion


async def yield_bytes(client, file_id: str, byte_start: int, byte_end: int):
    """
    Yield byte-exact content from Telegram via a prefetch queue.

    STREAM_PREFETCH_CHUNKS (default 4) × 1 MiB chunks are fetched ahead of
    what the HTTP layer has consumed, keeping the pipe full even when individual
    Telegram round-trips are slow.  Client disconnects cancel the fetcher task
    immediately so we don't waste bandwidth fetching data nobody will receive.
    """
    if byte_end < byte_start:
        return

    # Queue depth = how many 1 MiB chunks are buffered ahead
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(
        maxsize=config.STREAM_PREFETCH_CHUNKS
    )
    fetcher = asyncio.create_task(
        _fetch_to_queue(client, file_id, byte_start, byte_end, queue)
    )

    try:
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk
    except GeneratorExit:
        # Client disconnected — stop fetching immediately
        fetcher.cancel()
        try:
            await fetcher
        except (asyncio.CancelledError, Exception):
            pass
        return
    except Exception as e:
        print(f"⚠️ yield_bytes error (file_id={file_id}): {e}")
    finally:
        if not fetcher.done():
            fetcher.cancel()


async def _resolve_token(token: str) -> dict:
    data = await get_token(token)
    if not data:
        raise HTTPException(status_code=404, detail="Link expired or not found.")
    if not data.get("file_id"):
        raise HTTPException(status_code=404, detail="File reference missing.")
    data["file_size"] = int(data.get("file_size") or 0)
    return data


# ── /media/{token} — byte-range streaming for browser player ─────────────────
@router.get("/media/{token}")
async def media_endpoint(token: str, request: Request):
    ip = get_real_ip(request)
    if not await check_ip_rate_limit(ip, limit=300, window=10):
        raise HTTPException(status_code=429, detail="Too many requests.")

    data      = await _resolve_token(token)
    file_id   = data["file_id"]
    file_size = data["file_size"]
    mime_type = data.get("mime_type", "application/octet-stream")
    file_name = data.get("file_name", "file")

    from lastperson07.clients import stream_client

    if file_size <= 0:
        raise HTTPException(status_code=422, detail="File size unknown; cannot stream.")

    range_hdr = request.headers.get("Range")

    if range_hdr:
        start, end = parse_range(range_hdr, file_size)
        length = end - start + 1

        async def _stream_range():
            async with _get_stream_semaphore():
                async for chunk in yield_bytes(stream_client, file_id, start, end):
                    yield chunk

        return StreamingResponse(
            _stream_range(),
            status_code=206,
            headers={
                "Content-Range":       f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges":       "bytes",
                "Content-Length":      str(length),
                "Content-Disposition": _content_disposition("inline", file_name),
                "Cache-Control":       "no-cache",
            },
            media_type=mime_type,
        )

    # No Range header — stream the whole file
    async def _stream_full():
        async with _get_stream_semaphore():
            async for chunk in yield_bytes(stream_client, file_id, 0, file_size - 1):
                yield chunk

    return StreamingResponse(
        _stream_full(),
        status_code=200,
        headers={
            "Accept-Ranges":       "bytes",
            "Content-Length":      str(file_size),
            "Content-Disposition": _content_disposition("inline", file_name),
            "Cache-Control":       "no-cache",
        },
        media_type=mime_type,
    )


# ── /dl/{token} — full-file download ─────────────────────────────────────────
@router.get("/dl/{token}")
async def download_endpoint(token: str, request: Request):
    ip = get_real_ip(request)
    if not await check_ip_rate_limit(ip, limit=60, window=10):
        raise HTTPException(status_code=429, detail="Too many requests.")

    data      = await _resolve_token(token)
    file_id   = data["file_id"]
    file_size = data["file_size"]
    mime_type = data.get("mime_type", "application/octet-stream")
    file_name = data.get("file_name", "file")

    from lastperson07.clients import download_client

    if file_size <= 0:
        raise HTTPException(status_code=422, detail="File size unknown; cannot download.")

    async def _download():
        async with _get_download_semaphore():
            async for chunk in yield_bytes(download_client, file_id, 0, file_size - 1):
                yield chunk

    return StreamingResponse(
        _download(),
        status_code=200,
        headers={
            "Content-Disposition": _content_disposition("attachment", file_name),
            "Content-Length":      str(file_size),
            "Accept-Ranges":       "none",
            "Cache-Control":       "no-cache",
        },
        media_type=mime_type,
    )
