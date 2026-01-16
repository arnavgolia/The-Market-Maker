"""
Tests for sentiment calibration (Bonferroni + two-stage validation).

These tests verify that the calibration correctly handles the multiple
testing problem identified by Gemini.
"""

import pytest
import numpy as np

from src.sentiment.calibration.lead_lag import (
    SentimentCalibrator,
    LeadLagResult,
    SentimentMode,
)


class TestSentimentCalibration:
    """Tests for sentiment calibration."""
    
    def test_two_stage_validation(self):
        """Test that two-stage validation prevents multiple testing trap."""
        calibrator = SentimentCalibrator(lookback_days=90, lag_range_hours=24)
        
        # Create synthetic data with known relationship
        # Sentiment leads returns by 2 hours
        n = 200
        sentiment = np.random.randn(n)
        returns = np.roll(sentiment, -2) + np.random.randn(n) * 0.1  # 2-hour lead
        
        result = calibrator.measure_lead_lag(
            sentiment_series=sentiment,
            returns_series=returns,
            use_two_stage=True,
        )
        
        # Should find the 2-hour lead
        assert result.optimal_lag_hours == 2
        assert result.is_leading is True
    
    def test_validation_passed_gate(self):
        """Test that validation_passed is the critical gate."""
        calibrator = SentimentCalibrator()
        
        # Create noise (no real relationship)
        n = 200
        sentiment = np.random.randn(n)
        returns = np.random.randn(n)  # Independent noise
        
        result = calibrator.measure_lead_lag(
            sentiment_series=sentiment,
            returns_series=returns,
            use_two_stage=True,
        )
        
        # Should NOT pass validation (no real relationship)
        assert result.validation_passed is False
        
        # Mode should be DISABLED
        mode = calibrator.get_sentiment_mode(result)
        assert mode == SentimentMode.DISABLED
    
    def test_bonferroni_correction(self):
        """Test Bonferroni correction as fallback."""
        calibrator = SentimentCalibrator()
        
        # Create noise
        n = 200
        sentiment = np.random.randn(n)
        returns = np.random.randn(n)
        
        result = calibrator.measure_lead_lag(
            sentiment_series=sentiment,
            returns_series=returns,
            use_two_stage=False,  # Use Bonferroni instead
        )
        
        # With Bonferroni, p-value must be < 0.05/49 ≈ 0.001
        # Noise should fail this
        assert result.validation_passed is False or result.p_value >= 0.001
    
    def test_sentiment_mode_selection(self):
        """Test sentiment mode selection based on calibration."""
        calibrator = SentimentCalibrator()
        
        # Test DISABLED mode (validation failed)
        result = LeadLagResult(
            optimal_lag_hours=0,
            correlation=0.0,
            p_value=1.0,
            is_significant=False,
            is_leading=False,
            validation_passed=False,
        )
        
        mode = calibrator.get_sentiment_mode(result)
        assert mode == SentimentMode.DISABLED
        
        # Test CONFIRMING mode (leads + positive correlation)
        result = LeadLagResult(
            optimal_lag_hours=2,
            correlation=0.2,
            p_value=0.01,
            is_significant=True,
            is_leading=True,
            validation_passed=True,
            validation_correlation=0.18,
        )
        
        mode = calibrator.get_sentiment_mode(result)
        assert mode == SentimentMode.CONFIRMING
        
        # Test CONTRARIAN mode (leads + negative correlation)
        result = LeadLagResult(
            optimal_lag_hours=2,
            correlation=-0.2,
            p_value=0.01,
            is_significant=True,
            is_leading=True,
            validation_passed=True,
            validation_correlation=-0.18,
        )
        
        mode = calibrator.get_sentiment_mode(result)
        assert mode == SentimentMode.CONTRARIAN
