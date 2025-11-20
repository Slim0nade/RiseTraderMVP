import React, { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  DollarSign,
  TrendingUp,
  Target,
  Award,
  Activity,
} from 'lucide-react';
import { MetricCard } from '@/components/common/MetricCard';
import { PositionCard } from '@/components/trading/PositionCard';
import { AgentCard } from '@/components/agents/AgentCard';
import { PerformanceBarChart } from '@/components/charts/PerformanceBarChart';
import { tradingApi, performanceApi, agentsApi } from '@/api/endpoints';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useTradingStore } from '@/store/tradingStore';
import { useAgentStore } from '@/store/agentStore';

export const Dashboard: React.FC = () => {
  const { subscribe } = useWebSocket();
  const { positions, updatePosition } = useTradingStore();
  const { agents, updateAgent } = useAgentStore();

  // Fetch performance metrics
  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ['performance-metrics'],
    queryFn: performanceApi.getMetrics,
    refetchInterval: 5000,
  });

  // Fetch daily P&L
  const { data: dailyPnL } = useQuery({
    queryKey: ['daily-pnl'],
    queryFn: () => performanceApi.getDailyPnL(7),
    refetchInterval: 10000,
  });

  // Fetch open positions
  const { data: positionsData } = useQuery({
    queryKey: ['positions'],
    queryFn: tradingApi.getOpenPositions,
    refetchInterval: 3000,
  });

  // Fetch agents
  const { data: agentsData } = useQuery({
    queryKey: ['agents'],
    queryFn: agentsApi.getAllAgents,
    refetchInterval: 5000,
  });

  // Update stores when data changes
  useEffect(() => {
    if (positionsData) {
      positionsData.forEach(updatePosition);
    }
  }, [positionsData, updatePosition]);

  useEffect(() => {
    if (agentsData) {
      agentsData.forEach(updateAgent);
    }
  }, [agentsData, updateAgent]);

  // Subscribe to WebSocket updates
  useEffect(() => {
    const unsubscribePosition = subscribe('position_updated', (data) => {
      updatePosition(data);
    });

    const unsubscribeAgent = subscribe('agent_status_changed', (data) => {
      updateAgent(data);
    });

    return () => {
      unsubscribePosition();
      unsubscribeAgent();
    };
  }, [subscribe, updatePosition, updateAgent]);

  const activeAgents = agents.filter((a) => a.status === 'active').length;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-dark-50 mb-2">Dashboard</h1>
        <p className="text-dark-400">Real-time overview of your trading system</p>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Total P&L"
          value={metrics?.total_pnl || 0}
          format="currency"
          icon={DollarSign}
          trend={metrics && metrics.total_pnl >= 0 ? 'up' : 'down'}
          loading={metricsLoading}
        />
        <MetricCard
          title="Daily P&L"
          value={metrics?.daily_pnl || 0}
          format="currency"
          icon={TrendingUp}
          trend={metrics && metrics.daily_pnl >= 0 ? 'up' : 'down'}
          loading={metricsLoading}
        />
        <MetricCard
          title="Open Positions"
          value={metrics?.open_positions || 0}
          format="number"
          icon={Target}
          loading={metricsLoading}
        />
        <MetricCard
          title="Win Rate"
          value={metrics?.win_rate || 0}
          format="percentage"
          icon={Award}
          loading={metricsLoading}
        />
      </div>

      {/* System Status */}
      <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-primary-500" />
            <h2 className="text-xl font-semibold text-dark-50">System Status</h2>
          </div>
          <span className="text-sm text-dark-400">
            {activeAgents} / {agents.length} agents active
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
          {agents.slice(0, 5).map((agent) => (
            <AgentCard key={agent.name} agent={agent} />
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Open Positions */}
        <div>
          <h2 className="text-xl font-semibold text-dark-50 mb-4">Open Positions</h2>
          {positions.length === 0 ? (
            <div className="bg-dark-900 rounded-lg border border-dark-700 p-8 text-center text-dark-500">
              No open positions
            </div>
          ) : (
            <div className="space-y-3">
              {positions.slice(0, 3).map((position) => (
                <PositionCard key={position.id} position={position} />
              ))}
            </div>
          )}
        </div>

        {/* Daily Performance */}
        <div>
          {dailyPnL && <PerformanceBarChart data={dailyPnL} height={340} />}
        </div>
      </div>

      {/* Performance Summary */}
      {metrics && (
        <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
          <h2 className="text-xl font-semibold text-dark-50 mb-4">Performance Summary</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-dark-500 mb-1">Total Trades</p>
              <p className="text-2xl font-bold text-dark-50">{metrics.total_trades}</p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Sharpe Ratio</p>
              <p className="text-2xl font-bold text-dark-50">{metrics.sharpe_ratio.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Max Drawdown</p>
              <p className="text-2xl font-bold text-danger-500">
                {metrics.max_drawdown_pct.toFixed(2)}%
              </p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Avg Trade Duration</p>
              <p className="text-2xl font-bold text-dark-50">
                {Math.round(metrics.avg_trade_duration_minutes)}m
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
