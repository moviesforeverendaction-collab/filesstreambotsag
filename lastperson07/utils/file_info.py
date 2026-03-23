from kurigram.types import Message


def extract_file_info(message: Message) -> dict | None:
    """
    Pull file_id, metadata from any supported media message.
    Returns None if no supported media found.
    """
    media = (
        message.video
        or message.document
        or message.audio
        or message.voice
        or message.video_note
        or message.animation
    )
    if not media:
        return None

    mime_type = getattr(media, "mime_type", None) or "application/octet-stream"
    file_name = getattr(media, "file_name", None)

    if not file_name:
        ext = mime_type.split("/")[-1] if "/" in mime_type else "bin"
        file_name = f"{media.file_unique_id}.{ext}"

    return {
        "file_id":        media.file_id,
        "file_unique_id": media.file_unique_id,
        "file_name":      file_name,
        "file_size":      getattr(media, "file_size", 0) or 0,
        "mime_type":      mime_type,
        "duration":       getattr(media, "duration", None),
        "width":          getattr(media, "width", None),
        "height":         getattr(media, "height", None),
    }


def is_streamable(mime_type: str) -> bool:
    if not mime_type:
        return False
    return mime_type.startswith("video/") or mime_type.startswith("audio/")
