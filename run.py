"""
run.py — single entry point for Railway / Docker.

Order matters:
  1. Configure logging FIRST (before any imports that log)
  2. Import and start uvicorn

FastAPI's lifespan context manager (in server.py) handles:
  1. Connecting Redis + MongoDB
  2. Launching both Pyrogram clients as asyncio background tasks
  3. Starting the cleanup loop
  4. Graceful shutdown of all the above
"""
import asyncio
import logging

# Configure logging BEFORE any other imports so all early log messages
# use the correct format (including pyrogram, uvicorn, etc.)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from lastperson07.web.server import start_web  # noqa — import after logging setup

if __name__ == "__main__":
    asyncio.run(start_web())
