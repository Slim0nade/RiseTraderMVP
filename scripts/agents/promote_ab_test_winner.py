#!/usr/bin/env python3
"""
Promote the winner of an A/B test experiment.

Marks the experiment as completed and sets the winning variant as the
default configuration for its agent type.

Usage:
    python3 scripts/agents/promote_ab_test_winner.py --experiment-id <UUID>
    python3 scripts/agents/promote_ab_test_winner.py --experiment-id <UUID> --force
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


async def main():
    parser = argparse.ArgumentParser(
        description="Promote the winner of an A/B test experiment"
    )
    parser.add_argument(
        "--experiment-id",
        type=str,
        required=True,
        help="Experiment UUID to promote winner for",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )

    args = parser.parse_args()

    try:
        exp_id = UUID(args.experiment_id)
    except ValueError:
        print(f"Error: Invalid UUID format: {args.experiment_id}")
        sys.exit(1)

    db = initialize_database()

    try:
        # First show current results
        async with db.get_session() as session:
            service = ABTestService(session)

            try:
                results = await service.get_experiment_results(exp_id)
            except ValueError as e:
                print(f"Error: {e}")
                sys.exit(1)

        print(f"""
A/B Test Promotion
==================
Experiment:  {results['experiment_name']}
ID:          {results['experiment_id']}
Status:      {results['status']}

Variants:""")
        for v in results["variants"]:
            pm = v["performance_metrics"]
            mean_ret = pm.get("mean_return", 0) if pm else 0
            trades = v["result_count"]
            print(f"  {v['variant_name']}: {trades} trades, mean return {mean_ret:.4f}")

        stats = results["statistics"]
        if stats["winner"]:
            print(f"\nStatistical winner: {stats['winner']} (p={stats['p_value']:.6f})")
        elif stats["p_value"] is not None:
            print(f"\nNo statistically significant winner (p={stats['p_value']:.6f})")
        else:
            print("\nInsufficient data for statistical test")

        # Confirmation
        if not args.force:
            confirm = input("\nPromote winner and close experiment? [y/N]: ").strip().lower()
            if confirm != "y":
                print("Cancelled.")
                return

        # Promote
        async with db.get_session() as session:
            service = ABTestService(session)
            promotion = await service.promote_winner(exp_id)

        print(f"""
Promotion Complete
==================
Winner:       {promotion['winner_name']}
Variant ID:   {promotion['winner_variant_id']}
Mean Return:  {promotion['mean_return']:.4f}
Status:       {promotion['status']}

The winning variant has been set as the default configuration.
All experiment variants have been deactivated.
""")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
