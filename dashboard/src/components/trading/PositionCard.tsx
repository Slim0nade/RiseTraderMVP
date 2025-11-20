import React from 'react';
import { TrendingUp, TrendingDown, X } from 'lucide-react';
import { Position } from '@/types';
import { useFormatters } from '@/hooks/useFormatters';
import { cn } from '@/utils/cn';

interface PositionCardProps {
  position: Position;
  onClose?: (positionId: string) => void;
}

export const PositionCard: React.FC<PositionCardProps> = ({ position, onClose }) => {
  const formatters = useFormatters();
  const isProfit = position.unrealized_pnl >= 0;

  return (
    <div className="bg-dark-900 rounded-lg border border-dark-700 p-4 hover:border-dark-600 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'px-2 py-1 rounded text-xs font-bold',
              position.action === 'BUY'
                ? 'bg-success-500/10 text-success-500'
                : 'bg-danger-500/10 text-danger-500'
            )}
          >
            {position.action}
          </div>
          <div>
            <h3 className="font-semibold text-dark-50">{position.symbol}</h3>
            <p className="text-xs text-dark-500">{position.strategy_name || 'Manual'}</p>
          </div>
        </div>

        {onClose && (
          <button
            onClick={() => onClose(position.id)}
            className="p-1 hover:bg-dark-800 rounded transition-colors"
            title="Close position"
          >
            <X className="w-4 h-4 text-dark-400" />
          </button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <p className="text-xs text-dark-500 mb-0.5">Entry</p>
          <p className="text-sm font-mono text-dark-200">
            {formatters.price(position.entry_price)}
          </p>
        </div>
        <div>
          <p className="text-xs text-dark-500 mb-0.5">Current</p>
          <p className="text-sm font-mono text-dark-200">
            {formatters.price(position.current_price)}
          </p>
        </div>
        <div>
          <p className="text-xs text-dark-500 mb-0.5">Quantity</p>
          <p className="text-sm font-mono text-dark-200">{position.quantity}</p>
        </div>
        <div>
          <p className="text-xs text-dark-500 mb-0.5">Duration</p>
          <p className="text-sm text-dark-200">
            {formatters.relativeTime(position.entry_time)}
          </p>
        </div>
      </div>

      <div className="pt-3 border-t border-dark-800 flex items-center justify-between">
        <div>
          <p className="text-xs text-dark-500 mb-0.5">Unrealized P&L</p>
          <div className="flex items-center gap-1.5">
            {isProfit ? (
              <TrendingUp className="w-4 h-4 text-success-500" />
            ) : (
              <TrendingDown className="w-4 h-4 text-danger-500" />
            )}
            <p
              className={cn(
                'text-lg font-bold',
                isProfit ? 'text-success-500' : 'text-danger-500'
              )}
            >
              {formatters.currency(position.unrealized_pnl)}
            </p>
          </div>
        </div>

        {(position.stop_loss || position.take_profit) && (
          <div className="text-right">
            {position.stop_loss && (
              <p className="text-xs text-dark-500">
                SL: <span className="text-danger-400">{formatters.price(position.stop_loss)}</span>
              </p>
            )}
            {position.take_profit && (
              <p className="text-xs text-dark-500">
                TP:{' '}
                <span className="text-success-400">{formatters.price(position.take_profit)}</span>
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
