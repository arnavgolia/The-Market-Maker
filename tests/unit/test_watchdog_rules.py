"""
Tests for watchdog kill rules.

These tests verify that the safety limits work correctly.
The watchdog is the last line of defense against catastrophic loss.
"""

import pytest

from watchdog.rules import KillRules, DEFAULT_RULES


class TestKillRules:
    """Tests for KillRules."""
    
    def test_default_rules_frozen(self):
        """Default rules should be frozen (immutable)."""
        rules = DEFAULT_RULES
        
        # KillRules is a frozen dataclass
        with pytest.raises(AttributeError):
            rules.max_daily_loss_pct = -10.0
    
    def test_daily_loss_check_breach(self):
        """Daily loss should trigger at -5%."""
        rules = KillRules()
        
        # -6% should breach the -5% limit
        breached, reason = rules.check_daily_loss(-6.0)
        assert breached is True
        assert reason is not None
        assert "-6.00%" in reason
    
    def test_daily_loss_check_ok(self):
        """Daily loss within limit should not trigger."""
        rules = KillRules()
        
        # -3% should be fine
        breached, reason = rules.check_daily_loss(-3.0)
        assert breached is False
        assert reason is None
    
    def test_max_drawdown_permanent_breach(self):
        """Max drawdown should trigger permanent shutdown."""
        rules = KillRules()
        
        initial_equity = 100000
        current_equity = 80000  # -20% drawdown
        
        breached, reason = rules.check_max_drawdown(current_equity, initial_equity)
        assert breached is True
        assert "PERMANENT" in reason
    
    def test_max_drawdown_ok(self):
        """Drawdown within limit should not trigger."""
        rules = KillRules()
        
        initial_equity = 100000
        current_equity = 90000  # -10% drawdown (limit is -15%)
        
        breached, reason = rules.check_max_drawdown(current_equity, initial_equity)
        assert breached is False
    
    def test_position_concentration_breach(self):
        """Position > 25% should trigger."""
        rules = KillRules()
        
        position_value = 30000
        total_equity = 100000  # 30% concentration
        
        breached, reason = rules.check_position_concentration(position_value, total_equity)
        assert breached is True
        assert "30.0%" in reason
    
    def test_position_concentration_ok(self):
        """Position within limit should not trigger."""
        rules = KillRules()
        
        position_value = 20000
        total_equity = 100000  # 20% concentration
        
        breached, reason = rules.check_position_concentration(position_value, total_equity)
        assert breached is False
    
    def test_open_orders_breach(self):
        """Too many open orders should trigger."""
        rules = KillRules()
        
        breached, reason = rules.check_open_orders(100)  # Limit is 50
        assert breached is True
    
    def test_open_orders_ok(self):
        """Order count within limit should not trigger."""
        rules = KillRules()
        
        breached, reason = rules.check_open_orders(30)
        assert breached is False
    
    def test_zombie_order_breach(self):
        """Zombie order (>300s) should trigger."""
        rules = KillRules()
        
        # Order hanging for 400 seconds
        breached, reason = rules.check_zombie_orders(400)
        assert breached is True
        assert "400" in reason
    
    def test_zombie_order_ok(self):
        """Recent order should not trigger."""
        rules = KillRules()
        
        # Order only 60 seconds old
        breached, reason = rules.check_zombie_orders(60)
        assert breached is False
    
    def test_heartbeat_breach(self):
        """Missing heartbeat (>120s) should trigger."""
        rules = KillRules()
        
        breached, reason = rules.check_heartbeat(150)  # 150 seconds since heartbeat
        assert breached is True
    
    def test_heartbeat_ok(self):
        """Recent heartbeat should not trigger."""
        rules = KillRules()
        
        breached, reason = rules.check_heartbeat(60)
        assert breached is False


class TestDefaultRulesValues:
    """Test that default rule values are sensible."""
    
    def test_daily_loss_limit(self):
        """Daily loss limit should be -5%."""
        assert DEFAULT_RULES.max_daily_loss_pct == -5.0
    
    def test_max_drawdown_limit(self):
        """Max drawdown limit should be -15%."""
        assert DEFAULT_RULES.max_drawdown_permanent_pct == -15.0
    
    def test_position_concentration_limit(self):
        """Position concentration limit should be 25%."""
        assert DEFAULT_RULES.max_position_concentration_pct == 25.0
    
    def test_max_open_orders(self):
        """Max open orders should be 50."""
        assert DEFAULT_RULES.max_open_orders == 50
    
    def test_zombie_order_timeout(self):
        """Zombie order timeout should be 300 seconds."""
        assert DEFAULT_RULES.max_order_hang_seconds == 300
    
    def test_heartbeat_timeout(self):
        """Heartbeat timeout should be 120 seconds."""
        assert DEFAULT_RULES.heartbeat_timeout_seconds == 120
    
    def test_graceful_shutdown_timeout(self):
        """Graceful shutdown timeout should be 30 seconds."""
        assert DEFAULT_RULES.graceful_shutdown_timeout_seconds == 30
    
    def test_max_restart_attempts(self):
        """Max restart attempts should be 3."""
        assert DEFAULT_RULES.max_restart_attempts == 3
