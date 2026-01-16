"""
Free data client for simulation mode - no personal information required.

This client aggregates multiple free data sources:
- yfinance (no API key needed)
- Alpha Vantage (free API key, email only)
- Finnhub (free API key, email only)

All sources only require email signup, no SSN or identity verification.
"""

from datetime import datetime, timedelta
from typing import Optional, List
import structlog
import time

import yfinance as yf
import pandas as pd

from src.data.tiers import Bar, DataTier

logger = structlog.get_logger(__name__)


class FreeDataClient:
    """
    Unified free data client for simulation mode.
    
    Uses multiple free data sources with automatic fallback.
    No personal information (SSN, identity verification) required.
    """
    
    def __init__(
        self,
        alpha_vantage_key: Optional[str] = None,
        finnhub_key: Optional[str] = None,
    ):
        """
        Initialize free data client.
        
        Args:
            alpha_vantage_key: Optional Alpha Vantage API key (free at alphavantage.co)
            finnhub_key: Optional Finnhub API key (free at finnhub.io)
        """
        self.alpha_vantage_key = alpha_vantage_key
        self.finnhub_key = finnhub_key
        
        # Rate limiting
        self.alpha_vantage_last_call = 0
        self.alpha_vantage_calls_today = 0
        self.alpha_vantage_max_per_min = 5
        self.alpha_vantage_max_per_day = 500
        
        self.finnhub_last_call = 0
        self.finnhub_max_per_min = 60
        
        logger.info(
            "free_data_client_initialized",
            has_alpha_vantage=bool(alpha_vantage_key),
            has_finnhub=bool(finnhub_key),
        )
    
    def get_historical_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1Day",
    ) -> List[Bar]:
        """
        Get historical bars using free data sources.
        
        Priority: yfinance → Alpha Vantage → Finnhub
        
        Args:
            symbol: Stock symbol
            start: Start datetime
            end: End datetime
            timeframe: Bar timeframe (1Day, 1Hour, etc.)
        
        Returns:
            List of Bar objects
        """
        # Try yfinance first (no API key needed)
        try:
            bars = self._get_yfinance_bars(symbol, start, end, timeframe)
            if bars:
                logger.debug("using_yfinance_data", symbol=symbol, count=len(bars))
                return bars
        except Exception as e:
            logger.warning("yfinance_failed", symbol=symbol, error=str(e))
        
        # Try Alpha Vantage if available
        if self.alpha_vantage_key:
            try:
                bars = self._get_alpha_vantage_bars(symbol, start, end, timeframe)
                if bars:
                    logger.debug("using_alpha_vantage_data", symbol=symbol, count=len(bars))
                    return bars
            except Exception as e:
                logger.warning("alpha_vantage_failed", symbol=symbol, error=str(e))
        
        # Try Finnhub if available
        if self.finnhub_key:
            try:
                bars = self._get_finnhub_bars(symbol, start, end, timeframe)
                if bars:
                    logger.debug("using_finnhub_data", symbol=symbol, count=len(bars))
                    return bars
            except Exception as e:
                logger.warning("finnhub_failed", symbol=symbol, error=str(e))
        
        logger.error("all_data_sources_failed", symbol=symbol)
        return []
    
    def _get_yfinance_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> List[Bar]:
        """Get bars from yfinance (no API key needed)."""
        # Map timeframe to yfinance interval
        interval_map = {
            "1Day": "1d",
            "1Hour": "1h",
            "4Hour": "4h",
            "15Min": "15m",
            "5Min": "5m",
            "1Min": "1m",
        }
        
        interval = interval_map.get(timeframe, "1d")
        
        # Fetch data
        ticker = yf.Ticker(symbol)
        df = ticker.history(
            start=start,
            end=end,
            interval=interval,
            auto_adjust=False,  # Get unadjusted prices
            prepost=False,
        )
        
        if df.empty:
            return []
        
        # Convert to Bar objects
        bars = []
        for idx, row in df.iterrows():
            # Use unadjusted close if available, otherwise use close
            close = row.get('Close', row.get('close', 0))
            open_price = row.get('Open', row.get('open', close))
            high = row.get('High', row.get('high', close))
            low = row.get('Low', row.get('low', close))
            volume = row.get('Volume', row.get('volume', 0))
            
            # Convert timestamp
            if isinstance(idx, pd.Timestamp):
                timestamp = idx.to_pydatetime()
            else:
                timestamp = datetime.fromisoformat(str(idx))
            
            bar = Bar(
                symbol=symbol,
                timestamp=timestamp,
                open=float(open_price),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=float(volume),
                tier=DataTier.TIER_1_VALIDATION,  # Mark as valid for trading
                quality="GOOD",
            )
            bars.append(bar)
        
        return bars
    
    def _get_alpha_vantage_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> List[Bar]:
        """Get bars from Alpha Vantage (requires free API key)."""
        try:
            from alpha_vantage.timeseries import TimeSeries
        except ImportError:
            logger.warning("alpha_vantage_not_installed")
            return []
        
        # Check rate limits
        now = time.time()
        if now - self.alpha_vantage_last_call < 12:  # 5 calls/min = 12 sec between calls
            time.sleep(12 - (now - self.alpha_vantage_last_call))
        
        if self.alpha_vantage_calls_today >= self.alpha_vantage_max_per_day:
            logger.warning("alpha_vantage_daily_limit_reached")
            return []
        
        try:
            ts = TimeSeries(key=self.alpha_vantage_key, output_format='pandas')
            
            # Alpha Vantage only supports daily for free tier
            if timeframe != "1Day":
                logger.warning("alpha_vantage_only_daily", requested=timeframe)
                return []
            
            data, meta = ts.get_daily(symbol=symbol, outputsize='full')
            
            if data.empty:
                return []
            
            # Filter by date range
            data = data[(data.index >= start) & (data.index <= end)]
            
            bars = []
            for idx, row in data.iterrows():
                timestamp = idx.to_pydatetime() if isinstance(idx, pd.Timestamp) else datetime.fromisoformat(str(idx))
                
                bar = Bar(
                    symbol=symbol,
                    timestamp=timestamp,
                    open=float(row['1. open']),
                    high=float(row['2. high']),
                    low=float(row['3. low']),
                    close=float(row['4. close']),
                    volume=float(row['5. volume']),
                    tier=DataTier.TIER_1_VALIDATION,
                    quality="GOOD",
                )
                bars.append(bar)
            
            self.alpha_vantage_last_call = time.time()
            self.alpha_vantage_calls_today += 1
            
            return bars
            
        except Exception as e:
            logger.error("alpha_vantage_error", symbol=symbol, error=str(e))
            return []
    
    def _get_finnhub_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> List[Bar]:
        """Get bars from Finnhub (requires free API key)."""
        try:
            import finnhub
        except ImportError:
            logger.warning("finnhub_not_installed")
            return []
        
        # Check rate limits
        now = time.time()
        if now - self.finnhub_last_call < 1:  # 60 calls/min = 1 sec between calls
            time.sleep(1 - (now - self.finnhub_last_call))
        
        try:
            finnhub_client = finnhub.Client(api_key=self.finnhub_key)
            
            # Convert timeframe to Finnhub resolution
            resolution_map = {
                "1Day": "D",
                "1Hour": "60",
                "4Hour": "240",
                "15Min": "15",
                "5Min": "5",
                "1Min": "1",
            }
            
            resolution = resolution_map.get(timeframe, "D")
            
            # Finnhub uses Unix timestamps
            start_ts = int(start.timestamp())
            end_ts = int(end.timestamp())
            
            # Fetch candlestick data
            result = finnhub_client.stock_candles(symbol, resolution, start_ts, end_ts)
            
            if result['s'] != 'ok' or not result.get('c'):
                return []
            
            bars = []
            for i in range(len(result['t'])):
                bar = Bar(
                    symbol=symbol,
                    timestamp=datetime.fromtimestamp(result['t'][i]),
                    open=float(result['o'][i]),
                    high=float(result['h'][i]),
                    low=float(result['l'][i]),
                    close=float(result['c'][i]),
                    volume=float(result['v'][i]),
                    tier=DataTier.TIER_1_VALIDATION,
                    quality="GOOD",
                )
                bars.append(bar)
            
            self.finnhub_last_call = time.time()
            return bars
            
        except Exception as e:
            logger.error("finnhub_error", symbol=symbol, error=str(e))
            return []
    
    def get_latest_quote(self, symbol: str) -> Optional[float]:
        """
        Get latest quote price.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Latest price or None
        """
        # Try yfinance first
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d", interval="1m")
            if not data.empty:
                return float(data['Close'].iloc[-1])
        except Exception as e:
            logger.warning("yfinance_quote_failed", symbol=symbol, error=str(e))
        
        # Try Finnhub if available
        if self.finnhub_key:
            try:
                import finnhub
                finnhub_client = finnhub.Client(api_key=self.finnhub_key)
                quote = finnhub_client.quote(symbol)
                if quote and 'c' in quote:
                    return float(quote['c'])
            except Exception as e:
                logger.warning("finnhub_quote_failed", symbol=symbol, error=str(e))
        
        return None
    
    def get_account(self):
        """Get mock account for simulation."""
        class MockAccount:
            def __init__(self):
                self.equity = 100000.0
                self.cash = 100000.0
                self.buying_power = 200000.0
                self.status = type('Status', (), {'value': 'ACTIVE'})()
        return MockAccount()
    
    def get_clock(self):
        """Get market clock (simulated - always open for simulation)."""
        class MockClock:
            is_open = True
            timestamp = datetime.now()
            next_open = datetime.now() + timedelta(days=1)
            next_close = datetime.now() + timedelta(days=1, hours=6)
        return MockClock()
    
    def get_positions(self):
        """Get positions (empty for simulation)."""
        return []
    
    def get_orders(self, **kwargs):
        """Get orders (empty for simulation)."""
        return []
