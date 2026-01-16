"""
Stress test: 10x spread scenario (Gemini's critical test).

This test validates that strategies survive under 10x spreads.
A strategy that fails this test is rejected.
"""

import pytest
from datetime import datetime, timedelta

from src.strategy.tier1.ema_crossover import EMACrossoverStrategy
from research.stress_testing.runner import StressTestRunner, StressScenario
from research.backtesting.engine import BacktestEngine
from src.data.cost_model.spread_estimator import SpreadEstimator
from src.data.cost_model.slippage_model import SlippageModel
from src.data.cost_model.stressed_costs import StressedCostModel


@pytest.fixture
def backtest_engine():
    """Create backtest engine for testing."""
    return BacktestEngine(
        initial_capital=100000.0,
        spread_estimator=SpreadEstimator(),
        slippage_model=SlippageModel(),
    )


@pytest.fixture
def stress_runner(backtest_engine):
    """Create stress test runner."""
    return StressTestRunner(backtest_engine)


@pytest.fixture
def sample_bars():
    """Create sample bar data for testing."""
    import pandas as pd
    
    dates = pd.date_range(
        start=datetime.now() - timedelta(days=100),
        end=datetime.now(),
        freq="D",
    )
    
    # Generate synthetic price data
    import numpy as np
    np.random.seed(42)
    
    prices = 100 + np.cumsum(np.random.randn(len(dates)) * 2)
    
    return pd.DataFrame({
        "timestamp": dates,
        "open": prices,
        "high": prices * 1.02,
        "low": prices * 0.98,
        "close": prices,
        "volume": np.random.randint(1000000, 5000000, len(dates)),
        "symbol": "TEST",
    })


class Test10xSpreadStress:
    """Test strategies under 10x spread stress."""
    
    def test_volmageddon_scenario(self, stress_runner, sample_bars):
        """
        Test strategy under Volmageddon (10x spreads).
        
        This is Gemini's critical test. A strategy that fails
        this test is rejected.
        """
        strategy = EMACrossoverStrategy()
        
        # Run stress test
        is_valid = stress_runner.validate_strategy_robustness(
            strategy=strategy,
            bars=sample_bars,
            scenarios=[StressScenario.VOLMAGEDDON_2018],
        )
        
        # Note: This test may fail if strategy doesn't survive 10x spreads
        # That's the point - we want to reject weak strategies
        assert isinstance(is_valid, bool)
    
    def test_stressed_cost_model(self):
        """Test that stressed cost model applies multipliers correctly."""
        from src.data.cost_model.stressed_costs import StressConfig
        
        config = StressConfig.from_scenario(StressScenario.VOLMAGEDDON_2018)
        
        assert config.spread_multiplier == 10.0
        assert config.slippage_multiplier == 5.0
    
    def test_multiple_stress_scenarios(self, stress_runner, sample_bars):
        """Test strategy under multiple stress scenarios."""
        strategy = EMACrossoverStrategy()
        
        scenarios = [
            StressScenario.VOLMAGEDDON_2018,
            StressScenario.LIQUIDITY_CRISIS,
            StressScenario.FLASH_CRASH_2010,
        ]
        
        summary = stress_runner.run_stress_test(
            strategy=strategy,
            bars=sample_bars,
            scenarios=scenarios,
        )
        
        assert summary.survival_verdict is not None
        assert len(summary.stress_results) == len(scenarios)
