import React from 'react';
import { TrendingUp, TrendingDown, Minus, AlertCircle, CheckCircle } from 'lucide-react';
import type { AgentDecision } from '@/types';
import { format } from 'date-fns';

interface AgentDecisionListProps {
  decisions: AgentDecision[];
  loading?: boolean;
}

export const AgentDecisionList: React.FC<AgentDecisionListProps> = ({
  decisions,
  loading = false,
}) => {
  if (loading) {
    return (
      <div className="bg-dark-900 rounded-lg border border-dark-700 p-8 text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500 mx-auto"></div>
        <p className="text-dark-400 mt-4">Loading agent decisions...</p>
      </div>
    );
  }

  if (decisions.length === 0) {
    return (
      <div className="bg-dark-900 rounded-lg border border-dark-700 p-8 text-center">
        <AlertCircle className="w-12 h-12 text-dark-600 mx-auto mb-4" />
        <p className="text-dark-400">No agent decisions found</p>
      </div>
    );
  }

  const getDecisionIcon = (type: string) => {
    switch (type) {
      case 'BUY':
        return <TrendingUp className="w-5 h-5 text-success-500" />;
      case 'SELL':
        return <TrendingDown className="w-5 h-5 text-danger-500" />;
      case 'HOLD':
        return <Minus className="w-5 h-5 text-dark-500" />;
      default:
        return <Minus className="w-5 h-5 text-dark-500" />;
    }
  };

  const getDecisionColor = (type: string) => {
    switch (type) {
      case 'BUY':
        return 'bg-success-500/10 border-success-500/20 text-success-400';
      case 'SELL':
        return 'bg-danger-500/10 border-danger-500/20 text-danger-400';
      case 'HOLD':
        return 'bg-dark-800 border-dark-700 text-dark-400';
      default:
        return 'bg-dark-800 border-dark-700 text-dark-400';
    }
  };

  const getConvictionColor = (score: number) => {
    if (score >= 0.7) return 'text-success-500';
    if (score >= 0.5) return 'text-warning-500';
    return 'text-dark-500';
  };

  const getConvictionBadge = (score: number) => {
    if (score >= 0.7) return 'High';
    if (score >= 0.5) return 'Medium';
    return 'Low';
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-dark-50">
          Agent Decisions ({decisions.length})
        </h3>
        <div className="flex gap-4 text-sm">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-success-500" />
            <span className="text-dark-400">
              {decisions.filter((d) => d.decision_type === 'BUY').length} BUY
            </span>
          </div>
          <div className="flex items-center gap-2">
            <TrendingDown className="w-4 h-4 text-danger-500" />
            <span className="text-dark-400">
              {decisions.filter((d) => d.decision_type === 'SELL').length} SELL
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Minus className="w-4 h-4 text-dark-500" />
            <span className="text-dark-400">
              {decisions.filter((d) => d.decision_type === 'HOLD').length} HOLD
            </span>
          </div>
        </div>
      </div>

      <div className="space-y-2 max-h-[600px] overflow-y-auto pr-2">
        {decisions.map((decision, index) => (
          <div
            key={decision.id}
            className={`border rounded-lg p-4 transition-all hover:border-primary-500/30 ${getDecisionColor(
              decision.decision_type
            )}`}
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center w-8 h-8 rounded-full bg-dark-800 border border-dark-600">
                  {getDecisionIcon(decision.decision_type)}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-dark-50">
                      {decision.decision_type}
                    </span>
                    <span className="text-xs text-dark-500">#{index + 1}</span>
                  </div>
                  <p className="text-xs text-dark-500">
                    {format(new Date(decision.timestamp), 'MMM dd, HH:mm:ss')}
                  </p>
                </div>
              </div>

              <div className="text-right">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-dark-500">Conviction</span>
                  <span
                    className={`text-sm font-bold ${getConvictionColor(
                      decision.conviction_score
                    )}`}
                  >
                    {(decision.conviction_score * 100).toFixed(0)}%
                  </span>
                </div>
                <span
                  className={`text-xs px-2 py-0.5 rounded ${
                    decision.conviction_score >= 0.7
                      ? 'bg-success-500/20 text-success-400'
                      : decision.conviction_score >= 0.5
                      ? 'bg-warning-500/20 text-warning-400'
                      : 'bg-dark-700 text-dark-400'
                  }`}
                >
                  {getConvictionBadge(decision.conviction_score)}
                </span>
              </div>
            </div>

            <div className="mt-3 pt-3 border-t border-dark-700/50 space-y-2">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-dark-500 text-xs">Symbol</p>
                  <p className="text-dark-200 font-medium">{decision.symbol}</p>
                </div>
                {decision.quantity && (
                  <div>
                    <p className="text-dark-500 text-xs">Quantity</p>
                    <p className="text-dark-200 font-medium">{decision.quantity}</p>
                  </div>
                )}
              </div>

              {decision.risk_assessment && (
                <div className="mt-2">
                  <p className="text-dark-500 text-xs mb-1">Risk Assessment</p>
                  <p className="text-dark-300 text-sm bg-dark-800/50 rounded p-2">
                    {decision.risk_assessment}
                  </p>
                </div>
              )}

              {decision.reasoning && (
                <div className="mt-2">
                  <p className="text-dark-500 text-xs mb-1">Reasoning</p>
                  <p className="text-dark-300 text-sm bg-dark-800/50 rounded p-2">
                    {decision.reasoning}
                  </p>
                </div>
              )}

              {(decision.stop_loss || decision.take_profit) && (
                <div className="grid grid-cols-2 gap-4 text-sm mt-2">
                  {decision.stop_loss && (
                    <div>
                      <p className="text-dark-500 text-xs">Stop Loss</p>
                      <p className="text-danger-400 font-medium">
                        ${decision.stop_loss.toFixed(2)}
                      </p>
                    </div>
                  )}
                  {decision.take_profit && (
                    <div>
                      <p className="text-dark-500 text-xs">Take Profit</p>
                      <p className="text-success-400 font-medium">
                        ${decision.take_profit.toFixed(2)}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>

            {decision.decision_type !== 'HOLD' && decision.conviction_score < 0.6 && (
              <div className="mt-2 flex items-center gap-2 text-xs text-warning-500 bg-warning-500/10 border border-warning-500/20 rounded p-2">
                <AlertCircle className="w-4 h-4" />
                <span>
                  Below execution threshold (0.6) - Trade not executed
                </span>
              </div>
            )}

            {decision.decision_type !== 'HOLD' && decision.conviction_score >= 0.6 && (
              <div className="mt-2 flex items-center gap-2 text-xs text-success-500 bg-success-500/10 border border-success-500/20 rounded p-2">
                <CheckCircle className="w-4 h-4" />
                <span>Above execution threshold - Trade executed</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
