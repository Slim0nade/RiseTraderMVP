# AutoGen 0.4 Research Summary for RiseTrader Agents

**Date**: 2025-12-02
**Purpose**: Design guide for implementing 12 autonomous trading agents using AutoGen 0.4

---

## Executive Summary

AutoGen 0.4 is a complete rewrite from v0.2 with three main frameworks:
1. **AgentChat** - Conversational agents (our use case)
2. **Core** - Event-driven multi-agent systems
3. **Extensions** - External service integrations (Ollama, MCP, Docker)

**Key Insight**: Use **AgentChat** framework with **OllamaChatCompletionClient** for dual-LLM strategy.

---

## 1. AutoGen 0.4 Architecture

### Package Structure
```
autogen-agentchat==0.4.4   # AgentChat framework
autogen-core==0.4.4         # Core event system
autogen-ext==0.4.4          # Extensions (Ollama, MCP)
```

### Installation
```bash
# Already installed in our Docker container
pip install autogen-agentchat autogen-core "autogen-ext[ollama]"
```

---

## 2. AssistantAgent API

### Basic Pattern
```python
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.ollama import OllamaChatCompletionClient

# Create model client
model_client = OllamaChatCompletionClient(
    model="qwen3:14b",
    host="http://192.168.0.123:11434"  # Network Ollama instance
)

# Create agent
agent = AssistantAgent(
    name="technical_analyst",
    model_client=model_client,
    tools=[calculate_rsi, calculate_macd],  # Async functions
    system_message="You are a technical analyst...",
    reflect_on_tool_use=True,  # Self-reflection on tool results
    model_client_stream=True   # Streaming responses
)
```

### Key Parameters

| Parameter | Type | Purpose |
|-----------|------|---------|
| `name` | `str` | Agent identifier (must be unique) |
| `model_client` | `ChatCompletionClient` | LLM connection |
| `tools` | `List[Callable]` | Async functions with type hints |
| `system_message` | `str` | Agent role and instructions |
| `reflect_on_tool_use` | `bool` | Enable self-reflection |
| `model_client_stream` | `bool` | Enable streaming |

---

## 3. Ollama Integration

### OllamaChatCompletionClient Configuration

```python
from autogen_ext.models.ollama import OllamaChatCompletionClient
from pydantic import BaseModel

# Basic client
quick_think_client = OllamaChatCompletionClient(
    model="qwen3:14b",
    host="http://192.168.0.123:11434",
    options={
        "temperature": 0.1,
        "num_predict": 500
    }
)

# Client with structured output
class TradeSignal(BaseModel):
    direction: str
    confidence: float
    reasoning: str

deep_think_client = OllamaChatCompletionClient(
    model="deepseek-r1:14b",
    host="http://192.168.0.123:11434",
    response_format=TradeSignal,  # Pydantic model for JSON response
    options={
        "temperature": 0.7,
        "num_predict": 2000
    }
)
```

### Network Configuration

**Development Setup**: Using external Ollama instance on local network
- **Ollama Host**: Windows machine at `192.168.0.123:11434`
- **Models Available**: `qwen3:14b`, `deepseek-r1:14b`
- **From API Container**: Use `http://192.168.0.123:11434`
- **From Host**: Use `http://192.168.0.123:11434`

**Production**: Will use Digital Ocean droplet with firewall rules to restrict access

---

## 4. Tool/Function Registration

### Tool Definition Pattern

```python
async def calculate_rsi(
    symbol: str,
    period: int = 14,
    timeframe: str = "1h"
) -> dict:
    """
    Calculate Relative Strength Index for a symbol.

    Args:
        symbol: Trading symbol (e.g., "XAUUSD")
        period: RSI period (default 14)
        timeframe: Timeframe (default "1h")

    Returns:
        dict with rsi_value, is_overbought, is_oversold
    """
    # Implementation here
    return {
        "rsi_value": 65.5,
        "is_overbought": False,
        "is_oversold": False
    }
```

**Requirements**:
1. Must be `async` function
2. Must have type hints for all parameters
3. Must have docstring (used by LLM to understand tool)
4. Return type should be JSON-serializable

### Registering Tools

```python
agent = AssistantAgent(
    name="technical_analyst",
    model_client=model_client,
    tools=[
        calculate_rsi,
        calculate_macd,
        calculate_bollinger_bands,
        get_support_resistance
    ],
    ...
)
```

---

## 5. Message Patterns

### Running Agent

```python
from autogen_agentchat.ui import Console

async def run_analysis(symbol: str):
    task = f"Perform technical analysis on {symbol}"

    # Stream results to console
    await Console(agent.run_stream(task=task))

    # Or get result programmatically
    result = await agent.run(task=task)
    return result
```

### Message Types

```python
from autogen_core.models import UserMessage, AssistantMessage, FunctionCall

# User message
msg = UserMessage(content="Analyze XAUUSD", source="user")

# Messages include:
# - UserMessage: From human or system
# - AssistantMessage: Agent response
# - FunctionCall: Tool execution request
# - FunctionExecutionResult: Tool output
```

---

## 6. Multi-Agent Coordination (Future)

For multi-agent coordination, use `RoundRobinGroupChat`:

```python
from autogen_agentchat.teams import RoundRobinGroupChat

team = RoundRobinGroupChat(
    participants=[technical_analyst, fundamental_analyst, debate_agent]
)

result = await team.run(task="Should we trade XAUUSD?")
```

**Note**: For MVP, we'll start with single agents and add coordination later.

---

## 7. RiseTrader BaseAgent Design

### Architecture

```
BaseAgent (Abstract)
├── _autogen_agent: AssistantAgent
├── _model_client: OllamaChatCompletionClient
├── _db_session: AsyncSession
├── _agent_repository: AgentRepository
├── _decision_log_repository: DecisionLogRepository
└── _tools: List[Callable]

Methods:
├── __init__(agent_id, config, session, tools)
├── async run(task: str) -> DecisionSchema
├── async _log_decision(decision_data, reasoning)
├── async _handle_error(error)
├── async health_check() -> dict
└── async shutdown()
```

### Dual-LLM Strategy Implementation

```python
class BaseAgent:
    def __init__(
        self,
        agent_id: UUID,
        config: AgentConfig,
        session: AsyncSession,
        tools: List[Callable]
    ):
        # Determine which LLM tier to use
        if config.llm_tier == "quick_think":
            model_client = OllamaChatCompletionClient(
                model="qwen3:14b",
                host="http://192.168.0.123:11434",
                options={"temperature": 0.1, "num_predict": 500}
            )
        else:  # deep_think
            model_client = OllamaChatCompletionClient(
                model="deepseek-r1:14b",
                host="http://192.168.0.123:11434",
                options={"temperature": 0.7, "num_predict": 2000}
            )

        self._autogen_agent = AssistantAgent(
            name=config.name,
            model_client=model_client,
            tools=tools,
            system_message=config.system_message,
            reflect_on_tool_use=True,
            model_client_stream=False  # We'll handle streaming separately
        )
```

---

## 8. Key Differences from AutoGen 0.2

| Feature | AutoGen 0.2 | AutoGen 0.4 |
|---------|-------------|-------------|
| **Package** | `pyautogen` | `autogen-agentchat`, `autogen-core`, `autogen-ext` |
| **Agent Class** | `AssistantAgent` | `autogen_agentchat.agents.AssistantAgent` |
| **LLM Config** | `config_list` dict | `ChatCompletionClient` instance |
| **Tools** | `register_function` | Pass list to `tools` parameter |
| **Message Format** | Custom | Standard message types |
| **Streaming** | Basic | Native support with `run_stream()` |
| **Ollama** | Workarounds | Native `OllamaChatCompletionClient` |

---

## 9. Implementation Checklist

### Phase 1: BaseAgent (T029)
- [ ] Create `src/agents/base/base_agent.py`
- [ ] Implement dual-LLM client creation
- [ ] Wrap AssistantAgent with decision logging
- [ ] Add error handling and recovery
- [ ] Implement health checks
- [ ] Add performance tracking

### Phase 2: First Agent - Technical Analyst (T030)
- [ ] Define technical analysis tools (RSI, MACD, BB)
- [ ] Create TechnicalAnalystAgent class extending BaseAgent
- [ ] Test with sample market data
- [ ] Verify decision logging to database

### Phase 3: Integration Testing
- [ ] Test end-to-end: Event → Analysis → Decision → Log
- [ ] Verify Ollama connectivity from container
- [ ] Test both quick-think and deep-think models
- [ ] Validate decision_log entries in PostgreSQL

---

## 10. Code Templates

### BaseAgent Template

```python
# src/agents/base/base_agent.py
from abc import ABC, abstractmethod
from typing import List, Callable, Optional, Any
from uuid import UUID
from datetime import datetime

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.ollama import OllamaChatCompletionClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.base.agent_config import AgentConfig
from src.database.repositories import AgentRepository, DecisionLogRepository


class BaseAgent(ABC):
    """
    Base class for all RiseTrader agents using AutoGen 0.4.

    Wraps AutoGen's AssistantAgent with:
    - Decision logging to PostgreSQL
    - Error handling and recovery
    - Health monitoring
    - Performance tracking
    """

    def __init__(
        self,
        agent_id: UUID,
        config: AgentConfig,
        session: AsyncSession,
        tools: Optional[List[Callable]] = None
    ):
        self.agent_id = agent_id
        self.config = config
        self._session = session
        self._tools = tools or []

        # Initialize repositories
        self._agent_repo = AgentRepository(session)
        self._decision_log_repo = DecisionLogRepository(session)

        # Create Ollama client based on LLM tier
        self._model_client = self._create_model_client()

        # Create AutoGen AssistantAgent
        self._autogen_agent = AssistantAgent(
            name=config.name,
            model_client=self._model_client,
            tools=self._tools,
            system_message=config.system_message,
            reflect_on_tool_use=True,
            model_client_stream=False
        )

    def _create_model_client(self) -> OllamaChatCompletionClient:
        """Create Ollama client based on agent's LLM tier."""
        if self.config.llm_tier == "quick_think":
            return OllamaChatCompletionClient(
                model=self.config.llm_model or "qwen3:14b",
                host="http://192.168.0.123:11434",
                options={
                    "temperature": self.config.llm_temperature,
                    "num_predict": self.config.llm_max_tokens
                }
            )
        else:  # deep_think
            return OllamaChatCompletionClient(
                model=self.config.llm_model or "deepseek-r1:14b",
                host="http://192.168.0.123:11434",
                options={
                    "temperature": self.config.llm_temperature,
                    "num_predict": self.config.llm_max_tokens
                }
            )

    async def run(self, task: str, context: Optional[dict] = None) -> Any:
        """
        Execute agent task with decision logging.

        Args:
            task: Task description for the agent
            context: Optional context data

        Returns:
            Decision result
        """
        start_time = datetime.utcnow()

        try:
            # Run AutoGen agent
            result = await self._autogen_agent.run(task=task)

            # Extract decision from result
            decision_data = self._extract_decision(result)

            # Log decision to database
            await self._log_decision(
                decision_data=decision_data,
                reasoning=str(result),
                input_data={"task": task, "context": context},
                execution_time_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
            )

            # Update agent metrics
            await self._agent_repo.increment_decisions(
                self.agent_id,
                decision_time_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
            )

            return decision_data

        except Exception as e:
            await self._handle_error(e, task, context)
            raise

    @abstractmethod
    def _extract_decision(self, result: Any) -> dict:
        """
        Extract decision data from AutoGen result.
        Must be implemented by subclasses.
        """
        pass

    async def _log_decision(
        self,
        decision_data: dict,
        reasoning: str,
        input_data: dict,
        execution_time_ms: float
    ):
        """Log decision to decision_log table."""
        # Implementation here
        pass

    async def _handle_error(self, error: Exception, task: str, context: Optional[dict]):
        """Handle and log errors."""
        # Implementation here
        pass

    async def health_check(self) -> dict:
        """Check agent health status."""
        return {
            "agent_id": str(self.agent_id),
            "status": "healthy",
            "model_client": "connected",
            "last_decision": await self._agent_repo.get_by_id(self.agent_id)
        }

    async def shutdown(self):
        """Cleanup resources."""
        # Close model client if needed
        pass
```

---

## 11. Next Steps

**Immediate (This Session)**:
1. Create BaseAgent implementation (T029)
2. Test Ollama connectivity from API container
3. Verify dual-LLM client creation

**Next Session**:
1. Implement Technical Analyst agent (T030)
2. Create technical analysis tools (RSI, MACD, BB)
3. Test end-to-end agent execution
4. Verify decision logging

---

## 12. Critical Notes

### Ollama Models
- **Already pulled on external machine (192.168.0.123)**:
  - `qwen3:14b` (9.28 GB, Q4_K_M quantization)
  - `deepseek-r1:14b` (8.99 GB, Q4_K_M quantization)
- Models accessible via `http://192.168.0.123:11434/api/tags`

### Tool Requirements for Ollama
- Ollama is stricter than OpenAI for tools
- Must use typed property objects with `type` and `description`
- All parameters must have type hints

### Performance Considerations
- Use `quick_think` (Qwen2.5:14b) for rapid decisions
- Use `deep_think` (DeepSeek-R1:14b) for complex analysis
- Monitor token usage and response times in `decision_log`

---

**Status**: Research complete. Ready to implement BaseAgent (T029).
**Last Updated**: 2025-12-02
