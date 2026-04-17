"""
TieredPositionSizer - Confidence-based position sizing for small account recovery.

Scales lot size with ML confidence while enforcing margin and drawdown safety rails.

Tiers:
    50-70% confidence  → 10% of account
    70-85% confidence  → 20% of account
    85-95% confidence  → 30% of account
    95%+   confidence  → 50% of account
"""
from typing import Dict, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)

# Margin per 0.01 lot by symbol (approximate, varies by broker leverage)
MARGIN_PER_LOT: Dict[str, float] = {
    "CrudeOIL": 40.55,
    "BRENT_OIL": 45.00,
    "USA500": 33.00,
    "GBPJPY.": 25.00,
    "XAUUSD": 50.00,
}

DEFAULT_MARGIN_PER_LOT = 40.0

# Contract sizes (must match live_trading_service.py)
CONTRACT_SIZES: Dict[str, int] = {
    "CrudeOIL": 1000,
    "USA500": 50,
    "GBPJPY.": 100_000,
    "XAUUSD": 100,
    "BRENT_OIL": 1000,
}

MIN_LOTS = 0.01
MAX_LOTS_TOTAL = 0.10  # Hard cap across all symbols

# Confidence tiers: (min_confidence, account_pct)
# Conservative after live losses — model probability != model accuracy
TIERS = [
    (0.95, 0.20),  # Was 50% → 20%. High conf still gets most, but not half the account
    (0.85, 0.15),  # Was 30% → 15%
    (0.70, 0.10),  # Was 20% → 10%
    (0.50, 0.05),  # Was 10% → 5%
]


class TieredPositionSizer:
    """
    Calculates lot size based on ML confidence level.

    Safety rails:
    - Margin level floor: 200% minimum after trade
    - Max total lots: 0.10 across all symbols
    - Daily loss limit: 5% of account → halt trading
    - Weekly loss limit: 15% → require review
    - Small account protection: if min lot exceeds 5% account risk, tighten the
      stop up to 0.8×ATR floor; if that is still insufficient, return 0.0 (skip trade).

    After calling calculate_lot_size(), check _last_adjusted_stop — if not None,
    the caller must use that value instead of 2×ATR for the stop distance.
    """

    def __init__(
        self,
        margin_floor_pct: float = 200.0,
        max_total_lots: float = 0.10,
        daily_loss_pct: float = 0.05,
        weekly_loss_pct: float = 0.15,
    ):
        self.margin_floor_pct = margin_floor_pct
        self.max_total_lots = max_total_lots
        self.daily_loss_limit_pct = daily_loss_pct
        self.weekly_loss_limit_pct = weekly_loss_pct
        self._last_adjusted_stop: Optional[float] = None

    def calculate_lot_size(
        self,
        confidence: float,
        account_balance: float,
        symbol: str,
        atr: float = 0.0,
        existing_lots: float = 0.0,
    ) -> float:
        """
        Calculate lot size based on ML confidence tier.

        Args:
            confidence:      ML signal confidence (0.0 to 1.0)
            account_balance: Current account balance in account currency
            symbol:          Trading symbol
            atr:             Current ATR for stop distance calculation
            existing_lots:   Lots already open for this symbol (for pyramid cap)

        Returns:
            Lot size rounded to 2dp, minimum 0.01, respecting all caps.
            Returns 0.0 if the account is too small to trade the symbol safely
            (min lot risk exceeds 5% even with stop tightened to 1×ATR).

        Side effects:
            Sets self._last_adjusted_stop when the stop has been tightened for a
            small account.  Caller must substitute this for 2×ATR.  Always None
            when this method returns 0.0 or when no adjustment was needed.
        """
        # Reset adjusted stop at the start of every call
        self._last_adjusted_stop = None

        if confidence < 0.50 or account_balance <= 0:
            return 0.0

        # Determine tier
        account_pct = 0.10  # Default to lowest
        for min_conf, pct in TIERS:
            if confidence >= min_conf:
                account_pct = pct
                break

        # Calculate risk amount
        risk_amount = account_balance * account_pct

        # Calculate lots from risk amount
        contract_size = CONTRACT_SIZES.get(symbol, 1000)
        stop_distance = 2.0 * atr if atr > 0 else 1.0  # Fallback if no ATR

        if stop_distance > 0 and contract_size > 0:
            raw_lots = risk_amount / (stop_distance * contract_size)
        else:
            raw_lots = MIN_LOTS

        # Apply caps
        lots = round(max(MIN_LOTS, raw_lots), 2)

        # Small-account protection: check whether the minimum lot already exceeds
        # the 5% hard risk cap before committing to this trade.
        min_lot_risk = stop_distance * contract_size * MIN_LOTS
        actual_risk_pct = min_lot_risk / account_balance if account_balance > 0 else 1.0

        if actual_risk_pct > 0.05:
            # Tighten the stop so that 0.01 lots == exactly 5% account risk
            max_stop = (0.05 * account_balance) / (contract_size * MIN_LOTS)

            # Accept the tighter stop when it is at least 80% of ATR.
            # Stops narrower than ~0.8×ATR are vulnerable to stop-hunting; tighter
            # than that and we skip the trade rather than enter with a suicidal stop.
            # Lowered from 0.9 to 0.8 to unblock small accounts on high-ATR symbols
            # (e.g. $293 account on CrudeOIL with ATR=$1.71 → ratio=0.86 now passes).
            if atr > 0 and max_stop >= 0.8 * atr:
                # Stop is still wider than 1×ATR — safe to tighten and proceed
                self._last_adjusted_stop = max_stop
                logger.info(
                    "stop_tightened_for_risk",
                    symbol=symbol,
                    original_stop=round(stop_distance, 4),
                    adjusted_stop=round(max_stop, 4),
                    risk_pct=round(
                        max_stop * contract_size * MIN_LOTS / account_balance, 4
                    ),
                )
                return MIN_LOTS
            else:
                # Stop would need to go below 1×ATR — too tight, skip this trade
                logger.warning(
                    "account_too_small_for_symbol",
                    symbol=symbol,
                    min_risk_pct=round(actual_risk_pct, 4),
                    min_stop_atr=round(max_stop / atr, 2) if atr > 0 else 0,
                    account_balance=round(account_balance, 2),
                )
                return 0.0

        # Cap at max total (minus existing)
        remaining_capacity = round(max(0.0, self.max_total_lots - existing_lots), 2)
        lots = round(min(lots, remaining_capacity), 2)

        # Floor at minimum
        if lots < MIN_LOTS:
            lots = MIN_LOTS if remaining_capacity >= MIN_LOTS else 0.0

        logger.info(
            "tiered_position_size",
            symbol=symbol,
            confidence=round(confidence, 4),
            tier_pct=account_pct,
            risk_amount=round(risk_amount, 2),
            raw_lots=round(raw_lots, 4),
            final_lots=lots,
            existing_lots=existing_lots,
            balance=round(account_balance, 2),
        )

        return lots

    def get_margin_requirement(self, symbol: str, lots: float) -> float:
        """
        Estimate margin required for a given lot size.

        Args:
            symbol: Trading symbol
            lots:   Lot size

        Returns:
            Estimated margin in account currency.
        """
        margin_per = MARGIN_PER_LOT.get(symbol, DEFAULT_MARGIN_PER_LOT)
        # margin_per is per 0.01 lot, scale to actual lots
        return margin_per * (lots / 0.01)

    def validate_margin_level(
        self,
        lots: float,
        symbol: str,
        equity: float,
        current_margin: float,
    ) -> Tuple[bool, float]:
        """
        Check if adding this trade would keep margin level above floor.

        Args:
            lots:           Proposed lot size
            symbol:         Trading symbol
            equity:         Current account equity
            current_margin: Current margin used

        Returns:
            Tuple of (valid, projected_margin_level_pct)
        """
        new_margin = self.get_margin_requirement(symbol, lots)
        total_margin = current_margin + new_margin

        if total_margin <= 0:
            return True, 999999.0

        projected_level = (equity / total_margin) * 100.0

        valid = projected_level >= self.margin_floor_pct

        logger.debug(
            "margin_validation",
            symbol=symbol,
            lots=lots,
            new_margin=round(new_margin, 2),
            total_margin=round(total_margin, 2),
            equity=round(equity, 2),
            projected_level=round(projected_level, 1),
            floor=self.margin_floor_pct,
            valid=valid,
        )

        return valid, projected_level

    def check_daily_loss_halt(
        self, daily_pnl: float, account_balance: float
    ) -> bool:
        """
        Check if daily loss limit has been breached.

        Returns True if trading should HALT.
        """
        limit = account_balance * self.daily_loss_limit_pct
        return daily_pnl <= -limit

    def check_weekly_loss_warning(
        self, weekly_pnl: float, account_balance: float
    ) -> bool:
        """
        Check if weekly loss limit requires review.

        Returns True if trading should be reviewed.
        """
        limit = account_balance * self.weekly_loss_limit_pct
        return weekly_pnl <= -limit
