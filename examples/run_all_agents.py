"""
Example: Run All 10 RiseTrader Agents

This script demonstrates how to:
1. Initialize all agents via AgentCoordinator
2. Monitor agent status
3. Gracefully shutdown

Usage:
    python examples/run_all_agents.py
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.agent_coordinator import create_coordinator
import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger(__name__)


async def main():
    """Main entry point"""
    coordinator = None

    try:
        logger.info("starting_risetrader_agent_system")

        # Create and start all agents
        coordinator = await create_coordinator(
            config_path="/Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP/config/agents.yaml",
            redis_url="redis://localhost:6379",
            database_url="postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader",
        )

        logger.info("all_agents_started", agent_count=len(coordinator.agents))

        # Print agent status
        status = await coordinator.get_status()
        logger.info("system_status", **status)

        # Run for a while (or until interrupted)
        logger.info("system_running", message="Press Ctrl+C to stop")

        # Keep running
        while True:
            await asyncio.sleep(60)

            # Print periodic status
            status = await coordinator.get_status()
            logger.info(
                "periodic_status",
                running_agents=sum(1 for a in status["agents"] if a["running"]),
                total_agents=status["total_agents"],
            )

    except KeyboardInterrupt:
        logger.info("shutdown_requested")

    except Exception as e:
        logger.error("system_error", error=str(e), exc_info=True)

    finally:
        # Graceful shutdown
        if coordinator:
            logger.info("shutting_down_agents")
            await coordinator.stop()
            logger.info("all_agents_stopped")


if __name__ == "__main__":
    asyncio.run(main())
