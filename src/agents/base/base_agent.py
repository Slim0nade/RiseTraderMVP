"""
BaseAgent: Abstract base class for all RiseTrader agents using AutoGen 0.4.

Provides common infrastructure for:
- AutoGen AssistantAgent wrapping
- Dual-LLM client creation (quick-think vs deep-think)
- Decision logging to PostgreSQL
- Error handling and recovery
- Health monitoring
- Performance tracking
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

import structlog
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.base.agent_config import AgentConfig, AgentState, AgentStateModel, LLMTier
from src.database.repositories import AgentRepository, DecisionLogRepository

logger = structlog.get_logger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all RiseTrader autonomous trading agents.

    Wraps AutoGen 0.4's AssistantAgent with RiseTrader-specific features:
    - Decision logging to decision_log table
    - Error handling with retry logic
    - Health monitoring
    - Performance metrics tracking
    - State management

    Subclasses must implement:
    - _extract_decision(): Parse AutoGen result into decision data
    - _get_system_message(): Provide agent-specific system prompt
    """

    def __init__(
        self,
        agent_id: UUID,
        config: AgentConfig,
        session: AsyncSession,
        tools: Optional[List[Callable]] = None,
    ):
        """
        Initialize base agent.

        Args:
            agent_id: Unique agent instance ID from database
            config: Agent configuration (LLM settings, RL config, etc.)
            session: SQLAlchemy async session for database operations
            tools: Optional list of async functions (MCP tools) for the agent
        """
        self.agent_id = agent_id
        self.config = config
        self._session = session
        self._tools = tools or []

        # Initialize repositories
        self._agent_repo = AgentRepository(session)
        self._decision_log_repo = DecisionLogRepository(session)

        # Initialize state
        self._state = AgentStateModel(
            agent_id=agent_id,
            agent_type=config.agent_type,
            state=AgentState.IDLE,
        )

        # Create Ollama model client based on LLM tier
        self._model_client = self._create_model_client()

        # Create AutoGen AssistantAgent
        self._autogen_agent = AssistantAgent(
            name=config.name,
            model_client=self._model_client,
            tools=self._tools,
            system_message=self._get_system_message(),
            reflect_on_tool_use=True,  # Enable self-reflection
            model_client_stream=False,  # We'll handle streaming separately if needed
        )

        logger.info(
            "agent_initialized",
            agent_id=str(agent_id),
            agent_type=config.agent_type.value,
            agent_name=config.name,
            llm_tier=config.llm_tier.value,
            llm_model=config.llm_model,
            tools_count=len(self._tools),
        )

    def _create_model_client(self) -> OpenAIChatCompletionClient:
        """
        Create OpenAIChatCompletionClient configured for Ollama.

        Uses OpenAI-compatible client pointing to Ollama instance at 192.168.0.123:11434.
        Ollama provides an OpenAI-compatible API at /v1/chat/completions.

        Returns:
            Configured OpenAIChatCompletionClient for Ollama
        """
        # Get Ollama host from config or use default
        ollama_host = self.config.config_overrides.get(
            "ollama_host", "http://192.168.0.123:11434"
        )

        # Default models per tier
        if self.config.llm_tier == LLMTier.QUICK_THINK:
            default_model = "qwen3:14b"
            default_temp = 0.1
            default_tokens = 500
        else:  # DEEP_THINK
            default_model = "deepseek-r1:14b"
            default_temp = 0.7
            default_tokens = 2000

        model = self.config.llm_model or default_model
        temperature = self.config.temperature or default_temp
        max_tokens = self.config.max_tokens or default_tokens

        # Use OpenAI client with Ollama base URL
        # Ollama's OpenAI-compatible endpoint: http://host:port/v1
        return OpenAIChatCompletionClient(
            model=model,
            base_url=f"{ollama_host}/v1",  # Ollama OpenAI-compatible endpoint
            api_key="ollama",  # Ollama doesn't need a real API key, but client requires it
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @abstractmethod
    def _get_system_message(self) -> str:
        """
        Get agent-specific system message/prompt.

        Must be implemented by subclasses to provide their role-specific instructions.

        Returns:
            System message string for the LLM
        """
        pass

    @abstractmethod
    def _extract_decision(self, result: Any) -> Dict[str, Any]:
        """
        Extract decision data from AutoGen result.

        Must be implemented by subclasses to parse the LLM's response
        into structured decision data.

        Args:
            result: Result from AutoGen agent.run()

        Returns:
            Dictionary with decision data (structure depends on agent type)
        """
        pass

    async def run(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute agent task with decision logging and error handling.

        This is the main entry point for agent execution.

        Args:
            task: Task description for the agent
            context: Optional context data (market data, previous decisions, etc.)
            correlation_id: Optional correlation ID for multi-agent coordination

        Returns:
            Decision result dictionary

        Raises:
            Exception: If task fails after retries
        """
        start_time = datetime.utcnow()
        attempt = 0
        last_error = None

        # Update state to PROCESSING
        await self._update_state(
            AgentState.PROCESSING,
            current_task=task,
            task_started_at=start_time,
        )

        while attempt < (self.config.max_retries + 1):
            try:
                logger.info(
                    "agent_task_starting",
                    agent_id=str(self.agent_id),
                    agent_name=self.config.name,
                    task=task,
                    attempt=attempt + 1,
                    correlation_id=correlation_id,
                )

                # Run AutoGen agent
                result = await self._autogen_agent.run(task=task)

                # Extract decision from result
                decision_data = self._extract_decision(result)

                # Calculate execution time
                execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

                # Log decision to database
                if self.config.log_decisions:
                    await self._log_decision(
                        decision_data=decision_data,
                        reasoning=str(result),
                        input_data={"task": task, "context": context},
                        execution_time_ms=execution_time_ms,
                        correlation_id=correlation_id,
                    )

                # Update agent metrics
                await self._update_metrics(
                    decisions_count=1,
                    avg_decision_time_ms=execution_time_ms,
                )

                # Update state to IDLE
                await self._update_state(
                    AgentState.IDLE,
                    current_task=None,
                    task_started_at=None,
                )

                logger.info(
                    "agent_task_completed",
                    agent_id=str(self.agent_id),
                    agent_name=self.config.name,
                    execution_time_ms=round(execution_time_ms, 2),
                    correlation_id=correlation_id,
                )

                return decision_data

            except Exception as e:
                last_error = e
                attempt += 1

                logger.error(
                    "agent_task_error",
                    agent_id=str(self.agent_id),
                    agent_name=self.config.name,
                    error=str(e),
                    attempt=attempt,
                    max_retries=self.config.max_retries,
                    correlation_id=correlation_id,
                    exc_info=True,
                )

                # Update error tracking
                await self._handle_error(e, task, context)

                # If no retries left, raise
                if not self.config.retry_on_error or attempt > self.config.max_retries:
                    await self._update_state(
                        AgentState.ERROR,
                        current_task=None,
                        task_started_at=None,
                    )
                    raise

                # Wait before retry (exponential backoff)
                await self._wait_before_retry(attempt)

        # Should not reach here, but just in case
        await self._update_state(
            AgentState.ERROR,
            current_task=None,
            task_started_at=None,
        )
        raise last_error

    async def _log_decision(
        self,
        decision_data: Dict[str, Any],
        reasoning: str,
        input_data: Dict[str, Any],
        execution_time_ms: float,
        correlation_id: Optional[str] = None,
    ):
        """
        Log decision to decision_log table.

        Args:
            decision_data: Structured decision data
            reasoning: LLM reasoning/explanation
            input_data: Input context for the decision
            execution_time_ms: Execution time in milliseconds
            correlation_id: Optional correlation ID for multi-agent coordination
        """
        try:
            await self._decision_log_repo.create(
                agent_id=self.agent_id,
                decision_type=self.config.agent_type.value,
                decision_data=decision_data,
                reasoning=reasoning,
                input_data=input_data,
                execution_time_ms=execution_time_ms,
                model_name=self.config.llm_model,
                temperature=self.config.temperature,
                correlation_id=correlation_id,
            )

            logger.debug(
                "decision_logged",
                agent_id=str(self.agent_id),
                decision_type=self.config.agent_type.value,
                correlation_id=correlation_id,
            )

        except Exception as e:
            logger.error(
                "decision_log_error",
                agent_id=str(self.agent_id),
                error=str(e),
                exc_info=True,
            )
            # Don't raise - logging failure shouldn't stop agent execution

    async def _handle_error(
        self,
        error: Exception,
        task: str,
        context: Optional[Dict[str, Any]],
    ):
        """
        Handle and track errors.

        Args:
            error: Exception that occurred
            task: Task that was being executed
            context: Task context
        """
        # Update state tracking
        self._state.total_errors += 1
        self._state.last_error = str(error)
        self._state.last_error_at = datetime.utcnow()

        # Update agent record in database
        try:
            await self._agent_repo.increment_errors(self.agent_id)
        except Exception as db_error:
            logger.error(
                "error_tracking_failed",
                agent_id=str(self.agent_id),
                error=str(db_error),
                exc_info=True,
            )

    async def _update_state(
        self,
        state: AgentState,
        current_task: Optional[str] = None,
        task_started_at: Optional[datetime] = None,
    ):
        """
        Update agent operational state.

        Args:
            state: New agent state
            current_task: Current task description (if processing)
            task_started_at: Task start timestamp (if processing)
        """
        self._state.state = state
        self._state.last_state_change = datetime.utcnow()
        self._state.current_task = current_task
        self._state.task_started_at = task_started_at

        if state in [AgentState.IDLE, AgentState.PROCESSING]:
            self._state.last_active_at = datetime.utcnow()

    async def _update_metrics(
        self,
        decisions_count: int = 0,
        avg_decision_time_ms: Optional[float] = None,
    ):
        """
        Update agent performance metrics.

        Args:
            decisions_count: Number of decisions made
            avg_decision_time_ms: Average decision time in milliseconds
        """
        self._state.tasks_completed += decisions_count

        # Update rolling average decision time
        if avg_decision_time_ms is not None:
            if self._state.avg_task_duration_ms is None:
                self._state.avg_task_duration_ms = avg_decision_time_ms
            else:
                # Simple exponential moving average
                alpha = 0.2
                self._state.avg_task_duration_ms = (
                    alpha * avg_decision_time_ms
                    + (1 - alpha) * self._state.avg_task_duration_ms
                )

        # Update database record
        try:
            await self._agent_repo.increment_decisions(
                self.agent_id,
                decision_time_ms=avg_decision_time_ms,
            )
        except Exception as e:
            logger.error(
                "metrics_update_failed",
                agent_id=str(self.agent_id),
                error=str(e),
                exc_info=True,
            )

    async def _wait_before_retry(self, attempt: int):
        """
        Wait before retrying a failed task (exponential backoff).

        Args:
            attempt: Current attempt number
        """
        import asyncio

        wait_seconds = min(2 ** (attempt - 1), 30)  # Max 30 seconds
        logger.info(
            "agent_retry_waiting",
            agent_id=str(self.agent_id),
            attempt=attempt,
            wait_seconds=wait_seconds,
        )
        await asyncio.sleep(wait_seconds)

    async def health_check(self) -> Dict[str, Any]:
        """
        Check agent health status.

        Returns:
            Health status dictionary
        """
        try:
            # Fetch latest agent record from database
            agent_record = await self._agent_repo.get_by_id(self.agent_id)

            return {
                "agent_id": str(self.agent_id),
                "agent_name": self.config.name,
                "agent_type": self.config.agent_type.value,
                "status": "healthy" if self._state.is_healthy else "unhealthy",
                "state": self._state.state.value,
                "current_task": self._state.current_task,
                "tasks_completed": self._state.tasks_completed,
                "total_errors": self._state.total_errors,
                "avg_decision_time_ms": self._state.avg_task_duration_ms,
                "last_active_at": self._state.last_active_at.isoformat() if self._state.last_active_at else None,
                "model_client": "connected",
                "ollama_model": self.config.llm_model,
                "database_record": {
                    "is_active": agent_record.is_active if agent_record else None,
                    "total_decisions": agent_record.total_decisions if agent_record else 0,
                } if agent_record else None,
            }

        except Exception as e:
            logger.error(
                "health_check_error",
                agent_id=str(self.agent_id),
                error=str(e),
                exc_info=True,
            )
            return {
                "agent_id": str(self.agent_id),
                "status": "error",
                "error": str(e),
            }

    async def get_state(self) -> AgentStateModel:
        """
        Get current agent state.

        Returns:
            Current agent state model
        """
        return self._state

    async def pause(self):
        """Pause agent (stop accepting new tasks)."""
        await self._update_state(AgentState.PAUSED)
        logger.info("agent_paused", agent_id=str(self.agent_id))

    async def resume(self):
        """Resume agent from paused state."""
        await self._update_state(AgentState.IDLE)
        logger.info("agent_resumed", agent_id=str(self.agent_id))

    async def shutdown(self):
        """
        Cleanup resources before shutdown.

        Should be called when agent is being stopped.
        """
        await self._update_state(AgentState.STOPPED)
        logger.info(
            "agent_shutdown",
            agent_id=str(self.agent_id),
            agent_name=self.config.name,
            tasks_completed=self._state.tasks_completed,
            total_errors=self._state.total_errors,
        )

        # Close any resources if needed
        # (AutoGen agents don't require explicit cleanup currently)
