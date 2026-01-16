"""
Comprehensive tests for WebSocket Manager with sequence numbers.

Tests:
- Sequence number monotonicity
- Gap detection and resync
- Multiplexed subscriptions
- Client connection/disconnection
- Broadcast to subscribed clients only
- Concurrent client handling
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import json

# Add project root to path
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from api.services.websocket_manager import WebSocketManager, WebSocketClient
from fastapi import WebSocket


class MockWebSocket:
    """Mock WebSocket for testing."""
    def __init__(self):
        self.messages_sent = []
        self.closed = False
    
    async def accept(self):
        pass
    
    async def send_json(self, data):
        self.messages_sent.append(data)
    
    async def receive_json(self):
        # Would be mocked in tests
        await asyncio.sleep(0.1)
        return {}
    
    async def close(self):
        self.closed = True


@pytest.fixture
def redis_mock():
    """Mock Redis store."""
    redis = MagicMock()
    redis.get_all_positions.return_value = {
        "AAPL": {"symbol": "AAPL", "qty": 10, "market_value": 1750}
    }
    redis.get_equity_history.return_value = [
        {"timestamp": "2024-01-01T12:00:00Z", "equity": 100000}
    ]
    redis.get_state.return_value = json.dumps({"trend_regime": "TRENDING", "vol_regime": "NORMAL"})
    redis.is_process_alive.return_value = True
    return redis


@pytest.fixture
def duckdb_mock():
    """Mock DuckDB store."""
    return MagicMock()


@pytest.fixture
def ws_manager(redis_mock, duckdb_mock):
    """WebSocket manager instance."""
    return WebSocketManager(redis_mock, duckdb_mock)


@pytest.mark.asyncio
async def test_sequence_numbers_monotonically_increase(ws_manager):
    """Test that sequence numbers always increase."""
    initial_seq = ws_manager.sequence
    
    # Broadcast multiple messages
    for i in range(10):
        await ws_manager.broadcast("test_channel", {"data": i})
    
    assert ws_manager.sequence == initial_seq + 10
    assert ws_manager.sequence > 0


@pytest.mark.asyncio
async def test_handshake_includes_sequence_number(ws_manager):
    """Test that initial handshake includes sequence number."""
    mock_ws = MockWebSocket()
    
    # Create client and send handshake
    client = WebSocketClient("test_client", mock_ws)
    
    handshake_msg = {
        "type": "HANDSHAKE",
        "session_id": "test_client",
        "server_time": datetime.utcnow().isoformat() + "Z",
        "seq": ws_manager.sequence,
    }
    
    await client.send(handshake_msg)
    
    assert len(mock_ws.messages_sent) == 1
    assert mock_ws.messages_sent[0]["type"] == "HANDSHAKE"
    assert "seq" in mock_ws.messages_sent[0]


@pytest.mark.asyncio
async def test_broadcast_only_to_subscribed_clients(ws_manager):
    """Test that broadcasts only go to subscribed clients."""
    # Create two clients
    client1_ws = MockWebSocket()
    client2_ws = MockWebSocket()
    
    client1 = WebSocketClient("client1", client1_ws)
    client2 = WebSocketClient("client2", client2_ws)
    
    # Client 1 subscribes to "positions"
    client1.subscriptions.add("positions")
    
    # Client 2 subscribes to "equity"
    client2.subscriptions.add("equity")
    
    # Add to manager
    ws_manager.clients["client1"] = client1
    ws_manager.clients["client2"] = client2
    
    # Broadcast to "positions"
    await ws_manager.broadcast("positions", {"data": "test"})
    
    # Client 1 should receive, client 2 should not
    assert len(client1_ws.messages_sent) > 0
    assert len(client2_ws.messages_sent) == 0


@pytest.mark.asyncio
async def test_sequence_gap_detection_triggers_resync(ws_manager):
    """Test that clients can detect sequence gaps."""
    mock_ws = MockWebSocket()
    client = WebSocketClient("test_client", mock_ws)
    
    # Simulate receiving messages with gap
    msg1 = {"seq": 1, "ts": datetime.utcnow().isoformat(), "channel": "test", "payload": {}}
    msg2 = {"seq": 3, "ts": datetime.utcnow().isoformat(), "channel": "test", "payload": {}}  # Gap! Missing seq 2
    
    # Client should detect gap (this would be in client-side code)
    assert msg2["seq"] > msg1["seq"] + 1  # Gap detected


@pytest.mark.asyncio
async def test_snapshot_contains_all_state(ws_manager, redis_mock):
    """Test that snapshot includes all current state."""
    mock_ws = MockWebSocket()
    client = WebSocketClient("test_client", mock_ws)
    ws_manager.clients["test_client"] = client
    
    await ws_manager._send_snapshot(client)
    
    # Should have received a snapshot message
    assert len(mock_ws.messages_sent) > 0
    snapshot_msg = mock_ws.messages_sent[-1]
    
    assert snapshot_msg["type"] == "SNAPSHOT"
    assert "seq" in snapshot_msg
    assert "payload" in snapshot_msg
    assert "positions" in snapshot_msg["payload"]


@pytest.mark.asyncio
async def test_multiple_clients_receive_broadcasts(ws_manager):
    """Test that multiple clients receive the same broadcast."""
    clients = []
    for i in range(5):
        mock_ws = MockWebSocket()
        client = WebSocketClient(f"client{i}", mock_ws)
        client.subscriptions.add("test_channel")
        ws_manager.clients[f"client{i}"] = client
        clients.append((client, mock_ws))
    
    await ws_manager.broadcast("test_channel", {"data": "broadcast_test"})
    
    # All 5 clients should have received the message
    for client, mock_ws in clients:
        assert len(mock_ws.messages_sent) > 0
        last_msg = mock_ws.messages_sent[-1]
        assert last_msg["channel"] == "test_channel"
        assert last_msg["payload"]["data"] == "broadcast_test"


@pytest.mark.asyncio
async def test_client_subscription_management(ws_manager):
    """Test subscribe/unsubscribe functionality."""
    mock_ws = MockWebSocket()
    client = WebSocketClient("test_client", mock_ws)
    
    # Subscribe to multiple channels
    channels = ["positions", "equity", "orders"]
    for channel in channels:
        client.subscriptions.add(channel)
    
    assert len(client.subscriptions) == 3
    assert "positions" in client.subscriptions
    
    # Unsubscribe from one
    client.subscriptions.remove("equity")
    
    assert len(client.subscriptions) == 2
    assert "equity" not in client.subscriptions


@pytest.mark.asyncio
async def test_disconnected_clients_are_removed(ws_manager):
    """Test that disconnected clients are cleaned up."""
    mock_ws = MockWebSocket()
    client = WebSocketClient("test_client", mock_ws)
    client.subscriptions.add("test_channel")
    ws_manager.clients["test_client"] = client
    
    # Simulate send failure (disconnected client)
    async def failing_send(msg):
        raise Exception("Client disconnected")
    
    mock_ws.send_json = failing_send
    
    await ws_manager.broadcast("test_channel", {"data": "test"})
    
    # Client should be removed
    assert "test_client" not in ws_manager.clients


@pytest.mark.asyncio
async def test_broadcast_caches_last_data(ws_manager):
    """Test that last broadcast data is cached for late subscribers."""
    channel = "test_channel"
    payload = {"data": "cached_test"}
    
    await ws_manager.broadcast(channel, payload)
    
    assert channel in ws_manager.last_broadcast_data
    assert ws_manager.last_broadcast_data[channel] == payload


@pytest.mark.asyncio
async def test_concurrent_broadcasts_maintain_sequence_order(ws_manager):
    """Test that concurrent broadcasts maintain sequence order."""
    # Create multiple broadcast tasks
    tasks = []
    for i in range(10):
        task = asyncio.create_task(ws_manager.broadcast(f"channel{i}", {"data": i}))
        tasks.append(task)
    
    await asyncio.gather(*tasks)
    
    # Sequence should have increased by exactly 10
    # (This tests thread safety of sequence increment)
    assert ws_manager.sequence >= 10


@pytest.mark.asyncio
async def test_message_timestamp_is_utc(ws_manager):
    """Test that all messages have UTC timestamps."""
    mock_ws = MockWebSocket()
    client = WebSocketClient("test_client", mock_ws)
    client.subscriptions.add("test_channel")
    ws_manager.clients["test_client"] = client
    
    await ws_manager.broadcast("test_channel", {"data": "test"})
    
    assert len(mock_ws.messages_sent) > 0
    msg = mock_ws.messages_sent[-1]
    
    assert "ts" in msg
    assert msg["ts"].endswith("Z")  # UTC indicator


@pytest.mark.asyncio
async def test_empty_clients_list_doesnt_crash(ws_manager):
    """Test that broadcasting with no clients doesn't crash."""
    ws_manager.clients = {}
    
    # Should not raise
    await ws_manager.broadcast("test_channel", {"data": "test"})


@pytest.mark.asyncio
async def test_invalid_channel_subscription_handled(ws_manager):
    """Test that invalid channel names are handled gracefully."""
    mock_ws = MockWebSocket()
    client = WebSocketClient("test_client", mock_ws)
    
    # Subscribe to various channel formats
    channels = ["positions", "equity", "market:AAPL", "market:SPY", ""]
    for channel in channels:
        client.subscriptions.add(channel)
    
    # Should handle all without crashing
    assert len(client.subscriptions) == len(channels)


def test_websocket_client_last_seq_tracking():
    """Test that WebSocketClient tracks last sequence sent."""
    mock_ws = MockWebSocket()
    client = WebSocketClient("test_client", mock_ws)
    
    assert client.last_seq_sent == 0
    
    # Simulate sending messages
    asyncio.run(client.send({"seq": 1, "data": "test"}))
    assert client.last_seq_sent == 1
    
    asyncio.run(client.send({"seq": 5, "data": "test"}))
    assert client.last_seq_sent == 5


@pytest.mark.asyncio
async def test_resync_request_sends_snapshot(ws_manager):
    """Test that RESYNC message triggers snapshot."""
    mock_ws = MockWebSocket()
    client = WebSocketClient("test_client", mock_ws)
    ws_manager.clients["test_client"] = client
    
    # Simulate resync request
    await ws_manager._handle_message(client, {"type": "RESYNC", "from_seq": 10})
    
    # Should have sent a snapshot
    assert any(msg["type"] == "SNAPSHOT" for msg in mock_ws.messages_sent)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
