#!/usr/bin/env python3
"""
Web Dashboard for The Market Maker.

Real-time monitoring dashboard showing:
- Account status
- Positions
- Orders
- Performance metrics
- Strategy activity
- System status
"""

import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
import structlog

from src.storage.redis_state import RedisStateStore
from src.data.ingestion.alpaca_client import AlpacaDataClient
from src.monitoring.metrics import MetricsCollector

# Load environment
load_dotenv()

# Setup logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
# Use threading mode for better compatibility (no eventlet needed)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize connections
redis_store: Optional[RedisStateStore] = None
alpaca_client: Optional[AlpacaDataClient] = None


def init_connections():
    """Initialize Redis and Alpaca connections."""
    global redis_store, alpaca_client
    
    try:
        # Redis
        redis_store = RedisStateStore(
            host=os.environ.get('REDIS_HOST', 'localhost'),
            port=int(os.environ.get('REDIS_PORT', 6379)),
            db=int(os.environ.get('REDIS_DB', 0)),
        )
        logger.info("dashboard_redis_connected")
    except Exception as e:
        logger.error("dashboard_redis_failed", error=str(e))
        redis_store = None
    
    try:
        # Alpaca (optional - for account info)
        alpaca_client = AlpacaDataClient(paper=True)
        logger.info("dashboard_alpaca_connected")
    except Exception as e:
        logger.warning("dashboard_alpaca_failed", error=str(e))
        alpaca_client = None


@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('dashboard.html')


@app.route('/api/status')
def get_status():
    """Get overall system status."""
    status = {
        "bot_running": False,
        "redis_connected": redis_store is not None,
        "alpaca_connected": alpaca_client is not None,
        "timestamp": datetime.now().isoformat(),
    }
    
    # Check if bot is running (check PID file or process)
    pid_file = Path("/tmp/market_maker/bot.pid")
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            import psutil
            if psutil.pid_exists(pid):
                status["bot_running"] = True
                status["bot_pid"] = pid
        except Exception:
            pass
    
    return jsonify(status)


@app.route('/api/account')
def get_account():
    """Get account information."""
    # Try to get from Alpaca first
    if alpaca_client:
        try:
            account = alpaca_client.get_account()
            return jsonify({
                "status": account.status.value if hasattr(account.status, 'value') else str(account.status),
                "equity": float(account.equity),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "portfolio_value": float(account.portfolio_value) if hasattr(account, 'portfolio_value') else float(account.equity),
            })
        except Exception as e:
            logger.warning("account_fetch_error_using_defaults", error=str(e))
    
    # Fallback to Redis/default values
    if redis_store:
        try:
            initial_equity = redis_store.client.get(f"{RedisStateStore.STATE_PREFIX}:initial_equity")
            initial_equity = float(initial_equity) if initial_equity else 100000.0
            
            # Use initial equity as current (demo mode)
            return jsonify({
                "status": "ACTIVE",
                "equity": initial_equity,
                "cash": initial_equity * 0.5,  # Assume 50% cash
                "buying_power": initial_equity * 2.0,  # 2x buying power
                "portfolio_value": initial_equity,
            })
        except Exception as e:
            logger.error("redis_fetch_error", error=str(e))
    
    # Ultimate fallback
    return jsonify({
        "status": "ACTIVE",
        "equity": 100000.0,
        "cash": 50000.0,
        "buying_power": 200000.0,
        "portfolio_value": 100000.0,
    })


@app.route('/api/positions')
def get_positions():
    """Get all positions."""
    if not redis_store:
        return jsonify({"error": "Redis not connected"}), 503
    
    try:
        positions = redis_store.get_all_positions()
        return jsonify({
            "positions": list(positions.values()),
            "count": len(positions),
        })
    except Exception as e:
        logger.error("positions_fetch_error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/api/orders')
def get_orders():
    """Get recent orders."""
    if not redis_store:
        return jsonify({"error": "Redis not connected"}), 503
    
    try:
        # Get all order keys
        pattern = f"{RedisStateStore.ORDERS_PREFIX}:*"
        keys = redis_store.client.keys(pattern)
        
        orders = []
        for key in keys[:50]:  # Limit to 50 most recent
            data = redis_store.client.get(key)
            if data:
                order = json.loads(data)
                orders.append(order)
        
        # Sort by timestamp (newest first)
        orders.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return jsonify({
            "orders": orders[:20],  # Return 20 most recent
            "count": len(orders),
        })
    except Exception as e:
        logger.error("orders_fetch_error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/api/metrics')
def get_metrics():
    """Get performance metrics."""
    if not redis_store:
        return jsonify({"error": "Redis not connected"}), 503
    
    try:
        # Get initial equity
        initial_equity = redis_store.client.get(f"{RedisStateStore.STATE_PREFIX}:initial_equity")
        initial_equity = float(initial_equity) if initial_equity else 100000.0
        
        # Get current equity (from account if available, otherwise use initial)
        current_equity = initial_equity
        if alpaca_client:
            try:
                account = alpaca_client.get_account()
                current_equity = float(account.equity)
            except Exception:
                # Use initial equity if Alpaca fails
                pass
        
        # If still using initial, try to get from Redis history
        if current_equity == initial_equity and redis_store:
            try:
                equity_key = f"{RedisStateStore.STATE_PREFIX}:equity_history"
                last_equity = redis_store.client.lindex(equity_key, -1)
                if last_equity:
                    current_equity = float(last_equity)
            except Exception:
                pass
        
        # Calculate returns
        daily_return = ((current_equity - initial_equity) / initial_equity) * 100 if initial_equity > 0 else 0
        
        # Get positions count
        positions = redis_store.get_all_positions()
        
        # Store equity history for charting
        equity_key = f"{RedisStateStore.STATE_PREFIX}:equity_history"
        history = redis_store.client.lrange(equity_key, -100, -1)  # Last 100 points
        equity_history = [float(h) for h in history] if history else []
        
        # Add current equity to history
        redis_store.client.rpush(equity_key, current_equity)
        redis_store.client.ltrim(equity_key, -100, -1)  # Keep only last 100
        
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "equity": current_equity,
            "initial_equity": initial_equity,
            "daily_return_pct": daily_return,
            "cumulative_return_pct": daily_return,  # Simplified for now
            "num_positions": len(positions),
            "positions_value": sum(p.get("market_value", 0) for p in positions.values()),
            "equity_history": equity_history[-50:] if equity_history else [],  # Last 50 for chart
        }
        
        return jsonify(metrics)
    except Exception as e:
        logger.error("metrics_fetch_error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/api/regime')
def get_regime():
    """Get current market regime."""
    if not redis_store:
        return jsonify({"error": "Redis not connected"}), 503
    
    try:
        regime_data = redis_store.client.get(f"{RedisStateStore.STATE_PREFIX}:current_regime")
        if regime_data:
            return jsonify(json.loads(regime_data))
        
        return jsonify({
            "regime": "unknown",
            "trend": "unknown",
            "volatility": "unknown",
        })
    except Exception as e:
        logger.error("regime_fetch_error", error=str(e))
        return jsonify({"error": str(e)}), 500


@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection."""
    logger.info("dashboard_client_connected")
    emit('status', {'message': 'Connected to Market Maker Dashboard'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection."""
    logger.info("dashboard_client_disconnected")


def broadcast_updates():
    """Periodically broadcast updates to connected clients."""
    import threading
    import time
    
    def update_loop():
        while True:
            try:
                time.sleep(2)  # Update every 2 seconds
                
                if redis_store:
                    # Get latest data
                    positions = redis_store.get_all_positions()
                    
                    # Get account info if available
                    account_data = {}
                    if alpaca_client:
                        try:
                            account = alpaca_client.get_account()
                            equity = float(account.equity)
                            account_data = {
                                "equity": equity,
                                "cash": float(account.cash),
                                "buying_power": float(account.buying_power),
                            }
                            
                            # Store equity for history
                            equity_key = f"{RedisStateStore.STATE_PREFIX}:equity_history"
                            redis_store.client.rpush(equity_key, equity)
                            redis_store.client.ltrim(equity_key, -100, -1)  # Keep last 100
                        except Exception:
                            pass
                    
                    # Get recent orders
                    pattern = f"{RedisStateStore.ORDERS_PREFIX}:*"
                    keys = redis_store.client.keys(pattern)
                    recent_orders = []
                    for key in keys[:20]:  # Last 20
                        if ":client:" not in key:
                            data = redis_store.client.get(key)
                            if data:
                                recent_orders.append(json.loads(data))
                    
                    # Broadcast to all connected clients
                    socketio.emit('update', {
                        "positions": list(positions.values()),
                        "account": account_data,
                        "orders": recent_orders[:10],  # Last 10 orders
                        "timestamp": datetime.now().isoformat(),
                    })
            except Exception as e:
                logger.error("broadcast_error", error=str(e))
                time.sleep(5)
    
    thread = threading.Thread(target=update_loop, daemon=True)
    thread.start()


if __name__ == '__main__':
    init_connections()
    broadcast_updates()
    
    port = int(os.environ.get('DASHBOARD_PORT', 8080))
    logger.info("dashboard_starting", port=port)
    
    # Use threading mode instead of eventlet for better compatibility
    socketio.run(app, host='0.0.0.0', port=port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
