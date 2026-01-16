#!/usr/bin/env python3
"""
Run ETL pipeline as standalone process.

This processes events from the append-only log and loads them
into DuckDB for analytics. Can run as a background service.

Usage:
    python scripts/run_etl.py
    
    # Or as background service
    nohup python scripts/run_etl.py > logs/etl.log 2>&1 &
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import structlog
from dotenv import load_dotenv

from src.storage.append_log import AppendOnlyLog
from src.storage.duckdb_store import DuckDBStore
from src.storage.etl_pipeline import ETLPipeline

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
    parser = argparse.ArgumentParser(description="ETL Pipeline")
    parser.add_argument("--log-path", default="data/logs/events.jsonl")
    parser.add_argument("--duckdb-path", default="data/market_maker.duckdb")
    parser.add_argument("--interval", type=int, default=60, help="Batch interval in seconds")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    
    args = parser.parse_args()
    
    setup_logging()
    load_dotenv()
    
    logger.info("etl_pipeline_starting", log_path=args.log_path, duckdb_path=args.duckdb_path)
    
    # Initialize components
    append_log = AppendOnlyLog(args.log_path)
    duckdb = DuckDBStore(args.duckdb_path)
    
    etl = ETLPipeline(
        append_log=append_log,
        duckdb_store=duckdb,
        batch_interval_seconds=args.interval,
    )
    
    try:
        if args.once:
            # Run once
            summary = etl.run_once()
            logger.info("etl_complete", **summary)
        else:
            # Run continuously
            etl.run_continuously()
    except KeyboardInterrupt:
        logger.info("etl_stopped")
    except Exception as e:
        logger.exception("etl_error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
