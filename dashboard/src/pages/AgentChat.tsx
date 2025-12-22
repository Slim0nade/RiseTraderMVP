import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MessageSquare, Filter, RefreshCw, AlertCircle, TrendingUp } from 'lucide-react';
import { backtestApi } from '@/api/endpoints';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { AgentConversation } from '@/components/agents/AgentConversation';
import type { AgentDecision } from '@/types';

export const AgentChat: React.FC = () => {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [filterAgentType, setFilterAgentType] = useState<string>('all');
  const [filterDecisionType, setFilterDecisionType] = useState<string>('all');

  // Fetch all backtest runs (to select from)
  const { data: runsResponse, isLoading: runsLoading } = useQuery({
    queryKey: ['backtest-runs'],
    queryFn: () => backtestApi.listRuns({ limit: 50 }),
  });

  // Fetch agent decisions for selected run
  const {
    data: decisionsData,
    isLoading: decisionsLoading,
    refetch: refetchDecisions,
  } = useQuery({
    queryKey: ['agent-decisions', selectedRunId],
    queryFn: () => backtestApi.getRunDecisions(selectedRunId!, { limit: 1000 }),
    enabled: !!selectedRunId,
  });

  // Filter decisions based on selected filters
  const filteredDecisions = React.useMemo(() => {
    if (!decisionsData?.items) return [];

    let filtered = decisionsData.items as AgentDecision[];

    if (filterDecisionType !== 'all') {
      filtered = filtered.filter((d) => d.decision_type === filterDecisionType);
    }

    // Additional filtering can be added here

    return filtered;
  }, [decisionsData, filterDecisionType]);

  // Get unique agent types from decisions
  const agentTypes = React.useMemo(() => {
    if (!decisionsData?.items) return [];
    const types = new Set<string>();
    decisionsData.items.forEach((d: any) => {
      if (d.agent_name) types.add(d.agent_name);
    });
    return Array.from(types);
  }, [decisionsData]);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-dark-50 mb-2">Agent Interactions</h1>
        <p className="text-dark-400">
          View agent decision-making conversations and reasoning
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Sidebar - Run Selection */}
        <div className="lg:col-span-1">
          <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-dark-50">Backtest Runs</h2>
              <button
                onClick={() => window.location.reload()}
                className="p-2 hover:bg-dark-800 rounded-lg transition-colors"
              >
                <RefreshCw className="w-4 h-4 text-dark-400" />
              </button>
            </div>

            {runsLoading ? (
              <LoadingSpinner />
            ) : runsResponse?.items.length === 0 ? (
              <div className="text-center py-8">
                <MessageSquare className="w-12 h-12 text-dark-600 mx-auto mb-3" />
                <p className="text-dark-500 text-sm">No runs found</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-[600px] overflow-y-auto">
                {runsResponse?.items
                  .filter((run: any) => run.agent_decisions_count > 0)
                  .map((run: any) => (
                    <button
                      key={run.id}
                      onClick={() => setSelectedRunId(run.id)}
                      className={`w-full text-left p-3 rounded-lg border transition-all ${
                        selectedRunId === run.id
                          ? 'bg-primary-500/10 border-primary-500/50'
                          : 'bg-dark-800 border-dark-700 hover:border-dark-600'
                      }`}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <h3 className="font-medium text-dark-50 text-sm">
                          {run.config?.name || `Run ${run.id.slice(0, 8)}`}
                        </h3>
                        <span className="text-xs text-primary-500">
                          {run.agent_decisions_count} decisions
                        </span>
                      </div>
                      <div className="space-y-1 text-xs text-dark-500">
                        <p>Status: {run.status}</p>
                        <p>Trades: {run.total_trades}</p>
                      </div>
                    </button>
                  ))}
                {runsResponse?.items.filter((run: any) => run.agent_decisions_count > 0)
                  .length === 0 && (
                  <div className="text-center py-8">
                    <AlertCircle className="w-12 h-12 text-warning-500 mx-auto mb-3" />
                    <p className="text-dark-400 text-sm">
                      No runs with agent decisions found
                    </p>
                    <p className="text-dark-600 text-xs mt-1">
                      Run a backtest in full_pipeline mode to see agent interactions
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Main Content - Agent Conversations */}
        <div className="lg:col-span-3">
          {!selectedRunId ? (
            <div className="bg-dark-900 rounded-lg border border-dark-700 p-12 text-center">
              <MessageSquare className="w-16 h-16 text-dark-600 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-dark-300 mb-2">
                Select a backtest run
              </h3>
              <p className="text-dark-500 text-sm">
                Choose a run from the left to view agent decision conversations
              </p>
            </div>
          ) : decisionsLoading ? (
            <div className="bg-dark-900 rounded-lg border border-dark-700 p-12">
              <LoadingSpinner />
              <p className="text-dark-400 text-center mt-4">Loading agent decisions...</p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Filters */}
              <div className="bg-dark-900 rounded-lg border border-dark-700 p-4">
                <div className="flex items-center gap-4">
                  <Filter className="w-5 h-5 text-dark-400" />
                  <div className="flex items-center gap-3 flex-1">
                    <div className="flex items-center gap-2">
                      <label className="text-sm text-dark-400">Decision Type:</label>
                      <select
                        value={filterDecisionType}
                        onChange={(e) => setFilterDecisionType(e.target.value)}
                        className="bg-dark-800 border border-dark-600 rounded px-3 py-1.5 text-sm text-dark-50 focus:outline-none focus:border-primary-500"
                      >
                        <option value="all">All</option>
                        <option value="BUY">Buy</option>
                        <option value="SELL">Sell</option>
                        <option value="HOLD">Hold</option>
                      </select>
                    </div>

                    <button
                      onClick={() => refetchDecisions()}
                      className="ml-auto text-sm text-primary-500 hover:text-primary-400 flex items-center gap-2"
                    >
                      <RefreshCw className="w-4 h-4" />
                      Refresh
                    </button>
                  </div>
                </div>
              </div>

              {/* Decision Stats */}
              <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
                <h3 className="text-sm font-medium text-dark-300 mb-4">Decision Summary</h3>
                <div className="grid grid-cols-4 gap-4">
                  <div>
                    <p className="text-xs text-dark-500 mb-1">Total Decisions</p>
                    <p className="text-2xl font-bold text-dark-50">
                      {decisionsData?.total || 0}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-dark-500 mb-1">Buy Signals</p>
                    <p className="text-2xl font-bold text-success-500">
                      {
                        (decisionsData?.items as AgentDecision[])?.filter(
                          (d) => d.decision_type === 'BUY'
                        ).length || 0
                      }
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-dark-500 mb-1">Sell Signals</p>
                    <p className="text-2xl font-bold text-danger-500">
                      {
                        (decisionsData?.items as AgentDecision[])?.filter(
                          (d) => d.decision_type === 'SELL'
                        ).length || 0
                      }
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-dark-500 mb-1">Hold Signals</p>
                    <p className="text-2xl font-bold text-warning-500">
                      {
                        (decisionsData?.items as AgentDecision[])?.filter(
                          (d) => d.decision_type === 'HOLD'
                        ).length || 0
                      }
                    </p>
                  </div>
                </div>
              </div>

              {/* Agent Conversation */}
              {filteredDecisions.length > 0 ? (
                <AgentConversation decisions={filteredDecisions} />
              ) : (
                <div className="bg-dark-900 rounded-lg border border-dark-700 p-12 text-center">
                  <TrendingUp className="w-16 h-16 text-dark-600 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-dark-300 mb-2">
                    No decisions match filters
                  </h3>
                  <p className="text-dark-500 text-sm">
                    Try adjusting your filters to see more results
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
