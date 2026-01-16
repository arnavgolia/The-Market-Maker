#!/usr/bin/env python3
"""
Main entry point for the trading bot.

Usage:
    python scripts/run_bot.py
    
    # Or with custom config:
    python scripts/run_bot.py --config config/settings.yaml

WARNING: Ensure the watchdog is running in a separate terminal:
    python scripts/run_watchdog.py
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

from src.main import MarketMaker


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
        description="The Market Maker - Paper Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with default config
    python scripts/run_bot.py
    
    # Run with custom config
    python scripts/run_bot.py --config config/custom_settings.yaml
    
    # Run in debug mode
    python scripts/run_bot.py --log-level DEBUG

WARNING:
    Ensure the watchdog is running in a separate process:
    python scripts/run_watchdog.py
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without executing trades (simulation only)",
    )
    
    args = parser.parse_args()
    
    # Load environment variables
    load_dotenv()
    
    # Setup logging
    setup_logging(args.log_level)
    logger = structlog.get_logger(__name__)
    
    logger.info(
        "starting_market_maker",
        config=args.config,
        dry_run=args.dry_run,
    )
    
    # Check for required environment variables
    required_vars = ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"]
    missing = [v for v in required_vars if not os.environ.get(v)]
    
    if missing:
        logger.error(
            "missing_environment_variables",
            missing=missing,
            hint="Copy .env.example to .env and fill in your credentials",
        )
        sys.exit(1)
    
    # Create and run the market maker
    try:
        bot = MarketMaker(
            config_path=args.config,
            dry_run=args.dry_run,
        )
        bot.run()
    except KeyboardInterrupt:
        logger.info("bot_interrupted")
    except Exception as e:
        logger.exception("bot_crashed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
