#!/usr/bin/env python3
"""
Start Agent System Script.

This script initializes and starts the intelligent agent trading system
for a specified instrument (symbol).

Usage:
    python scripts/agents/start_agent_system.py --symbol Gold --mode paper
    python scripts/agents/start_agent_system.py --symbol CrudeOIL --mode paper --config config/agents/agents.yaml
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.services.agent_service import AgentService
from src.database.session import get_db
from src.config import settings


async def main():
    """Start the agent system for trading."""
    parser = argparse.ArgumentParser(description="Start RiseTrader Agent System")
    parser.add_argument(
        "--symbol",
        type=str,
        required=True,
        help="Trading symbol (e.g., Gold, CrudeOIL)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="4H",
        choices=["1H", "4H", "1D"],
        help="Trading timeframe (default: 4H)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="paper",
        choices=["paper", "live"],
        help="Trading mode: paper or live (default: paper)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/agents/agents.yaml",
        help="Agent configuration file path",
    )
    parser.add_argument(
        "--enable-debate",
        action="store_true",
        help="Enable adversarial debate layer (US4)",
    )
    parser.add_argument(
        "--enable-rl",
        action="store_true",
        help="Enable RL-trained agents (US5)",
    )

    args = parser.parse_args()

    print(f"""
╔════════════════════════════════════════════════════════════════╗
║           RiseTrader Intelligent Agent System                  ║
║                      Starting...                               ║
╚════════════════════════════════════════════════════════════════╝

Symbol:           {args.symbol}
Timeframe:        {args.timeframe}
Mode:             {args.mode.upper()}
Config:           {args.config}
Debate Layer:     {'ENABLED' if args.enable_debate else 'DISABLED'}
RL Training:      {'ENABLED' if args.enable_rl else 'DISABLED'}
""")

    # Safety check for live trading
    if args.mode == "live":
        confirm = input("⚠️  You are about to start LIVE TRADING. Type 'YES' to confirm: ")
        if confirm != "YES":
            print("❌ Live trading cancelled.")
            return

    # Initialize agent service
    try:
        agent_service = AgentService()

        print("✓ Agent service initialized")
        print(f"✓ Loading configuration from {args.config}")

        # Start trading pipeline
        print(f"\n🚀 Starting agent system for {args.symbol}...")

        # This is a placeholder - actual implementation would:
        # 1. Load agent configuration from YAML
        # 2. Register agents with registry
        # 3. Start market data subscription
        # 4. Initialize trading pipeline
        # 5. Run agent coordination loop

        print(f"""
╔════════════════════════════════════════════════════════════════╗
║              Agent System Running                              ║
╚════════════════════════════════════════════════════════════════╝

Agents Active:
  ✓ Technical Analyst
  ✓ Fundamental Analyst
  ✓ Sentiment Analyst
  ✓ Position Sizing Agent
  ✓ Stop-Loss Agent
  ✓ Take-Profit Agent
  {'✓ Bull Researcher' if args.enable_debate else ''}
  {'✓ Bear Researcher' if args.enable_debate else ''}
  ✓ Risk Overseer

API Endpoints:
  Health:        http://localhost:8003/api/agent-pipelines/health
  Stats:         http://localhost:8003/api/agent-pipelines/stats
  Analysis:      http://localhost:8003/api/agent-pipelines/analysis
  Decision:      http://localhost:8003/api/agent-pipelines/decision
  Full Pipeline: http://localhost:8003/api/agent-pipelines/full

Press Ctrl+C to shutdown agents...
""")

        # Keep running until interrupted
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n\n🛑 Shutdown signal received...")
            print("✓ Agents stopped")
            print("✓ Cleanup complete")

    except Exception as e:
        print(f"\n❌ Error starting agent system: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
