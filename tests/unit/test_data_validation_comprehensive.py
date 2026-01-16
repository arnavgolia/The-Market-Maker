"""
Comprehensive data validation tests.

Tests data tier system, quality checks, and validation logic.
"""

import pytest
from datetime import datetime

from src.data.tiers import (
    DataTier,
    DataQuality,
    Bar,
    DataPoint,
    validate_data_for_backtest,
    TieredDataQuality,
)


class TestDataTierSystem:
    """Test data tier classification and validation."""
    
    def test_tier_hierarchy(self):
        """Test that tiers are properly ordered."""
        assert DataTier.TIER_0_UNIVERSE.value < DataTier.TIER_1_VALIDATION.value
        assert DataTier.TIER_1_VALIDATION.value < DataTier.TIER_2_SPREAD_MODEL.value
        assert DataTier.TIER_2_SPREAD_MODEL.value < DataTier.TIER_3_LIVE.value
    
    def test_yfinance_is_tier0(self):
        """Test that yfinance data is classified as TIER_0."""
        bar = Bar.from_yfinance(
            symbol="TEST",
            timestamp=datetime(2020, 1, 1),
            open_=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000000,
            adjusted_close=100.5,
        )
        
        assert bar.tier == DataTier.TIER_0_UNIVERSE
        assert bar.quality.survivorship_bias is True
        assert bar.quality.adjusted_prices is True
    
    def test_alpaca_historical_is_tier1(self):
        """Test that Alpaca historical data is TIER_1."""
        bar = Bar.from_alpaca(
            symbol="TEST",
            timestamp=datetime(2020, 1, 1),
            open_=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000000,
        )
        
        assert bar.tier == DataTier.TIER_1_VALIDATION
        assert bar.quality.survivorship_bias is False
        assert bar.quality.adjusted_prices is False
    
    def test_tier0_not_backtest_valid(self):
        """Test that TIER_0 data is not valid for backtesting."""
        bar = Bar.from_yfinance(
            symbol="TEST",
            timestamp=datetime(2020, 1, 1),
            open_=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000000,
            adjusted_close=100.5,
        )
        
        assert not bar.is_backtest_valid()
    
    def test_tier1_is_backtest_valid(self):
        """Test that TIER_1 data is valid for backtesting."""
        bar = Bar.from_alpaca(
            symbol="TEST",
            timestamp=datetime(2020, 1, 1),
            open_=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000000,
        )
        
        assert bar.is_backtest_valid()
    
    def test_validate_backtest_data_rejects_tier0(self):
        """Test that validation rejects TIER_0 data."""
        bars = [
            Bar.from_yfinance(
                symbol="TEST",
                timestamp=datetime(2020, 1, i),
                open_=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1000000,
                adjusted_close=100.5,
            )
            for i in range(1, 11)
        ]
        
        with pytest.raises(ValueError, match="TIER_0"):
            validate_data_for_backtest(bars)
    
    def test_validate_backtest_data_accepts_tier1(self):
        """Test that validation accepts TIER_1 data."""
        bars = [
            Bar.from_alpaca(
                symbol="TEST",
                timestamp=datetime(2020, 1, i),
                open_=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1000000,
            )
            for i in range(1, 11)
        ]
        
        # Should not raise
        result = validate_data_for_backtest(bars)
        assert result is True
    
    def test_validate_mixed_tiers_rejected(self):
        """Test that mixed tier data is rejected."""
        bars = [
            Bar.from_alpaca(
                symbol="TEST",
                timestamp=datetime(2020, 1, i),
                open_=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1000000,
            )
            for i in range(1, 6)
        ]
        
        # Add TIER_0 bar
        bars.append(Bar.from_yfinance(
            symbol="TEST",
            timestamp=datetime(2020, 1, 6),
            open_=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000000,
            adjusted_close=100.5,
        ))
        
        with pytest.raises(ValueError):
            validate_data_for_backtest(bars)
    
    def test_empty_data_validation(self):
        """Test validation with empty data."""
        with pytest.raises(ValueError, match="empty"):
            validate_data_for_backtest([])


class TestDataQualityChecks:
    """Test data quality validation."""
    
    def test_spread_calculation(self):
        """Test bid/ask spread calculation."""
        point = DataPoint(
            symbol="TEST",
            timestamp=datetime(2020, 1, 1),
            price=100.0,
            bid=99.95,
            ask=100.05,
            volume=1000000,
            tier=DataTier.TIER_3_LIVE,
            source="alpaca_live",
            quality=DataQuality(),
        )
        
        spread = point.get_spread_bps()
        
        # (100.05 - 99.95) / 100.0 * 10000 = 10 bps
        assert abs(spread - 10.0) < 0.1
    
    def test_zero_spread(self):
        """Test handling of zero spread."""
        point = DataPoint(
            symbol="TEST",
            timestamp=datetime(2020, 1, 1),
            price=100.0,
            bid=100.0,
            ask=100.0,
            volume=1000000,
            tier=DataTier.TIER_3_LIVE,
            source="test",
            quality=DataQuality(),
        )
        
        spread = point.get_spread_bps()
        
        assert spread == 0.0
    
    def test_negative_spread_invalid(self):
        """Test that negative spread (crossed market) is invalid."""
        point = DataPoint(
            symbol="TEST",
            timestamp=datetime(2020, 1, 1),
            price=100.0,
            bid=100.05,  # Bid > ask (invalid)
            ask=99.95,
            volume=1000000,
            tier=DataTier.TIER_3_LIVE,
            source="test",
            quality=DataQuality(),
        )
        
        spread = point.get_spread_bps()
        
        # Should be negative (crossed market - error condition)
        assert spread < 0
    
    def test_wide_spread_detection(self):
        """Test detection of abnormally wide spreads."""
        point = DataPoint(
            symbol="TEST",
            timestamp=datetime(2020, 1, 1),
            price=100.0,
            bid=95.0,  # 5% wide spread
            ask=105.0,
            volume=1000000,
            tier=DataTier.TIER_3_LIVE,
            source="test",
            quality=DataQuality(),
        )
        
        spread = point.get_spread_bps()
        
        # 10 / 100 * 10000 = 1000 bps = 10%
        assert spread > 500  # > 5%
    
    def test_is_tradeable_with_live_data(self):
        """Test that TIER_3 data with bid/ask is tradeable."""
        point = DataPoint(
            symbol="TEST",
            timestamp=datetime(2020, 1, 1),
            price=100.0,
            bid=99.95,
            ask=100.05,
            volume=1000000,
            tier=DataTier.TIER_3_LIVE,
            source="alpaca_live",
            quality=DataQuality(),
        )
        
        assert point.is_tradeable()
    
    def test_is_not_tradeable_without_bid_ask(self):
        """Test that data without bid/ask is not tradeable."""
        point = DataPoint(
            symbol="TEST",
            timestamp=datetime(2020, 1, 1),
            price=100.0,
            bid=None,
            ask=None,
            volume=1000000,
            tier=DataTier.TIER_1_VALIDATION,
            source="alpaca_historical",
            quality=DataQuality(),
        )
        
        assert not point.is_tradeable()


class TestBarValidation:
    """Test bar-level validation."""
    
    def test_valid_bar_ohlc(self):
        """Test that valid OHLC relationships pass."""
        bar = Bar.from_alpaca(
            symbol="TEST",
            timestamp=datetime(2020, 1, 1),
            open_=100.0,
            high=102.0,
            low=98.0,
            close=101.0,
            volume=1000000,
        )
        
        # High should be highest
        assert bar.high >= bar.open
        assert bar.high >= bar.close
        assert bar.high >= bar.low
        
        # Low should be lowest
        assert bar.low <= bar.open
        assert bar.low <= bar.close
    
    def test_invalid_ohlc_relationships(self):
        """Test detection of invalid OHLC relationships."""
        # High below low (invalid)
        with pytest.raises((ValueError, AssertionError)):
            Bar(
                symbol="TEST",
                timestamp=datetime(2020, 1, 1),
                open=100.0,
                high=98.0,  # High < low (invalid)
                low=99.0,
                close=99.5,
                volume=1000000,
                tier=DataTier.TIER_1_VALIDATION,
                source="test",
                quality=DataQuality(),
            )
    
    def test_zero_volume_bar(self):
        """Test handling of zero volume bar."""
        bar = Bar.from_alpaca(
            symbol="TEST",
            timestamp=datetime(2020, 1, 1),
            open_=100.0,
            high=100.0,
            low=100.0,
            close=100.0,
            volume=0,  # Zero volume
        )
        
        # Should create but flag as potentially suspicious
        assert bar.volume == 0
    
    def test_negative_prices(self):
        """Test that negative prices are rejected."""
        with pytest.raises((ValueError, AssertionError)):
            Bar(
                symbol="TEST",
                timestamp=datetime(2020, 1, 1),
                open=-100.0,  # Negative price
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1000000,
                tier=DataTier.TIER_1_VALIDATION,
                source="test",
                quality=DataQuality(),
            )


class TestTieredDataQuality:
    """Test tiered data quality system."""
    
    def test_reject_tier0_for_backtest(self):
        """Test that TieredDataQuality rejects TIER_0."""
        quality_checker = TieredDataQuality()
        
        bars = [Bar.from_yfinance(
            symbol="TEST",
            timestamp=datetime(2020, 1, 1),
            open_=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000000,
            adjusted_close=100.5,
        )]
        
        assert not quality_checker.is_valid_for_backtest(bars)
    
    def test_accept_tier1_for_backtest(self):
        """Test that TieredDataQuality accepts TIER_1."""
        quality_checker = TieredDataQuality()
        
        bars = [Bar.from_alpaca(
            symbol="TEST",
            timestamp=datetime(2020, 1, 1),
            open_=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000000,
        )]
        
        assert quality_checker.is_valid_for_backtest(bars)
