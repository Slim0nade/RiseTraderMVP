import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { BarChart3, TrendingUp, Award, AlertCircle, Power } from 'lucide-react';
import { strategiesApi } from '@/api/endpoints';
import { StatusBadge } from '@/components/common/StatusBadge';
import { useFormatters } from '@/hooks/useFormatters';
import { cn } from '@/utils/cn';
import toast from 'react-hot-toast';
import type { Strategy } from '@/types';

export const Strategies: React.FC = () => {
  const queryClient = useQueryClient();
  const formatters = useFormatters();

  // Fetch all strategies
  const { data: strategies, isLoading } = useQuery({
    queryKey: ['strategies'],
    queryFn: strategiesApi.getAllStrategies,
    refetchInterval: 10000,
  });

  // Toggle strategy mutation
  const toggleMutation = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      strategiesApi.toggleStrategy(id, active),
    onSuccess: (_, variables) => {
      toast.success(
        `Strategy ${variables.active ? 'activated' : 'deactivated'} successfully`
      );
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
    },
    onError: () => {
      toast.error('Failed to toggle strategy');
    },
  });

  const handleToggle = (strategy: Strategy) => {
    toggleMutation.mutate({ id: strategy.id, active: !strategy.is_active });
  };

  // Ensure strategies is an array before filtering
  const strategiesArray = Array.isArray(strategies) ? strategies : [];
  const activeCount = strategiesArray.filter((s) => s.is_active).length;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-dark-50 mb-2">Strategies</h1>
        <p className="text-dark-400">Manage and monitor your trading strategies</p>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-primary-500/10 rounded-lg">
              <BarChart3 className="w-6 h-6 text-primary-500" />
            </div>
            <div>
              <p className="text-sm text-dark-500">Total Strategies</p>
              <p className="text-3xl font-bold text-dark-50">{strategiesArray.length}</p>
            </div>
          </div>
        </div>

        <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-success-500/10 rounded-lg">
              <Power className="w-6 h-6 text-success-500" />
            </div>
            <div>
              <p className="text-sm text-dark-500">Active</p>
              <p className="text-3xl font-bold text-dark-50">{activeCount}</p>
            </div>
          </div>
        </div>

        <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-primary-500/10 rounded-lg">
              <TrendingUp className="w-6 h-6 text-primary-500" />
            </div>
            <div>
              <p className="text-sm text-dark-500">Avg Win Rate</p>
              <p className="text-3xl font-bold text-dark-50">
                {strategiesArray.length > 0
                  ? (
                      strategiesArray.reduce((sum, s) => sum + (s.performance?.win_rate || 0), 0) /
                      strategiesArray.length
                    ).toFixed(1)
                  : '0'}
                %
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Strategies List */}
      <div>
        <h2 className="text-xl font-semibold text-dark-50 mb-4">All Strategies</h2>
        {isLoading ? (
          <div className="bg-dark-900 rounded-lg border border-dark-700 p-8 text-center">
            <p className="text-dark-400">Loading strategies...</p>
          </div>
        ) : strategiesArray.length === 0 ? (
          <div className="bg-dark-900 rounded-lg border border-dark-700 p-8 text-center text-dark-500">
            No strategies configured
          </div>
        ) : (
          <div className="space-y-4">
            {strategiesArray.map((strategy) => (
              <div
                key={strategy.id}
                className="bg-dark-900 rounded-lg border border-dark-700 p-6 hover:border-dark-600 transition-colors"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="text-xl font-semibold text-dark-50">{strategy.name}</h3>
                      <StatusBadge
                        status={strategy.is_active ? 'active' : 'stopped'}
                        text={strategy.is_active ? 'Active' : 'Inactive'}
                      />
                    </div>
                    <p className="text-dark-400">{strategy.description}</p>
                  </div>

                  <button
                    onClick={() => handleToggle(strategy)}
                    className={cn(
                      'px-4 py-2 rounded-lg font-medium transition-colors',
                      strategy.is_active
                        ? 'bg-danger-500 hover:bg-danger-600 text-white'
                        : 'bg-success-500 hover:bg-success-600 text-white'
                    )}
                  >
                    {strategy.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <div>
                    <p className="text-sm text-dark-500 mb-1">Allocation</p>
                    <p className="text-lg font-bold text-dark-50">
                      {strategy.allocation_pct.toFixed(1)}%
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-dark-500 mb-1">Symbols</p>
                    <p className="text-lg font-bold text-dark-50">{strategy.symbols.join(', ')}</p>
                  </div>
                  {strategy.performance && (
                    <>
                      <div>
                        <p className="text-sm text-dark-500 mb-1">Total Trades</p>
                        <p className="text-lg font-bold text-dark-50">
                          {strategy.performance.total_trades}
                        </p>
                      </div>
                      <div>
                        <p className="text-sm text-dark-500 mb-1">Win Rate</p>
                        <p className="text-lg font-bold text-success-500">
                          {strategy.performance.win_rate.toFixed(1)}%
                        </p>
                      </div>
                    </>
                  )}
                </div>

                {strategy.performance && (
                  <div className="pt-4 border-t border-dark-800">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div>
                        <p className="text-sm text-dark-500 mb-1">Total P&L</p>
                        <p
                          className={cn(
                            'text-lg font-bold',
                            strategy.performance.total_pnl >= 0
                              ? 'text-success-500'
                              : 'text-danger-500'
                          )}
                        >
                          {formatters.currency(strategy.performance.total_pnl)}
                        </p>
                      </div>
                      <div>
                        <p className="text-sm text-dark-500 mb-1">Avg Win</p>
                        <p className="text-lg font-bold text-success-500">
                          {formatters.currency(strategy.performance.avg_win)}
                        </p>
                      </div>
                      <div>
                        <p className="text-sm text-dark-500 mb-1">Avg Loss</p>
                        <p className="text-lg font-bold text-danger-500">
                          {formatters.currency(strategy.performance.avg_loss)}
                        </p>
                      </div>
                      <div>
                        <p className="text-sm text-dark-500 mb-1">Sharpe Ratio</p>
                        <p className="text-lg font-bold text-dark-50">
                          {strategy.performance.sharpe_ratio?.toFixed(2) || 'N/A'}
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Parameters */}
                {Object.keys(strategy.parameters || {}).length > 0 && (
                  <details className="mt-4">
                    <summary className="text-sm text-primary-500 cursor-pointer hover:text-primary-400">
                      View parameters
                    </summary>
                    <pre className="mt-2 p-3 bg-dark-950 rounded text-xs text-dark-400 overflow-auto">
                      {JSON.stringify(strategy.parameters, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
