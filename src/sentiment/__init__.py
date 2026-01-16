"""
Sentiment analysis module.

Handles:
- Real-time sentiment scraping (Reddit, Twitter)
- NLP processing (FinBERT)
- Lead-lag calibration (Bonferroni + A/B validation)
- Decay modeling
- Manipulation detection
"""

from src.sentiment.sources.reddit_scraper import RedditScraper
from src.sentiment.calibration.lead_lag import SentimentCalibrator, LeadLagResult

__all__ = ["RedditScraper", "SentimentCalibrator", "LeadLagResult"]
