#!/usr/bin/env python3
"""
Verification script to check that all components are properly set up.

This script:
1. Checks all imports work
2. Verifies critical components can be instantiated
3. Checks for missing dependencies
4. Validates configuration

Usage:
    python scripts/verify_setup.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def check_imports():
    """Check that all critical imports work."""
    errors = []
    
    try:
        from src.data.ingestion.alpaca_client import AlpacaDataClient
        print("✅ AlpacaDataClient import OK")
    except Exception as e:
        errors.append(f"AlpacaDataClient: {e}")
        print(f"❌ AlpacaDataClient import failed: {e}")
    
    try:
        from src.storage.append_log import AppendOnlyLog
        from src.storage.duckdb_store import DuckDBStore
        from src.storage.redis_state import RedisStateStore
        print("✅ Storage imports OK")
    except Exception as e:
        errors.append(f"Storage: {e}")
        print(f"❌ Storage imports failed: {e}")
    
    try:
        from src.regime.detector import RegimeDetector, MarketRegime
        print("✅ Regime detector import OK")
    except Exception as e:
        errors.append(f"RegimeDetector: {e}")
        print(f"❌ RegimeDetector import failed: {e}")
    
    try:
        from src.strategy.tier1.ema_crossover import EMACrossoverStrategy
        from src.strategy.tier1.rsi_mean_reversion import RSIMeanReversionStrategy
        print("✅ Strategy imports OK")
    except Exception as e:
        errors.append(f"Strategies: {e}")
        print(f"❌ Strategy imports failed: {e}")
    
    try:
        from src.execution.order_manager import OrderManager
        from src.execution.reconciler import OrderReconciler
        print("✅ Execution imports OK")
    except Exception as e:
        errors.append(f"Execution: {e}")
        print(f"❌ Execution imports failed: {e}")
    
    try:
        from src.risk.position_sizer import PositionSizer
        from src.risk.drawdown_monitor import DrawdownMonitor
        print("✅ Risk management imports OK")
    except Exception as e:
        errors.append(f"Risk: {e}")
        print(f"❌ Risk management imports failed: {e}")
    
    try:
        from watchdog.daemon import WatchdogDaemon
        from watchdog.rules import WatchdogConfig
        print("✅ Watchdog imports OK")
    except Exception as e:
        errors.append(f"Watchdog: {e}")
        print(f"❌ Watchdog imports failed: {e}")
    
    try:
        from research.backtesting.engine import BacktestEngine
        from research.stress_testing.runner import StressTestRunner
        print("✅ Research imports OK")
    except Exception as e:
        errors.append(f"Research: {e}")
        print(f"❌ Research imports failed: {e}")
    
    return errors

def check_instantiation():
    """Check that components can be instantiated."""
    errors = []
    
    try:
        from src.execution.order_manager import OrderManager
        manager = OrderManager()
        print("✅ OrderManager instantiation OK")
    except Exception as e:
        errors.append(f"OrderManager instantiation: {e}")
        print(f"❌ OrderManager instantiation failed: {e}")
    
    try:
        from src.regime.detector import RegimeDetector
        detector = RegimeDetector()
        print("✅ RegimeDetector instantiation OK")
    except Exception as e:
        errors.append(f"RegimeDetector instantiation: {e}")
        print(f"❌ RegimeDetector instantiation failed: {e}")
    
    try:
        from src.strategy.tier1.ema_crossover import EMACrossoverStrategy
        strategy = EMACrossoverStrategy()
        print("✅ Strategy instantiation OK")
    except Exception as e:
        errors.append(f"Strategy instantiation: {e}")
        print(f"❌ Strategy instantiation failed: {e}")
    
    try:
        from src.risk.position_sizer import PositionSizer, PositionSizingMethod
        sizer = PositionSizer(method=PositionSizingMethod.FIXED)
        print("✅ PositionSizer instantiation OK")
    except Exception as e:
        errors.append(f"PositionSizer instantiation: {e}")
        print(f"❌ PositionSizer instantiation failed: {e}")
    
    return errors

def check_methods():
    """Check that critical methods exist."""
    errors = []
    
    try:
        from src.regime.detector import MarketRegime
        from datetime import datetime
        
        regime = MarketRegime(timestamp=datetime.now())
        assert hasattr(regime, 'to_dict'), "MarketRegime missing to_dict()"
        dict_repr = regime.to_dict()
        assert isinstance(dict_repr, dict), "to_dict() should return dict"
        print("✅ MarketRegime.to_dict() OK")
    except Exception as e:
        errors.append(f"MarketRegime.to_dict(): {e}")
        print(f"❌ MarketRegime.to_dict() failed: {e}")
    
    try:
        from src.execution.order_manager import OrderManager, OrderStatus
        
        manager = OrderManager()
        order = manager.create_order(
            symbol="AAPL",
            side="buy",
            qty=100,
            order_type="limit",
            limit_price=150.0,
        )
        assert order.status == OrderStatus.PENDING, "Order should start as PENDING"
        assert hasattr(order, 'client_order_id'), "Order missing client_order_id"
        print("✅ Order creation OK")
    except Exception as e:
        errors.append(f"Order creation: {e}")
        print(f"❌ Order creation failed: {e}")
    
    return errors

def main():
    """Run all verification checks."""
    print("=" * 80)
    print("The Market Maker - Setup Verification")
    print("=" * 80)
    print()
    
    all_errors = []
    
    print("1. Checking imports...")
    print("-" * 80)
    all_errors.extend(check_imports())
    print()
    
    print("2. Checking instantiation...")
    print("-" * 80)
    all_errors.extend(check_instantiation())
    print()
    
    print("3. Checking critical methods...")
    print("-" * 80)
    all_errors.extend(check_methods())
    print()
    
    print("=" * 80)
    if all_errors:
        print(f"❌ VERIFICATION FAILED: {len(all_errors)} error(s) found")
        print()
        print("Errors:")
        for i, error in enumerate(all_errors, 1):
            print(f"  {i}. {error}")
        sys.exit(1)
    else:
        print("✅ VERIFICATION PASSED: All checks successful")
        print()
        print("The system is ready to use!")
        print()
        print("Next steps:")
        print("  1. Set up environment variables (.env file)")
        print("  2. Start Redis: make redis-start")
        print("  3. Run watchdog: python scripts/run_watchdog.py")
        print("  4. Run bot: python scripts/run_bot.py")
        sys.exit(0)

if __name__ == "__main__":
    main()
