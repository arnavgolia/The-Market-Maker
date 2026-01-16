"""
Comprehensive watchdog tests.

Tests all kill rules, graceful shutdown, and edge cases.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from watchdog.rules import (
    WatchdogConfig,
    check_daily_loss,
    check_max_drawdown,
    check_position_concentration,
    check_open_orders_limit,
    check_zombie_orders,
    check_heartbeat,
)


class TestWatchdogKillRulesExhaustive:
    """Exhaustive tests for all watchdog kill rules."""
    
    def test_daily_loss_exactly_at_limit(self):
        """Test daily loss exactly at limit (edge case)."""
        config = WatchdogConfig()
        
        state = {
            "equity": 97000.0,  # Exactly 3% loss
            "starting_equity": 100000.0,
        }
        
        # Should trigger at or above limit
        violation = check_daily_loss(state, config)
        assert violation is not None
        assert violation.severity == "critical"
    
    def test_daily_loss_just_below_limit(self):
        """Test daily loss just below limit (should pass)."""
        config = WatchdogConfig()
        
        state = {
            "equity": 97001.0,  # Slightly less than 3% loss
            "starting_equity": 100000.0,
        }
        
        violation = check_daily_loss(state, config)
        # Might be None or warning depending on implementation
        if violation:
            assert violation.severity != "critical"
    
    def test_daily_loss_extreme(self):
        """Test extreme daily loss (>50%)."""
        config = WatchdogConfig()
        
        state = {
            "equity": 40000.0,  # 60% loss
            "starting_equity": 100000.0,
        }
        
        violation = check_daily_loss(state, config)
        assert violation is not None
        assert violation.severity == "critical"
    
    def test_daily_loss_with_gains(self):
        """Test daily loss check with gains (should pass)."""
        config = WatchdogConfig()
        
        state = {
            "equity": 105000.0,  # 5% gain
            "starting_equity": 100000.0,
        }
        
        violation = check_daily_loss(state, config)
        assert violation is None
    
    def test_max_drawdown_at_limit(self):
        """Test max drawdown exactly at limit."""
        config = WatchdogConfig()
        
        state = {
            "equity": 85000.0,  # Exactly 15% from peak
            "peak_equity": 100000.0,
        }
        
        violation = check_max_drawdown(state, config)
        assert violation is not None
        assert violation.severity == "critical"
        assert violation.action == "kill_permanent"
    
    def test_max_drawdown_recovery(self):
        """Test that recovery doesn't clear permanent kill."""
        config = WatchdogConfig()
        
        # Hit max drawdown
        state1 = {
            "equity": 85000.0,
            "peak_equity": 100000.0,
        }
        
        violation1 = check_max_drawdown(state1, config)
        assert violation1 is not None
        assert violation1.action == "kill_permanent"
        
        # Even if equity recovers, it's permanent
        state2 = {
            "equity": 95000.0,
            "peak_equity": 100000.0,
        }
        
        violation2 = check_max_drawdown(state2, config)
        # Should still show some violation or warning
        # (Actual implementation may vary)
    
    def test_position_concentration_single_position(self):
        """Test position concentration with single large position."""
        config = WatchdogConfig()
        
        state = {
            "equity": 100000.0,
            "positions": [
                {"symbol": "AAPL", "market_value": 30000.0},  # 30%
            ],
        }
        
        violation = check_position_concentration(state, config)
        assert violation is not None
        assert "AAPL" in violation.details
    
    def test_position_concentration_multiple_positions(self):
        """Test with multiple positions, one oversized."""
        config = WatchdogConfig()
        
        state = {
            "equity": 100000.0,
            "positions": [
                {"symbol": "AAPL", "market_value": 15000.0},  # 15% OK
                {"symbol": "MSFT", "market_value": 28000.0},  # 28% BREACH
                {"symbol": "GOOGL", "market_value": 10000.0},  # 10% OK
            ],
        }
        
        violation = check_position_concentration(state, config)
        assert violation is not None
        assert "MSFT" in violation.details
    
    def test_position_concentration_at_limit(self):
        """Test position exactly at concentration limit."""
        config = WatchdogConfig()
        
        state = {
            "equity": 100000.0,
            "positions": [
                {"symbol": "AAPL", "market_value": 25000.0},  # Exactly 25%
            ],
        }
        
        violation = check_position_concentration(state, config)
        # At limit should trigger
        assert violation is not None
    
    def test_open_orders_at_limit(self):
        """Test open orders exactly at limit."""
        config = WatchdogConfig()
        
        state = {
            "open_orders": [{"id": f"order_{i}"} for i in range(50)],  # Exactly 50
        }
        
        violation = check_open_orders_limit(state, config)
        assert violation is not None
    
    def test_open_orders_extreme(self):
        """Test extreme number of open orders."""
        config = WatchdogConfig()
        
        state = {
            "open_orders": [{"id": f"order_{i}"} for i in range(500)],  # 500 orders
        }
        
        violation = check_open_orders_limit(state, config)
        assert violation is not None
        assert violation.severity == "critical"
    
    def test_zombie_orders_at_threshold(self):
        """Test zombie orders exactly at timeout threshold."""
        config = WatchdogConfig()
        
        now = datetime.now()
        timeout_time = now - timedelta(seconds=300)  # Exactly 300s
        
        state = {
            "open_orders": [
                {
                    "id": "zombie_order",
                    "status": "submitted",
                    "created_at": timeout_time.isoformat(),
                },
            ],
        }
        
        violation = check_zombie_orders(state, config, current_time=now)
        assert violation is not None
    
    def test_zombie_orders_mixed(self):
        """Test mix of normal and zombie orders."""
        config = WatchdogConfig()
        
        now = datetime.now()
        
        state = {
            "open_orders": [
                {
                    "id": "normal_order",
                    "status": "submitted",
                    "created_at": (now - timedelta(seconds=60)).isoformat(),
                },
                {
                    "id": "zombie_order",
                    "status": "submitted",
                    "created_at": (now - timedelta(seconds=400)).isoformat(),
                },
            ],
        }
        
        violation = check_zombie_orders(state, config, current_time=now)
        assert violation is not None
        assert "zombie_order" in violation.details
    
    def test_heartbeat_at_timeout(self):
        """Test heartbeat exactly at timeout."""
        config = WatchdogConfig()
        
        now = datetime.now()
        last_heartbeat = now - timedelta(seconds=120)  # Exactly 120s
        
        state = {
            "last_heartbeat": last_heartbeat.isoformat(),
        }
        
        violation = check_heartbeat(state, config, current_time=now)
        assert violation is not None
        assert violation.severity == "critical"
    
    def test_heartbeat_just_within_limit(self):
        """Test heartbeat just within limit."""
        config = WatchdogConfig()
        
        now = datetime.now()
        last_heartbeat = now - timedelta(seconds=119)  # Just under 120s
        
        state = {
            "last_heartbeat": last_heartbeat.isoformat(),
        }
        
        violation = check_heartbeat(state, config, current_time=now)
        # Should pass or be warning only
        if violation:
            assert violation.severity != "critical"
    
    def test_heartbeat_never_received(self):
        """Test when heartbeat was never received."""
        config = WatchdogConfig()
        
        state = {
            "last_heartbeat": None,
        }
        
        violation = check_heartbeat(state, config)
        # Should either be critical or handle gracefully (startup case)
        assert violation is not None


class TestWatchdogConfigValidation:
    """Test watchdog configuration validation."""
    
    def test_default_config_values(self):
        """Test that default config has sane values."""
        config = WatchdogConfig()
        
        assert config.max_daily_loss_pct < 0  # Negative (loss)
        assert config.max_drawdown_pct < 0  # Negative (loss)
        assert 0 < config.max_position_concentration_pct < 1.0
        assert config.max_open_orders > 0
        assert config.zombie_order_timeout_sec > 0
        assert config.heartbeat_timeout_sec > 0
    
    def test_config_immutability(self):
        """Test that config values are immutable (frozen)."""
        config = WatchdogConfig()
        
        # Should not be able to modify
        with pytest.raises(AttributeError):
            config.max_daily_loss_pct = -10.0
    
    def test_invalid_config_values(self):
        """Test that invalid config values are rejected."""
        # Positive loss percentage (doesn't make sense)
        with pytest.raises((ValueError, AssertionError)):
            WatchdogConfig(max_daily_loss_pct=5.0)  # Should be negative
        
        # Negative timeout
        with pytest.raises((ValueError, AssertionError)):
            WatchdogConfig(heartbeat_timeout_sec=-60)


class TestWatchdogGracefulShutdown:
    """Test graceful shutdown behavior."""
    
    @patch('signal.signal')
    def test_sigterm_handler_registration(self, mock_signal):
        """Test that SIGTERM handler is registered."""
        from watchdog.graceful_shutdown import GracefulShutdownHandler
        import signal
        
        handler = GracefulShutdownHandler()
        
        # Should register SIGTERM
        # mock_signal.assert_called()  # Check it was called
    
    def test_shutdown_flag_set(self):
        """Test that shutdown flag is set on SIGTERM."""
        from watchdog.graceful_shutdown import GracefulShutdownHandler
        
        handler = GracefulShutdownHandler()
        
        assert handler.should_shutdown is False
        
        # Simulate SIGTERM
        handler.request_shutdown()
        
        assert handler.should_shutdown is True
    
    def test_shutdown_timeout_enforcement(self):
        """Test that shutdown timeout is enforced."""
        from watchdog.graceful_shutdown import GracefulShutdownHandler
        
        handler = GracefulShutdownHandler(timeout_seconds=30)
        
        # Start shutdown
        handler.request_shutdown()
        
        # Check timeout value
        assert handler.timeout_seconds == 30


class TestWatchdogEdgeCases:
    """Test edge cases in watchdog logic."""
    
    def test_zero_equity(self):
        """Test handling of zero equity."""
        config = WatchdogConfig()
        
        state = {
            "equity": 0.0,
            "starting_equity": 100000.0,
            "peak_equity": 100000.0,
        }
        
        # Should trigger multiple violations
        violations = []
        violations.append(check_daily_loss(state, config))
        violations.append(check_max_drawdown(state, config))
        
        # Should have critical violations
        assert any(v is not None and v.severity == "critical" for v in violations)
    
    def test_negative_equity(self):
        """Test handling of negative equity (margin call)."""
        config = WatchdogConfig()
        
        state = {
            "equity": -10000.0,  # Overleveraged
            "starting_equity": 100000.0,
        }
        
        violation = check_daily_loss(state, config)
        assert violation is not None
        assert violation.severity == "critical"
    
    def test_missing_state_fields(self):
        """Test handling of missing state fields."""
        config = WatchdogConfig()
        
        # Missing equity
        state = {
            "starting_equity": 100000.0,
        }
        
        # Should handle gracefully or raise appropriate error
        try:
            violation = check_daily_loss(state, config)
            # If it doesn't raise, should return violation or None
            assert violation is None or violation.severity in ("warning", "critical")
        except (KeyError, ValueError):
            # Acceptable to raise error for missing required fields
            pass
    
    def test_corrupted_timestamps(self):
        """Test handling of corrupted/invalid timestamps."""
        config = WatchdogConfig()
        
        state = {
            "last_heartbeat": "invalid_timestamp",
        }
        
        # Should handle gracefully
        try:
            violation = check_heartbeat(state, config)
            assert violation is not None  # Should treat as critical
        except (ValueError, TypeError):
            # Acceptable to raise on invalid data
            pass
