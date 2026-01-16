"""
Independent Watchdog Process.

CRITICAL: This is a SEPARATE process from the main trading bot.
It has its own:
- Python interpreter
- Configuration file
- API credentials
- No shared memory with main bot

The watchdog monitors the trading bot and can:
- Kill the bot if rules are breached
- Liquidate all positions in emergency
- Send alerts
- Prevent restart without human intervention

This architecture prevents the "Knight Capital" failure mode where
a kill switch inside the failing process cannot execute.
"""

from watchdog.daemon import WatchdogDaemon
from watchdog.rules import KillRules

__all__ = ["WatchdogDaemon", "KillRules"]
