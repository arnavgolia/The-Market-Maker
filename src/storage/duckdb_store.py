"""
DuckDB storage for analytics and backtesting queries.

DuckDB is used for:
- Complex analytical queries
- Backtesting data retrieval
- Regime analysis
- Performance metrics

It is populated via batch ETL from the AppendOnlyLog.
Strategies read from DuckDB, never write directly.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
import structlog

import duckdb
import pandas as pd

logger = structlog.get_logger(__name__)


class DuckDBStore:
    """
    DuckDB store for analytics and backtesting.
    
    Design principles:
    - Write via ETL only (from AppendOnlyLog)
    - Read-heavy workload optimized
    - Strategies get read-only connections
    - Schema designed for time-series queries
    """
    
    def __init__(self, db_path: str, read_only: bool = False):
        """
        Initialize DuckDB store.
        
        Args:
            db_path: Path to DuckDB file
            read_only: Open in read-only mode (for strategies)
        """
        self.db_path = Path(db_path)
        self.read_only = read_only
        
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connect
        self.conn = duckdb.connect(
            str(self.db_path),
            read_only=read_only,
        )
        
        # Initialize schema if not read-only
        if not read_only:
            self._init_schema()
        
        logger.info(
            "duckdb_store_initialized",
            path=str(self.db_path),
            read_only=read_only,
        )
    
    def _init_schema(self) -> None:
        """Initialize database schema."""
        
        # Events table (generic event storage)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id VARCHAR PRIMARY KEY,
                event_type VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                symbol VARCHAR,
                source VARCHAR,
                correlation_id VARCHAR,
                data JSON,
                
                -- Indexes for common queries
                -- DuckDB handles these automatically, but we hint at them
            )
        """)
        
        # Bars table (OHLCV data for backtesting)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS bars (
                id INTEGER PRIMARY KEY,
                symbol VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                timeframe VARCHAR NOT NULL,
                tier VARCHAR NOT NULL,
                
                open DOUBLE NOT NULL,
                high DOUBLE NOT NULL,
                low DOUBLE NOT NULL,
                close DOUBLE NOT NULL,
                volume DOUBLE NOT NULL,
                
                -- Cost modeling
                estimated_spread_bps DOUBLE,
                
                -- Composite index for efficient queries
                UNIQUE (symbol, timestamp, timeframe)
            )
        """)
        
        # Sentiment table (aggregated sentiment scores)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sentiment (
                id INTEGER PRIMARY KEY,
                symbol VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                source VARCHAR NOT NULL,
                
                score DOUBLE NOT NULL,
                volume INTEGER,
                
                -- Calibration data
                is_calibrated BOOLEAN DEFAULT FALSE,
                lead_lag_hours DOUBLE,
                correlation DOUBLE,
                
                UNIQUE (symbol, timestamp, source)
            )
        """)
        
        # Trades table (executed trades for performance analysis)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                trade_id VARCHAR PRIMARY KEY,
                order_id VARCHAR NOT NULL,
                client_order_id VARCHAR,
                symbol VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                
                side VARCHAR NOT NULL,
                qty DOUBLE NOT NULL,
                price DOUBLE NOT NULL,
                
                -- Cost analysis
                expected_price DOUBLE,
                slippage_bps DOUBLE,
                commission DOUBLE DEFAULT 0,
                
                -- Strategy attribution
                strategy_name VARCHAR,
                signal_id VARCHAR
            )
        """)
        
        # Regime table (regime classifications over time)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS regimes (
                id INTEGER PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL,
                symbol VARCHAR,  -- NULL for market-wide regime
                
                -- Regime classification
                trend_regime VARCHAR NOT NULL,
                vol_regime VARCHAR NOT NULL,
                combined_regime VARCHAR NOT NULL,
                
                -- Indicators
                adx DOUBLE,
                fast_vol DOUBLE,
                slow_vol DOUBLE,
                vol_ratio DOUBLE,
                
                -- Trading implications
                momentum_enabled BOOLEAN,
                position_scale DOUBLE,
                
                UNIQUE (timestamp, symbol)
            )
        """)
        
        # Performance metrics (daily snapshots)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS performance (
                date DATE PRIMARY KEY,
                
                -- Portfolio metrics
                equity DOUBLE NOT NULL,
                cash DOUBLE NOT NULL,
                positions_value DOUBLE NOT NULL,
                
                -- Returns
                daily_return DOUBLE,
                cumulative_return DOUBLE,
                
                -- Risk metrics
                sharpe_30d DOUBLE,
                sortino_30d DOUBLE,
                max_drawdown DOUBLE,
                current_drawdown DOUBLE,
                
                -- Strategy breakdown (JSON)
                strategy_attribution JSON
            )
        """)
        
        self.conn.commit()
        logger.info("duckdb_schema_initialized")
    
    # =========================================================================
    # Bar Data Operations
    # =========================================================================
    
    def insert_bars(self, bars: list[dict]) -> int:
        """
        Insert bars into the database.
        
        Args:
            bars: List of bar dictionaries with keys:
                  symbol, timestamp, timeframe, tier, open, high, low, close, volume
        
        Returns:
            Number of bars inserted
        """
        if not bars:
            return 0
        
        df = pd.DataFrame(bars)
        
        # Use INSERT OR REPLACE for upsert behavior
        self.conn.execute("""
            INSERT OR REPLACE INTO bars 
            (symbol, timestamp, timeframe, tier, open, high, low, close, volume, estimated_spread_bps)
            SELECT * FROM df
        """)
        
        self.conn.commit()
        logger.debug("bars_inserted", count=len(bars))
        return len(bars)
    
    def get_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1Day",
        exclude_tier0: bool = True,
    ) -> pd.DataFrame:
        """
        Get bars for backtesting.
        
        Args:
            symbol: Stock symbol
            start: Start datetime
            end: End datetime
            timeframe: Bar timeframe
            exclude_tier0: If True, exclude TIER_0 data (yfinance)
        
        Returns:
            DataFrame with OHLCV data
        """
        tier_filter = "AND tier != 'TIER_0_UNIVERSE'" if exclude_tier0 else ""
        
        query = f"""
            SELECT 
                symbol, timestamp, open, high, low, close, volume,
                tier, estimated_spread_bps
            FROM bars
            WHERE symbol = ?
              AND timestamp >= ?
              AND timestamp <= ?
              AND timeframe = ?
              {tier_filter}
            ORDER BY timestamp
        """
        
        result = self.conn.execute(query, [symbol, start, end, timeframe]).fetchdf()
        
        if exclude_tier0 and not result.empty:
            # Verify no TIER_0 data slipped through
            tier0_count = (result["tier"] == "TIER_0_UNIVERSE").sum()
            if tier0_count > 0:
                logger.critical(
                    "TIER0_DATA_IN_BACKTEST",
                    count=tier0_count,
                    message="TIER_0 data found in backtest query. Results invalid.",
                )
                raise ValueError(f"TIER_0 data found in backtest: {tier0_count} bars")
        
        return result
    
    def get_bars_multi(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        timeframe: str = "1Day",
    ) -> dict[str, pd.DataFrame]:
        """Get bars for multiple symbols."""
        result = {}
        for symbol in symbols:
            result[symbol] = self.get_bars(symbol, start, end, timeframe)
        return result
    
    # =========================================================================
    # Sentiment Operations
    # =========================================================================
    
    def insert_sentiment(self, records: list[dict]) -> int:
        """Insert sentiment records."""
        if not records:
            return 0
        
        df = pd.DataFrame(records)
        
        self.conn.execute("""
            INSERT OR REPLACE INTO sentiment
            (symbol, timestamp, source, score, volume, is_calibrated, lead_lag_hours, correlation)
            SELECT * FROM df
        """)
        
        self.conn.commit()
        return len(records)
    
    def get_sentiment(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        source: Optional[str] = None,
    ) -> pd.DataFrame:
        """Get sentiment data for analysis."""
        source_filter = "AND source = ?" if source else ""
        params = [symbol, start, end]
        if source:
            params.append(source)
        
        query = f"""
            SELECT *
            FROM sentiment
            WHERE symbol = ?
              AND timestamp >= ?
              AND timestamp <= ?
              {source_filter}
            ORDER BY timestamp
        """
        
        return self.conn.execute(query, params).fetchdf()
    
    # =========================================================================
    # Regime Operations
    # =========================================================================
    
    def insert_regime(self, regime: dict) -> None:
        """Insert a regime classification."""
        self.conn.execute("""
            INSERT OR REPLACE INTO regimes
            (timestamp, symbol, trend_regime, vol_regime, combined_regime,
             adx, fast_vol, slow_vol, vol_ratio, momentum_enabled, position_scale)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            regime["timestamp"],
            regime.get("symbol"),
            regime["trend_regime"],
            regime["vol_regime"],
            regime["combined_regime"],
            regime.get("adx"),
            regime.get("fast_vol"),
            regime.get("slow_vol"),
            regime.get("vol_ratio"),
            regime.get("momentum_enabled"),
            regime.get("position_scale"),
        ])
        self.conn.commit()
    
    def get_latest_regime(self, symbol: Optional[str] = None) -> Optional[dict]:
        """Get the most recent regime classification."""
        symbol_filter = "WHERE symbol = ?" if symbol else "WHERE symbol IS NULL"
        params = [symbol] if symbol else []
        
        query = f"""
            SELECT *
            FROM regimes
            {symbol_filter}
            ORDER BY timestamp DESC
            LIMIT 1
        """
        
        result = self.conn.execute(query, params).fetchdf()
        
        if result.empty:
            return None
        
        return result.iloc[0].to_dict()
    
    # =========================================================================
    # Performance Operations
    # =========================================================================
    
    def insert_performance(self, metrics: dict) -> None:
        """Insert daily performance metrics."""
        # Handle both "date" and "timestamp" keys
        if "date" in metrics:
            date_value = metrics["date"]
        elif "timestamp" in metrics:
            # Convert timestamp to date
            if isinstance(metrics["timestamp"], str):
                from datetime import datetime
                date_value = datetime.fromisoformat(metrics["timestamp"]).date()
            else:
                date_value = metrics["timestamp"].date()
        else:
            # Use today's date as fallback
            date_value = datetime.now().date()
        
        self.conn.execute("""
            INSERT OR REPLACE INTO performance
            (date, equity, cash, positions_value, daily_return, cumulative_return,
             sharpe_30d, sortino_30d, max_drawdown, current_drawdown, strategy_attribution)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            date_value,
            metrics["equity"],
            metrics["cash"],
            metrics["positions_value"],
            metrics.get("daily_return"),
            metrics.get("cumulative_return"),
            metrics.get("sharpe_30d"),
            metrics.get("sortino_30d"),
            metrics.get("max_drawdown"),
            metrics.get("current_drawdown"),
            json.dumps(metrics.get("strategy_attribution", {})),
        ])
        self.conn.commit()
    
    def get_performance_history(
        self,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Get performance history for analysis."""
        return self.conn.execute("""
            SELECT *
            FROM performance
            WHERE date >= ?
              AND date <= ?
            ORDER BY date
        """, [start.date(), end.date()]).fetchdf()
    
    # =========================================================================
    # Trade Operations
    # =========================================================================
    
    def insert_trade(self, trade: dict) -> None:
        """Insert an executed trade."""
        self.conn.execute("""
            INSERT INTO trades
            (trade_id, order_id, client_order_id, symbol, timestamp,
             side, qty, price, expected_price, slippage_bps, commission,
             strategy_name, signal_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            trade["trade_id"],
            trade["order_id"],
            trade.get("client_order_id"),
            trade["symbol"],
            trade["timestamp"],
            trade["side"],
            trade["qty"],
            trade["price"],
            trade.get("expected_price"),
            trade.get("slippage_bps"),
            trade.get("commission", 0),
            trade.get("strategy_name"),
            trade.get("signal_id"),
        ])
        self.conn.commit()
    
    def get_trades(
        self,
        start: datetime,
        end: datetime,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
    ) -> pd.DataFrame:
        """Get trade history for analysis."""
        filters = ["timestamp >= ?", "timestamp <= ?"]
        params = [start, end]
        
        if symbol:
            filters.append("symbol = ?")
            params.append(symbol)
        
        if strategy:
            filters.append("strategy_name = ?")
            params.append(strategy)
        
        query = f"""
            SELECT *
            FROM trades
            WHERE {' AND '.join(filters)}
            ORDER BY timestamp
        """
        
        return self.conn.execute(query, params).fetchdf()
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def execute(self, query: str, params: list = None) -> Any:
        """Execute a raw query (for advanced analytics)."""
        if params:
            return self.conn.execute(query, params)
        return self.conn.execute(query)
    
    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()
        logger.info("duckdb_store_closed", path=str(self.db_path))
