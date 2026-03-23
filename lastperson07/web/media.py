from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from database.redis import get_token, check_ip_rate_limit
from urllib.parse import quote
import asyncio
import config

router = APIRouter()

CHUNK_SIZE = config.CHUNK_SIZE  # 1 MiB

# ── Concurrency caps (lazy — must be inside running event loop) ───────────────
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


async def _fetch_single_chunk(
    client,
    file_id: str,
    chunk_index: int,
    skip: int,
    trim: int,
) -> tuple[int, bytes]:
    """
    Fetch one 1-MiB chunk from Telegram by offset index.
    Returns (chunk_index, data) so the caller can reorder out-of-order results.

    skip  = bytes to strip from the START of chunk 0 (byte-range alignment)
    trim  = bytes to keep from the END of the last chunk (byte-range alignment)
           -1 means keep the whole chunk
    """
    data = b""
    async for part in client.stream_media(file_id, offset=chunk_index, limit=1):
        data = part
    if skip:
        data = data[skip:]
    if trim != -1:
        data = data[:trim]
    return chunk_index, data


async def yield_bytes_parallel(
    client,
    file_id: str,
    byte_start: int,
    byte_end: int,
    parallel: int = 4,
):
    """
    Yield byte-exact content using parallel chunk fetching.

    Instead of fetching chunks one-by-one (sequential, slow), we fire off
    `parallel` Telegram requests simultaneously and yield chunks in order.

    parallel=4 → 4 MiB in-flight at once → 4× faster than sequential.
    Telegram allows max_concurrent_transmissions (set to 20) per client,
    so parallel=4 is well within safe limits.

    Order is preserved: chunk N is always yielded before chunk N+1.
    """
    if byte_end < byte_start:
        return

    first_chunk  = byte_start // CHUNK_SIZE
    last_chunk   = byte_end   // CHUNK_SIZE
    total_chunks = last_chunk - first_chunk + 1

    # For the very first chunk: skip leading bytes (byte-range alignment)
    # For the very last chunk: keep only bytes up to byte_end
    first_skip = byte_start % CHUNK_SIZE
    last_trim  = (byte_end % CHUNK_SIZE) + 1  # bytes to keep in last chunk

    chunk_indices = list(range(first_chunk, last_chunk + 1))
    next_to_yield = first_chunk
    buffer: dict[int, bytes] = {}

    try:
        for batch_start in range(0, total_chunks, parallel):
            batch = chunk_indices[batch_start : batch_start + parallel]

            # Fire all chunks in this batch simultaneously
            tasks = []
            for idx in batch:
                skip = first_skip if idx == first_chunk else 0
                trim = last_trim  if idx == last_chunk  else -1
                tasks.append(
                    asyncio.create_task(
                        _fetch_single_chunk(client, file_id, idx, skip, trim)
                    )
                )

            # Gather results (preserves order via return value)
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    print(f"⚠️ chunk fetch error (file_id={file_id}): {result}")
                    return
                idx, data = result
                buffer[idx] = data

            # Yield buffered chunks in strict order
            while next_to_yield in buffer:
                yield buffer.pop(next_to_yield)
                next_to_yield += 1

    except GeneratorExit:
        # Client disconnected — cancel any pending tasks
        for task in tasks if 'tasks' in dir() else []:
            task.cancel()
        return
    except Exception as e:
        print(f"⚠️ yield_bytes_parallel error (file_id={file_id}): {e}")
        return


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
                async for chunk in yield_bytes_parallel(
                    stream_client, file_id, start, end,
                    parallel=config.STREAM_PARALLEL_CHUNKS,
                ):
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

    async def _stream_full():
        async with _get_stream_semaphore():
            async for chunk in yield_bytes_parallel(
                stream_client, file_id, 0, file_size - 1,
                parallel=config.STREAM_PARALLEL_CHUNKS,
            ):
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
            # Use higher parallelism for downloads — browser isn't seeking,
            # so we can saturate all available Telegram DC connections.
            async for chunk in yield_bytes_parallel(
                download_client, file_id, 0, file_size - 1,
                parallel=config.DOWNLOAD_PARALLEL_CHUNKS,
            ):
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
