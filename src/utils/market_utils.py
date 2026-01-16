"""
Market utility functions.

Helper functions for market hours, timezone handling, etc.
"""

from datetime import datetime, time, timedelta
from typing import Optional
import pytz

# Market timezone
MARKET_TZ = pytz.timezone("America/New_York")

# Market hours
MARKET_OPEN = time(9, 30)  # 9:30 AM EST
MARKET_CLOSE = time(16, 0)  # 4:00 PM EST

# Friday force close time (Gemini's recommendation)
FRIDAY_FORCE_CLOSE = time(15, 55)  # 3:55 PM EST


def get_market_time(utc_time: Optional[datetime] = None) -> datetime:
    """
    Get current time in market timezone.
    
    Args:
        utc_time: UTC datetime (defaults to now)
    
    Returns:
        Datetime in market timezone
    """
    if utc_time is None:
        utc_time = datetime.now(pytz.UTC)
    
    if utc_time.tzinfo is None:
        utc_time = pytz.UTC.localize(utc_time)
    
    return utc_time.astimezone(MARKET_TZ)


def is_market_open(market_time: Optional[datetime] = None) -> bool:
    """
    Check if market is currently open.
    
    Args:
        market_time: Market time (defaults to current market time)
    
    Returns:
        True if market is open
    """
    if market_time is None:
        market_time = get_market_time()
    
    # Check if weekday (Monday=0, Friday=4)
    if market_time.weekday() >= 5:  # Saturday or Sunday
        return False
    
    # Check if within market hours
    market_time_only = market_time.time()
    return MARKET_OPEN <= market_time_only < MARKET_CLOSE


def is_friday_force_close_time(market_time: Optional[datetime] = None) -> bool:
    """
    Check if it's Friday force close time (3:55 PM EST).
    
    Implements Gemini's recommendation: close all positions before weekend.
    """
    if market_time is None:
        market_time = get_market_time()
    
    # Must be Friday
    if market_time.weekday() != 4:  # Friday
        return False
    
    # Must be past force close time
    market_time_only = market_time.time()
    return market_time_only >= FRIDAY_FORCE_CLOSE


def get_next_market_open(market_time: Optional[datetime] = None) -> datetime:
    """
    Get next market open time.
    
    Useful for scheduling tasks.
    """
    if market_time is None:
        market_time = get_market_time()
    
    # If market is open, next open is tomorrow
    if is_market_open(market_time):
        next_open = market_time.replace(
            hour=MARKET_OPEN.hour,
            minute=MARKET_OPEN.minute,
            second=0,
            microsecond=0,
        ) + timedelta(days=1)
    else:
        # Market is closed - next open is today or tomorrow
        next_open = market_time.replace(
            hour=MARKET_OPEN.hour,
            minute=MARKET_OPEN.minute,
            second=0,
            microsecond=0,
        )
        
        if next_open < market_time:
            next_open += timedelta(days=1)
    
    # Skip weekends
    while next_open.weekday() >= 5:
        next_open += timedelta(days=1)
    
    return next_open
