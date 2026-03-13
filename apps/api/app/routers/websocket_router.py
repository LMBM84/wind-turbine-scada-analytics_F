"""
WebSocket endpoint for real-time SCADA streaming.

WS  /ws/turbines/{turbine_id}/live   — streams latest 10-min readings as JSON
WS  /ws/fleet/anomalies              — streams anomaly events to all subscribers
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from shared.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


class ConnectionManager:
    """Track active WebSocket connections per channel."""

    def __init__(self) -> None:
        self._active: Dict[str, Set[WebSocket]] = {}

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._active.setdefault(channel, set()).add(websocket)
        logger.info("WebSocket connected", channel=channel, total=len(self._active[channel]))

    def disconnect(self, channel: str, websocket: WebSocket) -> None:
        if channel in self._active:
            self._active[channel].discard(websocket)
        logger.info("WebSocket disconnected", channel=channel)

    async def broadcast(self, channel: str, message: dict) -> None:
        if channel not in self._active:
            return
        dead: Set[WebSocket] = set()
        payload = json.dumps(message, default=str)
        for ws in self._active[channel]:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._active[channel].discard(ws)


manager = ConnectionManager()


@router.websocket("/turbines/{turbine_id}/live")
async def turbine_live_stream(websocket: WebSocket, turbine_id: str):
    """
    Stream real-time SCADA readings for a specific turbine.
    The client receives one JSON message per 10-minute interval (or simulated).
    """
    channel = f"turbine:{turbine_id.upper()}"
    await manager.connect(channel, websocket)

    try:
        # Send initial handshake
        await websocket.send_json({
            "type": "connected",
            "turbine_id": turbine_id.upper(),
            "channel": channel,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        })

        # Keep connection alive — real data pushed via manager.broadcast()
        while True:
            try:
                # Heartbeat every 30s
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat", "ts": datetime.now(tz=timezone.utc).isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(channel, websocket)


@router.websocket("/fleet/anomalies")
async def fleet_anomaly_stream(websocket: WebSocket):
    """
    Broadcast real-time anomaly events across the entire fleet.
    All subscribers receive every new AnomalyEvent the moment it's detected.
    """
    channel = "fleet:anomalies"
    await manager.connect(channel, websocket)

    try:
        await websocket.send_json({
            "type": "connected",
            "channel": channel,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        })
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        manager.disconnect(channel, websocket)
