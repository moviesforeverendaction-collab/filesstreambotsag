from pyrogram.types import Message

# ── MIME → proper file extension map ─────────────────────────────────────────
# Python's mimetypes module returns wrong/missing extensions for many common
# media types (e.g. video/x-matroska → None, video/mp4 → .mp4 OK).
# This table covers every type Telegram commonly sends.
_MIME_TO_EXT: dict[str, str] = {
    # Video
    "video/x-matroska":          "mkv",
    "video/mp4":                 "mp4",
    "video/x-msvideo":           "avi",
    "video/quicktime":           "mov",
    "video/x-ms-wmv":            "wmv",
    "video/webm":                "webm",
    "video/mpeg":                "mpeg",
    "video/3gpp":                "3gp",
    "video/x-flv":               "flv",
    "video/x-m4v":               "m4v",
    "video/ogg":                 "ogv",
    # Audio
    "audio/mpeg":                "mp3",
    "audio/mp4":                 "m4a",
    "audio/x-m4a":               "m4a",
    "audio/ogg":                 "ogg",
    "audio/opus":                "opus",
    "audio/flac":                "flac",
    "audio/x-flac":              "flac",
    "audio/wav":                 "wav",
    "audio/x-wav":               "wav",
    "audio/aac":                 "aac",
    "audio/webm":                "weba",
    "audio/x-ms-wma":            "wma",
    # Documents
    "application/pdf":           "pdf",
    "application/zip":           "zip",
    "application/x-zip-compressed": "zip",
    "application/x-rar-compressed": "rar",
    "application/vnd.rar":       "rar",
    "application/x-7z-compressed": "7z",
    "application/x-tar":         "tar",
    "application/gzip":          "gz",
    "application/x-bzip2":       "bz2",
    "application/x-xz":         "xz",
    "application/msword":        "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel":  "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/x-iso9660-image": "iso",
    "application/x-apple-diskimage": "dmg",
    "application/java-archive":  "jar",
    "application/x-debian-package": "deb",
    "application/x-rpm":         "rpm",
    "application/vnd.android.package-archive": "apk",
    "application/x-executable": "exe",
    "application/octet-stream":  "bin",
    # Images
    "image/jpeg":                "jpg",
    "image/png":                 "png",
    "image/gif":                 "gif",
    "image/webp":                "webp",
    "image/svg+xml":             "svg",
    "image/bmp":                 "bmp",
    "image/tiff":                "tiff",
    # Text
    "text/plain":                "txt",
    "text/html":                 "html",
    "text/csv":                  "csv",
    "application/json":          "json",
    "application/xml":           "xml",
    "text/xml":                  "xml",
}


def _ext_from_mime(mime_type: str) -> str:
    """Return a clean file extension for a given MIME type."""
    if not mime_type:
        return "bin"
    # Check our table first
    ext = _MIME_TO_EXT.get(mime_type.lower())
    if ext:
        return ext
    # Fallback: take the subtype part and strip vendor prefixes
    subtype = mime_type.split("/")[-1]          # e.g. "x-matroska"
    subtype = subtype.split(";")[0].strip()     # drop params
    subtype = subtype.lstrip("x-").lstrip("vnd.").split(".")[-1]
    return subtype or "bin"


def extract_file_info(message: Message) -> dict | None:
    """
    Pull file_id and metadata from any supported media message.
    Returns None if no supported media found.

    Ensures file_name always has a proper extension — fixes the bug where
    files like .mkv (MIME: video/x-matroska) were downloaded without an
    extension because the raw MIME subtype was used as the extension.
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

    mime_type = (getattr(media, "mime_type", None) or "application/octet-stream").strip()
    file_name = (getattr(media, "file_name", None) or "").strip()

    if not file_name:
        # No filename from Telegram — build one from unique ID + proper extension
        ext = _ext_from_mime(mime_type)
        file_name = f"{media.file_unique_id}.{ext}"
    else:
        # Telegram gave us a filename — make sure it has an extension.
        # Sometimes Telegram strips the extension (e.g. sends "Shinchan" not "Shinchan.mkv").
        if "." not in file_name.rsplit("/", 1)[-1]:
            ext = _ext_from_mime(mime_type)
            file_name = f"{file_name}.{ext}"

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
