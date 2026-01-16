"""
ETL pipeline from AppendOnlyLog to DuckDB.

This periodically processes events from the append-only log
and loads them into DuckDB for analytics and backtesting.

Runs as a background process, typically every 1-5 minutes.
"""

from datetime import datetime
from typing import Optional
import structlog
import json

from src.storage.append_log import AppendOnlyLog, Event, EventType
from src.storage.duckdb_store import DuckDBStore

logger = structlog.get_logger(__name__)


class ETLPipeline:
    """
    ETL pipeline from append log to DuckDB.
    
    Processes events in batches to avoid blocking the append log.
    Runs periodically to keep DuckDB up-to-date for analytics.
    """
    
    def __init__(
        self,
        append_log: AppendOnlyLog,
        duckdb_store: DuckDBStore,
        batch_interval_seconds: int = 60,
        max_batch_size: int = 10000,
    ):
        """
        Initialize ETL pipeline.
        
        Args:
            append_log: Append-only log to read from
            duckdb_store: DuckDB store to write to
            batch_interval_seconds: How often to run ETL
            max_batch_size: Maximum events per batch
        """
        self.append_log = append_log
        self.duckdb = duckdb_store
        self.batch_interval = batch_interval_seconds
        self.max_batch_size = max_batch_size
        
        # Track last processed position
        self.last_processed_line: int = 0
        
        logger.info(
            "etl_pipeline_initialized",
            batch_interval=batch_interval_seconds,
            max_batch_size=max_batch_size,
        )
    
    def run_once(self) -> dict:
        """
        Run ETL once (process one batch).
        
        Returns:
            Summary of processed events
        """
        summary = {
            "events_processed": 0,
            "bars_inserted": 0,
            "sentiment_inserted": 0,
            "trades_inserted": 0,
            "errors": 0,
        }
        
        try:
            # Read new events from append log
            events = self._read_new_events()
            
            if not events:
                return summary
            
            # Process events by type
            bars = []
            sentiment_records = []
            trades = []
            
            for event in events:
                try:
                    if event.event_type == EventType.BAR:
                        bars.append(self._event_to_bar(event))
                    elif event.event_type in (
                        EventType.SENTIMENT_REDDIT,
                        EventType.SENTIMENT_TWITTER,
                        EventType.SENTIMENT_AGGREGATED,
                    ):
                        sentiment_records.append(self._event_to_sentiment(event))
                    elif event.event_type == EventType.ORDER_FILLED:
                        trades.append(self._event_to_trade(event))
                    
                    summary["events_processed"] += 1
                
                except Exception as e:
                    logger.error("event_processing_error", event_id=event.event_id, error=str(e))
                    summary["errors"] += 1
            
            # Insert into DuckDB
            if bars:
                count = self.duckdb.insert_bars(bars)
                summary["bars_inserted"] = count
            
            if sentiment_records:
                count = self.duckdb.insert_sentiment(sentiment_records)
                summary["sentiment_inserted"] = count
            
            if trades:
                for trade in trades:
                    self.duckdb.insert_trade(trade)
                summary["trades_inserted"] = len(trades)
            
            logger.info("etl_batch_complete", **summary)
        
        except Exception as e:
            logger.error("etl_pipeline_error", error=str(e))
            summary["errors"] += 1
        
        return summary
    
    def _read_new_events(self) -> list[Event]:
        """Read new events from append log."""
        # Read all events (in production, would track position)
        events = self.append_log.read_all()
        
        # Filter to new events (simplified - would track line numbers)
        return events
    
    def _event_to_bar(self, event: Event) -> dict:
        """Convert event to bar dictionary."""
        data = event.data
        
        return {
            "symbol": event.symbol or "UNKNOWN",
            "timestamp": event.timestamp,
            "timeframe": data.get("timeframe", "1Day"),
            "tier": data.get("tier", "TIER_1_VALIDATION"),
            "open": data["open"],
            "high": data["high"],
            "low": data["low"],
            "close": data["close"],
            "volume": data["volume"],
            "estimated_spread_bps": data.get("estimated_spread_bps"),
        }
    
    def _event_to_sentiment(self, event: Event) -> dict:
        """Convert event to sentiment record."""
        data = event.data
        
        return {
            "symbol": event.symbol or "UNKNOWN",
            "timestamp": event.timestamp,
            "source": event.source,
            "score": data["score"],
            "volume": data.get("volume", 0),
            "is_calibrated": False,  # Would be set during calibration
            "lead_lag_hours": None,
            "correlation": None,
        }
    
    def _event_to_trade(self, event: Event) -> dict:
        """Convert event to trade record."""
        data = event.data
        
        return {
            "trade_id": event.event_id,
            "order_id": data.get("order_id", ""),
            "client_order_id": event.correlation_id or "",
            "symbol": event.symbol or "UNKNOWN",
            "timestamp": event.timestamp,
            "side": data["side"],
            "qty": data["filled_qty"],
            "price": data["filled_price"],
            "expected_price": data.get("expected_price"),
            "slippage_bps": data.get("slippage_bps"),
            "commission": data.get("commission", 0),
            "strategy_name": data.get("strategy_name"),
            "signal_id": data.get("signal_id"),
        }
    
    def run_continuously(self) -> None:
        """Run ETL continuously (for background process)."""
        import time
        
        logger.info("etl_pipeline_starting_continuous")
        
        while True:
            try:
                self.run_once()
                time.sleep(self.batch_interval)
            except KeyboardInterrupt:
                logger.info("etl_pipeline_stopped")
                break
            except Exception as e:
                logger.error("etl_pipeline_continuous_error", error=str(e))
                time.sleep(self.batch_interval)
