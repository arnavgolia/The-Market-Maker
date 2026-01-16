"""
Exponential decay model for sentiment.

Sentiment signals decay over time. This models the decay function:
Signal(t) = Signal(0) × exp(-λt) × regime_multiplier

Typical half-lives:
- Twitter: 2-6 hours
- Reddit: 6-24 hours
"""

from datetime import datetime, timedelta
from typing import Optional
import structlog

import numpy as np

logger = structlog.get_logger(__name__)


class ExponentialDecayModel:
    """
    Exponential decay model for sentiment signals.
    
    Models how sentiment signal strength decays over time.
    """
    
    def __init__(
        self,
        half_life_hours: float = 4.0,
        source: str = "reddit",
    ):
        """
        Initialize decay model.
        
        Args:
            half_life_hours: Half-life of sentiment signal in hours
            source: Source of sentiment (reddit, twitter)
        """
        self.half_life = half_life_hours
        self.source = source
        
        # Calculate decay rate from half-life
        # Signal(t) = Signal(0) * exp(-λt)
        # At t = half_life, Signal = Signal(0) / 2
        # exp(-λ * half_life) = 0.5
        # λ = ln(2) / half_life
        self.decay_rate = np.log(2) / half_life_hours
        
        logger.info(
            "decay_model_initialized",
            half_life_hours=half_life_hours,
            source=source,
            decay_rate=self.decay_rate,
        )
    
    def apply_decay(
        self,
        signal_strength: float,
        age_hours: float,
        regime_multiplier: float = 1.0,
    ) -> float:
        """
        Apply decay to a sentiment signal.
        
        Args:
            signal_strength: Original signal strength (0 to 1)
            age_hours: Age of signal in hours
            regime_multiplier: Regime-based multiplier (high vol = faster decay)
        
        Returns:
            Decayed signal strength
        """
        # Exponential decay
        decay_factor = np.exp(-self.decay_rate * age_hours * regime_multiplier)
        
        decayed_signal = signal_strength * decay_factor
        
        return float(decayed_signal)
    
    def get_decay_factor(
        self,
        age_hours: float,
        regime_multiplier: float = 1.0,
    ) -> float:
        """
        Get decay factor for a given age.
        
        Returns:
            Decay factor (0 to 1)
        """
        return float(np.exp(-self.decay_rate * age_hours * regime_multiplier))
    
    def get_age_for_decay(
        self,
        target_decay_factor: float,
    ) -> float:
        """
        Calculate age at which signal decays to target factor.
        
        Useful for determining when to stop using old sentiment.
        """
        if target_decay_factor <= 0:
            return float('inf')
        
        age_hours = -np.log(target_decay_factor) / self.decay_rate
        return float(age_hours)
    
    @classmethod
    def from_source(cls, source: str) -> "ExponentialDecayModel":
        """
        Create decay model with source-specific defaults.
        
        Args:
            source: "reddit" or "twitter"
        """
        defaults = {
            "reddit": 6.0,   # 6 hour half-life
            "twitter": 3.0,  # 3 hour half-life
        }
        
        half_life = defaults.get(source.lower(), 4.0)
        
        return cls(
            half_life_hours=half_life,
            source=source,
        )
