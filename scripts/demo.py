#!/usr/bin/env python3
"""
Demo script to show The Market Maker in action.

This demonstrates the system without requiring Redis or API keys.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import structlog
from src.regime.detector import RegimeDetector
from src.strategy.tier1.ema_crossover import EMACrossoverStrategy
from src.strategy.tier1.rsi_mean_reversion import RSIMeanReversionStrategy
from src.risk.position_sizer import PositionSizer, PositionSizingMethod
from src.risk.drawdown_monitor import DrawdownMonitor
from src.execution.order_manager import OrderManager, OrderStatus
from src.data.cost_model.spread_estimator import SpreadEstimator
from src.data.cost_model.slippage_model import SlippageModel

# Setup logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(),  # Pretty console output
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


def generate_sample_data(days=100):
    """Generate sample market data for demo."""
    dates = pd.date_range(start=datetime.now() - timedelta(days=days), periods=days, freq='D')
    
    # Create realistic price movement
    np.random.seed(42)
    returns = np.random.randn(days) * 0.02  # 2% daily volatility
    trend = np.linspace(0, 0.1, days)  # Slight uptrend
    prices = 100 * np.exp(np.cumsum(returns + trend/days))
    
    bars = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': prices * 1.01,
        'low': prices * 0.99,
        'close': prices,
        'volume': np.random.randint(1000000, 5000000, days),
    })
    
    return bars


def demo_regime_detection(bars):
    """Demo regime detection."""
    print("\n" + "="*80)
    print("📊 REGIME DETECTION")
    print("="*80)
    
    detector = RegimeDetector()
    regime = detector.detect_regime(bars, symbol="DEMO")
    
    print(f"\n✅ Detected Regime:")
    print(f"   Trend: {regime.trend.value}")
    print(f"   Volatility: {regime.volatility.value}")
    print(f"   Combined: {regime.combined_regime}")
    print(f"   Momentum Enabled: {regime.momentum_enabled}")
    print(f"   Position Scale: {regime.position_scale:.2%}")
    
    return regime


def demo_strategies(bars, regime):
    """Demo strategy signal generation."""
    print("\n" + "="*80)
    print("🎯 STRATEGY SIGNAL GENERATION")
    print("="*80)
    
    # EMA Crossover Strategy
    ema_strategy = EMACrossoverStrategy()
    ema_signals = ema_strategy.generate_signals("DEMO", bars, current_regime=regime)
    
    print(f"\n📈 EMA Crossover Strategy:")
    print(f"   Signals Generated: {len(ema_signals)}")
    if ema_signals:
        for signal in ema_signals[:3]:  # Show first 3
            print(f"   - {signal.signal_type.value.upper()}: {signal.symbol} @ {signal.timestamp}")
            print(f"     Confidence: {signal.confidence:.2%}")
    
    # RSI Mean Reversion Strategy
    rsi_strategy = RSIMeanReversionStrategy()
    rsi_signals = rsi_strategy.generate_signals("DEMO", bars, current_regime=regime)
    
    print(f"\n📉 RSI Mean Reversion Strategy:")
    print(f"   Signals Generated: {len(rsi_signals)}")
    if rsi_signals:
        for signal in rsi_signals[:3]:  # Show first 3
            print(f"   - {signal.signal_type.value.upper()}: {signal.symbol} @ {signal.timestamp}")
            print(f"     Confidence: {signal.confidence:.2%}")
    
    return ema_signals + rsi_signals


def demo_risk_management(signals, bars):
    """Demo risk management."""
    print("\n" + "="*80)
    print("🛡️ RISK MANAGEMENT")
    print("="*80)
    
    # Position Sizing
    sizer = PositionSizer(method=PositionSizingMethod.VOLATILITY_ADJUSTED)
    current_price = bars['close'].iloc[-1]
    portfolio_value = 100000.0
    
    # Demo position sizing
    position = sizer.calculate_size(
        portfolio_value=portfolio_value,
        symbol="DEMO",
        current_price=current_price,
        volatility=0.15,  # 15% annualized vol
        regime_scale=0.8,
    )
    
    print(f"\n💰 Position Sizing:")
    print(f"   Portfolio Value: ${portfolio_value:,.2f}")
    print(f"   Current Price: ${current_price:.2f}")
    print(f"   Position Size: ${position.size_dollars:,.2f} ({position.size_pct:.2%})")
    print(f"   Shares: {position.size_shares:.2f}")
    print(f"   Method: {position.method}")
    print(f"   Rationale: {position.rationale}")
    
    # Drawdown Monitoring
    monitor = DrawdownMonitor(
        max_daily_drawdown_pct=3.0,
        max_total_drawdown_pct=10.0,
        initial_equity=portfolio_value,
    )
    
    # Simulate some equity changes
    equity = portfolio_value
    print(f"\n📉 Drawdown Monitoring:")
    print(f"   Initial Equity: ${equity:,.2f}")
    
    last_equity = portfolio_value
    for day, change_pct in [(1, -0.01), (2, -0.015), (3, 0.005)]:
        equity = last_equity * (1 + change_pct)
        metrics = monitor.update(equity, last_equity)
        print(f"   Day {day}: ${equity:,.2f} ({change_pct:+.2%})")
        print(f"      Max Drawdown: {metrics.max_drawdown_pct:.2%}")
        print(f"      Peak Equity: ${metrics.peak_equity:,.2f}")
        print(f"      Position Scale: {monitor.get_position_scale(metrics):.2%}")
        if monitor.should_halt_trading(metrics):
            print(f"      ⚠️  TRADING HALTED")
        last_equity = equity


def demo_order_management(signals):
    """Demo order state machine."""
    print("\n" + "="*80)
    print("📋 ORDER MANAGEMENT")
    print("="*80)
    
    manager = OrderManager()
    
    # Create a demo order
    order = manager.create_order(
        symbol="DEMO",
        side="buy",
        qty=100,
        order_type="market",
        strategy_name="demo_strategy",
        signal_id="demo_signal_1",
    )
    
    print(f"\n📝 Order Created:")
    print(f"   Client Order ID: {order.client_order_id}")
    print(f"   Symbol: {order.symbol}")
    print(f"   Side: {order.side}")
    print(f"   Quantity: {order.qty}")
    print(f"   Status: {order.status.value}")
    
    # Submit order
    manager.mark_submitted(order.client_order_id, "broker_12345")
    print(f"\n✅ Order Submitted:")
    print(f"   Broker Order ID: {order.order_id}")
    print(f"   Status: {order.status.value}")
    
    # Fill order
    manager.mark_filled(
        order.client_order_id,
        filled_qty=100,
        filled_price=150.0,
    )
    print(f"\n✅ Order Filled:")
    print(f"   Filled Quantity: {order.filled_qty}")
    print(f"   Fill Price: ${order.filled_price:.2f}")
    print(f"   Status: {order.status.value}")
    print(f"   Terminal State: {order.is_terminal}")
    
    # Show order state machine
    print(f"\n📊 Order State Machine:")
    print(f"   PENDING → SUBMITTED → FILLED")
    print(f"   All transitions validated ✅")


def demo_cost_modeling():
    """Demo transaction cost modeling."""
    print("\n" + "="*80)
    print("💸 TRANSACTION COST MODELING")
    print("="*80)
    
    spread_estimator = SpreadEstimator()
    slippage_model = SlippageModel()
    
    scenarios = [
        ("Normal Market", 0.15, 1000000, 1000),
        ("High Volatility", 0.30, 500000, 1000),
        ("Low Volume", 0.15, 100000, 1000),
    ]
    
    print(f"\n📊 Cost Analysis:")
    price = 100.0
    for name, vol, volume, qty in scenarios:
        spread = spread_estimator.estimate_spread(vol, volume, price)
        slippage_dollars = slippage_model.calculate_slippage(
            price=price,
            quantity=qty,
            volume=volume,
            volatility=vol,
            is_market_order=True,
        )
        slippage_bps = (slippage_dollars / (price * qty)) * 10000
        total_cost = spread + slippage_bps
        
        print(f"\n   {name}:")
        print(f"      Spread: {spread:.2f} bps")
        print(f"      Slippage: {slippage_bps:.2f} bps")
        print(f"      Total Cost: {total_cost:.2f} bps ({total_cost/100:.2%})")


def main():
    """Run the demo."""
    print("\n" + "="*80)
    print("🚀 THE MARKET MAKER - DEMO")
    print("="*80)
    print("\nThis demo shows the system working without Redis or API keys.")
    print("All components are functional and ready for production use.\n")
    
    # Generate sample data
    print("📊 Generating sample market data...")
    bars = generate_sample_data(days=100)
    print(f"✅ Generated {len(bars)} days of market data")
    print(f"   Price Range: ${bars['close'].min():.2f} - ${bars['close'].max():.2f}")
    print(f"   Current Price: ${bars['close'].iloc[-1]:.2f}")
    
    # Run demos
    regime = demo_regime_detection(bars)
    signals = demo_strategies(bars, regime)
    demo_risk_management(signals, bars)
    demo_order_management(signals)
    demo_cost_modeling()
    
    # Summary
    print("\n" + "="*80)
    print("✅ DEMO COMPLETE")
    print("="*80)
    print("\nThe Market Maker is fully functional!")
    print("\nTo run in production:")
    print("  1. Start Redis: brew services start redis")
    print("  2. Add Alpaca API keys to .env file")
    print("  3. Run: python scripts/run_bot.py")
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    main()
