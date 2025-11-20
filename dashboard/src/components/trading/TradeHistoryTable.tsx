import React from 'react';
import { Trade } from '@/types';
import { useFormatters } from '@/hooks/useFormatters';
import { cn } from '@/utils/cn';

interface TradeHistoryTableProps {
  trades: Trade[];
  loading?: boolean;
}

export const TradeHistoryTable: React.FC<TradeHistoryTableProps> = ({ trades, loading }) => {
  const formatters = useFormatters();

  if (loading) {
    return (
      <div className="bg-dark-900 rounded-lg border border-dark-700 p-8 text-center">
        <div className="animate-pulse">Loading trades...</div>
      </div>
    );
  }

  if (trades.length === 0) {
    return (
      <div className="bg-dark-900 rounded-lg border border-dark-700 p-8 text-center text-dark-500">
        No trades found
      </div>
    );
  }

  return (
    <div className="bg-dark-900 rounded-lg border border-dark-700 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-dark-800 border-b border-dark-700">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-dark-400 uppercase tracking-wider">
                Symbol
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-dark-400 uppercase tracking-wider">
                Action
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-dark-400 uppercase tracking-wider">
                Entry
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-dark-400 uppercase tracking-wider">
                Exit
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-dark-400 uppercase tracking-wider">
                Qty
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-dark-400 uppercase tracking-wider">
                P&L
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-dark-400 uppercase tracking-wider">
                Strategy
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-dark-400 uppercase tracking-wider">
                Time
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-dark-800">
            {trades.map((trade) => (
              <tr key={trade.id} className="hover:bg-dark-800/50 transition-colors">
                <td className="px-4 py-3 text-sm font-medium text-dark-200">
                  {trade.symbol}
                </td>
                <td className="px-4 py-3 text-sm">
                  <span
                    className={cn(
                      'px-2 py-1 rounded text-xs font-bold',
                      trade.action === 'BUY'
                        ? 'bg-success-500/10 text-success-500'
                        : 'bg-danger-500/10 text-danger-500'
                    )}
                  >
                    {trade.action}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm font-mono text-right text-dark-300">
                  {formatters.price(trade.entry_price)}
                </td>
                <td className="px-4 py-3 text-sm font-mono text-right text-dark-300">
                  {trade.exit_price ? formatters.price(trade.exit_price) : '-'}
                </td>
                <td className="px-4 py-3 text-sm font-mono text-right text-dark-300">
                  {trade.quantity}
                </td>
                <td className="px-4 py-3 text-sm font-bold text-right">
                  {trade.realized_pnl !== undefined ? (
                    <span
                      className={cn(
                        trade.realized_pnl >= 0 ? 'text-success-500' : 'text-danger-500'
                      )}
                    >
                      {formatters.currency(trade.realized_pnl)}
                    </span>
                  ) : (
                    <span className="text-dark-500">-</span>
                  )}
                </td>
                <td className="px-4 py-3 text-sm text-dark-400">
                  {trade.strategy_name || 'Manual'}
                </td>
                <td className="px-4 py-3 text-sm text-dark-400">
                  {formatters.date(trade.entry_time, 'MMM dd, HH:mm')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
