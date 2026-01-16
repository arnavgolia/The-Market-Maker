"""
Order management and state machine.

Manages order lifecycle:
PENDING → SUBMITTED → FILLED
    ↓         ↓
  FAILED   PARTIAL_FILL → FILLED
    ↓         ↓
 UNKNOWN → RECONCILED
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
import structlog
import uuid

logger = structlog.get_logger(__name__)


class OrderStatus(Enum):
    """Order status in state machine."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIAL_FILL = "partial_fill"
    CANCELLED = "cancelled"
    FAILED = "failed"
    UNKNOWN = "unknown"  # Timeout - needs reconciliation


@dataclass
class Order:
    """
    Order representation.
    
    Orders go through a state machine and are reconciled
    with broker state to ensure idempotency.
    """
    # Identifiers
    order_id: Optional[str] = None  # Broker order ID
    client_order_id: str = None  # Our internal ID
    
    # Order details
    symbol: str = ""
    side: str = ""  # "buy" or "sell"
    qty: float = 0.0
    order_type: str = "limit"  # "limit" or "market"
    limit_price: Optional[float] = None
    
    # State
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = None
    updated_at: datetime = None
    
    # Fill information
    filled_qty: float = 0.0
    filled_price: Optional[float] = None
    avg_fill_price: Optional[float] = None
    
    # Metadata
    strategy_name: Optional[str] = None
    signal_id: Optional[str] = None
    
    def __post_init__(self):
        """Initialize defaults."""
        if self.client_order_id is None:
            self.client_order_id = f"order_{uuid.uuid4().hex[:12]}"
        
        if self.created_at is None:
            self.created_at = datetime.now()
        
        if self.updated_at is None:
            self.updated_at = self.created_at
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "order_type": self.order_type,
            "limit_price": self.limit_price,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "filled_qty": self.filled_qty,
            "filled_price": self.filled_price,
            "avg_fill_price": self.avg_fill_price,
            "strategy_name": self.strategy_name,
            "signal_id": self.signal_id,
        }
    
    @property
    def is_terminal(self) -> bool:
        """Check if order is in terminal state."""
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.FAILED,
        )
    
    @property
    def is_open(self) -> bool:
        """Check if order is still open (not terminal)."""
        return not self.is_terminal


class OrderManager:
    """
    Manages order lifecycle and state transitions.
    
    This implements the order state machine and ensures
    proper state transitions with validation.
    """
    
    def __init__(self):
        """Initialize order manager."""
        self.orders: dict[str, Order] = {}  # client_order_id -> Order
        logger.info("order_manager_initialized")
    
    def create_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        order_type: str = "limit",
        limit_price: Optional[float] = None,
        strategy_name: Optional[str] = None,
        signal_id: Optional[str] = None,
    ) -> Order:
        """
        Create a new order.
        
        Args:
            symbol: Stock symbol
            side: "buy" or "sell"
            qty: Quantity
            order_type: "limit" or "market"
            limit_price: Limit price (required for limit orders)
            strategy_name: Strategy that generated the order
            signal_id: Signal ID that generated the order
        
        Returns:
            Order in PENDING state
        """
        order = Order(
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            limit_price=limit_price,
            strategy_name=strategy_name,
            signal_id=signal_id,
            status=OrderStatus.PENDING,
        )
        
        self.orders[order.client_order_id] = order
        
        logger.info(
            "order_created",
            client_order_id=order.client_order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
        )
        
        return order
    
    def update_status(
        self,
        client_order_id: str,
        status: OrderStatus,
        order_id: Optional[str] = None,
        filled_qty: Optional[float] = None,
        filled_price: Optional[float] = None,
    ) -> Optional[Order]:
        """
        Update order status.
        
        Validates state transitions and updates order.
        """
        order = self.orders.get(client_order_id)
        
        if not order:
            logger.warning("order_not_found", client_order_id=client_order_id)
            return None
        
        # Validate state transition
        if not self._is_valid_transition(order.status, status):
            logger.warning(
                "invalid_state_transition",
                client_order_id=client_order_id,
                from_status=order.status.value,
                to_status=status.value,
            )
            return None
        
        # Update order
        old_status = order.status
        order.status = status
        order.updated_at = datetime.now()
        
        if order_id:
            order.order_id = order_id
        
        if filled_qty is not None:
            order.filled_qty = filled_qty
        
        if filled_price is not None:
            order.filled_price = filled_price
            order.avg_fill_price = filled_price
        
        logger.info(
            "order_status_updated",
            client_order_id=client_order_id,
            from_status=old_status.value,
            to_status=status.value,
        )
        
        return order
    
    def mark_submitted(self, client_order_id: str, order_id: str) -> Optional[Order]:
        """Mark order as submitted to broker."""
        return self.update_status(
            client_order_id,
            OrderStatus.SUBMITTED,
            order_id=order_id,
        )
    
    def mark_filled(
        self,
        client_order_id: str,
        filled_qty: float,
        filled_price: float,
    ) -> Optional[Order]:
        """Mark order as filled."""
        return self.update_status(
            client_order_id,
            OrderStatus.FILLED,
            filled_qty=filled_qty,
            filled_price=filled_price,
        )
    
    def mark_partial_fill(
        self,
        client_order_id: str,
        filled_qty: float,
        filled_price: float,
    ) -> Optional[Order]:
        """Mark order as partially filled."""
        return self.update_status(
            client_order_id,
            OrderStatus.PARTIAL_FILL,
            filled_qty=filled_qty,
            filled_price=filled_price,
        )
    
    def mark_failed(self, client_order_id: str) -> Optional[Order]:
        """Mark order as failed."""
        return self.update_status(client_order_id, OrderStatus.FAILED)
    
    def mark_cancelled(self, client_order_id: str) -> Optional[Order]:
        """Mark order as cancelled."""
        return self.update_status(client_order_id, OrderStatus.CANCELLED)
    
    def mark_unknown(self, client_order_id: str) -> Optional[Order]:
        """
        Mark order as unknown (timeout).
        
        This triggers reconciliation to check broker state.
        """
        return self.update_status(client_order_id, OrderStatus.UNKNOWN)
    
    def get_order(self, client_order_id: str) -> Optional[Order]:
        """Get order by client order ID."""
        return self.orders.get(client_order_id)
    
    def get_open_orders(self) -> list[Order]:
        """Get all open (non-terminal) orders."""
        return [o for o in self.orders.values() if o.is_open]
    
    def get_orders_by_symbol(self, symbol: str) -> list[Order]:
        """Get all orders for a symbol."""
        return [o for o in self.orders.values() if o.symbol == symbol]
    
    def _is_valid_transition(self, from_status: OrderStatus, to_status: OrderStatus) -> bool:
        """
        Validate state transition.
        
        Valid transitions:
        - PENDING → SUBMITTED, FAILED
        - SUBMITTED → FILLED, PARTIAL_FILL, CANCELLED, UNKNOWN
        - PARTIAL_FILL → FILLED, CANCELLED
        - UNKNOWN → SUBMITTED, FAILED (after reconciliation)
        - Any → FAILED (error state)
        """
        valid_transitions = {
            OrderStatus.PENDING: {OrderStatus.SUBMITTED, OrderStatus.FAILED},
            OrderStatus.SUBMITTED: {
                OrderStatus.FILLED,
                OrderStatus.PARTIAL_FILL,
                OrderStatus.CANCELLED,
                OrderStatus.UNKNOWN,
            },
            OrderStatus.PARTIAL_FILL: {OrderStatus.FILLED, OrderStatus.CANCELLED},
            OrderStatus.UNKNOWN: {OrderStatus.SUBMITTED, OrderStatus.FAILED},
        }
        
        # FAILED can be reached from any state (error)
        if to_status == OrderStatus.FAILED:
            return True
        
        allowed = valid_transitions.get(from_status, set())
        return to_status in allowed
