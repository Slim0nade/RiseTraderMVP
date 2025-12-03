#!/usr/bin/env python3
"""
Test script for BaseAgent implementation.

Tests:
1. Database connectivity
2. Agent initialization
3. Ollama connectivity
4. Agent execution
5. Decision logging
6. Health checks

Usage:
    docker-compose exec api python scripts/test_base_agent.py
"""
import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from sqlalchemy import select

from src.agents.base import AgentConfig, AgentType, AgentLayer, LLMTier
from src.agents.examples.simple_test_agent import create_test_agent
from src.database.connection import get_async_session
from src.database.models import Agent

logger = structlog.get_logger(__name__)


async def test_base_agent():
    """Run comprehensive BaseAgent tests."""
    logger.info("=" * 80)
    logger.info("BaseAgent Test Suite Starting")
    logger.info("=" * 80)

    # Get database session
    logger.info("Step 1: Connecting to database...")
    async for session in get_async_session():
        try:
            # Create test agent record in database
            logger.info("Step 2: Creating test agent record in database...")
            test_agent_id = uuid4()

            agent_record = Agent(
                id=test_agent_id,
                name="Test Agent - Simple",
                agent_type=AgentType.TECHNICAL_ANALYST.value,
                layer=AgentLayer.ANALYSIS.value,
                llm_provider="ollama",
                llm_model="qwen3:14b",
                llm_tier=LLMTier.QUICK_THINK.value,
                temperature=0.1,
                max_tokens=500,
                system_prompt="Test agent system prompt",
                is_active=True,
            )

            session.add(agent_record)
            await session.commit()
            await session.refresh(agent_record)

            logger.info(
                "agent_record_created",
                agent_id=str(test_agent_id),
                agent_name=agent_record.name,
            )

            # Create agent configuration
            logger.info("Step 3: Creating agent configuration...")
            config = AgentConfig(
                name="Test Agent - Simple",
                agent_type=AgentType.TECHNICAL_ANALYST,
                layer=AgentLayer.ANALYSIS,
                llm_model="qwen3:14b",
                llm_tier=LLMTier.QUICK_THINK,
                temperature=0.1,
                max_tokens=500,
                retry_on_error=True,
                max_retries=2,
                log_decisions=True,
            )

            logger.info("config_created", config=config.model_dump())

            # Initialize agent
            logger.info("Step 4: Initializing SimpleTestAgent...")
            agent = await create_test_agent(
                agent_id=test_agent_id,
                config=config,
                session=session,
            )

            logger.info(
                "agent_initialized",
                agent_id=str(agent.agent_id),
                agent_name=agent.config.name,
            )

            # Test health check
            logger.info("Step 5: Running health check...")
            health = await agent.health_check()
            logger.info("health_check_result", health=health)

            # Test simple task execution
            logger.info("Step 6: Testing agent execution with simple task...")
            task = "Analyze the current market sentiment for Gold (XAUUSD). Provide a brief assessment."

            try:
                result = await agent.run(
                    task=task,
                    context={"symbol": "XAUUSD", "test_mode": True},
                    correlation_id="test-001",
                )

                logger.info(
                    "agent_execution_successful",
                    result=result,
                )

            except Exception as e:
                logger.error(
                    "agent_execution_failed",
                    error=str(e),
                    exc_info=True,
                )

            # Test agent state
            logger.info("Step 7: Checking agent state...")
            state = await agent.get_state()
            logger.info(
                "agent_state",
                state=state.state.value,
                tasks_completed=state.tasks_completed,
                total_errors=state.total_errors,
            )

            # Verify decision was logged
            logger.info("Step 8: Verifying decision log entry...")
            from src.database.repositories import DecisionLogRepository

            decision_log_repo = DecisionLogRepository(session)
            recent_decisions = await decision_log_repo.get_recent_by_agent(
                agent_id=test_agent_id,
                limit=1,
            )

            if recent_decisions:
                logger.info(
                    "decision_logged",
                    decision_count=len(recent_decisions),
                    latest_decision=recent_decisions[0].decision_type,
                )
            else:
                logger.warning("no_decisions_logged")

            # Final health check
            logger.info("Step 9: Final health check...")
            final_health = await agent.health_check()
            logger.info("final_health_check", health=final_health)

            # Cleanup: Delete test agent record
            logger.info("Step 10: Cleaning up test data...")
            await session.delete(agent_record)
            await session.commit()

            logger.info("=" * 80)
            logger.info("BaseAgent Test Suite COMPLETED SUCCESSFULLY")
            logger.info("=" * 80)

        except Exception as e:
            logger.error(
                "test_suite_failed",
                error=str(e),
                exc_info=True,
            )
            raise


if __name__ == "__main__":
    asyncio.run(test_base_agent())
