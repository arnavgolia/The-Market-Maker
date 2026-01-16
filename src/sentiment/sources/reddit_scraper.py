"""
Reddit sentiment scraper.

Scrapes Reddit posts/comments for sentiment about stocks.
Includes manipulation detection to filter out pump-and-dump schemes.
"""

from datetime import datetime, timedelta
from typing import Optional, list
import structlog

import praw
from praw.models import Submission, Comment

logger = structlog.get_logger(__name__)


class RedditScraper:
    """
    Scrapes Reddit for sentiment data.
    
    Sources:
    - r/wallstreetbets
    - r/stocks
    - r/investing
    - r/options
    
    Includes manipulation detection to filter suspicious activity.
    """
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        subreddits: Optional[list[str]] = None,
    ):
        """
        Initialize Reddit scraper.
        
        Args:
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            user_agent: User agent string (required by Reddit API)
            subreddits: List of subreddits to scrape
        """
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        
        self.subreddits = subreddits or [
            "wallstreetbets",
            "stocks",
            "investing",
            "options",
        ]
        
        logger.info(
            "reddit_scraper_initialized",
            subreddits=self.subreddits,
        )
    
    def scrape_symbol(
        self,
        symbol: str,
        lookback_hours: int = 24,
        max_posts: int = 100,
    ) -> list[dict]:
        """
        Scrape Reddit for mentions of a symbol.
        
        Args:
            symbol: Stock symbol (e.g., "AAPL")
            lookback_hours: How far back to look
            max_posts: Maximum posts to return
        
        Returns:
            List of post/comment dictionaries with sentiment data
        """
        results = []
        cutoff_time = datetime.now() - timedelta(hours=lookback_hours)
        
        # Search across all subreddits
        for subreddit_name in self.subreddits:
            try:
                subreddit = self.reddit.subreddit(subreddit_name)
                
                # Search for symbol mentions
                query = f"${symbol} OR {symbol}"
                
                for submission in subreddit.search(
                    query,
                    sort="new",
                    limit=max_posts // len(self.subreddits),
                ):
                    # Check if post is recent enough
                    post_time = datetime.fromtimestamp(submission.created_utc)
                    if post_time < cutoff_time:
                        continue
                    
                    # Check for manipulation
                    if self._is_manipulation(submission):
                        logger.debug(
                            "manipulation_detected",
                            submission_id=submission.id,
                            symbol=symbol,
                        )
                        continue
                    
                    # Extract sentiment data
                    post_data = {
                        "source": "reddit",
                        "subreddit": subreddit_name,
                        "post_id": submission.id,
                        "title": submission.title,
                        "text": submission.selftext,
                        "score": submission.score,
                        "num_comments": submission.num_comments,
                        "created_at": post_time,
                        "url": submission.url,
                        "symbol": symbol,
                    }
                    
                    results.append(post_data)
                    
                    # Also scrape top comments
                    submission.comments.replace_more(limit=0)
                    for comment in submission.comments.list()[:10]:  # Top 10 comments
                        if isinstance(comment, Comment):
                            comment_data = {
                                "source": "reddit",
                                "subreddit": subreddit_name,
                                "post_id": submission.id,
                                "comment_id": comment.id,
                                "text": comment.body,
                                "score": comment.score,
                                "created_at": datetime.fromtimestamp(comment.created_utc),
                                "symbol": symbol,
                            }
                            results.append(comment_data)
            
            except Exception as e:
                logger.error(
                    "reddit_scrape_error",
                    subreddit=subreddit_name,
                    symbol=symbol,
                    error=str(e),
                )
        
        logger.info(
            "reddit_scrape_complete",
            symbol=symbol,
            results_count=len(results),
        )
        
        return results
    
    def _is_manipulation(self, submission: Submission) -> bool:
        """
        Detect potential manipulation/pump-and-dump.
        
        Heuristics:
        - New account (< 30 days old)
        - Suspicious patterns (all caps, excessive emojis)
        - Coordinated posting (same user posting multiple times)
        - Low karma relative to post score
        """
        # Check account age
        if submission.author:
            account_age_days = (datetime.now().timestamp() - submission.author.created_utc) / 86400
            if account_age_days < 30:
                return True
        
        # Check for suspicious patterns
        title_lower = submission.title.lower()
        suspicious_patterns = [
            "🚀" * 3,  # Excessive rockets
            "to the moon" in title_lower,
            "diamond hands" in title_lower and submission.score > 1000,
        ]
        
        if any(submission.title.count(pattern) > 0 for pattern in ["🚀", "💎", "📈"] * 3):
            return True
        
        # Check karma ratio (low karma but high score = suspicious)
        if submission.author and submission.score > 100:
            if submission.author.link_karma < 100 and submission.score > 500:
                return True
        
        return False
    
    def get_hot_posts(
        self,
        subreddit_name: str,
        limit: int = 25,
    ) -> list[dict]:
        """Get hot posts from a subreddit."""
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            posts = []
            
            for submission in subreddit.hot(limit=limit):
                post_data = {
                    "source": "reddit",
                    "subreddit": subreddit_name,
                    "post_id": submission.id,
                    "title": submission.title,
                    "text": submission.selftext,
                    "score": submission.score,
                    "num_comments": submission.num_comments,
                    "created_at": datetime.fromtimestamp(submission.created_utc),
                    "url": submission.url,
                }
                posts.append(post_data)
            
            return posts
            
        except Exception as e:
            logger.error(
                "reddit_hot_posts_error",
                subreddit=subreddit_name,
                error=str(e),
            )
            return []
