"""
Backtesting framework with walk-forward validation.

Key principles:
- NO full-dataset backtests (guaranteed overfitting)
- Non-overlapping train/test folds
- Transaction costs always applied
- Regime-segmented evaluation
"""
