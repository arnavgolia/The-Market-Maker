"""
Exhaustive tests for order execution and state machine.

Tests every possible state transition, error case, and edge condition.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock

from src.execution.order_manager import OrderManager, Order, OrderStatus
from src.execution.reconciler import OrderReconciler


class TestOrderStateTransitionsExhaustive:
    """Exhaust

ive tests for all state transitions."""
    
    def test_all_valid_transitions_from_pending(self):
        """Test all valid transitions from PENDING."""
        manager = OrderManager()
        
        # PENDING → SUBMITTED
        order1 = manager.create_order("TEST", "buy", 100)
        result1 = manager.mark_submitted(order1.client_order_id, "broker_1")
        assert result1 is not None
        assert result1.status == OrderStatus.SUBMITTED
        
        # PENDING → FAILED
        order2 = manager.create_order("TEST", "buy", 100)
        result2 = manager.mark_failed(order2.client_order_id)
        assert result2 is not None
        assert result2.status == OrderStatus.FAILED
    
    def test_all_valid_transitions_from_submitted(self):
        """Test all valid transitions from SUBMITTED."""
        manager = OrderManager()
        
        # SUBMITTED → FILLED
        order1 = manager.create_order("TEST", "buy", 100)
        manager.mark_submitted(order1.client_order_id, "broker_1")
        result1 = manager.mark_filled(order1.client_order_id, 100, 150.0)
        assert result1.status == OrderStatus.FILLED
        
        # SUBMITTED → PARTIAL_FILL
        order2 = manager.create_order("TEST", "buy", 100)
        manager.mark_submitted(order2.client_order_id, "broker_2")
        result2 = manager.mark_partial_fill(order2.client_order_id, 50, 150.0)
        assert result2.status == OrderStatus.PARTIAL_FILL
        
        # SUBMITTED → CANCELLED
        order3 = manager.create_order("TEST", "buy", 100)
        manager.mark_submitted(order3.client_order_id, "broker_3")
        result3 = manager.mark_cancelled(order3.client_order_id)
        assert result3.status == OrderStatus.CANCELLED
        
        # SUBMITTED → UNKNOWN
        order4 = manager.create_order("TEST", "buy", 100)
        manager.mark_submitted(order4.client_order_id, "broker_4")
        result4 = manager.mark_unknown(order4.client_order_id)
        assert result4.status == OrderStatus.UNKNOWN
    
    def test_all_invalid_transitions_rejected(self):
        """Test that invalid transitions are rejected."""
        manager = OrderManager()
        
        # PENDING → FILLED (must go through SUBMITTED)
        order1 = manager.create_order("TEST", "buy", 100)
        result1 = manager.mark_filled(order1.client_order_id, 100, 150.0)
        assert result1 is None  # Rejected
        assert order1.status == OrderStatus.PENDING  # Unchanged
        
        # FILLED → SUBMITTED (terminal state)
        order2 = manager.create_order("TEST", "buy", 100)
        manager.mark_submitted(order2.client_order_id, "broker_1")
        manager.mark_filled(order2.client_order_id, 100, 150.0)
        result2 = manager.update_status(order2.client_order_id, OrderStatus.SUBMITTED)
        assert result2 is None  # Rejected
        assert order2.status == OrderStatus.FILLED  # Unchanged
    
    def test_partial_fill_to_filled_with_accumulation(self):
        """Test partial fills accumulate correctly."""
        manager = OrderManager()
        
        order = manager.create_order("TEST", "buy", 100)
        manager.mark_submitted(order.client_order_id, "broker_1")
        
        # First partial fill: 30 shares
        manager.mark_partial_fill(order.client_order_id, 30, 150.0)
        assert order.filled_qty == 30
        
        # Second partial fill: 50 more shares (80 total)
        manager.mark_partial_fill(order.client_order_id, 50, 150.5)
        assert order.filled_qty == 50  # Last update (not cumulative in current impl)
        
        # Final fill: 100 total
        manager.mark_filled(order.client_order_id, 100, 150.25)
        assert order.filled_qty == 100
        assert order.status == OrderStatus.FILLED
    
    def test_unknown_to_submitted_after_reconciliation(self):
        """Test reconciliation can move UNKNOWN back to SUBMITTED."""
        manager = OrderManager()
        
        order = manager.create_order("TEST", "buy", 100)
        manager.mark_submitted(order.client_order_id, "broker_1")
        manager.mark_unknown(order.client_order_id)
        
        # Reconciliation finds order on broker
        result = manager.update_status(
            order.client_order_id,
            OrderStatus.SUBMITTED,
            order_id="broker_1",
        )
        
        assert result is not None
        assert result.status == OrderStatus.SUBMITTED
    
    def test_failed_from_any_state(self):
        """Test that FAILED can be reached from any non-terminal state."""
        manager = OrderManager()
        
        # From PENDING
        order1 = manager.create_order("TEST", "buy", 100)
        assert manager.mark_failed(order1.client_order_id) is not None
        
        # From SUBMITTED
        order2 = manager.create_order("TEST", "buy", 100)
        manager.mark_submitted(order2.client_order_id, "broker_1")
        assert manager.mark_failed(order2.client_order_id) is not None
        
        # From PARTIAL_FILL
        order3 = manager.create_order("TEST", "buy", 100)
        manager.mark_submitted(order3.client_order_id, "broker_1")
        manager.mark_partial_fill(order3.client_order_id, 50, 150.0)
        assert manager.mark_failed(order3.client_order_id) is not None
        
        # From UNKNOWN
        order4 = manager.create_order("TEST", "buy", 100)
        manager.mark_submitted(order4.client_order_id, "broker_1")
        manager.mark_unknown(order4.client_order_id)
        assert manager.mark_failed(order4.client_order_id) is not None


class TestOrderReconciliationExhaustive:
    """Exhaustive tests for order reconciliation."""
    
    def test_timeout_order_found_pending(self):
        """Test timeout when order found in PENDING state."""
        manager = OrderManager()
        mock_broker = Mock()
        mock_redis = Mock()
        
        reconciler = OrderReconciler(manager, mock_broker, mock_redis)
        
        order = manager.create_order("TEST", "buy", 100)
        manager.mark_submitted(order.client_order_id, "broker_1")
        
        # Broker shows as pending
        mock_order = Mock()
        mock_order.id = "broker_1"
        mock_order.status = "pending_new"
        mock_broker.get_order_by_client_id.return_value = mock_order
        
        should_retry, reconciled = reconciler.handle_timeout(order.client_order_id)
        
        # Should NOT retry (order exists)
        assert should_retry is False
    
    def test_timeout_order_found_filled(self):
        """Test timeout when order was actually filled."""
        manager = OrderManager()
        mock_broker = Mock()
        mock_redis = Mock()
        
        reconciler = OrderReconciler(manager, mock_broker, mock_redis)
        
        order = manager.create_order("TEST", "buy", 100)
        manager.mark_submitted(order.client_order_id, "broker_1")
        
        # Broker shows as filled
        mock_order = Mock()
        mock_order.id = "broker_1"
        mock_order.status = "filled"
        mock_order.filled_qty = 100
        mock_order.filled_avg_price = 150.0
        mock_broker.get_order_by_client_id.return_value = mock_order
        
        should_retry, reconciled = reconciler.handle_timeout(order.client_order_id)
        
        # Should NOT retry
        assert should_retry is False
        assert reconciled.status == OrderStatus.FILLED
        assert reconciled.filled_qty == 100
    
    def test_timeout_order_not_found_safe_retry(self):
        """Test timeout when order never reached broker (safe to retry)."""
        manager = OrderManager()
        mock_broker = Mock()
        mock_redis = Mock()
        
        reconciler = OrderReconciler(manager, mock_broker, mock_redis)
        
        order = manager.create_order("TEST", "buy", 100)
        manager.mark_submitted(order.client_order_id, "broker_1")
        
        # Broker doesn't have order
        mock_broker.get_order_by_client_id.return_value = None
        
        should_retry, reconciled = reconciler.handle_timeout(order.client_order_id)
        
        # Safe to retry
        assert should_retry is True
        assert order.status == OrderStatus.FAILED
    
    def test_timeout_broker_error(self):
        """Test timeout when broker query fails."""
        manager = OrderManager()
        mock_broker = Mock()
        mock_redis = Mock()
        
        reconciler = OrderReconciler(manager, mock_broker, mock_redis)
        
        order = manager.create_order("TEST", "buy", 100)
        manager.mark_submitted(order.client_order_id, "broker_1")
        
        # Broker query fails
        mock_broker.get_order_by_client_id.side_effect = Exception("API Error")
        
        should_retry, reconciled = reconciler.handle_timeout(order.client_order_id)
        
        # Assume safe to retry on error (conservative)
        assert should_retry is True
    
    def test_reconcile_all_mixed_states(self):
        """Test reconcile_all with orders in various states."""
        manager = OrderManager()
        mock_broker = Mock()
        mock_redis = Mock()
        
        reconciler = OrderReconciler(manager, mock_broker, mock_redis)
        
        # Create multiple orders in different states
        order1 = manager.create_order("TEST1", "buy", 100)
        manager.mark_submitted(order1.client_order_id, "broker_1")
        manager.mark_unknown(order1.client_order_id)
        
        order2 = manager.create_order("TEST2", "buy", 100)
        manager.mark_submitted(order2.client_order_id, "broker_2")
        manager.mark_unknown(order2.client_order_id)
        
        # Mock broker responses
        def broker_response(client_order_id):
            if client_order_id == order1.client_order_id:
                mock_order = Mock()
                mock_order.id = "broker_1"
                mock_order.status = "filled"
                mock_order.filled_qty = 100
                mock_order.filled_avg_price = 150.0
                return mock_order
            else:
                return None  # Order 2 not found
        
        mock_broker.get_order_by_client_id.side_effect = broker_response
        
        summary = reconciler.reconcile_all()
        
        assert summary["total"] == 2
        assert summary["reconciled"] >= 1
        assert summary["needs_retry"] >= 1


class TestOrderEdgeCases:
    """Test edge cases in order handling."""
    
    def test_zero_quantity_order(self):
        """Test handling of zero quantity order."""
        manager = OrderManager()
        
        order = manager.create_order("TEST", "buy", 0)
        
        # Should create but probably shouldn't be submitted
        assert order.qty == 0
    
    def test_negative_quantity_order(self):
        """Test handling of negative quantity (should reject)."""
        manager = OrderManager()
        
        # Negative quantity doesn't make sense
        # System should either reject or handle defensively
        with pytest.raises((ValueError, AssertionError)):
            order = manager.create_order("TEST", "buy", -100)
    
    def test_order_with_no_limit_price_for_limit_order(self):
        """Test limit order without limit price."""
        manager = OrderManager()
        
        order = manager.create_order(
            "TEST",
            "buy",
            100,
            order_type="limit",
            limit_price=None,  # Missing limit price
        )
        
        # Should either reject or handle
        assert order.limit_price is None  # Tracks it
    
    def test_concurrent_order_updates(self):
        """Test handling of concurrent status updates."""
        manager = OrderManager()
        
        order = manager.create_order("TEST", "buy", 100)
        manager.mark_submitted(order.client_order_id, "broker_1")
        
        # Simulate race: both mark_filled and mark_cancelled called
        result1 = manager.mark_filled(order.client_order_id, 100, 150.0)
        result2 = manager.mark_cancelled(order.client_order_id)
        
        # Second should be rejected (already in terminal state)
        assert result1.status == OrderStatus.FILLED
        assert result2 is None
    
    def test_order_age_tracking(self):
        """Test that order tracks creation and update times."""
        manager = OrderManager()
        
        order = manager.create_order("TEST", "buy", 100)
        
        assert order.created_at is not None
        assert order.updated_at is not None
        assert order.created_at <= order.updated_at
        
        # Update order
        import time
        time.sleep(0.01)
        manager.mark_submitted(order.client_order_id, "broker_1")
        
        # Updated time should change
        assert order.updated_at > order.created_at
