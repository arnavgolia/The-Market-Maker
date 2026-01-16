"""
Tests for order reconciliation (idempotency).

Tests that the reconciliation layer prevents double execution
when orders timeout.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock

from src.execution.order_manager import OrderManager, Order, OrderStatus
from src.execution.reconciler import OrderReconciler
from src.storage.redis_state import RedisStateStore


class TestOrderReconciler:
    """Tests for order reconciliation."""
    
    def test_timeout_handling(self):
        """Test that timeout triggers reconciliation."""
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
            order_type="limit",
            limit_price=150.0,
        )
        
        # Simulate timeout
        mock_broker.get_order_by_client_id.return_value = None  # Order not found
        
        should_retry, reconciled = reconciler.handle_timeout(order.client_order_id)
        
        # Order not found on broker - safe to retry
        assert should_retry is True
        assert order_manager.get_order(order.client_order_id).status == OrderStatus.FAILED
    
    def test_reconciliation_finds_order(self):
        """Test that reconciliation finds existing order."""
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
            order_type="limit",
            limit_price=150.0,
        )
        
        # Mark as unknown (timeout)
        order_manager.mark_unknown(order.client_order_id)
        
        # Simulate broker has the order
        mock_broker_order = Mock()
        mock_broker_order.id = "broker_order_123"
        mock_broker_order.status = "filled"
        mock_broker_order.filled_qty = 100
        mock_broker_order.filled_avg_price = 150.0
        
        mock_broker.get_order_by_client_id.return_value = mock_broker_order
        
        should_retry, reconciled = reconciler.reconcile_order(order.client_order_id)
        
        # Order found - do NOT retry
        assert should_retry is False
        assert reconciled is not None
        assert reconciled.status == OrderStatus.FILLED
    
    def test_idempotency_guarantee(self):
        """
        Test that reconciliation prevents double execution.
        
        This is the critical test: if order exists on broker,
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
        
        # Create order
        order = order_manager.create_order(
            symbol="AAPL",
            side="buy",
            qty=100,
            order_type="limit",
            limit_price=150.0,
        )
        
        # Simulate timeout
        order_manager.mark_unknown(order.client_order_id)
        
        # Broker has the order (it was actually submitted)
        mock_broker_order = Mock()
        mock_broker_order.id = "broker_order_123"
        mock_broker_order.status = "submitted"
        mock_broker.get_order_by_client_id.return_value = mock_broker_order
        
        should_retry, _ = reconciler.handle_timeout(order.client_order_id)
        
        # CRITICAL: Must NOT retry if order exists
        assert should_retry is False, "Reconciliation must prevent double execution"
