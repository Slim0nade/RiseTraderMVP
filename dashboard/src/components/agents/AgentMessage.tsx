import React from 'react';
import { TrendingUp, TrendingDown, Minus, Clock, Target, Shield } from 'lucide-react';
import { format } from 'date-fns';
import type { AgentDecision } from '@/types';

interface AgentMessageProps {
  decision: AgentDecision;
  isFirst?: boolean;
}

export const AgentMessage: React.FC<AgentMessageProps> = ({ decision, isFirst }) => {
  const getDecisionIcon = () => {
    switch (decision.decision_type) {
      case 'BUY':
        return <TrendingUp className="w-5 h-5 text-success-500" />;
      case 'SELL':
        return <TrendingDown className="w-5 h-5 text-danger-500" />;
      case 'HOLD':
        return <Minus className="w-5 h-5 text-warning-500" />;
      default:
        return <Target className="w-5 h-5 text-dark-400" />;
    }
  };

  const getDecisionColor = () => {
    switch (decision.decision_type) {
      case 'BUY':
        return 'border-success-500/30 bg-success-500/5';
      case 'SELL':
        return 'border-danger-500/30 bg-danger-500/5';
      case 'HOLD':
        return 'border-warning-500/30 bg-warning-500/5';
      default:
        return 'border-dark-600 bg-dark-800/50';
    }
  };

  const getConvictionColor = (score: number) => {
    if (score >= 0.75) return 'text-success-500';
    if (score >= 0.5) return 'text-warning-500';
    return 'text-danger-500';
  };

  return (
    <div className={`relative ${!isFirst ? 'mt-3' : ''}`}>
      {/* Timeline connector */}
      {!isFirst && (
        <div className="absolute left-[23px] -top-3 w-0.5 h-3 bg-dark-700" />
      )}

      <div className={`border rounded-lg p-4 transition-all hover:border-primary-500/30 ${getDecisionColor()}`}>
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-dark-800 rounded-lg">{getDecisionIcon()}</div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-dark-50 text-sm">
                  {decision.decision_type} Decision
                </h3>
                <span className="text-xs text-dark-500">•</span>
                <span className="text-xs text-dark-500">{decision.symbol}</span>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <Clock className="w-3 h-3 text-dark-500" />
                <span className="text-xs text-dark-500">
                  {format(new Date(decision.timestamp), 'MMM dd, yyyy HH:mm:ss')}
                </span>
              </div>
            </div>
          </div>

          {/* Conviction Score */}
          <div className="text-right">
            <p className="text-xs text-dark-500 mb-1">Conviction</p>
            <p className={`text-lg font-bold ${getConvictionColor(decision.conviction_score)}`}>
              {(decision.conviction_score * 100).toFixed(0)}%
            </p>
          </div>
        </div>

        {/* Reasoning */}
        {decision.reasoning && (
          <div className="mb-3 p-3 bg-dark-800/50 rounded-lg">
            <p className="text-xs text-dark-400 mb-1 font-medium">Reasoning:</p>
            <p className="text-sm text-dark-200 leading-relaxed">{decision.reasoning}</p>
          </div>
        )}

        {/* Risk Assessment */}
        {decision.risk_assessment && (
          <div className="mb-3 p-3 bg-dark-800/50 rounded-lg">
            <div className="flex items-center gap-2 mb-1">
              <Shield className="w-3 h-3 text-primary-500" />
              <p className="text-xs text-dark-400 font-medium">Risk Assessment:</p>
            </div>
            <p className="text-sm text-dark-200">{decision.risk_assessment}</p>
          </div>
        )}

        {/* Trade Parameters */}
        {(decision.quantity || decision.stop_loss || decision.take_profit) && (
          <div className="grid grid-cols-3 gap-3 mt-3 pt-3 border-t border-dark-700">
            {decision.quantity && (
              <div>
                <p className="text-xs text-dark-500 mb-1">Quantity</p>
                <p className="text-sm font-medium text-dark-50">
                  {decision.quantity.toFixed(2)} lots
                </p>
              </div>
            )}
            {decision.stop_loss && (
              <div>
                <p className="text-xs text-dark-500 mb-1">Stop Loss</p>
                <p className="text-sm font-medium text-danger-400">
                  ${decision.stop_loss.toFixed(2)}
                </p>
              </div>
            )}
            {decision.take_profit && (
              <div>
                <p className="text-xs text-dark-500 mb-1">Take Profit</p>
                <p className="text-sm font-medium text-success-400">
                  ${decision.take_profit.toFixed(2)}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Market Context */}
        {decision.market_context && Object.keys(decision.market_context).length > 0 && (
          <details className="mt-3 pt-3 border-t border-dark-700">
            <summary className="text-xs text-dark-400 cursor-pointer hover:text-dark-300 transition-colors">
              View Market Context
            </summary>
            <div className="mt-2 p-3 bg-dark-800/50 rounded text-xs font-mono text-dark-300 overflow-x-auto">
              <pre>{JSON.stringify(decision.market_context, null, 2)}</pre>
            </div>
          </details>
        )}
      </div>
    </div>
  );
};
