"""
run.py — single entry point for Railway.

FastAPI's @app.on_event("startup") hook:
  1. Connects Redis + MongoDB
  2. Launches both Kurigram clients as asyncio background tasks
  3. Starts the cleanup loop

So run.py only needs to start uvicorn.
"""
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from lastperson07.web.server import start_web

if __name__ == "__main__":
    asyncio.run(start_web())
