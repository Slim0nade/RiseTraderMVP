#!/usr/bin/env python3
"""
View results of an A/B test experiment.

Usage:
    python3 scripts/agents/view_ab_test_results.py --experiment-id <UUID>
    python3 scripts/agents/view_ab_test_results.py --list          # List all active experiments
"""

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.config import initialize_database
from src.services.ab_test_service import ABTestService


async def list_experiments(db):
    """List all active A/B test experiments."""
    async with db.get_session() as session:
        service = ABTestService(session)
        experiments = await service.get_active_experiments()

    if not experiments:
        print("No active A/B test experiments found.")
        return

    print(f"""
Active A/B Test Experiments
===========================
""")
    for exp in experiments:
        print(f"  ID:       {exp.experiment_id}")
        print(f"  Name:     {exp.name}")
        print(f"  Variants: {exp.variant_count}")
        print(f"  Results:  {exp.total_results} total")
        if exp.created_at:
            print(f"  Created:  {exp.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print()


async def view_results(db, experiment_id: UUID):
    """View detailed results for a specific experiment."""
    async with db.get_session() as session:
        service = ABTestService(session)

        try:
            results = await service.get_experiment_results(experiment_id)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    stats = results["statistics"]

    print(f"""
A/B Test Results
================
Experiment:  {results['experiment_name']}
ID:          {results['experiment_id']}
Status:      {results['status']}
""")

    print("Variants:")
    print("-" * 80)
    for v in results["variants"]:
        pm = v["performance_metrics"]
        print(f"  {v['variant_name']}")
        print(f"    Traffic:     {v['traffic_pct']}%")
        print(f"    Trades:      {v['result_count']}")
        if pm:
            print(f"    Mean Return: {pm.get('mean_return', 0):.4f}")
            print(f"    Std Return:  {pm.get('std_return', 0):.4f}")
            print(f"    Win Rate:    {pm.get('win_rate', 0):.1%}")
            print(f"    Total P&L:   ${pm.get('total_pnl', 0):,.2f}")
            sharpe = pm.get("sharpe_ratio")
            if sharpe is not None:
                print(f"    Sharpe:      {sharpe:.3f}")
        print(f"    Default:     {v['is_default']}")
        print()

    print("Statistical Test:")
    print("-" * 80)
    if stats["t_statistic"] is not None:
        print(f"  T-statistic:      {stats['t_statistic']:.4f}")
        print(f"  P-value:          {stats['p_value']:.6f}")
        if stats["confidence_interval_95"]:
            ci = stats["confidence_interval_95"]
            print(f"  95% CI (diff):    [{ci[0]:.6f}, {ci[1]:.6f}]")
        print(f"  Significant:      {'YES' if stats['is_significant'] else 'NO'} (alpha=0.05)")
        if stats["winner"]:
            print(f"  Winner:           {stats['winner']}")
        else:
            print("  Winner:           No statistically significant winner")
    else:
        print("  Insufficient data for statistical test (need >= 2 results per variant)")

    print()


async def main():
    parser = argparse.ArgumentParser(
        description="View A/B test experiment results"
    )
    parser.add_argument(
        "--experiment-id",
        type=str,
        default=None,
        help="Experiment UUID to view results for",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all active experiments",
    )

    args = parser.parse_args()

    if not args.experiment_id and not args.list:
        parser.print_help()
        print("\nProvide --experiment-id <UUID> or --list")
        sys.exit(1)

    db = initialize_database()

    try:
        if args.list:
            await list_experiments(db)
        else:
            exp_id = UUID(args.experiment_id)
            await view_results(db, exp_id)
    except ValueError as e:
        print(f"Error: Invalid UUID format - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
