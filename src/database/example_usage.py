"""
Example usage of RiseTrader database layer.

Demonstrates how to use models, repositories, and async sessions.
"""
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

from config import get_database, initialize_database
from models import Forecast, MarketData, OpenPosition
from repositories import (
    ForecastsRepository,
    MarketDataRepository,
    PositionsRepository,
)


async def example_market_data_queries():
    """Example: Query market data."""
    print("\n=== Market Data Examples ===\n")

    # Initialize database
    db = initialize_database()

    async with db.get_session() as session:
        # Create repository
        market_data_repo = MarketDataRepository(session)

        # Example 1: Get latest tick
        print("1. Get latest tick for CrudeOIL:")
        latest = await market_data_repo.get_latest_tick(
            symbol="CrudeOIL", timeframe="1m"
        )
        if latest:
            print(f"   Time: {latest.time}")
            print(f"   Close: {latest.close}")
            print(f"   Volume: {latest.volume}")

        # Example 2: Get last 10 ticks
        print("\n2. Get last 10 ticks:")
        recent_ticks = await market_data_repo.get_latest_ticks(
            symbol="CrudeOIL", timeframe="1m", limit=10
        )
        print(f"   Retrieved {len(recent_ticks)} ticks")
        for tick in recent_ticks[:3]:
            print(f"   - {tick.time}: ${tick.close}")

        # Example 3: Get data for specific time range
        print("\n3. Get data for last 24 hours:")
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=24)
        range_data = await market_data_repo.get_by_timeframe_range(
            symbol="CrudeOIL",
            timeframe="1h",
            start_time=start_time,
            end_time=end_time,
        )
        print(f"   Retrieved {len(range_data)} hourly candles")

        # Example 4: Get OHLCV aggregates
        print("\n4. Get OHLCV aggregates:")
        aggregates = await market_data_repo.get_ohlcv_aggregates(
            symbol="CrudeOIL",
            start_time=start_time,
            end_time=end_time,
            timeframe="1m",
        )
        if aggregates:
            print(f"   Open: {aggregates['open']}")
            print(f"   High: {aggregates['high']}")
            print(f"   Low: {aggregates['low']}")
            print(f"   Close: {aggregates['close']}")
            print(f"   Volume: {aggregates['volume']}")

        # Example 5: Get available symbols
        print("\n5. Available symbols:")
        symbols = await market_data_repo.get_symbols(timeframe="1m")
        print(f"   Found {len(symbols)} symbols: {', '.join(symbols[:5])}")

        # Example 6: Count records
        print("\n6. Record count:")
        count = await market_data_repo.count_by_symbol_timeframe(
            symbol="CrudeOIL", timeframe="1m"
        )
        print(f"   CrudeOIL 1m records: {count:,}")


async def example_positions_queries():
    """Example: Query open positions."""
    print("\n=== Positions Examples ===\n")

    db = get_database()

    async with db.get_session() as session:
        positions_repo = PositionsRepository(session)

        # Example 1: Get all open positions
        print("1. All open positions:")
        positions = await positions_repo.get_open_positions()
        print(f"   Total positions: {len(positions)}")
        for pos in positions[:3]:
            print(
                f"   - {pos.symbol}: {pos.type} {pos.size} @ {pos.price} "
                f"(P&L: {pos.last_profit})"
            )

        # Example 2: Get position summary
        print("\n2. Position summary:")
        summary = await positions_repo.get_position_summary()
        print(f"   Total positions: {summary['total_positions']}")
        print(f"   Long positions: {summary['total_long']}")
        print(f"   Short positions: {summary['total_short']}")
        print(f"   Total P&L: ${summary['total_profit']:.2f}")
        print(f"   Active symbols: {', '.join(summary['symbols'][:5])}")

        # Example 3: Get positions by symbol
        print("\n3. Positions for CrudeOIL:")
        crude_positions = await positions_repo.get_positions_by_symbol("CrudeOIL")
        print(f"   Found {len(crude_positions)} positions")

        # Example 4: Total exposure
        print("\n4. Total exposure:")
        exposure = await positions_repo.get_total_exposure()
        print(f"   Total exposure: ${exposure:,.2f}")


async def example_forecasts_queries():
    """Example: Query ML forecasts."""
    print("\n=== Forecasts Examples ===\n")

    db = get_database()

    async with db.get_session() as session:
        forecasts_repo = ForecastsRepository(session)

        # Example 1: Get latest forecast
        print("1. Latest forecast for CrudeOIL (1h horizon):")
        latest = await forecasts_repo.get_latest_forecast(
            symbol="CrudeOIL", horizon="1h"
        )
        if latest:
            print(f"   Model: {latest.model_type} v{latest.model_version}")
            print(f"   Predicted: ${latest.predicted_price}")
            print(f"   Confidence: {latest.model_confidence}")
            print(f"   Target time: {latest.target_timestamp}")

        # Example 2: Get ensemble prediction
        print("\n2. Ensemble prediction:")
        target_time = datetime.utcnow() + timedelta(hours=1)
        ensemble = await forecasts_repo.get_ensemble_prediction(
            symbol="CrudeOIL", target_timestamp=target_time, horizon="1h"
        )
        if ensemble:
            print(f"   Ensemble price: ${ensemble['ensemble_prediction']:.2f}")
            print(f"   Models used: {ensemble['num_models']}")
            print(f"   Model types: {', '.join(ensemble['model_types'])}")

        # Example 3: Get forecast accuracy
        print("\n3. Model accuracy stats:")
        stats = await forecasts_repo.get_forecast_accuracy_stats(
            model_type="XGBoost", symbol="CrudeOIL", horizon="1h"
        )
        if stats:
            print(f"   Validated forecasts: {stats['total_validated']}")
            print(f"   MAE: {stats['mean_absolute_error']:.4f}")
            print(f"   MPE: {stats['mean_percentage_error']:.2f}%")

        # Example 4: Get unvalidated forecasts
        print("\n4. Unvalidated forecasts:")
        now = datetime.utcnow()
        unvalidated = await forecasts_repo.get_unvalidated_forecasts(
            symbol="CrudeOIL", before_time=now
        )
        print(f"   Found {len(unvalidated)} forecasts to validate")


async def example_create_operations():
    """Example: Create new records."""
    print("\n=== Create Operations Examples ===\n")

    db = get_database()

    async with db.get_session() as session:
        # Example 1: Create new market data tick
        print("1. Insert new market tick:")
        market_data_repo = MarketDataRepository(session)
        new_tick = await market_data_repo.create(
            {
                "time": datetime.utcnow(),
                "symbol": "EURUSD",
                "import_symbol": "EURUSD",
                "timeframe": "1m",
                "source": "API",
                "open": Decimal("1.0850"),
                "high": Decimal("1.0855"),
                "low": Decimal("1.0848"),
                "last": Decimal("1.0852"),
                "change": Decimal("0.0002"),
                "change_percent": Decimal("0.018"),
                "volume": 1000,
            }
        )
        print(f"   Created tick ID: {new_tick.id}")

        # Example 2: Bulk insert ticks
        print("\n2. Bulk insert ticks:")
        ticks_data = [
            {
                "time": datetime.utcnow() - timedelta(minutes=i),
                "symbol": "EURUSD",
                "import_symbol": "EURUSD",
                "timeframe": "1m",
                "source": "API",
                "open": Decimal(f"1.085{i}"),
                "high": Decimal(f"1.086{i}"),
                "low": Decimal(f"1.084{i}"),
                "last": Decimal(f"1.085{i}"),
                "change": Decimal("0.0001"),
                "change_percent": Decimal("0.009"),
                "volume": 500 + i * 10,
            }
            for i in range(10)
        ]
        count = await market_data_repo.bulk_insert_ticks(ticks_data)
        print(f"   Inserted {count} ticks")

        # Example 3: Create forecast
        print("\n3. Create ML forecast:")
        forecasts_repo = ForecastsRepository(session)
        forecast = await forecasts_repo.save_forecast(
            {
                "model_type": "XGBoost",
                "model_version": "v1.0",
                "symbol": "CrudeOIL",
                "forecast_horizon": "1h",
                "prediction_timestamp": datetime.utcnow(),
                "target_timestamp": datetime.utcnow() + timedelta(hours=1),
                "predicted_price": Decimal("73.45"),
                "confidence_lower": Decimal("72.90"),
                "confidence_upper": Decimal("74.00"),
                "confidence_level": Decimal("0.95"),
                "model_confidence": Decimal("0.87"),
            }
        )
        print(f"   Created forecast ID: {forecast.id}")


async def example_performance_metrics():
    """Example: Calculate performance metrics."""
    print("\n=== Performance Metrics Examples ===\n")

    db = get_database()

    async with db.get_session() as session:
        from repositories import TradingHistoryRepository

        history_repo = TradingHistoryRepository(session)

        # Example 1: Overall performance
        print("1. Overall performance metrics:")
        metrics = await history_repo.get_performance_metrics()
        print(f"   Total trades: {metrics['total_trades']}")
        print(f"   Win rate: {metrics['win_rate']:.2f}%")
        print(f"   Total profit: ${metrics['total_profit']:.2f}")
        print(f"   Average profit: ${metrics['average_profit']:.2f}")
        print(f"   Profit factor: {metrics['profit_factor']:.2f}")

        # Example 2: Performance by symbol
        print("\n2. Performance by symbol:")
        symbol_perf = await history_repo.get_symbol_performance()
        for perf in symbol_perf[:5]:
            print(
                f"   {perf['symbol']}: {perf['trades']} trades, "
                f"${perf['total_profit']:.2f} profit"
            )

        # Example 3: Daily P&L
        print("\n3. Last 7 days P&L:")
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)
        daily_pnl = await history_repo.get_daily_pnl(start_date, end_date)
        for day in daily_pnl[:5]:
            print(f"   {day['date']}: {day['trades']} trades, ${day['profit']:.2f}")


async def main():
    """Run all examples."""
    print("=" * 60)
    print("RiseTrader Database Layer Examples")
    print("=" * 60)

    try:
        # Initialize database connection
        initialize_database(echo=False)  # Set echo=True to see SQL queries

        # Run examples
        await example_market_data_queries()
        await example_positions_queries()
        await example_forecasts_queries()
        # await example_create_operations()  # Uncomment to test writes
        await example_performance_metrics()

        print("\n" + "=" * 60)
        print("Examples completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Close database connections
        db = get_database()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
