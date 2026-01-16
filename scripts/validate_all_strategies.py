#!/usr/bin/env python3
"""
Run full walk-forward + stress test validation on ALL strategies.

This script:
1. Runs walk-forward validation on each strategy
2. Runs stress tests (10x spreads) on each strategy
3. Generates validation report
4. Only strategies that pass BOTH are considered valid

Usage:
    python scripts/validate_all_strategies.py --symbol AAPL --start 2020-01-01 --end 2023-12-31
    
    # Validate specific strategy
    python scripts/validate_all_strategies.py --strategy ema_crossover
    
    # Validate all strategies
    python scripts/validate_all_strategies.py --all
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import structlog
from dotenv import load_dotenv

from src.data.ingestion.alpaca_client import AlpacaDataClient
from src.strategy.tier1.ema_crossover import EMACrossoverStrategy
from src.strategy.tier1.rsi_mean_reversion import RSIMeanReversionStrategy
from research.backtesting.engine import BacktestEngine
from research.backtesting.walk_forward import WalkForwardValidator
from research.stress_testing.runner import StressTestRunner, StressScenario
from src.data.cost_model.spread_estimator import SpreadEstimator
from src.data.cost_model.slippage_model import SlippageModel

logger = structlog.get_logger(__name__)


def setup_logging():
    """Configure logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


class StrategyValidator:
    """Validates strategies with walk-forward + stress testing."""
    
    def __init__(self, backtest_engine: BacktestEngine, stress_runner: StressTestRunner):
        """Initialize validator."""
        self.backtest_engine = backtest_engine
        self.stress_runner = stress_runner
        self.walk_forward_validator = WalkForwardValidator()
    
    def validate_strategy(
        self,
        strategy,
        bars,
        strategy_name: str,
    ) -> dict:
        """
        Validate a strategy with both walk-forward and stress tests.
        
        Returns validation result with pass/fail status.
        """
        logger.info("validating_strategy", strategy=strategy_name)
        
        result = {
            "strategy": strategy_name,
            "walk_forward": None,
            "stress_test": None,
            "valid": False,
            "errors": [],
        }
        
        # 1. Walk-Forward Validation
        try:
            logger.info("running_walk_forward_validation", strategy=strategy_name)
            
            walk_forward_results = self.walk_forward_validator.validate(
                strategy=strategy,
                bars=bars,
                backtest_engine=self.backtest_engine,
            )
            
            walk_forward_summary = self.walk_forward_validator.aggregate_results(walk_forward_results)
            
            result["walk_forward"] = {
                "passed": walk_forward_summary["valid"],
                "summary": walk_forward_summary,
            }
            
            if not walk_forward_summary["valid"]:
                result["errors"].append("Walk-forward validation failed")
                logger.warning("walk_forward_failed", strategy=strategy_name)
        
        except Exception as e:
            logger.error("walk_forward_error", strategy=strategy_name, error=str(e))
            result["errors"].append(f"Walk-forward error: {str(e)}")
            result["walk_forward"] = {"passed": False, "error": str(e)}
        
        # 2. Stress Testing (10x Spreads)
        try:
            logger.info("running_stress_tests", strategy=strategy_name)
            
            is_valid = self.stress_runner.validate_strategy_robustness(
                strategy=strategy,
                bars=bars,
                scenarios=[
                    StressScenario.VOLMAGEDDON_2018,  # 10x spreads - THE CRITICAL TEST
                    StressScenario.LIQUIDITY_CRISIS,
                    StressScenario.FLASH_CRASH_2010,
                ],
            )
            
            result["stress_test"] = {
                "passed": is_valid,
            }
            
            if not is_valid:
                result["errors"].append("Stress test failed (10x spreads)")
                logger.warning("stress_test_failed", strategy=strategy_name)
        
        except Exception as e:
            logger.error("stress_test_error", strategy=strategy_name, error=str(e))
            result["errors"].append(f"Stress test error: {str(e)}")
            result["stress_test"] = {"passed": False, "error": str(e)}
        
        # 3. Final verdict
        result["valid"] = (
            result["walk_forward"] is not None and
            result["walk_forward"].get("passed", False) and
            result["stress_test"] is not None and
            result["stress_test"].get("passed", False)
        )
        
        if result["valid"]:
            logger.info("strategy_validated", strategy=strategy_name)
        else:
            logger.warning("strategy_failed_validation", strategy=strategy_name, errors=result["errors"])
        
        return result


def main():
    parser = argparse.ArgumentParser(
        description="Validate all strategies with walk-forward + stress testing",
        epilog="""
This runs the complete validation suite:
1. Walk-forward validation (prevents overfitting)
2. Stress testing (10x spreads - Gemini's critical test)

Only strategies that pass BOTH are considered valid for production.
        """,
    )
    parser.add_argument("--strategy", choices=["ema_crossover", "rsi_mean_reversion", "all"])
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", type=str, help="Output JSON file for results")
    
    args = parser.parse_args()
    
    setup_logging()
    load_dotenv()
    
    logger.info("strategy_validation_starting", strategy=args.strategy, symbol=args.symbol)
    
    # Initialize data client
    alpaca = AlpacaDataClient(paper=True)
    
    # Get historical data
    if args.start and args.end:
        start = datetime.fromisoformat(args.start)
        end = datetime.fromisoformat(args.end)
    else:
        # Default: last 3 years
        end = datetime.now()
        start = datetime(end.year - 3, 1, 1)
    
    logger.info("fetching_historical_data", symbol=args.symbol, start=start, end=end)
    bars = alpaca.get_historical_bars(
        symbol=args.symbol,
        start=start,
        end=end,
        timeframe="1Day",
    )
    
    if not bars:
        logger.error("no_data_fetched")
        sys.exit(1)
    
    # Convert to DataFrame
    import pandas as pd
    bars_df = pd.DataFrame([
        {
            "timestamp": b.timestamp,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
            "symbol": b.symbol,
        }
        for b in bars
    ])
    
    logger.info("data_fetched", bars_count=len(bars_df))
    
    # Initialize backtest engine and stress runner
    backtest_engine = BacktestEngine(
        initial_capital=100000.0,
        spread_estimator=SpreadEstimator(),
        slippage_model=SlippageModel(),
    )
    
    stress_runner = StressTestRunner(backtest_engine)
    validator = StrategyValidator(backtest_engine, stress_runner)
    
    # Determine which strategies to validate
    strategies_to_validate = []
    
    if args.strategy == "all" or args.strategy == "ema_crossover":
        strategies_to_validate.append(("ema_crossover", EMACrossoverStrategy()))
    
    if args.strategy == "all" or args.strategy == "rsi_mean_reversion":
        strategies_to_validate.append(("rsi_mean_reversion", RSIMeanReversionStrategy()))
    
    if not strategies_to_validate:
        logger.error("no_strategies_to_validate")
        sys.exit(1)
    
    # Validate each strategy
    all_results = []
    
    for strategy_name, strategy in strategies_to_validate:
        result = validator.validate_strategy(
            strategy=strategy,
            bars=bars_df,
            strategy_name=strategy_name,
        )
        all_results.append(result)
    
    # Generate summary
    passed = [r for r in all_results if r["valid"]]
    failed = [r for r in all_results if not r["valid"]]
    
    summary = {
        "timestamp": datetime.now().isoformat(),
        "symbol": args.symbol,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "total_strategies": len(all_results),
        "passed": len(passed),
        "failed": len(failed),
        "results": all_results,
    }
    
    # Print summary
    print("\n" + "=" * 80)
    print("STRATEGY VALIDATION SUMMARY")
    print("=" * 80)
    print(f"Symbol: {args.symbol}")
    print(f"Period: {start.date()} to {end.date()}")
    print(f"Total Strategies: {len(all_results)}")
    print(f"Passed: {len(passed)}")
    print(f"Failed: {len(failed)}")
    print("\n" + "-" * 80)
    
    for result in all_results:
        status = "✅ PASSED" if result["valid"] else "❌ FAILED"
        print(f"\n{result['strategy']}: {status}")
        
        if result["walk_forward"]:
            wf_status = "✅" if result["walk_forward"]["passed"] else "❌"
            print(f"  Walk-Forward: {wf_status}")
        
        if result["stress_test"]:
            st_status = "✅" if result["stress_test"]["passed"] else "❌"
            print(f"  Stress Test: {st_status}")
        
        if result["errors"]:
            print(f"  Errors: {', '.join(result['errors'])}")
    
    print("\n" + "=" * 80)
    
    # Save results
    if args.output:
        with open(args.output, "w") as f:
            json.dump(summary, f, indent=2)
        logger.info("results_saved", output_file=args.output)
    
    # Exit with error if any strategy failed
    if failed:
        logger.warning("validation_complete_with_failures", failed_count=len(failed))
        sys.exit(1)
    else:
        logger.info("validation_complete_all_passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
