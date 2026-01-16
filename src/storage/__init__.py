"""
Storage layer with separated concerns.

- AppendOnlyLog: High-throughput event capture (no locks)
- DuckDB: Analytics and backtesting queries
- Redis: Live state (positions, orders)

This architecture eliminates the SQLite concurrency bottleneck
identified in the adversarial review.
"""

from src.storage.append_log import AppendOnlyLog, Event
from src.storage.duckdb_store import DuckDBStore
from src.storage.redis_state import RedisStateStore

__all__ = ["AppendOnlyLog", "Event", "DuckDBStore", "RedisStateStore"]
