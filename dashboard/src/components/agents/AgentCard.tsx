import React, { useState } from 'react';
import { Play, Square, RotateCw, Activity, AlertCircle } from 'lucide-react';
import { Agent } from '@/types';
import { StatusBadge } from '@/components/common/StatusBadge';
import { useFormatters } from '@/hooks/useFormatters';
import { cn } from '@/utils/cn';

interface AgentCardProps {
  agent: Agent;
  onStart?: (agentName: string) => void;
  onStop?: (agentName: string) => void;
  onRestart?: (agentName: string) => void;
}

export const AgentCard: React.FC<AgentCardProps> = ({ agent, onStart, onStop, onRestart }) => {
  const [showDetails, setShowDetails] = useState(false);
  const formatters = useFormatters();

  const isActive = agent.status === 'active';
  const canStart = agent.status === 'stopped' || agent.status === 'error';
  const canStop = agent.status === 'active' || agent.status === 'idle';

  return (
    <div className="bg-dark-900 rounded-lg border border-dark-700 p-4 hover:border-dark-600 transition-colors">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <h3 className="font-semibold text-dark-50 mb-1">{agent.name}</h3>
          <StatusBadge status={agent.status} />
        </div>
        <div className="flex items-center gap-1">
          {canStart && onStart && (
            <button
              onClick={() => onStart(agent.name)}
              className="p-1.5 hover:bg-dark-800 rounded transition-colors"
              title="Start agent"
            >
              <Play className="w-4 h-4 text-success-500" />
            </button>
          )}
          {canStop && onStop && (
            <button
              onClick={() => onStop(agent.name)}
              className="p-1.5 hover:bg-dark-800 rounded transition-colors"
              title="Stop agent"
            >
              <Square className="w-4 h-4 text-danger-500" />
            </button>
          )}
          {onRestart && (
            <button
              onClick={() => onRestart(agent.name)}
              className="p-1.5 hover:bg-dark-800 rounded transition-colors"
              title="Restart agent"
            >
              <RotateCw className="w-4 h-4 text-primary-500" />
            </button>
          )}
        </div>
      </div>

      {/* Last Active */}
      <div className="mb-3">
        <p className="text-xs text-dark-500">Last Active</p>
        <p className="text-sm text-dark-300">{formatters.relativeTime(agent.last_active)}</p>
      </div>

      {/* Last Event */}
      {agent.last_event && (
        <div className="mb-3">
          <p className="text-xs text-dark-500">Last Event</p>
          <p className="text-sm text-dark-300 font-mono truncate">{agent.last_event}</p>
        </div>
      )}

      {/* Error Message */}
      {agent.error_message && (
        <div className="mb-3 p-2 bg-danger-500/10 rounded border border-danger-500/20">
          <div className="flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-danger-500 mt-0.5 flex-shrink-0" />
            <p className="text-xs text-danger-400">{agent.error_message}</p>
          </div>
        </div>
      )}

      {/* Metrics */}
      {agent.metrics && (
        <div className="grid grid-cols-3 gap-2 mb-3 p-2 bg-dark-800 rounded">
          <div>
            <p className="text-xs text-dark-500">Events</p>
            <p className="text-sm font-bold text-dark-200">{agent.metrics.events_processed}</p>
          </div>
          <div>
            <p className="text-xs text-dark-500">Avg Time</p>
            <p className="text-sm font-bold text-dark-200">{agent.metrics.avg_response_time_ms}ms</p>
          </div>
          <div>
            <p className="text-xs text-dark-500">Success</p>
            <p className="text-sm font-bold text-dark-200">
              {formatters.percentage(agent.metrics.success_rate * 100)}
            </p>
          </div>
        </div>
      )}

      {/* State Details */}
      {Object.keys(agent.state || {}).length > 0 && (
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="w-full text-xs text-primary-500 hover:text-primary-400 transition-colors flex items-center justify-center gap-1"
        >
          <Activity className="w-3 h-3" />
          {showDetails ? 'Hide' : 'Show'} State
        </button>
      )}

      {showDetails && agent.state && (
        <div className="mt-2 p-2 bg-dark-950 rounded overflow-auto max-h-32">
          <pre className="text-xs text-dark-400">
            {JSON.stringify(agent.state, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
};
