import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { TrendingUp, Award, AlertCircle, Target } from 'lucide-react';
import { MetricCard } from '@/components/common/MetricCard';
import { EquityCurveChart } from '@/components/charts/EquityCurveChart';
import { PerformanceBarChart } from '@/components/charts/PerformanceBarChart';
import { performanceApi } from '@/api/endpoints';

export const Performance: React.FC = () => {
  // Fetch performance metrics
  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ['performance-metrics'],
    queryFn: performanceApi.getMetrics,
    refetchInterval: 10000,
  });

  // Fetch equity curve
  const { data: equityCurve } = useQuery({
    queryKey: ['equity-curve'],
    queryFn: performanceApi.getEquityCurve,
    refetchInterval: 15000,
  });

  // Fetch daily P&L
  const { data: dailyPnL } = useQuery({
    queryKey: ['daily-pnl-30'],
    queryFn: () => performanceApi.getDailyPnL(30),
    refetchInterval: 15000,
  });

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-dark-50 mb-2">Performance</h1>
        <p className="text-dark-400">Analyze your trading performance and metrics</p>
      </div>

      {/* Key Performance Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Total P&L"
          value={metrics?.total_pnl || 0}
          format="currency"
          icon={TrendingUp}
          trend={metrics && metrics.total_pnl >= 0 ? 'up' : 'down'}
          loading={metricsLoading}
        />
        <MetricCard
          title="Win Rate"
          value={metrics?.win_rate || 0}
          format="percentage"
          icon={Award}
          loading={metricsLoading}
        />
        <MetricCard
          title="Sharpe Ratio"
          value={metrics?.sharpe_ratio || 0}
          format="number"
          icon={Target}
          loading={metricsLoading}
        />
        <MetricCard
          title="Max Drawdown"
          value={metrics?.max_drawdown_pct || 0}
          format="percentage"
          icon={AlertCircle}
          trend="down"
          loading={metricsLoading}
        />
      </div>

      {/* Detailed Metrics */}
      {metrics && (
        <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
          <h2 className="text-xl font-semibold text-dark-50 mb-6">Detailed Metrics</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
            <div>
              <p className="text-sm text-dark-500 mb-1">Total Trades</p>
              <p className="text-2xl font-bold text-dark-50">{metrics.total_trades}</p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Daily P&L</p>
              <p
                className={`text-2xl font-bold ${
                  metrics.daily_pnl >= 0 ? 'text-success-500' : 'text-danger-500'
                }`}
              >
                ${metrics.daily_pnl.toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Weekly P&L</p>
              <p
                className={`text-2xl font-bold ${
                  metrics.weekly_pnl >= 0 ? 'text-success-500' : 'text-danger-500'
                }`}
              >
                ${metrics.weekly_pnl.toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Monthly P&L</p>
              <p
                className={`text-2xl font-bold ${
                  metrics.monthly_pnl >= 0 ? 'text-success-500' : 'text-danger-500'
                }`}
              >
                ${metrics.monthly_pnl.toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Best Trade</p>
              <p className="text-2xl font-bold text-success-500">
                ${metrics.best_trade.toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Worst Trade</p>
              <p className="text-2xl font-bold text-danger-500">
                ${metrics.worst_trade.toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Avg Trade Duration</p>
              <p className="text-2xl font-bold text-dark-50">
                {Math.round(metrics.avg_trade_duration_minutes)}m
              </p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Profit Factor</p>
              <p className="text-2xl font-bold text-dark-50">
                {metrics.profit_factor?.toFixed(2) || 'N/A'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Equity Curve */}
        <div>{equityCurve && <EquityCurveChart data={equityCurve} />}</div>

        {/* Daily P&L */}
        <div>{dailyPnL && <PerformanceBarChart data={dailyPnL} />}</div>
      </div>

      {/* Risk Metrics */}
      {metrics && (
        <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
          <h2 className="text-xl font-semibold text-dark-50 mb-6">Risk Analysis</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-4 bg-dark-800 rounded-lg">
              <p className="text-sm text-dark-500 mb-2">Max Drawdown</p>
              <p className="text-3xl font-bold text-danger-500 mb-1">
                ${metrics.max_drawdown.toFixed(2)}
              </p>
              <p className="text-sm text-danger-400">{metrics.max_drawdown_pct.toFixed(2)}%</p>
            </div>
            <div className="p-4 bg-dark-800 rounded-lg">
              <p className="text-sm text-dark-500 mb-2">Sharpe Ratio</p>
              <p className="text-3xl font-bold text-primary-500">
                {metrics.sharpe_ratio.toFixed(2)}
              </p>
              <p className="text-sm text-dark-400">Risk-adjusted returns</p>
            </div>
            <div className="p-4 bg-dark-800 rounded-lg">
              <p className="text-sm text-dark-500 mb-2">Open Positions</p>
              <p className="text-3xl font-bold text-dark-50">{metrics.open_positions}</p>
              <p className="text-sm text-dark-400">Currently active</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
