"""
Paper broker for simulated trading.

This simulates order execution with realistic:
- Fill delays
- Partial fills
- Slippage
- Spread costs

Used for backtesting and paper trading.
"""

from datetime import datetime
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


class PaperBroker:
    """
    Paper trading broker simulation.
    
    This simulates realistic order execution for paper trading.
    In production, this would be replaced with the actual Alpaca broker.
    """
    
    def __init__(
        self,
        initial_cash: float = 100000.0,
        spread_bps: float = 10.0,
        slippage_bps: float = 5.0,
    ):
        """
        Initialize paper broker.
        
        Args:
            initial_cash: Starting cash
            spread_bps: Bid-ask spread in basis points
            slippage_bps: Slippage in basis points
        """
        self.cash = initial_cash
        self.positions: dict[str, dict] = {}  # symbol -> position data
        self.orders: dict[str, dict] = {}  # order_id -> order data
        self.spread_bps = spread_bps
        self.slippage_bps = slippage_bps
        
        logger.info(
            "paper_broker_initialized",
            initial_cash=initial_cash,
            spread_bps=spread_bps,
            slippage_bps=slippage_bps,
        )
    
    def submit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        order_type: str = "limit",
        limit_price: Optional[float] = None,
        current_price: float = None,
    ) -> dict:
        """
        Submit an order (simulated).
        
        Returns order with simulated fill.
        """
        # Simulate fill price
        if order_type == "market":
            # Market order: pay spread + slippage
            fill_price = current_price * (1 + (self.spread_bps + self.slippage_bps) / 10000)
            if side == "sell":
                fill_price = current_price * (1 - (self.spread_bps + self.slippage_bps) / 10000)
        else:
            # Limit order: fill at limit (if favorable)
            fill_price = limit_price or current_price
        
        # Calculate cost
        cost = fill_price * qty
        
        # Check if we have enough cash (for buys)
        if side == "buy" and cost > self.cash:
            logger.warning(
                "insufficient_cash",
                cash=self.cash,
                required=cost,
            )
            return {
                "status": "rejected",
                "reason": "insufficient_cash",
            }
        
        # Execute order
        if side == "buy":
            self.cash -= cost
            if symbol in self.positions:
                # Add to existing position
                pos = self.positions[symbol]
                total_qty = pos["qty"] + qty
                total_cost = pos["avg_price"] * pos["qty"] + cost
                pos["qty"] = total_qty
                pos["avg_price"] = total_cost / total_qty
            else:
                # New position
                self.positions[symbol] = {
                    "qty": qty,
                    "avg_price": fill_price,
                }
        else:  # sell
            if symbol not in self.positions:
                return {
                    "status": "rejected",
                    "reason": "no_position",
                }
            
            pos = self.positions[symbol]
            if qty > pos["qty"]:
                return {
                    "status": "rejected",
                    "reason": "insufficient_position",
                }
            
            # Reduce position
            pos["qty"] -= qty
            self.cash += fill_price * qty
            
            # Remove position if fully closed
            if pos["qty"] <= 0:
                del self.positions[symbol]
        
        order_result = {
            "status": "filled",
            "order_id": f"paper_{datetime.now().timestamp()}",
            "filled_qty": qty,
            "filled_price": fill_price,
            "avg_fill_price": fill_price,
        }
        
        logger.info(
            "paper_order_filled",
            symbol=symbol,
            side=side,
            qty=qty,
            fill_price=fill_price,
        )
        
        return order_result
    
    def submit_limit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        limit_price: float,
        client_order_id: Optional[str] = None,
    ) -> dict:
        """Submit limit order (for compatibility with Alpaca interface)."""
        result = self.submit_order(
            symbol=symbol,
            side=side,
            qty=qty,
            order_type="limit",
            limit_price=limit_price,
            current_price=limit_price,
        )
        # Add order_id for compatibility
        if "order_id" not in result:
            result["order_id"] = result.get("order_id", client_order_id or f"paper_{datetime.now().timestamp()}")
        return result
    
    def submit_market_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        client_order_id: Optional[str] = None,
    ) -> dict:
        """Submit market order (for compatibility with Alpaca interface)."""
        # Get current price (would fetch from market in real implementation)
        current_price = 100.0  # Default - would be fetched
        
        if symbol in self.positions:
            current_price = self.positions[symbol]["avg_price"]
        
        return self.submit_order(
            symbol=symbol,
            side=side,
            qty=qty,
            order_type="market",
            current_price=current_price,
        )
    
    def get_account(self) -> dict:
        """Get account summary."""
        positions_value = sum(
            pos["qty"] * pos["avg_price"]
            for pos in self.positions.values()
        )
        
        return {
            "cash": self.cash,
            "equity": self.cash + positions_value,
            "positions_value": positions_value,
        }
    
    def get_positions(self) -> list[dict]:
        """Get all positions."""
        return [
            {
                "symbol": symbol,
                "qty": pos["qty"],
                "avg_price": pos["avg_price"],
            }
            for symbol, pos in self.positions.items()
        ]
