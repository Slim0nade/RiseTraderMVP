import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Brain, TrendingUp, Target } from 'lucide-react';
import { forecastsApi } from '@/api/endpoints';
import { useFormatters } from '@/hooks/useFormatters';
import { cn } from '@/utils/cn';
import type { Forecast } from '@/types';

const SYMBOLS = ['CrudeOIL', 'DXY', 'VIX'];

export const Forecasts: React.FC = () => {
  const formatters = useFormatters();
  const [selectedSymbol, setSelectedSymbol] = useState<string | undefined>(undefined);

  // Fetch latest forecasts
  const { data: forecasts, isLoading } = useQuery({
    queryKey: ['forecasts', selectedSymbol],
    queryFn: () => forecastsApi.getLatestForecasts(selectedSymbol),
    refetchInterval: 30000,
  });

  const groupedForecasts = forecasts?.reduce((acc, forecast) => {
    if (!acc[forecast.symbol]) {
      acc[forecast.symbol] = [];
    }
    acc[forecast.symbol].push(forecast);
    return acc;
  }, {} as Record<string, Forecast[]>);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-dark-50 mb-2">ML Forecasts</h1>
        <p className="text-dark-400">Machine learning powered price predictions</p>
      </div>

      {/* Symbol Filter */}
      <div className="bg-dark-900 rounded-lg border border-dark-700 p-4">
        <label className="text-sm text-dark-500 mb-2 block">Filter by Symbol</label>
        <div className="flex gap-2">
          <button
            onClick={() => setSelectedSymbol(undefined)}
            className={cn(
              'px-4 py-2 rounded-lg font-medium transition-colors',
              !selectedSymbol
                ? 'bg-primary-500 text-white'
                : 'bg-dark-800 text-dark-300 hover:bg-dark-700'
            )}
          >
            All
          </button>
          {SYMBOLS.map((symbol) => (
            <button
              key={symbol}
              onClick={() => setSelectedSymbol(symbol)}
              className={cn(
                'px-4 py-2 rounded-lg font-medium transition-colors',
                selectedSymbol === symbol
                  ? 'bg-primary-500 text-white'
                  : 'bg-dark-800 text-dark-300 hover:bg-dark-700'
              )}
            >
              {symbol}
            </button>
          ))}
        </div>
      </div>

      {/* Summary Stats */}
      {forecasts && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
            <div className="flex items-center gap-3">
              <div className="p-3 bg-primary-500/10 rounded-lg">
                <Brain className="w-6 h-6 text-primary-500" />
              </div>
              <div>
                <p className="text-sm text-dark-500">Total Forecasts</p>
                <p className="text-3xl font-bold text-dark-50">{forecasts.length}</p>
              </div>
            </div>
          </div>

          <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
            <div className="flex items-center gap-3">
              <div className="p-3 bg-success-500/10 rounded-lg">
                <TrendingUp className="w-6 h-6 text-success-500" />
              </div>
              <div>
                <p className="text-sm text-dark-500">Avg Confidence</p>
                <p className="text-3xl font-bold text-dark-50">
                  {(
                    (forecasts.reduce((sum, f) => sum + f.confidence, 0) / forecasts.length) *
                    100
                  ).toFixed(1)}
                  %
                </p>
              </div>
            </div>
          </div>

          <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
            <div className="flex items-center gap-3">
              <div className="p-3 bg-primary-500/10 rounded-lg">
                <Target className="w-6 h-6 text-primary-500" />
              </div>
              <div>
                <p className="text-sm text-dark-500">Symbols</p>
                <p className="text-3xl font-bold text-dark-50">
                  {Object.keys(groupedForecasts || {}).length}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Forecasts Grid */}
      {isLoading ? (
        <div className="bg-dark-900 rounded-lg border border-dark-700 p-8 text-center">
          <p className="text-dark-400">Loading forecasts...</p>
        </div>
      ) : groupedForecasts && Object.keys(groupedForecasts).length > 0 ? (
        <div className="space-y-6">
          {Object.entries(groupedForecasts).map(([symbol, symbolForecasts]) => (
            <div key={symbol}>
              <h2 className="text-xl font-semibold text-dark-50 mb-4">{symbol}</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {symbolForecasts.map((forecast) => (
                  <div
                    key={forecast.id}
                    className="bg-dark-900 rounded-lg border border-dark-700 p-6 hover:border-dark-600 transition-colors"
                  >
                    <div className="flex items-start justify-between mb-4">
                      <div>
                        <p className="text-sm text-dark-500 mb-1">Horizon</p>
                        <p className="text-2xl font-bold text-primary-500">
                          {forecast.forecast_horizon}m
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-dark-500 mb-1">Model</p>
                        <p className="text-sm font-medium text-dark-300">{forecast.model_name}</p>
                      </div>
                    </div>

                    <div className="mb-4">
                      <p className="text-sm text-dark-500 mb-1">Predicted Price</p>
                      <p className="text-3xl font-bold text-dark-50">
                        {formatters.price(forecast.predicted_price)}
                      </p>
                    </div>

                    <div className="flex items-center justify-between pt-4 border-t border-dark-800">
                      <div>
                        <p className="text-xs text-dark-500">Confidence</p>
                        <div className="flex items-center gap-2 mt-1">
                          <div className="w-20 h-2 bg-dark-800 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-gradient-to-r from-danger-500 via-warning-500 to-success-500"
                              style={{ width: `${forecast.confidence * 100}%` }}
                            />
                          </div>
                          <span className="text-sm font-bold text-dark-200">
                            {(forecast.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-xs text-dark-500">Generated</p>
                        <p className="text-xs text-dark-400 mt-1">
                          {formatters.relativeTime(forecast.timestamp)}
                        </p>
                      </div>
                    </div>

                    {/* Features */}
                    {forecast.features && Object.keys(forecast.features).length > 0 && (
                      <details className="mt-4">
                        <summary className="text-xs text-primary-500 cursor-pointer hover:text-primary-400">
                          View features
                        </summary>
                        <div className="mt-2 p-2 bg-dark-950 rounded">
                          {Object.entries(forecast.features).map(([key, value]) => (
                            <div
                              key={key}
                              className="flex items-center justify-between py-1 text-xs"
                            >
                              <span className="text-dark-500">{key}</span>
                              <span className="text-dark-300 font-mono">
                                {typeof value === 'number' ? value.toFixed(4) : value}
                              </span>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-dark-900 rounded-lg border border-dark-700 p-8 text-center text-dark-500">
          No forecasts available
        </div>
      )}
    </div>
  );
};
