"""
Simple Test Agent: Minimal implementation for testing BaseAgent.

This is a simple example agent used to verify:
1. BaseAgent initialization
2. Ollama connectivity
3. Decision logging
4. Error handling
"""
from typing import Any, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.base import AgentConfig, BaseAgent


class SimpleTestAgent(BaseAgent):
    """
    Simple test agent that echoes back analysis requests.

    Used for testing BaseAgent infrastructure without complex logic.
    """

    def _get_system_message(self) -> str:
        """
        Get system message for the test agent.

        Returns:
            System message instructing the agent to analyze and respond
        """
        return """You are a simple test agent for the RiseTrader trading system.

Your role is to:
1. Receive a task or question
2. Provide a brief, structured response
3. Include a confidence score (0.0-1.0)

Always respond in JSON format with these fields:
{
  "analysis": "Your brief analysis or response",
  "confidence": 0.85,
  "recommendation": "Your recommendation (if applicable)"
}

Be concise and clear. This is for testing infrastructure, not actual trading decisions.
"""

    def _extract_decision(self, result: Any) -> Dict[str, Any]:
        """
        Extract decision data from AutoGen result.

        For the test agent, we try to parse JSON from the result,
        or create a simple structure if parsing fails.

        Args:
            result: Result from AutoGen agent.run()

        Returns:
            Dictionary with decision data
        """
        import json

        # Try to get the text content from the result
        result_text = str(result)

        # Try to parse JSON from the response
        try:
            # Look for JSON in the response
            start_idx = result_text.find("{")
            end_idx = result_text.rfind("}") + 1

            if start_idx != -1 and end_idx > start_idx:
                json_str = result_text[start_idx:end_idx]
                decision_data = json.loads(json_str)
            else:
                # No JSON found, create simple structure
                decision_data = {
                    "analysis": result_text[:500],  # First 500 chars
                    "confidence": 0.5,
                    "recommendation": "N/A",
                }

        except (json.JSONDecodeError, ValueError):
            # If JSON parsing fails, create simple structure
            decision_data = {
                "analysis": result_text[:500],
                "confidence": 0.5,
                "recommendation": "N/A",
                "parse_error": "Could not parse JSON from response",
            }

        return decision_data


async def create_test_agent(
    agent_id: UUID,
    config: AgentConfig,
    session: AsyncSession,
) -> SimpleTestAgent:
    """
    Factory function to create a SimpleTestAgent.

    Args:
        agent_id: Unique agent instance ID
        config: Agent configuration
        session: Database session

    Returns:
        Initialized SimpleTestAgent
    """
    return SimpleTestAgent(
        agent_id=agent_id,
        config=config,
        session=session,
        tools=[],  # No MCP tools for simple test
    )
