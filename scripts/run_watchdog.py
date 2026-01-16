#!/usr/bin/env python3
"""
Entry point for the independent watchdog process.

CRITICAL: Run this in a SEPARATE terminal from the trading bot.

Usage:
    python scripts/run_watchdog.py
    
    # Or in background:
    nohup python scripts/run_watchdog.py > logs/watchdog.log 2>&1 &

The watchdog monitors the trading bot and can:
- Kill the bot if rules are breached
- Liquidate all positions in emergency
- Send alerts
- Prevent restart without human intervention
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

from watchdog.daemon import WatchdogDaemon
from watchdog.broker_client import WatchdogBrokerClient
from watchdog.alert_dispatcher import AlertDispatcher
from watchdog.rules import DEFAULT_RULES


def setup_logging(log_level: str = "INFO", log_file: str = None) -> None:
    """Configure structured logging for watchdog."""
    import logging
    
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    
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
    
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper()),
        handlers=handlers,
    )


def main():
    parser = argparse.ArgumentParser(
        description="The Market Maker - Independent Watchdog",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
CRITICAL: This must run as a SEPARATE process from the trading bot.
The watchdog uses SEPARATE API credentials and has no shared state.

Examples:
    # Run in foreground
    python scripts/run_watchdog.py
    
    # Run with specific PID file location
    python scripts/run_watchdog.py --pid-file /tmp/market_maker/bot.pid
    
    # Run with custom check interval
    python scripts/run_watchdog.py --interval 15
        """,
    )
    
    parser.add_argument(
        "--pid-file",
        type=str,
        default="/tmp/market_maker/bot.pid",
        help="Path to main bot's PID file",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Check interval in seconds",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default="logs/watchdog.log",
        help="Path to log file",
    )
    
    args = parser.parse_args()
    
    # Load environment variables
    load_dotenv()
    
    # Setup logging
    setup_logging(args.log_level, args.log_file)
    logger = structlog.get_logger(__name__)
    
    logger.info(
        "starting_watchdog",
        pid_file=args.pid_file,
        interval=args.interval,
    )
    
    # Check for required environment variables
    # Prefer separate watchdog credentials
    api_key = os.environ.get("WATCHDOG_ALPACA_API_KEY") or os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("WATCHDOG_ALPACA_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY")
    
    if not api_key or not secret_key:
        logger.error(
            "missing_api_credentials",
            hint="Set WATCHDOG_ALPACA_API_KEY and WATCHDOG_ALPACA_SECRET_KEY",
        )
        sys.exit(1)
    
    # Warn if using shared credentials
    if not os.environ.get("WATCHDOG_ALPACA_API_KEY"):
        logger.warning(
            "using_shared_credentials",
            message="Watchdog should have separate API credentials for safety",
        )
    
    # Initialize components
    try:
        broker_client = WatchdogBrokerClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=True,  # ALWAYS paper trading
        )
        
        alerter = AlertDispatcher(
            slack_webhook_url=os.environ.get("SLACK_WEBHOOK_URL"),
        )
        
        daemon = WatchdogDaemon(
            rules=DEFAULT_RULES,
            broker_client=broker_client,
            alerter=alerter,
            main_bot_pid_file=args.pid_file,
            check_interval_seconds=args.interval,
        )
        
        # Run the watchdog
        daemon.run()
        
    except KeyboardInterrupt:
        logger.info("watchdog_stopped")
    except Exception as e:
        logger.exception("watchdog_crashed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
