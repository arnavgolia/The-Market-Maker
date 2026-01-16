#!/usr/bin/env python3
"""
FastAPI Backend for Fidelity-Grade Trading Platform.

Provides REST and WebSocket endpoints with:
- Multiplexed WebSocket with sequence numbers
- Read-only access to Market Maker data stores
- Real-time position, equity, and market data streaming
"""

import os
import sys
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Set, Any
from contextlib import asynccontextmanager

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import structlog

from src.storage.redis_state import RedisStateStore
from src.storage.duckdb_store import DuckDBStore
from api.services.websocket_manager import WebSocketManager

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

# Global state
redis_store: Optional[RedisStateStore] = None
duckdb_store: Optional[DuckDBStore] = None
ws_manager: Optional[WebSocketManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI app."""
    global redis_store, duckdb_store, ws_manager
    
    # Startup
    logger.info("api_starting")
    
    try:
        # Initialize Redis
        redis_store = RedisStateStore(
            host=os.environ.get('REDIS_HOST', 'localhost'),
            port=int(os.environ.get('REDIS_PORT', 6379)),
            db=int(os.environ.get('REDIS_DB', 0)),
        )
        logger.info("redis_connected")
    except Exception as e:
        logger.error("redis_connection_failed", error=str(e))
        redis_store = None
    
    try:
        # Initialize DuckDB (read-only)
        db_path = os.path.expandvars(os.environ.get('DUCKDB_PATH', 'data/market_maker.duckdb'))
        duckdb_store = DuckDBStore(db_path, read_only=True)
        logger.info("duckdb_connected", path=db_path)
    except Exception as e:
        logger.error("duckdb_connection_failed", error=str(e))
        duckdb_store = None
    
    # Initialize WebSocket Manager
    ws_manager = WebSocketManager(redis_store, duckdb_store)
    
    # Start background broadcast task
    broadcast_task = asyncio.create_task(ws_manager.broadcast_loop())
    
    logger.info("api_ready")
    
    yield
    
    # Shutdown
    logger.info("api_shutting_down")
    broadcast_task.cancel()
    try:
        await broadcast_task
    except asyncio.CancelledError:
        pass
    
    if redis_store:
        redis_store.close()
    
    logger.info("api_shutdown_complete")


app = FastAPI(
    title="Market Maker API",
    description="Fidelity-grade trading platform API",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8080"],  # Frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency to get stores
def get_redis() -> RedisStateStore:
    if redis_store is None:
        raise HTTPException(status_code=503, detail="Redis not connected")
    return redis_store


def get_duckdb() -> DuckDBStore:
    if duckdb_store is None:
        raise HTTPException(status_code=503, detail="DuckDB not connected")
    return duckdb_store


# ============================================================================
# REST Endpoints
# ============================================================================

@app.get("/api/v1/health")
async def health_check():
    """System health check."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "redis": redis_store is not None,
        "duckdb": duckdb_store is not None,
        "websocket": ws_manager is not None,
    }


@app.get("/api/v1/portfolio/positions")
async def get_positions(redis: RedisStateStore = Depends(get_redis)):
    """Get all current positions."""
    try:
        positions = redis.get_all_positions()
        return {
            "positions": list(positions.values()),
            "count": len(positions),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.error("positions_fetch_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/portfolio/equity")
async def get_equity(redis: RedisStateStore = Depends(get_redis)):
    """Get current equity and equity history."""
    try:
        initial_equity = redis.get_initial_equity() or 100000.0
        equity_history = redis.get_equity_history()
        
        current_equity = equity_history[-1]["equity"] if equity_history else initial_equity
        
        return {
            "current_equity": current_equity,
            "initial_equity": initial_equity,
            "daily_return_pct": ((current_equity - initial_equity) / initial_equity) * 100,
            "equity_history": equity_history[-500:],  # Last 500 points for chart
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.error("equity_fetch_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/portfolio/orders")
async def get_orders(redis: RedisStateStore = Depends(get_redis), limit: int = 50):
    """Get recent orders."""
    try:
        # Get all order keys
        pattern = f"{RedisStateStore.ORDERS_PREFIX}:*"
        keys = redis.client.keys(pattern)
        
        orders = []
        for key in keys[:limit]:
            if ":client:" in key:
                continue
            data = redis.client.get(key)
            if data:
                orders.append(json.loads(data))
        
        # Sort by created_at (newest first)
        orders.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return {
            "orders": orders[:limit],
            "count": len(orders),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.error("orders_fetch_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/system/status")
async def get_system_status(redis: RedisStateStore = Depends(get_redis)):
    """Get system health status."""
    try:
        # Check main bot heartbeat
        main_bot_alive = redis.is_process_alive("main_bot", max_age_seconds=120)
        
        # Get Redis stats
        redis_stats = redis.get_stats() if redis else {}
        
        return {
            "components": {
                "main_bot": {
                    "status": "ok" if main_bot_alive else "warning",
                    "last_heartbeat": redis.check_heartbeat("main_bot").isoformat() if main_bot_alive else None,
                },
                "redis": {
                    "status": "ok",
                    "stats": redis_stats,
                },
                "duckdb": {
                    "status": "ok" if duckdb_store else "error",
                },
            },
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.error("system_status_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/regime/current")
async def get_current_regime(redis: RedisStateStore = Depends(get_redis)):
    """Get current market regime."""
    try:
        regime_data = redis.get_state("current_regime")
        if regime_data:
            return json.loads(regime_data) if isinstance(regime_data, str) else regime_data
        
        return {
            "trend_regime": "unknown",
            "vol_regime": "unknown",
            "momentum_enabled": False,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.error("regime_fetch_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/system/emergency-halt")
async def emergency_halt(redis: RedisStateStore = Depends(get_redis)):
    """
    Emergency halt endpoint.
    
    Triggers emergency stop by setting halt flag in Redis.
    Main bot must check this flag and stop trading when set.
    """
    try:
        # Set halt flag
        redis.set_state("emergency_halt", "true")
        
        logger.critical("emergency_halt_triggered", timestamp=datetime.utcnow().isoformat())
        
        return {
            "status": "halted",
            "message": "Emergency halt triggered. Trading stopped.",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.error("emergency_halt_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WebSocket Endpoint (Multiplexed)
# ============================================================================

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    """
    Multiplexed WebSocket endpoint with sequence numbers.
    
    Client can subscribe to multiple channels:
    - positions: Position updates
    - equity: Equity updates
    - orders: Order updates
    - regime: Regime changes
    - health: System health
    - market:{symbol}: Market data for specific symbol
    """
    await ws_manager.connect(websocket)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("API_PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )
