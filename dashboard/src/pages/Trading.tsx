import React, { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Target, History, X } from 'lucide-react';
import { PositionCard } from '@/components/trading/PositionCard';
import { TradeHistoryTable } from '@/components/trading/TradeHistoryTable';
import { tradingApi } from '@/api/endpoints';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useTradingStore } from '@/store/tradingStore';
import toast from 'react-hot-toast';

export const Trading: React.FC = () => {
  const queryClient = useQueryClient();
  const { subscribe } = useWebSocket();
  const { positions, updatePosition, removePosition, recentTrades, addTrade } = useTradingStore();
  const [historyPage, setHistoryPage] = useState(1);

  // Fetch open positions
  const { data: positionsData, isLoading: positionsLoading } = useQuery({
    queryKey: ['positions'],
    queryFn: tradingApi.getOpenPositions,
    refetchInterval: 3000,
  });

  // Fetch trade history
  const { data: historyData, isLoading: historyLoading } = useQuery({
    queryKey: ['trade-history', historyPage],
    queryFn: () => tradingApi.getTradeHistory({ page: historyPage, page_size: 20 }),
    refetchInterval: 10000,
  });

  // Update store when data changes
  useEffect(() => {
    if (positionsData) {
      positionsData.forEach(updatePosition);
    }
  }, [positionsData, updatePosition]);

  // Subscribe to WebSocket updates
  useEffect(() => {
    const unsubscribePositionOpened = subscribe('position_opened', (data) => {
      updatePosition(data);
      toast.success(`Position opened: ${data.symbol} ${data.action}`);
    });

    const unsubscribePositionUpdated = subscribe('position_updated', (data) => {
      updatePosition(data);
    });

    const unsubscribePositionClosed = subscribe('position_closed', (data) => {
      removePosition(data.id);
      addTrade(data);
      const profit = data.realized_pnl >= 0;
      toast.success(`Position closed: ${profit ? '+' : ''}${data.realized_pnl.toFixed(2)}`, {
        icon: profit ? '📈' : '📉',
      });
    });

    return () => {
      unsubscribePositionOpened();
      unsubscribePositionUpdated();
      unsubscribePositionClosed();
    };
  }, [subscribe, updatePosition, removePosition, addTrade]);

  // Close position mutation
  const closePositionMutation = useMutation({
    mutationFn: tradingApi.closePosition,
    onSuccess: (_, positionId) => {
      toast.success('Position closed successfully');
      queryClient.invalidateQueries({ queryKey: ['positions'] });
      queryClient.invalidateQueries({ queryKey: ['trade-history'] });
    },
    onError: (error) => {
      toast.error('Failed to close position');
      console.error(error);
    },
  });

  const handleClosePosition = (positionId: string) => {
    if (confirm('Are you sure you want to close this position?')) {
      closePositionMutation.mutate(positionId);
    }
  };

  const totalUnrealizedPnL = positions.reduce((sum, p) => sum + p.unrealized_pnl, 0);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-dark-50 mb-2">Trading</h1>
        <p className="text-dark-400">Monitor and manage your trading positions</p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-primary-500/10 rounded-lg">
              <Target className="w-6 h-6 text-primary-500" />
            </div>
            <div>
              <p className="text-sm text-dark-500">Open Positions</p>
              <p className="text-3xl font-bold text-dark-50">{positions.length}</p>
            </div>
          </div>
        </div>

        <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
          <div className="flex items-center gap-3">
            <div
              className={`p-3 rounded-lg ${
                totalUnrealizedPnL >= 0 ? 'bg-success-500/10' : 'bg-danger-500/10'
              }`}
            >
              <Target
                className={`w-6 h-6 ${
                  totalUnrealizedPnL >= 0 ? 'text-success-500' : 'text-danger-500'
                }`}
              />
            </div>
            <div>
              <p className="text-sm text-dark-500">Unrealized P&L</p>
              <p
                className={`text-3xl font-bold ${
                  totalUnrealizedPnL >= 0 ? 'text-success-500' : 'text-danger-500'
                }`}
              >
                ${totalUnrealizedPnL.toFixed(2)}
              </p>
            </div>
          </div>
        </div>

        <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-primary-500/10 rounded-lg">
              <History className="w-6 h-6 text-primary-500" />
            </div>
            <div>
              <p className="text-sm text-dark-500">Total Trades</p>
              <p className="text-3xl font-bold text-dark-50">
                {historyData?.total || 0}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Open Positions */}
      <div>
        <h2 className="text-xl font-semibold text-dark-50 mb-4">Open Positions</h2>
        {positionsLoading ? (
          <div className="bg-dark-900 rounded-lg border border-dark-700 p-8 text-center">
            <p className="text-dark-400">Loading positions...</p>
          </div>
        ) : positions.length === 0 ? (
          <div className="bg-dark-900 rounded-lg border border-dark-700 p-8 text-center text-dark-500">
            No open positions
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {positions.map((position) => (
              <PositionCard
                key={position.id}
                position={position}
                onClose={handleClosePosition}
              />
            ))}
          </div>
        )}
      </div>

      {/* Trade History */}
      <div>
        <h2 className="text-xl font-semibold text-dark-50 mb-4">Trade History</h2>
        <TradeHistoryTable
          trades={historyData?.items || []}
          loading={historyLoading}
        />

        {/* Pagination */}
        {historyData && historyData.total_pages > 1 && (
          <div className="flex items-center justify-center gap-2 mt-4">
            <button
              onClick={() => setHistoryPage((p) => Math.max(1, p - 1))}
              disabled={historyPage === 1}
              className="px-4 py-2 bg-dark-800 text-dark-200 rounded-lg hover:bg-dark-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Previous
            </button>
            <span className="text-dark-400">
              Page {historyPage} of {historyData.total_pages}
            </span>
            <button
              onClick={() => setHistoryPage((p) => Math.min(historyData.total_pages, p + 1))}
              disabled={historyPage === historyData.total_pages}
              className="px-4 py-2 bg-dark-800 text-dark-200 rounded-lg hover:bg-dark-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
