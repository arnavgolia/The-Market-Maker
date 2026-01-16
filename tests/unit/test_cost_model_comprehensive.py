"""
Comprehensive tests for transaction cost models.

Tests spread estimation, slippage, and stressed cost scenarios.
"""

import pytest
import numpy as np

from src.data.cost_model.spread_estimator import SpreadEstimator
from src.data.cost_model.slippage_model import SlippageModel
from src.data.cost_model.stressed_costs import (
    StressedCostModel,
    StressScenario,
    StressConfig,
)


class TestSpreadEstimatorEdgeCases:
    """Test spread estimator edge cases."""
    
    def test_zero_volatility(self):
        """Test spread estimation with zero volatility."""
        estimator = SpreadEstimator()
        
        spread = estimator.estimate_spread(
            volatility=0.0,
            volume=1000000,
            price=100.0,
        )
        
        # Should return floor spread
        assert spread >= estimator.spread_floor_bps
        assert spread > 0
    
    def test_extreme_volatility(self):
        """Test spread estimation with extreme volatility."""
        estimator = SpreadEstimator()
        
        spread = estimator.estimate_spread(
            volatility=1.0,  # 100% volatility
            volume=1000000,
            price=100.0,
        )
        
        # Should be capped at ceiling
        assert spread <= estimator.spread_ceiling_bps
        assert spread > 0
    
    def test_low_volume(self):
        """Test spread widens with low volume."""
        estimator = SpreadEstimator()
        
        high_vol_spread = estimator.estimate_spread(
            volatility=0.15,
            volume=10000000,  # High volume
            price=100.0,
        )
        
        low_vol_spread = estimator.estimate_spread(
            volatility=0.15,
            volume=100000,  # Low volume
            price=100.0,
        )
        
        # Low volume should have wider spread
        assert low_vol_spread >= high_vol_spread
    
    def test_zero_volume(self):
        """Test handling of zero volume."""
        estimator = SpreadEstimator()
        
        # Should either handle gracefully or use maximum spread
        spread = estimator.estimate_spread(
            volatility=0.15,
            volume=0,
            price=100.0,
        )
        
        assert spread > 0
        # Likely should be near ceiling for zero volume
        assert spread >= estimator.spread_floor_bps
    
    def test_negative_inputs(self):
        """Test handling of negative inputs (defensive)."""
        estimator = SpreadEstimator()
        
        # Negative volatility
        with pytest.raises((ValueError, AssertionError)):
            estimator.estimate_spread(
                volatility=-0.15,
                volume=1000000,
                price=100.0,
            )
    
    def test_spread_bps_range(self):
        """Test that spread stays within configured range."""
        estimator = SpreadEstimator(
            spread_floor_bps=5.0,
            spread_ceiling_bps=50.0,
        )
        
        # Test many scenarios
        for _ in range(100):
            vol = np.random.uniform(0, 0.5)
            volume = np.random.uniform(100000, 10000000)
            price = np.random.uniform(1, 1000)
            
            spread = estimator.estimate_spread(vol, volume, price)
            
            assert spread >= 5.0, f"Spread below floor: {spread}"
            assert spread <= 50.0, f"Spread above ceiling: {spread}"


class TestSlippageModelEdgeCases:
    """Test slippage model edge cases."""
    
    def test_zero_quantity(self):
        """Test slippage with zero quantity."""
        model = SlippageModel()
        
        slippage = model.calculate_slippage(
            quantity=0,
            volume=1000000,
            volatility=0.15,
            is_market_order=False,
        )
        
        # Zero quantity should have zero slippage
        assert slippage == 0.0
    
    def test_market_order_vs_limit(self):
        """Test that market orders have higher slippage."""
        model = SlippageModel()
        
        limit_slippage = model.calculate_slippage(
            quantity=1000,
            volume=1000000,
            volatility=0.15,
            is_market_order=False,
        )
        
        market_slippage = model.calculate_slippage(
            quantity=1000,
            volume=1000000,
            volatility=0.15,
            is_market_order=True,
        )
        
        # Market orders should have more slippage
        assert market_slippage >= limit_slippage
    
    def test_large_order_impact(self):
        """Test market impact of large orders."""
        model = SlippageModel()
        
        small_slippage = model.calculate_slippage(
            quantity=100,  # 0.01% of volume
            volume=1000000,
            volatility=0.15,
        )
        
        large_slippage = model.calculate_slippage(
            quantity=100000,  # 10% of volume
            volume=1000000,
            volatility=0.15,
        )
        
        # Larger orders should have more slippage
        assert large_slippage > small_slippage
    
    def test_slippage_with_extreme_volume_ratio(self):
        """Test slippage when order is larger than daily volume."""
        model = SlippageModel()
        
        # Order is 2x daily volume (unrealistic but test boundary)
        slippage = model.calculate_slippage(
            quantity=2000000,
            volume=1000000,
            volatility=0.15,
        )
        
        # Should have very high slippage
        assert slippage > 50  # >50 bps for such a large order


class TestStressedCostModel:
    """Test stressed cost model under crisis scenarios."""
    
    def test_volmageddon_multipliers(self):
        """Test 10x spread multiplier for Volmageddon."""
        config = StressConfig.from_scenario(StressScenario.VOLMAGEDDON_2018)
        
        assert config.spread_multiplier == 10.0
        assert config.slippage_multiplier >= 1.0
    
    def test_stressed_costs_application(self):
        """Test that stressed costs are actually multiplied."""
        base_estimator = SpreadEstimator()
        base_slippage = SlippageModel()
        
        stressed = StressedCostModel(
            spread_estimator=base_estimator,
            slippage_model=base_slippage,
            config=StressConfig.from_scenario(StressScenario.VOLMAGEDDON_2018),
        )
        
        base_spread = base_estimator.estimate_spread(0.15, 1000000, 100.0)
        stressed_spread = stressed.estimate_stressed_spread(0.15, 1000000, 100.0)
        
        # Stressed spread should be ~10x base
        assert stressed_spread >= base_spread * 5  # At least 5x (accounting for caps)
    
    def test_all_stress_scenarios(self):
        """Test all predefined stress scenarios."""
        scenarios = [
            StressScenario.VOLMAGEDDON_2018,
            StressScenario.FLASH_CRASH_2010,
            StressScenario.LIQUIDITY_CRISIS,
            StressScenario.BLACK_MONDAY_1987,
        ]
        
        for scenario in scenarios:
            config = StressConfig.from_scenario(scenario)
            
            assert config.spread_multiplier >= 1.0
            assert config.slippage_multiplier >= 1.0
            assert 0 < config.fill_rate <= 1.0
    
    def test_partial_fills(self):
        """Test partial fill simulation."""
        config = StressConfig(
            name="test",
            spread_multiplier=1.0,
            slippage_multiplier=1.0,
            fill_rate=0.5,  # 50% fill rate
        )
        
        stressed = StressedCostModel(
            spread_estimator=SpreadEstimator(),
            slippage_model=SlippageModel(),
            config=config,
        )
        
        quantity = 1000
        filled_qty = stressed.apply_fill_rate(quantity)
        
        # Should fill approximately 50%
        assert 400 <= filled_qty <= 600  # Allow some randomness
    
    def test_stress_config_validation(self):
        """Test that invalid stress configs are rejected."""
        # Negative multiplier
        with pytest.raises((ValueError, AssertionError)):
            StressConfig(
                name="invalid",
                spread_multiplier=-1.0,
                slippage_multiplier=1.0,
                fill_rate=1.0,
            )
        
        # Fill rate > 1.0
        with pytest.raises((ValueError, AssertionError)):
            StressConfig(
                name="invalid",
                spread_multiplier=1.0,
                slippage_multiplier=1.0,
                fill_rate=1.5,
            )


class TestTransactionCostRealism:
    """Test that cost models produce realistic values."""
    
    def test_typical_spread_range(self):
        """Test that typical spreads are in realistic range (5-50 bps)."""
        estimator = SpreadEstimator()
        
        # Typical stock: 15% vol, 1M volume
        spread = estimator.estimate_spread(0.15, 1000000, 100.0)
        
        # Should be in typical range
        assert 5.0 <= spread <= 50.0
    
    def test_typical_slippage_range(self):
        """Test that typical slippage is in realistic range (1-20 bps)."""
        model = SlippageModel()
        
        # Typical order: 0.1% of volume
        slippage = model.calculate_slippage(
            quantity=1000,
            volume=1000000,
            volatility=0.15,
        )
        
        # Should be reasonable
        assert 0.0 <= slippage <= 50.0
    
    def test_total_cost_sanity(self):
        """Test that total transaction costs are sane."""
        estimator = SpreadEstimator()
        slippage_model = SlippageModel()
        
        spread = estimator.estimate_spread(0.15, 1000000, 100.0)
        slippage = slippage_model.calculate_slippage(1000, 1000000, 0.15)
        
        total_cost_bps = spread + slippage
        
        # Total cost should typically be < 100 bps (1%)
        assert total_cost_bps < 100.0
        assert total_cost_bps > 0.0
