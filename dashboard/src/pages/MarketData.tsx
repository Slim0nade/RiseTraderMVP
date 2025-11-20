import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { TrendingUp, Clock } from 'lucide-react';
import { PriceChart } from '@/components/charts/PriceChart';
import { marketDataApi } from '@/api/endpoints';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useMarketStore } from '@/store/marketStore';
import { useFormatters } from '@/hooks/useFormatters';
import { cn } from '@/utils/cn';

const SYMBOLS = ['CrudeOIL', 'DXY', 'VIX'];
const TIMEFRAMES = ['M1', 'M5', 'M15', 'H1'];

export const MarketData: React.FC = () => {
  const formatters = useFormatters();
  const { subscribe } = useWebSocket();
  const {
    currentSymbol,
    currentTimeframe,
    marketData,
    latestTicks,
    setCurrentSymbol,
    setCurrentTimeframe,
    setMarketData,
    updateLatestTick,
    appendMarketData,
  } = useMarketStore();

  // Fetch historical data
  const { data: historicalData, isLoading } = useQuery({
    queryKey: ['market-data', currentSymbol, currentTimeframe],
    queryFn: () => marketDataApi.getHistoricalData(currentSymbol, currentTimeframe, 500),
    refetchInterval: 10000,
  });

  // Update store when historical data changes
  useEffect(() => {
    if (historicalData) {
      setMarketData(currentSymbol, historicalData);
    }
  }, [historicalData, currentSymbol, setMarketData]);

  // Subscribe to real-time ticks
  useEffect(() => {
    const unsubscribe = subscribe('new_tick', (data) => {
      if (data.symbol === currentSymbol) {
        updateLatestTick(data.symbol, data);
        if (data.timeframe === currentTimeframe) {
          appendMarketData(data.symbol, data);
        }
      }
    });

    return unsubscribe;
  }, [subscribe, currentSymbol, currentTimeframe, updateLatestTick, appendMarketData]);

  const chartData = marketData[currentSymbol] || [];
  const latestTick = latestTicks[currentSymbol];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-dark-50 mb-2">Market Data</h1>
        <p className="text-dark-400">Real-time market data and price charts</p>
      </div>

      {/* Symbol & Timeframe Selector */}
      <div className="bg-dark-900 rounded-lg border border-dark-700 p-4">
        <div className="flex flex-wrap items-center gap-4">
          {/* Symbol Selector */}
          <div>
            <label className="text-sm text-dark-500 mb-2 block">Symbol</label>
            <div className="flex gap-2">
              {SYMBOLS.map((symbol) => (
                <button
                  key={symbol}
                  onClick={() => setCurrentSymbol(symbol)}
                  className={cn(
                    'px-4 py-2 rounded-lg font-medium transition-colors',
                    currentSymbol === symbol
                      ? 'bg-primary-500 text-white'
                      : 'bg-dark-800 text-dark-300 hover:bg-dark-700'
                  )}
                >
                  {symbol}
                </button>
              ))}
            </div>
          </div>

          {/* Timeframe Selector */}
          <div>
            <label className="text-sm text-dark-500 mb-2 block">Timeframe</label>
            <div className="flex gap-2">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  onClick={() => setCurrentTimeframe(tf)}
                  className={cn(
                    'px-4 py-2 rounded-lg font-medium transition-colors',
                    currentTimeframe === tf
                      ? 'bg-primary-500 text-white'
                      : 'bg-dark-800 text-dark-300 hover:bg-dark-700'
                  )}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Current Price Card */}
      {latestTick && (
        <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold text-dark-50 mb-1">{currentSymbol}</h2>
              <p className="text-4xl font-bold text-primary-500">
                {formatters.price(latestTick.close)}
              </p>
            </div>
            <div className="text-right">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp className="w-5 h-5 text-success-500" />
                <span className="text-lg font-semibold text-success-500">
                  +{((latestTick.close - latestTick.open) / latestTick.open * 100).toFixed(2)}%
                </span>
              </div>
              <div className="flex items-center gap-2 text-dark-400">
                <Clock className="w-4 h-4" />
                <span className="text-sm">{formatters.relativeTime(latestTick.timestamp)}</span>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-4 mt-6 pt-6 border-t border-dark-800">
            <div>
              <p className="text-sm text-dark-500 mb-1">Open</p>
              <p className="text-lg font-mono text-dark-200">
                {formatters.price(latestTick.open)}
              </p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">High</p>
              <p className="text-lg font-mono text-success-500">
                {formatters.price(latestTick.high)}
              </p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Low</p>
              <p className="text-lg font-mono text-danger-500">
                {formatters.price(latestTick.low)}
              </p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Volume</p>
              <p className="text-lg font-mono text-dark-200">
                {formatters.number(latestTick.volume)}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Price Chart */}
      <div>
        {isLoading ? (
          <div className="bg-dark-900 rounded-lg border border-dark-700 p-8 text-center">
            <p className="text-dark-400">Loading chart data...</p>
          </div>
        ) : (
          <PriceChart data={chartData} height={500} />
        )}
      </div>

      {/* Market Statistics */}
      {chartData.length > 0 && (
        <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
          <h3 className="text-lg font-semibold text-dark-50 mb-4">Statistics</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-dark-500 mb-1">Data Points</p>
              <p className="text-2xl font-bold text-dark-50">{chartData.length}</p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Avg Volume</p>
              <p className="text-2xl font-bold text-dark-50">
                {formatters.number(
                  chartData.reduce((sum, d) => sum + d.volume, 0) / chartData.length
                )}
              </p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Period High</p>
              <p className="text-2xl font-bold text-success-500">
                {formatters.price(Math.max(...chartData.map((d) => d.high)))}
              </p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Period Low</p>
              <p className="text-2xl font-bold text-danger-500">
                {formatters.price(Math.min(...chartData.map((d) => d.low)))}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
