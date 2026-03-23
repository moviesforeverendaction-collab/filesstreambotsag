import uuid
import config


def gen_token() -> str:
    return uuid.uuid4().hex  # 32-char hex, no dashes


def stream_url(token: str) -> str:
    """Link sent to user for streaming — renders stream.html page."""
    return f"{config.BASE_URL}/stream/{token}"


def download_url(token: str) -> str:
    """Link sent to user for downloading — renders dl.html page."""
    return f"{config.BASE_URL}/download/{token}"
