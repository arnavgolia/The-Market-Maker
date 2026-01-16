"""
Comprehensive tests for order state machine.

Tests all state transitions, edge cases, and validation logic.
"""

import pytest
from datetime import datetime

from src.execution.order_manager import OrderManager, Order, OrderStatus


class TestOrderStateMachine:
    """Tests for order state machine."""
    
    def test_order_creation(self):
        """Test order creation starts in PENDING state."""
        manager = OrderManager()
        
        order = manager.create_order(
            symbol="AAPL",
            side="buy",
            qty=100,
            order_type="limit",
            limit_price=150.0,
        )
        
        assert order.status == OrderStatus.PENDING
        assert order.symbol == "AAPL"
        assert order.qty == 100
        assert order.client_order_id is not None
    
    def test_valid_transitions_pending_to_submitted(self):
        """Test PENDING → SUBMITTED transition."""
        manager = OrderManager()
        
        order = manager.create_order(
            symbol="AAPL",
            side="buy",
            qty=100,
        )
        
        updated = manager.mark_submitted(order.client_order_id, "broker_123")
        
        assert updated is not None
        assert updated.status == OrderStatus.SUBMITTED
        assert updated.order_id == "broker_123"
    
    def test_valid_transitions_submitted_to_filled(self):
        """Test SUBMITTED → FILLED transition."""
        manager = OrderManager()
        
        order = manager.create_order(symbol="AAPL", side="buy", qty=100)
        manager.mark_submitted(order.client_order_id, "broker_123")
        
        updated = manager.mark_filled(
            order.client_order_id,
            filled_qty=100,
            filled_price=150.0,
        )
        
        assert updated is not None
        assert updated.status == OrderStatus.FILLED
        assert updated.filled_qty == 100
        assert updated.filled_price == 150.0
    
    def test_valid_transitions_submitted_to_partial_fill(self):
        """Test SUBMITTED → PARTIAL_FILL transition."""
        manager = OrderManager()
        
        order = manager.create_order(symbol="AAPL", side="buy", qty=100)
        manager.mark_submitted(order.client_order_id, "broker_123")
        
        updated = manager.mark_partial_fill(
            order.client_order_id,
            filled_qty=50,
            filled_price=150.0,
        )
        
        assert updated is not None
        assert updated.status == OrderStatus.PARTIAL_FILL
        assert updated.filled_qty == 50
    
    def test_valid_transitions_partial_fill_to_filled(self):
        """Test PARTIAL_FILL → FILLED transition."""
        manager = OrderManager()
        
        order = manager.create_order(symbol="AAPL", side="buy", qty=100)
        manager.mark_submitted(order.client_order_id, "broker_123")
        manager.mark_partial_fill(order.client_order_id, filled_qty=50, filled_price=150.0)
        
        updated = manager.mark_filled(
            order.client_order_id,
            filled_qty=100,
            filled_price=150.0,
        )
        
        assert updated is not None
        assert updated.status == OrderStatus.FILLED
        assert updated.filled_qty == 100
    
    def test_valid_transitions_submitted_to_unknown(self):
        """Test SUBMITTED → UNKNOWN transition (timeout)."""
        manager = OrderManager()
        
        order = manager.create_order(symbol="AAPL", side="buy", qty=100)
        manager.mark_submitted(order.client_order_id, "broker_123")
        
        updated = manager.mark_unknown(order.client_order_id)
        
        assert updated is not None
        assert updated.status == OrderStatus.UNKNOWN
    
    def test_valid_transitions_unknown_to_submitted(self):
        """Test UNKNOWN → SUBMITTED transition (reconciliation found order)."""
        manager = OrderManager()
        
        order = manager.create_order(symbol="AAPL", side="buy", qty=100)
        manager.mark_submitted(order.client_order_id, "broker_123")
        manager.mark_unknown(order.client_order_id)
        
        # Reconciliation finds order on broker
        updated = manager.update_status(
            order.client_order_id,
            OrderStatus.SUBMITTED,
            order_id="broker_123",
        )
        
        assert updated is not None
        assert updated.status == OrderStatus.SUBMITTED
    
    def test_invalid_transitions_pending_to_filled(self):
        """Test invalid transition: PENDING → FILLED (must go through SUBMITTED)."""
        manager = OrderManager()
        
        order = manager.create_order(symbol="AAPL", side="buy", qty=100)
        
        # Try to mark as filled directly (should fail)
        updated = manager.mark_filled(
            order.client_order_id,
            filled_qty=100,
            filled_price=150.0,
        )
        
        # Should be None (invalid transition)
        assert updated is None
        assert order.status == OrderStatus.PENDING  # Unchanged
    
    def test_invalid_transitions_filled_to_submitted(self):
        """Test invalid transition: FILLED → SUBMITTED (terminal state)."""
        manager = OrderManager()
        
        order = manager.create_order(symbol="AAPL", side="buy", qty=100)
        manager.mark_submitted(order.client_order_id, "broker_123")
        manager.mark_filled(order.client_order_id, filled_qty=100, filled_price=150.0)
        
        # Try to go back to SUBMITTED (should fail)
        updated = manager.update_status(
            order.client_order_id,
            OrderStatus.SUBMITTED,
        )
        
        assert updated is None
        assert order.status == OrderStatus.FILLED  # Unchanged
    
    def test_failed_from_any_state(self):
        """Test that FAILED can be reached from any state (error handling)."""
        manager = OrderManager()
        
        # Test from PENDING
        order1 = manager.create_order(symbol="AAPL", side="buy", qty=100)
        manager.mark_failed(order1.client_order_id)
        assert order1.status == OrderStatus.FAILED
        
        # Test from SUBMITTED
        order2 = manager.create_order(symbol="AAPL", side="buy", qty=100)
        manager.mark_submitted(order2.client_order_id, "broker_123")
        manager.mark_failed(order2.client_order_id)
        assert order2.status == OrderStatus.FAILED
        
        # Test from PARTIAL_FILL
        order3 = manager.create_order(symbol="AAPL", side="buy", qty=100)
        manager.mark_submitted(order3.client_order_id, "broker_123")
        manager.mark_partial_fill(order3.client_order_id, filled_qty=50, filled_price=150.0)
        manager.mark_failed(order3.client_order_id)
        assert order3.status == OrderStatus.FAILED
    
    def test_terminal_states(self):
        """Test that terminal states cannot be changed."""
        manager = OrderManager()
        
        # FILLED is terminal
        order1 = manager.create_order(symbol="AAPL", side="buy", qty=100)
        manager.mark_submitted(order1.client_order_id, "broker_123")
        manager.mark_filled(order1.client_order_id, filled_qty=100, filled_price=150.0)
        assert order1.is_terminal is True
        assert order1.is_open is False
        
        # CANCELLED is terminal
        order2 = manager.create_order(symbol="AAPL", side="buy", qty=100)
        manager.mark_submitted(order2.client_order_id, "broker_123")
        manager.mark_cancelled(order2.client_order_id)
        assert order2.is_terminal is True
        assert order2.is_open is False
        
        # FAILED is terminal
        order3 = manager.create_order(symbol="AAPL", side="buy", qty=100)
        manager.mark_failed(order3.client_order_id)
        assert order3.is_terminal is True
        assert order3.is_open is False
    
    def test_get_open_orders(self):
        """Test getting only open (non-terminal) orders."""
        manager = OrderManager()
        
        # Create multiple orders
        order1 = manager.create_order(symbol="AAPL", side="buy", qty=100)
        order2 = manager.create_order(symbol="MSFT", side="buy", qty=50)
        order3 = manager.create_order(symbol="GOOGL", side="sell", qty=25)
        
        # Fill one
        manager.mark_submitted(order1.client_order_id, "broker_123")
        manager.mark_filled(order1.client_order_id, filled_qty=100, filled_price=150.0)
        
        # Cancel one
        manager.mark_submitted(order2.client_order_id, "broker_456")
        manager.mark_cancelled(order2.client_order_id)
        
        # Leave one open
        manager.mark_submitted(order3.client_order_id, "broker_789")
        
        open_orders = manager.get_open_orders()
        
        assert len(open_orders) == 1
        assert open_orders[0].client_order_id == order3.client_order_id
        assert open_orders[0].status == OrderStatus.SUBMITTED
    
    def test_get_orders_by_symbol(self):
        """Test getting orders filtered by symbol."""
        manager = OrderManager()
        
        order1 = manager.create_order(symbol="AAPL", side="buy", qty=100)
        order2 = manager.create_order(symbol="AAPL", side="sell", qty=50)
        order3 = manager.create_order(symbol="MSFT", side="buy", qty=25)
        
        aapl_orders = manager.get_orders_by_symbol("AAPL")
        
        assert len(aapl_orders) == 2
        assert all(o.symbol == "AAPL" for o in aapl_orders)
    
    def test_order_metadata(self):
        """Test that order metadata is preserved."""
        manager = OrderManager()
        
        order = manager.create_order(
            symbol="AAPL",
            side="buy",
            qty=100,
            strategy_name="ema_crossover",
            signal_id="signal_123",
        )
        
        assert order.strategy_name == "ema_crossover"
        assert order.signal_id == "signal_123"
        
        # Metadata should be in dict representation
        order_dict = order.to_dict()
        assert order_dict["strategy_name"] == "ema_crossover"
        assert order_dict["signal_id"] == "signal_123"
