#!/usr/bin/env python3
"""
Stress test a strategy under crisis conditions.

Implements Gemini's critical test: Does the strategy survive 10x spreads?

Usage:
    python scripts/stress_test_strategy.py --strategy ema_crossover --symbol AAPL
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
from research.stress_testing.runner import StressTestRunner, StressScenario
from research.backtesting.engine import BacktestEngine
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
    parser = argparse.ArgumentParser(
        description="Stress test strategy under crisis conditions",
        epilog="""
This implements Gemini's critical test: Does the strategy survive 10x spreads?

A strategy that fails this test is rejected - it was surviving on spread
arbitrage that won't exist in real crisis conditions.
        """,
    )
    parser.add_argument("--strategy", required=True, choices=["ema_crossover"])
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    
    args = parser.parse_args()
    
    setup_logging()
    load_dotenv()
    
    logger.info("stress_test_starting", strategy=args.strategy, symbol=args.symbol)
    
    # Initialize data client
    alpaca = AlpacaDataClient(paper=True)
    
    # Get historical data
    if args.start and args.end:
        start = datetime.fromisoformat(args.start)
        end = datetime.fromisoformat(args.end)
    else:
        end = datetime.now()
        start = datetime(end.year - 2, 1, 1)
    
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
    
    # Initialize strategy
    strategy = EMACrossoverStrategy()
    
    # Initialize backtest engine
    backtest_engine = BacktestEngine(
        initial_capital=100000.0,
        spread_estimator=SpreadEstimator(),
        slippage_model=SlippageModel(),
    )
    
    # Run stress test
    stress_runner = StressTestRunner(backtest_engine)
    
    logger.info("running_10x_spread_test", scenario="volmageddon")
    
    is_valid = stress_runner.validate_strategy_robustness(
        strategy=strategy,
        bars=bars_df,
        scenarios=[
            StressScenario.VOLMAGEDDON_2018,  # 10x spreads - THE CRITICAL TEST
            StressScenario.LIQUIDITY_CRISIS,
            StressScenario.FLASH_CRASH_2010,
        ],
    )
    
    if is_valid:
        logger.info("STRESS_TEST_PASSED", message="Strategy survives 10x spreads")
        sys.exit(0)
    else:
        logger.error("STRESS_TEST_FAILED", message="Strategy fails under 10x spreads - REJECTED")
        sys.exit(1)


if __name__ == "__main__":
    main()
