"""
Kill rules for the watchdog.

These are HARDCODED safety limits - not tunable parameters.
They represent institutional-grade risk management practices.

WARNING: Modifying these values increases risk of catastrophic loss.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class KillRules:
    """
    Kill switch rules. These are FROZEN - not configurable at runtime.
    
    Each rule represents a failure mode that requires immediate action.
    If ANY rule is breached, the watchdog takes protective action.
    """
    
    # ==========================================================================
    # LOSS LIMITS
    # ==========================================================================
    
    # Maximum daily loss before emergency shutdown
    # If daily PnL < -5%, liquidate all positions and halt
    max_daily_loss_pct: float = -5.0
    
    # Maximum total drawdown before PERMANENT shutdown (Gemini's recommendation)
    # If total equity < 85% of initial, delete API keys and require human intervention
    max_drawdown_permanent_pct: float = -15.0
    
    # ==========================================================================
    # POSITION LIMITS
    # ==========================================================================
    
    # Maximum single position concentration
    # If any position > 25% of portfolio, trigger kill
    max_position_concentration_pct: float = 25.0
    
    # ==========================================================================
    # ORDER LIMITS
    # ==========================================================================
    
    # Maximum open orders (runaway detection)
    # If open orders > 50, something is wrong
    max_open_orders: int = 50
    
    # Order rate limit (runaway detection)
    # If > 20 orders/minute, trigger kill
    max_orders_per_minute: int = 20
    
    # Zombie order detection (Gemini's recommendation)
    # If ANY order is OPEN for > 300s, trigger kill
    # Orders should fill, cancel, or fail - never hang
    max_order_hang_seconds: int = 300
    
    # ==========================================================================
    # HEARTBEAT
    # ==========================================================================
    
    # Heartbeat timeout
    # If main bot doesn't heartbeat for 120s, assume dead
    heartbeat_timeout_seconds: int = 120
    
    # ==========================================================================
    # SHUTDOWN PROTOCOL
    # ==========================================================================
    
    # Time to wait for graceful shutdown (SIGTERM)
    graceful_shutdown_timeout_seconds: int = 30
    
    # Maximum restart attempts before requiring human intervention
    max_restart_attempts: int = 3
    
    # Cooldown between restart attempts
    restart_cooldown_seconds: int = 300  # 5 minutes
    
    # ==========================================================================
    # API HEALTH
    # ==========================================================================
    
    # Maximum acceptable API latency before deferring kill decision
    max_api_latency_seconds: float = 5.0
    
    # ==========================================================================
    # TIME-BASED RULES (Gemini's recommendation)
    # ==========================================================================
    
    # Force close all positions before market close on Friday
    # No weekend risk. Period.
    friday_force_close_time: str = "15:55:00"  # 3:55 PM EST
    
    
    def check_daily_loss(self, daily_pnl_pct: float) -> tuple[bool, Optional[str]]:
        """Check if daily loss limit is breached."""
        if daily_pnl_pct < self.max_daily_loss_pct:
            return True, f"Daily loss limit breached: {daily_pnl_pct:.2f}% < {self.max_daily_loss_pct}%"
        return False, None
    
    def check_max_drawdown(self, current_equity: float, initial_equity: float) -> tuple[bool, Optional[str]]:
        """
        Check if max drawdown is breached (permanent shutdown).
        
        This is the "nuclear option" - requires human intervention to restart.
        """
        if initial_equity <= 0:
            return False, None
        
        drawdown_pct = ((current_equity - initial_equity) / initial_equity) * 100
        
        if drawdown_pct < self.max_drawdown_permanent_pct:
            return True, (
                f"PERMANENT DRAWDOWN LIMIT BREACHED: {drawdown_pct:.2f}% < {self.max_drawdown_permanent_pct}%. "
                "System requires human intervention to restart."
            )
        return False, None
    
    def check_position_concentration(
        self, 
        position_value: float, 
        total_equity: float
    ) -> tuple[bool, Optional[str]]:
        """Check if position concentration is too high."""
        if total_equity <= 0:
            return False, None
        
        concentration = (abs(position_value) / total_equity) * 100
        
        if concentration > self.max_position_concentration_pct:
            return True, (
                f"Position concentration breached: {concentration:.1f}% > {self.max_position_concentration_pct}%"
            )
        return False, None
    
    def check_open_orders(self, order_count: int) -> tuple[bool, Optional[str]]:
        """Check if too many orders are open (runaway detection)."""
        if order_count > self.max_open_orders:
            return True, f"Too many open orders: {order_count} > {self.max_open_orders}"
        return False, None
    
    def check_order_rate(self, orders_per_minute: int) -> tuple[bool, Optional[str]]:
        """Check if order rate is too high (runaway detection)."""
        if orders_per_minute > self.max_orders_per_minute:
            return True, f"Order rate too high: {orders_per_minute}/min > {self.max_orders_per_minute}/min"
        return False, None
    
    def check_zombie_orders(self, oldest_order_age_seconds: float) -> tuple[bool, Optional[str]]:
        """
        Check for zombie orders (Gemini's recommendation).
        
        Orders should fill, cancel, or fail - never hang indefinitely.
        """
        if oldest_order_age_seconds > self.max_order_hang_seconds:
            return True, (
                f"Zombie order detected: {oldest_order_age_seconds:.0f}s > {self.max_order_hang_seconds}s"
            )
        return False, None
    
    def check_heartbeat(self, seconds_since_heartbeat: float) -> tuple[bool, Optional[str]]:
        """Check if heartbeat has timed out."""
        if seconds_since_heartbeat > self.heartbeat_timeout_seconds:
            return True, (
                f"Heartbeat timeout: {seconds_since_heartbeat:.0f}s > {self.heartbeat_timeout_seconds}s"
            )
        return False, None


# Default rules instance (use this everywhere)
DEFAULT_RULES = KillRules()


def get_warning_thresholds() -> dict:
    """
    Get warning thresholds (alerts before kill triggers).
    
    These provide early warning before hard limits are hit.
    """
    return {
        "daily_loss_warning_pct": -3.0,  # Warn at -3%, kill at -5%
        "position_concentration_warning_pct": 20.0,  # Warn at 20%, kill at 25%
        "open_orders_warning": 30,  # Warn at 30, kill at 50
        "heartbeat_warning_seconds": 90,  # Warn at 90s, kill at 120s
    }
