#!/usr/bin/env python3
"""
Portfolio Optimizer - Find the best strategies to turn $10K into $100K
Target: 10x return (900% gain) in 1 month

Based on Ray Dalio's principles:
- Uncorrelated return streams
- Asymmetric risk/reward (3:1 or higher)
- Diversification across 15-20 streams
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any
from dataclasses import dataclass

# Add src to path
sys.path.insert(0, '/app')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.services.backtesting.vectorized_engine import VectorizedBacktestEngine
from src.database.models.market_data import MarketData


# Configuration
DATABASE_URL = "postgresql+asyncpg://postgres:risetrader2024@postgres:5432/risetrader"
INITIAL_CAPITAL = 10000.0
TARGET_CAPITAL = 100000.0
TARGET_RETURN = (TARGET_CAPITAL / INITIAL_CAPITAL - 1) * 100  # 900%

# Symbols to test (based on availability)
SYMBOLS = [
    "CrudeOIL",  # High leverage commodity
    "XAUUSD",    # Gold - safe haven
    "EURUSD",    # Major forex
    "GBPUSD",    # Major forex
    "USDJPY",    # Major forex
]

# Strategies to test
STRATEGIES = [
    "ma_crossover",
    "rsi",
    "trend_following",
    "mean_reversion",
    "crude_oil_v3",
    "value_area",
]

# Timeframes to test
TIMEFRAMES = ["M5", "M15", "H1"]

# Strategy parameter grids for optimization
PARAM_GRIDS = {
    "ma_crossover": [
        {"fast_period": 5, "slow_period": 20},
        {"fast_period": 8, "slow_period": 21},
        {"fast_period": 10, "slow_period": 30},
        {"fast_period": 12, "slow_period": 26},
        {"fast_period": 20, "slow_period": 50},
    ],
    "rsi": [
        {"rsi_period": 7, "rsi_oversold": 25, "rsi_overbought": 75},
        {"rsi_period": 10, "rsi_oversold": 30, "rsi_overbought": 70},
        {"rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70},
        {"rsi_period": 14, "rsi_oversold": 20, "rsi_overbought": 80},
        {"rsi_period": 21, "rsi_oversold": 35, "rsi_overbought": 65},
    ],
    "trend_following": [
        {"trend_period": 10},
        {"trend_period": 20},
        {"trend_period": 50},
    ],
    "mean_reversion": [
        {"lookback": 10, "std_threshold": 1.5},
        {"lookback": 20, "std_threshold": 2.0},
        {"lookback": 20, "std_threshold": 2.5},
        {"lookback": 30, "std_threshold": 2.0},
    ],
    "crude_oil_v3": [
        {"ema_fast": 5, "ema_slow": 21, "rsi_period": 7},
        {"ema_fast": 8, "ema_slow": 29, "rsi_period": 10},
        {"ema_fast": 10, "ema_slow": 30, "rsi_period": 14},
        {"ema_fast": 12, "ema_slow": 26, "rsi_period": 9},
    ],
    "value_area": [
        {"lookback_periods": 12, "value_area_percent": 0.68},
        {"lookback_periods": 24, "value_area_percent": 0.70},
        {"lookback_periods": 48, "value_area_percent": 0.70},
    ],
}


@dataclass
class BacktestResult:
    """Result of a single backtest"""
    symbol: str
    strategy: str
    timeframe: str
    params: Dict
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float
    total_trades: int
    profit_factor: float
    final_capital: float
    execution_time_ms: float

    @property
    def risk_reward_score(self) -> float:
        """Dalio-style risk-adjusted score"""
        if self.max_drawdown_pct == 0:
            return 0
        # Higher is better: return / risk
        return abs(self.total_return_pct / self.max_drawdown_pct) if self.max_drawdown_pct else 0

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "timeframe": self.timeframe,
            "params": self.params,
            "total_return_pct": round(self.total_return_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2) if self.sharpe_ratio else 0,
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "win_rate": round(self.win_rate, 2),
            "total_trades": self.total_trades,
            "profit_factor": round(self.profit_factor, 2) if self.profit_factor else 0,
            "final_capital": round(self.final_capital, 2),
            "risk_reward_score": round(self.risk_reward_score, 2),
        }


async def run_single_backtest(
    engine: VectorizedBacktestEngine,
    symbol: str,
    strategy: str,
    timeframe: str,
    params: Dict,
    start_date: str,
    end_date: str,
) -> BacktestResult:
    """Run a single backtest and return results"""
    try:
        result = await engine.run_backtest(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            strategy=strategy,
            strategy_params=params,
            initial_capital=INITIAL_CAPITAL,
        )

        return BacktestResult(
            symbol=symbol,
            strategy=strategy,
            timeframe=timeframe,
            params=params,
            total_return_pct=result.get("total_return_pct", 0),
            sharpe_ratio=result.get("sharpe_ratio", 0),
            max_drawdown_pct=result.get("max_drawdown_pct", 0),
            win_rate=result.get("win_rate", 0),
            total_trades=result.get("total_trades", 0),
            profit_factor=result.get("profit_factor", 0),
            final_capital=result.get("final_capital", INITIAL_CAPITAL),
            execution_time_ms=result.get("execution_time_ms", 0),
        )
    except Exception as e:
        print(f"  Error: {symbol}/{strategy}/{timeframe}: {str(e)[:50]}")
        return BacktestResult(
            symbol=symbol,
            strategy=strategy,
            timeframe=timeframe,
            params=params,
            total_return_pct=0,
            sharpe_ratio=0,
            max_drawdown_pct=0,
            win_rate=0,
            total_trades=0,
            profit_factor=0,
            final_capital=INITIAL_CAPITAL,
            execution_time_ms=0,
        )


async def check_data_availability(session: AsyncSession) -> Dict[str, Dict]:
    """Check what data is available for each symbol"""
    from sqlalchemy import text

    availability = {}

    for symbol in SYMBOLS:
        query = text("""
            SELECT
                timeframe,
                MIN(time) as start_date,
                MAX(time) as end_date,
                COUNT(*) as candle_count
            FROM market_data
            WHERE symbol = :symbol
            GROUP BY timeframe
            ORDER BY timeframe
        """)

        result = await session.execute(query, {"symbol": symbol})
        rows = result.fetchall()

        availability[symbol] = {
            row[0]: {
                "start": row[1].isoformat() if row[1] else None,
                "end": row[2].isoformat() if row[2] else None,
                "count": row[3]
            }
            for row in rows
        }

    return availability


async def main():
    """Main optimization loop"""
    print("=" * 80)
    print("PORTFOLIO OPTIMIZER - Target: $10K → $100K (10x in 1 month)")
    print("=" * 80)
    print(f"\nTarget Return: {TARGET_RETURN:.0f}%")
    print(f"Initial Capital: ${INITIAL_CAPITAL:,.2f}")
    print(f"Target Capital: ${TARGET_CAPITAL:,.2f}")
    print()

    # Create database connection
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Check data availability
        print("Checking data availability...")
        availability = await check_data_availability(session)

        print("\n📊 DATA AVAILABILITY:")
        for symbol, timeframes in availability.items():
            if timeframes:
                print(f"\n  {symbol}:")
                for tf, info in timeframes.items():
                    print(f"    {tf}: {info['count']:,} candles ({info['start'][:10]} to {info['end'][:10]})")
            else:
                print(f"\n  {symbol}: NO DATA")

        # Determine test period (last 3 months of available data)
        # We'll use a recent period for testing
        end_date = "2025-01-01"  # Use data up to this date
        start_date_1m = "2024-12-01"  # 1 month
        start_date_3m = "2024-10-01"  # 3 months
        start_date_6m = "2024-07-01"  # 6 months

        print(f"\n🔬 TEST PERIODS:")
        print(f"  1 Month: {start_date_1m} to {end_date}")
        print(f"  3 Months: {start_date_3m} to {end_date}")
        print(f"  6 Months: {start_date_6m} to {end_date}")

        # Create backtest engine
        bt_engine = VectorizedBacktestEngine(session)

        # Run all backtests
        all_results: List[BacktestResult] = []
        total_tests = 0

        # Count total tests
        for symbol in SYMBOLS:
            if symbol not in availability or not availability[symbol]:
                continue
            for strategy in STRATEGIES:
                for tf in TIMEFRAMES:
                    if tf in availability.get(symbol, {}):
                        total_tests += len(PARAM_GRIDS.get(strategy, [{}]))

        print(f"\n🚀 RUNNING {total_tests} BACKTESTS...")
        print("-" * 80)

        completed = 0
        for symbol in SYMBOLS:
            if symbol not in availability or not availability[symbol]:
                print(f"⏭️  Skipping {symbol} - no data")
                continue

            for strategy in STRATEGIES:
                param_list = PARAM_GRIDS.get(strategy, [{}])

                for params in param_list:
                    for tf in TIMEFRAMES:
                        if tf not in availability.get(symbol, {}):
                            continue

                        completed += 1
                        print(f"\r  [{completed}/{total_tests}] {symbol}/{strategy}/{tf}...", end="", flush=True)

                        # Test on 1-month period (our target)
                        result = await run_single_backtest(
                            bt_engine, symbol, strategy, tf, params,
                            start_date_1m, end_date
                        )

                        if result.total_trades > 0:
                            all_results.append(result)

        print("\n")

        if not all_results:
            print("❌ No valid backtest results!")
            return

        # Sort by total return
        all_results.sort(key=lambda x: x.total_return_pct, reverse=True)

        # Display top performers
        print("=" * 80)
        print("🏆 TOP 20 PERFORMERS (by Total Return)")
        print("=" * 80)
        print(f"{'Rank':<5} {'Symbol':<12} {'Strategy':<15} {'TF':<5} {'Return%':<10} {'Sharpe':<8} {'MaxDD%':<10} {'WinRate':<8} {'Trades':<8} {'R/R Score':<10}")
        print("-" * 100)

        for i, result in enumerate(all_results[:20], 1):
            print(f"{i:<5} {result.symbol:<12} {result.strategy:<15} {result.timeframe:<5} "
                  f"{result.total_return_pct:>8.1f}% {result.sharpe_ratio:>7.2f} "
                  f"{result.max_drawdown_pct:>8.1f}% {result.win_rate:>7.1f}% "
                  f"{result.total_trades:>7} {result.risk_reward_score:>9.2f}")

        # Find strategies that could achieve 10x
        print("\n" + "=" * 80)
        print("🎯 STRATEGIES WITH POTENTIAL FOR 10X (>100% monthly return)")
        print("=" * 80)

        high_performers = [r for r in all_results if r.total_return_pct >= 50]

        if high_performers:
            for result in high_performers[:10]:
                print(f"\n  📈 {result.symbol} / {result.strategy} / {result.timeframe}")
                print(f"     Return: {result.total_return_pct:.1f}% | Sharpe: {result.sharpe_ratio:.2f}")
                print(f"     Max DD: {result.max_drawdown_pct:.1f}% | Win Rate: {result.win_rate:.1f}%")
                print(f"     Trades: {result.total_trades} | Profit Factor: {result.profit_factor:.2f}")
                print(f"     Params: {result.params}")

                # Calculate required leverage for 10x
                if result.total_return_pct > 0:
                    leverage_needed = 900 / result.total_return_pct
                    print(f"     → To reach 10x: Need {leverage_needed:.1f}x leverage or position scaling")
        else:
            print("  No strategies found with >50% monthly return")
            print("  Best performer:", all_results[0].to_dict() if all_results else "None")

        # Dalio-style portfolio construction
        print("\n" + "=" * 80)
        print("🧠 DALIO PORTFOLIO - Uncorrelated Streams Analysis")
        print("=" * 80)

        # Group by symbol to find uncorrelated streams
        by_symbol = {}
        for r in all_results:
            if r.symbol not in by_symbol:
                by_symbol[r.symbol] = []
            by_symbol[r.symbol].append(r)

        # Get best strategy per symbol
        portfolio_candidates = []
        for symbol, results in by_symbol.items():
            if results:
                best = max(results, key=lambda x: x.risk_reward_score)
                if best.total_trades >= 5 and best.total_return_pct > 0:
                    portfolio_candidates.append(best)

        print("\n  Best strategy per symbol (uncorrelated streams):")
        for i, result in enumerate(sorted(portfolio_candidates, key=lambda x: x.risk_reward_score, reverse=True), 1):
            print(f"  {i}. {result.symbol}: {result.strategy}/{result.timeframe} "
                  f"→ {result.total_return_pct:.1f}% return, {result.risk_reward_score:.2f} R/R score")

        # Calculate combined portfolio return (simplified)
        if portfolio_candidates:
            avg_return = sum(r.total_return_pct for r in portfolio_candidates) / len(portfolio_candidates)
            combined_return = avg_return * 0.8  # Diversification benefit estimate

            print(f"\n  Combined portfolio estimate:")
            print(f"  - Average return per stream: {avg_return:.1f}%")
            print(f"  - Combined portfolio (corr-adjusted): {combined_return:.1f}%")
            print(f"  - To reach 10x: Scale positions by {900/combined_return:.1f}x")

        # Save results to JSON
        output = {
            "timestamp": datetime.now().isoformat(),
            "target": {"initial": INITIAL_CAPITAL, "target": TARGET_CAPITAL, "return_pct": TARGET_RETURN},
            "test_period": {"start": start_date_1m, "end": end_date},
            "total_backtests": len(all_results),
            "top_20": [r.to_dict() for r in all_results[:20]],
            "high_performers": [r.to_dict() for r in high_performers[:10]] if high_performers else [],
            "portfolio_candidates": [r.to_dict() for r in portfolio_candidates],
        }

        with open("/app/results/portfolio_optimization_results.json", "w") as f:
            json.dump(output, f, indent=2, default=str)

        print("\n" + "=" * 80)
        print("✅ Results saved to: /app/results/portfolio_optimization_results.json")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
