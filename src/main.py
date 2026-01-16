"""
Main Market Maker application.

This is the entry point for the trading bot. It coordinates:
- Data ingestion
- Strategy execution
- Risk management
- Order execution
- Monitoring

CRITICAL: Run the watchdog in a separate process:
    python scripts/run_watchdog.py
"""

import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import structlog
import yaml

from src.data.ingestion.alpaca_client import AlpacaDataClient
from src.storage.append_log import AppendOnlyLog, Event, EventType
from src.storage.duckdb_store import DuckDBStore
from src.storage.redis_state import RedisStateStore
from src.storage.etl_pipeline import ETLPipeline
from src.regime.detector import RegimeDetector
from src.strategy.tier1.ema_crossover import EMACrossoverStrategy
from src.strategy.tier1.rsi_mean_reversion import RSIMeanReversionStrategy
from src.risk.position_sizer import PositionSizer, PositionSizingMethod
from src.risk.drawdown_monitor import DrawdownMonitor
from src.portfolio.allocator import PortfolioAllocator
from src.execution.order_manager import OrderManager
from src.execution.reconciler import OrderReconciler
from src.execution.paper_broker import PaperBroker
from src.monitoring.metrics import MetricsCollector
from src.monitoring.alerter import Alerter
from src.monitoring.decay_detector import StrategyDecayDetector
from watchdog.graceful_shutdown import create_shutdown_handler_for_bot

logger = structlog.get_logger(__name__)


class MarketMaker:
    """
    Main trading bot application.
    
    This coordinates all components:
    - Data ingestion from Alpaca
    - Storage (AppendOnlyLog, DuckDB, Redis)
    - Strategy execution (Tier 1, 2, 3)
    - Risk management
    - Order execution
    - Monitoring and heartbeats
    """
    
    def __init__(
        self,
        config_path: str = "config/settings.yaml",
        dry_run: bool = False,
    ):
        """
        Initialize the Market Maker.
        
        Args:
            config_path: Path to configuration file
            dry_run: If True, don't execute actual trades
        """
        self.dry_run = dry_run
        
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Initialize components
        self._init_storage()
        self._init_data_clients()
        self._init_strategies()
        self._init_risk_management()
        self._init_execution()
        self._init_monitoring()
        self._init_etl()
        self._init_shutdown_handler()
        
        # State
        self.running = False
        self.last_heartbeat = datetime.now()
        self.last_reconciliation = datetime.now()
        self.last_etl_run = datetime.now()
        
        logger.info(
            "market_maker_initialized",
            dry_run=dry_run,
            config_path=config_path,
        )
    
    def _load_config(self, path: str) -> dict:
        """Load configuration from YAML file."""
        config_path = Path(path)
        
        if not config_path.exists():
            logger.warning("config_not_found_using_defaults", path=path)
            return self._default_config()
        
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        logger.info("config_loaded", path=path)
        return config
    
    def _default_config(self) -> dict:
        """Return default configuration."""
        return {
            "environment": "paper",
            "log_level": "INFO",
            "storage": {
                "append_log": {"path": "data/logs/events.jsonl"},
                "duckdb": {"path": "data/market_maker.duckdb"},
                "redis": {"host": "localhost", "port": 6379},
            },
            "strategies": {"enabled": True},
        }
    
    def _expand_env_vars(self, value: str) -> str:
        """Expand environment variables in config values."""
        import re
        if isinstance(value, str) and "${" in value:
            def replace_env(match):
                env_var = match.group(1)
                return os.environ.get(env_var, match.group(0))
            return re.sub(r'\$\{([^}]+)\}', replace_env, value)
        return value
    
    def _init_storage(self) -> None:
        """Initialize storage components."""
        storage_config = self.config.get("storage", {})
        
        # Append-only log
        log_path = storage_config.get("append_log", {}).get(
            "path", "data/logs/events.jsonl"
        )
        log_path = self._expand_env_vars(log_path)
        self.append_log = AppendOnlyLog(log_path)
        
        # DuckDB
        duckdb_path = storage_config.get("duckdb", {}).get(
            "path", "data/market_maker.duckdb"
        )
        duckdb_path = self._expand_env_vars(duckdb_path)
        self.duckdb = DuckDBStore(duckdb_path)
        
        # Redis
        redis_config = storage_config.get("redis", {})
        redis_host_raw = redis_config.get("host", "localhost")
        redis_host = self._expand_env_vars(redis_host_raw) if isinstance(redis_host_raw, str) else redis_host_raw
        redis_port = redis_config.get("port", 6379)
        redis_db = redis_config.get("db", 0)
        self.redis = RedisStateStore(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            socket_timeout=redis_config.get("socket_timeout", 5),
        )
        
        logger.info("storage_initialized")
    
    def _init_data_clients(self) -> None:
        """Initialize data and trading clients."""
        # Check if we're in simulation mode (no API needed)
        simulation_mode = os.environ.get("SIMULATION_MODE", "false").lower() == "true"
        
        if simulation_mode:
            # Use free data client (no personal info required)
            from src.data.ingestion.free_data_client import FreeDataClient
            
            # Get optional API keys from environment
            alpha_vantage_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
            finnhub_key = os.environ.get("FINNHUB_API_KEY")
            
            self.alpaca = FreeDataClient(
                alpha_vantage_key=alpha_vantage_key,
                finnhub_key=finnhub_key,
            )
            initial_equity = 100000.0
            self.redis.set_initial_equity(initial_equity)
            logger.info(
                "simulation_mode_initialized",
                initial_equity=initial_equity,
                has_alpha_vantage=bool(alpha_vantage_key),
                has_finnhub=bool(finnhub_key),
                message="Running in FULL SIMULATION MODE with free data sources!",
            )
        else:
            self.alpaca = AlpacaDataClient(paper=True)
            
            # Record initial equity (handle unauthorized errors gracefully)
            try:
                account = self.alpaca.get_account()
                initial_equity = float(account.equity)
                self.redis.set_initial_equity(initial_equity)
                
                logger.info(
                    "data_clients_initialized",
                    initial_equity=initial_equity,
                )
            except Exception as e:
                error_str = str(e).lower()
                if "unauthorized" in error_str or "401" in error_str:
                    # Use default equity if API keys are invalid
                    initial_equity = 100000.0
                    self.redis.set_initial_equity(initial_equity)
                    logger.warning(
                        "account_fetch_failed_using_default",
                        initial_equity=initial_equity,
                        error=str(e),
                        message="API keys invalid or account not set up. Using default equity. Bot will run in demo mode.",
                    )
                    # Don't raise - allow bot to continue in demo mode
                else:
                    logger.warning("account_fetch_failed", error=str(e))
                    raise
    
    def _init_strategies(self) -> None:
        """Initialize trading strategies."""
        strategy_config = self.config.get("strategies", {})
        
        # Tier 1 strategies
        tier1_config = strategy_config.get("tier1", {})
        
        self.strategies = []
        
        if tier1_config.get("ema_crossover", {}).get("enabled", True):
            ema_config = tier1_config["ema_crossover"]
            strategy = EMACrossoverStrategy(
                fast_period=ema_config.get("fast_period", 12),
                slow_period=ema_config.get("slow_period", 26),
                enabled=True,
            )
            self.strategies.append(strategy)
        
        if tier1_config.get("rsi_mean_reversion", {}).get("enabled", True):
            rsi_config = tier1_config["rsi_mean_reversion"]
            strategy = RSIMeanReversionStrategy(
                period=rsi_config.get("period", 14),
                oversold_threshold=rsi_config.get("oversold_threshold", 30.0),
                overbought_threshold=rsi_config.get("overbought_threshold", 70.0),
                enabled=True,
            )
            self.strategies.append(strategy)
        
        # Regime detector
        regime_config = self.config.get("regime", {})
        self.regime_detector = RegimeDetector(
            fast_window_days=regime_config.get("fast", {}).get("window_days", 3),
            slow_window_days=regime_config.get("slow", {}).get("window_days", 20),
            crisis_multiplier=regime_config.get("crisis_multiplier", 2.0),
        )
        
        logger.info("strategies_initialized", count=len(self.strategies))
    
    def _init_risk_management(self) -> None:
        """Initialize risk management components."""
        risk_config = self.config.get("risk", {})
        
        # Position sizer
        sizing_config = risk_config.get("position_sizing", {})
        self.position_sizer = PositionSizer(
            method=PositionSizingMethod(sizing_config.get("method", "volatility_adjusted")),
            max_position_pct=sizing_config.get("max_position_pct", 10.0),
            volatility_target_pct=sizing_config.get("volatility_target_pct", 15.0),
        )
        
        # Drawdown monitor
        drawdown_config = risk_config.get("drawdown", {})
        try:
            account = self.alpaca.get_account()
            initial_equity = float(account.equity)
        except Exception as e:
            error_str = str(e).lower()
            if "unauthorized" in error_str or "401" in error_str:
                initial_equity = 100000.0  # Default for demo mode
                logger.warning(
                    "using_default_equity_for_drawdown",
                    initial_equity=initial_equity,
                    reason="API keys invalid",
                )
            else:
                raise
        
        self.drawdown_monitor = DrawdownMonitor(
            max_daily_drawdown_pct=drawdown_config.get("max_daily_drawdown_pct", 3.0),
            max_total_drawdown_pct=drawdown_config.get("max_total_drawdown_pct", 10.0),
            initial_equity=initial_equity,
        )
        
        # Portfolio allocator
        self.portfolio_allocator = PortfolioAllocator(
            max_position_pct=risk_config.get("position_sizing", {}).get("max_position_pct", 10.0),
            max_sector_pct=risk_config.get("correlation", {}).get("max_sector_exposure_pct", 30.0),
        )
        
        logger.info("risk_management_initialized")
    
    def _init_execution(self) -> None:
        """Initialize execution components."""
        self.order_manager = OrderManager()
        
        self.order_reconciler = OrderReconciler(
            order_manager=self.order_manager,
            broker_client=self.alpaca,
            redis_state=self.redis,
            reconciliation_interval_seconds=self.config.get("execution", {}).get(
                "reconciliation", {}
            ).get("interval_seconds", 300),
        )
        
        # Paper broker for simulation
        if self.dry_run:
            self.broker = PaperBroker(initial_cash=100000.0)
        else:
            self.broker = self.alpaca
        
        logger.info("execution_initialized", dry_run=self.dry_run)
    
    def _init_monitoring(self) -> None:
        """Initialize monitoring components."""
        self.metrics_collector = MetricsCollector()
        self.alerter = Alerter()
        self.decay_detector = StrategyDecayDetector()
        
        logger.info("monitoring_initialized")
    
    def _init_etl(self) -> None:
        """Initialize ETL pipeline."""
        etl_config = self.config.get("etl", {})
        
        self.etl_pipeline = ETLPipeline(
            append_log=self.append_log,
            duckdb_store=self.duckdb,
            batch_interval_seconds=etl_config.get("batch_interval_seconds", 60),
            max_batch_size=etl_config.get("max_batch_size", 10000),
        )
        
        logger.info("etl_pipeline_initialized")
    
    def _init_shutdown_handler(self) -> None:
        """Initialize graceful shutdown handler."""
        self.shutdown_handler = create_shutdown_handler_for_bot(
            append_log=self.append_log,
            duckdb_store=self.duckdb,
            redis_state=self.redis,
            pid_file="/tmp/market_maker/bot.pid",
        )
        self.shutdown_handler.install()
        
        logger.info("shutdown_handler_installed")
    
    def run(self) -> None:
        """
        Main run loop.
        
        This is the heart of the trading bot.
        """
        logger.info("market_maker_starting")
        self.running = True
        
        # Log startup event
        self._log_event(EventType.HEARTBEAT, {"status": "startup"})
        
        try:
            while not self.shutdown_handler.should_shutdown():
                self._run_iteration()
                time.sleep(1)  # Main loop interval
                
        except Exception as e:
            logger.exception("main_loop_error", error=str(e))
            self._log_event(EventType.ERROR, {"error": str(e)})
            raise
        finally:
            self.running = False
            logger.info("market_maker_stopped")
    
    def _run_iteration(self) -> None:
        """
        Single iteration of the main loop.
        
        This is where the magic happens:
        1. Check market status
        2. Update data
        3. Run strategies
        4. Execute orders
        5. Send heartbeat
        """
        now = datetime.now()
        
        # Check if market is open (handle unauthorized errors gracefully)
        try:
            clock = self.alpaca.get_clock()
        except Exception as e:
            error_str = str(e).lower()
            if "unauthorized" in error_str or "401" in error_str:
                # Use mock clock if API keys are invalid
                class MockClock:
                    is_open = True
                    timestamp = now
                clock = MockClock()
                logger.debug("using_mock_clock", reason="API keys invalid")
            else:
                raise
        
        if not clock.is_open:
            # Market closed - reduced activity
            if (now - self.last_heartbeat).seconds > 60:
                self._send_heartbeat()
            return
        
        # Market is open - full activity
        try:
            # 1. Sync positions with broker (broker is TRUTH)
            self._sync_positions()
            
            # 2. Check for Friday force close
            self._check_friday_close()
            
            # 3. Run ETL (periodically)
            if (now - self.last_etl_run).seconds >= 60:
                self._run_etl()
                self.last_etl_run = now
            
            # 4. Reconcile orders (periodically)
            if (now - self.last_reconciliation).seconds >= 300:
                self._reconcile_orders()
                self.last_reconciliation = now
            
            # 5. Run strategies (if enabled)
            if self.config.get("strategies", {}).get("enabled", True):
                self._run_strategies()
            
            # 6. Update metrics
            self._update_metrics()
            
            # 7. Send heartbeat
            self._send_heartbeat()
            
        except Exception as e:
            logger.error("iteration_error", error=str(e))
            self._log_event(EventType.ERROR, {
                "phase": "iteration",
                "error": str(e),
            })
    
    def _sync_positions(self) -> None:
        """Sync positions with broker (broker is TRUTH)."""
        try:
            positions = self.alpaca.get_positions()
            
            # Convert to dict format for Redis
            position_data = [
                {
                    "symbol": p.symbol,
                    "qty": float(p.qty),
                    "avg_price": float(p.avg_entry_price),
                    "market_value": float(p.market_value),
                    "unrealized_pnl": float(p.unrealized_pl),
                    "side": "long" if float(p.qty) > 0 else "short",
                }
                for p in positions
            ]
            
            self.redis.sync_positions(position_data)
            
        except Exception as e:
            logger.error("position_sync_error", error=str(e))
    
    def _check_friday_close(self) -> None:
        """
        Check if it's time for Friday force close.
        
        Implements Gemini's "Time-Based Exit" recommendation:
        Close ALL positions at 3:55 PM EST every Friday.
        No weekend risk. Period.
        """
        now = datetime.now()
        
        # Check if Friday
        if now.weekday() != 4:  # 4 = Friday
            return
        
        # Check if past force close time (3:55 PM)
        force_close_time = now.replace(hour=15, minute=55, second=0, microsecond=0)
        
        if now >= force_close_time:
            positions = self.redis.get_all_positions()
            
            if positions:
                logger.warning(
                    "friday_force_close",
                    positions=len(positions),
                    message="Closing all positions for weekend",
                )
                
                if not self.dry_run:
                    self.alpaca.close_all_positions()
                    
                self._log_event(EventType.RISK_ALERT, {
                    "type": "friday_force_close",
                    "positions_closed": len(positions),
                })
    
    def _run_strategies(self) -> None:
        """
        Run trading strategies and execute signals.
        
        Process:
        1. Detect current regime
        2. Run all enabled strategies
        3. Collect signals
        4. Apply risk management
        5. Allocate portfolio
        6. Execute orders
        """
        if not self.strategies:
            return
        
        # Get current positions
        current_positions = self.redis.get_all_positions()
        
        # Get account for portfolio value
        try:
            account = self.alpaca.get_account()
            portfolio_value = float(account.equity)
        except Exception as e:
            logger.error("account_fetch_error", error=str(e))
            return
        
        # Check drawdown limits
        last_equity = self.redis.get_state("last_equity") or portfolio_value
        metrics = self.drawdown_monitor.update(portfolio_value, last_equity)
        
        # Store last equity for next iteration
        self.redis.set_state("last_equity", portfolio_value)
        
        if self.drawdown_monitor.should_halt_trading(metrics):
            logger.critical("trading_halted_due_to_drawdown", drawdown=metrics.total_drawdown_pct)
            self.alerter.send_critical(f"Trading halted: {metrics.total_drawdown_pct:.2f}% drawdown")
            return
        
        # Get position scale from drawdown
        position_scale = self.drawdown_monitor.get_position_scale(metrics)
        
        # Process each symbol in universe
        # For now, use a simple universe (would come from config)
        symbols = list(set(p["symbol"] for p in current_positions.values()))
        
        # If no positions, use default universe from config
        if not symbols:
            # Get universe from config or default
            universe_config = self.config.get("data", {}).get("tier0", {})
            if universe_config.get("enabled"):
                # Would use UniverseSelector here
                symbols = ["SPY"]  # Default for now
            else:
                symbols = ["SPY"]  # Default to SPY for simplicity
        
        all_signals = []
        
        for symbol in symbols:
            # Get historical bars for regime detection
            try:
                bars = self.duckdb.get_bars(
                    symbol=symbol,
                    start=datetime.now() - timedelta(days=60),
                    end=datetime.now(),
                    timeframe="1Day",
                )
                
                if bars.empty:
                    # Try fetching from Alpaca if DuckDB is empty
                    try:
                        alpaca_bars = self.alpaca.get_historical_bars(
                            symbol=symbol,
                            start=datetime.now() - timedelta(days=60),
                            end=datetime.now(),
                            timeframe="1Day",
                        )
                        
                        if alpaca_bars:
                            # Convert to DataFrame
                            import pandas as pd
                            bars = pd.DataFrame([
                                {
                                    "timestamp": b.timestamp,
                                    "open": b.open,
                                    "high": b.high,
                                    "low": b.low,
                                    "close": b.close,
                                    "volume": b.volume,
                                }
                                for b in alpaca_bars
                            ])
                    except Exception as e:
                        logger.warning("data_fetch_error", symbol=symbol, error=str(e))
                        continue
                
                if bars.empty:
                    continue
                
                # Detect regime
                current_regime = self.regime_detector.detect_regime(bars, symbol=symbol)
                
                # Store regime in DuckDB
                self.duckdb.insert_regime(current_regime.to_dict())
                
                # Get current position
                current_position = current_positions.get(symbol)
                
                # Run strategies
                for strategy in self.strategies:
                    if not strategy.should_generate_signals(current_regime):
                        continue
                    
                    try:
                        signals = strategy.generate_signals(
                            symbol=symbol,
                            bars=bars,
                            current_regime=current_regime,
                            current_position=current_position,
                        )
                        
                        all_signals.extend(signals)
                    except Exception as e:
                        logger.error("strategy_error", strategy=strategy.name, symbol=symbol, error=str(e))
            
            except Exception as e:
                logger.error("strategy_execution_error", symbol=symbol, error=str(e))
        
        # Process signals through risk management and execution
        if all_signals:
            self._process_signals(all_signals, portfolio_value, position_scale)
    
    def _process_signals(
        self,
        signals: list,
        portfolio_value: float,
        position_scale: float,
    ) -> None:
        """Process signals through risk management and execution."""
        for signal in signals:
            try:
                # Calculate position size
                # Get volatility for sizing (simplified - would fetch from bars)
                volatility = 0.15  # Default
                
                size_result = self.position_sizer.calculate_size(
                    portfolio_value=portfolio_value,
                    symbol=signal.symbol,
                    current_price=signal.entry_price or 100.0,
                    volatility=volatility,
                    regime_scale=position_scale,
                )
                
                # Apply max limit
                size_result = self.position_sizer.apply_max_limit(size_result, portfolio_value)
                
                # Create order
                if signal.signal_type.value == "buy":
                    if not signal.entry_price or signal.entry_price <= 0:
                        logger.warning("invalid_entry_price", signal_id=signal.signal_id)
                        continue
                    
                    qty = size_result.size_dollars / signal.entry_price
                    
                    if qty <= 0:
                        logger.warning("invalid_quantity", signal_id=signal.signal_id, qty=qty)
                        continue
                    
                    order = self.order_manager.create_order(
                        symbol=signal.symbol,
                        side="buy",
                        qty=qty,
                        order_type="limit",
                        limit_price=signal.entry_price,
                        strategy_name=signal.strategy_name,
                        signal_id=signal.signal_id,
                    )
                    
                    # Submit order
                    try:
                        if not self.dry_run:
                            if hasattr(self.broker, 'submit_limit_order'):
                                broker_order = self.broker.submit_limit_order(
                                    symbol=signal.symbol,
                                    qty=qty,
                                    side="buy",
                                    limit_price=signal.entry_price,
                                    client_order_id=order.client_order_id,
                                )
                                
                                self.order_manager.mark_submitted(
                                    order.client_order_id,
                                    str(broker_order.id) if hasattr(broker_order, 'id') else str(broker_order.get("order_id", "")),
                                )
                            else:
                                # Paper broker
                                result = self.broker.submit_order(
                                    symbol=signal.symbol,
                                    side="buy",
                                    qty=qty,
                                    order_type="limit",
                                    limit_price=signal.entry_price,
                                    current_price=signal.entry_price,
                                )
                                
                                if result.get("status") == "filled":
                                    self.order_manager.mark_filled(
                                        order.client_order_id,
                                        filled_qty=qty,
                                        filled_price=result.get("filled_price", signal.entry_price),
                                    )
                        else:
                            logger.info("dry_run_order", order=order.to_dict())
                        
                        self._log_event(EventType.ORDER_SUBMITTED, order.to_dict())
                    
                    except Exception as e:
                        logger.error("order_submission_error", order_id=order.client_order_id, error=str(e))
                        self.order_manager.mark_failed(order.client_order_id)
                
                elif signal.signal_type.value in ("sell", "close"):
                    # Close position
                    current_position = self.redis.get_position(signal.symbol)
                    if current_position:
                        qty = abs(current_position["qty"])
                        
                        if qty <= 0:
                            continue
                        
                        order = self.order_manager.create_order(
                            symbol=signal.symbol,
                            side="sell",
                            qty=qty,
                            order_type="market",
                            strategy_name=signal.strategy_name,
                            signal_id=signal.signal_id,
                        )
                        
                        try:
                            if not self.dry_run:
                                if hasattr(self.broker, 'submit_market_order'):
                                    broker_order = self.broker.submit_market_order(
                                        symbol=signal.symbol,
                                        qty=qty,
                                        side="sell",
                                        client_order_id=order.client_order_id,
                                    )
                                    
                                    self.order_manager.mark_submitted(
                                        order.client_order_id,
                                        str(broker_order.id) if hasattr(broker_order, 'id') else str(broker_order.get("order_id", "")),
                                    )
                                else:
                                    # Paper broker
                                    result = self.broker.submit_order(
                                        symbol=signal.symbol,
                                        side="sell",
                                        qty=qty,
                                        order_type="market",
                                        current_price=current_position.get("avg_price", 100.0),
                                    )
                                    
                                    if result.get("status") == "filled":
                                        self.order_manager.mark_filled(
                                            order.client_order_id,
                                            filled_qty=qty,
                                            filled_price=result.get("filled_price"),
                                        )
                            else:
                                logger.info("dry_run_order", order=order.to_dict())
                            
                            self._log_event(EventType.ORDER_SUBMITTED, order.to_dict())
                        
                        except Exception as e:
                            logger.error("order_submission_error", order_id=order.client_order_id, error=str(e))
                            self.order_manager.mark_failed(order.client_order_id)
            
            except Exception as e:
                logger.error("signal_processing_error", signal_id=signal.signal_id, error=str(e))
    
    def _run_etl(self) -> None:
        """Run ETL pipeline to process events."""
        try:
            summary = self.etl_pipeline.run_once()
            logger.debug("etl_run_complete", **summary)
        except Exception as e:
            logger.error("etl_run_error", error=str(e))
    
    def _reconcile_orders(self) -> None:
        """Reconcile orders with broker state."""
        try:
            summary = self.order_reconciler.reconcile_all()
            self.order_reconciler.reconcile_positions()
            logger.debug("reconciliation_complete", **summary)
        except Exception as e:
            logger.error("reconciliation_error", error=str(e))
    
    def _update_metrics(self) -> None:
        """Update performance metrics."""
        try:
            account = self.alpaca.get_account()
            equity = float(account.equity)
            cash = float(account.cash)
            positions = self.redis.get_all_positions()
            positions_value = sum(p.get("market_value", 0) for p in positions.values())
            
            # Get returns history (simplified - would fetch from DuckDB)
            returns_history = None  # Would be fetched from DuckDB
            
            metrics = self.metrics_collector.calculate_metrics(
                equity=equity,
                cash=cash,
                positions_value=positions_value,
                initial_equity=self.redis.get_initial_equity() or equity,
                returns_history=returns_history,
                num_positions=len(positions),
                num_open_orders=len(self.order_manager.get_open_orders()),
            )
            
            # Store metrics in DuckDB
            self.duckdb.insert_performance(metrics.to_dict())
            
            # Check for alerts
            if metrics.current_drawdown and abs(metrics.current_drawdown) > 0.05:
                self.alerter.send_warning(
                    f"Current drawdown: {metrics.current_drawdown:.2%}",
                    drawdown=metrics.current_drawdown,
                )
        
        except Exception as e:
            logger.error("metrics_update_error", error=str(e))
    
    def _send_heartbeat(self) -> None:
        """Send heartbeat to Redis (for watchdog monitoring)."""
        self.redis.send_heartbeat("main_bot", ttl_seconds=120)
        self.last_heartbeat = datetime.now()
        
        self._log_event(EventType.HEARTBEAT, {
            "timestamp": self.last_heartbeat.isoformat(),
        })
    
    def _log_event(self, event_type: EventType, data: dict) -> None:
        """Log an event to the append-only log."""
        event = Event(
            event_type=event_type,
            timestamp=datetime.now(),
            data=data,
            source="main_bot",
        )
        self.append_log.write(event)


def main():
    """Entry point for the Market Maker."""
    import argparse
    
    parser = argparse.ArgumentParser(description="The Market Maker")
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--dry-run", action="store_true")
    
    args = parser.parse_args()
    
    bot = MarketMaker(
        config_path=args.config,
        dry_run=args.dry_run,
    )
    bot.run()


if __name__ == "__main__":
    main()
