#!/usr/bin/env python3
"""
Generate demo trading activity for the dashboard.

This script creates sample positions and orders to demonstrate
the dashboard functionality.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.storage.redis_state import RedisStateStore

def generate_demo_activity():
    """Generate demo positions and orders."""
    redis = RedisStateStore()
    
    print("🎮 Generating demo trading activity...")
    
    # Demo positions
    demo_positions = [
        {
            "symbol": "AAPL",
            "qty": 10.0,
            "avg_price": 175.50,
            "market_value": 1760.00,  # Current price ~$176
            "unrealized_pnl": 5.00,  # Small profit
            "side": "long",
        },
        {
            "symbol": "MSFT",
            "qty": 5.0,
            "avg_price": 380.00,
            "market_value": 1925.00,  # Current price ~$385
            "unrealized_pnl": 25.00,  # Profit
            "side": "long",
        },
        {
            "symbol": "TSLA",
            "qty": 15.0,
            "avg_price": 245.00,
            "market_value": 3600.00,  # Current price ~$240
            "unrealized_pnl": -75.00,  # Loss
            "side": "long",
        },
    ]
    
    # Set positions in Redis
    for pos in demo_positions:
        redis.set_position(
            symbol=pos["symbol"],
            qty=pos["qty"],
            avg_price=pos["avg_price"],
            market_value=pos["market_value"],
            unrealized_pnl=pos["unrealized_pnl"],
            side=pos["side"],
        )
        print(f"  ✅ Position: {pos['symbol']} - {pos['qty']} shares @ ${pos['avg_price']:.2f}")
    
    # Demo orders
    demo_orders = [
        {
            "order_id": f"demo_order_{int(datetime.now().timestamp())}",
            "client_order_id": f"client_{int(datetime.now().timestamp())}",
            "symbol": "SPY",
            "side": "buy",
            "qty": 20.0,
            "order_type": "limit",
            "status": "filled",
            "limit_price": 485.50,
            "filled_qty": 20.0,
            "filled_price": 485.50,
            "created_at": (datetime.now() - timedelta(minutes=5)).isoformat(),
            "updated_at": (datetime.now() - timedelta(minutes=5)).isoformat(),
        },
        {
            "order_id": f"demo_order_{int(datetime.now().timestamp()) + 1}",
            "client_order_id": f"client_{int(datetime.now().timestamp()) + 1}",
            "symbol": "QQQ",
            "side": "buy",
            "qty": 15.0,
            "order_type": "limit",
            "status": "pending",
            "limit_price": 420.00,
            "filled_qty": 0.0,
            "filled_price": None,
            "created_at": (datetime.now() - timedelta(minutes=2)).isoformat(),
            "updated_at": (datetime.now() - timedelta(minutes=2)).isoformat(),
        },
    ]
    
    # Set orders in Redis
    for order in demo_orders:
        redis.set_order(
            order_id=order["order_id"],
            client_order_id=order["client_order_id"],
            symbol=order["symbol"],
            side=order["side"],
            qty=order["qty"],
            order_type=order["order_type"],
            status=order["status"],
            limit_price=order.get("limit_price"),
            filled_qty=order.get("filled_qty", 0),
            filled_price=order.get("filled_price"),
            created_at=datetime.fromisoformat(order["created_at"]),
        )
        print(f"  ✅ Order: {order['symbol']} {order['side'].upper()} {order['qty']} @ ${order.get('limit_price', 0):.2f} - {order['status']}")
    
    # Update account equity
    total_positions_value = sum(p["market_value"] for p in demo_positions)
    cash = 100000.0 - total_positions_value
    equity = 100000.0 + sum(p["unrealized_pnl"] for p in demo_positions)
    
    redis.set_initial_equity(100000.0)
    
    # Update equity history
    equity_key = f"{RedisStateStore.STATE_PREFIX}:equity_history"
    for i in range(20):
        # Create some variation in equity
        equity_value = equity + (i * 10) - 100  # Some up and down movement
        redis.client.rpush(equity_key, equity_value)
    redis.client.ltrim(equity_key, -100, -1)
    
    print()
    print("✅ Demo activity generated!")
    print(f"   Positions: {len(demo_positions)}")
    print(f"   Orders: {len(demo_orders)}")
    print(f"   Total Equity: ${equity:,.2f}")
    print()
    print("🌐 Refresh your dashboard at http://localhost:8080 to see the activity!")

if __name__ == "__main__":
    generate_demo_activity()
