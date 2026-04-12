"""
Paper Trading Validation Service

Runs alongside the live service with dry_run=True.
Tracks all signals, their outcomes, and accumulates statistics.

When the system generates a signal:
  1. Log the signal with entry price, stop, TP
  2. On each subsequent cycle, check if stop or TP was hit
  3. Track win rate, average R:R, profit factor

Activation criteria (ALL must be met):
  - Minimum 50 resolved signals (hit TP or SL)
  - Win rate >= 55%
  - Profit factor >= 1.3 (gross profit / gross loss)
  - Max consecutive losses <= 5
  - At least 2 different regime classifications observed

Concurrent paper trades (up to 3 per symbol) with spacing guards:
  - 4-hour minimum time gap between entries on the same symbol
  - 1×ATR minimum price distance between entries on the same symbol
  - Max 3 concurrent open trades per symbol
"""
import structlog
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = structlog.get_logger(__name__)

# Spacing guards for concurrent paper trades
MAX_CONCURRENT_PER_SYMBOL = 3
MIN_TIME_GAP_HOURS = 4
MIN_PRICE_GAP_ATR = 1.0  # Must be 1×ATR away from any open entry


@dataclass
class PaperTrade:
    symbol: str
    action: str  # BUY or SELL
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_time: datetime
    regime: str
    lots: float = 0.01
    resolved: bool = False
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    pnl: float = 0.0
    outcome: str = ""  # "win", "loss", "open"


class PaperValidationService:
    MIN_SIGNALS = 50
    MIN_WIN_RATE = 0.55
    MIN_PROFIT_FACTOR = 1.3
    MAX_CONSECUTIVE_LOSSES = 5
    MIN_REGIME_TYPES = 2

    def __init__(self) -> None:
        self._open_trades: Dict[str, List[PaperTrade]] = {}  # symbol → list of trades
        self._resolved_trades: List[PaperTrade] = []
        self._regimes_seen: set = set()
        self._consecutive_losses: int = 0
        self._max_consecutive_losses: int = 0

    def record_signal(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        regime: str,
        lots: float = 0.01,
        atr: float = 0.0,
    ) -> None:
        """Record a new paper signal to track.

        Allows up to MAX_CONCURRENT_PER_SYMBOL concurrent trades per symbol,
        with spacing guards to ensure entries are genuinely independent:
          - 4-hour minimum time gap since last entry on this symbol
          - 1×ATR minimum price gap from any open entry on this symbol
        """
        existing = self._open_trades.get(symbol, [])

        # Guard 1: max concurrent trades per symbol
        if len(existing) >= MAX_CONCURRENT_PER_SYMBOL:
            logger.debug("paper_skip_max_concurrent", symbol=symbol,
                         open_count=len(existing))
            return

        # Guard 2: minimum time since last entry on this symbol
        if existing:
            last_entry_time = existing[-1].entry_time
            hours_since = (datetime.now(timezone.utc) - last_entry_time).total_seconds() / 3600
            if hours_since < MIN_TIME_GAP_HOURS:
                logger.debug("paper_skip_time_gap", symbol=symbol,
                             hours_since=round(hours_since, 2),
                             min_gap=MIN_TIME_GAP_HOURS)
                return

        # Guard 3: minimum price distance from any open entry
        if existing and atr > 0:
            for open_trade in existing:
                if abs(entry_price - open_trade.entry_price) < MIN_PRICE_GAP_ATR * atr:
                    logger.debug("paper_skip_price_gap", symbol=symbol,
                                 entry_price=entry_price,
                                 open_entry=open_trade.entry_price,
                                 price_gap=round(abs(entry_price - open_trade.entry_price), 5),
                                 min_gap=round(MIN_PRICE_GAP_ATR * atr, 5))
                    return

        trade = PaperTrade(
            symbol=symbol,
            action=action,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_time=datetime.now(timezone.utc),
            regime=regime,
            lots=lots,
        )
        existing.append(trade)
        self._open_trades[symbol] = existing
        self._regimes_seen.add(regime)

        logger.info(
            "paper_trade_opened",
            symbol=symbol,
            action=action,
            entry=entry_price,
            sl=stop_loss,
            tp=take_profit,
            regime=regime,
            concurrent_count=len(existing),
        )

    def check_outcomes(self, symbol: str, current_price: float) -> List[PaperTrade]:
        """Check if any open paper trades for this symbol hit TP or SL.

        Returns a list of resolved PaperTrades (may be empty).
        Each trade in the list was resolved this tick.
        """
        if symbol not in self._open_trades or not self._open_trades[symbol]:
            return []

        resolved = []
        remaining = []
        for trade in self._open_trades[symbol]:
            if trade.action == "BUY":
                if current_price <= trade.stop_loss:
                    self._resolve(trade, current_price, "loss")
                    resolved.append(trade)
                elif current_price >= trade.take_profit:
                    self._resolve(trade, current_price, "win")
                    resolved.append(trade)
                else:
                    remaining.append(trade)
            elif trade.action == "SELL":
                if current_price >= trade.stop_loss:
                    self._resolve(trade, current_price, "loss")
                    resolved.append(trade)
                elif current_price <= trade.take_profit:
                    self._resolve(trade, current_price, "win")
                    resolved.append(trade)
                else:
                    remaining.append(trade)

        self._open_trades[symbol] = remaining
        return resolved

    def _resolve(self, trade: PaperTrade, exit_price: float, outcome: str) -> None:
        """Mark a trade as closed and update running statistics."""
        trade.resolved = True
        trade.exit_price = exit_price
        trade.exit_time = datetime.now(timezone.utc)
        trade.outcome = outcome

        # Approximate P&L: price move × lots × contract size (1 000 units).
        # This is a simplified dollar-per-point calculation used solely for
        # comparing gross profit vs gross loss inside the profit factor metric.
        # Real live sizing uses the full risk-manager pipeline.
        if trade.action == "BUY":
            trade.pnl = (exit_price - trade.entry_price) * trade.lots * 1000
        else:
            trade.pnl = (trade.entry_price - exit_price) * trade.lots * 1000

        self._resolved_trades.append(trade)

        if outcome == "loss":
            self._consecutive_losses += 1
            self._max_consecutive_losses = max(
                self._max_consecutive_losses, self._consecutive_losses
            )
        else:
            self._consecutive_losses = 0

        logger.info(
            "paper_trade_resolved",
            symbol=trade.symbol,
            outcome=outcome,
            pnl=round(trade.pnl, 2),
            entry=trade.entry_price,
            exit=exit_price,
        )

    def get_validation_status(self) -> Dict:
        """Return current validation statistics and whether all criteria are met."""
        total = len(self._resolved_trades)
        wins = sum(1 for t in self._resolved_trades if t.outcome == "win")
        losses = sum(1 for t in self._resolved_trades if t.outcome == "loss")

        win_rate = wins / total if total > 0 else 0.0

        gross_profit = sum(t.pnl for t in self._resolved_trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self._resolved_trades if t.pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        criteria_met = (
            total >= self.MIN_SIGNALS
            and win_rate >= self.MIN_WIN_RATE
            and profit_factor >= self.MIN_PROFIT_FACTOR
            and self._max_consecutive_losses <= self.MAX_CONSECUTIVE_LOSSES
            and len(self._regimes_seen) >= self.MIN_REGIME_TYPES
        )

        return {
            "total_signals": total,
            "wins": wins,
            "losses": losses,
            "open_trades": sum(len(trades) for trades in self._open_trades.values()),
            "win_rate": round(win_rate, 4),
            "profit_factor": round(profit_factor, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "max_consecutive_losses": self._max_consecutive_losses,
            "regimes_seen": list(self._regimes_seen),
            "criteria_met": criteria_met,
            "criteria_detail": {
                "min_signals": total >= self.MIN_SIGNALS,
                "min_win_rate": win_rate >= self.MIN_WIN_RATE,
                "min_profit_factor": profit_factor >= self.MIN_PROFIT_FACTOR,
                "max_consec_losses": self._max_consecutive_losses <= self.MAX_CONSECUTIVE_LOSSES,
                "min_regimes": len(self._regimes_seen) >= self.MIN_REGIME_TYPES,
            },
        }
