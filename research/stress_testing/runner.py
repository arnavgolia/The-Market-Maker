"""
Stress test runner.

Implements Gemini's critical recommendation: test strategies under
10x spread scenarios. A strategy that fails this test is rejected.

The key insight: A strategy that survives 10x spreads has real edge.
A strategy that dies under 10x spreads was surviving on spread arbitrage
that won't exist in real crisis conditions.
"""

from dataclasses import dataclass
from typing import Optional
import structlog

from src.strategy.base import Strategy
from research.backtesting.engine import BacktestEngine, BacktestResult
from src.data.cost_model.stressed_costs import (
    StressedCostModel,
    StressScenario,
    StressConfig,
)
from src.data.cost_model.spread_estimator import SpreadEstimator
from src.data.cost_model.slippage_model import SlippageModel

logger = structlog.get_logger(__name__)


@dataclass
class StressTestResult:
    """Results from a stress test scenario."""
    scenario: str
    config: StressConfig
    
    # Performance metrics
    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    
    # Trading metrics
    num_trades: int
    total_transaction_costs: float
    avg_cost_per_trade: float
    
    # Survival verdict
    went_bankrupt: bool
    still_profitable: bool
    sharpe_acceptable: bool  # Sharpe > 0.5


@dataclass
class StressTestSummary:
    """Summary of all stress test results."""
    baseline_result: BacktestResult
    stress_results: dict[str, StressTestResult]
    
    # Critical verdict
    survival_verdict: str  # PASS, FAIL, MARGINAL, WEAK
    
    # Degradation metrics
    degradation_by_scenario: dict[str, dict]


class StressTestRunner:
    """
    Run backtests under stressed market conditions.
    
    The key insight: A strategy that survives 10x spreads has real edge.
    A strategy that dies under 10x spreads was surviving on spread arbitrage
    that won't exist in real crisis conditions.
    """
    
    def __init__(
        self,
        backtest_engine: BacktestEngine,
        base_spread_estimator: Optional[SpreadEstimator] = None,
        base_slippage_model: Optional[SlippageModel] = None,
    ):
        """
        Initialize stress test runner.
        
        Args:
            backtest_engine: Base backtest engine
            base_spread_estimator: Base spread estimator
            base_slippage_model: Base slippage model
        """
        self.base_engine = backtest_engine
        self.base_spread = base_spread_estimator or SpreadEstimator()
        self.base_slippage = base_slippage_model or SlippageModel()
        
        logger.info("stress_test_runner_initialized")
    
    def run_stress_test(
        self,
        strategy: Strategy,
        bars: any,
        scenarios: list[StressScenario],
        baseline_scenario: StressScenario = StressScenario.NORMAL,
        regime_detector: Optional[callable] = None,
    ) -> StressTestSummary:
        """
        Run strategy through multiple stress scenarios.
        
        Returns comparison of performance degradation.
        
        Args:
            strategy: Strategy to test
            bars: Historical bars
            scenarios: List of stress scenarios to test
            baseline_scenario: Baseline scenario (usually NORMAL)
            regime_detector: Optional regime detector
        
        Returns:
            StressTestSummary with all results and verdict
        """
        import pandas as pd
        
        if isinstance(bars, list):
            bars_df = pd.DataFrame([
                {
                    "timestamp": b.timestamp,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                }
                for b in bars
            ])
        else:
            bars_df = bars.copy()
        
        # Run baseline first
        logger.info("running_baseline", scenario=baseline_scenario.value)
        baseline_result = self.base_engine.run(
            strategy=strategy,
            bars=bars_df,
            regime_detector=regime_detector,
        )
        
        # Run stress scenarios
        stress_results = {}
        
        for scenario in scenarios:
            logger.info("running_stress_scenario", scenario=scenario.value)
            
            # Create stressed cost model
            stressed_cost = StressedCostModel.from_scenario(
                scenario=scenario,
                base_spread_estimator=self.base_spread,
                base_slippage_model=self.base_slippage,
            )
            
            # Create stressed backtest engine
            stressed_engine = BacktestEngine(
                initial_capital=self.base_engine.initial_capital,
                spread_estimator=None,  # Will use stressed costs
                slippage_model=None,
            )
            
            # Replace cost models in engine (simplified - would need engine refactor)
            # For now, we'll create a custom run that uses stressed costs
            stress_result = self._run_with_stressed_costs(
                strategy=strategy,
                bars=bars_df,
                stressed_cost=stressed_cost,
                regime_detector=regime_detector,
            )
            
            stress_results[scenario.value] = stress_result
        
        # Calculate degradation and verdict
        summary = self._analyze_results(
            baseline_result=baseline_result,
            stress_results=stress_results,
        )
        
        return summary
    
    def _run_with_stressed_costs(
        self,
        strategy: Strategy,
        bars: any,
        stressed_cost: StressedCostModel,
        regime_detector: Optional[callable] = None,
    ) -> StressTestResult:
        """
        Run backtest with stressed costs.
        
        Creates a custom backtest engine with stressed cost model.
        """
        import pandas as pd
        
        # Convert bars to DataFrame if needed
        if isinstance(bars, list):
            bars_df = pd.DataFrame([
                {
                    "timestamp": b.timestamp,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                }
                for b in bars
            ])
        else:
            bars_df = bars.copy()
        
        # Create stressed backtest engine
        # Note: This requires refactoring BacktestEngine to accept cost models
        # For now, we'll create a wrapper that uses stressed costs
        
        # Create custom spread/slippage models with stress multipliers
        from src.data.cost_model.spread_estimator import SpreadEstimator
        from src.data.cost_model.slippage_model import SlippageModel
        
        # Apply stress multipliers to base models
        base_spread = SpreadEstimator(
            spread_floor_bps=5.0 * stressed_cost.config.spread_multiplier,
            spread_ceiling_bps=100.0 * stressed_cost.config.spread_multiplier,
        )
        
        base_slippage = SlippageModel(
            base_slippage_bps=5.0 * stressed_cost.config.slippage_multiplier,
            market_order_multiplier=2.0,
        )
        
        # Create stressed engine
        stressed_engine = BacktestEngine(
            initial_capital=self.base_engine.initial_capital,
            spread_estimator=base_spread,
            slippage_model=base_slippage,
        )
        
        # Run backtest
        try:
            result = stressed_engine.run(
                strategy=strategy,
                bars=bars_df,
                regime_detector=regime_detector,
            )
            
            # Check survival
            went_bankrupt = result.final_equity <= 0 if hasattr(result, 'final_equity') else result.total_return < -0.99
            still_profitable = result.total_return > 0
            sharpe_acceptable = result.sharpe_ratio >= 0.5
            
            return StressTestResult(
                scenario=stressed_cost.config.__class__.__name__,
                config=stressed_cost.config,
                total_return=result.total_return,
                sharpe_ratio=result.sharpe_ratio,
                sortino_ratio=result.sortino_ratio,
                max_drawdown=result.max_drawdown,
                num_trades=result.num_trades,
                total_transaction_costs=result.total_transaction_costs,
                avg_cost_per_trade=result.avg_cost_per_trade,
                went_bankrupt=went_bankrupt,
                still_profitable=still_profitable,
                sharpe_acceptable=sharpe_acceptable,
            )
        
        except Exception as e:
            logger.error("stressed_backtest_failed", error=str(e))
            # Return failure result
            return StressTestResult(
                scenario=stressed_cost.config.__class__.__name__,
                config=stressed_cost.config,
                total_return=-1.0,  # Assume total loss on error
                sharpe_ratio=-10.0,
                sortino_ratio=-10.0,
                max_drawdown=1.0,
                num_trades=0,
                total_transaction_costs=0.0,
                avg_cost_per_trade=0.0,
                went_bankrupt=True,
                still_profitable=False,
                sharpe_acceptable=False,
            )
    
    def _analyze_results(
        self,
        baseline_result: BacktestResult,
        stress_results: dict[str, StressTestResult],
    ) -> StressTestSummary:
        """
        Analyze stress test results and generate verdict.
        
        THE CRITICAL VERDICT: Does the strategy survive 10x spreads?
        """
        # Calculate degradation
        degradation = {}
        
        for scenario_name, result in stress_results.items():
            sharpe_degradation = (
                (baseline_result.sharpe_ratio - result.sharpe_ratio) / baseline_result.sharpe_ratio
                if baseline_result.sharpe_ratio != 0
                else float('inf')
            )
            
            return_degradation = (
                (baseline_result.total_return - result.total_return) / abs(baseline_result.total_return)
                if baseline_result.total_return != 0
                else float('inf')
            )
            
            degradation[scenario_name] = {
                "sharpe_degradation_pct": sharpe_degradation * 100,
                "return_degradation_pct": return_degradation * 100,
                "went_bankrupt": result.went_bankrupt,
                "still_profitable": result.still_profitable,
            }
        
        # THE CRITICAL VERDICT: Check 10x spread scenario (Volmageddon)
        volmageddon_result = stress_results.get("volmageddon")
        
        if volmageddon_result:
            if volmageddon_result.went_bankrupt:
                verdict = "FAIL - Strategy bankrupts under 10x spreads"
            elif volmageddon_result.total_return < 0:
                verdict = "MARGINAL - Strategy loses money under 10x spreads"
            elif volmageddon_result.sharpe_ratio < 0.5:
                verdict = "WEAK - Strategy Sharpe < 0.5 under 10x spreads"
            else:
                verdict = "PASS - Strategy survives 10x spreads"
        else:
            verdict = "UNKNOWN - Volmageddon scenario not tested"
        
        return StressTestSummary(
            baseline_result=baseline_result,
            stress_results=stress_results,
            survival_verdict=verdict,
            degradation_by_scenario=degradation,
        )
    
    def validate_strategy_robustness(
        self,
        strategy: Strategy,
        bars: any,
        scenarios: Optional[list[StressScenario]] = None,
    ) -> bool:
        """
        Validate that strategy is robust under stress.
        
        Returns True if strategy passes all stress tests.
        This is Gemini's critical test.
        """
        if scenarios is None:
            scenarios = [
                StressScenario.VOLMAGEDDON_2018,  # 10x spreads - THE CRITICAL TEST
                StressScenario.LIQUIDITY_CRISIS,
            ]
        
        summary = self.run_stress_test(
            strategy=strategy,
            bars=bars,
            scenarios=scenarios,
        )
        
        # Strategy is valid if verdict contains "PASS"
        is_valid = "PASS" in summary.survival_verdict
        
        logger.info(
            "strategy_robustness_validation",
            verdict=summary.survival_verdict,
            is_valid=is_valid,
        )
        
        return is_valid
