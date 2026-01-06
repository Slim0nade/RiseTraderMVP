import React, { useState } from 'react';
import { TrendingUp, TrendingDown, Pause, AlertCircle, CheckCircle, ChevronDown, ChevronRight } from 'lucide-react';
import type { AgentDecision } from '@/types';
import { format } from 'date-fns';

interface AgentDecisionListProps {
  decisions: AgentDecision[];
  loading?: boolean;
}

// Group consecutive decisions of the same type
interface DecisionGroup {
  type: string;
  decisions: AgentDecision[];
  isTransition: boolean; // true if this group starts a new decision type (transition from previous)
}

const groupDecisions = (decisions: AgentDecision[]): DecisionGroup[] => {
  if (decisions.length === 0) return [];

  const groups: DecisionGroup[] = [];
  let currentGroup: AgentDecision[] = [decisions[0]];
  let currentType = decisions[0].decision_type;

  for (let i = 1; i < decisions.length; i++) {
    const decision = decisions[i];

    if (decision.decision_type === currentType) {
      // Same type, add to current group
      currentGroup.push(decision);
    } else {
      // Type changed - save current group and start new one
      groups.push({
        type: currentType,
        decisions: currentGroup,
        isTransition: groups.length > 0, // All groups except first are transitions
      });

      currentGroup = [decision];
      currentType = decision.decision_type;
    }
  }

  // Add the last group
  groups.push({
    type: currentType,
    decisions: currentGroup,
    isTransition: groups.length > 0,
  });

  return groups;
};

export const AgentDecisionList: React.FC<AgentDecisionListProps> = ({
  decisions,
  loading = false,
}) => {
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());
  const [hoveredDecision, setHoveredDecision] = useState<string | null>(null);

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

  const toggleGroup = (index: number) => {
    const newExpanded = new Set(expandedGroups);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedGroups(newExpanded);
  };

  const getDecisionIcon = (type: string) => {
    switch (type) {
      case 'BUY':
        return <TrendingUp className="w-5 h-5 text-success-500" />;
      case 'SELL':
        return <TrendingDown className="w-5 h-5 text-danger-500" />;
      case 'HOLD':
        return <Pause className="w-5 h-5 text-warning-500" />;
      default:
        return <Pause className="w-5 h-5 text-dark-500" />;
    }
  };

  const getDecisionColor = (type: string) => {
    switch (type) {
      case 'BUY':
        return 'bg-success-500/10 border-success-500/20 text-success-400';
      case 'SELL':
        return 'bg-danger-500/10 border-danger-500/20 text-danger-400';
      case 'HOLD':
        return 'bg-warning-500/10 border-warning-500/20 text-warning-400';
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

  const groups = groupDecisions(decisions);

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
            <Pause className="w-4 h-4 text-warning-500" />
            <span className="text-dark-400">
              {decisions.filter((d) => d.decision_type === 'HOLD').length} HOLD
            </span>
          </div>
        </div>
      </div>

      <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
        {groups.map((group, groupIndex) => {
          const isExpanded = expandedGroups.has(groupIndex);
          const avgConviction = group.decisions.reduce((sum, d) => sum + d.conviction_score, 0) / group.decisions.length;

          return (
            <div
              key={groupIndex}
              className={`border rounded-lg overflow-hidden transition-all ${
                group.isTransition
                  ? 'ring-2 ring-primary-500/40 shadow-lg shadow-primary-500/20'
                  : ''
              } ${getDecisionColor(group.type)}`}
            >
              {/* Group Header - Always Visible */}
              <div
                className="p-4 cursor-pointer hover:bg-dark-800/30 transition-colors"
                onClick={() => toggleGroup(groupIndex)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {isExpanded ? (
                      <ChevronDown className="w-5 h-5 text-dark-400" />
                    ) : (
                      <ChevronRight className="w-5 h-5 text-dark-400" />
                    )}

                    <div className="flex items-center justify-center w-8 h-8 rounded-full bg-dark-800 border border-dark-600">
                      {getDecisionIcon(group.type)}
                    </div>

                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-dark-50">
                          {group.type}
                        </span>
                        <span className="text-xs text-dark-500">
                          ×{group.decisions.length}
                        </span>
                        {group.isTransition && (
                          <span className="text-xs px-2 py-0.5 rounded bg-primary-500/20 text-primary-400 border border-primary-500/30">
                            Decision Change
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-dark-500">
                        {format(new Date(group.decisions[0].timestamp), 'MMM dd, HH:mm:ss')}
                        {group.decisions.length > 1 && (
                          <>
                            {' → '}
                            {format(
                              new Date(group.decisions[group.decisions.length - 1].timestamp),
                              'HH:mm:ss'
                            )}
                          </>
                        )}
                      </p>
                    </div>
                  </div>

                  <div className="text-right">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-dark-500">Avg Conviction</span>
                      <span className={`text-sm font-bold ${getConvictionColor(avgConviction)}`}>
                        {(avgConviction * 100).toFixed(0)}%
                      </span>
                    </div>
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${
                        avgConviction >= 0.7
                          ? 'bg-success-500/20 text-success-400'
                          : avgConviction >= 0.5
                          ? 'bg-warning-500/20 text-warning-400'
                          : 'bg-dark-700 text-dark-400'
                      }`}
                    >
                      {getConvictionBadge(avgConviction)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Expanded Decision Details */}
              {isExpanded && (
                <div className="border-t border-dark-700/50">
                  {group.decisions.map((decision, decisionIndex) => (
                    <div
                      key={decision.id}
                      className="relative group/decision"
                      onMouseEnter={() => setHoveredDecision(decision.id)}
                      onMouseLeave={() => setHoveredDecision(null)}
                    >
                      {/* Vertical Timeline Item */}
                      <div className="flex items-start gap-3 p-3 hover:bg-dark-800/30 transition-colors border-l-2 border-dark-700 ml-4">
                        <div className="flex-shrink-0 w-2 h-2 rounded-full bg-dark-500 mt-1.5 -ml-[9px]" />

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2 text-xs text-dark-400">
                              <span className="font-mono">
                                {format(new Date(decision.timestamp), 'HH:mm:ss')}
                              </span>
                              <span className="text-dark-600">•</span>
                              <span className={getConvictionColor(decision.conviction_score)}>
                                {(decision.conviction_score * 100).toFixed(0)}%
                              </span>
                            </div>

                            {decision.conviction_score >= 0.6 ? (
                              <CheckCircle className="w-3 h-3 text-success-500" />
                            ) : (
                              <AlertCircle className="w-3 h-3 text-warning-500" />
                            )}
                          </div>

                          {/* Tooltip on Hover */}
                          {hoveredDecision === decision.id && (
                            <div className="absolute left-full ml-4 top-0 z-10 w-96 bg-dark-800 border border-dark-600 rounded-lg shadow-xl p-4 pointer-events-none">
                              <div className="space-y-3">
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-2">
                                    {getDecisionIcon(decision.decision_type)}
                                    <span className="font-semibold text-dark-50">
                                      {decision.decision_type}
                                    </span>
                                  </div>
                                  <span className="text-xs text-dark-500">
                                    {format(new Date(decision.timestamp), 'MMM dd, HH:mm:ss')}
                                  </span>
                                </div>

                                {/* Order Details Section */}
                                {decision.decision_type !== 'HOLD' && (
                                  <div className="bg-dark-900 border border-dark-700 rounded p-3">
                                    <p className="text-xs font-semibold text-primary-400 mb-2">Order Details</p>
                                    <div className="grid grid-cols-2 gap-3 text-sm">
                                      <div>
                                        <p className="text-dark-500 text-xs">Symbol</p>
                                        <p className="text-dark-200 font-semibold">{decision.symbol}</p>
                                      </div>
                                      {decision.quantity && (
                                        <div>
                                          <p className="text-dark-500 text-xs">Quantity</p>
                                          <p className="text-dark-200 font-semibold">{decision.quantity}</p>
                                        </div>
                                      )}
                                      {decision.market_context?.current_price && (
                                        <div>
                                          <p className="text-dark-500 text-xs">Entry Price</p>
                                          <p className="text-primary-400 font-semibold font-mono">
                                            ${decision.market_context.current_price.toFixed(2)}
                                          </p>
                                        </div>
                                      )}
                                      <div>
                                        <p className="text-dark-500 text-xs">Conviction</p>
                                        <p className={`${getConvictionColor(decision.conviction_score)} font-semibold`}>
                                          {(decision.conviction_score * 100).toFixed(0)}%
                                        </p>
                                      </div>
                                    </div>

                                    {/* Risk Management */}
                                    {(decision.stop_loss || decision.take_profit) && (
                                      <div className="mt-3 pt-3 border-t border-dark-700">
                                        <p className="text-xs font-semibold text-dark-400 mb-2">Risk Management</p>
                                        <div className="grid grid-cols-2 gap-3 text-sm">
                                          {decision.stop_loss && (
                                            <div>
                                              <p className="text-dark-500 text-xs">Stop Loss</p>
                                              <p className="text-danger-400 font-semibold font-mono">
                                                ${decision.stop_loss.toFixed(2)}
                                              </p>
                                              {decision.market_context?.current_price && (
                                                <p className="text-xs text-dark-600 mt-0.5">
                                                  {((decision.stop_loss - decision.market_context.current_price) / decision.market_context.current_price * 100).toFixed(2)}%
                                                </p>
                                              )}
                                            </div>
                                          )}
                                          {decision.take_profit && (
                                            <div>
                                              <p className="text-dark-500 text-xs">Take Profit</p>
                                              <p className="text-success-400 font-semibold font-mono">
                                                ${decision.take_profit.toFixed(2)}
                                              </p>
                                              {decision.market_context?.current_price && (
                                                <p className="text-xs text-dark-600 mt-0.5">
                                                  +{((decision.take_profit - decision.market_context.current_price) / decision.market_context.current_price * 100).toFixed(2)}%
                                                </p>
                                              )}
                                            </div>
                                          )}
                                        </div>
                                        {decision.stop_loss && decision.take_profit && decision.market_context?.current_price && (
                                          <div className="mt-2 text-xs text-dark-500">
                                            Risk/Reward: 1:{((decision.take_profit - decision.market_context.current_price) / (decision.market_context.current_price - decision.stop_loss)).toFixed(2)}
                                          </div>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                )}

                                {decision.reasoning && (
                                  <div>
                                    <p className="text-dark-500 text-xs mb-1">Reasoning</p>
                                    <p className="text-dark-300 text-xs bg-dark-900 rounded p-2 max-h-32 overflow-y-auto">
                                      {decision.reasoning}
                                    </p>
                                  </div>
                                )}

                                {decision.risk_assessment && (
                                  <div>
                                    <p className="text-dark-500 text-xs mb-1">Risk Assessment</p>
                                    <p className="text-dark-300 text-xs bg-dark-900 rounded p-2">
                                      {decision.risk_assessment}
                                    </p>
                                  </div>
                                )}

                                {/* Market Context */}
                                {decision.market_context && Object.keys(decision.market_context).length > 0 && (
                                  <details className="text-xs">
                                    <summary className="text-dark-500 cursor-pointer hover:text-dark-400">
                                      Market Context ({Object.keys(decision.market_context).length} indicators)
                                    </summary>
                                    <div className="mt-2 bg-dark-900 rounded p-2 max-h-32 overflow-y-auto space-y-1">
                                      {Object.entries(decision.market_context).map(([key, value]) => (
                                        <div key={key} className="flex items-center justify-between">
                                          <span className="text-dark-500">{key}</span>
                                          <span className="text-dark-300 font-mono">
                                            {typeof value === 'number' ? value.toFixed(4) : String(value)}
                                          </span>
                                        </div>
                                      ))}
                                    </div>
                                  </details>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
