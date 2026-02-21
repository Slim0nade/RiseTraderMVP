#!/usr/bin/env python3
"""
Mark a stuck backtest as completed.

This script updates the database to mark a backtest run as COMPLETED
when it has crashed or hung but has saved all intermediate data.
"""

import sys
import asyncio
from pathlib import Path
from datetime import datetime
from uuid import UUID

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update, text
import os

# Database URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/risetrader"
)


async def mark_complete(run_id: str):
    """Mark backtest as completed."""

    print(f"Connecting to database...")
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            run_uuid = UUID(run_id)

            # Get current run data
            result = await session.execute(
                text("""
                    SELECT status, candles_processed, agent_decisions_count, total_trades, start_time
                    FROM backtest_runs
                    WHERE id = :run_id
                """),
                {"run_id": run_uuid}
            )
            row = result.fetchone()

            if not row:
                print(f"❌ Backtest run {run_id} not found")
                return

            status, candles, decisions, trades, start_time = row

            print(f"\n📊 Current Backtest Status:")
            print(f"   Status: {status}")
            print(f"   Candles Processed: {candles}")
            print(f"   Agent Decisions: {decisions}")
            print(f"   Total Trades: {trades}")
            print(f"   Start Time: {start_time}")

            if status == "COMPLETED":
                print(f"\n✓ Backtest is already marked as COMPLETED")
                return

            # Get final snapshot for metrics
            result = await session.execute(
                text("""
                    SELECT total_value, unrealized_pnl, realized_pnl
                    FROM portfolio_snapshots
                    WHERE backtest_run_id = :run_id
                    ORDER BY timestamp DESC
                    LIMIT 1
                """),
                {"run_id": run_uuid}
            )
            snapshot = result.fetchone()

            if snapshot:
                final_capital, unrealized_pnl, realized_pnl = snapshot
                print(f"\n📈 Final Portfolio State:")
                print(f"   Final Capital: ${final_capital}")
                print(f"   Unrealized P&L: ${unrealized_pnl}")
                print(f"   Realized P&L: ${realized_pnl}")
            else:
                final_capital = 10000  # Default initial capital
                print(f"\n⚠️ No snapshots found, using default final capital")

            # Update to COMPLETED
            end_time = datetime.utcnow()

            update_data = {
                "status": "COMPLETED",
                "end_time": end_time,
                "final_capital": float(final_capital) if snapshot else None,
            }

            await session.execute(
                text("""
                    UPDATE backtest_runs
                    SET status = :status,
                        end_time = :end_time,
                        final_capital = :final_capital
                    WHERE id = :run_id
                """),
                {
                    "run_id": run_uuid,
                    "status": update_data["status"],
                    "end_time": update_data["end_time"],
                    "final_capital": update_data["final_capital"],
                }
            )

            await session.commit()

            print(f"\n✅ Successfully marked backtest as COMPLETED")
            print(f"   End Time: {end_time}")
            print(f"   Final Capital: ${final_capital}")
            print(f"\n🔄 Refresh your browser to see the updated status!")

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            await session.rollback()
        finally:
            await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python mark_backtest_complete.py <run_id>")
        print("Example: python mark_backtest_complete.py be6391b0-e2e3-431a-983d-54826991a220")
        sys.exit(1)

    run_id = sys.argv[1]
    asyncio.run(mark_complete(run_id))
