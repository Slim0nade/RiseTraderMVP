import React from 'react';
import { TrendingUp, TrendingDown, Target, Award, DollarSign, Activity } from 'lucide-react';
import type { BacktestMetrics } from '@/types';

interface MetricsTableProps {
  metrics: BacktestMetrics;
  initialCapital: number;
  finalCapital?: number;
}

export const MetricsTable: React.FC<MetricsTableProps> = ({
  metrics,
  initialCapital,
  finalCapital,
}) => {
  const formatCurrency = (value: number | null | undefined) => {
    if (value === null || value === undefined || isNaN(value)) {
      return '$0.00';
    }
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  const formatPercent = (value: number | null | undefined) => {
    if (value === null || value === undefined || isNaN(value)) {
      return '0.00%';
    }
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  };

  const getReturnColor = (value: number) => {
    if (value > 0) return 'text-success-500';
    if (value < 0) return 'text-danger-500';
    return 'text-dark-400';
  };

  const getRiskScore = (sharpe: number) => {
    if (sharpe >= 2) return { label: 'Excellent', color: 'text-success-500' };
    if (sharpe >= 1) return { label: 'Good', color: 'text-primary-500' };
    if (sharpe >= 0.5) return { label: 'Fair', color: 'text-warning-500' };
    return { label: 'Poor', color: 'text-danger-500' };
  };

  const riskScore = getRiskScore(metrics.sharpe_ratio);

  // Handle field name differences between backend and frontend
  // Backend sends max_drawdown_abs, frontend legacy expects max_drawdown
  const maxDrawdownDollars = metrics.max_drawdown_abs ?? metrics.max_drawdown ?? 0;

  return (
    <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
      <h3 className="text-lg font-semibold text-dark-50 mb-6">Performance Metrics</h3>

      {/* Key Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {/* Total Return */}
        <div className="bg-dark-800 rounded-lg p-4 border border-dark-700">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-dark-500">Total Return</p>
            <TrendingUp className={`w-4 h-4 ${getReturnColor(metrics.total_return_pct)}`} />
          </div>
          <p className={`text-2xl font-bold ${getReturnColor(metrics.total_return_pct)}`}>
            {formatPercent(metrics.total_return_pct)}
          </p>
          <p className="text-xs text-dark-500 mt-1">
            {formatCurrency(metrics.total_return)}
          </p>
        </div>

        {/* Sharpe Ratio */}
        <div className="bg-dark-800 rounded-lg p-4 border border-dark-700">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-dark-500">Sharpe Ratio</p>
            <Activity className="w-4 h-4 text-primary-500" />
          </div>
          <p className="text-2xl font-bold text-dark-50">
            {metrics.sharpe_ratio.toFixed(2)}
          </p>
          <p className={`text-xs ${riskScore.color} mt-1`}>{riskScore.label}</p>
        </div>

        {/* Win Rate */}
        <div className="bg-dark-800 rounded-lg p-4 border border-dark-700">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-dark-500">Win Rate</p>
            <Target className="w-4 h-4 text-success-500" />
          </div>
          <p className="text-2xl font-bold text-dark-50">
            {(metrics.win_rate * 100).toFixed(1)}%
          </p>
          <p className="text-xs text-dark-500 mt-1">
            {metrics.winning_trades} / {metrics.total_trades} trades
          </p>
        </div>

        {/* Profit Factor */}
        <div className="bg-dark-800 rounded-lg p-4 border border-dark-700">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-dark-500">Profit Factor</p>
            <Award className="w-4 h-4 text-warning-500" />
          </div>
          <p className="text-2xl font-bold text-dark-50">
            {metrics.profit_factor.toFixed(2)}
          </p>
          <p className="text-xs text-dark-500 mt-1">
            {metrics.profit_factor >= 2 ? 'Excellent' : metrics.profit_factor >= 1.5 ? 'Good' : 'Fair'}
          </p>
        </div>
      </div>

      {/* Detailed Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Returns & Risk */}
        <div>
          <h4 className="text-sm font-semibold text-dark-300 mb-3">Returns & Risk</h4>
          <div className="space-y-3">
            <div className="flex items-center justify-between py-2 border-b border-dark-800">
              <span className="text-sm text-dark-500">Initial Capital</span>
              <span className="text-sm font-medium text-dark-200">
                {formatCurrency(initialCapital)}
              </span>
            </div>
            {finalCapital && (
              <div className="flex items-center justify-between py-2 border-b border-dark-800">
                <span className="text-sm text-dark-500">Final Capital</span>
                <span className="text-sm font-medium text-dark-200">
                  {formatCurrency(finalCapital)}
                </span>
              </div>
            )}
            <div className="flex items-center justify-between py-2 border-b border-dark-800">
              <span className="text-sm text-dark-500">Sharpe Ratio</span>
              <span className="text-sm font-medium text-dark-200">
                {metrics.sharpe_ratio.toFixed(3)}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-800">
              <span className="text-sm text-dark-500">Sortino Ratio</span>
              <span className="text-sm font-medium text-dark-200">
                {metrics.sortino_ratio.toFixed(3)}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-800">
              <span className="text-sm text-dark-500">Calmar Ratio</span>
              <span className="text-sm font-medium text-dark-200">
                {metrics.calmar_ratio.toFixed(3)}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-800">
              <span className="text-sm text-dark-500">Max Drawdown</span>
              <span className="text-sm font-medium text-danger-500">
                -{Math.abs(metrics.max_drawdown_pct).toFixed(2)}%
              </span>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-sm text-dark-500">Max Drawdown ($)</span>
              <span className="text-sm font-medium text-danger-500">
                {formatCurrency(Math.abs(maxDrawdownDollars))}
              </span>
            </div>
          </div>
        </div>

        {/* Trade Statistics */}
        <div>
          <h4 className="text-sm font-semibold text-dark-300 mb-3">Trade Statistics</h4>
          <div className="space-y-3">
            <div className="flex items-center justify-between py-2 border-b border-dark-800">
              <span className="text-sm text-dark-500">Total Trades</span>
              <span className="text-sm font-medium text-dark-200">
                {metrics.total_trades}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-800">
              <span className="text-sm text-dark-500">Winning Trades</span>
              <span className="text-sm font-medium text-success-500">
                {metrics.winning_trades}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-800">
              <span className="text-sm text-dark-500">Losing Trades</span>
              <span className="text-sm font-medium text-danger-500">
                {metrics.losing_trades}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-800">
              <span className="text-sm text-dark-500">Avg Win</span>
              <span className="text-sm font-medium text-success-500">
                {formatCurrency(metrics.avg_win)}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-800">
              <span className="text-sm text-dark-500">Avg Loss</span>
              <span className="text-sm font-medium text-danger-500">
                {formatCurrency(Math.abs(metrics.avg_loss))}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-800">
              <span className="text-sm text-dark-500">Largest Win</span>
              <span className="text-sm font-medium text-success-500">
                {formatCurrency(metrics.largest_win)}
              </span>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-sm text-dark-500">Largest Loss</span>
              <span className="text-sm font-medium text-danger-500">
                {formatCurrency(Math.abs(metrics.largest_loss))}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Risk Assessment */}
      <div className="mt-6 p-4 bg-dark-800 border border-dark-700 rounded-lg">
        <h4 className="text-sm font-semibold text-dark-300 mb-2">Risk Assessment</h4>
        <div className="flex items-start gap-3">
          <div className={`w-2 h-2 rounded-full mt-1.5 ${
            metrics.sharpe_ratio >= 2 ? 'bg-success-500' :
            metrics.sharpe_ratio >= 1 ? 'bg-primary-500' :
            metrics.sharpe_ratio >= 0.5 ? 'bg-warning-500' : 'bg-danger-500'
          }`}></div>
          <div>
            <p className="text-sm text-dark-300">
              {metrics.sharpe_ratio >= 2 && (
                <>Excellent risk-adjusted returns. The strategy shows strong performance relative to its volatility.</>
              )}
              {metrics.sharpe_ratio >= 1 && metrics.sharpe_ratio < 2 && (
                <>Good risk-adjusted returns. The strategy performs well with acceptable volatility.</>
              )}
              {metrics.sharpe_ratio >= 0.5 && metrics.sharpe_ratio < 1 && (
                <>Fair risk-adjusted returns. Consider optimizing to improve risk management.</>
              )}
              {metrics.sharpe_ratio < 0.5 && (
                <>Poor risk-adjusted returns. The strategy may need significant improvements or should be avoided.</>
              )}
            </p>
            <p className="text-xs text-dark-500 mt-1">
              Win Rate: {(metrics.win_rate * 100).toFixed(1)}% |
              Profit Factor: {metrics.profit_factor.toFixed(2)} |
              Max DD: {formatPercent(metrics.max_drawdown_pct)}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
