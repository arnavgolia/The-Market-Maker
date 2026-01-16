"""
Order reconciliation for idempotency.

Implements Gemini's recommendation: NEVER retry an order without
checking broker state first. This prevents double execution.

Protocol:
1. Order times out → mark as UNKNOWN
2. Query broker for order by client_order_id
3. If found → sync state, do NOT retry
4. If not found → safe to retry
"""

from datetime import datetime, timedelta
from typing import Optional
import structlog

from src.execution.order_manager import OrderManager, Order, OrderStatus
from src.storage.redis_state import RedisStateStore

logger = structlog.get_logger(__name__)


class OrderReconciler:
    """
    Reconciles local order state with broker state.
    
    This ensures idempotency: if an order times out, we check
    broker state before retrying to prevent double execution.
    """
    
    def __init__(
        self,
        order_manager: OrderManager,
        broker_client,
        redis_state: RedisStateStore,
        reconciliation_interval_seconds: int = 300,
    ):
        """
        Initialize order reconciler.
        
        Args:
            order_manager: Order manager instance
            broker_client: Broker API client
            redis_state: Redis state store
            reconciliation_interval_seconds: How often to run reconciliation
        """
        self.order_manager = order_manager
        self.broker = broker_client
        self.redis = redis_state
        self.reconciliation_interval = reconciliation_interval_seconds
        
        logger.info(
            "order_reconciler_initialized",
            interval_seconds=reconciliation_interval_seconds,
        )
    
    def handle_timeout(
        self,
        client_order_id: str,
    ) -> tuple[bool, Optional[Order]]:
        """
        Handle order timeout.
        
        This is called when an order submission times out.
        We mark it as UNKNOWN and then reconcile.
        
        Returns:
            (should_retry, reconciled_order)
            - should_retry: True if order never reached broker (safe to retry)
            - reconciled_order: Order with updated state if found
        """
        logger.warning(
            "order_timeout",
            client_order_id=client_order_id,
        )
        
        # Mark as UNKNOWN
        self.order_manager.mark_unknown(client_order_id)
        
        # Reconcile immediately
        return self.reconcile_order(client_order_id)
    
    def reconcile_order(
        self,
        client_order_id: str,
    ) -> tuple[bool, Optional[Order]]:
        """
        Reconcile a single order with broker state.
        
        Returns:
            (should_retry, reconciled_order)
        """
        order = self.order_manager.get_order(client_order_id)
        
        if not order:
            logger.warning("order_not_found_for_reconciliation", client_order_id=client_order_id)
            return False, None
        
        # Query broker for order
        try:
            broker_order = self.broker.get_order_by_client_id(client_order_id)
        except Exception as e:
            logger.error(
                "broker_query_failed",
                client_order_id=client_order_id,
                error=str(e),
            )
            # Assume order doesn't exist (safe to retry)
            return True, None
        
        if broker_order:
            # Order exists on broker - sync state
            logger.info(
                "order_found_on_broker",
                client_order_id=client_order_id,
                broker_status=str(broker_order.status),
            )
            
            # Map broker status to our status
            status = self._map_broker_status(broker_order.status)
            
            # Update order state
            self.order_manager.update_status(
                client_order_id,
                status,
                order_id=str(broker_order.id),
                filled_qty=float(broker_order.filled_qty) if hasattr(broker_order, 'filled_qty') else None,
                filled_price=float(broker_order.filled_avg_price) if hasattr(broker_order, 'filled_avg_price') else None,
            )
            
            # Update Redis
            self._sync_to_redis(order)
            
            # DO NOT RETRY - order exists
            return False, self.order_manager.get_order(client_order_id)
        else:
            # Order not found on broker - safe to retry
            logger.info(
                "order_not_found_on_broker",
                client_order_id=client_order_id,
                action="safe_to_retry",
            )
            
            # Mark as failed (so we can retry)
            self.order_manager.mark_failed(client_order_id)
            
            return True, None
    
    def reconcile_all(self) -> dict:
        """
        Reconcile all open orders.
        
        This should be called periodically (e.g., every 5 minutes)
        to ensure local state matches broker state.
        
        Returns:
            Reconciliation summary
        """
        open_orders = self.order_manager.get_open_orders()
        
        summary = {
            "total": len(open_orders),
            "reconciled": 0,
            "needs_retry": 0,
            "errors": 0,
        }
        
        for order in open_orders:
            try:
                should_retry, reconciled = self.reconcile_order(order.client_order_id)
                
                if reconciled:
                    summary["reconciled"] += 1
                elif should_retry:
                    summary["needs_retry"] += 1
            except Exception as e:
                logger.error(
                    "reconciliation_error",
                    client_order_id=order.client_order_id,
                    error=str(e),
                )
                summary["errors"] += 1
        
        logger.info("reconciliation_complete", **summary)
        return summary
    
    def reconcile_positions(self) -> None:
        """
        Reconcile positions with broker.
        
        Broker positions are TRUTH. Local state is CACHE.
        """
        try:
            broker_positions = self.broker.get_positions()
            
            # Convert to dict format
            position_data = [
                {
                    "symbol": p.symbol,
                    "qty": float(p.qty),
                    "avg_price": float(p.avg_entry_price),
                    "market_value": float(p.market_value),
                    "unrealized_pnl": float(p.unrealized_pl),
                    "side": "long" if float(p.qty) > 0 else "short",
                }
                for p in broker_positions
            ]
            
            # Sync to Redis
            self.redis.sync_positions(position_data)
            
            logger.info("positions_reconciled", count=len(position_data))
            
        except Exception as e:
            logger.error("position_reconciliation_error", error=str(e))
    
    def _map_broker_status(self, broker_status: str) -> OrderStatus:
        """Map broker order status to our OrderStatus enum."""
        status_map = {
            "new": OrderStatus.SUBMITTED,
            "accepted": OrderStatus.SUBMITTED,
            "pending_new": OrderStatus.PENDING,
            "pending_replace": OrderStatus.SUBMITTED,
            "pending_cancel": OrderStatus.SUBMITTED,
            "filled": OrderStatus.FILLED,
            "partially_filled": OrderStatus.PARTIAL_FILL,
            "canceled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.FAILED,
            "expired": OrderStatus.FAILED,
        }
        
        return status_map.get(broker_status.lower(), OrderStatus.UNKNOWN)
    
    def _sync_to_redis(self, order: Order) -> None:
        """Sync order state to Redis."""
        try:
            self.redis.set_order(
                order_id=order.order_id or "",
                client_order_id=order.client_order_id,
                symbol=order.symbol,
                side=order.side,
                qty=order.qty,
                order_type=order.order_type,
                status=order.status.value,
                limit_price=order.limit_price,
                filled_qty=order.filled_qty,
                filled_price=order.filled_price,
                created_at=order.created_at,
            )
        except Exception as e:
            logger.error("redis_sync_error", error=str(e))
