import React, { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Play, RefreshCw, TrendingUp, BarChart3, AlertCircle, Plus, Loader2 } from 'lucide-react';
import { backtestApi } from '@/api/endpoints';
import { useBacktestStore } from '@/store/backtestStore';
import { AgentDecisionList } from '@/components/backtesting/AgentDecisionList';
import { MetricsTable } from '@/components/backtesting/MetricsTable';
import { EquityCurveChart } from '@/components/backtesting/EquityCurveChart';
import { RunStatusBadge } from '@/components/backtesting/RunStatusBadge';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { CreateBacktestModal } from '@/components/backtesting/CreateBacktestModal';
import { format } from 'date-fns';
import type { BacktestRun, AgentDecision, SimulatedTrade } from '@/types';

export const Backtesting: React.FC = () => {
  const { selectedRun, setSelectedRun, setDecisions, decisions, setTrades, trades } =
    useBacktestStore();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [runningConfigs, setRunningConfigs] = useState<Set<string>>(new Set());

  // Fetch configurations
  const { data: configsResponse, isLoading: configsLoading } = useQuery({
    queryKey: ['backtest-configurations'],
    queryFn: () => backtestApi.getConfigurations({ limit: 50 }),
    refetchInterval: 10000,
  });

  // Fetch the latest run for each config to show accurate statuses
  const { data: allRunsData } = useQuery({
    queryKey: ['all-backtest-runs'],
    queryFn: async () => {
      const runsResponse = await backtestApi.listRuns({ limit: 100 });
      return runsResponse.items;
    },
    refetchInterval: 10000,
  });

  // Fetch run status if a run is selected
  const {
    data: runData,
    isLoading: runLoading,
    refetch: refetchRun,
  } = useQuery({
    queryKey: ['backtest-run', selectedRunId],
    queryFn: () => backtestApi.getRunStatus(selectedRunId!),
    enabled: !!selectedRunId,
    refetchInterval: (data) => {
      // Poll every 2 seconds if running, otherwise don't poll
      return data?.status === 'running' || data?.status === 'pending' ? 2000 : false;
    },
  });

  // Fetch the configuration for the selected run
  const { data: selectedConfig } = useQuery({
    queryKey: ['backtest-config', runData?.config_id],
    queryFn: () => backtestApi.getConfigurations({ limit: 100 }).then(response =>
      response.items.find((config: any) => config.id === runData?.config_id)
    ),
    enabled: !!runData?.config_id,
  });

  // Fetch run metrics
  const { data: metricsData } = useQuery({
    queryKey: ['backtest-metrics', selectedRunId],
    queryFn: () => backtestApi.getRunMetrics(selectedRunId!),
    enabled: !!selectedRunId && runData?.status === 'completed',
  });

  // Fetch trades
  const { data: tradesData } = useQuery({
    queryKey: ['backtest-trades', selectedRunId],
    queryFn: () => backtestApi.getRunTrades(selectedRunId!, { limit: 1000 }),
    enabled: !!selectedRunId && runData?.status === 'completed',
  });


  // Fetch agent decisions
  const { data: decisionsData } = useQuery({
    queryKey: ['backtest-decisions', selectedRunId],
    queryFn: () => backtestApi.getRunDecisions(selectedRunId!, { limit: 1000 }),
    enabled: !!selectedRunId && (runData?.agent_decisions_count || 0) > 0,
  });

  useEffect(() => {
    if (runData) {
      setSelectedRun(runData as BacktestRun);
    }
  }, [runData, setSelectedRun]);

  useEffect(() => {
    if (tradesData) {
      setTrades(tradesData.items as SimulatedTrade[]);
    }
  }, [tradesData, setTrades]);

  useEffect(() => {
    if (decisionsData) {
      setDecisions(decisionsData.items as AgentDecision[]);
    }
  }, [decisionsData, setDecisions]);

  // Helper function to get the latest run for a config
  const getLatestRunForConfig = (configId: string) => {
    if (!allRunsData) return null;
    // Find the most recent run for this config (runs are sorted by start_time DESC)
    return allRunsData.find((run: any) => run.config_id === configId) || null;
  };

  const handleSelectRun = async (configId: string) => {
    // Fetch the most recent run for this config
    try {
      const runsResponse = await backtestApi.listRuns({ config_id: configId, limit: 1 });
      if (runsResponse.items.length > 0) {
        // Use the most recent run ID (sorted by start_time DESC from API)
        setSelectedRunId(runsResponse.items[0].id);
      } else {
        // No runs for this config yet
        setSelectedRunId(null);
      }
    } catch (error) {
      console.error('Failed to fetch runs for config:', error);
      setSelectedRunId(null);
    }
  };

  const handleStartRun = async (configId: string, event: React.MouseEvent) => {
    event.stopPropagation(); // Prevent triggering handleSelectRun

    setRunningConfigs(prev => new Set(prev).add(configId));

    try {
      // Start a new backtest run for this config
      const run = await backtestApi.runBacktest({
        config_id: configId,
        timeframe: 'M1', // Use M1 - we have data until Nov 2025 (M5 only goes to Dec 2024)
      });

      // Select the newly created run
      setSelectedRunId(run.run_id);

      // Remove from running set
      setRunningConfigs(prev => {
        const newSet = new Set(prev);
        newSet.delete(configId);
        return newSet;
      });
    } catch (error) {
      console.error('Failed to start backtest run:', error);
      setRunningConfigs(prev => {
        const newSet = new Set(prev);
        newSet.delete(configId);
        return newSet;
      });
    }
  };

  const handleBacktestCreated = (runId: string) => {
    // Set the newly created run as selected
    setSelectedRunId(runId);
    // Refetch configurations to show the new one
    window.location.reload(); // Simple refresh - could be improved with query invalidation
  };

  // Create equity curve data from trades
  const createEquityCurveData = () => {
    if (!metricsData?.final_capital || !tradesData?.items) return [];

    const initialCapital = metricsData.config_id ? 10000 : 10000; // Get from config
    let currentCapital = initialCapital;
    const equityPoints: { time: number; value: number }[] = [];

    // Add initial point
    if (runData?.start_time) {
      equityPoints.push({
        time: Math.floor(new Date(runData.start_time).getTime() / 1000),
        value: initialCapital,
      });
    }

    // Add points for each closed trade
    tradesData.items
      .filter((trade: any) => trade.exit_timestamp)
      .sort(
        (a: any, b: any) =>
          new Date(a.exit_timestamp).getTime() - new Date(b.exit_timestamp).getTime()
      )
      .forEach((trade: any) => {
        currentCapital += trade.pnl || 0;
        equityPoints.push({
          time: Math.floor(new Date(trade.exit_timestamp).getTime() / 1000),
          value: currentCapital,
        });
      });

    return equityPoints;
  };

  const equityCurveData = createEquityCurveData();

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-dark-50 mb-2">Backtesting</h1>
          <p className="text-dark-400">
            Analyze agent-mode backtest results and agent decisions
          </p>
        </div>
        <button
          onClick={() => setIsCreateModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-primary-500 hover:bg-primary-600 text-white rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          Create Backtest
        </button>
      </div>

      {/* Create Backtest Modal */}
      <CreateBacktestModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onSuccess={handleBacktestCreated}
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Configurations List */}
        <div className="lg:col-span-1">
          <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-dark-50">
                Backtest Configurations
              </h2>
              <button
                onClick={() => window.location.reload()}
                className="p-2 hover:bg-dark-800 rounded-lg transition-colors"
              >
                <RefreshCw className="w-4 h-4 text-dark-400" />
              </button>
            </div>

            {configsLoading ? (
              <LoadingSpinner />
            ) : configsResponse?.items.length === 0 ? (
              <div className="text-center py-8">
                <BarChart3 className="w-12 h-12 text-dark-600 mx-auto mb-3" />
                <p className="text-dark-500 text-sm">No configurations found</p>
                <p className="text-dark-600 text-xs mt-1">
                  Run a backtest from the terminal to see results here
                </p>
              </div>
            ) : (
              <div className="space-y-2 max-h-[600px] overflow-y-auto">
                {configsResponse?.items.map((config: any) => {
                  const latestRun = getLatestRunForConfig(config.id);
                  return (
                    <button
                      key={config.id}
                      onClick={() => handleSelectRun(config.id)}
                      className={`w-full text-left p-4 rounded-lg border transition-all ${
                        selectedRunId === config.id
                          ? 'bg-primary-500/10 border-primary-500/50'
                          : 'bg-dark-800 border-dark-700 hover:border-dark-600'
                      }`}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <h3 className="font-medium text-dark-50 text-sm">
                          {config.name}
                        </h3>
                        {latestRun ? (
                          <RunStatusBadge
                            status={latestRun.status}
                            size="sm"
                          />
                        ) : runningConfigs.has(config.id) ? (
                          <div className="flex items-center gap-1 px-2 py-1 bg-primary-500/10 border border-primary-500/50 rounded text-xs text-primary-400">
                            <Loader2 className="w-3 h-3 animate-spin" />
                            <span>Starting...</span>
                          </div>
                        ) : (
                          <button
                            onClick={(e) => handleStartRun(config.id, e)}
                            className="flex items-center gap-1 px-2 py-1 bg-success-500/10 border border-success-500/50 rounded text-xs text-success-400 hover:bg-success-500/20 transition-colors"
                          >
                            <Play className="w-3 h-3" />
                            <span>Run</span>
                          </button>
                        )}
                      </div>
                      <div className="space-y-1 text-xs text-dark-500">
                        <p>Symbol: {config.symbol}</p>
                        <p>
                          Period: {format(new Date(config.start_date), 'MMM dd')} -{' '}
                          {format(new Date(config.end_date), 'MMM dd, yyyy')}
                        </p>
                        <p>
                          Mode:{' '}
                          {config.execution_mode === 'full_pipeline'
                            ? 'Agent Pipeline'
                            : 'Synthetic'}
                        </p>
                        <p>Capital: ${config.initial_capital.toLocaleString()}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Results Panel */}
        <div className="lg:col-span-2">
          {!selectedRunId ? (
            <div className="bg-dark-900 rounded-lg border border-dark-700 p-12 text-center">
              <TrendingUp className="w-16 h-16 text-dark-600 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-dark-300 mb-2">
                Select a backtest configuration
              </h3>
              <p className="text-dark-500 text-sm">
                Choose a configuration from the left to view detailed results and agent
                decisions
              </p>
            </div>
          ) : runLoading ? (
            <div className="bg-dark-900 rounded-lg border border-dark-700 p-12">
              <LoadingSpinner />
              <p className="text-dark-400 text-center mt-4">Loading backtest data...</p>
            </div>
          ) : runData?.status === 'running' || runData?.status === 'pending' ? (
            <div className="bg-dark-900 rounded-lg border border-dark-700 p-12 text-center">
              <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-primary-500 mx-auto mb-4"></div>
              <h3 className="text-lg font-medium text-dark-300 mb-2">
                Backtest in Progress
              </h3>
              <p className="text-dark-500 text-sm mb-4">
                Candles processed: {runData.candles_processed} | Decisions:{' '}
                {runData.agent_decisions_count}
              </p>
              <button
                onClick={() => refetchRun()}
                className="text-primary-500 hover:text-primary-400 text-sm flex items-center gap-2 mx-auto"
              >
                <RefreshCw className="w-4 h-4" />
                Refresh Status
              </button>
            </div>
          ) : runData?.status === 'failed' ? (
            <div className="bg-dark-900 rounded-lg border border-danger-500/50 p-12 text-center">
              <AlertCircle className="w-16 h-16 text-danger-500 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-dark-300 mb-2">
                Backtest Failed
              </h3>
              <p className="text-danger-400 text-sm">
                {runData.error_message || 'Unknown error occurred'}
              </p>
            </div>
          ) : !runData ? (
            <div className="bg-dark-900 rounded-lg border border-dark-700 p-12 text-center">
              <TrendingUp className="w-16 h-16 text-dark-600 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-dark-300 mb-2">
                No backtest run found
              </h3>
              <p className="text-dark-500 text-sm">
                This configuration hasn't been run yet. Start a new backtest run to see results.
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Backtest Configuration Info */}
              {selectedConfig && (
                <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
                  <h2 className="text-lg font-semibold text-dark-50 mb-4">Configuration</h2>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <p className="text-xs text-dark-500 mb-1">Symbol</p>
                      <p className="text-sm font-medium text-dark-50">{selectedConfig.symbol}</p>
                    </div>
                    <div>
                      <p className="text-xs text-dark-500 mb-1">Time Period</p>
                      <p className="text-sm font-medium text-dark-50">
                        {format(new Date(selectedConfig.start_date), 'MMM dd, yyyy')} -{' '}
                        {format(new Date(selectedConfig.end_date), 'MMM dd, yyyy')}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-dark-500 mb-1">Execution Mode</p>
                      <p className="text-sm font-medium text-dark-50">
                        {selectedConfig.execution_mode === 'full_pipeline' ? 'Agent Pipeline' : 'Synthetic'}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-dark-500 mb-1">Initial Capital</p>
                      <p className="text-sm font-medium text-dark-50">
                        ${selectedConfig.initial_capital?.toLocaleString()}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Run Summary */}
              <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold text-dark-50">Run Summary</h2>
                  {runData?.status && <RunStatusBadge status={runData.status} />}
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <p className="text-xs text-dark-500 mb-1">Candles Processed</p>
                    <p className="text-lg font-bold text-dark-50">
                      {runData.candles_processed?.toLocaleString()}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-dark-500 mb-1">Agent Decisions</p>
                    <p className="text-lg font-bold text-primary-500">
                      {runData.agent_decisions_count}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-dark-500 mb-1">Total Trades</p>
                    <p className="text-lg font-bold text-dark-50">
                      {runData.total_trades}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-dark-500 mb-1">Final Capital</p>
                    <p
                      className={`text-lg font-bold ${
                        (runData.final_capital || 0) >= 10000
                          ? 'text-success-500'
                          : 'text-danger-500'
                      }`}
                    >
                      ${runData.final_capital?.toLocaleString('en-US', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </p>
                  </div>
                </div>
              </div>

              {/* Metrics Table */}
              {metricsData?.metrics && (
                <MetricsTable
                  metrics={metricsData.metrics}
                  initialCapital={10000} // Get from config
                  finalCapital={metricsData.final_capital}
                />
              )}

              {/* Equity Curve */}
              {equityCurveData.length > 0 && (
                <EquityCurveChart data={equityCurveData} initialCapital={10000} />
              )}

              {/* Agent Decisions */}
              {runData.agent_decisions_count > 0 && (
                <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
                  <AgentDecisionList decisions={decisions} loading={false} />
                  {decisions.length === 0 && (
                    <div className="text-center py-8">
                      <AlertCircle className="w-12 h-12 text-warning-500 mx-auto mb-3" />
                      <p className="text-dark-400 text-sm">
                        {runData.agent_decisions_count} decisions were generated, but
                        they need to be fetched from the database.
                      </p>
                      <p className="text-dark-600 text-xs mt-1">
                        Check the agent_decisions table or implement the decisions
                        endpoint
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Trades Table (if any) */}
              {tradesData && tradesData.items.length > 0 && (
                <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
                  <h3 className="text-lg font-semibold text-dark-50 mb-4">
                    Simulated Trades ({tradesData.total})
                  </h3>
                  <div className="text-sm text-dark-400">
                    <p>Open: {tradesData.open_trades}</p>
                    <p>Closed: {tradesData.closed_trades}</p>
                  </div>
                  {/* Add trades table component here if needed */}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
