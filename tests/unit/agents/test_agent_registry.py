"""
Unit Tests for AgentRegistry

Tests:
- Agent registration and unregistration
- Health monitoring and heartbeat
- Circuit breaker functionality
- Agent discovery and lookup
- Status tracking
"""

import asyncio
import time

import pytest

from src.agents.agent_registry import (
    AgentRegistry,
    AgentStatus,
    AgentMetadata,
    CircuitBreaker,
    CircuitBreakerState,
)


# ============================================================================
# CIRCUIT BREAKER TESTS
# ============================================================================

class TestCircuitBreaker:
    """Test CircuitBreaker class"""
    
    def test_circuit_breaker_creation(self):
        """Test circuit breaker initialization"""
        cb = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0,
            half_open_max_calls=3,
        )
        
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0
        assert cb.failure_threshold == 5
    
    def test_circuit_breaker_record_success(self):
        """Test recording successful operation"""
        cb = CircuitBreaker()
        
        cb.record_success()
        
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0
    
    def test_circuit_breaker_record_failure(self):
        """Test recording failed operation"""
        cb = CircuitBreaker(failure_threshold=3)
        
        cb.record_failure()
        cb.record_failure()
        
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 2
    
    def test_circuit_breaker_open_on_threshold(self):
        """Test circuit opens after threshold failures"""
        cb = CircuitBreaker(failure_threshold=3)
        
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.is_open() is True
    
    def test_circuit_breaker_half_open_after_timeout(self):
        """Test circuit enters half-open state after recovery timeout"""
        cb = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0.1,  # Short timeout for testing
        )
        
        # Open circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        
        # Wait for recovery timeout
        time.sleep(0.15)
        
        # Check should trigger half-open
        cb.is_open()
        assert cb.state == CircuitBreakerState.HALF_OPEN
    
    def test_circuit_breaker_close_after_half_open_successes(self):
        """Test circuit closes after successful half-open calls"""
        cb = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0.1,
            half_open_max_calls=3,
        )
        
        # Open circuit
        cb.record_failure()
        cb.record_failure()
        
        # Wait and trigger half-open
        time.sleep(0.15)
        cb.is_open()
        
        # Record successes in half-open
        cb.record_success()
        cb.record_success()
        cb.record_success()
        
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0


# ============================================================================
# AGENT METADATA TESTS
# ============================================================================

class TestAgentMetadata:
    """Test AgentMetadata class"""
    
    def test_agent_metadata_creation(self):
        """Test agent metadata creation"""
        metadata = AgentMetadata(
            agent_id="test_agent",
            agent_class="TestAgent",
            priority=5,
        )
        
        assert metadata.agent_id == "test_agent"
        assert metadata.agent_class == "TestAgent"
        assert metadata.status == AgentStatus.STARTING
        assert metadata.priority == 5
    
    def test_agent_metadata_serialization(self):
        """Test metadata to_dict"""
        metadata = AgentMetadata(
            agent_id="test_agent",
            agent_class="TestAgent",
        )
        
        data = metadata.to_dict()
        
        assert data["agent_id"] == "test_agent"
        assert data["agent_class"] == "TestAgent"
        assert "status" in data
        assert "priority" in data
    
    def test_agent_metadata_deserialization(self):
        """Test metadata from_dict"""
        data = {
            "agent_id": "test_agent",
            "agent_class": "TestAgent",
            "status": "running",
            "priority": 5,
            "config": {"key": "value"},
            "registered_at": time.time(),
            "last_heartbeat": time.time(),
            "error_count": 0,
            "circuit_breaker_state": 0,
            "metadata": {},
        }
        
        metadata = AgentMetadata.from_dict(data)
        
        assert metadata.agent_id == "test_agent"
        assert metadata.status == AgentStatus.RUNNING
        assert metadata.priority == 5


# ============================================================================
# AGENT REGISTRATION TESTS
# ============================================================================

class TestAgentRegistration:
    """Test agent registration functionality"""
    
    @pytest.mark.asyncio
    async def test_register_agent(self, agent_registry):
        """Test registering new agent"""
        metadata = await agent_registry.register(
            agent_id="test_agent",
            agent_class="TestAgent",
            priority=5,
        )
        
        assert metadata.agent_id == "test_agent"
        assert metadata.agent_class == "TestAgent"
        assert metadata.status == AgentStatus.STARTING
        assert "test_agent" in agent_registry.agents
    
    @pytest.mark.asyncio
    async def test_register_with_config(self, agent_registry):
        """Test registering agent with configuration"""
        config = {"key": "value", "timeout": 30}
        
        metadata = await agent_registry.register(
            agent_id="test_agent",
            agent_class="TestAgent",
            config=config,
        )
        
        assert metadata.config == config
    
    @pytest.mark.asyncio
    async def test_register_creates_circuit_breaker(self, agent_registry):
        """Test registration creates circuit breaker"""
        await agent_registry.register(
            agent_id="test_agent",
            agent_class="TestAgent",
        )
        
        assert "test_agent" in agent_registry.circuit_breakers
        assert isinstance(agent_registry.circuit_breakers["test_agent"], CircuitBreaker)
    
    @pytest.mark.asyncio
    async def test_unregister_agent(self, agent_registry):
        """Test unregistering agent"""
        await agent_registry.register(
            agent_id="test_agent",
            agent_class="TestAgent",
        )
        
        await agent_registry.unregister("test_agent")
        
        assert "test_agent" not in agent_registry.agents
        assert "test_agent" not in agent_registry.circuit_breakers


# ============================================================================
# HEARTBEAT TESTS
# ============================================================================

class TestHeartbeat:
    """Test heartbeat functionality"""
    
    @pytest.mark.asyncio
    async def test_heartbeat_updates_timestamp(self, agent_registry):
        """Test heartbeat updates last_heartbeat"""
        await agent_registry.register(
            agent_id="test_agent",
            agent_class="TestAgent",
        )
        
        agent = agent_registry.agents["test_agent"]
        old_heartbeat = agent.last_heartbeat
        
        await asyncio.sleep(0.1)
        await agent_registry.heartbeat("test_agent")
        
        assert agent.last_heartbeat > old_heartbeat
    
    @pytest.mark.asyncio
    async def test_heartbeat_records_circuit_breaker_success(self, agent_registry):
        """Test heartbeat records success in circuit breaker"""
        await agent_registry.register(
            agent_id="test_agent",
            agent_class="TestAgent",
        )
        
        # Record failure
        await agent_registry.record_error("test_agent", "test error")
        
        # Heartbeat should record success
        await agent_registry.heartbeat("test_agent")
        
        # Circuit breaker should reset failure count
        cb = agent_registry.circuit_breakers["test_agent"]
        assert cb.state == CircuitBreakerState.CLOSED
    
    @pytest.mark.asyncio
    async def test_heartbeat_timeout_marks_failed(self, agent_registry):
        """Test agent marked failed after heartbeat timeout"""
        # Short timeout for testing
        agent_registry.heartbeat_timeout = 0.5
        
        await agent_registry.register(
            agent_id="test_agent",
            agent_class="TestAgent",
        )
        
        await agent_registry.update_status("test_agent", AgentStatus.RUNNING)
        
        # Wait for timeout
        await asyncio.sleep(0.6)
        
        # Trigger health check
        await agent_registry._check_agent_health()
        
        agent = agent_registry.agents["test_agent"]
        assert agent.status == AgentStatus.FAILED


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Test error handling functionality"""
    
    @pytest.mark.asyncio
    async def test_record_error_increments_count(self, agent_registry):
        """Test recording error increments count"""
        await agent_registry.register(
            agent_id="test_agent",
            agent_class="TestAgent",
        )
        
        agent = agent_registry.agents["test_agent"]
        initial_count = agent.error_count
        
        await agent_registry.record_error("test_agent", "Test error")
        
        assert agent.error_count == initial_count + 1
    
    @pytest.mark.asyncio
    async def test_record_error_updates_circuit_breaker(self, agent_registry):
        """Test recording error updates circuit breaker"""
        await agent_registry.register(
            agent_id="test_agent",
            agent_class="TestAgent",
        )
        
        cb = agent_registry.circuit_breakers["test_agent"]
        initial_failures = cb.failure_count
        
        await agent_registry.record_error("test_agent", "Test error")
        
        assert cb.failure_count == initial_failures + 1
    
    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold_errors(self, agent_registry):
        """Test circuit breaker opens after threshold errors"""
        agent_registry.failure_threshold = 3
        
        await agent_registry.register(
            agent_id="test_agent",
            agent_class="TestAgent",
        )
        
        # Record errors until threshold
        for _ in range(3):
            await agent_registry.record_error("test_agent", "Test error")
        
        assert agent_registry.is_circuit_open("test_agent") is True
        
        # Agent should be marked failed
        agent = agent_registry.agents["test_agent"]
        assert agent.status == AgentStatus.FAILED


# ============================================================================
# STATUS MANAGEMENT TESTS
# ============================================================================

class TestStatusManagement:
    """Test agent status management"""
    
    @pytest.mark.asyncio
    async def test_update_agent_status(self, agent_registry):
        """Test updating agent status"""
        await agent_registry.register(
            agent_id="test_agent",
            agent_class="TestAgent",
        )
        
        await agent_registry.update_status("test_agent", AgentStatus.RUNNING)
        
        agent = agent_registry.agents["test_agent"]
        assert agent.status == AgentStatus.RUNNING
    
    @pytest.mark.asyncio
    async def test_update_status_invalid_agent(self, agent_registry):
        """Test updating status of non-existent agent"""
        # Should not raise error
        await agent_registry.update_status("invalid_agent", AgentStatus.RUNNING)


# ============================================================================
# AGENT DISCOVERY TESTS
# ============================================================================

class TestAgentDiscovery:
    """Test agent discovery functionality"""
    
    @pytest.mark.asyncio
    async def test_get_agent(self, agent_registry):
        """Test getting agent metadata"""
        await agent_registry.register(
            agent_id="test_agent",
            agent_class="TestAgent",
        )
        
        agent = await agent_registry.get_agent("test_agent")
        
        assert agent is not None
        assert agent.agent_id == "test_agent"
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_agent(self, agent_registry):
        """Test getting non-existent agent returns None"""
        agent = await agent_registry.get_agent("invalid_agent")
        
        assert agent is None
    
    @pytest.mark.asyncio
    async def test_list_all_agents(self, agent_registry):
        """Test listing all agents"""
        await agent_registry.register("agent1", "Agent1")
        await agent_registry.register("agent2", "Agent2")
        await agent_registry.register("agent3", "Agent3")
        
        agents = await agent_registry.list_agents()
        
        assert len(agents) == 3
    
    @pytest.mark.asyncio
    async def test_list_agents_by_status(self, agent_registry):
        """Test listing agents filtered by status"""
        await agent_registry.register("agent1", "Agent1")
        await agent_registry.register("agent2", "Agent2")
        await agent_registry.register("agent3", "Agent3")
        
        await agent_registry.update_status("agent1", AgentStatus.RUNNING)
        await agent_registry.update_status("agent2", AgentStatus.RUNNING)
        await agent_registry.update_status("agent3", AgentStatus.PAUSED)
        
        running_agents = await agent_registry.list_agents(status=AgentStatus.RUNNING)
        
        assert len(running_agents) == 2
    
    @pytest.mark.asyncio
    async def test_list_agents_sorted_by_priority(self, agent_registry):
        """Test agents listed in priority order"""
        await agent_registry.register("agent1", "Agent1", priority=5)
        await agent_registry.register("agent2", "Agent2", priority=1)
        await agent_registry.register("agent3", "Agent3", priority=3)
        
        agents = await agent_registry.list_agents()
        
        # Should be sorted by priority (lowest first)
        assert agents[0].agent_id == "agent2"  # priority 1
        assert agents[1].agent_id == "agent3"  # priority 3
        assert agents[2].agent_id == "agent1"  # priority 5
    
    @pytest.mark.asyncio
    async def test_get_agents_by_priority(self, agent_registry):
        """Test getting agents by specific priority"""
        await agent_registry.register("agent1", "Agent1", priority=5)
        await agent_registry.register("agent2", "Agent2", priority=1)
        await agent_registry.register("agent3", "Agent3", priority=5)
        
        priority_5_agents = await agent_registry.get_agents_by_priority(5)
        
        assert len(priority_5_agents) == 2


# ============================================================================
# STATISTICS TESTS
# ============================================================================

class TestRegistryStatistics:
    """Test registry statistics"""
    
    @pytest.mark.asyncio
    async def test_get_stats(self, agent_registry):
        """Test getting registry statistics"""
        await agent_registry.register("agent1", "Agent1")
        await agent_registry.register("agent2", "Agent2")
        
        await agent_registry.update_status("agent1", AgentStatus.RUNNING)
        await agent_registry.update_status("agent2", AgentStatus.PAUSED)
        
        stats = await agent_registry.get_stats()
        
        assert stats["total_agents"] == 2
        assert "status_counts" in stats
        assert stats["status_counts"]["running"] == 1
        assert stats["status_counts"]["paused"] == 1
        assert "circuit_breaker_states" in stats
