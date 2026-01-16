"""
Graceful shutdown handler for the main trading bot.

This module is installed in the MAIN BOT (not the watchdog)
to handle SIGTERM signals gracefully.

When the watchdog sends SIGTERM, this handler ensures:
1. No new trades are initiated
2. All pending writes are flushed
3. Database connections are closed cleanly
4. PID file is removed

This prevents the "Zombie State" where SIGKILL causes database
corruption and restart loops.
"""

import signal
import sys
import os
from pathlib import Path
from typing import Optional, Callable
import structlog

logger = structlog.get_logger(__name__)


class GracefulShutdownHandler:
    """
    Handles SIGTERM for graceful shutdown.
    
    Install this in the main trading bot to respond properly
    when the watchdog requests shutdown.
    
    Usage:
        handler = GracefulShutdownHandler()
        handler.register_cleanup(lambda: db.close())
        handler.register_cleanup(lambda: log.flush())
        handler.install()
        
        # In main loop:
        while not handler.shutdown_requested:
            # do work
    """
    
    def __init__(
        self,
        pid_file: Optional[str] = None,
    ):
        """
        Initialize shutdown handler.
        
        Args:
            pid_file: Path to PID file (will be removed on shutdown)
        """
        self.pid_file = Path(pid_file) if pid_file else None
        self.shutdown_requested = False
        self._cleanup_callbacks: list[Callable] = []
        
        logger.info("graceful_shutdown_handler_initialized")
    
    def register_cleanup(self, callback: Callable) -> None:
        """
        Register a cleanup callback to run on shutdown.
        
        Callbacks are run in reverse order of registration (LIFO).
        
        Args:
            callback: Callable to run during shutdown
        """
        self._cleanup_callbacks.append(callback)
    
    def install(self) -> None:
        """
        Install signal handlers.
        
        This installs handlers for:
        - SIGTERM: Graceful shutdown (from watchdog)
        - SIGINT: Graceful shutdown (from Ctrl+C)
        """
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        
        # Write PID file
        if self.pid_file:
            self.pid_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.pid_file, "w") as f:
                f.write(str(os.getpid()))
            logger.info("pid_file_written", path=str(self.pid_file))
        
        logger.info("signal_handlers_installed")
    
    def _handle_signal(self, signum: int, frame) -> None:
        """
        Handle shutdown signal.
        
        This is called when SIGTERM or SIGINT is received.
        """
        signal_name = signal.Signals(signum).name
        logger.info("shutdown_signal_received", signal=signal_name)
        
        self.shutdown_requested = True
        
        try:
            # Run cleanup callbacks in reverse order
            logger.info("running_cleanup_callbacks", count=len(self._cleanup_callbacks))
            
            for callback in reversed(self._cleanup_callbacks):
                try:
                    callback()
                except Exception as e:
                    logger.error("cleanup_callback_error", error=str(e))
            
            # Remove PID file
            if self.pid_file and self.pid_file.exists():
                self.pid_file.unlink()
                logger.info("pid_file_removed")
            
            logger.info("graceful_shutdown_complete")
            sys.exit(0)
            
        except Exception as e:
            logger.error("graceful_shutdown_error", error=str(e))
            sys.exit(1)
    
    def should_shutdown(self) -> bool:
        """
        Check if shutdown has been requested.
        
        Use this in your main loop:
        
            while not handler.should_shutdown():
                # do work
        """
        return self.shutdown_requested


class ShutdownCoordinator:
    """
    Coordinates shutdown across multiple components.
    
    This is a higher-level abstraction that manages
    the shutdown of complex systems with multiple
    interdependent components.
    """
    
    def __init__(self):
        self.handler = GracefulShutdownHandler()
        self._components: dict[str, dict] = {}
    
    def register_component(
        self,
        name: str,
        cleanup_fn: Callable,
        priority: int = 0,
    ) -> None:
        """
        Register a component for coordinated shutdown.
        
        Components are shut down in priority order (highest first).
        
        Args:
            name: Component name (for logging)
            cleanup_fn: Cleanup function
            priority: Shutdown priority (higher = earlier)
        """
        self._components[name] = {
            "cleanup_fn": cleanup_fn,
            "priority": priority,
        }
    
    def install(self, pid_file: Optional[str] = None) -> None:
        """Install signal handlers and configure shutdown."""
        self.handler.pid_file = Path(pid_file) if pid_file else None
        
        # Register all components as cleanup callbacks
        # Sort by priority (descending)
        sorted_components = sorted(
            self._components.items(),
            key=lambda x: x[1]["priority"],
            reverse=True,
        )
        
        for name, config in sorted_components:
            def make_cleanup(n: str, fn: Callable) -> Callable:
                def cleanup():
                    logger.info("shutting_down_component", component=n)
                    fn()
                return cleanup
            
            self.handler.register_cleanup(make_cleanup(name, config["cleanup_fn"]))
        
        self.handler.install()
    
    def should_shutdown(self) -> bool:
        """Check if shutdown requested."""
        return self.handler.should_shutdown()


def create_shutdown_handler_for_bot(
    append_log,
    duckdb_store,
    redis_state,
    pid_file: str = "/tmp/market_maker/bot.pid",
) -> GracefulShutdownHandler:
    """
    Create a configured shutdown handler for the trading bot.
    
    This is a convenience function that sets up proper cleanup
    for all major components.
    
    Args:
        append_log: AppendOnlyLog instance
        duckdb_store: DuckDBStore instance
        redis_state: RedisStateStore instance
        pid_file: Path to PID file
    
    Returns:
        Configured GracefulShutdownHandler
    """
    handler = GracefulShutdownHandler(pid_file=pid_file)
    
    # Register cleanups in reverse dependency order
    # (Redis last because strategies might need it during cleanup)
    
    # 1. Flush append log first (most critical data)
    handler.register_cleanup(lambda: (
        logger.info("flushing_append_log"),
        append_log.flush(),
        append_log.close(),
    ))
    
    # 2. Close DuckDB
    handler.register_cleanup(lambda: (
        logger.info("closing_duckdb"),
        duckdb_store.close(),
    ))
    
    # 3. Close Redis last
    handler.register_cleanup(lambda: (
        logger.info("closing_redis"),
        redis_state.close(),
    ))
    
    return handler
