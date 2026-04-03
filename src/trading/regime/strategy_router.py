"""
StrategyRouter — maps MarketRegime to a filtered strategy configuration.

Replaces the "run all strategies blindly" approach with a regime-aware routing
table.  Each regime has a fixed set of allowed strategies, per-strategy weights,
a signal score threshold, and a trading-allowed flag.

Routing table
-------------
TRENDING:
    Allowed   : momentum (0.40), breakout (0.35), trend_following (0.25)
    Blocked   : value_area, mean_reversion, ml_reversal
    Threshold : 0.60

RANGING:
    Allowed   : value_area (0.45), mean_reversion (0.35), ml_reversal (0.20)
    Blocked   : momentum, breakout
    Threshold : 0.60

VOLATILE:
    allow_trading = False — no new entries during high-volatility halts.

UNKNOWN:
    All strategies equal weight (0.20 each).
    Threshold : 0.75 (extra selectivity to compensate for regime uncertainty).

Strategy names
--------------
The names used here match the keys used in ``_generate_signal`` inside
``LiveTradingService``:
    "momentum", "mean_reversion", "breakout", "value_area", "ml_reversal"

A sixth strategy name, "trend_following", maps to the momentum strategy
implementation in live_trading_service.py (they share the same signal
function; the router uses the name to control weight allocation).

Input contract
--------------
regime : MarketRegime
    One of TRENDING, RANGING, VOLATILE, UNKNOWN from
    ``src.trading.regime.regime_classifier``.

Output contract
---------------
Dict with keys:
    strategies      : Dict[str, float]   — {strategy_name: weight}
    signal_threshold: float              — minimum |score| to emit a signal
    allow_trading   : bool               — False → skip symbol this cycle
    reason          : str                — human-readable justification

Edge cases
----------
- Unknown/future MarketRegime values → treated as UNKNOWN routing.
- All weights in a routing entry sum to 1.0; callers must NOT normalise them
  further; the weights are already intentional fractions.
- VOLATILE returns an empty strategy dict — callers must check allow_trading
  before attempting to iterate strategies.
"""

from __future__ import annotations

import copy
from typing import Dict, Optional

import structlog

from src.trading.regime.regime_classifier import MarketRegime

logger = structlog.get_logger(__name__)


class StrategyRouter:
    """
    Routes a detected MarketRegime to an allowed strategy configuration.

    This class is effectively stateless when used without a config file.
    Instantiate once and reuse across all calls.

    Usage::

        router = StrategyRouter()
        config = router.get_strategy_config(regime)

        if not config["allow_trading"]:
            return  # volatile halt

        for strategy_name, weight in config["strategies"].items():
            ...  # run strategy, apply weight

    Usage with YAML override::

        router = StrategyRouter(config_path="/abs/path/config/regime.yaml")

    Configuration contract
    ----------------------
    The returned dict always contains:
        strategies       Dict[str, float]   non-empty unless allow_trading=False
        signal_threshold float              in [0.0, 1.0]
        allow_trading    bool
        reason           str

    Args:
        config_path : str, optional
            Path to a YAML file with a ``strategy_router`` section.
            Any regime sub-key present in the file overrides the class-level
            default for that regime.  Omitted regimes retain their defaults.
            When None (default), the class-level ``_ROUTING_TABLE`` is used
            unchanged — fully backward-compatible.
    """

    # ------------------------------------------------------------------
    # Routing table — defined as class-level constants so they can be
    # introspected in tests without instantiation.
    # ------------------------------------------------------------------

    #: Strategies and weights for each regime.
    #: Weights within each regime sum to 1.0.
    _ROUTING_TABLE: Dict[MarketRegime, Dict] = {
        MarketRegime.TRENDING: {
            "strategies": {
                "momentum": 0.40,
                "breakout": 0.35,
                "trend_following": 0.25,
            },
            "blocked": frozenset({"value_area", "mean_reversion", "ml_reversal"}),
            "signal_threshold": 0.60,
            "allow_trading": True,
            "reason": "Trending regime: momentum and breakout strategies selected.",
        },
        MarketRegime.RANGING: {
            "strategies": {
                "value_area": 0.45,
                "mean_reversion": 0.35,
                "ml_reversal": 0.20,
            },
            "blocked": frozenset({"momentum", "breakout"}),
            "signal_threshold": 0.60,
            "allow_trading": True,
            "reason": "Ranging regime: mean-reversion and value-area strategies selected.",
        },
        MarketRegime.VOLATILE: {
            "strategies": {},
            "blocked": frozenset(
                {"momentum", "breakout", "value_area", "mean_reversion", "ml_reversal",
                 "trend_following"}
            ),
            "signal_threshold": 1.0,  # unreachable — trading halted
            "allow_trading": False,
            "reason": "Volatile regime: all strategies blocked. No new entries.",
        },
        MarketRegime.UNKNOWN: {
            "strategies": {
                "momentum": 0.20,
                "breakout": 0.20,
                "value_area": 0.20,
                "mean_reversion": 0.20,
                "ml_reversal": 0.20,
            },
            "blocked": frozenset(),
            "signal_threshold": 0.75,
            "allow_trading": True,
            "reason": (
                "Unknown regime: all strategies run at equal weight. "
                "Extra-selective threshold (0.75) applied."
            ),
        },
    }

    def __init__(self, config_path: Optional[str] = None) -> None:
        """
        Initialise the router.

        When ``config_path`` is None the class-level ``_ROUTING_TABLE`` is used
        as-is (no copy needed — read-only usage).  When a config path is
        provided, a deep copy of the routing table is made per-instance so that
        YAML overrides do not leak across instances or affect the class constant.

        Args:
            config_path: Absolute or relative path to a YAML file containing a
                         ``strategy_router`` section.  None means use defaults.
        """
        # Per-instance routing table — deep-copied only when we need to mutate.
        self._routing_table: Dict[MarketRegime, Dict] = self._ROUTING_TABLE

        if config_path is not None:
            self._routing_table = copy.deepcopy(self._ROUTING_TABLE)
            self._load_config(config_path)

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_config(self, path: str) -> None:
        """
        Read the ``strategy_router`` section from a YAML file and apply
        overrides to ``self._routing_table``.

        Supported YAML structure (all keys optional)::

            strategy_router:
              trending:
                strategies:
                  momentum: 0.50
                  breakout: 0.30
                  trend_following: 0.20
                signal_threshold: 0.55
              ranging:
                strategies:
                  value_area: 0.50
                  mean_reversion: 0.30
                  ml_reversal: 0.20
                signal_threshold: 0.65
              volatile:
                allow_trading: false
              unknown:
                strategies:
                  momentum: 0.20
                  breakout: 0.20
                  trend_following: 0.20
                  value_area: 0.20
                  mean_reversion: 0.20
                signal_threshold: 0.80

        Constraints enforced here:
            - ``allow_trading`` is always False for volatile regardless of YAML.
            - ``strategies`` weights are stored as-is; callers may normalise.
            - Unrecognised regime keys or strategy keys are silently ignored.
            - Missing sub-keys within a regime leave that attribute unchanged.

        Args:
            path: Path to the YAML file.

        Returns:
            None.  Modifications are applied to ``self._routing_table``.

        Edge cases:
            - File not found → warning logged, routing table unchanged.
            - YAML parse error → warning logged, routing table unchanged.
        """
        import yaml

        _REGIME_NAME_MAP: Dict[str, MarketRegime] = {
            "trending": MarketRegime.TRENDING,
            "ranging": MarketRegime.RANGING,
            "volatile": MarketRegime.VOLATILE,
            "unknown": MarketRegime.UNKNOWN,
        }

        try:
            with open(path) as fh:
                raw = yaml.safe_load(fh)
        except FileNotFoundError:
            logger.warning(
                "strategy_router.config_not_found",
                path=path,
                message="Falling back to class-level routing table defaults.",
            )
            return
        except yaml.YAMLError as exc:
            logger.warning(
                "strategy_router.config_parse_error",
                path=path,
                error=str(exc),
                message="Falling back to class-level routing table defaults.",
            )
            return

        section: Dict = (raw or {}).get("strategy_router", {})
        if not section:
            logger.debug("strategy_router.config_empty_section", path=path)
            return

        applied: Dict[str, object] = {}

        for regime_key, regime_cfg in section.items():
            regime = _REGIME_NAME_MAP.get(regime_key)
            if regime is None:
                logger.debug(
                    "strategy_router.config_unknown_regime_key",
                    key=regime_key,
                )
                continue

            if not isinstance(regime_cfg, dict):
                continue

            entry = self._routing_table[regime]

            if "strategies" in regime_cfg and isinstance(regime_cfg["strategies"], dict):
                entry["strategies"] = {
                    str(k): float(v)
                    for k, v in regime_cfg["strategies"].items()
                }
                applied[f"{regime_key}.strategies"] = entry["strategies"]

            if "signal_threshold" in regime_cfg:
                entry["signal_threshold"] = float(regime_cfg["signal_threshold"])
                applied[f"{regime_key}.signal_threshold"] = entry["signal_threshold"]

            if "allow_trading" in regime_cfg and regime != MarketRegime.VOLATILE:
                # VOLATILE allow_trading is always False — cannot be overridden
                # to True via config because that would bypass the halt logic.
                entry["allow_trading"] = bool(regime_cfg["allow_trading"])
                applied[f"{regime_key}.allow_trading"] = entry["allow_trading"]

        logger.info(
            "strategy_router.config_loaded",
            path=path,
            overrides=list(applied.keys()),
        )

    def get_strategy_config(self, regime: MarketRegime) -> Dict:
        """
        Return the strategy configuration for a given MarketRegime.

        Args:
            regime: The classified market regime.  Must be one of the four
                    MarketRegime enum members.  Unrecognised values fall back
                    to UNKNOWN routing.

        Returns:
            Dict with keys:
                strategies       Dict[str, float]  — {name: weight}.
                                 Empty dict when allow_trading=False.
                signal_threshold float             — minimum |score| threshold.
                allow_trading    bool              — False halts trading.
                reason           str               — log-friendly explanation.

        Edge cases:
            - If regime is not in the routing table (future enum additions),
              UNKNOWN routing is returned and a warning is logged.
            - Returned dict is a shallow copy of the routing entry; mutating it
              does NOT affect the instance routing table.
        """
        entry = self._routing_table.get(regime)

        if entry is None:
            logger.warning(
                "strategy_router.unknown_regime_value",
                regime=str(regime),
                fallback="UNKNOWN",
            )
            entry = self._routing_table[MarketRegime.UNKNOWN]

        config = {
            "strategies": dict(entry["strategies"]),
            "signal_threshold": entry["signal_threshold"],
            "allow_trading": entry["allow_trading"],
            "reason": entry["reason"],
        }

        logger.debug(
            "strategy_router.routed",
            regime=regime.value if hasattr(regime, "value") else str(regime),
            allow_trading=config["allow_trading"],
            strategies=list(config["strategies"].keys()),
            signal_threshold=config["signal_threshold"],
        )

        return config

    def get_blocked_strategies(self, regime: MarketRegime) -> frozenset:
        """
        Return the set of strategy names explicitly blocked for a regime.

        Args:
            regime: The classified market regime.

        Returns:
            frozenset of blocked strategy name strings.  Empty frozenset if
            regime not in routing table.

        Useful for logging and test assertions.
        """
        entry = self._routing_table.get(regime, {})
        return entry.get("blocked", frozenset())
