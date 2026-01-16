"""
Monitoring and alerting module.

Handles:
- Performance metrics (Sharpe, Sortino, drawdown)
- Strategy decay detection
- Alert deduplication (prevent fatigue)
- Real-time monitoring
"""

from src.monitoring.metrics import MetricsCollector
from src.monitoring.alerter import Alerter
from src.monitoring.decay_detector import StrategyDecayDetector

__all__ = ["MetricsCollector", "Alerter", "StrategyDecayDetector"]
