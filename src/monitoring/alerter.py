"""
Alerting system with deduplication.

Prevents alert fatigue by deduplicating similar alerts.
Critical alerts are never suppressed.
"""

from datetime import datetime, timedelta
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


class AlertSeverity:
    """Alert severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Alerter:
    """
    Alert dispatcher with deduplication.
    
    Implements Gemini's recommendation to prevent alert fatigue.
    Same alert within 5 minutes = suppress (except critical).
    """
    
    def __init__(
        self,
        deduplication_window_seconds: int = 300,  # 5 minutes
        max_alerts_per_hour: int = 10,
    ):
        """
        Initialize alerter.
        
        Args:
            deduplication_window_seconds: Window for deduplication
            max_alerts_per_hour: Max same alert per hour before suppression
        """
        self.dedup_window = deduplication_window_seconds
        self.max_per_hour = max_alerts_per_hour
        
        # Track sent alerts
        self.sent_alerts: dict[str, list[datetime]] = {}
        
        logger.info(
            "alerter_initialized",
            dedup_window=deduplication_window_seconds,
            max_per_hour=max_alerts_per_hour,
        )
    
    def send_alert(
        self,
        severity: str,
        message: str,
        **context,
    ) -> None:
        """
        Send an alert.
        
        Args:
            severity: Alert severity (debug, info, warning, critical)
            message: Alert message
            context: Additional context data
        """
        # Check deduplication (except for critical)
        if severity != AlertSeverity.CRITICAL:
            if not self._should_send(message, severity):
                logger.debug("alert_deduplicated", message=message[:50])
                return
        
        # Log alert
        log_method = {
            AlertSeverity.DEBUG: logger.debug,
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.CRITICAL: logger.critical,
        }.get(severity, logger.info)
        
        log_method(
            "alert_sent",
            severity=severity,
            message=message,
            **context,
        )
        
        # Record for deduplication
        self._record_alert(message)
    
    def _should_send(self, message: str, severity: str) -> bool:
        """
        Check if alert should be sent (deduplication logic).
        
        Critical alerts always send.
        Other alerts are deduplicated within time window.
        """
        if severity == AlertSeverity.CRITICAL:
            return True
        
        alert_times = self.sent_alerts.get(message, [])
        
        # Remove old alerts
        cutoff = datetime.now() - timedelta(seconds=self.dedup_window)
        alert_times = [t for t in alert_times if t > cutoff]
        
        # Check if too many in last hour
        hour_ago = datetime.now() - timedelta(hours=1)
        recent_count = sum(1 for t in alert_times if t > hour_ago)
        
        if recent_count >= self.max_per_hour:
            return False  # Suppress
        
        return True
    
    def _record_alert(self, message: str) -> None:
        """Record alert for deduplication."""
        if message not in self.sent_alerts:
            self.sent_alerts[message] = []
        
        self.sent_alerts[message].append(datetime.now())
        
        # Cleanup old entries
        cutoff = datetime.now() - timedelta(hours=2)
        self.sent_alerts[message] = [
            t for t in self.sent_alerts[message]
            if t > cutoff
        ]
    
    def send_critical(self, message: str, **context) -> None:
        """Send critical alert (never suppressed)."""
        self.send_alert(AlertSeverity.CRITICAL, message, **context)
    
    def send_warning(self, message: str, **context) -> None:
        """Send warning alert."""
        self.send_alert(AlertSeverity.WARNING, message, **context)
    
    def send_info(self, message: str, **context) -> None:
        """Send info alert."""
        self.send_alert(AlertSeverity.INFO, message, **context)
