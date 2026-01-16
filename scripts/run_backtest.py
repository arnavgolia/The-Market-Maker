#!/usr/bin/env python3
"""
Run backtesting suite.

Usage:
    python scripts/run_backtest.py --strategy ema_crossover --symbol AAPL --start 2020-01-01 --end 2023-12-31
    
    # With walk-forward validation
    python scripts/run_backtest.py --strategy ema_crossover --walk-forward
    
    # With stress testing
    python scripts/run_backtest.py --strategy ema_crossover --stress-test
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

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


def main():
    parser = argparse.ArgumentParser(description="Run backtesting suite")
    parser.add_argument("--strategy", required=True, choices=["ema_crossover", "rsi_mean_reversion"])
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--walk-forward", action="store_true", help="Use walk-forward validation")
    parser.add_argument("--stress-test", action="store_true", help="Run stress tests")
    
    args = parser.parse_args()
    
    setup_logging()
    load_dotenv()
    
    logger.info("backtest_starting", strategy=args.strategy, symbol=args.symbol)
    
    # Initialize data client
    alpaca = AlpacaDataClient(paper=True)
    
    # Get historical data
    if args.start and args.end:
        start = datetime.fromisoformat(args.start)
        end = datetime.fromisoformat(args.end)
    else:
        # Default: last 2 years
        end = datetime.now()
        start = datetime(end.year - 2, 1, 1)
    
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
    
    # Initialize strategy
    if args.strategy == "ema_crossover":
        strategy = EMACrossoverStrategy()
    elif args.strategy == "rsi_mean_reversion":
        strategy = RSIMeanReversionStrategy()
    else:
        logger.error("unknown_strategy", strategy=args.strategy)
        sys.exit(1)
    
    # Initialize backtest engine
    backtest_engine = BacktestEngine(
        initial_capital=100000.0,
        spread_estimator=SpreadEstimator(),
        slippage_model=SlippageModel(),
    )
    
    # Run backtest
    if args.walk_forward:
        logger.info("running_walk_forward_validation")
        validator = WalkForwardValidator()
        results = validator.validate(
            strategy=strategy,
            bars=bars_df,
            backtest_engine=backtest_engine,
        )
        
        summary = validator.aggregate_results(results)
        logger.info("walk_forward_complete", **summary)
        
        if not summary["valid"]:
            logger.warning("strategy_failed_walk_forward_validation")
            sys.exit(1)
    
    elif args.stress_test:
        logger.info("running_stress_tests")
        stress_runner = StressTestRunner(backtest_engine)
        
        is_valid = stress_runner.validate_strategy_robustness(
            strategy=strategy,
            bars=bars_df,
            scenarios=[
                StressScenario.VOLMAGEDDON_2018,  # 10x spreads - THE CRITICAL TEST
                StressScenario.LIQUIDITY_CRISIS,
            ],
        )
        
        if not is_valid:
            logger.warning("strategy_failed_stress_tests")
            sys.exit(1)
        
        logger.info("strategy_passed_stress_tests")
    
    else:
        # Standard backtest
        logger.info("running_standard_backtest")
        result = backtest_engine.run(strategy=strategy, bars=bars_df)
        
        logger.info(
            "backtest_complete",
            total_return=result.total_return,
            sharpe=result.sharpe_ratio,
            sortino=result.sortino_ratio,
            max_drawdown=result.max_drawdown,
            num_trades=result.num_trades,
            total_costs=result.total_transaction_costs,
        )
    
    logger.info("backtest_suite_complete")


if __name__ == "__main__":
    main()
