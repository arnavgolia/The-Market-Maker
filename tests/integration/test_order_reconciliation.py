"""
Integration tests for order reconciliation and idempotency.

Tests the full reconciliation flow to ensure idempotency guarantees.
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timedelta

from src.execution.order_manager import OrderManager, OrderStatus
from src.execution.reconciler import OrderReconciler
from src.storage.redis_state import RedisStateStore


class TestOrderReconciliation:
    """Integration tests for order reconciliation."""
    
    def test_full_reconciliation_flow_order_found(self):
        """
        Test full reconciliation flow when order is found on broker.
        
        This is the critical idempotency test: if order exists on broker,
        we must NOT retry.
        """
        order_manager = OrderManager()
        mock_broker = Mock()
        mock_redis = Mock(spec=RedisStateStore)
        
        reconciler = OrderReconciler(
            order_manager=order_manager,
            broker_client=mock_broker,
            redis_state=mock_redis,
        )
        
        # Create and submit order
        order = order_manager.create_order(
            symbol="AAPL",
            side="buy",
            qty=100,
            order_type="limit",
            limit_price=150.0,
        )
        
        order_manager.mark_submitted(order.client_order_id, "broker_123")
        
        # Simulate timeout
        order_manager.mark_unknown(order.client_order_id)
        
        # Broker has the order (it was actually submitted)
        mock_broker_order = Mock()
        mock_broker_order.id = "broker_123"
        mock_broker_order.status = "filled"
        mock_broker_order.filled_qty = 100
        mock_broker_order.filled_avg_price = 150.0
        
        mock_broker.get_order_by_client_id.return_value = mock_broker_order
        
        # Reconcile
        should_retry, reconciled = reconciler.reconcile_order(order.client_order_id)
        
        # CRITICAL: Must NOT retry if order exists
        assert should_retry is False
        assert reconciled is not None
        assert reconciled.status == OrderStatus.FILLED
        assert reconciled.filled_qty == 100
        assert reconciled.filled_price == 150.0
    
    def test_full_reconciliation_flow_order_not_found(self):
        """
        Test full reconciliation flow when order is NOT found on broker.
        
        This means order never reached broker - safe to retry.
        """
        order_manager = OrderManager()
        mock_broker = Mock()
        mock_redis = Mock(spec=RedisStateStore)
        
        reconciler = OrderReconciler(
            order_manager=order_manager,
            broker_client=mock_broker,
            redis_state=mock_redis,
        )
        
        # Create and submit order
        order = order_manager.create_order(
            symbol="AAPL",
            side="buy",
            qty=100,
        )
        
        order_manager.mark_submitted(order.client_order_id, "broker_123")
        
        # Simulate timeout
        order_manager.mark_unknown(order.client_order_id)
        
        # Broker does NOT have the order
        mock_broker.get_order_by_client_id.return_value = None
        
        # Reconcile
        should_retry, reconciled = reconciler.reconcile_order(order.client_order_id)
        
        # Safe to retry
        assert should_retry is True
        assert order.status == OrderStatus.FAILED  # Marked as failed for retry
    
    def test_reconcile_all_orders(self):
        """Test reconciling all open orders."""
        order_manager = OrderManager()
        mock_broker = Mock()
        mock_redis = Mock(spec=RedisStateStore)
        
        reconciler = OrderReconciler(
            order_manager=order_manager,
            broker_client=mock_broker,
            redis_state=mock_redis,
        )
        
        # Create multiple orders
        order1 = order_manager.create_order(symbol="AAPL", side="buy", qty=100)
        order2 = order_manager.create_order(symbol="MSFT", side="buy", qty=50)
        order3 = order_manager.create_order(symbol="GOOGL", side="sell", qty=25)
        
        # Submit all
        order_manager.mark_submitted(order1.client_order_id, "broker_1")
        order_manager.mark_submitted(order2.client_order_id, "broker_2")
        order_manager.mark_submitted(order3.client_order_id, "broker_3")
        
        # Mark all as unknown (timeout)
        order_manager.mark_unknown(order1.client_order_id)
        order_manager.mark_unknown(order2.client_order_id)
        order_manager.mark_unknown(order3.client_order_id)
        
        # Mock broker responses
        def get_order_side_effect(client_order_id):
            if client_order_id == order1.client_order_id:
                mock_order = Mock()
                mock_order.id = "broker_1"
                mock_order.status = "filled"
                mock_order.filled_qty = 100
                mock_order.filled_avg_price = 150.0
                return mock_order
            elif client_order_id == order2.client_order_id:
                return None  # Not found
            else:
                mock_order = Mock()
                mock_order.id = "broker_3"
                mock_order.status = "submitted"
                return mock_order
        
        mock_broker.get_order_by_client_id.side_effect = get_order_side_effect
        
        # Reconcile all
        summary = reconciler.reconcile_all()
        
        assert summary["total"] == 3
        assert summary["reconciled"] == 2  # order1 and order3 found
        assert summary["needs_retry"] == 1  # order2 not found
    
    def test_idempotency_guarantee_no_double_execution(self):
        """
        CRITICAL TEST: Ensure idempotency - no double execution.
        
        Scenario:
        1. Order submitted, times out
        2. Reconciliation finds order on broker (already filled)
        3. System must NOT retry
        """
        order_manager = OrderManager()
        mock_broker = Mock()
        mock_redis = Mock(spec=RedisStateStore)
        
        reconciler = OrderReconciler(
            order_manager=order_manager,
            broker_client=mock_broker,
            redis_state=mock_redis,
        )
        
        # Create order
        order = order_manager.create_order(
            symbol="AAPL",
            side="buy",
            qty=100,
        )
        
        # Submit
        order_manager.mark_submitted(order.client_order_id, "broker_123")
        
        # Timeout
        order_manager.mark_unknown(order.client_order_id)
        
        # Broker shows order was already filled
        mock_broker_order = Mock()
        mock_broker_order.id = "broker_123"
        mock_broker_order.status = "filled"
        mock_broker_order.filled_qty = 100
        mock_broker_order.filled_avg_price = 150.0
        
        mock_broker.get_order_by_client_id.return_value = mock_broker_order
        
        # Reconcile
        should_retry, _ = reconciler.handle_timeout(order.client_order_id)
        
        # CRITICAL: Must NOT retry
        assert should_retry is False, "Idempotency violation: Would retry already-filled order"
        
        # Verify order was updated, not retried
        updated_order = order_manager.get_order(order.client_order_id)
        assert updated_order.status == OrderStatus.FILLED
        assert updated_order.filled_qty == 100
    
    def test_position_reconciliation(self):
        """Test position reconciliation (broker is truth)."""
        order_manager = OrderManager()
        mock_broker = Mock()
        mock_redis = Mock(spec=RedisStateStore)
        
        reconciler = OrderReconciler(
            order_manager=order_manager,
            broker_client=mock_broker,
            redis_state=mock_redis,
        )
        
        # Mock broker positions
        mock_position1 = Mock()
        mock_position1.symbol = "AAPL"
        mock_position1.qty = 100.0
        mock_position1.avg_entry_price = 150.0
        mock_position1.market_value = 15000.0
        mock_position1.unrealized_pl = 500.0
        
        mock_position2 = Mock()
        mock_position2.symbol = "MSFT"
        mock_position2.qty = 50.0
        mock_position2.avg_entry_price = 200.0
        mock_position2.market_value = 10000.0
        mock_position2.unrealized_pl = -200.0
        
        mock_broker.get_positions.return_value = [mock_position1, mock_position2]
        
        # Reconcile positions
        reconciler.reconcile_positions()
        
        # Verify Redis was updated
        assert mock_redis.sync_positions.called
        call_args = mock_redis.sync_positions.call_args[0][0]
        
        assert len(call_args) == 2
        assert call_args[0]["symbol"] == "AAPL"
        assert call_args[0]["qty"] == 100.0
        assert call_args[1]["symbol"] == "MSFT"
        assert call_args[1]["qty"] == 50.0
