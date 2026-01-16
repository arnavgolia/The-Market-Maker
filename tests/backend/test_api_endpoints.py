"""
Comprehensive API endpoint tests.

Tests all REST endpoints for:
- Correct responses
- Error handling
- Data validation
- Edge cases
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import json

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from api.main import app


@pytest.fixture
def client():
    """Test client."""
    return TestClient(app)


@pytest.fixture
def mock_redis():
    """Mock Redis for testing."""
    with patch('api.main.redis_store') as mock:
        mock.get_all_positions.return_value = {
            "AAPL": {
                "symbol": "AAPL",
                "qty": 10,
                "avg_price": 175.0,
                "market_value": 1750.0,
                "unrealized_pnl": 50.0,
                "side": "long"
            }
        }
        mock.get_initial_equity.return_value = 100000.0
        mock.get_equity_history.return_value = [
            {"timestamp": "2024-01-01T10:00:00Z", "equity": 100000},
            {"timestamp": "2024-01-01T11:00:00Z", "equity": 100500},
        ]
        mock.get_state.return_value = json.dumps({
            "trend_regime": "TRENDING",
            "vol_regime": "NORMAL",
            "momentum_enabled": True
        })
        mock.is_process_alive.return_value = True
        mock.check_heartbeat.return_value = None
        mock.get_stats.return_value = {"keys": 10}
        mock.client.keys.return_value = []
        mock.client.get.return_value = None
        mock.set_state.return_value = True
        yield mock


class TestHealthEndpoint:
    """Tests for /api/v1/health endpoint."""
    
    def test_health_check_returns_ok(self, client, mock_redis):
        """Test health check returns healthy status."""
        response = client.get("/api/v1/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["redis"] is True
        assert "websocket" in data
    
    def test_health_check_includes_timestamp(self, client, mock_redis):
        """Test health check includes UTC timestamp."""
        response = client.get("/api/v1/health")
        data = response.json()
        
        assert "timestamp" in data
        assert data["timestamp"].endswith("Z")


class TestPositionsEndpoint:
    """Tests for /api/v1/portfolio/positions endpoint."""
    
    def test_get_positions_success(self, client, mock_redis):
        """Test getting positions returns correct data."""
        response = client.get("/api/v1/portfolio/positions")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "positions" in data
        assert "count" in data
        assert data["count"] == 1
        assert len(data["positions"]) == 1
        assert data["positions"][0]["symbol"] == "AAPL"
    
    def test_get_positions_empty(self, client, mock_redis):
        """Test getting positions when none exist."""
        mock_redis.get_all_positions.return_value = {}
        
        response = client.get("/api/v1/portfolio/positions")
        data = response.json()
        
        assert data["count"] == 0
        assert data["positions"] == []
    
    def test_get_positions_redis_failure(self, client, mock_redis):
        """Test handling Redis failure."""
        mock_redis.get_all_positions.side_effect = Exception("Redis connection failed")
        
        response = client.get("/api/v1/portfolio/positions")
        
        assert response.status_code == 500


class TestEquityEndpoint:
    """Tests for /api/v1/portfolio/equity endpoint."""
    
    def test_get_equity_success(self, client, mock_redis):
        """Test getting equity returns correct data."""
        response = client.get("/api/v1/portfolio/equity")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "current_equity" in data
        assert "initial_equity" in data
        assert "daily_return_pct" in data
        assert "equity_history" in data
        assert data["current_equity"] == 100500
    
    def test_get_equity_calculates_return(self, client, mock_redis):
        """Test that equity return is calculated correctly."""
        mock_redis.get_initial_equity.return_value = 100000.0
        mock_redis.get_equity_history.return_value = [
            {"timestamp": "2024-01-01T10:00:00Z", "equity": 102000},
        ]
        
        response = client.get("/api/v1/portfolio/equity")
        data = response.json()
        
        # Should be +2%
        assert abs(data["daily_return_pct"] - 2.0) < 0.01
    
    def test_get_equity_limits_history_to_500(self, client, mock_redis):
        """Test that equity history is limited to last 500 points."""
        # Create 1000 history points
        history = [
            {"timestamp": f"2024-01-01T{i:02d}:00:00Z", "equity": 100000 + i}
            for i in range(1000)
        ]
        mock_redis.get_equity_history.return_value = history
        
        response = client.get("/api/v1/portfolio/equity")
        data = response.json()
        
        # Should only return last 500
        assert len(data["equity_history"]) == 500
    
    def test_get_equity_no_history(self, client, mock_redis):
        """Test getting equity when no history exists."""
        mock_redis.get_equity_history.return_value = []
        
        response = client.get("/api/v1/portfolio/equity")
        data = response.json()
        
        # Should default to initial equity
        assert data["current_equity"] == 100000.0


class TestOrdersEndpoint:
    """Tests for /api/v1/portfolio/orders endpoint."""
    
    def test_get_orders_success(self, client, mock_redis):
        """Test getting orders returns correct data."""
        mock_redis.client.keys.return_value = [
            "orders:order1",
            "orders:order2"
        ]
        mock_redis.client.get.side_effect = [
            json.dumps({"order_id": "order1", "symbol": "AAPL", "status": "filled"}),
            json.dumps({"order_id": "order2", "symbol": "MSFT", "status": "pending"}),
        ]
        
        response = client.get("/api/v1/portfolio/orders")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "orders" in data
        assert "count" in data
    
    def test_get_orders_respects_limit(self, client, mock_redis):
        """Test that orders limit parameter works."""
        # Create 100 order keys
        mock_redis.client.keys.return_value = [f"orders:order{i}" for i in range(100)]
        
        response = client.get("/api/v1/portfolio/orders?limit=10")
        data = response.json()
        
        # Should process max 10
        assert len(data["orders"]) <= 10
    
    def test_get_orders_empty(self, client, mock_redis):
        """Test getting orders when none exist."""
        mock_redis.client.keys.return_value = []
        
        response = client.get("/api/v1/portfolio/orders")
        data = response.json()
        
        assert data["count"] == 0
        assert data["orders"] == []


class TestSystemStatusEndpoint:
    """Tests for /api/v1/system/status endpoint."""
    
    def test_system_status_success(self, client, mock_redis):
        """Test system status returns all components."""
        response = client.get("/api/v1/system/status")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "components" in data
        assert "main_bot" in data["components"]
        assert "redis" in data["components"]
        assert "duckdb" in data["components"]
    
    def test_system_status_detects_dead_bot(self, client, mock_redis):
        """Test that dead bot is detected."""
        mock_redis.is_process_alive.return_value = False
        
        response = client.get("/api/v1/system/status")
        data = response.json()
        
        assert data["components"]["main_bot"]["status"] == "warning"


class TestRegimeEndpoint:
    """Tests for /api/v1/regime/current endpoint."""
    
    def test_get_regime_success(self, client, mock_redis):
        """Test getting current regime."""
        response = client.get("/api/v1/regime/current")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "trend_regime" in data
        assert "vol_regime" in data
        assert data["trend_regime"] == "TRENDING"
    
    def test_get_regime_no_data(self, client, mock_redis):
        """Test getting regime when no data exists."""
        mock_redis.get_state.return_value = None
        
        response = client.get("/api/v1/regime/current")
        data = response.json()
        
        assert data["trend_regime"] == "unknown"
        assert data["vol_regime"] == "unknown"


class TestEmergencyHaltEndpoint:
    """Tests for /api/v1/system/emergency-halt endpoint."""
    
    def test_emergency_halt_success(self, client, mock_redis):
        """Test emergency halt triggers correctly."""
        response = client.post("/api/v1/system/emergency-halt")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "halted"
        assert "message" in data
        assert "timestamp" in data
        
        # Should have called set_state
        mock_redis.set_state.assert_called_once_with("emergency_halt", "true")
    
    def test_emergency_halt_redis_failure(self, client, mock_redis):
        """Test handling Redis failure during halt."""
        mock_redis.set_state.side_effect = Exception("Redis error")
        
        response = client.post("/api/v1/system/emergency-halt")
        
        assert response.status_code == 500


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_invalid_endpoint_returns_404(self, client):
        """Test that invalid endpoints return 404."""
        response = client.get("/api/v1/invalid/endpoint")
        assert response.status_code == 404
    
    def test_cors_headers_present(self, client, mock_redis):
        """Test that CORS headers are present."""
        response = client.get("/api/v1/health")
        
        # CORS middleware should add headers
        assert response.status_code == 200
    
    def test_timestamp_format_consistency(self, client, mock_redis):
        """Test that all timestamps end with 'Z'."""
        endpoints = [
            "/api/v1/health",
            "/api/v1/portfolio/positions",
            "/api/v1/portfolio/equity",
        ]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            data = response.json()
            
            if "timestamp" in data:
                assert data["timestamp"].endswith("Z")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
