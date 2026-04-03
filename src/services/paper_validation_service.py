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
"""
import structlog
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = structlog.get_logger(__name__)


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
        self._open_trades: Dict[str, PaperTrade] = {}  # symbol → trade
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
    ) -> None:
        """Record a new paper signal to track.

        Silently skips the symbol if a trade is already open for it — one open
        position per instrument at a time matches the live trading constraint.
        """
        if symbol in self._open_trades:
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
        self._open_trades[symbol] = trade
        self._regimes_seen.add(regime)

        logger.info(
            "paper_trade_opened",
            symbol=symbol,
            action=action,
            entry=entry_price,
            sl=stop_loss,
            tp=take_profit,
            regime=regime,
        )

    def check_outcomes(self, symbol: str, current_price: float) -> Optional[PaperTrade]:
        """Check if an open paper trade hit TP or SL.

        Returns the resolved PaperTrade if the trade closed this tick, or
        None if no trade is open for the symbol or neither level was hit.
        """
        if symbol not in self._open_trades:
            return None

        trade = self._open_trades[symbol]

        if trade.action == "BUY":
            if current_price <= trade.stop_loss:
                self._resolve(trade, current_price, "loss")
            elif current_price >= trade.take_profit:
                self._resolve(trade, current_price, "win")
        elif trade.action == "SELL":
            if current_price >= trade.stop_loss:
                self._resolve(trade, current_price, "loss")
            elif current_price <= trade.take_profit:
                self._resolve(trade, current_price, "win")

        if trade.resolved:
            del self._open_trades[symbol]
            return trade

        return None

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
            "open_trades": len(self._open_trades),
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
