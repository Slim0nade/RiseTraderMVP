import React, { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Activity, RefreshCw } from 'lucide-react';
import { AgentCard } from '@/components/agents/AgentCard';
import { AgentEventLog } from '@/components/agents/AgentEventLog';
import { StatusBadge } from '@/components/common/StatusBadge';
import { agentsApi } from '@/api/endpoints';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useAgentStore } from '@/store/agentStore';
import toast from 'react-hot-toast';

export const Agents: React.FC = () => {
  const queryClient = useQueryClient();
  const { subscribe } = useWebSocket();
  const { agents, updateAgent, agentEvents, addEvent } = useAgentStore();
  const [selectedAgentName, setSelectedAgentName] = useState<string | null>(null);

  // Fetch all agents
  const { data: agentsData, isLoading, refetch } = useQuery({
    queryKey: ['agents'],
    queryFn: agentsApi.getAllAgents,
    refetchInterval: 3000,
  });

  // Update store when data changes
  useEffect(() => {
    if (agentsData) {
      agentsData.forEach(updateAgent);
    }
  }, [agentsData, updateAgent]);

  // Subscribe to WebSocket events
  useEffect(() => {
    const unsubscribeAgent = subscribe('agent_status_changed', (data) => {
      updateAgent(data);
      toast.success(`${data.name} status changed to ${data.status}`);
    });

    const unsubscribeEvent = subscribe('*', (message) => {
      addEvent({
        agent_name: message.data?.agent_name || 'system',
        event_type: message.event_type,
        timestamp: message.timestamp,
        data: message.data,
        success: true,
      });
    });

    return () => {
      unsubscribeAgent();
      unsubscribeEvent();
    };
  }, [subscribe, updateAgent, addEvent]);

  // Mutations for agent control
  const startMutation = useMutation({
    mutationFn: agentsApi.startAgent,
    onSuccess: (_, agentName) => {
      toast.success(`${agentName} started successfully`);
      queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
    onError: (error, agentName) => {
      toast.error(`Failed to start ${agentName}`);
      console.error(error);
    },
  });

  const stopMutation = useMutation({
    mutationFn: agentsApi.stopAgent,
    onSuccess: (_, agentName) => {
      toast.success(`${agentName} stopped successfully`);
      queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
    onError: (error, agentName) => {
      toast.error(`Failed to stop ${agentName}`);
      console.error(error);
    },
  });

  const restartMutation = useMutation({
    mutationFn: agentsApi.restartAgent,
    onSuccess: (_, agentName) => {
      toast.success(`${agentName} restarted successfully`);
      queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
    onError: (error, agentName) => {
      toast.error(`Failed to restart ${agentName}`);
      console.error(error);
    },
  });

  const handleStart = (agentName: string) => {
    startMutation.mutate(agentName);
  };

  const handleStop = (agentName: string) => {
    stopMutation.mutate(agentName);
  };

  const handleRestart = (agentName: string) => {
    restartMutation.mutate(agentName);
  };

  const activeCount = agents.filter((a) => a.status === 'active').length;
  const errorCount = agents.filter((a) => a.status === 'error').length;

  const filteredEvents = selectedAgentName
    ? agentEvents.filter((e) => e.agent_name === selectedAgentName)
    : agentEvents;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-dark-50 mb-2">Agent Monitor</h1>
          <p className="text-dark-400">Manage and monitor all autonomous trading agents</p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Status Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-success-500/10 rounded-lg">
              <Activity className="w-6 h-6 text-success-500" />
            </div>
            <div>
              <p className="text-sm text-dark-500">Active Agents</p>
              <p className="text-3xl font-bold text-dark-50">{activeCount}</p>
            </div>
          </div>
        </div>

        <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-primary-500/10 rounded-lg">
              <Activity className="w-6 h-6 text-primary-500" />
            </div>
            <div>
              <p className="text-sm text-dark-500">Total Agents</p>
              <p className="text-3xl font-bold text-dark-50">{agents.length}</p>
            </div>
          </div>
        </div>

        <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-danger-500/10 rounded-lg">
              <Activity className="w-6 h-6 text-danger-500" />
            </div>
            <div>
              <p className="text-sm text-dark-500">Errors</p>
              <p className="text-3xl font-bold text-dark-50">{errorCount}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Agents Grid */}
      <div>
        <h2 className="text-xl font-semibold text-dark-50 mb-4">All Agents</h2>
        {isLoading ? (
          <div className="bg-dark-900 rounded-lg border border-dark-700 p-8 text-center">
            <p className="text-dark-400">Loading agents...</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {agents.map((agent) => (
              <div key={agent.name} onClick={() => setSelectedAgentName(agent.name)}>
                <AgentCard
                  agent={agent}
                  onStart={handleStart}
                  onStop={handleStop}
                  onRestart={handleRestart}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Event Log */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-dark-50">Event Log</h2>
          <div className="flex items-center gap-2">
            {selectedAgentName && (
              <>
                <StatusBadge status="active" text={selectedAgentName} />
                <button
                  onClick={() => setSelectedAgentName(null)}
                  className="text-sm text-primary-500 hover:text-primary-400"
                >
                  Clear filter
                </button>
              </>
            )}
          </div>
        </div>
        <AgentEventLog events={filteredEvents} maxHeight="max-h-[500px]" />
      </div>
    </div>
  );
};
