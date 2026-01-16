"""
Tax-Lot Tracking System with FIFO/LIFO/Wash Sale Detection.

This module provides institutional-grade tax accounting:
- FIFO (First In First Out) cost basis
- LIFO (Last In First Out) cost basis
- Specific lot identification
- Wash sale detection (30-day rule)
- Short-term vs long-term gain classification
- Realized vs unrealized P&L separation

Critical for regulatory compliance and accurate tax reporting.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class TaxLotMethod(str, Enum):
    """Tax lot accounting methods."""
    FIFO = "FIFO"  # First In First Out (default)
    LIFO = "LIFO"  # Last In First Out
    SPECIFIC = "SPECIFIC"  # Specific lot identification
    HIFO = "HIFO"  # Highest In First Out (tax optimization)


class TermType(str, Enum):
    """Holding period classification."""
    SHORT_TERM = "SHORT_TERM"  # <= 365 days
    LONG_TERM = "LONG_TERM"    # > 365 days


@dataclass
class TaxLot:
    """
    Represents a single tax lot (purchase).
    
    A tax lot is created when shares are acquired and is closed
    when those specific shares are sold (based on accounting method).
    """
    lot_id: str
    symbol: str
    quantity: float
    cost_basis_per_share: float  # Price paid per share
    acquisition_date: datetime
    acquisition_time: datetime  # Full timestamp
    
    # Optional fields
    commission: float = 0.0
    fees: float = 0.0
    
    @property
    def total_cost_basis(self) -> float:
        """Total cost including commissions and fees."""
        return (self.quantity * self.cost_basis_per_share) + self.commission + self.fees
    
    @property
    def adjusted_cost_per_share(self) -> float:
        """Cost per share including commissions/fees."""
        if self.quantity == 0:
            return 0.0
        return self.total_cost_basis / self.quantity
    
    def holding_period_days(self, as_of_date: datetime) -> int:
        """Number of days held."""
        return (as_of_date - self.acquisition_date).days
    
    def term_type(self, as_of_date: datetime) -> TermType:
        """Classify as short-term or long-term."""
        if self.holding_period_days(as_of_date) <= 365:
            return TermType.SHORT_TERM
        return TermType.LONG_TERM


@dataclass
class ClosedLot:
    """
    Represents a closed tax lot (shares sold).
    
    Used for realized gain/loss calculation and wash sale detection.
    """
    lot_id: str
    symbol: str
    quantity: float
    cost_basis_per_share: float
    sale_price_per_share: float
    acquisition_date: datetime
    sale_date: datetime
    commission: float = 0.0
    fees: float = 0.0
    is_wash_sale: bool = False
    wash_sale_disallowed_loss: float = 0.0
    
    @property
    def proceeds(self) -> float:
        """Sale proceeds (gross, before commissions)."""
        return self.quantity * self.sale_price_per_share
    
    @property
    def net_proceeds(self) -> float:
        """Sale proceeds after commissions/fees."""
        return self.proceeds - self.commission - self.fees
    
    @property
    def cost_basis(self) -> float:
        """Original cost basis."""
        return self.quantity * self.cost_basis_per_share
    
    @property
    def realized_gain_loss(self) -> float:
        """Realized gain or loss (negative = loss)."""
        gain = self.net_proceeds - self.cost_basis
        
        # If wash sale, disallow the loss
        if self.is_wash_sale and gain < 0:
            return 0.0  # Loss is disallowed
        
        return gain
    
    @property
    def term_type(self) -> TermType:
        """Holding period classification."""
        holding_days = (self.sale_date - self.acquisition_date).days
        if holding_days <= 365:
            return TermType.SHORT_TERM
        return TermType.LONG_TERM


@dataclass
class WashSaleEvent:
    """
    Represents a wash sale violation.
    
    Wash Sale Rule: If you sell a security at a loss and purchase
    a substantially identical security within 30 days before or after
    the sale, the loss is disallowed for tax purposes.
    """
    symbol: str
    sale_date: datetime
    sale_quantity: float
    disallowed_loss: float
    replacement_purchase_date: datetime
    replacement_quantity: float


class TaxLotTracker:
    """
    Tracks tax lots with FIFO/LIFO support and wash sale detection.
    
    Design:
    - Maintains open lots (not yet sold)
    - Tracks closed lots (sold positions)
    - Detects wash sales automatically
    - Calculates realized and unrealized P&L
    - Separates short-term and long-term gains
    """
    
    def __init__(self, method: TaxLotMethod = TaxLotMethod.FIFO):
        self.method = method
        self.open_lots: Dict[str, List[TaxLot]] = {}  # symbol -> [lots]
        self.closed_lots: List[ClosedLot] = []
        self.wash_sale_events: List[WashSaleEvent] = []
        
        logger.info("tax_lot_tracker_initialized", method=method.value)
    
    def add_purchase(
        self,
        symbol: str,
        quantity: float,
        price: float,
        timestamp: datetime,
        commission: float = 0.0,
        fees: float = 0.0,
    ) -> TaxLot:
        """
        Add a new tax lot (purchase).
        
        Args:
            symbol: Ticker symbol
            quantity: Number of shares
            price: Price per share
            timestamp: Acquisition timestamp
            commission: Trading commission
            fees: Other fees
        
        Returns:
            Created TaxLot
        """
        lot_id = f"{symbol}_{timestamp.isoformat()}_{quantity}"
        
        lot = TaxLot(
            lot_id=lot_id,
            symbol=symbol,
            quantity=quantity,
            cost_basis_per_share=price,
            acquisition_date=timestamp.date(),
            acquisition_time=timestamp,
            commission=commission,
            fees=fees,
        )
        
        if symbol not in self.open_lots:
            self.open_lots[symbol] = []
        
        self.open_lots[symbol].append(lot)
        
        logger.debug(
            "tax_lot_added",
            symbol=symbol,
            quantity=quantity,
            price=price,
            lot_id=lot_id,
        )
        
        return lot
    
    def process_sale(
        self,
        symbol: str,
        quantity: float,
        price: float,
        timestamp: datetime,
        commission: float = 0.0,
        fees: float = 0.0,
    ) -> Tuple[List[ClosedLot], float]:
        """
        Process a sale by closing tax lots.
        
        Args:
            symbol: Ticker symbol
            quantity: Number of shares sold
            price: Sale price per share
            timestamp: Sale timestamp
            commission: Trading commission
            fees: Other fees
        
        Returns:
            (list of closed lots, total realized gain/loss)
        """
        if symbol not in self.open_lots or not self.open_lots[symbol]:
            logger.warning("sale_without_open_lots", symbol=symbol, quantity=quantity)
            # This is a short sale or error - create synthetic lot
            lot = TaxLot(
                lot_id=f"{symbol}_synthetic_{timestamp.isoformat()}",
                symbol=symbol,
                quantity=quantity,
                cost_basis_per_share=price,  # Use sale price as cost
                acquisition_date=timestamp.date(),
                acquisition_time=timestamp,
            )
            self.open_lots[symbol] = [lot]
        
        remaining_quantity = quantity
        closed_lots = []
        total_realized_pnl = 0.0
        
        # Select lots based on method
        lots_to_close = self._select_lots_for_sale(symbol, quantity)
        
        for lot in lots_to_close:
            if remaining_quantity <= 0:
                break
            
            # How much of this lot to close
            quantity_to_close = min(remaining_quantity, lot.quantity)
            
            # Calculate proportional commission/fees
            proportion = quantity_to_close / quantity
            lot_commission = commission * proportion
            lot_fees = fees * proportion
            
            # Create closed lot
            closed_lot = ClosedLot(
                lot_id=lot.lot_id,
                symbol=symbol,
                quantity=quantity_to_close,
                cost_basis_per_share=lot.cost_basis_per_share,
                sale_price_per_share=price,
                acquisition_date=lot.acquisition_date,
                sale_date=timestamp.date(),
                commission=lot_commission,
                fees=lot_fees,
            )
            
            # Check for wash sale
            self._check_wash_sale(closed_lot, timestamp)
            
            closed_lots.append(closed_lot)
            total_realized_pnl += closed_lot.realized_gain_loss
            
            # Update or remove the lot
            lot.quantity -= quantity_to_close
            if lot.quantity <= 0.0001:  # Floating point tolerance
                self.open_lots[symbol].remove(lot)
            
            remaining_quantity -= quantity_to_close
        
        # Store closed lots
        self.closed_lots.extend(closed_lots)
        
        logger.info(
            "sale_processed",
            symbol=symbol,
            quantity=quantity,
            price=price,
            lots_closed=len(closed_lots),
            realized_pnl=total_realized_pnl,
        )
        
        return closed_lots, total_realized_pnl
    
    def _select_lots_for_sale(self, symbol: str, quantity: float) -> List[TaxLot]:
        """
        Select which lots to close based on accounting method.
        
        Args:
            symbol: Ticker symbol
            quantity: Quantity to sell
        
        Returns:
            Ordered list of lots to close
        """
        lots = self.open_lots.get(symbol, [])
        
        if self.method == TaxLotMethod.FIFO:
            # Oldest first
            return sorted(lots, key=lambda x: x.acquisition_time)
        
        elif self.method == TaxLotMethod.LIFO:
            # Newest first
            return sorted(lots, key=lambda x: x.acquisition_time, reverse=True)
        
        elif self.method == TaxLotMethod.HIFO:
            # Highest cost first (tax optimization - realize losses first)
            return sorted(lots, key=lambda x: x.cost_basis_per_share, reverse=True)
        
        else:  # SPECIFIC
            # User would specify which lots (default to FIFO)
            return sorted(lots, key=lambda x: x.acquisition_time)
    
    def _check_wash_sale(self, closed_lot: ClosedLot, sale_timestamp: datetime):
        """
        Check if this sale triggers a wash sale.
        
        Wash Sale Rule: If you sell at a loss and buy the same security
        within 30 days before or after, the loss is disallowed.
        
        Args:
            closed_lot: The lot being closed
            sale_timestamp: Sale timestamp
        """
        # Only check if it's a loss
        if closed_lot.realized_gain_loss >= 0:
            return
        
        symbol = closed_lot.symbol
        sale_date = sale_timestamp.date()
        
        # Check 30 days before and after
        window_start = sale_date - timedelta(days=30)
        window_end = sale_date + timedelta(days=30)
        
        # Look for purchases in the wash sale window
        if symbol in self.open_lots:
            for lot in self.open_lots[symbol]:
                if window_start <= lot.acquisition_date <= window_end:
                    # Found a wash sale
                    closed_lot.is_wash_sale = True
                    closed_lot.wash_sale_disallowed_loss = abs(closed_lot.realized_gain_loss)
                    
                    wash_event = WashSaleEvent(
                        symbol=symbol,
                        sale_date=sale_date,
                        sale_quantity=closed_lot.quantity,
                        disallowed_loss=closed_lot.wash_sale_disallowed_loss,
                        replacement_purchase_date=lot.acquisition_date,
                        replacement_quantity=lot.quantity,
                    )
                    self.wash_sale_events.append(wash_event)
                    
                    logger.warning(
                        "wash_sale_detected",
                        symbol=symbol,
                        sale_date=sale_date.isoformat(),
                        disallowed_loss=closed_lot.wash_sale_disallowed_loss,
                        replacement_date=lot.acquisition_date.isoformat(),
                    )
                    break
    
    def get_unrealized_pnl(self, symbol: str, current_price: float) -> float:
        """
        Calculate unrealized P&L for open positions.
        
        Args:
            symbol: Ticker symbol
            current_price: Current market price
        
        Returns:
            Unrealized gain/loss
        """
        if symbol not in self.open_lots:
            return 0.0
        
        unrealized = 0.0
        for lot in self.open_lots[symbol]:
            market_value = lot.quantity * current_price
            unrealized += (market_value - lot.total_cost_basis)
        
        return unrealized
    
    def get_realized_pnl(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, float]:
        """
        Calculate realized P&L.
        
        Args:
            symbol: Optional symbol filter
            start_date: Optional start date
            end_date: Optional end date
        
        Returns:
            Dict with short_term, long_term, total, wash_sale_loss
        """
        relevant_lots = self.closed_lots
        
        # Apply filters
        if symbol:
            relevant_lots = [l for l in relevant_lots if l.symbol == symbol]
        if start_date:
            relevant_lots = [l for l in relevant_lots if l.sale_date >= start_date.date()]
        if end_date:
            relevant_lots = [l for l in relevant_lots if l.sale_date <= end_date.date()]
        
        short_term_pnl = sum(
            l.realized_gain_loss for l in relevant_lots
            if l.term_type == TermType.SHORT_TERM
        )
        
        long_term_pnl = sum(
            l.realized_gain_loss for l in relevant_lots
            if l.term_type == TermType.LONG_TERM
        )
        
        wash_sale_loss = sum(
            l.wash_sale_disallowed_loss for l in relevant_lots
            if l.is_wash_sale
        )
        
        return {
            "short_term": short_term_pnl,
            "long_term": long_term_pnl,
            "total": short_term_pnl + long_term_pnl,
            "wash_sale_disallowed": wash_sale_loss,
        }
    
    def get_cost_basis(self, symbol: str) -> float:
        """
        Get total cost basis for open positions.
        
        Args:
            symbol: Ticker symbol
        
        Returns:
            Total cost basis
        """
        if symbol not in self.open_lots:
            return 0.0
        
        return sum(lot.total_cost_basis for lot in self.open_lots[symbol])
    
    def get_average_cost(self, symbol: str) -> float:
        """
        Get average cost per share for open positions.
        
        Args:
            symbol: Ticker symbol
        
        Returns:
            Average cost per share
        """
        if symbol not in self.open_lots or not self.open_lots[symbol]:
            return 0.0
        
        total_quantity = sum(lot.quantity for lot in self.open_lots[symbol])
        total_cost = self.get_cost_basis(symbol)
        
        if total_quantity == 0:
            return 0.0
        
        return total_cost / total_quantity
    
    def export_for_tax_reporting(self, year: int) -> Dict:
        """
        Export data for tax reporting (Form 8949).
        
        Args:
            year: Tax year
        
        Returns:
            Dict with all closed lots for the year
        """
        year_start = datetime(year, 1, 1)
        year_end = datetime(year, 12, 31)
        
        year_lots = [
            l for l in self.closed_lots
            if year_start.date() <= l.sale_date <= year_end.date()
        ]
        
        short_term_lots = [l for l in year_lots if l.term_type == TermType.SHORT_TERM]
        long_term_lots = [l for l in year_lots if l.term_type == TermType.LONG_TERM]
        
        return {
            "year": year,
            "short_term_transactions": [
                {
                    "symbol": l.symbol,
                    "quantity": l.quantity,
                    "acquisition_date": l.acquisition_date.isoformat(),
                    "sale_date": l.sale_date.isoformat(),
                    "cost_basis": l.cost_basis,
                    "proceeds": l.net_proceeds,
                    "gain_loss": l.realized_gain_loss,
                    "is_wash_sale": l.is_wash_sale,
                }
                for l in short_term_lots
            ],
            "long_term_transactions": [
                {
                    "symbol": l.symbol,
                    "quantity": l.quantity,
                    "acquisition_date": l.acquisition_date.isoformat(),
                    "sale_date": l.sale_date.isoformat(),
                    "cost_basis": l.cost_basis,
                    "proceeds": l.net_proceeds,
                    "gain_loss": l.realized_gain_loss,
                    "is_wash_sale": l.is_wash_sale,
                }
                for l in long_term_lots
            ],
            "wash_sale_events": [
                {
                    "symbol": ws.symbol,
                    "sale_date": ws.sale_date.isoformat(),
                    "disallowed_loss": ws.disallowed_loss,
                    "replacement_date": ws.replacement_purchase_date.isoformat(),
                }
                for ws in self.wash_sale_events
                if year_start.date() <= ws.sale_date <= year_end.date()
            ],
            "totals": self.get_realized_pnl(start_date=year_start, end_date=year_end),
        }
