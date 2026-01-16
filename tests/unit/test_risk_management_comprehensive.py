"""
Comprehensive risk management tests.

Tests position sizing, drawdown limits, and risk controls under all conditions.
"""

import pytest
from datetime import datetime

from src.risk.position_sizer import PositionSizer, PositionSizingMethod, PositionSizeResult
from src.risk.drawdown_monitor import DrawdownMonitor, DrawdownMetrics


class TestPositionSizerEdgeCases:
    """Comprehensive tests for position sizer."""
    
    def test_zero_portfolio_value(self):
        """Test handling of zero portfolio value."""
        sizer = PositionSizer(method=PositionSizingMethod.FIXED)
        
        result = sizer.calculate_size(
            portfolio_value=0.0,
            symbol="TEST",
            current_price=100.0,
            volatility=0.15,
        )
        
        # Should return zero size
        assert result.size_dollars == 0.0
        assert result.size_shares == 0.0
    
    def test_negative_portfolio_value(self):
        """Test handling of negative portfolio value (margin call scenario)."""
        sizer = PositionSizer(method=PositionSizingMethod.FIXED)
        
        # Negative portfolio (overleveraged)
        result = sizer.calculate_size(
            portfolio_value=-10000.0,
            symbol="TEST",
            current_price=100.0,
            volatility=0.15,
        )
        
        # Should return zero or handle defensively
        assert result.size_dollars <= 0.0
    
    def test_extreme_volatility_reduces_size(self):
        """Test that extreme volatility reduces position size."""
        sizer = PositionSizer(
            method=PositionSizingMethod.VOLATILITY_ADJUSTED,
            volatility_target_pct=15.0,
        )
        
        low_vol_result = sizer.calculate_size(
            portfolio_value=100000.0,
            symbol="TEST",
            current_price=100.0,
            volatility=0.05,  # Low vol
        )
        
        high_vol_result = sizer.calculate_size(
            portfolio_value=100000.0,
            symbol="TEST",
            current_price=100.0,
            volatility=0.50,  # Extreme vol
        )
        
        # High vol should have smaller position
        assert high_vol_result.size_dollars < low_vol_result.size_dollars
    
    def test_kelly_criterion_edge_cases(self):
        """Test Kelly criterion with edge cases."""
        sizer = PositionSizer(method=PositionSizingMethod.KELLY)
        
        # Zero edge (50/50 win probability)
        result = sizer.calculate_kelly_size(
            portfolio_value=100000.0,
            win_prob=0.5,
            win_loss_ratio=1.0,
        )
        
        # Should be zero or very small
        assert result.size_pct <= 0.01
        
        # 100% edge (guaranteed win - unrealistic but test boundary)
        result = sizer.calculate_kelly_size(
            portfolio_value=100000.0,
            win_prob=1.0,
            win_loss_ratio=1.0,
        )
        
        # Should be capped (never bet everything)
        assert result.size_pct < 1.0
    
    def test_max_position_limit(self):
        """Test that maximum position limit is enforced."""
        sizer = PositionSizer(
            method=PositionSizingMethod.FIXED,
            max_position_pct=10.0,  # 10% max
        )
        
        result = sizer.calculate_size(
            portfolio_value=100000.0,
            symbol="TEST",
            current_price=100.0,
        )
        
        # Apply max limit
        limited_result = sizer.apply_max_limit(result, 100000.0)
        
        # Should never exceed 10% of portfolio
        assert limited_result.size_dollars <= 10000.0
    
    def test_fractional_shares_handling(self):
        """Test handling of fractional shares."""
        sizer = PositionSizer(method=PositionSizingMethod.FIXED)
        
        result = sizer.calculate_size(
            portfolio_value=100000.0,
            symbol="TEST",
            current_price=333.33,  # Will result in fractional shares
        )
        
        # Should handle fractional shares
        assert result.size_shares >= 0
    
    def test_high_price_stock(self):
        """Test position sizing for very high-priced stock (e.g., BRK.A)."""
        sizer = PositionSizer(
            method=PositionSizingMethod.FIXED,
            max_position_pct=10.0,
        )
        
        result = sizer.calculate_size(
            portfolio_value=100000.0,
            symbol="BRK.A",
            current_price=500000.0,  # $500k per share
        )
        
        # Might only afford 1 share or less
        assert result.size_shares >= 0
        assert result.size_dollars <= 100000.0
    
    def test_penny_stock(self):
        """Test position sizing for penny stock."""
        sizer = PositionSizer(method=PositionSizingMethod.FIXED)
        
        result = sizer.calculate_size(
            portfolio_value=100000.0,
            symbol="PENNY",
            current_price=0.01,  # 1 cent
        )
        
        # Should handle tiny prices
        assert result.size_shares >= 0
        assert result.current_price == 0.01


class TestDrawdownMonitorEdgeCases:
    """Comprehensive tests for drawdown monitor."""
    
    def test_initial_state(self):
        """Test drawdown monitor initial state."""
        monitor = DrawdownMonitor(
            max_daily_drawdown_pct=3.0,
            max_total_drawdown_pct=10.0,
            initial_equity=100000.0,
        )
        
        metrics = monitor.update(100000.0, 100000.0)
        
        # Initial state: no drawdown
        assert metrics.total_drawdown_pct == 0.0
        assert metrics.daily_drawdown_pct == 0.0
        assert monitor.should_halt_trading(metrics) is False
    
    def test_daily_drawdown_breach(self):
        """Test that daily drawdown breach halts trading."""
        monitor = DrawdownMonitor(
            max_daily_drawdown_pct=3.0,
            max_total_drawdown_pct=10.0,
            initial_equity=100000.0,
        )
        
        # 5% daily loss
        metrics = monitor.update(95000.0, 100000.0)
        
        # Should halt trading
        assert metrics.daily_drawdown_pct >= 3.0
        assert monitor.should_halt_trading(metrics) is True
    
    def test_total_drawdown_breach(self):
        """Test that total drawdown breach halts trading."""
        monitor = DrawdownMonitor(
            max_daily_drawdown_pct=3.0,
            max_total_drawdown_pct=10.0,
            initial_equity=100000.0,
        )
        
        # 15% total loss from peak
        metrics = monitor.update(85000.0, 100000.0)
        
        # Should halt trading
        assert metrics.total_drawdown_pct >= 10.0
        assert monitor.should_halt_trading(metrics) is True
    
    def test_recovery_from_drawdown(self):
        """Test recovery from drawdown."""
        monitor = DrawdownMonitor(
            max_daily_drawdown_pct=3.0,
            max_total_drawdown_pct=10.0,
            initial_equity=100000.0,
        )
        
        # Drawdown
        monitor.update(95000.0, 100000.0)
        
        # Recovery
        metrics = monitor.update(99000.0, 95000.0)
        
        # Daily drawdown should reset
        assert metrics.daily_drawdown_pct < 3.0
        assert monitor.should_halt_trading(metrics) is False
    
    def test_new_peak(self):
        """Test that new peaks update peak equity."""
        monitor = DrawdownMonitor(
            max_daily_drawdown_pct=3.0,
            max_total_drawdown_pct=10.0,
            initial_equity=100000.0,
        )
        
        # Make profit - new peak
        metrics = monitor.update(110000.0, 100000.0)
        
        # Peak should be updated
        assert metrics.peak_equity >= 110000.0
        assert metrics.total_drawdown_pct == 0.0
    
    def test_zero_equity(self):
        """Test handling of zero equity (blown up account)."""
        monitor = DrawdownMonitor(
            max_daily_drawdown_pct=3.0,
            max_total_drawdown_pct=10.0,
            initial_equity=100000.0,
        )
        
        metrics = monitor.update(0.0, 100000.0)
        
        # Should definitely halt
        assert monitor.should_halt_trading(metrics) is True
        assert metrics.total_drawdown_pct == 1.0  # 100% drawdown
    
    def test_position_scale_calculation(self):
        """Test position scale calculation at various drawdown levels."""
        monitor = DrawdownMonitor(
            max_daily_drawdown_pct=5.0,
            max_total_drawdown_pct=15.0,
            initial_equity=100000.0,
        )
        
        # No drawdown - full scale
        metrics1 = monitor.update(100000.0, 100000.0)
        scale1 = monitor.get_position_scale(metrics1)
        assert scale1 == 1.0
        
        # 5% drawdown - reduced scale
        metrics2 = monitor.update(95000.0, 100000.0)
        scale2 = monitor.get_position_scale(metrics2)
        assert scale2 < 1.0
        
        # 10% drawdown - further reduced
        metrics3 = monitor.update(90000.0, 100000.0)
        scale3 = monitor.get_position_scale(metrics3)
        assert scale3 < scale2
    
    def test_consecutive_losing_days(self):
        """Test handling of consecutive losing days."""
        monitor = DrawdownMonitor(
            max_daily_drawdown_pct=3.0,
            max_total_drawdown_pct=10.0,
            initial_equity=100000.0,
        )
        
        equity = 100000.0
        
        # 5 consecutive 2% losing days
        for _ in range(5):
            last_equity = equity
            equity = equity * 0.98
            metrics = monitor.update(equity, last_equity)
        
        # Should accumulate drawdown
        assert metrics.total_drawdown_pct > 5.0
    
    def test_volatility_of_returns(self):
        """Test drawdown monitoring with volatile returns."""
        monitor = DrawdownMonitor(
            max_daily_drawdown_pct=5.0,
            max_total_drawdown_pct=15.0,
            initial_equity=100000.0,
        )
        
        import numpy as np
        np.random.seed(42)
        
        equity = 100000.0
        
        # Random volatile returns
        for _ in range(20):
            last_equity = equity
            daily_return = np.random.randn() * 0.03  # ±3% daily
            equity = equity * (1 + daily_return)
            
            metrics = monitor.update(equity, last_equity)
            
            # Should track correctly
            assert metrics is not None


class TestRiskLimitsIntegration:
    """Test interaction between different risk controls."""
    
    def test_position_size_reduced_by_drawdown(self):
        """Test that drawdown reduces position sizes."""
        sizer = PositionSizer(method=PositionSizingMethod.FIXED)
        monitor = DrawdownMonitor(
            max_daily_drawdown_pct=5.0,
            max_total_drawdown_pct=15.0,
            initial_equity=100000.0,
        )
        
        # Normal conditions
        base_result = sizer.calculate_size(
            portfolio_value=100000.0,
            symbol="TEST",
            current_price=100.0,
            regime_scale=1.0,
        )
        
        # After 8% drawdown
        metrics = monitor.update(92000.0, 100000.0)
        drawdown_scale = monitor.get_position_scale(metrics)
        
        reduced_result = sizer.calculate_size(
            portfolio_value=92000.0,
            symbol="TEST",
            current_price=100.0,
            regime_scale=drawdown_scale,
        )
        
        # Position should be smaller
        assert reduced_result.size_dollars < base_result.size_dollars
    
    def test_multiple_risk_factors_compound(self):
        """Test that multiple risk factors compound correctly."""
        sizer = PositionSizer(
            method=PositionSizingMethod.VOLATILITY_ADJUSTED,
            max_position_pct=10.0,
        )
        
        # High vol + regime scale + drawdown scale
        result = sizer.calculate_size(
            portfolio_value=100000.0,
            symbol="TEST",
            current_price=100.0,
            volatility=0.50,  # High vol
            regime_scale=0.5,  # Crisis regime
        )
        
        # Position should be heavily reduced
        assert result.size_dollars < 10000.0  # Less than max 10%
