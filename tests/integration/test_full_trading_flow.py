"""
Full trading flow integration tests.

Tests complete end-to-end scenarios from data → signal → order → execution.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock

from src.data.tiers import Bar, DataTier
from src.regime.detector import RegimeDetector, MarketRegime
from src.strategy.tier1.ema_crossover import EMACrossoverStrategy
from src.risk.position_sizer import PositionSizer, PositionSizingMethod
from src.risk.drawdown_monitor import DrawdownMonitor
from src.execution.order_manager import OrderManager, OrderStatus
from src.execution.reconciler import OrderReconciler


class TestFullTradingFlow:
    """Test complete trading flow integration."""
    
    def test_end_to_end_buy_signal_to_order(self):
        """Test complete flow: data → regime → strategy → risk → order."""
        
        # 1. Create market data
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=100, freq='D')
        prices = 100 + np.random.randn(100).cumsum()
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'open': prices,
            'volume': [1000000] * 100,
        })
        
        # 2. Detect regime
        regime_detector = RegimeDetector()
        regime = regime_detector.detect_regime(bars, symbol="TEST")
        
        assert regime is not None
        
        # 3. Generate signals
        strategy = EMACrossoverStrategy()
        signals = strategy.generate_signals("TEST", bars, current_regime=regime)
        
        # 4. Apply risk management
        position_sizer = PositionSizer(method=PositionSizingMethod.FIXED)
        
        if signals:
            signal = signals[0]
            
            position = position_sizer.calculate_size(
                portfolio_value=100000.0,
                symbol=signal.symbol,
                current_price=bars['close'].iloc[-1],
                regime_scale=regime.position_scale,
            )
            
            assert position.size_dollars > 0
            assert position.size_shares >= 0
            
            # 5. Create order
            order_manager = OrderManager()
            
            order = order_manager.create_order(
                symbol=signal.symbol,
                side="buy" if signal.is_bullish else "sell",
                qty=position.size_shares,
                strategy_name=signal.strategy_name,
                signal_id=signal.signal_id,
            )
            
            assert order is not None
            assert order.status == OrderStatus.PENDING
    
    def test_risk_rejection_flow(self):
        """Test flow when risk management rejects a signal."""
        
        # Create scenario with high drawdown
        drawdown_monitor = DrawdownMonitor(
            max_daily_drawdown_pct=3.0,
            max_total_drawdown_pct=10.0,
            initial_equity=100000.0,
        )
        
        # Trigger drawdown
        metrics = drawdown_monitor.update(87000.0, 100000.0)  # 13% drawdown
        
        # Should halt trading
        assert drawdown_monitor.should_halt_trading(metrics) is True
        
        # Position scale should be minimal or zero
        scale = drawdown_monitor.get_position_scale(metrics)
        assert scale < 0.5  # Severely restricted
    
    def test_order_timeout_and_reconciliation_flow(self):
        """Test flow when order times out and needs reconciliation."""
        
        order_manager = OrderManager()
        mock_broker = Mock()
        mock_redis = Mock()
        
        reconciler = OrderReconciler(order_manager, mock_broker, mock_redis)
        
        # 1. Create and submit order
        order = order_manager.create_order("TEST", "buy", 100)
        order_manager.mark_submitted(order.client_order_id, "broker_123")
        
        # 2. Simulate timeout
        order_manager.mark_unknown(order.client_order_id)
        
        # 3. Reconciliation finds order was filled
        mock_order = Mock()
        mock_order.id = "broker_123"
        mock_order.status = "filled"
        mock_order.filled_qty = 100
        mock_order.filled_avg_price = 150.0
        mock_broker.get_order_by_client_id.return_value = mock_order
        
        # 4. Reconcile
        should_retry, reconciled = reconciler.handle_timeout(order.client_order_id)
        
        # Should not retry (order was filled)
        assert should_retry is False
        assert reconciled.status == OrderStatus.FILLED
    
    def test_multiple_strategies_interaction(self):
        """Test multiple strategies generating conflicting signals."""
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=100, freq='D')
        prices = 100 + np.random.randn(100).cumsum()
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'open': prices,
            'volume': [1000000] * 100,
        })
        
        regime_detector = RegimeDetector()
        regime = regime_detector.detect_regime(bars, symbol="TEST")
        
        # Run multiple strategies
        from src.strategy.tier1.ema_crossover import EMACrossoverStrategy
        from src.strategy.tier1.rsi_mean_reversion import RSIMeanReversionStrategy
        
        ema_strategy = EMACrossoverStrategy()
        rsi_strategy = RSIMeanReversionStrategy()
        
        ema_signals = ema_strategy.generate_signals("TEST", bars, current_regime=regime)
        rsi_signals = rsi_strategy.generate_signals("TEST", bars, current_regime=regime)
        
        # Both should handle same data gracefully
        assert isinstance(ema_signals, list)
        assert isinstance(rsi_signals, list)


class TestCrisisScenarios:
    """Test system behavior during crisis scenarios."""
    
    def test_flash_crash_handling(self):
        """Test system response to flash crash."""
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=50, freq='Min')
        
        # Normal trading
        normal = np.ones(45) * 100
        
        # Flash crash: -20% in 5 minutes
        crash = [100, 95, 88, 82, 80]
        
        prices = np.concatenate([normal, crash])
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'open': prices,
            'volume': [1000000] * 50,
        })
        
        # Should detect as crisis
        regime_detector = RegimeDetector()
        regime = regime_detector.detect_regime(bars, symbol="TEST")
        
        # Position scale should be drastically reduced
        assert regime.position_scale < 1.0
    
    def test_gap_opening_handling(self):
        """Test handling of large gap up/down at market open."""
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=100, freq='D')
        prices = [100] * 100
        
        # Gap down -15% on day 50
        prices[50:] = [85] * 50
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': [p * 1.01 for p in prices],
            'low': [p * 0.99 for p in prices],
            'open': prices,
            'volume': [1000000] * 100,
        })
        
        # System should handle gap gracefully
        regime_detector = RegimeDetector()
        regime = regime_detector.detect_regime(bars, symbol="TEST")
        
        assert regime is not None
    
    def test_extended_downtrend_position_sizing(self):
        """Test that position sizing decreases during extended losses."""
        
        drawdown_monitor = DrawdownMonitor(
            max_daily_drawdown_pct=5.0,
            max_total_drawdown_pct=15.0,
            initial_equity=100000.0,
        )
        
        position_sizer = PositionSizer(method=PositionSizingMethod.FIXED)
        
        equity = 100000.0
        
        # Simulate 10 consecutive losing days
        for day in range(10):
            last_equity = equity
            equity = equity * 0.98  # -2% per day
            
            metrics = drawdown_monitor.update(equity, last_equity)
            scale = drawdown_monitor.get_position_scale(metrics)
            
            # Position scale should decrease
            if day > 0:
                assert scale < 1.0


class TestDataIntegrity:
    """Test data integrity throughout the system."""
    
    def test_tier_0_data_rejection(self):
        """Test that TIER_0 data is rejected for trading."""
        from src.data.tiers import validate_data_for_backtest, DataTier
        
        # Create TIER_0 bars (from yfinance)
        bars_tier0 = [
            Bar(
                symbol="TEST",
                timestamp=datetime(2020, 1, i),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1000000,
                tier=DataTier.TIER_0_UNIVERSE,
                source="yfinance",
            )
            for i in range(1, 11)
        ]
        
        # Should reject
        with pytest.raises(ValueError, match="TIER_0"):
            validate_data_for_backtest(bars_tier0)
    
    def test_mixed_tier_data_rejection(self):
        """Test that mixed tier data is rejected."""
        from src.data.tiers import validate_data_for_backtest, DataTier
        
        bars = [
            Bar(
                symbol="TEST",
                timestamp=datetime(2020, 1, i),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1000000,
                tier=DataTier.TIER_1_VALIDATION if i <= 5 else DataTier.TIER_0_UNIVERSE,
                source="alpaca" if i <= 5 else "yfinance",
            )
            for i in range(1, 11)
        ]
        
        # Should reject mixed tiers
        with pytest.raises(ValueError):
            validate_data_for_backtest(bars)


class TestConcurrency:
    """Test concurrent operations."""
    
    def test_multiple_order_manager_instances(self):
        """Test that multiple order managers maintain separate state."""
        
        manager1 = OrderManager()
        manager2 = OrderManager()
        
        order1 = manager1.create_order("TEST1", "buy", 100)
        order2 = manager2.create_order("TEST2", "buy", 200)
        
        # Each manager should have only its own orders
        assert len(manager1.orders) == 1
        assert len(manager2.orders) == 1
        assert order1.client_order_id != order2.client_order_id
    
    def test_concurrent_signal_generation(self):
        """Test that strategies can run concurrently."""
        from concurrent.futures import ThreadPoolExecutor
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=100, freq='D')
        prices = 100 + np.random.randn(100).cumsum()
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'open': prices,
            'volume': [1000000] * 100,
        })
        
        regime_detector = RegimeDetector()
        regime = regime_detector.detect_regime(bars, symbol="TEST")
        
        strategy = EMACrossoverStrategy()
        
        # Run same strategy concurrently
        def generate():
            return strategy.generate_signals("TEST", bars, current_regime=regime)
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(generate) for _ in range(10)]
            results = [f.result() for f in futures]
        
        # All should complete successfully
        assert len(results) == 10
        assert all(isinstance(r, list) for r in results)
