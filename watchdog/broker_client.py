"""
Direct broker client for the watchdog.

CRITICAL: This is a SEPARATE client from the main bot.
It uses its own API credentials and has no shared state.

This ensures the watchdog can liquidate positions even if
the main bot is hung or corrupted.
"""

import os
from typing import Optional
import structlog

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import OrderStatus

logger = structlog.get_logger(__name__)


class WatchdogBrokerClient:
    """
    Direct broker client for watchdog operations.
    
    This client:
    - Uses SEPARATE API credentials from the main bot
    - Can liquidate positions independently
    - Can cancel orders independently
    - Is the watchdog's "loaded gun" - use with extreme caution
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        paper: bool = True,
    ):
        """
        Initialize watchdog broker client.
        
        Args:
            api_key: Watchdog's Alpaca API key (separate from main bot)
            secret_key: Watchdog's Alpaca secret key
            paper: Use paper trading (ALWAYS True unless you really know what you're doing)
        """
        # Use separate environment variables for watchdog credentials
        self.api_key = api_key or os.environ.get("WATCHDOG_ALPACA_API_KEY")
        self.secret_key = secret_key or os.environ.get("WATCHDOG_ALPACA_SECRET_KEY")
        
        # Fall back to main API keys if watchdog-specific not set
        # (not recommended for production)
        if not self.api_key:
            self.api_key = os.environ.get("ALPACA_API_KEY")
            logger.warning(
                "using_main_api_key_for_watchdog",
                message="Watchdog should have separate credentials for safety",
            )
        
        if not self.secret_key:
            self.secret_key = os.environ.get("ALPACA_SECRET_KEY")
        
        if not self.api_key or not self.secret_key:
            raise ValueError(
                "Watchdog requires API credentials. Set WATCHDOG_ALPACA_API_KEY and "
                "WATCHDOG_ALPACA_SECRET_KEY environment variables."
            )
        
        self.client = TradingClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=paper,
        )
        
        logger.info(
            "watchdog_broker_client_initialized",
            paper=paper,
        )
    
    def get_account(self):
        """Get account information."""
        return self.client.get_account()
    
    def get_clock(self):
        """Get market clock (for health checks)."""
        return self.client.get_clock()
    
    def list_positions(self):
        """List all current positions."""
        return self.client.get_all_positions()
    
    def list_orders(self, status: Optional[str] = None, limit: int = 500):
        """
        List orders with optional status filter.
        
        Args:
            status: Order status filter (open, closed, all)
            limit: Maximum orders to return
        """
        request = GetOrdersRequest(
            status=OrderStatus(status) if status else None,
            limit=limit,
        )
        return self.client.get_orders(request)
    
    def cancel_all_orders(self):
        """
        Cancel ALL open orders.
        
        WARNING: This is a destructive operation. Use only in emergencies.
        """
        logger.critical("watchdog_cancelling_all_orders")
        return self.client.cancel_orders()
    
    def close_all_positions(self):
        """
        Close ALL positions.
        
        WARNING: This is a destructive operation. Use only in emergencies.
        This will submit market orders to close all positions.
        """
        logger.critical("watchdog_closing_all_positions")
        return self.client.close_all_positions()
    
    def close_position(self, symbol: str):
        """
        Close a specific position.
        
        Args:
            symbol: Stock symbol to close
        """
        logger.warning("watchdog_closing_position", symbol=symbol)
        return self.client.close_position(symbol)
    
    def cancel_order(self, order_id: str):
        """
        Cancel a specific order.
        
        Args:
            order_id: Order ID to cancel
        """
        logger.warning("watchdog_cancelling_order", order_id=order_id)
        return self.client.cancel_order_by_id(order_id)
