"""
WebSocket Manager with sequence numbers and multiplexing.

Implements:
- Single WebSocket connection per client
- Server-side channel subscriptions
- Monotonically increasing sequence numbers
- Automatic resync on sequence gaps
- Broadcast to subscribed clients only
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Set, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect
import structlog

from src.storage.redis_state import RedisStateStore
from src.storage.duckdb_store import DuckDBStore

logger = structlog.get_logger(__name__)


class WebSocketClient:
    """Represents a connected WebSocket client."""
    
    def __init__(self, client_id: str, websocket: WebSocket):
        self.client_id = client_id
        self.websocket = websocket
        self.subscriptions: Set[str] = set()
        self.last_seq_sent = 0
    
    async def send(self, message: dict):
        """Send message to client."""
        try:
            await self.websocket.send_json(message)
            if "seq" in message:
                self.last_seq_sent = message["seq"]
        except Exception as e:
            logger.error("websocket_send_error", client_id=self.client_id, error=str(e))
            raise


class WebSocketManager:
    """
    Manages WebSocket connections with sequence numbers.
    
    Design:
    - Single global sequence counter
    - Each message tagged with seq number
    - Clients can detect gaps and request resync
    - Broadcasts only to subscribed clients
    """
    
    def __init__(self, redis: Optional[RedisStateStore], duckdb: Optional[DuckDBStore]):
        self.redis = redis
        self.duckdb = duckdb
        self.clients: Dict[str, WebSocketClient] = {}
        self.sequence = 0
        self.last_broadcast_data: Dict[str, Any] = {}  # Channel -> last data
        logger.info("websocket_manager_initialized")
    
    async def connect(self, websocket: WebSocket):
        """Handle new WebSocket connection."""
        await websocket.accept()
        
        client_id = f"client_{len(self.clients)}_{datetime.utcnow().timestamp()}"
        client = WebSocketClient(client_id, websocket)
        self.clients[client_id] = client
        
        logger.info("websocket_client_connected", client_id=client_id)
        
        # Send initial handshake
        await client.send({
            "type": "HANDSHAKE",
            "session_id": client_id,
            "server_time": datetime.utcnow().isoformat() + "Z",
            "seq": self.sequence,
        })
        
        try:
            # Handle incoming messages
            while True:
                data = await websocket.receive_json()
                await self._handle_message(client, data)
        
        except WebSocketDisconnect:
            logger.info("websocket_client_disconnected", client_id=client_id)
            del self.clients[client_id]
        except Exception as e:
            logger.error("websocket_error", client_id=client_id, error=str(e))
            del self.clients[client_id]
    
    async def _handle_message(self, client: WebSocketClient, data: dict):
        """Handle incoming message from client."""
        msg_type = data.get("type")
        
        if msg_type == "SUBSCRIBE":
            channels = data.get("channels", [])
            client.subscriptions.update(channels)
            logger.debug("client_subscribed", client_id=client.client_id, channels=channels)
            
            # Send ACK with current subscription list
            await client.send({
                "type": "SUBSCRIBED",
                "channels": list(client.subscriptions),
                "seq": self.sequence,
            })
            
            # Send latest data for subscribed channels
            for channel in channels:
                if channel in self.last_broadcast_data:
                    await self._send_to_client(
                        client,
                        channel,
                        self.last_broadcast_data[channel]
                    )
        
        elif msg_type == "UNSUBSCRIBE":
            channels = data.get("channels", [])
            client.subscriptions.difference_update(channels)
            logger.debug("client_unsubscribed", client_id=client.client_id, channels=channels)
        
        elif msg_type == "RESYNC":
            # Client detected sequence gap, send full snapshot
            await self._send_snapshot(client)
        
        else:
            logger.warning("unknown_message_type", type=msg_type, client_id=client.client_id)
    
    async def _send_snapshot(self, client: WebSocketClient):
        """Send full state snapshot to client."""
        logger.info("sending_snapshot", client_id=client.client_id)
        
        snapshot = {}
        
        # Get all current state if redis available
        if self.redis:
            try:
                snapshot["positions"] = list(self.redis.get_all_positions().values())
                snapshot["equity"] = self.redis.get_equity_history()
                snapshot["regime"] = self.redis.get_state("current_regime")
            except Exception as e:
                logger.error("snapshot_build_error", error=str(e))
        
        self.sequence += 1
        await client.send({
            "type": "SNAPSHOT",
            "seq": self.sequence,
            "ts": datetime.utcnow().isoformat() + "Z",
            "payload": snapshot,
        })
    
    async def broadcast(self, channel: str, payload: Any):
        """
        Broadcast message to all clients subscribed to channel.
        
        Args:
            channel: Channel name (e.g., "positions", "equity", "market:AAPL")
            payload: Data to send
        """
        if not self.clients:
            return
        
        self.sequence += 1
        message = {
            "type": "DATA",
            "seq": self.sequence,
            "ts": datetime.utcnow().isoformat() + "Z",
            "channel": channel,
            "payload": payload,
        }
        
        # Cache for late subscribers
        self.last_broadcast_data[channel] = payload
        
        # Send to subscribed clients
        disconnected = []
        for client_id, client in self.clients.items():
            if channel in client.subscriptions:
                try:
                    await client.send(message)
                except Exception:
                    disconnected.append(client_id)
        
        # Clean up disconnected clients
        for client_id in disconnected:
            del self.clients[client_id]
            logger.warning("client_removed_due_to_send_error", client_id=client_id)
    
    async def _send_to_client(self, client: WebSocketClient, channel: str, payload: Any):
        """Send message to specific client."""
        self.sequence += 1
        message = {
            "type": "DATA",
            "seq": self.sequence,
            "ts": datetime.utcnow().isoformat() + "Z",
            "channel": channel,
            "payload": payload,
        }
        await client.send(message)
    
    async def broadcast_loop(self):
        """
        Background task to periodically broadcast updates.
        
        Polls Redis every 2 seconds and broadcasts changes.
        """
        logger.info("broadcast_loop_started")
        
        while True:
            try:
                await asyncio.sleep(2)  # 2-second update interval
                
                if not self.redis or not self.clients:
                    continue
                
                # Broadcast positions
                if any("positions" in c.subscriptions for c in self.clients.values()):
                    positions = self.redis.get_all_positions()
                    await self.broadcast("positions", list(positions.values()))
                
                # Broadcast equity
                if any("equity" in c.subscriptions for c in self.clients.values()):
                    equity_history = self.redis.get_equity_history()
                    if equity_history:
                        latest = equity_history[-1]
                        await self.broadcast("equity", latest)
                
                # Broadcast regime
                if any("regime" in c.subscriptions for c in self.clients.values()):
                    regime = self.redis.get_state("current_regime")
                    if regime:
                        regime_data = json.loads(regime) if isinstance(regime, str) else regime
                        await self.broadcast("regime", regime_data)
                
                # Broadcast system health
                if any("health" in c.subscriptions for c in self.clients.values()):
                    health = {
                        "main_bot_alive": self.redis.is_process_alive("main_bot"),
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    }
                    await self.broadcast("health", health)
            
            except asyncio.CancelledError:
                logger.info("broadcast_loop_cancelled")
                break
            except Exception as e:
                logger.error("broadcast_loop_error", error=str(e))
                await asyncio.sleep(5)  # Back off on error
        
        logger.info("broadcast_loop_stopped")
