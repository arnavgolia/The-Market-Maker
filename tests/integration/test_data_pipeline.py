"""
Integration test for data pipeline.

Tests the full flow:
Data Ingestion → Append Log → ETL → DuckDB
"""

import pytest
from datetime import datetime, timedelta

from src.data.ingestion.alpaca_client import AlpacaDataClient
from src.storage.append_log import AppendOnlyLog, Event, EventType
from src.storage.duckdb_store import DuckDBStore
from src.storage.etl_pipeline import ETLPipeline


@pytest.fixture
def append_log(tmp_path):
    """Create append log for testing."""
    log_path = tmp_path / "events.jsonl"
    return AppendOnlyLog(str(log_path))


@pytest.fixture
def duckdb_store(tmp_path):
    """Create DuckDB store for testing."""
    db_path = tmp_path / "test.duckdb"
    return DuckDBStore(str(db_path))


@pytest.fixture
def etl_pipeline(append_log, duckdb_store):
    """Create ETL pipeline for testing."""
    return ETLPipeline(
        append_log=append_log,
        duckdb_store=duckdb_store,
        batch_interval_seconds=1,
    )


class TestDataPipeline:
    """Test data pipeline integration."""
    
    def test_append_log_to_duckdb(self, append_log, duckdb_store, etl_pipeline):
        """Test that events flow from append log to DuckDB."""
        # Create test events
        event1 = Event(
            event_type=EventType.BAR,
            timestamp=datetime.now(),
            symbol="AAPL",
            data={
                "open": 150.0,
                "high": 152.0,
                "low": 149.0,
                "close": 151.0,
                "volume": 1000000,
                "timeframe": "1Day",
                "tier": "TIER_1_VALIDATION",
            },
        )
        
        append_log.write(event1)
        
        # Run ETL
        summary = etl_pipeline.run_once()
        
        assert summary["events_processed"] > 0
        assert summary["bars_inserted"] > 0
        
        # Verify data in DuckDB
        bars = duckdb_store.get_bars(
            symbol="AAPL",
            start=datetime.now() - timedelta(days=1),
            end=datetime.now(),
            timeframe="1Day",
        )
        
        assert not bars.empty
        assert len(bars) > 0
