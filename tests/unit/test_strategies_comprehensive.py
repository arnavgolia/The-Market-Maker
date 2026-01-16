"""
Comprehensive strategy tests.

Tests all strategies under various market conditions, edge cases, and error scenarios.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.strategy.tier1.ema_crossover import EMACrossoverStrategy
from src.strategy.tier1.rsi_mean_reversion import RSIMeanReversionStrategy
from src.strategy.base import SignalType
from src.regime.detector import MarketRegime, TrendRegime, VolRegime


class TestEMACrossoverComprehensive:
    """Comprehensive tests for EMA crossover strategy."""
    
    def test_no_signal_choppy_regime(self):
        """Test that no signals are generated in choppy regime."""
        strategy = EMACrossoverStrategy()
        
        # Create bars
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
        
        # Choppy regime
        regime = MarketRegime(
            timestamp=datetime.now(),
            trend=TrendRegime.CHOPPY,
            volatility=VolRegime.NORMAL,
            momentum_enabled=False,
        )
        
        signals = strategy.generate_signals("TEST", bars, current_regime=regime)
        
        # Should generate no signals in choppy regime
        assert len(signals) == 0
    
    def test_bullish_crossover(self):
        """Test bullish EMA crossover generates buy signal."""
        strategy = EMACrossoverStrategy(fast_period=5, slow_period=10)
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=50, freq='D')
        
        # Create downtrend then uptrend (crossover)
        downtrend = np.linspace(100, 90, 25)
        uptrend = np.linspace(90, 110, 25)
        prices = np.concatenate([downtrend, uptrend])
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'open': prices,
            'volume': [1000000] * 50,
        })
        
        # Trending regime
        regime = MarketRegime(
            timestamp=datetime.now(),
            trend=TrendRegime.STRONG_TREND,
            volatility=VolRegime.NORMAL,
            momentum_enabled=True,
        )
        
        signals = strategy.generate_signals("TEST", bars, current_regime=regime)
        
        # Should generate buy signal
        assert len(signals) > 0
        assert any(s.signal_type == SignalType.BUY for s in signals)
    
    def test_bearish_crossover(self):
        """Test bearish crossover generates sell signal."""
        strategy = EMACrossoverStrategy(fast_period=5, slow_period=10)
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=50, freq='D')
        
        # Create uptrend then downtrend (bearish crossover)
        uptrend = np.linspace(90, 110, 25)
        downtrend = np.linspace(110, 90, 25)
        prices = np.concatenate([uptrend, downtrend])
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'open': prices,
            'volume': [1000000] * 50,
        })
        
        regime = MarketRegime(
            timestamp=datetime.now(),
            trend=TrendRegime.STRONG_TREND,
            volatility=VolRegime.NORMAL,
            momentum_enabled=True,
        )
        
        # Simulate having a position
        current_position = {"qty": 100, "avg_price": 105.0}
        
        signals = strategy.generate_signals("TEST", bars, current_regime=regime, current_position=current_position)
        
        # Should generate sell/close signal
        assert len(signals) > 0
        assert any(s.signal_type in (SignalType.SELL, SignalType.CLOSE) for s in signals)
    
    def test_insufficient_data(self):
        """Test handling of insufficient data."""
        strategy = EMACrossoverStrategy(fast_period=12, slow_period=26)
        
        # Only 10 bars (need at least 26)
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=10, freq='D')
        prices = [100 + i for i in range(10)]
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': [p * 1.01 for p in prices],
            'low': [p * 0.99 for p in prices],
            'open': prices,
            'volume': [1000000] * 10,
        })
        
        regime = MarketRegime(
            timestamp=datetime.now(),
            trend=TrendRegime.STRONG_TREND,
            momentum_enabled=True,
        )
        
        signals = strategy.generate_signals("TEST", bars, current_regime=regime)
        
        # Should return empty list, not crash
        assert isinstance(signals, list)
    
    def test_flat_market(self):
        """Test strategy with perfectly flat market."""
        strategy = EMACrossoverStrategy()
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=100, freq='D')
        prices = [100.0] * 100  # Perfectly flat
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices,
            'low': prices,
            'open': prices,
            'volume': [1000000] * 100,
        })
        
        regime = MarketRegime(
            timestamp=datetime.now(),
            trend=TrendRegime.CHOPPY,
            momentum_enabled=False,
        )
        
        signals = strategy.generate_signals("TEST", bars, current_regime=regime)
        
        # Should handle gracefully
        assert isinstance(signals, list)
    
    def test_whipsaw_protection(self):
        """Test that strategy doesn't generate excessive signals in whipsaw market."""
        strategy = EMACrossoverStrategy(fast_period=5, slow_period=10)
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=100, freq='D')
        
        # Create whipsaw (rapid reversals)
        prices = 100 + np.sin(np.linspace(0, 20, 100)) * 10
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'open': prices,
            'volume': [1000000] * 100,
        })
        
        regime = MarketRegime(
            timestamp=datetime.now(),
            trend=TrendRegime.CHOPPY,
            momentum_enabled=False,
        )
        
        signals = strategy.generate_signals("TEST", bars, current_regime=regime)
        
        # Choppy regime should suppress signals
        assert len(signals) == 0


class TestRSIMeanReversionComprehensive:
    """Comprehensive tests for RSI mean reversion strategy."""
    
    def test_oversold_generates_buy(self):
        """Test that oversold RSI generates buy signal."""
        strategy = RSIMeanReversionStrategy(period=14, oversold_threshold=30.0)
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=50, freq='D')
        
        # Create strong downtrend (oversold)
        prices = np.linspace(100, 70, 50)
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'open': prices,
            'volume': [1000000] * 50,
        })
        
        regime = MarketRegime(
            timestamp=datetime.now(),
            trend=TrendRegime.WEAK_TREND,
            momentum_enabled=True,
        )
        
        signals = strategy.generate_signals("TEST", bars, current_regime=regime)
        
        # Should generate buy signal
        assert len(signals) > 0
        assert any(s.signal_type == SignalType.BUY for s in signals)
    
    def test_overbought_with_position_generates_sell(self):
        """Test that overbought RSI with position generates sell."""
        strategy = RSIMeanReversionStrategy(period=14, overbought_threshold=70.0)
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=50, freq='D')
        
        # Create strong uptrend (overbought)
        prices = np.linspace(70, 100, 50)
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'open': prices,
            'volume': [1000000] * 50,
        })
        
        regime = MarketRegime(
            timestamp=datetime.now(),
            trend=TrendRegime.WEAK_TREND,
            momentum_enabled=True,
        )
        
        # Have position
        current_position = {"qty": 100, "avg_price": 75.0}
        
        signals = strategy.generate_signals("TEST", bars, current_regime=regime, current_position=current_position)
        
        # Should generate sell signal
        assert len(signals) > 0
        assert any(s.signal_type in (SignalType.SELL, SignalType.CLOSE) for s in signals)
    
    def test_rsi_extreme_values(self):
        """Test RSI with extreme price movements."""
        strategy = RSIMeanReversionStrategy()
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=50, freq='D')
        
        # Extreme crash then recovery
        crash = np.linspace(100, 10, 10)  # 90% crash
        recovery = np.linspace(10, 100, 40)
        prices = np.concatenate([crash, recovery])
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.1,
            'low': prices * 0.9,
            'open': prices,
            'volume': [1000000] * 50,
        })
        
        regime = MarketRegime(
            timestamp=datetime.now(),
            trend=TrendRegime.STRONG_TREND,
            momentum_enabled=True,
        )
        
        # Should handle extreme values gracefully
        signals = strategy.generate_signals("TEST", bars, current_regime=regime)
        assert isinstance(signals, list)
    
    def test_rsi_with_gaps(self):
        """Test RSI calculation with price gaps."""
        strategy = RSIMeanReversionStrategy()
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=50, freq='D')
        prices = [100] * 50
        
        # Introduce gaps
        prices[10] = 120  # +20% gap up
        prices[20] = 80   # -33% gap down
        prices[30] = 110  # +37.5% gap up
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': [p * 1.01 for p in prices],
            'low': [p * 0.99 for p in prices],
            'open': prices,
            'volume': [1000000] * 50,
        })
        
        regime = MarketRegime(
            timestamp=datetime.now(),
            trend=TrendRegime.CHOPPY,
            momentum_enabled=False,
        )
        
        # Should handle gaps without crashing
        signals = strategy.generate_signals("TEST", bars, current_regime=regime)
        assert isinstance(signals, list)


class TestStrategyValidation:
    """Test strategy validation and error handling."""
    
    def test_empty_bars(self):
        """Test handling of empty bars DataFrame."""
        strategy = EMACrossoverStrategy()
        
        bars = pd.DataFrame()
        
        regime = MarketRegime(
            timestamp=datetime.now(),
            trend=TrendRegime.STRONG_TREND,
            momentum_enabled=True,
        )
        
        signals = strategy.generate_signals("TEST", bars, current_regime=regime)
        
        # Should return empty list
        assert signals == []
    
    def test_missing_columns(self):
        """Test handling of missing required columns."""
        strategy = EMACrossoverStrategy()
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=50, freq='D')
        
        # Missing 'close' column
        bars = pd.DataFrame({
            'timestamp': dates,
            'open': [100] * 50,
            'volume': [1000000] * 50,
        })
        
        regime = MarketRegime(
            timestamp=datetime.now(),
            trend=TrendRegime.STRONG_TREND,
            momentum_enabled=True,
        )
        
        # Should either handle gracefully or raise appropriate error
        try:
            signals = strategy.generate_signals("TEST", bars, current_regime=regime)
            assert isinstance(signals, list)
        except (KeyError, ValueError):
            # Acceptable to reject invalid data
            pass
    
    def test_signal_confidence_range(self):
        """Test that signal confidence is in valid range [0, 1]."""
        strategy = EMACrossoverStrategy()
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=50, freq='D')
        prices = np.linspace(90, 110, 50)
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'open': prices,
            'volume': [1000000] * 50,
        })
        
        regime = MarketRegime(
            timestamp=datetime.now(),
            trend=TrendRegime.STRONG_TREND,
            momentum_enabled=True,
        )
        
        signals = strategy.generate_signals("TEST", bars, current_regime=regime)
        
        for signal in signals:
            assert 0.0 <= signal.confidence <= 1.0, f"Invalid confidence: {signal.confidence}"
    
    def test_signal_has_required_fields(self):
        """Test that all signals have required fields."""
        strategy = EMACrossoverStrategy()
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=50, freq='D')
        prices = np.linspace(90, 110, 50)
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'open': prices,
            'volume': [1000000] * 50,
        })
        
        regime = MarketRegime(
            timestamp=datetime.now(),
            trend=TrendRegime.STRONG_TREND,
            momentum_enabled=True,
        )
        
        signals = strategy.generate_signals("TEST", bars, current_regime=regime)
        
        for signal in signals:
            # Check required fields
            assert signal.symbol is not None
            assert signal.signal_type is not None
            assert signal.timestamp is not None
            assert signal.strategy_name is not None
            assert signal.signal_id is not None
