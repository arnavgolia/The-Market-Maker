"""
Lead-lag calibration with Bonferroni correction and two-stage validation.

CRITICAL: This fixes the multiple testing trap identified by Gemini.
Testing 49 lag values and picking the best guarantees finding noise.

Solution: Two-stage A/B validation
- Stage 1: Discover optimal lag on subset A
- Stage 2: Validate ONLY that lag on holdout subset B
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import structlog

import numpy as np
from scipy import stats

logger = structlog.get_logger(__name__)


class SentimentMode(Enum):
    """How to use sentiment based on calibration."""
    DISABLED = "disabled"      # No validated edge - don't use
    CONFIRMING = "confirming"  # Positive sentiment → bullish filter
    CONTRARIAN = "contrarian"  # Positive sentiment → bearish filter (crowded)


@dataclass
class LeadLagResult:
    """
    Result of lead-lag calibration.
    
    CRITICAL: Only use sentiment if validation_passed is True.
    """
    optimal_lag_hours: int
    correlation: float
    p_value: float
    is_significant: bool
    is_leading: bool
    
    # Validation results (THE CRITICAL FIELDS)
    validation_correlation: Optional[float] = None
    validation_p_value: Optional[float] = None
    validation_passed: bool = False
    
    # Calibration metadata
    discovery_correlation: Optional[float] = None
    discovery_p_value: Optional[float] = None


class SentimentCalibrator:
    """
    Statistically rigorous lead-lag calibration.
    
    Uses two-stage validation to eliminate the multiple testing problem:
    1. Discovery phase: Find candidate lag on data subset A
    2. Validation phase: Test ONLY that lag on holdout subset B
    
    This is the ONLY statistically valid approach when searching
    over multiple hypotheses (lag values).
    """
    
    # Bonferroni-corrected threshold for 49 tests at α=0.05
    # α_corrected = 0.05 / 49 ≈ 0.001
    BONFERRONI_ALPHA = 0.05 / 49
    
    # Minimum correlation to be practically useful
    MIN_PRACTICAL_CORRELATION = 0.15
    
    # Train/validation split ratio
    DISCOVERY_RATIO = 0.6  # 60% for discovery, 40% for validation
    
    def __init__(
        self,
        lookback_days: int = 90,
        lag_range_hours: int = 24,
    ):
        """
        Initialize sentiment calibrator.
        
        Args:
            lookback_days: Historical window for analysis
            lag_range_hours: Range of lags to test (-lag_range to +lag_range)
        """
        self.lookback_days = lookback_days
        self.lag_range = lag_range_hours
        
        logger.info(
            "sentiment_calibrator_initialized",
            lookback_days=lookback_days,
            lag_range_hours=lag_range_hours,
        )
    
    def measure_lead_lag(
        self,
        sentiment_series: np.ndarray,
        returns_series: np.ndarray,
        use_two_stage: bool = True,
    ) -> LeadLagResult:
        """
        Measure lead-lag relationship between sentiment and returns.
        
        Args:
            sentiment_series: Time series of sentiment scores
            returns_series: Time series of returns
            use_two_stage: If True, use A/B split validation (recommended)
        
        Returns:
            LeadLagResult with validation status
        """
        if len(sentiment_series) < 100:
            logger.warning("insufficient_data_for_calibration", length=len(sentiment_series))
            return self._insufficient_data_result()
        
        if use_two_stage:
            return self._two_stage_validation(sentiment_series, returns_series)
        else:
            return self._bonferroni_validation(sentiment_series, returns_series)
    
    def _two_stage_validation(
        self,
        sentiment: np.ndarray,
        returns: np.ndarray,
    ) -> LeadLagResult:
        """
        Two-stage validation: Discover on A, validate on B.
        
        This is the ONLY statistically valid approach when searching
        over multiple hypotheses (lag values).
        """
        n = len(sentiment)
        split_idx = int(n * self.DISCOVERY_RATIO)
        
        # Stage 1: Discovery on subset A
        sentiment_A = sentiment[:split_idx]
        returns_A = returns[:split_idx]
        
        discovery_result = self._find_optimal_lag(sentiment_A, returns_A)
        
        if not discovery_result["is_candidate"]:
            return LeadLagResult(
                optimal_lag_hours=0,
                correlation=0.0,
                p_value=1.0,
                is_significant=False,
                is_leading=False,
                validation_passed=False,
            )
        
        # Stage 2: Validate ONLY the discovered lag on subset B
        sentiment_B = sentiment[split_idx:]
        returns_B = returns[split_idx:]
        
        validation_corr, validation_p = self._test_single_lag(
            sentiment_B,
            returns_B,
            discovery_result["optimal_lag"],
        )
        
        # Validation uses standard α=0.05 (single test, no correction needed)
        validation_passed = (
            validation_p < 0.05 and
            abs(validation_corr) > self.MIN_PRACTICAL_CORRELATION and
            np.sign(validation_corr) == np.sign(discovery_result["correlation"])
        )
        
        return LeadLagResult(
            optimal_lag_hours=discovery_result["optimal_lag"],
            correlation=discovery_result["correlation"],
            p_value=discovery_result["p_value"],
            is_significant=True,  # Passed discovery phase
            is_leading=discovery_result["optimal_lag"] > 0,
            validation_correlation=validation_corr,
            validation_p_value=validation_p,
            validation_passed=validation_passed,  # THE CRITICAL FIELD
            discovery_correlation=discovery_result["correlation"],
            discovery_p_value=discovery_result["p_value"],
        )
    
    def _bonferroni_validation(
        self,
        sentiment: np.ndarray,
        returns: np.ndarray,
    ) -> LeadLagResult:
        """
        Bonferroni correction: Adjust significance threshold for multiple tests.
        
        Less powerful than two-stage but uses all data.
        """
        result = self._find_optimal_lag(sentiment, returns)
        
        # Apply Bonferroni correction: p-value must beat corrected threshold
        is_significant = (
            result["p_value"] < self.BONFERRONI_ALPHA and
            abs(result["correlation"]) > self.MIN_PRACTICAL_CORRELATION
        )
        
        return LeadLagResult(
            optimal_lag_hours=result["optimal_lag"],
            correlation=result["correlation"],
            p_value=result["p_value"],
            is_significant=is_significant,
            is_leading=result["optimal_lag"] > 0,
            validation_passed=is_significant,  # Same as significance for this method
        )
    
    def _find_optimal_lag(
        self,
        sentiment: np.ndarray,
        returns: np.ndarray,
    ) -> dict:
        """Search for optimal lag across all candidate values."""
        best_lag = 0
        best_corr = 0.0
        best_p = 1.0
        
        for lag in range(-self.lag_range, self.lag_range + 1):
            corr, p_value = self._test_single_lag(sentiment, returns, lag)
            
            if abs(corr) > abs(best_corr):
                best_lag = lag
                best_corr = corr
                best_p = p_value
        
        return {
            "optimal_lag": best_lag,
            "correlation": best_corr,
            "p_value": best_p,
            "is_candidate": abs(best_corr) > 0.1,  # Loose threshold for discovery
        }
    
    def _test_single_lag(
        self,
        sentiment: np.ndarray,
        returns: np.ndarray,
        lag: int,
    ) -> tuple[float, float]:
        """
        Test correlation at a specific lag value.
        
        Returns (correlation, p_value)
        """
        if lag > 0:
            # Sentiment leads: shift sentiment back
            aligned_sentiment = sentiment[:-lag] if lag > 0 else sentiment
            aligned_returns = returns[lag:] if lag > 0 else returns
        elif lag < 0:
            # Sentiment lags: shift returns back
            aligned_sentiment = sentiment[-lag:]
            aligned_returns = returns[:lag]
        else:
            aligned_sentiment = sentiment
            aligned_returns = returns
        
        # Use Pearson correlation with proper p-value
        if len(aligned_sentiment) < 30:
            return 0.0, 1.0
        
        corr, p_value = stats.pearsonr(aligned_sentiment, aligned_returns)
        return corr, p_value
    
    def get_sentiment_mode(self, result: LeadLagResult) -> SentimentMode:
        """
        Determine how to use sentiment based on VALIDATED calibration.
        
        CRITICAL: Only use sentiment if validation_passed is True.
        """
        if not result.validation_passed:
            return SentimentMode.DISABLED  # No validated edge, don't use sentiment
        
        if result.is_leading and result.validation_correlation and result.validation_correlation > 0:
            return SentimentMode.CONFIRMING  # Positive sentiment → likely up
        elif result.is_leading and result.validation_correlation and result.validation_correlation < 0:
            return SentimentMode.CONTRARIAN  # Positive sentiment → likely down (crowded)
        else:
            return SentimentMode.DISABLED  # Sentiment lags price, useless for prediction
    
    def _insufficient_data_result(self) -> LeadLagResult:
        """Return result for insufficient data."""
        return LeadLagResult(
            optimal_lag_hours=0,
            correlation=0.0,
            p_value=1.0,
            is_significant=False,
            is_leading=False,
            validation_passed=False,
        )
