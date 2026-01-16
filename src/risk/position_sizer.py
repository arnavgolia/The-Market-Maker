"""
Position sizing module.

Implements multiple position sizing methods:
- Fixed: Constant position size
- Volatility-adjusted: Scale by volatility to target constant risk
- Kelly: Optimal bet sizing based on win rate and edge
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import structlog

import numpy as np

logger = structlog.get_logger(__name__)


class PositionSizingMethod(Enum):
    """Position sizing methods."""
    FIXED = "fixed"
    VOLATILITY_ADJUSTED = "volatility_adjusted"
    KELLY = "kelly"


@dataclass
class PositionSizeResult:
    """Result of position sizing calculation."""
    size_pct: float  # Position size as % of portfolio
    size_dollars: float  # Position size in dollars
    size_shares: float  # Position size in shares
    current_price: float  # Price used for calculation
    method: str
    rationale: str


class PositionSizer:
    """
    Position sizing calculator.
    
    Position sizing is critical for risk management. Poor sizing
    can turn a profitable strategy into a losing one.
    """
    
    def __init__(
        self,
        method: PositionSizingMethod = PositionSizingMethod.VOLATILITY_ADJUSTED,
        max_position_pct: float = 10.0,
        volatility_target_pct: float = 15.0,
        base_position_pct: float = 5.0,
    ):
        """
        Initialize position sizer.
        
        Args:
            method: Position sizing method
            max_position_pct: Maximum position size (% of portfolio)
            volatility_target_pct: Target annualized volatility (%)
            base_position_pct: Base position size for fixed method (%)
        """
        self.method = method
        self.max_position_pct = max_position_pct
        self.volatility_target = volatility_target_pct / 100
        self.base_position_pct = base_position_pct
        
        logger.info(
            "position_sizer_initialized",
            method=method.value,
            max_position_pct=max_position_pct,
            volatility_target_pct=volatility_target_pct,
        )
    
    def calculate_size(
        self,
        portfolio_value: float,
        symbol: str,
        current_price: float,
        volatility: Optional[float] = None,
        win_rate: Optional[float] = None,
        avg_win: Optional[float] = None,
        avg_loss: Optional[float] = None,
        regime_scale: float = 1.0,
    ) -> PositionSizeResult:
        """
        Calculate position size.
        
        Args:
            portfolio_value: Total portfolio value
            symbol: Stock symbol
            current_price: Current stock price
            volatility: Annualized volatility (for volatility-adjusted)
            win_rate: Win rate (for Kelly)
            avg_win: Average win amount (for Kelly)
            avg_loss: Average loss amount (for Kelly)
            regime_scale: Regime-based scaling factor
        
        Returns:
            PositionSizeResult with size and rationale
        """
        if self.method == PositionSizingMethod.FIXED:
            return self._calculate_fixed(portfolio_value, regime_scale, current_price)
        
        elif self.method == PositionSizingMethod.VOLATILITY_ADJUSTED:
            if volatility is None:
                logger.warning(
                    "volatility_missing_using_fixed",
                    symbol=symbol,
                )
                return self._calculate_fixed(portfolio_value, regime_scale, current_price)
            
            return self._calculate_volatility_adjusted(
                portfolio_value,
                volatility,
                regime_scale,
                current_price,
            )
        
        elif self.method == PositionSizingMethod.KELLY:
            if win_rate is None or avg_win is None or avg_loss is None:
                logger.warning(
                    "kelly_params_missing_using_fixed",
                    symbol=symbol,
                )
                return self._calculate_fixed(portfolio_value, regime_scale, current_price)
            
            return self._calculate_kelly(
                portfolio_value,
                win_rate,
                avg_win,
                avg_loss,
                regime_scale,
                current_price,
            )
        
        else:
            # Fallback to fixed
            return self._calculate_fixed(portfolio_value, regime_scale, current_price)
    
    def _calculate_fixed(
        self,
        portfolio_value: float,
        regime_scale: float,
        current_price: float = 100.0,
    ) -> PositionSizeResult:
        """Calculate fixed position size."""
        size_pct = self.base_position_pct * regime_scale
        size_pct = min(size_pct, self.max_position_pct)  # Cap at max
        
        size_dollars = portfolio_value * (size_pct / 100)
        size_shares = size_dollars / current_price if current_price > 0 else 0
        
        return PositionSizeResult(
            size_pct=size_pct,
            size_dollars=size_dollars,
            size_shares=size_shares,
            current_price=current_price,
            method="fixed",
            rationale=f"Fixed {self.base_position_pct}% scaled by regime ({regime_scale:.2f})",
        )
    
    def _calculate_volatility_adjusted(
        self,
        portfolio_value: float,
        volatility: float,
        regime_scale: float,
        current_price: float,
    ) -> PositionSizeResult:
        """
        Calculate volatility-adjusted position size.
        
        This scales position size inversely with volatility to maintain
        constant risk across different assets.
        
        Formula: size = target_vol / asset_vol * base_size
        """
        if volatility <= 0:
            logger.warning("invalid_volatility_using_fixed", volatility=volatility)
            return self._calculate_fixed(portfolio_value, regime_scale, current_price)
        
        # Scale position size to target volatility
        vol_ratio = self.volatility_target / volatility
        
        # Base size scaled by volatility ratio
        size_pct = self.base_position_pct * vol_ratio * regime_scale
        
        # Cap at maximum
        size_pct = min(size_pct, self.max_position_pct)
        
        # Floor at 0.5% (minimum meaningful position)
        size_pct = max(size_pct, 0.5)
        
        size_dollars = portfolio_value * (size_pct / 100)
        size_shares = size_dollars / current_price if current_price > 0 else 0
        
        return PositionSizeResult(
            size_pct=size_pct,
            size_dollars=size_dollars,
            size_shares=size_shares,
            current_price=current_price,
            method="volatility_adjusted",
            rationale=(
                f"Vol-adjusted: target_vol={self.volatility_target:.1%}, "
                f"asset_vol={volatility:.1%}, ratio={vol_ratio:.2f}, "
                f"regime_scale={regime_scale:.2f}"
            ),
        )
    
    def _calculate_kelly(
        self,
        portfolio_value: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        regime_scale: float,
        current_price: float,
    ) -> PositionSizeResult:
        """
        Calculate Kelly criterion position size.
        
        Kelly formula: f* = (bp - q) / b
        where:
        - b = odds (avg_win / avg_loss)
        - p = win probability
        - q = loss probability (1 - p)
        
        We use fractional Kelly (typically 0.25-0.5) to reduce risk.
        """
        if win_rate <= 0 or win_rate >= 1:
            logger.warning("invalid_win_rate_using_fixed", win_rate=win_rate)
            return self._calculate_fixed(portfolio_value, regime_scale, current_price)
        
        if avg_loss <= 0:
            logger.warning("invalid_avg_loss_using_fixed", avg_loss=avg_loss)
            return self._calculate_fixed(portfolio_value, regime_scale, current_price)
        
        # Calculate Kelly fraction
        odds = avg_win / avg_loss
        kelly_fraction = (odds * win_rate - (1 - win_rate)) / odds
        
        # Use fractional Kelly (25% of full Kelly) for safety
        fractional_kelly = kelly_fraction * 0.25
        
        # Convert to position size percentage
        size_pct = fractional_kelly * 100 * regime_scale
        
        # Cap at maximum
        size_pct = min(size_pct, self.max_position_pct)
        
        # Floor at 0.5%
        size_pct = max(size_pct, 0.5)
        
        size_dollars = portfolio_value * (size_pct / 100)
        size_shares = size_dollars / current_price if current_price > 0 else 0
        
        return PositionSizeResult(
            size_pct=size_pct,
            size_dollars=size_dollars,
            size_shares=size_shares,
            current_price=current_price,
            method="kelly",
            rationale=(
                f"Kelly: win_rate={win_rate:.1%}, odds={odds:.2f}, "
                f"kelly={kelly_fraction:.2%}, fractional={fractional_kelly:.2%}, "
                f"regime_scale={regime_scale:.2f}"
            ),
        )
    
    def calculate_kelly_size(
        self,
        portfolio_value: float,
        win_prob: float,
        win_loss_ratio: float,
        current_price: float = 100.0,
    ) -> PositionSizeResult:
        """Helper method for Kelly calculation with simplified interface."""
        # Convert win/loss ratio to avg_win and avg_loss
        avg_loss = 1.0
        avg_win = win_loss_ratio
        
        return self._calculate_kelly(
            portfolio_value=portfolio_value,
            win_rate=win_prob,
            avg_win=avg_win,
            avg_loss=avg_loss,
            regime_scale=1.0,
            current_price=current_price,
        )
    
    def apply_max_limit(
        self,
        size_result: PositionSizeResult,
        portfolio_value: float,
    ) -> PositionSizeResult:
        """
        Apply maximum position limit.
        
        This is a safety check to ensure no single position
        exceeds the maximum allowed size.
        """
        if size_result.size_pct > self.max_position_pct:
            logger.warning(
                "position_size_capped",
                requested_pct=size_result.size_pct,
                max_pct=self.max_position_pct,
            )
            
            size_result.size_pct = self.max_position_pct
            size_result.size_dollars = portfolio_value * (self.max_position_pct / 100)
            size_result.rationale += f" (capped at {self.max_position_pct}%)"
        
        return size_result
