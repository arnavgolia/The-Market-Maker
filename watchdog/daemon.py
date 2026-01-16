"""
Independent Watchdog Daemon.

This is the main watchdog process that monitors the trading bot
and enforces kill rules. It runs as a COMPLETELY SEPARATE process.

Key principles:
- Independent from main bot (separate process, separate credentials)
- Direct broker access (can liquidate without main bot)
- Graceful shutdown first (SIGTERM), SIGKILL only as fallback
- Human intervention required after critical failures
"""

import os
import sys
import signal
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import structlog

from watchdog.rules import KillRules, DEFAULT_RULES, get_warning_thresholds
from watchdog.broker_client import WatchdogBrokerClient
from watchdog.alert_dispatcher import AlertDispatcher

logger = structlog.get_logger(__name__)


class WatchdogDaemon:
    """
    Independent watchdog daemon.
    
    CRITICAL: This process must be completely independent:
    - Separate Python interpreter
    - Separate config file
    - Direct broker API credentials (not shared)
    - No shared memory with main bot
    
    The watchdog's job is to:
    1. Monitor the trading bot's health
    2. Enforce kill rules
    3. Liquidate positions in emergency
    4. Prevent restart without human intervention after critical failures
    """
    
    def __init__(
        self,
        rules: KillRules = DEFAULT_RULES,
        broker_client: Optional[WatchdogBrokerClient] = None,
        alerter: Optional[AlertDispatcher] = None,
        main_bot_pid_file: str = "/tmp/market_maker/bot.pid",
        check_interval_seconds: int = 30,
    ):
        """
        Initialize watchdog daemon.
        
        Args:
            rules: Kill rules to enforce
            broker_client: Direct broker client (separate from main bot)
            alerter: Alert dispatcher
            main_bot_pid_file: Path to main bot's PID file
            check_interval_seconds: How often to check rules
        """
        self.rules = rules
        self.broker = broker_client or WatchdogBrokerClient()
        self.alerter = alerter or AlertDispatcher()
        self.pid_file = Path(main_bot_pid_file)
        self.check_interval = check_interval_seconds
        
        # State tracking
        self.last_heartbeat: Optional[datetime] = None
        self.restart_attempts = 0
        self.last_restart_time: Optional[datetime] = None
        self.order_timestamps: list[datetime] = []
        self.initial_equity: Optional[float] = None
        self.permanent_shutdown = False
        
        # Warning thresholds
        self.warnings = get_warning_thresholds()
        
        logger.info(
            "watchdog_daemon_initialized",
            pid_file=str(self.pid_file),
            check_interval=check_interval_seconds,
        )
    
    def run(self) -> None:
        """
        Main watchdog loop - runs forever.
        
        This is the entry point for the watchdog process.
        """
        logger.info("watchdog_daemon_starting")
        
        # Record initial equity on startup
        self._record_initial_equity()
        
        while True:
            try:
                if self.permanent_shutdown:
                    logger.critical(
                        "permanent_shutdown_active",
                        message="Watchdog refusing to monitor. Human intervention required.",
                    )
                    time.sleep(60)
                    continue
                
                self._check_all_rules()
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                logger.info("watchdog_interrupted")
                break
            except Exception as e:
                logger.error("watchdog_error", error=str(e))
                self.alerter.send_warning(f"Watchdog internal error: {e}")
                time.sleep(60)  # Back off on error
    
    def _record_initial_equity(self) -> None:
        """Record initial equity for drawdown calculation."""
        try:
            account = self.broker.get_account()
            self.initial_equity = float(account.equity)
            logger.info("initial_equity_recorded", equity=self.initial_equity)
        except Exception as e:
            logger.error("failed_to_record_initial_equity", error=str(e))
    
    def _check_all_rules(self) -> None:
        """
        Check all kill rules.
        
        Any breach triggers protective action.
        """
        # Get current state from broker
        try:
            account = self.broker.get_account()
            positions = self.broker.list_positions()
            open_orders = self.broker.list_orders(status="open")
        except Exception as e:
            logger.error("broker_query_failed", error=str(e))
            # Check if this is an API health issue
            if not self._is_broker_api_healthy():
                logger.warning("broker_api_unhealthy_deferring_checks")
                return
            raise
        
        equity = float(account.equity)
        last_equity = float(account.last_equity)
        
        # Calculate daily PnL
        daily_pnl_pct = 0.0
        if last_equity > 0:
            daily_pnl_pct = ((equity - last_equity) / last_equity) * 100
        
        # ==========================================================================
        # RULE 1: Daily Loss Limit
        # ==========================================================================
        breached, reason = self.rules.check_daily_loss(daily_pnl_pct)
        if breached:
            self._emergency_shutdown(reason)
            return
        
        # Warning check
        if daily_pnl_pct < self.warnings["daily_loss_warning_pct"]:
            self.alerter.send_warning(f"Daily loss warning: {daily_pnl_pct:.2f}%")
        
        # ==========================================================================
        # RULE 2: Max Drawdown (Permanent Shutdown)
        # ==========================================================================
        if self.initial_equity:
            breached, reason = self.rules.check_max_drawdown(equity, self.initial_equity)
            if breached:
                self._permanent_shutdown(reason)
                return
        
        # ==========================================================================
        # RULE 3: Position Concentration
        # ==========================================================================
        for pos in positions:
            market_value = float(pos.market_value)
            breached, reason = self.rules.check_position_concentration(market_value, equity)
            if breached:
                self._emergency_shutdown(f"{reason} (symbol: {pos.symbol})")
                return
        
        # ==========================================================================
        # RULE 4: Open Order Count
        # ==========================================================================
        breached, reason = self.rules.check_open_orders(len(open_orders))
        if breached:
            self._emergency_shutdown(reason)
            return
        
        # ==========================================================================
        # RULE 5: Zombie Orders (Gemini's recommendation)
        # ==========================================================================
        if open_orders:
            oldest_order_time = min(
                datetime.fromisoformat(str(o.created_at).replace('Z', '+00:00').replace('+00:00', ''))
                for o in open_orders
            )
            age_seconds = (datetime.now() - oldest_order_time).total_seconds()
            
            breached, reason = self.rules.check_zombie_orders(age_seconds)
            if breached:
                self._emergency_shutdown(reason)
                return
        
        # ==========================================================================
        # RULE 6: Heartbeat (checked via Redis or file)
        # ==========================================================================
        # Note: In production, check Redis or a heartbeat file
        # For now, we assume heartbeat is healthy if we can query broker
        
        logger.debug(
            "watchdog_check_passed",
            equity=equity,
            daily_pnl_pct=daily_pnl_pct,
            open_orders=len(open_orders),
            positions=len(positions),
        )
    
    def _is_broker_api_healthy(self) -> bool:
        """
        Check if broker API is responsive.
        
        Prevents killing bot due to API latency issues.
        """
        try:
            start = time.time()
            self.broker.get_clock()
            latency = time.time() - start
            
            if latency > self.rules.max_api_latency_seconds:
                logger.warning("broker_api_slow", latency_seconds=latency)
                return False
            
            return True
        except Exception as e:
            logger.error("broker_api_check_failed", error=str(e))
            return False
    
    def _emergency_shutdown(self, reason: str) -> None:
        """
        Emergency shutdown: Liquidate all positions and kill bot.
        
        This is triggered when a kill rule is breached.
        """
        logger.critical("EMERGENCY_SHUTDOWN", reason=reason)
        self.alerter.send_critical(f"EMERGENCY SHUTDOWN: {reason}")
        
        try:
            # Step 1: Cancel all open orders
            logger.info("cancelling_all_orders")
            self.broker.cancel_all_orders()
            time.sleep(2)  # Allow cancellations to process
            
            # Step 2: Close all positions
            logger.info("closing_all_positions")
            self.broker.close_all_positions()
            
            # Step 3: Kill the main bot (graceful first)
            self._kill_main_bot()
            
        except Exception as e:
            logger.critical("emergency_shutdown_failed", error=str(e))
            self.alerter.send_critical(f"EMERGENCY SHUTDOWN FAILED: {e}")
    
    def _permanent_shutdown(self, reason: str) -> None:
        """
        Permanent shutdown: Max drawdown breached.
        
        This is the "nuclear option" - requires human intervention to restart.
        Implements Gemini's "Equity Hard-Stop" recommendation.
        """
        logger.critical("PERMANENT_SHUTDOWN", reason=reason)
        self.alerter.send_critical(f"PERMANENT SHUTDOWN: {reason}")
        
        # First, do emergency shutdown
        self._emergency_shutdown(reason)
        
        # Then, set permanent shutdown flag
        self.permanent_shutdown = True
        
        # In production, you might delete API keys here
        # self._delete_api_keys()
        
        logger.critical(
            "SYSTEM_HALTED",
            message="System halted. Human intervention required to restart.",
        )
    
    def _kill_main_bot(self) -> None:
        """
        Kill the main bot process.
        
        Protocol:
        1. Send SIGTERM (graceful) - wait for cleanup
        2. Only SIGKILL if graceful fails
        3. Track restart attempts
        """
        pid = self._get_main_bot_pid()
        
        if pid is None:
            logger.warning("main_bot_pid_not_found")
            return
        
        # Check restart cooldown
        if self.last_restart_time:
            time_since = datetime.now() - self.last_restart_time
            if time_since < timedelta(seconds=self.rules.restart_cooldown_seconds):
                remaining = self.rules.restart_cooldown_seconds - time_since.seconds
                logger.warning("restart_cooldown_active", remaining_seconds=remaining)
                return
        
        # Check restart limit
        if self.restart_attempts >= self.rules.max_restart_attempts:
            logger.critical(
                "max_restart_attempts_exceeded",
                attempts=self.restart_attempts,
            )
            self.alerter.send_critical(
                "Max restart attempts exceeded. Human intervention required."
            )
            return
        
        logger.info("attempting_graceful_shutdown", pid=pid)
        
        # Step 1: SIGTERM (graceful)
        try:
            os.kill(pid, signal.SIGTERM)
            logger.info("sigterm_sent", pid=pid)
        except ProcessLookupError:
            logger.info("process_already_dead", pid=pid)
            return
        except PermissionError:
            logger.error("permission_denied_killing_process", pid=pid)
            return
        
        # Step 2: Wait for graceful exit
        graceful_success = self._wait_for_exit(
            pid,
            timeout=self.rules.graceful_shutdown_timeout_seconds,
        )
        
        if graceful_success:
            logger.info("graceful_shutdown_successful", pid=pid)
        else:
            # Step 3: SIGKILL as last resort
            logger.warning("graceful_shutdown_failed_sending_sigkill", pid=pid)
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # Already dead
            
            self.alerter.send_warning(
                "Bot required SIGKILL - check for database corruption"
            )
        
        # Update restart tracking
        self.restart_attempts += 1
        self.last_restart_time = datetime.now()
        
        # Clean up PID file
        if self.pid_file.exists():
            self.pid_file.unlink()
    
    def _wait_for_exit(self, pid: int, timeout: int) -> bool:
        """Wait for process to exit, return True if exited gracefully."""
        start = time.time()
        
        while time.time() - start < timeout:
            try:
                os.kill(pid, 0)  # Check if process exists
                time.sleep(1)
            except ProcessLookupError:
                return True  # Process exited
        
        return False  # Timeout
    
    def _get_main_bot_pid(self) -> Optional[int]:
        """Read main bot PID from file."""
        try:
            if not self.pid_file.exists():
                return None
            
            with open(self.pid_file) as f:
                return int(f.read().strip())
        except (ValueError, IOError) as e:
            logger.error("failed_to_read_pid", error=str(e))
            return None
    
    def receive_heartbeat(self) -> None:
        """
        Called when heartbeat is received from main bot.
        
        In production, this might be called via Redis pub/sub or HTTP.
        """
        self.last_heartbeat = datetime.now()
        self.restart_attempts = 0  # Reset on successful heartbeat


def main():
    """Entry point for watchdog process."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Market Maker Watchdog")
    parser.add_argument(
        "--pid-file",
        default="/tmp/market_maker/bot.pid",
        help="Path to main bot PID file",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Check interval in seconds",
    )
    
    args = parser.parse_args()
    
    # Configure logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )
    
    daemon = WatchdogDaemon(
        main_bot_pid_file=args.pid_file,
        check_interval_seconds=args.interval,
    )
    
    daemon.run()


if __name__ == "__main__":
    main()
