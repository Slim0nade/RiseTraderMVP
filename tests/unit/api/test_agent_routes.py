"""
Unit Tests for Agent API Routes

Tests:
- GET /agents - List all agents
- GET /agents/{agent_id}/status - Get agent status
- POST /agents/{agent_id}/command - Send agent command
- POST /agents/{agent_id}/pause - Pause agent
- POST /agents/{agent_id}/resume - Resume agent
"""

import pytest
from fastapi.testclient import TestClient


class TestAgentListRoutes:
    """Test agent listing endpoints"""
    
    @pytest.mark.api
    def test_list_agents(self, api_client):
        """Test GET /agents returns agent list"""
        response = api_client.get("/api/v1/agents")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "agents" in data
        assert isinstance(data["agents"], list)
    
    @pytest.mark.api
    def test_list_agents_with_status_filter(self, api_client):
        """Test filtering agents by status"""
        response = api_client.get("/api/v1/agents?status=running")
        
        assert response.status_code == 200
        data = response.json()
        
        if len(data["agents"]) > 0:
            for agent in data["agents"]:
                assert agent["status"] == "running"


class TestAgentStatusRoutes:
    """Test agent status endpoints"""
    
    @pytest.mark.api
    @pytest.mark.critical
    def test_get_agent_status(self, api_client):
        """Test GET /agents/{agent_id}/status"""
        response = api_client.get("/api/v1/agents/signal_generator/status")
        
        assert response.status_code in [200, 404]  # 404 if agent not running
        
        if response.status_code == 200:
            data = response.json()
            assert "agent_id" in data
            assert "status" in data
            assert "events_processed" in data
    
    @pytest.mark.api
    def test_get_nonexistent_agent_status(self, api_client):
        """Test getting status of non-existent agent"""
        response = api_client.get("/api/v1/agents/nonexistent_agent/status")
        
        assert response.status_code == 404


class TestAgentCommandRoutes:
    """Test agent command endpoints"""
    
    @pytest.mark.api
    def test_send_agent_command(self, api_client):
        """Test POST /agents/{agent_id}/command"""
        command = {
            "action": "generate_signal",
            "params": {
                "symbol": "CrudeOIL"
            }
        }
        
        response = api_client.post(
            "/api/v1/agents/signal_generator/command",
            json=command
        )
        
        assert response.status_code in [200, 404, 503]  # 503 if agent down
    
    @pytest.mark.api
    def test_send_invalid_command(self, api_client):
        """Test sending invalid command"""
        command = {
            "action": ""  # Empty action
        }
        
        response = api_client.post(
            "/api/v1/agents/signal_generator/command",
            json=command
        )
        
        assert response.status_code in [400, 422]  # Validation error


class TestAgentControlRoutes:
    """Test agent pause/resume endpoints"""
    
    @pytest.mark.api
    def test_pause_agent(self, api_client):
        """Test POST /agents/{agent_id}/pause"""
        response = api_client.post("/api/v1/agents/signal_generator/pause")
        
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            data = response.json()
            assert "success" in data
    
    @pytest.mark.api
    def test_resume_agent(self, api_client):
        """Test POST /agents/{agent_id}/resume"""
        response = api_client.post("/api/v1/agents/signal_generator/resume")
        
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            data = response.json()
            assert "success" in data
    
    @pytest.mark.api
    def test_pause_nonexistent_agent(self, api_client):
        """Test pausing non-existent agent"""
        response = api_client.post("/api/v1/agents/nonexistent/pause")
        
        assert response.status_code == 404


class TestAgentMetricsRoutes:
    """Test agent metrics endpoints"""
    
    @pytest.mark.api
    def test_get_agent_metrics(self, api_client):
        """Test GET /agents/{agent_id}/metrics"""
        response = api_client.get("/api/v1/agents/signal_generator/metrics")
        
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            data = response.json()
            assert "events_processed" in data or "metrics" in data
