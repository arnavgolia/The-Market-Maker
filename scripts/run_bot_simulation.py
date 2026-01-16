#!/usr/bin/env python3
"""
Run The Market Maker in FULL SIMULATION MODE - NO API REQUIRED!

This mode uses:
- yfinance for free market data (no API keys needed)
- PaperBroker for simulated trading (no API needed)
- Mock account data for dashboard

Perfect for testing and demonstration without any external APIs.
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import structlog
from dotenv import load_dotenv

# Mock Alpaca client for simulation
class MockAlpacaClient:
    """Mock Alpaca client that works without API."""
    
    def __init__(self):
        self.equity = 100000.0
        self.cash = 100000.0
        self.buying_power = 200000.0
        
    def get_account(self):
        class MockAccount:
            def __init__(self, equity, cash, buying_power):
                self.equity = equity
                self.cash = cash
                self.buying_power = buying_power
                self.status = type('Status', (), {'value': 'ACTIVE'})()
        return MockAccount(self.equity, self.cash, self.buying_power)
    
    def get_clock(self):
        class MockClock:
            is_open = True
            from datetime import datetime, timedelta
            timestamp = datetime.now()
            next_open = datetime.now() + timedelta(days=1)
            next_close = datetime.now() + timedelta(days=1, hours=6)
        return MockClock()
    
    def get_positions(self):
        return []
    
    def get_orders(self, **kwargs):
        return []


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    import logging
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper()),
        stream=sys.stdout,
    )


def main():
    parser = argparse.ArgumentParser(
        description="The Market Maker - FULL SIMULATION MODE (No API Required)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This mode runs completely offline using:
- yfinance for free market data
- PaperBroker for simulated trading
- No API keys required!

Examples:
    # Run simulation mode
    python scripts/run_bot_simulation.py
    
    # Run with debug logging
    python scripts/run_bot_simulation.py --log-level DEBUG
        """,
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config/settings.yaml",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    
    args = parser.parse_args()
    
    # Load environment variables (optional)
    load_dotenv()
    
    # Setup logging
    setup_logging(args.log_level)
    logger = structlog.get_logger(__name__)
    
    logger.info(
        "starting_market_maker_simulation",
        config=args.config,
        mode="FULL_SIMULATION_NO_API",
    )
    
    # Set environment to use simulation mode
    os.environ["SIMULATION_MODE"] = "true"
    os.environ["ALPACA_API_KEY"] = os.environ.get("ALPACA_API_KEY", "simulation")
    os.environ["ALPACA_SECRET_KEY"] = os.environ.get("ALPACA_SECRET_KEY", "simulation")
    
    # Import and patch the MarketMaker to use simulation
    from src.main import MarketMaker
    
    # No need to patch - main.py now handles SIMULATION_MODE
    
    # Create and run the market maker in simulation mode
    try:
        bot = MarketMaker(
            config_path=args.config,
            dry_run=True,  # Always use dry_run for simulation
        )
        
        logger.info(
            "simulation_mode_active",
            message="Running in FULL SIMULATION MODE - No API required!",
            data_source="yfinance (free)",
            broker="PaperBroker (simulated)",
        )
        
        bot.run()
    except KeyboardInterrupt:
        logger.info("bot_interrupted")
    except Exception as e:
        logger.exception("bot_crashed", error=str(e))
        sys.exit(1)
    finally:
        # Restore original if we patched it
        if original_init:
            try:
                alpaca_client.AlpacaDataClient.__init__ = original_init
            except:
                pass


if __name__ == "__main__":
    main()
