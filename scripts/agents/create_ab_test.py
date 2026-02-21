#!/usr/bin/env python3
"""
Create an A/B test experiment for comparing model configurations.

Usage:
    python3 scripts/agents/create_ab_test.py \
        --name "qwen3 vs deepseek" \
        --variants "qwen3:14b,deepseek-r1:14b" \
        --traffic "50,50"

    python3 scripts/agents/create_ab_test.py \
        --name "three-way LLM test" \
        --variants "qwen3:14b,deepseek-r1:14b,mistral:7b-instruct" \
        --traffic "40,30,30" \
        --agent-type "technical_analyst" \
        --description "Compare three LLMs for technical analysis accuracy"
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.config import initialize_database
from src.services.ab_test_service import ABTestService, VariantDefinition


async def main():
    parser = argparse.ArgumentParser(
        description="Create an A/B test experiment for RiseTrader agent models"
    )
    parser.add_argument(
        "--name",
        type=str,
        required=True,
        help="Experiment name (e.g., 'qwen3 vs deepseek')",
    )
    parser.add_argument(
        "--variants",
        type=str,
        required=True,
        help="Comma-separated variant names (e.g., 'qwen3:14b,deepseek-r1:14b')",
    )
    parser.add_argument(
        "--traffic",
        type=str,
        required=True,
        help="Comma-separated traffic percentages (must sum to 100, e.g., '50,50')",
    )
    parser.add_argument(
        "--agent-type",
        type=str,
        default="signal_generator",
        help="Agent type being tested (default: signal_generator)",
    )
    parser.add_argument(
        "--description",
        type=str,
        default="",
        help="Experiment description",
    )

    args = parser.parse_args()

    variant_names = [v.strip() for v in args.variants.split(",")]
    traffic_pcts = [int(t.strip()) for t in args.traffic.split(",")]

    if len(variant_names) != len(traffic_pcts):
        print(f"Error: Number of variants ({len(variant_names)}) does not match "
              f"number of traffic values ({len(traffic_pcts)})")
        sys.exit(1)

    if sum(traffic_pcts) != 100:
        print(f"Error: Traffic percentages must sum to 100, got {sum(traffic_pcts)}")
        sys.exit(1)

    variants = [
        VariantDefinition(
            name=name,
            traffic_pct=pct,
            config={"model": name},
        )
        for name, pct in zip(variant_names, traffic_pcts)
    ]

    db = initialize_database()

    try:
        async with db.get_session() as session:
            service = ABTestService(session)

            result = await service.create_experiment(
                name=args.name,
                description=args.description,
                variants=variants,
                agent_type=args.agent_type,
            )

        print(f"""
A/B Test Experiment Created
===========================
Experiment ID:  {result['experiment_id']}
Name:           {args.name}
Agent Type:     {args.agent_type}
Status:         {result['status']}

Variants:""")
        for i, (name, pct, vid) in enumerate(
            zip(variant_names, traffic_pcts, result["variant_ids"])
        ):
            print(f"  [{i}] {name} ({pct}% traffic) - ID: {vid}")

        print(f"""
Next steps:
  - Record results:  Use ABTestService.record_result()
  - View results:    python3 scripts/agents/view_ab_test_results.py --experiment-id {result['experiment_id']}
  - Promote winner:  python3 scripts/agents/promote_ab_test_winner.py --experiment-id {result['experiment_id']}
""")

    except Exception as e:
        print(f"Error creating experiment: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
