import asyncio
import logging
from typing import Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

ws_router = APIRouter()


class WebSocketManager:
    """Verwaltet aktive WebSocket-Verbindungen zum Frontend."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.debug(f"Neuer WebSocket-Client verbunden. Gesamt: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.debug(f"WebSocket-Client getrennt. Verbleibend: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Sendet ein JSON-Objekt asynchron an alle Clients."""
        async with self._lock:
            connections = list(self.active_connections)

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Fehler beim Senden an WebSocket: {e}")
                async with self._lock:
                    self.active_connections.discard(connection)


ws_manager = WebSocketManager()


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Lauscht auf Heartbeats oder Ping-Nachrichten des Clients
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"WebSocket Exception: {e}")
        await ws_manager.disconnect(websocket)
