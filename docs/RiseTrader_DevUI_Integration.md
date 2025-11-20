# RiseTrader + Microsoft Agent Framework DevUI Integration
## Real-Time Agent Visualization & Debugging

**Date:** November 16, 2025  
**Status:** 🎨 **RECOMMENDED INTEGRATION**

---

## 1. What is Microsoft Agent Framework DevUI?

**DevUI** is an interactive developer interface for visualizing, debugging, and testing AI agents and multi-agent workflows.

### Key Features:
```
✅ Real-time workflow visualization
✅ Agent interaction tracing
✅ Tool invocation tracking
✅ Token usage monitoring
✅ OpenTelemetry integration
✅ Browser-based interface
✅ Live execution paths
✅ Message flow visualization
✅ Performance metrics
✅ State inspection
```

### What It Looks Like:
```
┌─────────────────────────────────────────────────────────┐
│  RiseTrader Agent Workflow Visualization                │
├─────────────────────────────────────────────────────────┤
│  Left Panel: Workflow Graph                            │
│  ┌──────────────────────────────────────────────┐      │
│  │  ┌─────────────┐                             │      │
│  │  │ MarketData  │──→ ┌──────────────┐        │      │
│  │  │   Agent     │    │ Signal       │        │      │
│  │  └─────────────┘    │ Generator    │─┐      │      │
│  │                     └──────────────┘ │      │      │
│  │  ┌─────────────┐                     │      │      │
│  │  │ ML          │──→──────────────────┘      │      │
│  │  │ Prediction  │                            │      │
│  │  └─────────────┘                            │      │
│  │                     ┌──────────────┐        │      │
│  │                     │ Risk         │─┐      │      │
│  │                     │ Manager      │ │      │      │
│  │                     └──────────────┘ │      │      │
│  │                                      │      │      │
│  │                     ┌──────────────┐ │      │      │
│  │                     │ Execution    │←┘      │      │
│  │                     │ Agent        │        │      │
│  │                     └──────────────┘        │      │
│  └──────────────────────────────────────────────┘      │
│                                                         │
│  Right Panel: Live Events & Traces                     │
│  ┌──────────────────────────────────────────────┐      │
│  │ [15:23:45] MarketDataAgent: New tick CrudeOIL│      │
│  │ [15:23:45] SignalGenerator: Processing...    │      │
│  │ [15:23:46] MLPrediction: Forecast 73.85      │      │
│  │ [15:23:46] SignalGenerator: BUY signal (0.82)│      │
│  │ [15:23:47] RiskManager: Validating...        │      │
│  │ [15:23:47] RiskManager: ✅ Approved (0.5 lots)│      │
│  │ [15:23:48] ExecutionAgent: Order sent to MT4 │      │
│  │ [15:23:48] ExecutionAgent: ✅ Filled @73.52   │      │
│  └──────────────────────────────────────────────┘      │
│                                                         │
│  Bottom Panel: Metrics                                 │
│  ┌──────────────────────────────────────────────┐      │
│  │ Signals: 15 | Trades: 3 | Win Rate: 67%      │      │
│  │ Latency: 234ms | Token Usage: 1,247          │      │
│  └──────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Integration Architecture

### 2.1 How It Fits with RiseTrader

```
Current Architecture:
┌─────────────────┐
│  RiseTrader     │
│  MCP Server     │  ← Our custom coordination
│                 │
│  10 Agents      │
└─────────────────┘

Enhanced with DevUI:
┌──────────────────────────────────────┐
│  DevUI (Port 8090)                   │
│  • Visual workflow graph             │
│  • Real-time event streaming         │
│  • Trace visualization               │
│  • Performance metrics               │
└──────────────────────────────────────┘
           ↕ (OpenTelemetry)
┌──────────────────────────────────────┐
│  RiseTrader MCP Server + Agents      │
│  • SignalGeneratorAgent              │
│  • RiskManagerAgent                  │
│  • ExecutionAgent                    │
│  • ... (all 10 agents)               │
└──────────────────────────────────────┘
```

### 2.2 Integration Strategy

**Two Options:**

**Option A: Wrapper Approach** (Recommended)
- Keep our MCP server as-is
- Wrap our agents in Agent Framework interfaces
- DevUI visualizes the wrapped agents
- Best of both worlds

**Option B: Full Migration**
- Replace MCP with Agent Framework orchestration
- Use Agent Framework workflows
- Native DevUI integration
- More work but cleaner

**We'll use Option A** for faster implementation.

---

## 3. Implementation Plan

### 3.1 Install Agent Framework DevUI

```bash
# Add to requirements.txt
agent-framework[devui]>=0.1.0

# Install
pip install agent-framework[devui] --pre
```

### 3.2 Create Agent Framework Wrappers

```python
# src/agents/devui_integration/agent_wrappers.py

from agent_framework import ChatAgent, Tool
from agent_framework.openai import OpenAIChatClient
from typing import List, Any, Dict
import asyncio

class RiseTraderAgentWrapper:
    """
    Wrapper to expose RiseTrader agents to Agent Framework DevUI
    """
    
    def __init__(self, risetrader_agent, name: str, description: str):
        self.risetrader_agent = risetrader_agent
        self.name = name
        self.description = description
        self.chat_client = OpenAIChatClient()  # For DevUI compatibility
        
        # Create Agent Framework agent
        self.af_agent = self._create_af_agent()
    
    def _create_af_agent(self) -> ChatAgent:
        """Create Agent Framework agent that wraps RiseTrader agent"""
        
        # Extract tools from RiseTrader agent
        tools = self._extract_tools()
        
        # Create Agent Framework agent
        agent = ChatAgent(
            name=self.name,
            description=self.description,
            chat_client=self.chat_client,
            tools=tools,
            system_message=self._get_system_message()
        )
        
        return agent
    
    def _extract_tools(self) -> List[Tool]:
        """Extract tools from RiseTrader agent and wrap them"""
        tools = []
        
        # Map RiseTrader agent methods to Agent Framework tools
        if hasattr(self.risetrader_agent, 'generate_signal'):
            @Tool(name="generate_signal", description="Generate trading signal")
            async def generate_signal_tool(symbol: str) -> dict:
                return await self.risetrader_agent.generate_signal(symbol)
            tools.append(generate_signal_tool)
        
        if hasattr(self.risetrader_agent, 'validate_trade'):
            @Tool(name="validate_trade", description="Validate trade against risk rules")
            async def validate_trade_tool(signal: dict) -> dict:
                return await self.risetrader_agent.validate_trade(signal)
            tools.append(validate_trade_tool)
        
        if hasattr(self.risetrader_agent, 'execute_trade'):
            @Tool(name="execute_trade", description="Execute trade on MT4")
            async def execute_trade_tool(trade: dict) -> dict:
                return await self.risetrader_agent.execute_trade(trade)
            tools.append(execute_trade_tool)
        
        # Add more tool mappings as needed
        
        return tools
    
    def _get_system_message(self) -> str:
        """Get system message for the agent"""
        return f"You are {self.name}, responsible for {self.description}"
    
    async def process(self, input_data: Any) -> Any:
        """Process input through both RiseTrader agent and AF agent"""
        # Process through RiseTrader agent
        result = await self.risetrader_agent.handle_message("process", input_data)
        
        # Log to DevUI via AF agent
        await self.af_agent.run(
            message=f"Processing: {input_data}",
            context={"result": result}
        )
        
        return result


class SignalGeneratorAgentWrapper(RiseTraderAgentWrapper):
    """Wrapper for SignalGeneratorAgent"""
    
    def __init__(self, signal_generator_agent):
        super().__init__(
            risetrader_agent=signal_generator_agent,
            name="SignalGenerator",
            description="Generates trading signals from multiple strategies"
        )


class RiskManagerAgentWrapper(RiseTraderAgentWrapper):
    """Wrapper for RiskManagerAgent"""
    
    def __init__(self, risk_manager_agent):
        super().__init__(
            risetrader_agent=risk_manager_agent,
            name="RiskManager",
            description="Validates trades against risk management rules"
        )


class ExecutionAgentWrapper(RiseTraderAgentWrapper):
    """Wrapper for ExecutionAgent"""
    
    def __init__(self, execution_agent):
        super().__init__(
            risetrader_agent=execution_agent,
            name="ExecutionAgent",
            description="Executes validated trades on MetaTrader 4"
        )


# Create wrappers for all 10 agents...
```

### 3.3 Create Workflow for DevUI

```python
# src/agents/devui_integration/trading_workflow.py

from agent_framework import Workflow, WorkflowNode
from agent_framework.devui import serve
from typing import List
import asyncio

class RiseTraderWorkflow:
    """
    RiseTrader trading workflow for DevUI visualization
    """
    
    def __init__(self, agent_wrappers: dict):
        self.wrappers = agent_wrappers
        self.workflow = self._create_workflow()
    
    def _create_workflow(self) -> Workflow:
        """Create Agent Framework workflow"""
        
        workflow = Workflow(name="RiseTraderTradingFlow")
        
        # Define workflow nodes
        market_data_node = WorkflowNode(
            name="MarketData",
            agent=self.wrappers["market_data"].af_agent,
            description="Streams market data"
        )
        
        signal_gen_node = WorkflowNode(
            name="SignalGeneration",
            agent=self.wrappers["signal_generator"].af_agent,
            description="Generates trading signals",
            depends_on=[market_data_node]
        )
        
        risk_mgmt_node = WorkflowNode(
            name="RiskManagement",
            agent=self.wrappers["risk_manager"].af_agent,
            description="Validates trades",
            depends_on=[signal_gen_node]
        )
        
        execution_node = WorkflowNode(
            name="Execution",
            agent=self.wrappers["execution"].af_agent,
            description="Executes trades on MT4",
            depends_on=[risk_mgmt_node]
        )
        
        # Add nodes to workflow
        workflow.add_node(market_data_node)
        workflow.add_node(signal_gen_node)
        workflow.add_node(risk_mgmt_node)
        workflow.add_node(execution_node)
        
        return workflow
    
    def serve_devui(self, port: int = 8090, tracing_enabled: bool = True):
        """Launch DevUI to visualize the workflow"""
        serve(
            entities=[self.workflow],
            port=port,
            auto_open=True,
            tracing_enabled=tracing_enabled
        )
```

### 3.4 Integrate with AgentOrchestrator

```python
# src/agents/coordination/orchestrator.py (additions)

from src.agents.devui_integration.agent_wrappers import (
    SignalGeneratorAgentWrapper,
    RiskManagerAgentWrapper,
    ExecutionAgentWrapper,
    # ... other wrappers
)
from src.agents.devui_integration.trading_workflow import RiseTraderWorkflow

class AgentOrchestrator:
    """Enhanced orchestrator with DevUI integration"""
    
    def __init__(self, enable_devui: bool = False):
        self.mcp_server = RiseTraderMCPServer()
        self.agents = {}
        self.enable_devui = enable_devui
        self.devui_wrappers = {}
        self.devui_workflow = None
        
    async def initialize(self):
        """Initialize all agents"""
        logger.info("Initializing agent system...")
        
        # ... existing agent initialization ...
        
        # Initialize DevUI if enabled
        if self.enable_devui:
            await self._initialize_devui()
        
        logger.info("Agent system initialized successfully")
    
    async def _initialize_devui(self):
        """Initialize DevUI integration"""
        logger.info("Initializing DevUI integration...")
        
        # Create wrappers for all agents
        self.devui_wrappers = {
            "signal_generator": SignalGeneratorAgentWrapper(
                self.agents["signal_generator"]
            ),
            "risk_manager": RiskManagerAgentWrapper(
                self.agents["risk_manager"]
            ),
            "execution": ExecutionAgentWrapper(
                self.agents["execution"]
            ),
            # ... create wrappers for all 10 agents
        }
        
        # Create workflow
        self.devui_workflow = RiseTraderWorkflow(self.devui_wrappers)
        
        # Start DevUI server (non-blocking)
        asyncio.create_task(self._run_devui())
        
        logger.info("✅ DevUI available at http://localhost:8090")
    
    async def _run_devui(self):
        """Run DevUI server in background"""
        try:
            self.devui_workflow.serve_devui(
                port=8090,
                tracing_enabled=True
            )
        except Exception as e:
            logger.error(f"DevUI error: {e}")
```

### 3.5 Add DevUI Configuration

```yaml
# config/agents.yaml (additions)

devui:
  enabled: true  # Enable DevUI visualization
  port: 8090
  auto_open_browser: true
  tracing_enabled: true
  
  # OpenTelemetry configuration for DevUI
  otel:
    exporter_endpoint: "http://jaeger:4318"
    service_name: "risetrader-agents"
    export_interval_seconds: 5
```

### 3.6 Update Docker Compose

```yaml
# docker-compose.yml (additions)

services:
  agent-coordinator:
    # ... existing config ...
    ports:
      - "7000:7000"  # MCP server
      - "8090:8090"  # DevUI
    environment:
      - ENABLE_DEVUI=true
      - DEVUI_PORT=8090
```

---

## 4. Enhanced Features

### 4.1 Custom Metrics in DevUI

```python
# src/agents/devui_integration/metrics.py

from agent_framework.telemetry import MetricsCollector

class RiseTraderMetrics:
    """Custom metrics for RiseTrader agents"""
    
    def __init__(self):
        self.collector = MetricsCollector()
    
    async def record_signal_generated(self, signal: dict):
        """Record signal generation"""
        self.collector.record_event(
            event_type="signal_generated",
            properties={
                "symbol": signal["symbol"],
                "direction": signal["direction"],
                "confidence": signal["confidence"],
                "timestamp": signal["timestamp"]
            }
        )
    
    async def record_trade_executed(self, trade: dict):
        """Record trade execution"""
        self.collector.record_event(
            event_type="trade_executed",
            properties={
                "symbol": trade["symbol"],
                "type": trade["type"],
                "volume": trade["volume"],
                "price": trade["price"],
                "latency_ms": trade["execution_time_ms"]
            }
        )
    
    async def record_risk_check(self, result: dict):
        """Record risk validation"""
        self.collector.record_event(
            event_type="risk_check",
            properties={
                "approved": result["approved"],
                "reason": result["reason"],
                "position_size": result.get("position_size", 0)
            }
        )
```

### 4.2 Real-Time Event Streaming

```python
# src/agents/devui_integration/event_streamer.py

import asyncio
from typing import AsyncIterator
import json

class DevUIEventStreamer:
    """Stream RiseTrader events to DevUI"""
    
    def __init__(self, mcp_server):
        self.mcp = mcp_server
        self.event_queue = asyncio.Queue()
    
    async def start_streaming(self):
        """Start streaming events to DevUI"""
        
        # Subscribe to all MCP events
        events_to_track = [
            "new_tick",
            "signal_generated",
            "trade_validated",
            "trade_executed",
            "risk_limit_exceeded",
            "performance_alert"
        ]
        
        for event_name in events_to_track:
            self.mcp.server.on(event_name, self._handle_event)
    
    async def _handle_event(self, event_name: str, data: dict):
        """Handle MCP event and forward to DevUI"""
        
        # Transform to DevUI format
        devui_event = {
            "type": event_name,
            "timestamp": data.get("timestamp", ""),
            "data": data,
            "agent": data.get("agent", "system")
        }
        
        # Send to DevUI
        await self.event_queue.put(devui_event)
    
    async def get_events(self) -> AsyncIterator[dict]:
        """Get events for DevUI consumption"""
        while True:
            event = await self.event_queue.get()
            yield event
```

### 4.3 Custom Dashboard Components

```python
# src/agents/devui_integration/custom_dashboard.py

from agent_framework.devui import DashboardComponent

class TradingPerformancePanel(DashboardComponent):
    """Custom panel showing trading performance"""
    
    def __init__(self, performance_monitor):
        self.monitor = performance_monitor
    
    async def render(self) -> dict:
        """Render performance metrics"""
        
        metrics = await self.monitor.get_current_metrics()
        
        return {
            "type": "panel",
            "title": "Trading Performance",
            "widgets": [
                {
                    "type": "metric",
                    "label": "Total P&L",
                    "value": f"${metrics['total_pnl']:.2f}",
                    "color": "green" if metrics['total_pnl'] > 0 else "red"
                },
                {
                    "type": "metric",
                    "label": "Win Rate",
                    "value": f"{metrics['win_rate']:.1f}%"
                },
                {
                    "type": "metric",
                    "label": "Open Positions",
                    "value": metrics['open_positions']
                },
                {
                    "type": "chart",
                    "chart_type": "line",
                    "data": metrics['equity_curve'][-50:],  # Last 50 points
                    "title": "Equity Curve"
                }
            ]
        }


class RiskMonitoringPanel(DashboardComponent):
    """Custom panel showing risk metrics"""
    
    def __init__(self, risk_overseer):
        self.overseer = risk_overseer
    
    async def render(self) -> dict:
        """Render risk metrics"""
        
        risk_data = await self.overseer.get_risk_status()
        
        return {
            "type": "panel",
            "title": "Risk Monitoring",
            "widgets": [
                {
                    "type": "gauge",
                    "label": "Portfolio Risk",
                    "value": risk_data['portfolio_risk_pct'],
                    "max": 100,
                    "thresholds": [
                        {"value": 50, "color": "green"},
                        {"value": 75, "color": "yellow"},
                        {"value": 90, "color": "red"}
                    ]
                },
                {
                    "type": "metric",
                    "label": "Max Drawdown",
                    "value": f"{risk_data['max_drawdown']:.2f}%"
                },
                {
                    "type": "list",
                    "title": "Active Risk Limits",
                    "items": risk_data['active_limits']
                }
            ]
        }
```

---

## 5. DevUI Features for RiseTrader

### 5.1 What You Can See

**1. Agent Workflow Graph:**
```
- Visual representation of all 10 agents
- Connection flows between agents
- Active/inactive status
- Real-time state updates
```

**2. Live Event Stream:**
```
- Every agent action logged
- Message passing between agents
- Tool invocations
- Decision explanations
```

**3. Performance Metrics:**
```
- Signal generation rate
- Trade execution latency
- Model inference time
- Risk check duration
- Total system throughput
```

**4. Trace Visualization:**
```
- Complete trace of each trade
- From tick → signal → validation → execution
- Timing at each step
- Data transformations
```

**5. Token Usage (if using LLMs):**
```
- Input/output tokens per agent
- Cost estimation
- Usage patterns
```

### 5.2 What You Can Do

**1. Interactive Testing:**
```
- Send test signals through the system
- Simulate market conditions
- Test risk scenarios
- Validate agent responses
```

**2. Debugging:**
```
- Inspect agent state at any point
- View message history
- Examine decision logic
- Identify bottlenecks
```

**3. Performance Analysis:**
```
- Compare agent execution times
- Identify slow operations
- Optimize workflows
- Track resource usage
```

**4. Live Monitoring:**
```
- Watch agents work in real-time
- See signal generation → execution flow
- Monitor risk checks
- Track performance metrics
```

---

## 6. Benefits for RiseTrader

### 6.1 Development Benefits

```
✅ Visual debugging - See exactly what each agent is doing
✅ Faster iteration - Test changes visually
✅ Better understanding - Graph shows system architecture
✅ Easy troubleshooting - Trace problems through the system
✅ Team collaboration - Share visual workflows
```

### 6.2 Production Benefits

```
✅ Real-time monitoring - Watch system health
✅ Performance insights - Identify optimization opportunities  
✅ Audit trail - Complete trace of all decisions
✅ Quick diagnosis - Rapidly identify issues
✅ Transparency - See why trades were made
```

### 6.3 Business Benefits

```
✅ Explainability - Show clients how decisions are made
✅ Compliance - Demonstrate proper risk management
✅ Confidence - See system working correctly
✅ Optimization - Data-driven improvements
✅ Documentation - Visual workflow is self-documenting
```

---

## 7. Implementation Timeline

**Add to Phase 2.5 (Agent Development):**

**Week 5 (Day 3-5): DevUI Integration**
```
Day 3:
- [ ] Install Agent Framework DevUI
- [ ] Create base wrapper classes
- [ ] Wrap first 3 agents (Signal, Risk, Execution)
- [ ] Test basic visualization

Day 4:
- [ ] Wrap remaining 7 agents
- [ ] Create trading workflow
- [ ] Integrate with orchestrator
- [ ] Test complete flow

Day 5:
- [ ] Add custom metrics
- [ ] Create custom dashboard panels
- [ ] Setup event streaming
- [ ] Document usage
- [ ] Demo to team
```

**Time Impact:** +2 days (well worth it!)

---

## 8. Alternative: What Else Do You Want?

You started to say "we also want..." but didn't finish. Here are some possibilities:

### Option 1: Real-Time Dashboard Integration
```
- Embed DevUI visualizations in React dashboard
- Show agent status in main UI
- Live workflow graph in sidebar
```

### Option 2: Agent Performance Leaderboard
```
- Compare agent performance metrics
- Show which strategies work best
- Automatic A/B testing results
```

### Option 3: Historical Replay
```
- Replay past trading sessions
- See agent decisions in hindsight
- Learn from mistakes
```

### Option 4: Alert System Integration
```
- DevUI triggers alerts on anomalies
- Slack/email notifications
- Custom alert rules
```

### Option 5: Multi-Environment View
```
- DevUI for dev, staging, production
- Compare environments side-by-side
- Deployment validation
```

**Please complete: "We also want _______________"**

---

## 9. Quick Start Commands

```bash
# Install DevUI
pip install agent-framework[devui] --pre

# Launch DevUI standalone (for testing)
agent-framework devui

# Launch with RiseTrader agents
python -m src.agents.devui_integration.launcher

# Access DevUI
open http://localhost:8090

# View with tracing enabled
ENABLE_DEVUI=true DEVUI_TRACING=true docker-compose up
```

---

## 10. Configuration Example

```yaml
# config/devui.yaml

devui:
  # Basic settings
  enabled: true
  port: 8090
  host: "0.0.0.0"
  auto_open_browser: false  # Set true for local dev
  
  # Tracing
  tracing:
    enabled: true
    framework: "opentelemetry"
    exporter:
      type: "otlp"
      endpoint: "http://jaeger:4318"
    
  # Custom dashboards
  dashboards:
    - name: "Trading Performance"
      component: "TradingPerformancePanel"
      refresh_interval_seconds: 5
    
    - name: "Risk Monitoring"
      component: "RiskMonitoringPanel"
      refresh_interval_seconds: 10
    
    - name: "Agent Health"
      component: "AgentHealthPanel"
      refresh_interval_seconds: 30
  
  # Event streaming
  events:
    buffer_size: 1000
    retention_seconds: 3600
    
  # Performance
  max_trace_depth: 10
  max_events_displayed: 100
```

---

## 11. Summary

### What We're Adding:

**Microsoft Agent Framework DevUI** - Production-ready visualization tool

### Why It's Perfect:

```
✅ Built by Microsoft - Enterprise-grade
✅ Open source - Free to use
✅ Python support - Matches our stack
✅ OpenTelemetry integration - Works with our monitoring
✅ Real-time visualization - See agents work live
✅ Easy integration - Wrapper approach keeps our MCP
✅ Production-ready - Not just a dev tool
✅ Well-documented - Lots of examples
```

### Integration Approach:

```
1. Keep our MCP server (don't replace it)
2. Create Agent Framework wrappers for our agents
3. Use DevUI to visualize wrapped agents
4. Get best of both worlds
```

### Timeline Impact:

```
+2 days in Phase 2.5 (Week 5, Day 3-5)
Total: Still 11 weeks
```

### What You Get:

```
🎨 Beautiful visual workflow graph
📊 Real-time event streaming
📈 Performance metrics dashboard
🔍 Complete trace visualization
⚡ Interactive debugging
🎯 Production monitoring
```

---

## 12. Next Steps

1. **Confirm** you want DevUI integration ✅
2. **Complete** "we also want..." statement
3. **Review** integration approach
4. **Start** implementation in Week 5

---

**DevUI will transform how you develop and monitor RiseTrader!** 🎨🤖

Instead of reading logs, you'll **SEE** your agents working together in real-time!

**Ready to add this?** Please complete your thought: "We also want _______________" so I can create a complete integration plan! 🚀