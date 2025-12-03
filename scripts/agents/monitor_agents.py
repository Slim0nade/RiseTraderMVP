#!/usr/bin/env python3
"""
Monitor Agents Script.

This script provides real-time monitoring of agent system health,
performance metrics, and decision statistics.

Usage:
    python scripts/agents/monitor_agents.py
    python scripts/agents/monitor_agents.py --refresh 5
    python scripts/agents/monitor_agents.py --symbol Gold
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import httpx


API_BASE_URL = "http://localhost:8003/api/agent-pipelines"


async def fetch_agent_stats():
    """Fetch agent registry statistics."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE_URL}/stats")
        response.raise_for_status()
        return response.json()


async def fetch_agent_health():
    """Fetch agent health status."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE_URL}/health")
        response.raise_for_status()
        return response.json()


def format_timestamp(ts_str: str) -> str:
    """Format timestamp for display."""
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.strftime("%H:%M:%S")
    except:
        return ts_str


def display_dashboard(stats: dict, health: dict):
    """Display agent monitoring dashboard."""
    # Clear screen (cross-platform)
    print("\033[2J\033[H")  # ANSI escape codes

    print(f"""
╔════════════════════════════════════════════════════════════════╗
║        RiseTrader Agent System - Live Monitoring               ║
║        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                                      ║
╚════════════════════════════════════════════════════════════════╝

┌─ REGISTRY STATISTICS ──────────────────────────────────────────┐
│ Total Agents:     {stats.get('total_agents', 0):>3}                                         │
│ Active:           {health.get('healthy', 0):>3}                                         │
│ Inactive:         {health.get('unhealthy', 0):>3}                                         │
│ Overall Status:   {health.get('overall_status', 'unknown').upper():<10}                       │
└────────────────────────────────────────────────────────────────┘
""")

    # Display agents by type
    by_type = stats.get("by_type", {})
    if by_type:
        print("┌─ AGENTS BY TYPE ───────────────────────────────────────────────┐")
        for agent_type, count in by_type.items():
            print(f"│ {agent_type:<30} {count:>3}                         │")
        print("└────────────────────────────────────────────────────────────────┘")

    # Display agents by symbol
    by_symbol = stats.get("by_symbol", {})
    if by_symbol:
        print("\n┌─ AGENTS BY SYMBOL ─────────────────────────────────────────────┐")
        for symbol, count in by_symbol.items():
            print(f"│ {symbol:<30} {count:>3}                         │")
        print("└────────────────────────────────────────────────────────────────┘")

    # Display individual agent health
    agents = health.get("agents", [])
    if agents:
        print("\n┌─ AGENT HEALTH STATUS ──────────────────────────────────────────┐")
        print("│ Agent Name                     Symbol      State      Health   │")
        print("├────────────────────────────────────────────────────────────────┤")
        for agent in agents:
            name = agent.get("name", "Unknown")[:30]
            symbol = agent.get("symbol", "N/A")[:10]
            state = agent.get("state", "unknown")[:10]
            is_healthy = agent.get("is_healthy", False)
            health_status = "✓ HEALTHY" if is_healthy else "✗ UNHEALTHY"

            print(f"│ {name:<30} {symbol:<10} {state:<10} {health_status:<8} │")
        print("└────────────────────────────────────────────────────────────────┘")
    else:
        print("\n┌─ AGENT HEALTH STATUS ──────────────────────────────────────────┐")
        print("│ No agents currently registered                                 │")
        print("└────────────────────────────────────────────────────────────────┘")

    print("\n[Press Ctrl+C to exit]")


async def monitor_loop(refresh_seconds: int, filter_symbol: str = None):
    """Main monitoring loop."""
    try:
        while True:
            try:
                # Fetch data
                stats = await fetch_agent_stats()
                health = await fetch_agent_health()

                # Filter by symbol if specified
                if filter_symbol:
                    health["agents"] = [
                        agent for agent in health.get("agents", [])
                        if agent.get("symbol") == filter_symbol
                    ]

                # Display dashboard
                display_dashboard(stats, health)

            except httpx.HTTPError as e:
                print(f"\n❌ Error fetching agent data: {e}")
                print("Is the API server running on port 8003?")
                await asyncio.sleep(5)
                continue

            # Wait before next refresh
            await asyncio.sleep(refresh_seconds)

    except KeyboardInterrupt:
        print("\n\n✓ Monitoring stopped")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Monitor RiseTrader Agent System")
    parser.add_argument(
        "--refresh",
        type=int,
        default=3,
        help="Refresh interval in seconds (default: 3)",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Filter by symbol (e.g., Gold, CrudeOIL)",
    )

    args = parser.parse_args()

    print(f"""
╔════════════════════════════════════════════════════════════════╗
║           RiseTrader Agent Monitoring                          ║
║              Connecting to API...                              ║
╚════════════════════════════════════════════════════════════════╝

Refresh Interval: {args.refresh} seconds
Symbol Filter:    {args.symbol or 'All'}
API Endpoint:     {API_BASE_URL}
""")

    # Test connection
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE_URL}/health", timeout=2.0)
            response.raise_for_status()
            print("✓ Connection successful\n")
    except httpx.HTTPError as e:
        print(f"❌ Cannot connect to API: {e}")
        print("Make sure the API server is running:")
        print("  docker-compose up -d api")
        sys.exit(1)

    # Start monitoring
    await monitor_loop(args.refresh, args.symbol)


if __name__ == "__main__":
    asyncio.run(main())
