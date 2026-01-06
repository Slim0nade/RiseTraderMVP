import React, { useState } from 'react';
import { TrendingUp, TrendingDown, Clock, Target, AlertTriangle, CheckCircle, X, Info } from 'lucide-react';
import type { SimulatedTrade } from '@/types';
import { format, formatDistanceStrict } from 'date-fns';

interface PositionsListProps {
  trades: SimulatedTrade[];
  loading?: boolean;
}

export const PositionsList: React.FC<PositionsListProps> = ({
  trades,
  loading = false,
}) => {
  const [filterStatus, setFilterStatus] = useState<'all' | 'open' | 'closed'>('all');
  const [sortBy, setSortBy] = useState<'time' | 'pnl' | 'duration'>('time');
  const [hoveredTrade, setHoveredTrade] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="bg-dark-900 rounded-lg border border-dark-700 p-8 text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500 mx-auto"></div>
        <p className="text-dark-400 mt-4">Loading positions...</p>
      </div>
    );
  }

  if (!trades || trades.length === 0) {
    return (
      <div className="bg-dark-900 rounded-lg border border-dark-700 p-8 text-center">
        <AlertTriangle className="w-12 h-12 text-dark-600 mx-auto mb-4" />
        <p className="text-dark-400">No positions found</p>
      </div>
    );
  }

  // Helper function to calculate P&L (must be defined before sort uses it)
  const calculatePnL = (trade: SimulatedTrade): number => {
    // Priority 1: Use net_pnl from backend (includes fees - most accurate)
    if (trade.net_pnl !== undefined && trade.net_pnl !== null) {
      return typeof trade.net_pnl === 'number' ? trade.net_pnl : parseFloat(trade.net_pnl as any);
    }

    // Priority 2: Use legacy pnl field if available
    if (trade.pnl !== undefined && trade.pnl !== null) {
      return typeof trade.pnl === 'number' ? trade.pnl : parseFloat(trade.pnl as any);
    }

    // Priority 3: Calculate from entry/exit prices (doesn't include fees - less accurate)
    if (!trade.exit_price) return 0;

    const entryPrice = typeof trade.entry_price === 'number' ? trade.entry_price : parseFloat(trade.entry_price || '0');
    const exitPrice = typeof trade.exit_price === 'number' ? trade.exit_price : parseFloat(trade.exit_price);
    const quantity = typeof trade.quantity === 'number' ? trade.quantity : parseFloat(trade.quantity || '0');

    if (trade.action === 'BUY') {
      return (exitPrice - entryPrice) * quantity;
    } else {
      return (entryPrice - exitPrice) * quantity;
    }
  };

  // Filter trades
  const filteredTrades = trades.filter((trade) => {
    if (filterStatus === 'all') return true;
    if (filterStatus === 'open') return !trade.exit_timestamp;
    if (filterStatus === 'closed') return !!trade.exit_timestamp;
    return true;
  });

  // Sort trades
  const sortedTrades = [...filteredTrades].sort((a, b) => {
    if (sortBy === 'time') {
      return new Date(b.entry_timestamp).getTime() - new Date(a.entry_timestamp).getTime();
    }
    if (sortBy === 'pnl') {
      return calculatePnL(b) - calculatePnL(a);
    }
    if (sortBy === 'duration') {
      const aDuration = a.exit_timestamp
        ? new Date(a.exit_timestamp).getTime() - new Date(a.entry_timestamp).getTime()
        : Date.now() - new Date(a.entry_timestamp).getTime();
      const bDuration = b.exit_timestamp
        ? new Date(b.exit_timestamp).getTime() - new Date(b.entry_timestamp).getTime()
        : Date.now() - new Date(b.entry_timestamp).getTime();
      return bDuration - aDuration;
    }
    return 0;
  });

  const openTrades = trades.filter((t) => !t.exit_timestamp);
  const closedTrades = trades.filter((t) => !!t.exit_timestamp);
  const totalPnL = closedTrades.reduce((sum, t) => sum + calculatePnL(t), 0);
  const winningTrades = closedTrades.filter((t) => calculatePnL(t) > 0);
  const losingTrades = closedTrades.filter((t) => calculatePnL(t) < 0);

  // Determine exit reason
  const getExitReason = (trade: SimulatedTrade): { label: string; color: string; icon: React.ReactNode } => {
    if (!trade.exit_timestamp) {
      return {
        label: 'Open',
        color: 'text-primary-500',
        icon: <Clock className="w-4 h-4" />
      };
    }

    // Convert to numbers to avoid type errors
    const exitPrice = trade.exit_price ? (typeof trade.exit_price === 'number' ? trade.exit_price : parseFloat(trade.exit_price)) : null;
    const entryPrice = typeof trade.entry_price === 'number' ? trade.entry_price : parseFloat(trade.entry_price || '0');
    const stopLoss = trade.stop_loss ? (typeof trade.stop_loss === 'number' ? trade.stop_loss : parseFloat(trade.stop_loss)) : null;
    const takeProfit = trade.take_profit ? (typeof trade.take_profit === 'number' ? trade.take_profit : parseFloat(trade.take_profit)) : null;

    // Check if hit stop loss
    if (stopLoss && exitPrice) {
      const slDistance = Math.abs(exitPrice - stopLoss);
      const currentDistance = Math.abs(exitPrice - entryPrice);
      if (slDistance < currentDistance * 0.01) { // Within 1% of SL
        return {
          label: 'Stop Loss',
          color: 'text-danger-500',
          icon: <X className="w-4 h-4" />
        };
      }
    }

    // Check if hit take profit
    if (takeProfit && exitPrice) {
      const tpDistance = Math.abs(exitPrice - takeProfit);
      const currentDistance = Math.abs(exitPrice - entryPrice);
      if (tpDistance < currentDistance * 0.01) { // Within 1% of TP
        return {
          label: 'Take Profit',
          color: 'text-success-500',
          icon: <Target className="w-4 h-4" />
        };
      }
    }

    // Agent decision to close
    return {
      label: 'Agent Decision',
      color: 'text-warning-500',
      icon: <CheckCircle className="w-4 h-4" />
    };
  };

  // Get tooltip message for exit reason
  const getExitTooltip = (trade: SimulatedTrade): string | null => {
    if (!trade.exit_timestamp) return null;

    const exitPrice = trade.exit_price ? (typeof trade.exit_price === 'number' ? trade.exit_price : parseFloat(trade.exit_price)) : null;
    const entryPrice = typeof trade.entry_price === 'number' ? trade.entry_price : parseFloat(trade.entry_price || '0');
    const stopLoss = trade.stop_loss ? (typeof trade.stop_loss === 'number' ? trade.stop_loss : parseFloat(trade.stop_loss)) : null;
    const takeProfit = trade.take_profit ? (typeof trade.take_profit === 'number' ? trade.take_profit : parseFloat(trade.take_profit)) : null;

    // Check if hit stop loss
    if (stopLoss && exitPrice) {
      const slDistance = Math.abs(exitPrice - stopLoss);
      const currentDistance = Math.abs(exitPrice - entryPrice);
      if (slDistance < currentDistance * 0.01) {
        const lossAmount = trade.action === 'BUY'
          ? (exitPrice - entryPrice) * (typeof trade.quantity === 'number' ? trade.quantity : parseFloat(trade.quantity || '0'))
          : (entryPrice - exitPrice) * (typeof trade.quantity === 'number' ? trade.quantity : parseFloat(trade.quantity || '0'));
        return `Stop Loss triggered at $${exitPrice.toFixed(2)}. Loss limited to $${Math.abs(lossAmount).toFixed(2)} (${((lossAmount / (entryPrice * (typeof trade.quantity === 'number' ? trade.quantity : parseFloat(trade.quantity || '0')))) * 100).toFixed(2)}%). Risk management protected your capital.`;
      }
    }

    // Check if hit take profit
    if (takeProfit && exitPrice) {
      const tpDistance = Math.abs(exitPrice - takeProfit);
      const currentDistance = Math.abs(exitPrice - entryPrice);
      if (tpDistance < currentDistance * 0.01) {
        const profitAmount = trade.action === 'BUY'
          ? (exitPrice - entryPrice) * (typeof trade.quantity === 'number' ? trade.quantity : parseFloat(trade.quantity || '0'))
          : (entryPrice - exitPrice) * (typeof trade.quantity === 'number' ? trade.quantity : parseFloat(trade.quantity || '0'));
        return `Take Profit achieved at $${exitPrice.toFixed(2)}. Secured profit of $${profitAmount.toFixed(2)} (${((profitAmount / (entryPrice * (typeof trade.quantity === 'number' ? trade.quantity : parseFloat(trade.quantity || '0')))) * 100).toFixed(2)}%). Target successfully reached!`;
      }
    }

    // Agent decision
    return `Position closed by agent decision at $${exitPrice?.toFixed(2)}. The agent analyzed market conditions and decided to exit. Check the Agent Decisions panel for detailed reasoning and conviction score.`;
  };

  return (
    <div className="space-y-4">
      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="bg-dark-800 rounded-lg p-4">
          <p className="text-xs text-dark-500 mb-1">Total Positions</p>
          <p className="text-2xl font-bold text-dark-50">{trades.length}</p>
        </div>
        <div className="bg-dark-800 rounded-lg p-4">
          <p className="text-xs text-dark-500 mb-1">Open</p>
          <p className="text-2xl font-bold text-primary-500">{openTrades.length}</p>
        </div>
        <div className="bg-dark-800 rounded-lg p-4">
          <p className="text-xs text-dark-500 mb-1">Closed</p>
          <p className="text-2xl font-bold text-dark-300">{closedTrades.length}</p>
        </div>
        <div className="bg-dark-800 rounded-lg p-4">
          <p className="text-xs text-dark-500 mb-1">Win Rate</p>
          <p className="text-2xl font-bold text-success-500">
            {closedTrades.length > 0
              ? ((winningTrades.length / closedTrades.length) * 100).toFixed(1)
              : 0}%
          </p>
        </div>
        <div className="bg-dark-800 rounded-lg p-4">
          <p className="text-xs text-dark-500 mb-1">Total P&L</p>
          <p className={`text-2xl font-bold ${totalPnL >= 0 ? 'text-success-500' : 'text-danger-500'}`}>
            ${totalPnL.toFixed(2)}
          </p>
        </div>
      </div>

      {/* Filters and Sorting */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex gap-2">
          <button
            onClick={() => setFilterStatus('all')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              filterStatus === 'all'
                ? 'bg-primary-500 text-white'
                : 'bg-dark-800 text-dark-300 hover:bg-dark-700'
            }`}
          >
            All ({trades.length})
          </button>
          <button
            onClick={() => setFilterStatus('open')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              filterStatus === 'open'
                ? 'bg-primary-500 text-white'
                : 'bg-dark-800 text-dark-300 hover:bg-dark-700'
            }`}
          >
            Open ({openTrades.length})
          </button>
          <button
            onClick={() => setFilterStatus('closed')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              filterStatus === 'closed'
                ? 'bg-primary-500 text-white'
                : 'bg-dark-800 text-dark-300 hover:bg-dark-700'
            }`}
          >
            Closed ({closedTrades.length})
          </button>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-dark-500">Sort by:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as 'time' | 'pnl' | 'duration')}
            className="px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-sm text-dark-200 focus:outline-none focus:border-primary-500"
          >
            <option value="time">Time</option>
            <option value="pnl">P&L</option>
            <option value="duration">Duration</option>
          </select>
        </div>
      </div>

      {/* Positions Table */}
      <div className="bg-dark-900 rounded-lg border border-dark-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-dark-700 bg-dark-800">
                <th className="text-left p-4 text-xs font-semibold text-dark-500 uppercase">Symbol</th>
                <th className="text-center p-4 text-xs font-semibold text-dark-500 uppercase">Action</th>
                <th className="text-right p-4 text-xs font-semibold text-dark-500 uppercase">Quantity</th>
                <th className="text-right p-4 text-xs font-semibold text-dark-500 uppercase">Entry Price</th>
                <th className="text-right p-4 text-xs font-semibold text-dark-500 uppercase">Exit Price</th>
                <th className="text-right p-4 text-xs font-semibold text-dark-500 uppercase">P&L</th>
                <th className="text-left p-4 text-xs font-semibold text-dark-500 uppercase">Open Time</th>
                <th className="text-left p-4 text-xs font-semibold text-dark-500 uppercase">Close Time</th>
                <th className="text-right p-4 text-xs font-semibold text-dark-500 uppercase">Duration</th>
                <th className="text-center p-4 text-xs font-semibold text-dark-500 uppercase">Exit Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-dark-700">
              {sortedTrades.map((trade) => {
                const isOpen = !trade.exit_timestamp;
                const exitReason = getExitReason(trade);
                const duration = trade.exit_timestamp
                  ? formatDistanceStrict(
                      new Date(trade.entry_timestamp),
                      new Date(trade.exit_timestamp)
                    )
                  : formatDistanceStrict(new Date(trade.entry_timestamp), new Date());

                // Ensure all price values are numbers
                const entryPrice = typeof trade.entry_price === 'number' ? trade.entry_price : parseFloat(trade.entry_price || '0');
                const exitPrice = trade.exit_price ? (typeof trade.exit_price === 'number' ? trade.exit_price : parseFloat(trade.exit_price)) : null;
                const quantity = typeof trade.quantity === 'number' ? trade.quantity : parseFloat(trade.quantity || '0');
                const stopLoss = trade.stop_loss ? (typeof trade.stop_loss === 'number' ? trade.stop_loss : parseFloat(trade.stop_loss)) : null;
                const takeProfit = trade.take_profit ? (typeof trade.take_profit === 'number' ? trade.take_profit : parseFloat(trade.take_profit)) : null;

                // Calculate P&L if not provided by the database
                let pnl: number | undefined;
                if (trade.pnl !== undefined && trade.pnl !== null) {
                  // Use database-provided P&L
                  pnl = typeof trade.pnl === 'number' ? trade.pnl : parseFloat(trade.pnl as any);
                } else if (exitPrice !== null) {
                  // Calculate P&L based on action type
                  if (trade.action === 'BUY') {
                    // BUY: profit when price goes up
                    pnl = (exitPrice - entryPrice) * quantity;
                  } else {
                    // SELL: profit when price goes down
                    pnl = (entryPrice - exitPrice) * quantity;
                  }
                }

                const pnlPercent = exitPrice && pnl !== undefined
                  ? (pnl / (entryPrice * quantity)) * 100
                  : 0;

                return (
                  <tr
                    key={trade.id}
                    className="hover:bg-dark-800/50 transition-colors"
                  >
                    <td className="p-4">
                      <span className="font-semibold text-dark-50">{trade.symbol}</span>
                    </td>
                    <td className="p-4">
                      <div className="flex items-center justify-center">
                        {trade.action === 'BUY' ? (
                          <div className="flex items-center gap-1 text-success-500">
                            <TrendingUp className="w-4 h-4" />
                            <span className="text-sm font-semibold">BUY</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1 text-danger-500">
                            <TrendingDown className="w-4 h-4" />
                            <span className="text-sm font-semibold">SELL</span>
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="p-4 text-right">
                      <span className="text-sm text-dark-300 font-mono">{trade.quantity}</span>
                    </td>
                    <td className="p-4 text-right">
                      <span className="text-sm font-mono font-semibold text-dark-50">
                        ${entryPrice.toFixed(2)}
                      </span>
                    </td>
                    <td className="p-4 text-right">
                      {exitPrice ? (
                        <span className="text-sm font-mono font-semibold text-dark-50">
                          ${exitPrice.toFixed(2)}
                        </span>
                      ) : (
                        <span className="text-sm text-dark-500">-</span>
                      )}
                    </td>
                    <td className="p-4 text-right">
                      {pnl !== undefined ? (
                        <div>
                          <span
                            className={`text-sm font-mono font-bold ${
                              pnl >= 0 ? 'text-success-500' : 'text-danger-500'
                            }`}
                          >
                            {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                          </span>
                          <div
                            className={`text-xs font-mono ${
                              pnlPercent >= 0 ? 'text-success-500' : 'text-danger-500'
                            }`}
                          >
                            {pnlPercent >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%
                          </div>
                        </div>
                      ) : (
                        <span className="text-sm text-dark-500">-</span>
                      )}
                    </td>
                    <td className="p-4">
                      <div className="text-sm text-dark-300">
                        {format(new Date(trade.entry_timestamp), 'MMM dd, HH:mm:ss')}
                      </div>
                    </td>
                    <td className="p-4">
                      {trade.exit_timestamp ? (
                        <div className="text-sm text-dark-300">
                          {format(new Date(trade.exit_timestamp), 'MMM dd, HH:mm:ss')}
                        </div>
                      ) : (
                        <span className="text-sm text-dark-500">-</span>
                      )}
                    </td>
                    <td className="p-4 text-right">
                      <span className="text-sm font-mono text-dark-300">{duration}</span>
                    </td>
                    <td className="p-4 relative">
                      <div
                        className="flex items-center justify-center gap-2 cursor-help"
                        onMouseEnter={() => setHoveredTrade(trade.id)}
                        onMouseLeave={() => setHoveredTrade(null)}
                      >
                        <span className={`${exitReason.color}`}>
                          {exitReason.icon}
                        </span>
                        <span className={`text-xs font-semibold ${exitReason.color}`}>
                          {exitReason.label}
                        </span>
                        {trade.exit_timestamp && (
                          <Info className="w-3 h-3 text-dark-500" />
                        )}

                        {/* Tooltip */}
                        {hoveredTrade === trade.id && getExitTooltip(trade) && (
                          <div className="absolute right-0 bottom-full mb-2 z-10 w-96 bg-dark-800 border border-dark-600 rounded-lg shadow-xl p-4 pointer-events-none">
                            <div className="flex items-start gap-2">
                              {exitReason.icon}
                              <div>
                                <p className="text-sm font-semibold text-dark-50 mb-1">{exitReason.label}</p>
                                <p className="text-xs text-dark-300 leading-relaxed">
                                  {getExitTooltip(trade)}
                                </p>
                              </div>
                            </div>
                            {/* Arrow pointing down */}
                            <div className="absolute right-4 top-full w-0 h-0 border-l-8 border-r-8 border-t-8 border-transparent border-t-dark-600"></div>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {sortedTrades.length === 0 && (
          <div className="p-8 text-center text-dark-500">
            No positions found for the selected filter
          </div>
        )}
      </div>
    </div>
  );
};
