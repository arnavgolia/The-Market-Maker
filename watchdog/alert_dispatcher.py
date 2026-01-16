"""
Alert dispatcher for the watchdog.

Sends alerts through configured channels when issues are detected.
Supports multiple channels: log, Slack, email, SMS.
"""

import os
import json
from datetime import datetime
from typing import Optional
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertDispatcher:
    """
    Dispatches alerts to configured channels.
    
    In production, this would integrate with:
    - Slack webhooks
    - Email (SMTP)
    - SMS (Twilio)
    - PagerDuty
    """
    
    def __init__(
        self,
        slack_webhook_url: Optional[str] = None,
        email_config: Optional[dict] = None,
    ):
        """
        Initialize alert dispatcher.
        
        Args:
            slack_webhook_url: Slack webhook URL for alerts
            email_config: Email configuration dict
        """
        self.slack_webhook_url = slack_webhook_url or os.environ.get("SLACK_WEBHOOK_URL")
        self.email_config = email_config
        
        # Track sent alerts for deduplication
        self.sent_alerts: dict[str, datetime] = {}
        self.dedup_window_seconds = 300  # 5 minutes
        
        logger.info(
            "alert_dispatcher_initialized",
            has_slack=bool(self.slack_webhook_url),
            has_email=bool(self.email_config),
        )
    
    def send_debug(self, message: str, **context) -> None:
        """Send debug alert (logged only)."""
        self._dispatch(AlertSeverity.DEBUG, message, context)
    
    def send_info(self, message: str, **context) -> None:
        """Send informational alert."""
        self._dispatch(AlertSeverity.INFO, message, context)
    
    def send_warning(self, message: str, **context) -> None:
        """Send warning alert."""
        self._dispatch(AlertSeverity.WARNING, message, context)
    
    def send_critical(self, message: str, **context) -> None:
        """
        Send critical alert.
        
        Critical alerts are NEVER deduplicated - they always send.
        """
        self._dispatch(AlertSeverity.CRITICAL, message, context, force=True)
    
    def _dispatch(
        self,
        severity: AlertSeverity,
        message: str,
        context: dict,
        force: bool = False,
    ) -> None:
        """
        Dispatch alert to all configured channels.
        
        Args:
            severity: Alert severity
            message: Alert message
            context: Additional context
            force: If True, bypass deduplication
        """
        # Check deduplication (except for forced/critical alerts)
        if not force and not self._should_send(message, severity):
            logger.debug("alert_deduplicated", message=message[:50])
            return
        
        # Always log
        log_method = {
            AlertSeverity.DEBUG: logger.debug,
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.CRITICAL: logger.critical,
        }.get(severity, logger.info)
        
        log_method(
            "alert_dispatched",
            severity=severity.value,
            message=message,
            **context,
        )
        
        # Send to Slack if configured
        if self.slack_webhook_url and severity in (AlertSeverity.WARNING, AlertSeverity.CRITICAL):
            self._send_slack(severity, message, context)
        
        # Send email if configured (critical only)
        if self.email_config and severity == AlertSeverity.CRITICAL:
            self._send_email(severity, message, context)
        
        # Record for deduplication
        self.sent_alerts[message] = datetime.now()
    
    def _should_send(self, message: str, severity: AlertSeverity) -> bool:
        """
        Check if alert should be sent (deduplication).
        
        Critical alerts always send.
        Other alerts are deduplicated within a time window.
        """
        if severity == AlertSeverity.CRITICAL:
            return True
        
        last_sent = self.sent_alerts.get(message)
        if last_sent is None:
            return True
        
        elapsed = (datetime.now() - last_sent).total_seconds()
        return elapsed > self.dedup_window_seconds
    
    def _send_slack(self, severity: AlertSeverity, message: str, context: dict) -> None:
        """Send alert to Slack webhook."""
        try:
            import httpx
            
            # Format message
            emoji = {
                AlertSeverity.WARNING: ":warning:",
                AlertSeverity.CRITICAL: ":rotating_light:",
            }.get(severity, ":information_source:")
            
            slack_message = {
                "text": f"{emoji} *Market Maker Alert*",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{emoji} {severity.value.upper()}: Market Maker Alert",
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": message,
                        },
                    },
                ],
            }
            
            if context:
                context_text = "\n".join(f"• *{k}*: {v}" for k, v in context.items())
                slack_message["blocks"].append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Context:*\n{context_text}",
                    },
                })
            
            response = httpx.post(
                self.slack_webhook_url,
                json=slack_message,
                timeout=10,
            )
            response.raise_for_status()
            
            logger.debug("slack_alert_sent")
            
        except Exception as e:
            logger.error("slack_alert_failed", error=str(e))
    
    def _send_email(self, severity: AlertSeverity, message: str, context: dict) -> None:
        """Send alert via email."""
        # Placeholder for email implementation
        # In production, use smtplib or a service like SendGrid
        logger.debug(
            "email_alert_would_send",
            severity=severity.value,
            message=message[:100],
        )
    
    def cleanup_old_alerts(self) -> None:
        """Remove old alerts from deduplication cache."""
        now = datetime.now()
        cutoff_seconds = self.dedup_window_seconds * 2
        
        self.sent_alerts = {
            msg: ts
            for msg, ts in self.sent_alerts.items()
            if (now - ts).total_seconds() < cutoff_seconds
        }
