"""
FastAPI WebSocket server for Riichi Mahjong AI Trainer.

Serves the game via WebSocket and static frontend files.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.game_session import GameSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Riichi Mahjong AI Trainer")

# Resolve frontend dist path
_FRONTEND_DIST = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    logger.info("WebSocket connected")

    session: Optional[GameSession] = None
    send_task: Optional[asyncio.Task] = None

    async def send_loop(sess: GameSession):
        """Forward messages from engine thread to WebSocket client."""
        try:
            while True:
                msg = await asyncio.to_thread(sess.web_agent.ws_send_queue.get)
                if msg is None:  # sentinel — graceful exit
                    return
                await ws.send_json(msg)
        except asyncio.CancelledError:
            pass

    async def start_new_game():
        nonlocal session, send_task
        # Stop old session + send_loop
        if send_task and not send_task.done():
            send_task.cancel()
        if session is not None:
            session.stop()
        # Start new
        session = GameSession()
        session.start()
        send_task = asyncio.create_task(send_loop(session))
        logger.info(f"New game started (mortal={session.use_mortal})")

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "new_game":
                await start_new_game()

            elif msg_type == "action":
                if session and session.is_running:
                    session.web_agent.receive_player_action(data)

            elif msg_type == "continue_round":
                if session:
                    session.continue_round()

            elif msg_type == "chat_message":
                if session and session.is_running:
                    content = data.get("content", "")
                    if content.strip():
                        session.handle_chat_message(content)

            else:
                logger.warning(f"Unknown message type: {msg_type}")

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.exception(f"WebSocket error: {e}")
    finally:
        if send_task and not send_task.done():
            send_task.cancel()
        if session is not None:
            session.stop()
        logger.info("WebSocket session cleaned up")


# Serve frontend static files — MUST be after WebSocket route
if os.path.isdir(_FRONTEND_DIST):
    @app.get("/")
    async def index():
        return FileResponse(os.path.join(_FRONTEND_DIST, "index.html"))

    app.mount("/", StaticFiles(directory=_FRONTEND_DIST), name="static")
