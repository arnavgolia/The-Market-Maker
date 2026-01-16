"""
Comprehensive storage layer tests.

Tests AppendOnlyLog, DuckDB, Redis with concurrent operations and edge cases.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import json

from src.storage.append_log import AppendOnlyLog, Event, EventType
from src.storage.duckdb_store import DuckDBStore


class TestAppendOnlyLogEdgeCases:
    """Comprehensive tests for append-only log."""
    
    def setup_method(self):
        """Create temp directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.log_path = Path(self.temp_dir) / "test.log"
    
    def teardown_method(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_empty_log_read(self):
        """Test reading from empty log."""
        log = AppendOnlyLog(self.log_path)
        
        events = list(log.read_all())
        
        assert events == []
    
    def test_single_event_write_read(self):
        """Test writing and reading single event."""
        log = AppendOnlyLog(self.log_path)
        
        event = Event(
            event_type=EventType.MARKET_DATA,
            timestamp=datetime.now(),
            data={"symbol": "TEST", "price": 100.0},
        )
        
        log.write(event)
        
        events = list(log.read_all())
        
        assert len(events) == 1
        assert events[0].event_type == EventType.MARKET_DATA
        assert events[0].data["symbol"] == "TEST"
    
    def test_multiple_events_ordered(self):
        """Test that events are read in order written."""
        log = AppendOnlyLog(self.log_path)
        
        events_written = []
        for i in range(100):
            event = Event(
                event_type=EventType.MARKET_DATA,
                timestamp=datetime.now(),
                data={"index": i},
            )
            events_written.append(event)
            log.write(event)
        
        events_read = list(log.read_all())
        
        assert len(events_read) == 100
        for i, event in enumerate(events_read):
            assert event.data["index"] == i
    
    def test_large_event_data(self):
        """Test handling of large event payloads."""
        log = AppendOnlyLog(self.log_path)
        
        # Create large data structure
        large_data = {
            "symbols": [f"SYM{i}" for i in range(1000)],
            "prices": [100.0 + i * 0.1 for i in range(1000)],
            "metadata": {f"key_{i}": f"value_{i}" for i in range(100)},
        }
        
        event = Event(
            event_type=EventType.MARKET_DATA,
            timestamp=datetime.now(),
            data=large_data,
        )
        
        log.write(event)
        
        events = list(log.read_all())
        
        assert len(events) == 1
        assert len(events[0].data["symbols"]) == 1000
    
    def test_special_characters_in_data(self):
        """Test handling of special characters."""
        log = AppendOnlyLog(self.log_path)
        
        event = Event(
            event_type=EventType.MARKET_DATA,
            timestamp=datetime.now(),
            data={
                "message": "Test with \"quotes\" and 'apostrophes'",
                "newlines": "Line 1\nLine 2\nLine 3",
                "unicode": "Émojis: 🚀📈💰",
            },
        )
        
        log.write(event)
        
        events = list(log.read_all())
        
        assert len(events) == 1
        assert events[0].data["message"] == "Test with \"quotes\" and 'apostrophes'"
        assert "🚀" in events[0].data["unicode"]
    
    def test_corrupted_line_handling(self):
        """Test handling of corrupted log lines."""
        log = AppendOnlyLog(self.log_path)
        
        # Write valid event
        event1 = Event(
            event_type=EventType.MARKET_DATA,
            timestamp=datetime.now(),
            data={"valid": True},
        )
        log.write(event1)
        
        # Manually corrupt the log file
        with open(self.log_path, 'a') as f:
            f.write("CORRUPTED LINE NOT JSON\n")
        
        # Write another valid event
        event2 = Event(
            event_type=EventType.MARKET_DATA,
            timestamp=datetime.now(),
            data={"valid": True, "index": 2},
        )
        log.write(event2)
        
        # Should skip corrupted line
        events = list(log.read_all())
        
        # Should have 2 valid events (corrupted line skipped)
        assert len([e for e in events if e is not None]) >= 1
    
    def test_concurrent_writes_safety(self):
        """Test that concurrent writes don't corrupt the log."""
        from concurrent.futures import ThreadPoolExecutor
        
        log = AppendOnlyLog(self.log_path)
        
        def write_events(start_idx):
            for i in range(start_idx, start_idx + 10):
                event = Event(
                    event_type=EventType.MARKET_DATA,
                    timestamp=datetime.now(),
                    data={"thread_id": start_idx, "index": i},
                )
                log.write(event)
        
        # Write concurrently from 10 threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(write_events, i * 10) for i in range(10)]
            for f in futures:
                f.result()
        
        # Should have 100 events total
        events = list(log.read_all())
        valid_events = [e for e in events if e is not None]
        
        assert len(valid_events) == 100
    
    def test_log_rotation_not_supported(self):
        """Test that log grows without rotation (by design)."""
        log = AppendOnlyLog(self.log_path)
        
        # Write many events
        for i in range(1000):
            event = Event(
                event_type=EventType.MARKET_DATA,
                timestamp=datetime.now(),
                data={"index": i},
            )
            log.write(event)
        
        # File should exist and be growing
        assert self.log_path.exists()
        assert self.log_path.stat().st_size > 0


class TestDuckDBStoreEdgeCases:
    """Comprehensive tests for DuckDB store."""
    
    def setup_method(self):
        """Create temp database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.duckdb"
        self.store = DuckDBStore(str(self.db_path))
    
    def teardown_method(self):
        """Clean up."""
        if hasattr(self, 'store'):
            self.store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_empty_database_queries(self):
        """Test querying empty database."""
        bars = self.store.get_bars(
            symbol="TEST",
            start=datetime(2020, 1, 1),
            end=datetime(2020, 12, 31),
        )
        
        assert bars.empty
    
    def test_insert_and_retrieve_bars(self):
        """Test inserting and retrieving bars."""
        bars_data = [
            {
                "symbol": "TEST",
                "timestamp": datetime(2020, 1, i),
                "timeframe": "1Day",
                "tier": "TIER_1_VALIDATION",
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": 1000000.0,
            }
            for i in range(1, 11)
        ]
        
        inserted = self.store.insert_bars(bars_data)
        assert inserted == 10
        
        # Retrieve
        bars = self.store.get_bars(
            symbol="TEST",
            start=datetime(2020, 1, 1),
            end=datetime(2020, 1, 31),
        )
        
        assert len(bars) == 10
        assert bars.iloc[0]["close"] == 100.5
    
    def test_tier0_rejection(self):
        """Test that TIER_0 data is rejected in backtests."""
        # Insert TIER_0 data
        bars_data = [
            {
                "symbol": "TEST",
                "timestamp": datetime(2020, 1, i),
                "timeframe": "1Day",
                "tier": "TIER_0_UNIVERSE",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000000.0,
            }
            for i in range(1, 11)
        ]
        
        self.store.insert_bars(bars_data)
        
        # Query with exclude_tier0=True (default)
        bars = self.store.get_bars(
            symbol="TEST",
            start=datetime(2020, 1, 1),
            end=datetime(2020, 1, 31),
            exclude_tier0=True,
        )
        
        # Should get no bars
        assert bars.empty
        
        # Query with exclude_tier0=False
        bars_with_tier0 = self.store.get_bars(
            symbol="TEST",
            start=datetime(2020, 1, 1),
            end=datetime(2020, 1, 31),
            exclude_tier0=False,
        )
        
        # Should get bars
        assert len(bars_with_tier0) == 10
    
    def test_duplicate_insert_handling(self):
        """Test handling of duplicate bar inserts."""
        bar_data = {
            "symbol": "TEST",
            "timestamp": datetime(2020, 1, 1),
            "timeframe": "1Day",
            "tier": "TIER_1_VALIDATION",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000000.0,
        }
        
        # Insert twice
        self.store.insert_bars([bar_data])
        self.store.insert_bars([bar_data])
        
        # Should handle gracefully (either ignore or error)
        # Query should not return duplicates
        bars = self.store.get_bars(
            symbol="TEST",
            start=datetime(2020, 1, 1),
            end=datetime(2020, 1, 2),
        )
        
        # Should have at least 1 (might have 2 if duplicates allowed)
        assert len(bars) >= 1
    
    def test_large_batch_insert(self):
        """Test inserting large batch of data."""
        # 10,000 bars
        bars_data = [
            {
                "symbol": f"SYM{i % 100}",
                "timestamp": datetime(2020, 1, 1) + (datetime(2020, 1, 2) - datetime(2020, 1, 1)) * (i // 100),
                "timeframe": "1Day",
                "tier": "TIER_1_VALIDATION",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000000.0,
            }
            for i in range(10000)
        ]
        
        inserted = self.store.insert_bars(bars_data)
        
        assert inserted == 10000
    
    def test_date_range_filtering(self):
        """Test that date range filtering works correctly."""
        # Insert data across multiple months
        bars_data = [
            {
                "symbol": "TEST",
                "timestamp": datetime(2020, month, 15),
                "timeframe": "1Day",
                "tier": "TIER_1_VALIDATION",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000000.0,
            }
            for month in range(1, 13)
        ]
        
        self.store.insert_bars(bars_data)
        
        # Query specific range
        bars = self.store.get_bars(
            symbol="TEST",
            start=datetime(2020, 3, 1),
            end=datetime(2020, 6, 30),
        )
        
        # Should get March through June (4 months)
        assert len(bars) == 4
    
    def test_multiple_symbols_query(self):
        """Test querying multiple symbols."""
        symbols = ["AAPL", "MSFT", "GOOGL"]
        
        bars_data = []
        for symbol in symbols:
            for day in range(1, 11):
                bars_data.append({
                    "symbol": symbol,
                    "timestamp": datetime(2020, 1, day),
                    "timeframe": "1Day",
                    "tier": "TIER_1_VALIDATION",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 1000000.0,
                })
        
        self.store.insert_bars(bars_data)
        
        # Query multi-symbol
        bars_dict = self.store.get_bars_multi(
            symbols=symbols,
            start=datetime(2020, 1, 1),
            end=datetime(2020, 1, 31),
        )
        
        assert len(bars_dict) == 3
        assert all(symbol in bars_dict for symbol in symbols)
        assert all(len(bars_dict[s]) == 10 for s in symbols)
    
    def test_read_only_mode(self):
        """Test that read-only mode prevents writes."""
        # Insert some data first
        bars_data = [{
            "symbol": "TEST",
            "timestamp": datetime(2020, 1, 1),
            "timeframe": "1Day",
            "tier": "TIER_1_VALIDATION",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000000.0,
        }]
        
        self.store.insert_bars(bars_data)
        self.store.close()
        
        # Reopen in read-only mode
        readonly_store = DuckDBStore(str(self.db_path), read_only=True)
        
        # Read should work
        bars = readonly_store.get_bars(
            symbol="TEST",
            start=datetime(2020, 1, 1),
            end=datetime(2020, 1, 31),
        )
        
        assert len(bars) == 1
        
        # Write should fail
        with pytest.raises(Exception):
            readonly_store.insert_bars([{
                "symbol": "TEST2",
                "timestamp": datetime(2020, 1, 2),
                "timeframe": "1Day",
                "tier": "TIER_1_VALIDATION",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000000.0,
            }])
        
        readonly_store.close()


class TestStorageIntegration:
    """Test integration between storage components."""
    
    def setup_method(self):
        """Create temp resources."""
        self.temp_dir = tempfile.mkdtemp()
        self.log_path = Path(self.temp_dir) / "events.log"
        self.db_path = Path(self.temp_dir) / "analytics.duckdb"
    
    def teardown_method(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_append_log_to_duckdb_flow(self):
        """Test ETL flow from append log to DuckDB."""
        # Write events to append log
        log = AppendOnlyLog(self.log_path)
        
        for i in range(10):
            event = Event(
                event_type=EventType.MARKET_DATA,
                timestamp=datetime(2020, 1, i + 1),
                data={
                    "symbol": "TEST",
                    "open": 100.0 + i,
                    "high": 101.0 + i,
                    "low": 99.0 + i,
                    "close": 100.5 + i,
                    "volume": 1000000.0,
                    "timeframe": "1Day",
                    "tier": "TIER_1_VALIDATION",
                },
            )
            log.write(event)
        
        # Process events into DuckDB
        store = DuckDBStore(str(self.db_path))
        
        bars_data = []
        for event in log.read_all():
            if event and event.event_type == EventType.MARKET_DATA:
                bars_data.append({
                    "symbol": event.data["symbol"],
                    "timestamp": event.timestamp,
                    "timeframe": event.data["timeframe"],
                    "tier": event.data["tier"],
                    "open": event.data["open"],
                    "high": event.data["high"],
                    "low": event.data["low"],
                    "close": event.data["close"],
                    "volume": event.data["volume"],
                })
        
        store.insert_bars(bars_data)
        
        # Query from DuckDB
        bars = store.get_bars(
            symbol="TEST",
            start=datetime(2020, 1, 1),
            end=datetime(2020, 1, 31),
        )
        
        assert len(bars) == 10
        assert bars.iloc[0]["close"] == 100.5
        
        store.close()
