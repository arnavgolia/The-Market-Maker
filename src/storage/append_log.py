"""
Append-only log for high-throughput event capture.

This is the primary write path for all events (market data, sentiment, orders).
It uses simple file appending with no locks, enabling concurrent writes
from multiple sources without the SQLite bottleneck.

Events are later batch-ETL'd to DuckDB for analytics.
"""

import json
import os
import gzip
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from threading import Lock
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class EventType(Enum):
    """Types of events that can be logged."""
    # Market data events
    QUOTE = "quote"
    BAR = "bar"
    TRADE = "trade"
    
    # Sentiment events
    SENTIMENT_REDDIT = "sentiment_reddit"
    SENTIMENT_TWITTER = "sentiment_twitter"
    SENTIMENT_AGGREGATED = "sentiment_aggregated"
    
    # Trading events
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_REJECTED = "order_rejected"
    ORDER_PARTIAL_FILL = "order_partial_fill"
    
    # Strategy events
    SIGNAL_GENERATED = "signal_generated"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    
    # System events
    REGIME_CHANGE = "regime_change"
    RISK_ALERT = "risk_alert"
    HEARTBEAT = "heartbeat"
    ERROR = "error"


@dataclass
class Event:
    """
    A single event to be logged.
    
    Events are immutable records of something that happened.
    They are written to the append log and later ETL'd to DuckDB.
    """
    event_type: EventType
    timestamp: datetime
    data: dict[str, Any]
    
    # Optional metadata
    symbol: Optional[str] = None
    source: str = "unknown"
    correlation_id: Optional[str] = None
    
    # Set automatically
    event_id: str = field(default_factory=lambda: "")
    
    def __post_init__(self):
        """Generate event ID if not provided."""
        if not self.event_id:
            # Simple event ID: timestamp + type + random suffix
            import uuid
            ts = self.timestamp.strftime("%Y%m%d%H%M%S%f")
            self.event_id = f"{ts}_{self.event_type.value}_{uuid.uuid4().hex[:8]}"
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "source": self.source,
            "correlation_id": self.correlation_id,
            "data": self.data,
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event":
        """Create Event from dictionary."""
        return cls(
            event_id=d["event_id"],
            event_type=EventType(d["event_type"]),
            timestamp=datetime.fromisoformat(d["timestamp"]),
            symbol=d.get("symbol"),
            source=d.get("source", "unknown"),
            correlation_id=d.get("correlation_id"),
            data=d["data"],
        )


class AppendOnlyLog:
    """
    High-throughput append-only log for event capture.
    
    Design principles:
    - Append-only: No updates, no deletes
    - No locks on writes (thread-safe via file append semantics)
    - Simple JSONL format for easy parsing
    - Automatic rotation when file gets too large
    - Compression of rotated files
    
    This avoids the SQLite single-writer bottleneck that would
    cause latency issues under high-throughput sentiment ingestion.
    """
    
    def __init__(
        self,
        log_path: str,
        max_file_size_mb: float = 100.0,
        rotation_count: int = 10,
    ):
        """
        Initialize append-only log.
        
        Args:
            log_path: Path to the log file (JSONL format)
            max_file_size_mb: Max file size before rotation
            rotation_count: Number of rotated files to keep
        """
        self.log_path = Path(log_path)
        self.max_file_size_bytes = int(max_file_size_mb * 1024 * 1024)
        self.rotation_count = rotation_count
        
        # Ensure directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Lock for rotation (not for writes)
        self._rotation_lock = Lock()
        
        # File handle (opened on first write)
        self._file: Optional[Any] = None
        
        logger.info(
            "append_log_initialized",
            path=str(self.log_path),
            max_size_mb=max_file_size_mb,
        )
    
    def write(self, event: Event) -> None:
        """
        Write an event to the log.
        
        This is the hot path - optimized for throughput.
        """
        # Check if rotation needed (cheap check)
        if self._should_rotate():
            self._rotate()
        
        # Write event
        line = event.to_json() + "\n"
        
        try:
            with open(self.log_path, "a") as f:
                f.write(line)
        except Exception as e:
            logger.error("append_log_write_error", error=str(e))
            raise
    
    def write_batch(self, events: list[Event]) -> None:
        """
        Write multiple events in a single operation.
        
        More efficient than individual writes for high-throughput scenarios.
        """
        if not events:
            return
        
        # Check rotation before batch
        if self._should_rotate():
            self._rotate()
        
        lines = [event.to_json() + "\n" for event in events]
        
        try:
            with open(self.log_path, "a") as f:
                f.writelines(lines)
            
            logger.debug("batch_written", count=len(events))
        except Exception as e:
            logger.error("append_log_batch_error", error=str(e))
            raise
    
    def _should_rotate(self) -> bool:
        """Check if log file should be rotated."""
        if not self.log_path.exists():
            return False
        return self.log_path.stat().st_size >= self.max_file_size_bytes
    
    def _rotate(self) -> None:
        """
        Rotate the log file.
        
        Rotation is:
        1. Rename current file to .1
        2. Shift existing rotated files (.1 -> .2, etc.)
        3. Compress old files
        4. Delete files beyond rotation_count
        """
        with self._rotation_lock:
            # Double-check after acquiring lock
            if not self._should_rotate():
                return
            
            logger.info("rotating_log", path=str(self.log_path))
            
            # Shift existing rotated files
            for i in range(self.rotation_count - 1, 0, -1):
                old_path = Path(f"{self.log_path}.{i}.gz")
                new_path = Path(f"{self.log_path}.{i + 1}.gz")
                
                if old_path.exists():
                    if i + 1 >= self.rotation_count:
                        old_path.unlink()  # Delete oldest
                    else:
                        old_path.rename(new_path)
            
            # Compress and rename current file
            if self.log_path.exists():
                rotated_path = Path(f"{self.log_path}.1.gz")
                with open(self.log_path, "rb") as f_in:
                    with gzip.open(rotated_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                # Clear current file
                self.log_path.unlink()
            
            logger.info("log_rotated", path=str(self.log_path))
    
    def read_all(self) -> list[Event]:
        """
        Read all events from the current log file.
        
        NOTE: This is for debugging/testing only.
        Use DuckDB for production queries.
        """
        events = []
        
        if not self.log_path.exists():
            return events
        
        with open(self.log_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        d = json.loads(line)
                        events.append(Event.from_dict(d))
                    except json.JSONDecodeError as e:
                        logger.warning("invalid_log_line", error=str(e))
        
        return events
    
    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the log."""
        if not self.log_path.exists():
            return {"exists": False, "size_bytes": 0, "size_mb": 0}
        
        size = self.log_path.stat().st_size
        return {
            "exists": True,
            "size_bytes": size,
            "size_mb": size / (1024 * 1024),
            "needs_rotation": size >= self.max_file_size_bytes,
        }
    
    def flush(self) -> None:
        """
        Flush any buffered writes.
        
        Called during graceful shutdown to ensure all events are persisted.
        """
        # With file append mode, writes are unbuffered
        # This method exists for API compatibility
        pass
    
    def close(self) -> None:
        """Close the log (for graceful shutdown)."""
        self.flush()
        logger.info("append_log_closed", path=str(self.log_path))


# Convenience functions for creating common events

def create_quote_event(
    symbol: str,
    bid: float,
    ask: float,
    bid_size: float,
    ask_size: float,
    source: str = "alpaca",
) -> Event:
    """Create a quote event."""
    return Event(
        event_type=EventType.QUOTE,
        timestamp=datetime.now(),
        symbol=symbol,
        source=source,
        data={
            "bid": bid,
            "ask": ask,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "spread": ask - bid,
            "spread_bps": ((ask - bid) / ((bid + ask) / 2)) * 10000,
        },
    )


def create_sentiment_event(
    symbol: str,
    score: float,
    volume: int,
    source: str,
    raw_data: Optional[dict] = None,
) -> Event:
    """Create a sentiment event."""
    event_type = (
        EventType.SENTIMENT_REDDIT if source == "reddit"
        else EventType.SENTIMENT_TWITTER if source == "twitter"
        else EventType.SENTIMENT_AGGREGATED
    )
    
    return Event(
        event_type=event_type,
        timestamp=datetime.now(),
        symbol=symbol,
        source=source,
        data={
            "score": score,
            "volume": volume,
            "raw": raw_data,
        },
    )


def create_order_event(
    event_type: EventType,
    order_id: str,
    client_order_id: str,
    symbol: str,
    side: str,
    qty: float,
    price: Optional[float] = None,
    filled_qty: Optional[float] = None,
    filled_price: Optional[float] = None,
) -> Event:
    """Create an order event."""
    return Event(
        event_type=event_type,
        timestamp=datetime.now(),
        symbol=symbol,
        source="execution_engine",
        correlation_id=client_order_id,
        data={
            "order_id": order_id,
            "client_order_id": client_order_id,
            "side": side,
            "qty": qty,
            "price": price,
            "filled_qty": filled_qty,
            "filled_price": filled_price,
        },
    )
