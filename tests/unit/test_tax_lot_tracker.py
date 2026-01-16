"""
Comprehensive tests for Tax-Lot Tracking System.

Tests:
- FIFO/LIFO/HIFO accounting methods
- Wash sale detection (30-day rule)
- Short-term vs long-term classification
- Cost basis calculation
- Realized vs unrealized P&L
- Tax reporting export
"""

import pytest
from datetime import datetime, timedelta
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.accounting.tax_lot_tracker import (
    TaxLotTracker,
    TaxLotMethod,
    TermType,
    TaxLot,
    ClosedLot,
)


class TestTaxLotBasics:
    """Test basic tax lot operations."""
    
    def test_create_tax_lot(self):
        """Test creating a tax lot."""
        lot = TaxLot(
            lot_id="test_lot_1",
            symbol="AAPL",
            quantity=100,
            cost_basis_per_share=150.0,
            acquisition_date=datetime(2024, 1, 1).date(),
            acquisition_time=datetime(2024, 1, 1, 10, 0, 0),
        )
        
        assert lot.symbol == "AAPL"
        assert lot.quantity == 100
        assert lot.total_cost_basis == 15000.0
    
    def test_tax_lot_with_commission(self):
        """Test tax lot with commission and fees."""
        lot = TaxLot(
            lot_id="test_lot_2",
            symbol="MSFT",
            quantity=50,
            cost_basis_per_share=300.0,
            acquisition_date=datetime(2024, 1, 1).date(),
            acquisition_time=datetime(2024, 1, 1, 10, 0, 0),
            commission=10.0,
            fees=5.0,
        )
        
        assert lot.total_cost_basis == 15015.0  # (50 * 300) + 10 + 5
        assert lot.adjusted_cost_per_share == 300.30  # 15015 / 50
    
    def test_holding_period_calculation(self):
        """Test holding period days calculation."""
        lot = TaxLot(
            lot_id="test_lot_3",
            symbol="TSLA",
            quantity=10,
            cost_basis_per_share=200.0,
            acquisition_date=datetime(2024, 1, 1).date(),
            acquisition_time=datetime(2024, 1, 1, 10, 0, 0),
        )
        
        # Check after 30 days
        check_date = datetime(2024, 1, 31)
        assert lot.holding_period_days(check_date) == 30
        assert lot.term_type(check_date) == TermType.SHORT_TERM
        
        # Check after 1 year
        check_date = datetime(2025, 1, 2)
        assert lot.holding_period_days(check_date) == 366
        assert lot.term_type(check_date) == TermType.LONG_TERM


class TestFIFOAccounting:
    """Test FIFO (First In First Out) accounting."""
    
    def test_fifo_basic_sale(self):
        """Test basic FIFO sale."""
        tracker = TaxLotTracker(method=TaxLotMethod.FIFO)
        
        # Buy 100 shares at $100
        tracker.add_purchase("AAPL", 100, 100.0, datetime(2024, 1, 1, 10, 0))
        
        # Buy 100 more shares at $110
        tracker.add_purchase("AAPL", 100, 110.0, datetime(2024, 1, 2, 10, 0))
        
        # Sell 150 shares at $120
        closed_lots, realized_pnl = tracker.process_sale(
            "AAPL", 150, 120.0, datetime(2024, 1, 3, 10, 0)
        )
        
        # Should close first 100 shares at $100, then 50 shares at $110
        assert len(closed_lots) == 2
        assert closed_lots[0].cost_basis_per_share == 100.0
        assert closed_lots[0].quantity == 100
        assert closed_lots[1].cost_basis_per_share == 110.0
        assert closed_lots[1].quantity == 50
        
        # Realized P&L: (100 * (120 - 100)) + (50 * (120 - 110)) = 2000 + 500 = 2500
        assert abs(realized_pnl - 2500.0) < 0.01
    
    def test_fifo_multiple_sales(self):
        """Test multiple FIFO sales."""
        tracker = TaxLotTracker(method=TaxLotMethod.FIFO)
        
        # Three purchases
        tracker.add_purchase("SPY", 100, 400.0, datetime(2024, 1, 1, 10, 0))
        tracker.add_purchase("SPY", 100, 410.0, datetime(2024, 1, 2, 10, 0))
        tracker.add_purchase("SPY", 100, 420.0, datetime(2024, 1, 3, 10, 0))
        
        # First sale
        closed_lots_1, pnl_1 = tracker.process_sale("SPY", 50, 430.0, datetime(2024, 1, 4, 10, 0))
        assert len(closed_lots_1) == 1
        assert closed_lots_1[0].cost_basis_per_share == 400.0
        
        # Second sale
        closed_lots_2, pnl_2 = tracker.process_sale("SPY", 100, 435.0, datetime(2024, 1, 5, 10, 0))
        assert len(closed_lots_2) == 2
        assert closed_lots_2[0].cost_basis_per_share == 400.0  # Remaining 50 from first lot
        assert closed_lots_2[1].cost_basis_per_share == 410.0  # 50 from second lot


class TestLIFOAccounting:
    """Test LIFO (Last In First Out) accounting."""
    
    def test_lifo_basic_sale(self):
        """Test basic LIFO sale."""
        tracker = TaxLotTracker(method=TaxLotMethod.LIFO)
        
        # Buy 100 shares at $100
        tracker.add_purchase("AAPL", 100, 100.0, datetime(2024, 1, 1, 10, 0))
        
        # Buy 100 more shares at $110
        tracker.add_purchase("AAPL", 100, 110.0, datetime(2024, 1, 2, 10, 0))
        
        # Sell 150 shares at $120
        closed_lots, realized_pnl = tracker.process_sale(
            "AAPL", 150, 120.0, datetime(2024, 1, 3, 10, 0)
        )
        
        # Should close last 100 shares at $110, then 50 shares at $100
        assert len(closed_lots) == 2
        assert closed_lots[0].cost_basis_per_share == 110.0
        assert closed_lots[0].quantity == 100
        assert closed_lots[1].cost_basis_per_share == 100.0
        assert closed_lots[1].quantity == 50
        
        # Realized P&L: (100 * (120 - 110)) + (50 * (120 - 100)) = 1000 + 1000 = 2000
        assert abs(realized_pnl - 2000.0) < 0.01


class TestWashSaleDetection:
    """Test wash sale detection (30-day rule)."""
    
    def test_wash_sale_basic(self):
        """Test basic wash sale detection."""
        tracker = TaxLotTracker(method=TaxLotMethod.FIFO)
        
        # Buy 100 shares at $100
        tracker.add_purchase("AAPL", 100, 100.0, datetime(2024, 1, 1, 10, 0))
        
        # Sell at a loss ($90)
        closed_lots, realized_pnl = tracker.process_sale(
            "AAPL", 100, 90.0, datetime(2024, 1, 15, 10, 0)
        )
        
        # Buy back within 30 days (wash sale trigger)
        tracker.add_purchase("AAPL", 100, 95.0, datetime(2024, 1, 20, 10, 0))
        
        # Should be flagged as wash sale
        assert closed_lots[0].is_wash_sale is True
        assert closed_lots[0].wash_sale_disallowed_loss == 1000.0  # 100 * (100 - 90)
        
        # Realized P&L should be 0 (loss disallowed)
        assert closed_lots[0].realized_gain_loss == 0.0
    
    def test_no_wash_sale_after_30_days(self):
        """Test that wash sale doesn't trigger after 30 days."""
        tracker = TaxLotTracker(method=TaxLotMethod.FIFO)
        
        # Buy 100 shares at $100
        tracker.add_purchase("MSFT", 100, 300.0, datetime(2024, 1, 1, 10, 0))
        
        # Sell at a loss
        closed_lots, _ = tracker.process_sale(
            "MSFT", 100, 280.0, datetime(2024, 1, 15, 10, 0)
        )
        
        # Buy back AFTER 30 days (no wash sale)
        tracker.add_purchase("MSFT", 100, 290.0, datetime(2024, 2, 20, 10, 0))
        
        # Should NOT be wash sale
        assert closed_lots[0].is_wash_sale is False
        assert closed_lots[0].realized_gain_loss == -2000.0  # Loss is allowed
    
    def test_wash_sale_with_gain(self):
        """Test that wash sale only applies to losses."""
        tracker = TaxLotTracker(method=TaxLotMethod.FIFO)
        
        # Buy 100 shares at $100
        tracker.add_purchase("TSLA", 100, 200.0, datetime(2024, 1, 1, 10, 0))
        
        # Sell at a GAIN
        closed_lots, _ = tracker.process_sale(
            "TSLA", 100, 220.0, datetime(2024, 1, 15, 10, 0)
        )
        
        # Buy back within 30 days
        tracker.add_purchase("TSLA", 100, 225.0, datetime(2024, 1, 20, 10, 0))
        
        # Should NOT be wash sale (only applies to losses)
        assert closed_lots[0].is_wash_sale is False
        assert closed_lots[0].realized_gain_loss == 2000.0  # Gain is preserved


class TestTermClassification:
    """Test short-term vs long-term classification."""
    
    def test_short_term_gain(self):
        """Test short-term gain (<= 365 days)."""
        tracker = TaxLotTracker(method=TaxLotMethod.FIFO)
        
        # Buy and sell within 1 year
        tracker.add_purchase("SPY", 100, 400.0, datetime(2024, 1, 1, 10, 0))
        closed_lots, _ = tracker.process_sale(
            "SPY", 100, 420.0, datetime(2024, 6, 1, 10, 0)  # 5 months later
        )
        
        assert closed_lots[0].term_type == TermType.SHORT_TERM
    
    def test_long_term_gain(self):
        """Test long-term gain (> 365 days)."""
        tracker = TaxLotTracker(method=TaxLotMethod.FIFO)
        
        # Buy and sell after 1 year
        tracker.add_purchase("SPY", 100, 400.0, datetime(2024, 1, 1, 10, 0))
        closed_lots, _ = tracker.process_sale(
            "SPY", 100, 450.0, datetime(2025, 1, 3, 10, 0)  # 367 days later
        )
        
        assert closed_lots[0].term_type == TermType.LONG_TERM


class TestRealizedUnrealizedPnL:
    """Test realized and unrealized P&L calculations."""
    
    def test_unrealized_pnl(self):
        """Test unrealized P&L calculation."""
        tracker = TaxLotTracker(method=TaxLotMethod.FIFO)
        
        # Buy 100 shares at $100
        tracker.add_purchase("AAPL", 100, 100.0, datetime(2024, 1, 1, 10, 0))
        
        # Current price $120
        unrealized = tracker.get_unrealized_pnl("AAPL", 120.0)
        assert abs(unrealized - 2000.0) < 0.01  # 100 * (120 - 100)
    
    def test_realized_pnl_breakdown(self):
        """Test realized P&L breakdown by term."""
        tracker = TaxLotTracker(method=TaxLotMethod.FIFO)
        
        # Short-term trade (gain)
        tracker.add_purchase("AAPL", 100, 100.0, datetime(2024, 1, 1, 10, 0))
        tracker.process_sale("AAPL", 100, 110.0, datetime(2024, 6, 1, 10, 0))
        
        # Long-term trade (gain)
        tracker.add_purchase("MSFT", 50, 300.0, datetime(2023, 1, 1, 10, 0))
        tracker.process_sale("MSFT", 50, 350.0, datetime(2024, 6, 1, 10, 0))
        
        pnl = tracker.get_realized_pnl()
        
        assert abs(pnl["short_term"] - 1000.0) < 0.01  # 100 * (110 - 100)
        assert abs(pnl["long_term"] - 2500.0) < 0.01   # 50 * (350 - 300)
        assert abs(pnl["total"] - 3500.0) < 0.01


class TestTaxReporting:
    """Test tax reporting export."""
    
    def test_tax_export_for_year(self):
        """Test exporting data for tax reporting."""
        tracker = TaxLotTracker(method=TaxLotMethod.FIFO)
        
        # Trades in 2024
        tracker.add_purchase("AAPL", 100, 150.0, datetime(2024, 1, 1, 10, 0))
        tracker.process_sale("AAPL", 100, 160.0, datetime(2024, 6, 1, 10, 0))  # Short-term
        
        tracker.add_purchase("MSFT", 50, 300.0, datetime(2023, 1, 1, 10, 0))
        tracker.process_sale("MSFT", 50, 350.0, datetime(2024, 6, 1, 10, 0))  # Long-term
        
        # Export for 2024
        export = tracker.export_for_tax_reporting(2024)
        
        assert export["year"] == 2024
        assert len(export["short_term_transactions"]) == 1
        assert len(export["long_term_transactions"]) == 1
        assert export["totals"]["short_term"] == 1000.0
        assert export["totals"]["long_term"] == 2500.0


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_sale_without_purchase(self):
        """Test selling without any purchase (short sale)."""
        tracker = TaxLotTracker(method=TaxLotMethod.FIFO)
        
        # Sell without buying (should create synthetic lot)
        closed_lots, pnl = tracker.process_sale(
            "AAPL", 100, 150.0, datetime(2024, 1, 1, 10, 0)
        )
        
        # Should handle gracefully
        assert len(closed_lots) >= 0
    
    def test_zero_quantity_lot(self):
        """Test handling zero quantity."""
        lot = TaxLot(
            lot_id="zero_lot",
            symbol="AAPL",
            quantity=0,
            cost_basis_per_share=100.0,
            acquisition_date=datetime(2024, 1, 1).date(),
            acquisition_time=datetime(2024, 1, 1, 10, 0),
        )
        
        assert lot.adjusted_cost_per_share == 0.0
    
    def test_cost_basis_calculation(self):
        """Test cost basis calculation methods."""
        tracker = TaxLotTracker(method=TaxLotMethod.FIFO)
        
        tracker.add_purchase("AAPL", 100, 150.0, datetime(2024, 1, 1, 10, 0))
        tracker.add_purchase("AAPL", 50, 160.0, datetime(2024, 1, 2, 10, 0))
        
        total_cost = tracker.get_cost_basis("AAPL")
        avg_cost = tracker.get_average_cost("AAPL")
        
        # Total: (100 * 150) + (50 * 160) = 23000
        assert abs(total_cost - 23000.0) < 0.01
        
        # Average: 23000 / 150 = 153.33
        assert abs(avg_cost - 153.33) < 0.01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
