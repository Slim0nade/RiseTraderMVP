#!/usr/bin/env python3
"""
🚀 ZILLIONS OPTIMIZER 🚀

Run CrudeOIL V3 parameter optimization to find the best configuration.

Usage:
    # Quick test (500 combinations)
    python -m scripts.run_optimization --mode quick --symbol CrudeOIL --timeframe M5
    
    # Comprehensive search (50,000+ combinations)
    python -m scripts.run_optimization --mode comprehensive --workers 8
    
    # ZILLIONS mode (1M+ combinations, distributed)
    python -m scripts.run_optimization --mode zillions --workers 16 --samples 10000
"""
import argparse
import asyncio
import logging
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.backtesting.batch_optimizer import (
    BatchOptimizer,
    ParameterGrid,
    ExtendedParameterGrid,
    OptimizationResult,
    create_quick_grid,
    create_comprehensive_grid,
    create_zillions_grid,
    random_search_grid,
)
from src.services.backtesting.crude_oil_strategy import (
    CrudeOilStrategy,
    CrudeOilParams,
)
from src.services.backtesting.crude_oil_strategy_extended import (
    CrudeOilStrategyExtended,
    CrudeOilParamsExtended,
)
from src.services.backtesting.synthetic_engine import SyntheticEngine
from src.services.backtesting.data_replay_engine import MarketTick
from src.services.backtesting.portfolio_state import PortfolioState
from src.services.backtesting.trade_simulator import TradeSimulator
from src.services.backtesting.metrics_calculator import MetricsCalculator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class InMemoryBacktester:
    """
    Fast in-memory backtester for optimization.
    
    Runs without database for maximum speed during parameter search.
    """
    
    def __init__(
        self,
        historical_data: list,
        initial_capital: float = 10000.0,
        commission_rate: float = 0.001,
        slippage_rate: float = 0.0001,
    ):
        """
        Initialize backtester.
        
        Args:
            historical_data: List of OHLCV dictionaries
            initial_capital: Starting capital
            commission_rate: Commission as decimal (0.001 = 0.1%)
            slippage_rate: Slippage as decimal (0.0001 = 0.01%)
        """
        self.data = historical_data
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        
    def run(self, params: Dict[str, Any], use_extended: bool = False) -> OptimizationResult:
        """
        Run backtest with given parameters.
        
        Args:
            params: Strategy parameters
            use_extended: Use extended strategy with more indicators
            
        Returns:
            OptimizationResult with all metrics
        """
        # Initialize strategy
        if use_extended:
            strategy_params = CrudeOilParamsExtended(**{
                k: v for k, v in params.items() 
                if hasattr(CrudeOilParamsExtended, k)
            })
            strategy = CrudeOilStrategyExtended(params=strategy_params)
        else:
            strategy_params = CrudeOilParams(**{
                k: v for k, v in params.items() 
                if hasattr(CrudeOilParams, k)
            })
            strategy = CrudeOilStrategy(params=strategy_params)
        
        # Initialize tracking
        capital = self.initial_capital
        position_size = 0.0
        entry_price = 0.0
        trades = []
        equity_curve = [capital]
        
        # Process each candle
        for bar in self.data:
            tick = MarketTick(
                symbol=bar.get('symbol', 'CrudeOIL'),
                timestamp=bar['timestamp'],
                open=Decimal(str(bar['open'])),
                high=Decimal(str(bar['high'])),
                low=Decimal(str(bar['low'])),
                close=Decimal(str(bar['close'])),
                volume=bar.get('volume', 1000),
            )
            
            signal = strategy.process_tick(tick)
            
            # Execute signal
            if signal.action == 'buy' and position_size == 0:
                # Calculate position size based on risk
                risk_amount = capital * 0.01  # 1% risk
                if signal.stop_loss:
                    stop_distance = float(tick.close) - signal.stop_loss
                    if stop_distance > 0:
                        position_size = risk_amount / stop_distance
                    else:
                        position_size = capital * 0.1 / float(tick.close)
                else:
                    position_size = capital * 0.1 / float(tick.close)
                
                # Apply slippage
                entry_price = float(tick.close) * (1 + self.slippage_rate)
                commission = position_size * entry_price * self.commission_rate
                capital -= commission
                
            elif signal.action == 'sell' and position_size == 0:
                # Short position
                risk_amount = capital * 0.01
                if signal.stop_loss:
                    stop_distance = signal.stop_loss - float(tick.close)
                    if stop_distance > 0:
                        position_size = -risk_amount / stop_distance
                    else:
                        position_size = -capital * 0.1 / float(tick.close)
                else:
                    position_size = -capital * 0.1 / float(tick.close)
                
                entry_price = float(tick.close) * (1 - self.slippage_rate)
                commission = abs(position_size) * entry_price * self.commission_rate
                capital -= commission
                
            elif signal.action == 'close' and position_size != 0:
                # Close position
                if position_size > 0:
                    exit_price = float(tick.close) * (1 - self.slippage_rate)
                    pnl = position_size * (exit_price - entry_price)
                else:
                    exit_price = float(tick.close) * (1 + self.slippage_rate)
                    pnl = abs(position_size) * (entry_price - exit_price)
                
                commission = abs(position_size) * exit_price * self.commission_rate
                capital += pnl - commission
                
                trades.append({
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'pnl': pnl - commission,
                    'position_size': position_size,
                })
                
                position_size = 0.0
                entry_price = 0.0
            
            # Track equity
            if position_size != 0:
                current_price = float(tick.close)
                if position_size > 0:
                    unrealized = position_size * (current_price - entry_price)
                else:
                    unrealized = abs(position_size) * (entry_price - current_price)
                equity_curve.append(capital + unrealized)
            else:
                equity_curve.append(capital)
        
        # Calculate metrics
        return self._calculate_metrics(params, trades, equity_curve)
    
    def _calculate_metrics(
        self,
        params: Dict[str, Any],
        trades: list,
        equity_curve: list,
    ) -> OptimizationResult:
        """Calculate performance metrics."""
        import numpy as np
        
        # Basic counts
        total_trades = len(trades)
        if total_trades == 0:
            return OptimizationResult(
                params=params,
                total_trades=0,
                error="No trades generated"
            )
        
        # P&L analysis
        pnls = [t['pnl'] for t in trades]
        winning_trades = [p for p in pnls if p > 0]
        losing_trades = [p for p in pnls if p < 0]
        
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
        avg_win = np.mean(winning_trades) if winning_trades else 0
        avg_loss = np.mean(losing_trades) if losing_trades else 0
        
        # Profit factor
        gross_profit = sum(winning_trades) if winning_trades else 0
        gross_loss = abs(sum(losing_trades)) if losing_trades else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Returns
        equity_array = np.array(equity_curve)
        returns = np.diff(equity_array) / equity_array[:-1]
        
        total_return = (equity_curve[-1] - equity_curve[0]) / equity_curve[0]
        
        # Sharpe ratio (annualized)
        if len(returns) > 0 and np.std(returns) > 0:
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252 * 24)  # Hourly data
        else:
            sharpe = 0
        
        # Sortino ratio
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0 and np.std(downside_returns) > 0:
            sortino = np.mean(returns) / np.std(downside_returns) * np.sqrt(252 * 24)
        else:
            sortino = sharpe
        
        # Max drawdown
        peak = equity_array[0]
        max_dd = 0
        for value in equity_array:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
        
        # Calmar ratio
        calmar = total_return / max_dd if max_dd > 0 else 0
        
        return OptimizationResult(
            params=params,
            total_return=total_return,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown=max_dd,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=max(winning_trades) if winning_trades else 0,
            largest_loss=min(losing_trades) if losing_trades else 0,
            volatility=np.std(returns) if len(returns) > 0 else 0,
            candles_processed=len(self.data),
        )


def generate_sample_data(
    n_candles: int = 50000,
    start_price: float = 70.0,
    volatility: float = 0.02,
    trend: float = 0.0001,
) -> list:
    """
    Generate sample price data for testing.
    
    In production, this would be replaced with real database data.
    """
    import numpy as np
    from datetime import datetime, timedelta
    
    np.random.seed(42)
    
    data = []
    price = start_price
    timestamp = datetime(2023, 1, 1, 0, 0)
    
    for i in range(n_candles):
        # Random walk with drift
        change = np.random.normal(trend, volatility)
        price *= (1 + change)
        
        # Generate OHLC
        intrabar_vol = abs(np.random.normal(0, volatility * 0.5))
        high = price * (1 + intrabar_vol)
        low = price * (1 - intrabar_vol)
        open_price = price * (1 + np.random.normal(0, volatility * 0.3))
        
        data.append({
            'symbol': 'CrudeOIL',
            'timestamp': timestamp,
            'open': open_price,
            'high': max(high, open_price, price),
            'low': min(low, open_price, price),
            'close': price,
            'volume': int(np.random.uniform(1000, 5000)),
        })
        
        timestamp += timedelta(minutes=5)  # M5 timeframe
    
    return data


async def load_real_data(
    symbol: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
) -> list:
    """
    Load real data from database.
    
    Requires database connection to be configured.
    """
    from src.database.repositories.market_data_repository import MarketDataRepository
    from src.database.session import get_session
    
    async with get_session() as session:
        repo = MarketDataRepository(session)
        candles = await repo.get_by_timeframe_range(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_date,
            end_time=end_date,
        )
        
        return [
            {
                'symbol': c.symbol,
                'timestamp': c.time,
                'open': float(c.open),
                'high': float(c.high),
                'low': float(c.low),
                'close': float(c.last),
                'volume': int(c.volume or 0),
            }
            for c in candles
        ]


def main():
    parser = argparse.ArgumentParser(description='🚀 ZILLIONS Parameter Optimizer')
    
    parser.add_argument(
        '--mode',
        choices=['quick', 'comprehensive', 'zillions', 'custom'],
        default='quick',
        help='Optimization mode (quick=500, comprehensive=50K, zillions=1M+)'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        default=4,
        help='Number of parallel workers'
    )
    
    parser.add_argument(
        '--samples',
        type=int,
        default=None,
        help='Random sample size (for zillions mode)'
    )
    
    parser.add_argument(
        '--symbol',
        default='CrudeOIL',
        help='Trading symbol'
    )
    
    parser.add_argument(
        '--timeframe',
        default='M5',
        help='Timeframe (M1, M5, H1, etc.)'
    )
    
    parser.add_argument(
        '--data-source',
        choices=['sample', 'database'],
        default='sample',
        help='Data source (sample for testing, database for real data)'
    )
    
    parser.add_argument(
        '--candles',
        type=int,
        default=50000,
        help='Number of candles for sample data'
    )
    
    parser.add_argument(
        '--output-dir',
        default='optimization_results',
        help='Directory for results'
    )
    
    parser.add_argument(
        '--extended',
        action='store_true',
        help='Use extended strategy with more indicators'
    )
    
    args = parser.parse_args()
    
    # Banner
    print("=" * 80)
    print("🚀 ZILLIONS PARAMETER OPTIMIZER 🚀")
    print("=" * 80)
    print(f"Mode: {args.mode}")
    print(f"Workers: {args.workers}")
    print(f"Symbol: {args.symbol}")
    print(f"Timeframe: {args.timeframe}")
    print(f"Extended Strategy: {args.extended}")
    print("=" * 80)
    
    # Load data
    logger.info("Loading historical data...")
    
    if args.data_source == 'sample':
        data = generate_sample_data(n_candles=args.candles)
        logger.info(f"Generated {len(data)} sample candles")
    else:
        # Would need async context for database
        logger.error("Database mode not yet implemented in CLI. Use sample data.")
        return
    
    # Create backtester
    backtester = InMemoryBacktester(
        historical_data=data,
        initial_capital=10000.0,
    )
    
    # Create backtest function
    def backtest_func(params: Dict[str, Any]) -> OptimizationResult:
        return backtester.run(params, use_extended=args.extended)
    
    # Create parameter grid
    logger.info(f"Creating {args.mode} parameter grid...")
    
    if args.mode == 'quick':
        grid = create_quick_grid()
    elif args.mode == 'comprehensive':
        grid = create_comprehensive_grid()
    elif args.mode == 'zillions':
        grid = create_zillions_grid()
    else:
        grid = create_quick_grid()
    
    total_combos = grid.get_total_combinations()
    logger.info(f"Total parameter combinations: {total_combos:,}")
    
    # Random sampling for large grids
    if args.samples and args.samples < total_combos:
        logger.info(f"Using random sampling: {args.samples:,} samples")
        combinations = random_search_grid(grid, n_samples=args.samples)
    else:
        combinations = None  # Let optimizer generate all
    
    # Create optimizer
    optimizer = BatchOptimizer(
        parameter_grid=grid,
        backtest_function=backtest_func,
        max_workers=args.workers,
        results_dir=Path(args.output_dir),
    )
    
    # Progress tracking
    def progress_callback(completed: int, total: int):
        if completed % 50 == 0:
            pct = 100 * completed / total
            print(f"\rProgress: {completed:,}/{total:,} ({pct:.1f}%)", end='', flush=True)
    
    # Run optimization
    logger.info("Starting optimization...")
    start_time = datetime.now()
    
    results = optimizer.run(progress_callback=progress_callback)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    print()  # New line after progress
    
    logger.info(f"Optimization complete in {elapsed:.1f} seconds")
    logger.info(f"Tested {len(results):,} combinations")
    
    # Print report
    print("\n" + optimizer.generate_report())
    
    # Final summary
    best = results[0]
    print("\n" + "=" * 80)
    print("🎯 BEST CONFIGURATION FOUND! 🎯")
    print("=" * 80)
    print(f"Total Return: {best.total_return*100:.2f}%")
    print(f"Sharpe Ratio: {best.sharpe_ratio:.3f}")
    print(f"Win Rate: {best.win_rate*100:.1f}%")
    print(f"Profit Factor: {best.profit_factor:.2f}")
    print(f"Max Drawdown: {best.max_drawdown*100:.2f}%")
    print(f"Total Trades: {best.total_trades}")
    print(f"Composite Score: {best.composite_score():.4f}")
    print("=" * 80)
    print("🚀 Let's turn these parameters into ZILLIONS! 🚀")
    print("=" * 80)


if __name__ == '__main__':
    main()
