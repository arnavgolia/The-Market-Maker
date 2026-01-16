"""
Backtesting engine.

Runs strategies on historical data with realistic transaction costs.
All backtests MUST use walk-forward validation (no full-dataset backtests).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Callable
import structlog

import pandas as pd
import numpy as np

from src.strategy.base import Strategy, Signal
from src.data.cost_model.spread_estimator import SpreadEstimator
from src.data.cost_model.slippage_model import SlippageModel

logger = structlog.get_logger(__name__)


@dataclass
class BacktestResult:
    """Results from a backtest run."""
    # Returns
    total_return: float
    annualized_return: float
    daily_returns: pd.Series
    
    # Risk metrics
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    volatility: float
    
    # Trading metrics
    num_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    
    # Cost metrics
    total_transaction_costs: float
    avg_cost_per_trade: float
    cost_as_pct_of_return: float
    
    # Equity curve
    equity_curve: pd.Series
    
    # Strategy attribution
    strategy_name: str
    
    @property
    def final_equity(self) -> float:
        """Get final equity from equity curve."""
        if len(self.equity_curve) > 0:
            return float(self.equity_curve.iloc[-1])
        return 0.0


class BacktestEngine:
    """
    Backtesting engine with transaction cost modeling.
    
    Key principles:
    - Transaction costs ALWAYS applied
    - Realistic fill prices (spread + slippage)
    - Position sizing respected
    - Regime detection integrated
    """
    
    def __init__(
        self,
        initial_capital: float = 100000.0,
        spread_estimator: Optional[SpreadEstimator] = None,
        slippage_model: Optional[SlippageModel] = None,
    ):
        """
        Initialize backtest engine.
        
        Args:
            initial_capital: Starting capital
            spread_estimator: Spread estimator (defaults to standard)
            slippage_model: Slippage model (defaults to standard)
        """
        self.initial_capital = initial_capital
        self.spread_estimator = spread_estimator or SpreadEstimator()
        self.slippage_model = slippage_model or SlippageModel()
        
        logger.info(
            "backtest_engine_initialized",
            initial_capital=initial_capital,
        )
    
    def run(
        self,
        strategy: Strategy,
        bars: pd.DataFrame,
        regime_detector: Optional[Callable] = None,
    ) -> BacktestResult:
        """
        Run backtest on historical data.
        
        Args:
            strategy: Strategy to backtest
            bars: Historical bars (DataFrame with columns: timestamp, open, high, low, close, volume)
            regime_detector: Optional function to detect regime (takes bars, returns MarketRegime)
        
        Returns:
            BacktestResult with performance metrics
        """
        if bars.empty:
            raise ValueError("Cannot backtest on empty data")
        
        # Initialize state
        equity = self.initial_capital
        cash = self.initial_capital
        positions: dict[str, dict] = {}  # symbol -> {qty, avg_price}
        
        equity_curve = []
        trades = []
        transaction_costs = []
        
        # Process bars chronologically
        for i in range(len(bars)):
            current_bar = bars.iloc[i]
            current_bars = bars.iloc[:i+1]  # Historical data up to current point
            
            # Detect regime if detector provided
            current_regime = None
            if regime_detector:
                try:
                    current_regime = regime_detector(current_bars)
                except Exception as e:
                    logger.warning("regime_detection_error", error=str(e))
            
            # Get current position
            symbol = current_bar.get("symbol", "UNKNOWN")
            current_position = positions.get(symbol)
            
            # Generate signals
            signals = strategy.generate_signals(
                symbol=symbol,
                bars=current_bars,
                current_regime=current_regime,
                current_position=current_position,
            )
            
            # Execute signals
            for signal in signals:
                if signal.signal_type.value == "buy":
                    trade_result = self._execute_buy(
                        signal=signal,
                        current_price=current_bar["close"],
                        current_volume=current_bar.get("volume", 0),
                        cash=cash,
                        positions=positions,
                    )
                    
                    if trade_result:
                        cash -= trade_result["cost"]
                        transaction_costs.append(trade_result["transaction_cost"])
                        trades.append(trade_result)
                
                elif signal.signal_type.value in ("sell", "close"):
                    trade_result = self._execute_sell(
                        signal=signal,
                        current_price=current_bar["close"],
                        current_volume=current_bar.get("volume", 0),
                        positions=positions,
                    )
                    
                    if trade_result:
                        cash += trade_result["proceeds"]
                        transaction_costs.append(trade_result["transaction_cost"])
                        trades.append(trade_result)
            
            # Update equity (mark-to-market)
            positions_value = sum(
                pos["qty"] * current_bar["close"]
                for pos in positions.values()
            )
            equity = cash + positions_value
            
            equity_curve.append({
                "timestamp": current_bar.get("timestamp", i),
                "equity": equity,
                "cash": cash,
                "positions_value": positions_value,
            })
            
            # Store final equity for access
            self._last_equity = equity
        
        # Calculate metrics
        equity_df = pd.DataFrame(equity_curve)
        if equity_df.empty:
            # No equity data - return failure result
            return BacktestResult(
                total_return=-1.0,
                annualized_return=-1.0,
                daily_returns=pd.Series(),
                sharpe_ratio=-10.0,
                sortino_ratio=-10.0,
                max_drawdown=1.0,
                volatility=0.0,
                num_trades=0,
                win_rate=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                profit_factor=0.0,
                total_transaction_costs=0.0,
                avg_cost_per_trade=0.0,
                cost_as_pct_of_return=0.0,
                equity_curve=pd.Series(),
                strategy_name=strategy.name,
            )
        
        equity_series = equity_df.set_index("timestamp")["equity"]
        self._last_equity = float(equity_series.iloc[-1])
        
        returns = equity_series.pct_change().dropna()
        
        total_return = (equity_series.iloc[-1] / equity_series.iloc[0]) - 1 if len(equity_series) > 0 and equity_series.iloc[0] > 0 else 0.0
        
        # Annualized return
        days = (equity_df["timestamp"].iloc[-1] - equity_df["timestamp"].iloc[0]).days
        if days > 0:
            annualized_return = (1 + total_return) ** (252 / days) - 1
        else:
            annualized_return = 0.0
        
        # Risk metrics
        sharpe = self._calculate_sharpe(returns)
        sortino = self._calculate_sortino(returns)
        max_dd = self._calculate_max_drawdown(equity_series)
        volatility = returns.std() * np.sqrt(252) if len(returns) > 0 else 0.0
        
        # Trading metrics
        if trades:
            winning_trades = [t for t in trades if t.get("pnl", 0) > 0]
            losing_trades = [t for t in trades if t.get("pnl", 0) < 0]
            
            win_rate = len(winning_trades) / len(trades) if trades else 0.0
            avg_win = np.mean([t["pnl"] for t in winning_trades]) if winning_trades else 0.0
            avg_loss = np.mean([abs(t["pnl"]) for t in losing_trades]) if losing_trades else 0.0
            
            total_wins = sum(t["pnl"] for t in winning_trades)
            total_losses = abs(sum(t["pnl"] for t in losing_trades))
            profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        else:
            win_rate = 0.0
            avg_win = 0.0
            avg_loss = 0.0
            profit_factor = 0.0
        
        # Cost metrics
        total_costs = sum(transaction_costs)
        avg_cost = np.mean(transaction_costs) if transaction_costs else 0.0
        cost_pct = (total_costs / (equity_series.iloc[-1] - equity_series.iloc[0])) * 100 if equity_series.iloc[-1] > equity_series.iloc[0] else 0.0
        
        return BacktestResult(
            total_return=total_return,
            annualized_return=annualized_return,
            daily_returns=returns,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            volatility=volatility,
            num_trades=len(trades),
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            total_transaction_costs=total_costs,
            avg_cost_per_trade=avg_cost,
            cost_as_pct_of_return=cost_pct,
            equity_curve=equity_series,
            strategy_name=strategy.name,
        )
    
    @property
    def final_equity(self) -> float:
        """Get final equity from equity curve."""
        if hasattr(self, '_last_equity'):
            return self._last_equity
        return self.initial_capital
    
    def _execute_buy(
        self,
        signal: Signal,
        current_price: float,
        current_volume: float,
        cash: float,
        positions: dict,
    ) -> Optional[dict]:
        """Execute a buy signal."""
        # Calculate position size (simplified - use signal confidence)
        position_size_pct = signal.suggested_size_pct or (signal.confidence * 10.0)
        position_size_pct = min(position_size_pct, 10.0)  # Cap at 10%
        
        # Calculate quantity
        notional = cash * (position_size_pct / 100)
        quantity = notional / current_price
        
        if quantity <= 0 or notional > cash:
            return None
        
        # Calculate transaction costs
        volatility = 0.15  # Default - should be calculated from bars
        spread = self.spread_estimator.estimate_spread(
            price=current_price,
            volatility=volatility,
            volume=current_volume,
        )
        
        slippage = self.slippage_model.calculate_slippage(
            price=current_price,
            quantity=quantity,
            volume=current_volume,
            volatility=volatility,
            is_market_order=True,  # Assume market orders for simplicity
        )
        
        transaction_cost = spread + slippage
        fill_price = current_price + (spread / quantity) + (slippage / quantity)
        
        # Update position
        symbol = signal.symbol
        if symbol in positions:
            pos = positions[symbol]
            total_qty = pos["qty"] + quantity
            total_cost = pos["avg_price"] * pos["qty"] + fill_price * quantity
            pos["qty"] = total_qty
            pos["avg_price"] = total_cost / total_qty
        else:
            positions[symbol] = {
                "qty": quantity,
                "avg_price": fill_price,
            }
        
        return {
            "symbol": symbol,
            "side": "buy",
            "quantity": quantity,
            "price": fill_price,
            "cost": fill_price * quantity + transaction_cost,
            "transaction_cost": transaction_cost,
            "pnl": 0.0,  # Will be calculated on exit
        }
    
    def _execute_sell(
        self,
        signal: Signal,
        current_price: float,
        current_volume: float,
        positions: dict,
    ) -> Optional[dict]:
        """Execute a sell/close signal."""
        symbol = signal.symbol
        
        if symbol not in positions:
            return None
        
        pos = positions[symbol]
        quantity = pos["qty"]
        
        # Calculate transaction costs
        volatility = 0.15
        spread = self.spread_estimator.estimate_spread(
            price=current_price,
            volatility=volatility,
            volume=current_volume,
        )
        
        slippage = self.slippage_model.calculate_slippage(
            price=current_price,
            quantity=quantity,
            volume=current_volume,
            volatility=volatility,
            is_market_order=True,
        )
        
        transaction_cost = spread + slippage
        fill_price = current_price - (spread / quantity) - (slippage / quantity)
        
        # Calculate PnL
        proceeds = fill_price * quantity - transaction_cost
        cost_basis = pos["avg_price"] * quantity
        pnl = proceeds - cost_basis
        
        # Remove position
        del positions[symbol]
        
        return {
            "symbol": symbol,
            "side": "sell",
            "quantity": quantity,
            "price": fill_price,
            "proceeds": proceeds,
            "transaction_cost": transaction_cost,
            "pnl": pnl,
        }
    
    def _calculate_sharpe(self, returns: pd.Series, risk_free_rate: float = 0.0) -> float:
        """Calculate Sharpe ratio."""
        if len(returns) == 0 or returns.std() == 0:
            return 0.0
        
        excess_returns = returns.mean() - (risk_free_rate / 252)
        sharpe = (excess_returns / returns.std()) * np.sqrt(252)
        
        return float(sharpe)
    
    def _calculate_sortino(self, returns: pd.Series, risk_free_rate: float = 0.0) -> float:
        """Calculate Sortino ratio (downside deviation only)."""
        if len(returns) == 0:
            return 0.0
        
        excess_returns = returns.mean() - (risk_free_rate / 252)
        downside_returns = returns[returns < 0]
        
        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return float('inf') if excess_returns > 0 else 0.0
        
        downside_std = downside_returns.std()
        sortino = (excess_returns / downside_std) * np.sqrt(252)
        
        return float(sortino)
    
    def _calculate_max_drawdown(self, equity: pd.Series) -> float:
        """Calculate maximum drawdown."""
        if len(equity) == 0:
            return 0.0
        
        running_max = equity.expanding().max()
        drawdown = (equity - running_max) / running_max
        max_dd = abs(drawdown.min())
        
        return float(max_dd)
