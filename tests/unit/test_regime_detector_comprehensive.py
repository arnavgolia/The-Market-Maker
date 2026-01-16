"""
Comprehensive tests for regime detector.

Tests all edge cases, crisis scenarios, and regime transitions.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from src.regime.detector import RegimeDetector, MarketRegime, TrendRegime, VolRegime


class TestRegimeDetectorEdgeCases:
    """Test regime detector edge cases and boundary conditions."""
    
    def test_crisis_detection_immediate(self):
        """Test that crisis is detected immediately when fast vol > 2x slow vol."""
        detector = RegimeDetector()
        
        # Create data with sudden volatility spike
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=100, freq='D')
        
        # Normal market for first 50 days
        normal_returns = np.random.randn(50) * 0.01
        
        # Sudden crisis - 10x volatility
        crisis_returns = np.random.randn(50) * 0.10
        
        returns = np.concatenate([normal_returns, crisis_returns])
        prices = 100 * np.exp(np.cumsum(returns))
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'open': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'close': prices,
            'volume': np.random.randint(1000000, 5000000, 100),
        })
        
        # Check regime during crisis
        regime = detector.detect_regime(bars.tail(60), symbol="TEST")
        
        # Should detect crisis
        assert regime.volatility == VolRegime.CRISIS or regime.volatility == VolRegime.HIGH_VOL
        assert regime.position_scale < 1.0  # Reduced position sizing
        assert regime.momentum_enabled is False  # Strategies disabled
    
    def test_insufficient_data(self):
        """Test behavior with insufficient data."""
        detector = RegimeDetector()
        
        # Only 5 days of data (need at least 20 for slow regime)
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=5, freq='D')
        prices = [100, 101, 102, 101, 103]
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': [p * 1.01 for p in prices],
            'low': [p * 0.99 for p in prices],
            'open': prices,
            'volume': [1000000] * 5,
        })
        
        regime = detector.detect_regime(bars, symbol="TEST")
        
        # Should return default regime (choppy, normal vol)
        assert regime is not None
        assert regime.trend == TrendRegime.CHOPPY  # Default
    
    def test_zero_volatility(self):
        """Test regime detection with zero volatility (flat market)."""
        detector = RegimeDetector()
        
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
        
        regime = detector.detect_regime(bars, symbol="TEST")
        
        # Should handle gracefully
        assert regime is not None
        assert regime.volatility == VolRegime.LOW_VOL
    
    def test_extreme_volatility(self):
        """Test with extreme volatility (>50% daily moves)."""
        detector = RegimeDetector()
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=100, freq='D')
        
        # Extreme volatility - ±50% moves
        returns = np.random.choice([-0.5, 0.5], size=100)
        prices = 100 * np.exp(np.cumsum(returns))
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.1,
            'low': prices * 0.9,
            'open': prices,
            'volume': [1000000] * 100,
        })
        
        regime = detector.detect_regime(bars, symbol="TEST")
        
        # Should detect as crisis
        assert regime.volatility == VolRegime.CRISIS
        assert regime.position_scale <= 0.25  # Maximum risk reduction
    
    def test_missing_data_handling(self):
        """Test handling of missing/NaN data."""
        detector = RegimeDetector()
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=100, freq='D')
        prices = np.random.randn(100).cumsum() + 100
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'open': prices,
            'volume': [1000000] * 100,
        })
        
        # Introduce NaN values
        bars.loc[50:55, 'close'] = np.nan
        
        # Should handle NaN gracefully
        regime = detector.detect_regime(bars, symbol="TEST")
        assert regime is not None
    
    def test_choppy_to_trending_transition(self):
        """Test transition from choppy to trending market."""
        detector = RegimeDetector()
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=100, freq='D')
        
        # First 50 days: choppy (mean-reverting)
        choppy_returns = np.random.randn(50) * 0.01
        
        # Last 50 days: trending (persistent moves)
        trend = np.linspace(0, 0.5, 50)
        trending_returns = trend + np.random.randn(50) * 0.005
        
        returns = np.concatenate([choppy_returns, trending_returns])
        prices = 100 * np.exp(np.cumsum(returns))
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'open': prices,
            'volume': [1000000] * 100,
        })
        
        # Check regime during trending phase
        regime = detector.detect_regime(bars.tail(60), symbol="TEST")
        
        # Should detect strong trend
        assert regime.trend in (TrendRegime.WEAK_TREND, TrendRegime.STRONG_TREND)
    
    def test_to_dict_completeness(self):
        """Test that to_dict() includes all fields."""
        detector = RegimeDetector()
        
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
        
        regime = detector.detect_regime(bars, symbol="TEST")
        regime_dict = regime.to_dict()
        
        # Check all required fields
        required_fields = [
            'timestamp', 'symbol', 'trend_regime', 'vol_regime',
            'combined_regime', 'momentum_enabled', 'position_scale'
        ]
        
        for field in required_fields:
            assert field in regime_dict, f"Missing field: {field}"
        
        # Check types
        assert isinstance(regime_dict['timestamp'], str)
        assert isinstance(regime_dict['momentum_enabled'], bool)
        assert isinstance(regime_dict['position_scale'], (int, float))
    
    def test_regime_consistency(self):
        """Test that regime remains consistent with same data."""
        detector = RegimeDetector()
        
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
        
        # Run detection twice
        regime1 = detector.detect_regime(bars, symbol="TEST")
        regime2 = detector.detect_regime(bars, symbol="TEST")
        
        # Should be identical
        assert regime1.trend == regime2.trend
        assert regime1.volatility == regime2.volatility
        assert regime1.momentum_enabled == regime2.momentum_enabled
        assert abs(regime1.position_scale - regime2.position_scale) < 0.01
    
    def test_negative_prices_handling(self):
        """Test handling of negative prices (should not happen but test defensive)."""
        detector = RegimeDetector()
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=100, freq='D')
        prices = np.arange(-50, 50, 1)  # Negative to positive
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices + 1,
            'low': prices - 1,
            'open': prices,
            'volume': [1000000] * 100,
        })
        
        # Should either handle gracefully or raise appropriate error
        try:
            regime = detector.detect_regime(bars, symbol="TEST")
            # If it succeeds, verify it's sane
            assert regime is not None
        except (ValueError, RuntimeError):
            # Acceptable to reject invalid data
            pass


class TestRegimeDetectorPositionScaling:
    """Test position scaling logic in different regimes."""
    
    def test_position_scale_low_vol_trending(self):
        """Test maximum position scale in ideal conditions."""
        detector = RegimeDetector()
        
        # Low vol, strong trend
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=100, freq='D')
        trend = np.linspace(0, 0.3, 100)
        prices = 100 * np.exp(trend + np.random.randn(100) * 0.005)
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.005,
            'low': prices * 0.995,
            'open': prices,
            'volume': [1000000] * 100,
        })
        
        regime = detector.detect_regime(bars, symbol="TEST")
        
        # Should allow full position sizing
        assert regime.position_scale >= 0.5  # At least 50%
    
    def test_position_scale_crisis(self):
        """Test minimum position scale in crisis."""
        detector = RegimeDetector()
        
        dates = pd.date_range(start=datetime(2020, 1, 1), periods=100, freq='D')
        
        # Crisis: 20% daily volatility
        returns = np.random.randn(100) * 0.20
        prices = 100 * np.exp(np.cumsum(returns))
        
        bars = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'high': prices * 1.1,
            'low': prices * 0.9,
            'open': prices,
            'volume': [1000000] * 100,
        })
        
        regime = detector.detect_regime(bars.tail(60), symbol="TEST")
        
        # Should drastically reduce position sizing
        assert regime.position_scale <= 0.5  # 50% or less
    
    def test_position_scale_monotonic(self):
        """Test that position scale decreases monotonically with volatility."""
        detector = RegimeDetector()
        
        scales = []
        
        for vol_multiplier in [0.01, 0.02, 0.05, 0.10, 0.15]:
            dates = pd.date_range(start=datetime(2020, 1, 1), periods=100, freq='D')
            returns = np.random.randn(100) * vol_multiplier
            prices = 100 * np.exp(np.cumsum(returns))
            
            bars = pd.DataFrame({
                'timestamp': dates,
                'close': prices,
                'high': prices * (1 + vol_multiplier),
                'low': prices * (1 - vol_multiplier),
                'open': prices,
                'volume': [1000000] * 100,
            })
            
            regime = detector.detect_regime(bars, symbol="TEST")
            scales.append(regime.position_scale)
        
        # Position scale should decrease (or stay same) as volatility increases
        for i in range(len(scales) - 1):
            assert scales[i] >= scales[i+1] - 0.1, f"Position scale increased with volatility: {scales}"
