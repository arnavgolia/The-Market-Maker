"""
NLP pipeline for sentiment analysis.

Uses FinBERT (financial BERT) for domain-specific sentiment analysis.
Processes Reddit/Twitter text and extracts sentiment scores.
"""

from typing import Optional
import structlog

try:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logger.warning("transformers not available - sentiment analysis will be limited")

logger = structlog.get_logger(__name__)


class SentimentPipeline:
    """
    NLP pipeline for sentiment analysis.
    
    Uses FinBERT for financial sentiment classification.
    FinBERT is pre-trained on financial text and outperforms
    general-purpose sentiment models for market-related text.
    """
    
    def __init__(
        self,
        model_name: str = "ProsusAI/finbert",
        use_gpu: bool = False,
    ):
        """
        Initialize sentiment pipeline.
        
        Args:
            model_name: HuggingFace model name (default: FinBERT)
            use_gpu: Use GPU if available
        """
        if not TRANSFORMERS_AVAILABLE:
            logger.warning("transformers_not_available_using_basic_sentiment")
            self.model = None
            self.tokenizer = None
            self.device = "cpu"
        else:
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(model_name)
                self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
                self.device = "cuda" if use_gpu and torch.cuda.is_available() else "cpu"
                self.model.to(self.device)
                self.model.eval()
                
                logger.info(
                    "sentiment_pipeline_initialized",
                    model=model_name,
                    device=self.device,
                )
            except Exception as e:
                logger.error("sentiment_model_load_failed", error=str(e))
                self.model = None
                self.tokenizer = None
                self.device = "cpu"
    
    def analyze_sentiment(
        self,
        text: str,
    ) -> dict:
        """
        Analyze sentiment of text.
        
        Returns:
            Dictionary with sentiment score and label
        """
        if not text or len(text.strip()) == 0:
            return {
                "score": 0.0,
                "label": "neutral",
                "confidence": 0.0,
            }
        
        # Use FinBERT if available
        if self.model and self.tokenizer:
            return self._analyze_with_finbert(text)
        else:
            # Fallback to basic sentiment
            return self._analyze_basic(text)
    
    def _analyze_with_finbert(self, text: str) -> dict:
        """Analyze sentiment using FinBERT."""
        try:
            import torch.nn.functional as F
            
            # Tokenize
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True,
            ).to(self.device)
            
            # Get predictions
            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits
                probs = F.softmax(logits, dim=-1)
            
            # FinBERT labels: positive, negative, neutral
            labels = ["positive", "negative", "neutral"]
            scores = probs[0].cpu().numpy()
            
            # Get predicted label
            predicted_idx = scores.argmax()
            predicted_label = labels[predicted_idx]
            confidence = float(scores[predicted_idx])
            
            # Calculate sentiment score (-1 to +1)
            # positive = +1, negative = -1, neutral = 0
            if predicted_label == "positive":
                score = confidence
            elif predicted_label == "negative":
                score = -confidence
            else:
                score = 0.0
            
            return {
                "score": score,
                "label": predicted_label,
                "confidence": confidence,
                "probabilities": {
                    "positive": float(scores[0]),
                    "negative": float(scores[1]),
                    "neutral": float(scores[2]),
                },
            }
            
        except Exception as e:
            logger.error("finbert_analysis_error", error=str(e))
            return self._analyze_basic(text)
    
    def _analyze_basic(self, text: str) -> dict:
        """
        Basic sentiment analysis (fallback).
        
        Uses simple keyword matching when FinBERT is not available.
        """
        text_lower = text.lower()
        
        # Positive keywords
        positive_keywords = [
            "bullish", "buy", "long", "moon", "rocket", "gains",
            "profit", "win", "up", "rise", "surge", "rally",
        ]
        
        # Negative keywords
        negative_keywords = [
            "bearish", "sell", "short", "crash", "drop", "loss",
            "down", "fall", "decline", "dump", "bear",
        ]
        
        positive_count = sum(1 for kw in positive_keywords if kw in text_lower)
        negative_count = sum(1 for kw in negative_keywords if kw in text_lower)
        
        if positive_count > negative_count:
            score = min(0.5, positive_count / 10.0)
            label = "positive"
        elif negative_count > positive_count:
            score = -min(0.5, negative_count / 10.0)
            label = "negative"
        else:
            score = 0.0
            label = "neutral"
        
        return {
            "score": score,
            "label": label,
            "confidence": abs(score),
        }
    
    def aggregate_sentiment(
        self,
        sentiment_scores: list[float],
        weights: Optional[list[float]] = None,
    ) -> dict:
        """
        Aggregate multiple sentiment scores.
        
        Args:
            sentiment_scores: List of sentiment scores (-1 to +1)
            weights: Optional weights for each score (e.g., by upvotes)
        
        Returns:
            Aggregated sentiment metrics
        """
        if not sentiment_scores:
            return {
                "mean": 0.0,
                "median": 0.0,
                "std": 0.0,
                "count": 0,
            }
        
        import numpy as np
        
        scores = np.array(sentiment_scores)
        
        if weights:
            weights_array = np.array(weights)
            weights_array = weights_array / weights_array.sum()  # Normalize
            mean = np.average(scores, weights=weights_array)
        else:
            mean = np.mean(scores)
        
        median = np.median(scores)
        std = np.std(scores)
        
        return {
            "mean": float(mean),
            "median": float(median),
            "std": float(std),
            "count": len(sentiment_scores),
            "positive_ratio": float(np.sum(scores > 0) / len(scores)),
            "negative_ratio": float(np.sum(scores < 0) / len(scores)),
        }
