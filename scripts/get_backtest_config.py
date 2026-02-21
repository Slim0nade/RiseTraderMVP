#!/usr/bin/env python3
"""
Get backtest configuration details.
"""

import sys
import asyncio
from pathlib import Path
from uuid import UUID
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import os

# Database URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/risetrader"
)


async def get_config(run_id: str):
    """Get backtest configuration."""

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            run_uuid = UUID(run_id)

            # Get configuration
            result = await session.execute(
                text("""
                    SELECT
                        bc.name,
                        bc.symbol,
                        bc.start_date,
                        bc.end_date,
                        bc.initial_capital,
                        bc.execution_mode,
                        bc.agent_config_ref,
                        bc.allow_short_selling,
                        bc.slippage_pct,
                        bc.commission_pct,
                        bc.max_leverage,
                        bc.config_params,
                        br.candles_processed,
                        br.agent_decisions_count,
                        br.total_trades,
                        br.status
                    FROM backtest_runs br
                    JOIN backtest_configurations bc ON br.config_id = bc.id
                    WHERE br.id = :run_id
                """),
                {"run_id": run_uuid}
            )
            row = result.fetchone()

            if not row:
                print(f"❌ Backtest run {run_id} not found")
                return

            (name, symbol, start_date, end_date, initial_capital,
             execution_mode, agent_config_ref, allow_short, slippage_pct,
             commission_pct, max_leverage, config_params, candles, decisions,
             trades, status) = row

            print(f"\n" + "="*80)
            print(f"📋 BACKTEST CONFIGURATION")
            print(f"="*80)
            print(f"\n🏷️  Name: {name}")
            print(f"📊 Symbol: {symbol}")
            print(f"📅 Date Range: {start_date} → {end_date}")
            print(f"💰 Initial Capital: ${initial_capital}")
            print(f"🎯 Execution Mode: {execution_mode}")
            print(f"🤖 Agent Config: {agent_config_ref or 'N/A'}")
            print(f"📉 Allow Short Selling: {allow_short}")
            print(f"📊 Slippage: {slippage_pct}%")
            print(f"💵 Commission: {commission_pct}%")
            print(f"⚡ Max Leverage: {max_leverage}x")

            print(f"\n📈 RESULTS")
            print(f"="*80)
            print(f"Status: {status}")
            print(f"Candles Processed: {candles}")
            print(f"Agent Decisions: {decisions}")
            print(f"Total Trades: {trades}")

            if config_params:
                print(f"\n⚙️  CONFIGURATION PARAMETERS")
                print(f"="*80)

                # Pretty print the JSON config
                if isinstance(config_params, str):
                    params = json.loads(config_params)
                else:
                    params = config_params

                print(json.dumps(params, indent=2))

            print(f"\n" + "="*80)
            print(f"\n📋 COPY-PASTE CONFIG (for API request):")
            print(f"="*80)

            copy_config = {
                "name": f"{name} (Copy)",
                "symbol": symbol,
                "start_date": start_date.isoformat() if hasattr(start_date, 'isoformat') else str(start_date),
                "end_date": end_date.isoformat() if hasattr(end_date, 'isoformat') else str(end_date),
                "initial_capital": float(initial_capital),
                "execution_mode": execution_mode,
                "agent_config_ref": agent_config_ref,
                "allow_short_selling": allow_short,
                "slippage_pct": float(slippage_pct),
                "commission_pct": float(commission_pct),
                "max_leverage": float(max_leverage),
                "config_params": params if config_params else {}
            }

            print(json.dumps(copy_config, indent=2))
            print(f"\n" + "="*80)

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python get_backtest_config.py <run_id>")
        print("Example: python get_backtest_config.py be6391b0-e2e3-431a-983d-54826991a220")
        sys.exit(1)

    run_id = sys.argv[1]
    asyncio.run(get_config(run_id))
