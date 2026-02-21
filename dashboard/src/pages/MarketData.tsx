import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { TrendingUp, Clock, Database, Search } from 'lucide-react';
import { PriceChart } from '@/components/charts/PriceChart';
import { marketDataApi } from '@/api/endpoints';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useMarketStore } from '@/store/marketStore';
import { useFormatters } from '@/hooks/useFormatters';
import { cn } from '@/utils/cn';

const TIMEFRAMES = ['M1', 'M5', 'M15', 'H1', 'H4', 'D1'];

// Source color palette for multi-source overlay
const SOURCE_COLORS: Record<string, string> = {
  MT4: '#3b82f6',       // blue
  CSV: '#10b981',       // green
  DUKASCOPY: '#f59e0b', // amber
  BARCHART: '#8b5cf6',  // purple
  BC: '#ec4899',        // pink
  HISTDATA: '#06b6d4',  // cyan
};

const getSourceColor = (source: string) =>
  SOURCE_COLORS[source] || '#94a3b8';

interface SymbolInfo {
  symbol: string;
  data_points_count: number;
  latest_time?: string;
}

interface SourceInfo {
  source: string;
  data_points: number;
  latest_time: string | null;
  first_time: string | null;
}

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

  const [availableTimeframes, setAvailableTimeframes] = useState<Record<string, string[]>>({});
  const [symbolSearch, setSymbolSearch] = useState('');
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [sourceDataMap, setSourceDataMap] = useState<Record<string, any[]>>({});

  // Fetch all available symbols dynamically
  const { data: allSymbols = [] } = useQuery<SymbolInfo[]>({
    queryKey: ['symbols-list'],
    queryFn: () => marketDataApi.getSymbols(),
    staleTime: 60000, // Cache for 1 minute
  });

  // Fetch available sources for current symbol + timeframe
  const { data: availableSources = [] } = useQuery<SourceInfo[]>({
    queryKey: ['sources', currentSymbol, currentTimeframe],
    queryFn: () => marketDataApi.getSourcesForSymbol(currentSymbol, currentTimeframe),
    enabled: !!currentSymbol,
  });

  // Fetch available timeframes on mount
  useEffect(() => {
    const fetchAvailableTimeframes = async () => {
      try {
        const timeframes = await marketDataApi.getAvailableTimeframes();
        setAvailableTimeframes(timeframes);
      } catch (error) {
        console.error('Failed to fetch available timeframes:', error);
      }
    };
    fetchAvailableTimeframes();
  }, []);

  // Check if a timeframe is available for the current symbol
  const isTimeframeAvailable = (timeframe: string) => {
    const symbolTimeframes = availableTimeframes[currentSymbol];
    return symbolTimeframes ? symbolTimeframes.includes(timeframe) : true;
  };

  // Auto-switch to available timeframe when symbol changes
  useEffect(() => {
    if (Object.keys(availableTimeframes).length > 0) {
      const symbolTimeframes = availableTimeframes[currentSymbol];
      if (symbolTimeframes && !symbolTimeframes.includes(currentTimeframe)) {
        setCurrentTimeframe(symbolTimeframes[0]);
      }
    }
  }, [currentSymbol, availableTimeframes]);

  // Reset source selection when symbol changes
  useEffect(() => {
    setSelectedSources([]);
    setSourceDataMap({});
  }, [currentSymbol]);

  // Fetch historical data for current symbol (default: all sources combined)
  const { data: historicalData, isLoading } = useQuery({
    queryKey: ['market-data', currentSymbol, currentTimeframe],
    queryFn: () => marketDataApi.getHistoricalData(currentSymbol, currentTimeframe, 500),
    refetchInterval: 10000,
    enabled: isTimeframeAvailable(currentTimeframe),
  });

  // Fetch data per selected source for comparison
  useEffect(() => {
    if (selectedSources.length === 0) {
      setSourceDataMap({});
      return;
    }

    const fetchSourceData = async () => {
      const newMap: Record<string, any[]> = {};
      for (const source of selectedSources) {
        try {
          const data = await marketDataApi.getHistoricalData(
            currentSymbol,
            currentTimeframe,
            500,
            source
          );
          newMap[source] = data;
        } catch (err) {
          console.error(`Failed to fetch data for source ${source}:`, err);
        }
      }
      setSourceDataMap(newMap);
    };

    fetchSourceData();
    const interval = setInterval(fetchSourceData, 15000);
    return () => clearInterval(interval);
  }, [selectedSources, currentSymbol, currentTimeframe]);

  // Fetch latest data for top symbols to populate live instruments
  useEffect(() => {
    if (allSymbols.length === 0) return;

    const fetchAllSymbols = async () => {
      // Only fetch live ticks for top symbols (by data points) to avoid overload
      const topSymbols = allSymbols
        .sort((a, b) => b.data_points_count - a.data_points_count)
        .slice(0, 12);

      for (const { symbol } of topSymbols) {
        try {
          const data = await marketDataApi.getHistoricalData(symbol, 'M1', 1);
          if (data && data.length > 0) {
            updateLatestTick(symbol, data[0]);
          }
        } catch (error) {
          // Try H1 fallback if M1 not available
          try {
            const data = await marketDataApi.getHistoricalData(symbol, 'H1', 1);
            if (data && data.length > 0) {
              updateLatestTick(symbol, data[0]);
            }
          } catch (_) {
            // Skip this symbol
          }
        }
      }
    };

    fetchAllSymbols();
    const interval = setInterval(fetchAllSymbols, 10000);
    return () => clearInterval(interval);
  }, [allSymbols, updateLatestTick]);

  // Update store when historical data changes
  useEffect(() => {
    if (historicalData && historicalData.length > 0) {
      setMarketData(currentSymbol, historicalData);
      const latestDataPoint = historicalData[historicalData.length - 1];
      updateLatestTick(currentSymbol, latestDataPoint);
    }
  }, [historicalData, currentSymbol, setMarketData, updateLatestTick]);

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

  // Filter symbols by search
  const filteredSymbols = allSymbols.filter((s) =>
    s.symbol.toLowerCase().includes(symbolSearch.toLowerCase())
  );

  // Toggle source selection (multi-select)
  const toggleSource = (source: string) => {
    setSelectedSources((prev) =>
      prev.includes(source)
        ? prev.filter((s) => s !== source)
        : [...prev, source]
    );
  };

  // Sort symbols: put the ones with most data first
  const sortedSymbols = [...filteredSymbols].sort(
    (a, b) => b.data_points_count - a.data_points_count
  );

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-dark-50 mb-2">Market Data</h1>
        <p className="text-dark-400">Real-time market data and price charts</p>
      </div>

      {/* Symbol & Timeframe Selector */}
      <div className="bg-dark-900 rounded-lg border border-dark-700 p-4">
        <div className="flex flex-col gap-4">
          {/* Symbol Selector with search */}
          <div>
            <label className="text-sm text-dark-500 mb-2 block">Symbol</label>
            <div className="flex flex-wrap items-center gap-2">
              {/* Search box */}
              <div className="relative">
                <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-500" />
                <input
                  type="text"
                  placeholder="Search..."
                  value={symbolSearch}
                  onChange={(e) => setSymbolSearch(e.target.value)}
                  className="pl-8 pr-3 py-2 bg-dark-800 border border-dark-600 rounded-lg text-sm text-dark-200 w-36 focus:outline-none focus:border-primary-500"
                />
              </div>
              {sortedSymbols.map(({ symbol }) => (
                <button
                  key={symbol}
                  onClick={() => setCurrentSymbol(symbol)}
                  className={cn(
                    'px-3 py-2 rounded-lg font-medium transition-colors text-sm',
                    currentSymbol === symbol
                      ? 'bg-primary-500 text-white'
                      : 'bg-dark-800 text-dark-300 hover:bg-dark-700'
                  )}
                >
                  {symbol}
                </button>
              ))}
              {sortedSymbols.length === 0 && (
                <span className="text-sm text-dark-500 italic">No symbols found</span>
              )}
            </div>
          </div>

          {/* Timeframe Selector */}
          <div className="flex flex-wrap items-center gap-4">
            <div>
              <label className="text-sm text-dark-500 mb-2 block">Timeframe</label>
              <div className="flex gap-2">
                {TIMEFRAMES.map((tf) => {
                  const available = isTimeframeAvailable(tf);
                  return (
                    <button
                      key={tf}
                      onClick={() => available && setCurrentTimeframe(tf)}
                      disabled={!available}
                      className={cn(
                        'px-4 py-2 rounded-lg font-medium transition-colors',
                        currentTimeframe === tf
                          ? 'bg-primary-500 text-white'
                          : available
                          ? 'bg-dark-800 text-dark-300 hover:bg-dark-700'
                          : 'bg-dark-900 text-dark-600 cursor-not-allowed opacity-50'
                      )}
                      title={!available ? 'No data available for this timeframe' : undefined}
                    >
                      {tf}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Source Selector (multi-select for comparison) */}
            {availableSources.length > 0 && (
              <div>
                <label className="text-sm text-dark-500 mb-2 block">
                  <Database className="inline w-3.5 h-3.5 mr-1" />
                  Data Source {selectedSources.length > 0 && `(${selectedSources.length} selected)`}
                </label>
                <div className="flex gap-2">
                  {availableSources.map(({ source, data_points }) => {
                    const isSelected = selectedSources.includes(source);
                    const color = getSourceColor(source);
                    return (
                      <button
                        key={source}
                        onClick={() => toggleSource(source)}
                        className={cn(
                          'px-3 py-2 rounded-lg font-medium transition-colors text-sm border',
                          isSelected
                            ? 'text-white border-transparent'
                            : 'bg-dark-800 text-dark-300 hover:bg-dark-700 border-dark-600'
                        )}
                        style={isSelected ? { backgroundColor: color, borderColor: color } : undefined}
                        title={`${data_points.toLocaleString()} data points`}
                      >
                        {source}
                        <span className="ml-1 text-xs opacity-70">
                          ({data_points > 1000 ? `${(data_points / 1000).toFixed(0)}k` : data_points})
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
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
                  +{(((Number(latestTick.close) - Number(latestTick.open)) / Number(latestTick.open)) * 100).toFixed(2)}%
                </span>
              </div>
              <div className="flex items-center gap-2 text-dark-400">
                <Clock className="w-4 h-4" />
                <span className="text-sm">{formatters.relativeTime(latestTick.time || latestTick.timestamp)}</span>
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
          <PriceChart
            data={chartData}
            height={500}
            sourceOverlays={selectedSources.length > 0 ? sourceDataMap : undefined}
            sourceColors={SOURCE_COLORS}
          />
        )}
      </div>

      {/* Real-Time Instruments Price List */}
      <div className="bg-dark-900 rounded-lg border border-dark-700">
        <div className="p-6 border-b border-dark-700">
          <h3 className="text-lg font-semibold text-dark-50">
            Live Instruments
          </h3>
          <p className="text-sm text-dark-400 mt-1">
            Real-time price updates for all monitored instruments ({allSymbols.length} symbols)
          </p>
        </div>
        <div className="divide-y divide-dark-700">
          {allSymbols
            .sort((a, b) => b.data_points_count - a.data_points_count)
            .slice(0, 12)
            .map(({ symbol }) => {
              const tick = latestTicks[symbol];
              if (!tick) {
                return (
                  <div
                    key={symbol}
                    className="p-4 hover:bg-dark-800/50 transition-colors cursor-pointer"
                    onClick={() => setCurrentSymbol(symbol)}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <h4 className="text-base font-semibold text-dark-50">{symbol}</h4>
                        <p className="text-xs text-dark-500 mt-1">Waiting for data...</p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-dark-500">--</p>
                      </div>
                    </div>
                  </div>
                );
              }

              const priceChange = Number(tick.close) - Number(tick.open);
              const priceChangePercent = (priceChange / Number(tick.open)) * 100;
              const isPositive = priceChange >= 0;

              return (
                <div
                  key={symbol}
                  className={cn(
                    'p-4 hover:bg-dark-800/50 transition-colors cursor-pointer',
                    currentSymbol === symbol && 'bg-primary-500/10 border-l-4 border-l-primary-500'
                  )}
                  onClick={() => setCurrentSymbol(symbol)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3">
                        <h4 className="text-base font-semibold text-dark-50">{symbol}</h4>
                        {currentSymbol === symbol && (
                          <span className="text-xs px-2 py-0.5 rounded bg-primary-500/20 text-primary-400 border border-primary-500/30">
                            Selected
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-dark-500 mt-1">
                        Updated {formatters.relativeTime(tick.time || tick.timestamp)}
                      </p>
                    </div>

                    <div className="flex items-center gap-6">
                      {/* OHLC Data */}
                      <div className="hidden md:grid grid-cols-4 gap-4 text-xs">
                        <div>
                          <p className="text-dark-500 mb-0.5">Open</p>
                          <p className="font-mono text-dark-200">{formatters.price(tick.open)}</p>
                        </div>
                        <div>
                          <p className="text-dark-500 mb-0.5">High</p>
                          <p className="font-mono text-success-500">{formatters.price(tick.high)}</p>
                        </div>
                        <div>
                          <p className="text-dark-500 mb-0.5">Low</p>
                          <p className="font-mono text-danger-500">{formatters.price(tick.low)}</p>
                        </div>
                        <div>
                          <p className="text-dark-500 mb-0.5">Volume</p>
                          <p className="font-mono text-dark-200">{formatters.number(tick.volume)}</p>
                        </div>
                      </div>

                      {/* Current Price & Change */}
                      <div className="text-right min-w-[140px]">
                        <p className="text-2xl font-bold text-dark-50 font-mono">
                          {formatters.price(tick.close)}
                        </p>
                        <div className={cn(
                          'flex items-center justify-end gap-1 mt-1',
                          isPositive ? 'text-success-500' : 'text-danger-500'
                        )}>
                          <TrendingUp
                            className={cn('w-4 h-4', !isPositive && 'rotate-180')}
                          />
                          <span className="text-sm font-semibold">
                            {isPositive ? '+' : ''}{priceChangePercent.toFixed(2)}%
                          </span>
                          <span className="text-xs text-dark-500">
                            ({isPositive ? '+' : ''}{formatters.price(priceChange)})
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
        </div>
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
                  chartData.reduce((sum, d) => sum + Number(d.volume), 0) / chartData.length
                )}
              </p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Period High</p>
              <p className="text-2xl font-bold text-success-500">
                {formatters.price(Math.max(...chartData.map((d) => Number(d.high))))}
              </p>
            </div>
            <div>
              <p className="text-sm text-dark-500 mb-1">Period Low</p>
              <p className="text-2xl font-bold text-danger-500">
                {formatters.price(Math.min(...chartData.map((d) => Number(d.low))))}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
