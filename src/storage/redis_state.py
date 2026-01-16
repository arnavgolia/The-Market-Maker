"""
Redis state store for live trading state.

Redis is used for:
- Current positions
- Open orders
- Order state machine state
- Heartbeat tracking
- Quick key-value lookups

This is the only component that tracks mutable state.
The append log and DuckDB are append-only / read-heavy.
"""

import json
from datetime import datetime, timedelta
from typing import Any, Optional
import structlog

import redis

logger = structlog.get_logger(__name__)


class RedisStateStore:
    """
    Redis-based state store for live trading operations.
    
    Design principles:
    - Atomic operations for critical state
    - TTL on ephemeral data (heartbeats, locks)
    - Structured key naming for organization
    - Broker is TRUTH, Redis is CACHE
    
    Key naming convention:
    - mm:positions:{symbol} - Position state
    - mm:orders:{order_id} - Order state
    - mm:orders:client:{client_id} - Order lookup by client ID
    - mm:heartbeat:{process} - Process heartbeat
    - mm:state:{key} - General state
    """
    
    # Key prefixes
    PREFIX = "mm"
    POSITIONS_PREFIX = f"{PREFIX}:positions"
    ORDERS_PREFIX = f"{PREFIX}:orders"
    HEARTBEAT_PREFIX = f"{PREFIX}:heartbeat"
    STATE_PREFIX = f"{PREFIX}:state"
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        socket_timeout: float = 5.0,
    ):
        """
        Initialize Redis connection.
        
        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password (optional)
            socket_timeout: Socket timeout in seconds
        """
        self.client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            socket_timeout=socket_timeout,
            decode_responses=True,  # Return strings, not bytes
        )
        
        # Test connection
        try:
            self.client.ping()
            logger.info(
                "redis_connected",
                host=host,
                port=port,
                db=db,
            )
        except redis.ConnectionError as e:
            logger.error("redis_connection_failed", error=str(e))
            raise
    
    # =========================================================================
    # Position State
    # =========================================================================
    
    def set_position(
        self,
        symbol: str,
        qty: float,
        avg_price: float,
        market_value: float,
        unrealized_pnl: float,
        side: str,
    ) -> None:
        """
        Set position state.
        
        NOTE: Broker positions are TRUTH. This is a cache for fast lookups.
        Always reconcile with broker periodically.
        """
        key = f"{self.POSITIONS_PREFIX}:{symbol}"
        
        data = {
            "symbol": symbol,
            "qty": qty,
            "avg_price": avg_price,
            "market_value": market_value,
            "unrealized_pnl": unrealized_pnl,
            "side": side,
            "updated_at": datetime.now().isoformat(),
        }
        
        self.client.set(key, json.dumps(data))
        logger.debug("position_set", symbol=symbol, qty=qty)
    
    def get_position(self, symbol: str) -> Optional[dict]:
        """Get position state for a symbol."""
        key = f"{self.POSITIONS_PREFIX}:{symbol}"
        data = self.client.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    def get_all_positions(self) -> dict[str, dict]:
        """Get all position states."""
        pattern = f"{self.POSITIONS_PREFIX}:*"
        keys = self.client.keys(pattern)
        
        positions = {}
        for key in keys:
            data = self.client.get(key)
            if data:
                position = json.loads(data)
                positions[position["symbol"]] = position
        
        return positions
    
    def delete_position(self, symbol: str) -> None:
        """Delete a position (when closed)."""
        key = f"{self.POSITIONS_PREFIX}:{symbol}"
        self.client.delete(key)
        logger.debug("position_deleted", symbol=symbol)
    
    def sync_positions(self, broker_positions: list[dict]) -> None:
        """
        Sync positions with broker truth.
        
        This clears all cached positions and replaces with broker data.
        Broker is TRUTH.
        """
        # Clear existing positions
        pattern = f"{self.POSITIONS_PREFIX}:*"
        keys = self.client.keys(pattern)
        if keys:
            self.client.delete(*keys)
        
        # Set new positions
        for pos in broker_positions:
            self.set_position(
                symbol=pos["symbol"],
                qty=pos["qty"],
                avg_price=pos["avg_price"],
                market_value=pos["market_value"],
                unrealized_pnl=pos.get("unrealized_pnl", 0),
                side=pos["side"],
            )
        
        logger.info("positions_synced", count=len(broker_positions))
    
    # =========================================================================
    # Order State
    # =========================================================================
    
    def set_order(
        self,
        order_id: str,
        client_order_id: str,
        symbol: str,
        side: str,
        qty: float,
        order_type: str,
        status: str,
        limit_price: Optional[float] = None,
        filled_qty: Optional[float] = None,
        filled_price: Optional[float] = None,
        created_at: Optional[datetime] = None,
    ) -> None:
        """Set order state."""
        key = f"{self.ORDERS_PREFIX}:{order_id}"
        client_key = f"{self.ORDERS_PREFIX}:client:{client_order_id}"
        
        data = {
            "order_id": order_id,
            "client_order_id": client_order_id,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_type": order_type,
            "status": status,
            "limit_price": limit_price,
            "filled_qty": filled_qty,
            "filled_price": filled_price,
            "created_at": (created_at or datetime.now()).isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        
        # Store by both order_id and client_order_id
        self.client.set(key, json.dumps(data))
        self.client.set(client_key, order_id)  # Map client_id -> order_id
        
        logger.debug("order_set", order_id=order_id, status=status)
    
    def get_order(self, order_id: str) -> Optional[dict]:
        """Get order by order ID."""
        key = f"{self.ORDERS_PREFIX}:{order_id}"
        data = self.client.get(key)
        return json.loads(data) if data else None
    
    def get_order_by_client_id(self, client_order_id: str) -> Optional[dict]:
        """Get order by client order ID (for reconciliation)."""
        client_key = f"{self.ORDERS_PREFIX}:client:{client_order_id}"
        order_id = self.client.get(client_key)
        
        if order_id:
            return self.get_order(order_id)
        return None
    
    def update_order_status(
        self,
        order_id: str,
        status: str,
        filled_qty: Optional[float] = None,
        filled_price: Optional[float] = None,
    ) -> None:
        """Update order status."""
        order = self.get_order(order_id)
        
        if order:
            order["status"] = status
            order["updated_at"] = datetime.now().isoformat()
            
            if filled_qty is not None:
                order["filled_qty"] = filled_qty
            if filled_price is not None:
                order["filled_price"] = filled_price
            
            key = f"{self.ORDERS_PREFIX}:{order_id}"
            self.client.set(key, json.dumps(order))
            
            logger.debug("order_status_updated", order_id=order_id, status=status)
    
    def get_open_orders(self) -> list[dict]:
        """Get all open orders."""
        pattern = f"{self.ORDERS_PREFIX}:*"
        keys = self.client.keys(pattern)
        
        open_orders = []
        for key in keys:
            # Skip client_id mapping keys
            if ":client:" in key:
                continue
            
            data = self.client.get(key)
            if data:
                order = json.loads(data)
                if order.get("status") in ("pending", "submitted", "partial_fill", "new", "accepted"):
                    open_orders.append(order)
        
        return open_orders
    
    def get_zombie_orders(self, max_age_seconds: int = 300) -> list[dict]:
        """
        Get orders that have been open too long (zombie detection).
        
        This implements Gemini's "Zombie Check" recommendation.
        Orders should fill, cancel, or fail - never hang.
        """
        threshold = datetime.now() - timedelta(seconds=max_age_seconds)
        
        open_orders = self.get_open_orders()
        zombies = []
        
        for order in open_orders:
            created_at = datetime.fromisoformat(order["created_at"])
            if created_at < threshold:
                zombies.append(order)
        
        if zombies:
            logger.warning(
                "zombie_orders_detected",
                count=len(zombies),
                max_age_seconds=max_age_seconds,
            )
        
        return zombies
    
    def delete_order(self, order_id: str) -> None:
        """Delete order state (after terminal state reached)."""
        order = self.get_order(order_id)
        
        if order:
            key = f"{self.ORDERS_PREFIX}:{order_id}"
            client_key = f"{self.ORDERS_PREFIX}:client:{order['client_order_id']}"
            
            self.client.delete(key, client_key)
            logger.debug("order_deleted", order_id=order_id)
    
    # =========================================================================
    # Heartbeat
    # =========================================================================
    
    def send_heartbeat(self, process_name: str, ttl_seconds: int = 120) -> None:
        """
        Send a heartbeat for a process.
        
        Args:
            process_name: Name of the process (e.g., "main_bot", "sentiment_scraper")
            ttl_seconds: Time-to-live for the heartbeat
        """
        key = f"{self.HEARTBEAT_PREFIX}:{process_name}"
        
        data = {
            "process": process_name,
            "timestamp": datetime.now().isoformat(),
        }
        
        self.client.setex(key, ttl_seconds, json.dumps(data))
    
    def check_heartbeat(self, process_name: str) -> Optional[datetime]:
        """
        Check last heartbeat for a process.
        
        Returns the timestamp of the last heartbeat, or None if no heartbeat found.
        """
        key = f"{self.HEARTBEAT_PREFIX}:{process_name}"
        data = self.client.get(key)
        
        if data:
            heartbeat = json.loads(data)
            return datetime.fromisoformat(heartbeat["timestamp"])
        return None
    
    def is_process_alive(self, process_name: str, max_age_seconds: int = 120) -> bool:
        """Check if a process is alive based on heartbeat."""
        last_heartbeat = self.check_heartbeat(process_name)
        
        if last_heartbeat is None:
            return False
        
        age = (datetime.now() - last_heartbeat).total_seconds()
        return age < max_age_seconds
    
    # =========================================================================
    # General State
    # =========================================================================
    
    def set_state(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Set a general state value."""
        full_key = f"{self.STATE_PREFIX}:{key}"
        data = json.dumps(value) if not isinstance(value, str) else value
        
        if ttl_seconds:
            self.client.setex(full_key, ttl_seconds, data)
        else:
            self.client.set(full_key, data)
    
    def get_state(self, key: str) -> Optional[Any]:
        """Get a general state value."""
        full_key = f"{self.STATE_PREFIX}:{key}"
        data = self.client.get(full_key)
        
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return data
        return None
    
    def delete_state(self, key: str) -> None:
        """Delete a state key."""
        full_key = f"{self.STATE_PREFIX}:{key}"
        self.client.delete(full_key)
    
    # =========================================================================
    # Initial Equity (for max drawdown calculation)
    # =========================================================================
    
    def set_initial_equity(self, equity: float) -> None:
        """Set initial equity for drawdown calculation."""
        self.set_state("initial_equity", equity)
        logger.info("initial_equity_set", equity=equity)
    
    def get_initial_equity(self) -> Optional[float]:
        """Get initial equity."""
        return self.get_state("initial_equity")
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def ping(self) -> bool:
        """Check if Redis is responding."""
        try:
            return self.client.ping()
        except Exception:
            return False
    
    def flush_all(self) -> None:
        """
        Clear all data (DANGEROUS - for testing only).
        """
        logger.critical("flushing_all_redis_data")
        pattern = f"{self.PREFIX}:*"
        keys = self.client.keys(pattern)
        if keys:
            self.client.delete(*keys)
    
    def close(self) -> None:
        """Close Redis connection."""
        self.client.close()
        logger.info("redis_connection_closed")
    
    def get_stats(self) -> dict:
        """Get Redis stats for monitoring."""
        info = self.client.info()
        
        return {
            "connected_clients": info.get("connected_clients"),
            "used_memory_human": info.get("used_memory_human"),
            "total_commands_processed": info.get("total_commands_processed"),
            "uptime_in_seconds": info.get("uptime_in_seconds"),
        }
