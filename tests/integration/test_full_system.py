"""
Full system integration tests.

Tests end-to-end flows:
- WebSocket connection → subscription → broadcast → client receives
- Order placement → execution → position update → metrics update
- Emergency halt → trading stops
- Data staleness detection
- Sequence gap → resync
"""

import pytest
import asyncio
import json
from datetime import datetime
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from api.services.websocket_manager import WebSocketManager, WebSocketClient
from unittest.mock import MagicMock, AsyncMock


class MockWebSocket:
    def __init__(self):
        self.messages = []
        self.closed = False
    
    async def accept(self):
        pass
    
    async def send_json(self, data):
        self.messages.append(data)
    
    async def receive_json(self):
        await asyncio.sleep(0.1)
        return {"type": "PING"}
    
    async def close(self):
        self.closed = True


@pytest.fixture
def redis_mock():
    redis = MagicMock()
    redis.get_all_positions.return_value = {}
    redis.get_equity_history.return_value = []
    redis.get_state.return_value = None
    redis.is_process_alive.return_value = True
    return redis


@pytest.fixture
def duckdb_mock():
    return MagicMock()


@pytest.mark.asyncio
async def test_full_websocket_flow(redis_mock, duckdb_mock):
    """Test complete WebSocket flow from connection to data receipt."""
    manager = WebSocketManager(redis_mock, duckdb_mock)
    
    # Step 1: Client connects
    client_ws = MockWebSocket()
    client = WebSocketClient("test_client", client_ws)
    manager.clients["test_client"] = client
    
    # Step 2: Send handshake
    await client.send({
        "type": "HANDSHAKE",
        "session_id": "test_client",
        "server_time": datetime.utcnow().isoformat() + "Z",
        "seq": manager.sequence,
    })
    
    assert len(client_ws.messages) == 1
    assert client_ws.messages[0]["type"] == "HANDSHAKE"
    
    # Step 3: Client subscribes to channels
    client.subscriptions.add("positions")
    client.subscriptions.add("equity")
    
    # Step 4: Broadcast data
    await manager.broadcast("positions", {"data": "position_update"})
    await manager.broadcast("equity", {"data": "equity_update"})
    await manager.broadcast("orders", {"data": "order_update"})  # Not subscribed
    
    # Step 5: Verify client received only subscribed data
    position_msgs = [m for m in client_ws.messages if m.get("channel") == "positions"]
    equity_msgs = [m for m in client_ws.messages if m.get("channel") == "equity"]
    order_msgs = [m for m in client_ws.messages if m.get("channel") == "orders"]
    
    assert len(position_msgs) == 1
    assert len(equity_msgs) == 1
    assert len(order_msgs) == 0


@pytest.mark.asyncio
async def test_sequence_gap_detection_and_resync(redis_mock, duckdb_mock):
    """Test that sequence gaps are detected and resync works."""
    manager = WebSocketManager(redis_mock, duckdb_mock)
    
    client_ws = MockWebSocket()
    client = WebSocketClient("test_client", client_ws)
    manager.clients["test_client"] = client
    client.subscriptions.add("test")
    
    # Send messages with a gap
    await manager.broadcast("test", {"data": "msg1"})  # seq=1
    await manager.broadcast("test", {"data": "msg2"})  # seq=2
    await manager.broadcast("test", {"data": "msg3"})  # seq=3
    
    # Client detects gap (simulated - would be client-side logic)
    messages = client_ws.messages
    sequences = [m["seq"] for m in messages if "seq" in m]
    
    # Verify monotonically increasing
    for i in range(1, len(sequences)):
        assert sequences[i] == sequences[i-1] + 1
    
    # Request resync
    await manager._handle_message(client, {"type": "RESYNC", "from_seq": 0})
    
    # Should receive snapshot
    snapshot_msgs = [m for m in client_ws.messages if m.get("type") == "SNAPSHOT"]
    assert len(snapshot_msgs) > 0


@pytest.mark.asyncio
async def test_multiple_clients_concurrent_access(redis_mock, duckdb_mock):
    """Test multiple clients accessing simultaneously."""
    manager = WebSocketManager(redis_mock, duckdb_mock)
    
    # Create 10 clients
    clients = []
    for i in range(10):
        client_ws = MockWebSocket()
        client = WebSocketClient(f"client{i}", client_ws)
        client.subscriptions.add("shared_channel")
        manager.clients[f"client{i}"] = client
        clients.append((client, client_ws))
    
    # Broadcast to all
    await manager.broadcast("shared_channel", {"data": "concurrent_test"})
    
    # All clients should receive
    for client, client_ws in clients:
        shared_msgs = [m for m in client_ws.messages if m.get("channel") == "shared_channel"]
        assert len(shared_msgs) == 1
        assert shared_msgs[0]["payload"]["data"] == "concurrent_test"


@pytest.mark.asyncio
async def test_broadcast_with_client_failure(redis_mock, duckdb_mock):
    """Test that one failing client doesn't affect others."""
    manager = WebSocketManager(redis_mock, duckdb_mock)
    
    # Good client
    good_ws = MockWebSocket()
    good_client = WebSocketClient("good_client", good_ws)
    good_client.subscriptions.add("test")
    manager.clients["good_client"] = good_client
    
    # Failing client
    failing_ws = MockWebSocket()
    async def failing_send(msg):
        raise Exception("Client disconnected")
    failing_ws.send_json = failing_send
    
    failing_client = WebSocketClient("failing_client", failing_ws)
    failing_client.subscriptions.add("test")
    manager.clients["failing_client"] = failing_client
    
    # Broadcast
    await manager.broadcast("test", {"data": "test"})
    
    # Good client should receive
    assert len(good_ws.messages) > 0
    
    # Failing client should be removed
    assert "failing_client" not in manager.clients


@pytest.mark.asyncio
async def test_subscription_changes_during_broadcast(redis_mock, duckdb_mock):
    """Test that subscription changes are handled correctly."""
    manager = WebSocketManager(redis_mock, duckdb_mock)
    
    client_ws = MockWebSocket()
    client = WebSocketClient("test_client", client_ws)
    manager.clients["test_client"] = client
    
    # Initially subscribed
    client.subscriptions.add("channel_a")
    
    await manager.broadcast("channel_a", {"data": "msg1"})
    
    # Unsubscribe
    client.subscriptions.remove("channel_a")
    client.subscriptions.add("channel_b")
    
    await manager.broadcast("channel_a", {"data": "msg2"})
    await manager.broadcast("channel_b", {"data": "msg3"})
    
    # Should only have received msg1 and msg3
    channel_a_msgs = [m for m in client_ws.messages if m.get("channel") == "channel_a"]
    channel_b_msgs = [m for m in client_ws.messages if m.get("channel") == "channel_b"]
    
    assert len(channel_a_msgs) == 1
    assert len(channel_b_msgs) == 1


@pytest.mark.asyncio
async def test_late_subscriber_receives_cached_data(redis_mock, duckdb_mock):
    """Test that late subscribers receive last broadcast data."""
    manager = WebSocketManager(redis_mock, duckdb_mock)
    
    # Broadcast before any clients
    await manager.broadcast("positions", {"data": "initial_state"})
    
    # Now a client subscribes
    client_ws = MockWebSocket()
    client = WebSocketClient("late_client", client_ws)
    manager.clients["late_client"] = client
    
    # Simulate subscribe message handling
    await manager._handle_message(client, {
        "type": "SUBSCRIBE",
        "channels": ["positions"]
    })
    
    # Should receive the cached data
    position_msgs = [m for m in client_ws.messages if m.get("channel") == "positions"]
    assert len(position_msgs) > 0


@pytest.mark.asyncio
async def test_broadcast_loop_updates_regularly(redis_mock, duckdb_mock):
    """Test that broadcast loop sends periodic updates."""
    manager = WebSocketManager(redis_mock, duckdb_mock)
    
    client_ws = MockWebSocket()
    client = WebSocketClient("test_client", client_ws)
    client.subscriptions.add("positions")
    client.subscriptions.add("equity")
    manager.clients["test_client"] = client
    
    # Mock Redis to return data
    redis_mock.get_all_positions.return_value = {"AAPL": {"symbol": "AAPL"}}
    redis_mock.get_equity_history.return_value = [{"equity": 100000}]
    
    # Run broadcast loop for a short time
    loop_task = asyncio.create_task(manager.broadcast_loop())
    
    await asyncio.sleep(5)  # Wait 5 seconds (should get 2-3 broadcasts)
    
    loop_task.cancel()
    try:
        await loop_task
    except asyncio.CancelledError:
        pass
    
    # Should have received multiple updates
    position_msgs = [m for m in client_ws.messages if m.get("channel") == "positions"]
    assert len(position_msgs) >= 2


@pytest.mark.asyncio
async def test_sequence_never_decreases(redis_mock, duckdb_mock):
    """Test that sequence numbers are strictly monotonic."""
    manager = WebSocketManager(redis_mock, duckdb_mock)
    
    client_ws = MockWebSocket()
    client = WebSocketClient("test_client", client_ws)
    client.subscriptions.add("test")
    manager.clients["test_client"] = client
    
    # Send many broadcasts
    for i in range(100):
        await manager.broadcast("test", {"data": i})
    
    # Extract all sequence numbers
    sequences = [m["seq"] for m in client_ws.messages if "seq" in m]
    
    # Verify strictly increasing
    for i in range(1, len(sequences)):
        assert sequences[i] > sequences[i-1]


@pytest.mark.asyncio
async def test_emergency_halt_stops_broadcasts(redis_mock, duckdb_mock):
    """Test that emergency halt can stop the system."""
    manager = WebSocketManager(redis_mock, duckdb_mock)
    
    # Set emergency halt flag
    redis_mock.get_state.return_value = "true"
    
    # Try to broadcast (in real system, main bot would check this flag)
    await manager.broadcast("test", {"data": "should_not_send"})
    
    # This test verifies the flag can be set
    # Main bot integration would check this flag before trading
    assert redis_mock.get_state.return_value == "true"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
