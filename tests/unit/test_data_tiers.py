"""
Tests for the data tier system.

The tiered data system is critical for preventing the common failure mode
of backtesting on adjusted prices that never existed in reality.
"""

import pytest
from datetime import datetime

from src.data.tiers import (
    DataTier,
    DataQuality,
    DataPoint,
    Bar,
    validate_data_for_backtest,
)


class TestDataTier:
    """Tests for DataTier enum and validation."""
    
    def test_tier_ordering(self):
        """Verify tier enum values exist."""
        assert DataTier.TIER_0_UNIVERSE is not None
        assert DataTier.TIER_1_VALIDATION is not None
        assert DataTier.TIER_2_SPREAD is not None
        assert DataTier.TIER_3_LIVE is not None
    
    def test_tier_distinctness(self):
        """All tiers should be distinct."""
        tiers = [
            DataTier.TIER_0_UNIVERSE,
            DataTier.TIER_1_VALIDATION,
            DataTier.TIER_2_SPREAD,
            DataTier.TIER_3_LIVE,
        ]
        assert len(tiers) == len(set(tiers))


class TestDataPoint:
    """Tests for DataPoint class."""
    
    def test_spread_calculation(self):
        """Test spread calculation from bid/ask."""
        dp = DataPoint(
            symbol="AAPL",
            timestamp=datetime.now(),
            tier=DataTier.TIER_3_LIVE,
            quality=DataQuality.REALTIME,
            price=150.0,
            bid=149.95,
            ask=150.05,
        )
        
        assert dp.spread == pytest.approx(0.10)
        assert dp.spread_bps == pytest.approx(6.67, rel=0.01)
    
    def test_is_tradeable_tier3_realtime(self):
        """Only TIER_3 + REALTIME is tradeable."""
        dp = DataPoint(
            symbol="AAPL",
            timestamp=datetime.now(),
            tier=DataTier.TIER_3_LIVE,
            quality=DataQuality.REALTIME,
            price=150.0,
        )
        assert dp.is_tradeable is True
    
    def test_is_not_tradeable_tier1(self):
        """TIER_1 data is not tradeable."""
        dp = DataPoint(
            symbol="AAPL",
            timestamp=datetime.now(),
            tier=DataTier.TIER_1_VALIDATION,
            quality=DataQuality.DELAYED,
            price=150.0,
        )
        assert dp.is_tradeable is False
    
    def test_tier0_not_backtest_valid(self):
        """TIER_0 data is NEVER valid for backtesting."""
        dp = DataPoint(
            symbol="AAPL",
            timestamp=datetime.now(),
            tier=DataTier.TIER_0_UNIVERSE,
            quality=DataQuality.DELAYED,
            price=150.0,
        )
        assert dp.is_backtest_valid is False
    
    def test_tier1_is_backtest_valid(self):
        """TIER_1 data IS valid for backtesting."""
        dp = DataPoint(
            symbol="AAPL",
            timestamp=datetime.now(),
            tier=DataTier.TIER_1_VALIDATION,
            quality=DataQuality.DELAYED,
            price=150.0,
        )
        assert dp.is_backtest_valid is True


class TestBar:
    """Tests for Bar class."""
    
    def test_from_yfinance_is_tier0(self):
        """Bars from yfinance should be marked as TIER_0."""
        bar = Bar.from_yfinance(
            symbol="AAPL",
            timestamp=datetime.now(),
            open_=150.0,
            high=152.0,
            low=149.0,
            close=151.0,
            volume=1000000,
        )
        
        assert bar.tier == DataTier.TIER_0_UNIVERSE
        assert bar.is_backtest_valid is False
    
    def test_from_alpaca_is_tier1(self):
        """Bars from Alpaca should be marked as TIER_1."""
        bar = Bar.from_alpaca(
            symbol="AAPL",
            timestamp=datetime.now(),
            open_=150.0,
            high=152.0,
            low=149.0,
            close=151.0,
            volume=1000000,
        )
        
        assert bar.tier == DataTier.TIER_1_VALIDATION
        assert bar.is_backtest_valid is True


class TestValidateDataForBacktest:
    """Tests for backtest data validation."""
    
    def test_validates_tier1_data(self):
        """TIER_1 data should pass validation."""
        bars = [
            Bar.from_alpaca(
                symbol="AAPL",
                timestamp=datetime.now(),
                open_=150.0,
                high=152.0,
                low=149.0,
                close=151.0,
                volume=1000000,
            )
            for _ in range(10)
        ]
        
        is_valid, errors = validate_data_for_backtest(bars)
        assert is_valid is True
        assert len(errors) == 0
    
    def test_rejects_tier0_data(self):
        """TIER_0 (yfinance) data should FAIL validation."""
        bars = [
            Bar.from_yfinance(
                symbol="AAPL",
                timestamp=datetime.now(),
                open_=150.0,
                high=152.0,
                low=149.0,
                close=151.0,
                volume=1000000,
            )
            for _ in range(10)
        ]
        
        is_valid, errors = validate_data_for_backtest(bars)
        assert is_valid is False
        assert len(errors) > 0
        assert "TIER_0" in errors[0]
    
    def test_rejects_mixed_data(self):
        """Mixed TIER_0 and TIER_1 data should FAIL validation."""
        bars = [
            Bar.from_alpaca(
                symbol="AAPL",
                timestamp=datetime.now(),
                open_=150.0,
                high=152.0,
                low=149.0,
                close=151.0,
                volume=1000000,
            ),
            Bar.from_yfinance(  # This one is TIER_0 - should fail
                symbol="AAPL",
                timestamp=datetime.now(),
                open_=150.0,
                high=152.0,
                low=149.0,
                close=151.0,
                volume=1000000,
            ),
        ]
        
        is_valid, errors = validate_data_for_backtest(bars)
        assert is_valid is False
    
    def test_empty_data_fails(self):
        """Empty data should fail validation."""
        is_valid, errors = validate_data_for_backtest([])
        assert is_valid is False
