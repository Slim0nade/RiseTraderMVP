import React, { useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { MarketData } from '@/types';
import { format } from 'date-fns';

interface PriceChartProps {
  data: MarketData[];
  height?: number;
  sourceOverlays?: Record<string, any[]>;
  sourceColors?: Record<string, string>;
}

export const PriceChart: React.FC<PriceChartProps> = ({
  data,
  height = 400,
  sourceOverlays,
  sourceColors,
}) => {
  // Validate data is an array
  if (!Array.isArray(data) || data.length === 0) {
    return (
      <div
        className="bg-dark-900 rounded-lg border border-dark-700 flex items-center justify-center"
        style={{ height }}
      >
        <p className="text-dark-500">No data available</p>
      </div>
    );
  }

  const hasOverlays = sourceOverlays && Object.keys(sourceOverlays).length > 0;

  // Build merged chart data: base price + per-source price columns
  const chartData = useMemo(() => {
    if (!hasOverlays) {
      // Simple mode: just the main data
      return data.map((item) => ({
        timestamp: new Date(item.time || item.timestamp || '').getTime(),
        price: typeof item.close === 'string' ? parseFloat(item.close) : item.close,
        volume: typeof item.volume === 'string' ? parseFloat(item.volume) : item.volume,
      }));
    }

    // Multi-source mode: merge all source datasets by timestamp
    // Build a map of timestamp -> { price_SOURCE1, price_SOURCE2, ... }
    const timeMap = new Map<number, Record<string, number>>();

    // Add base data (all sources combined) as "Combined"
    for (const item of data) {
      const ts = new Date(item.time || item.timestamp || '').getTime();
      const close = typeof item.close === 'string' ? parseFloat(item.close) : item.close;
      if (!isNaN(ts) && !isNaN(close)) {
        const existing = timeMap.get(ts) || {};
        existing['Combined'] = close;
        existing['volume'] = typeof item.volume === 'string' ? parseFloat(item.volume) : item.volume;
        timeMap.set(ts, existing);
      }
    }

    // Add each source overlay
    for (const [source, sourceData] of Object.entries(sourceOverlays!)) {
      if (!Array.isArray(sourceData)) continue;
      for (const item of sourceData) {
        const ts = new Date(item.time || item.timestamp || '').getTime();
        const close = typeof item.close === 'string' ? parseFloat(item.close) : item.close;
        if (!isNaN(ts) && !isNaN(close)) {
          const existing = timeMap.get(ts) || {};
          existing[source] = close;
          timeMap.set(ts, existing);
        }
      }
    }

    // Convert map to sorted array
    return Array.from(timeMap.entries())
      .sort(([a], [b]) => a - b)
      .map(([ts, values]) => ({
        timestamp: ts,
        ...values,
      }));
  }, [data, sourceOverlays, hasOverlays]);

  if (chartData.length === 0) {
    return (
      <div
        className="bg-dark-900 rounded-lg border border-dark-700 flex items-center justify-center"
        style={{ height }}
      >
        <p className="text-dark-500">No data available</p>
      </div>
    );
  }

  // Determine which source lines to render
  const sourceKeys = hasOverlays ? Object.keys(sourceOverlays!) : [];
  const defaultColor = '#3b82f6';

  // Custom tooltip for multi-source
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload || payload.length === 0) return null;

    return (
      <div className="bg-dark-800 border border-dark-600 rounded-lg p-3 shadow-lg">
        <p className="text-xs text-dark-400 mb-2">
          {format(new Date(label), 'MMM dd, yyyy HH:mm:ss')}
        </p>
        {payload.map((entry: any, index: number) => (
          <div key={index} className="flex items-center justify-between gap-4 text-sm">
            <div className="flex items-center gap-2">
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: entry.color }}
              />
              <span className="text-dark-300">{entry.name}</span>
            </div>
            <span className="font-mono font-semibold text-dark-100">
              {typeof entry.value === 'number' ? entry.value.toFixed(5) : '--'}
            </span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="bg-dark-900 rounded-lg border border-dark-700 p-4">
      {/* Source Legend Header (only in multi-source mode) */}
      {hasOverlays && (
        <div className="flex items-center gap-3 mb-3 pb-3 border-b border-dark-800">
          <span className="text-xs text-dark-500 font-medium">Sources:</span>
          <div className="flex items-center gap-1.5">
            <span
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: '#94a3b8' }}
            />
            <span className="text-xs text-dark-400">Combined</span>
          </div>
          {sourceKeys.map((source) => (
            <div key={source} className="flex items-center gap-1.5">
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{
                  backgroundColor:
                    sourceColors?.[source] || defaultColor,
                }}
              />
              <span className="text-xs text-dark-400">{source}</span>
            </div>
          ))}
        </div>
      )}

      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={(time) => format(new Date(time), 'HH:mm')}
            stroke="#64748b"
            style={{ fontSize: 12 }}
          />
          <YAxis
            domain={['auto', 'auto']}
            stroke="#64748b"
            style={{ fontSize: 12 }}
            tickFormatter={(value) =>
              typeof value === 'number' ? value.toFixed(2) : value
            }
          />
          <Tooltip content={hasOverlays ? <CustomTooltip /> : undefined}
            {...(!hasOverlays && {
              contentStyle: {
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '8px',
                padding: '8px 12px',
              },
              labelStyle: { color: '#cbd5e1', marginBottom: 4 },
              itemStyle: { color: '#3b82f6' },
              labelFormatter: (time: number) =>
                format(new Date(time), 'MMM dd, yyyy HH:mm:ss'),
              formatter: (value: number) => [value.toFixed(5), 'Price'],
            })}
          />

          {/* Main price line */}
          {hasOverlays ? (
            // In multi-source mode, show "Combined" as a dashed subtle line
            <Line
              type="monotone"
              dataKey="Combined"
              name="Combined"
              stroke="#94a3b8"
              strokeWidth={1.5}
              strokeDasharray="4 2"
              dot={false}
              activeDot={{ r: 3 }}
              connectNulls
            />
          ) : (
            // Single mode: solid blue line
            <Line
              type="monotone"
              dataKey="price"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: '#3b82f6' }}
            />
          )}

          {/* Source overlay lines */}
          {sourceKeys.map((source) => (
            <Line
              key={source}
              type="monotone"
              dataKey={source}
              name={source}
              stroke={sourceColors?.[source] || defaultColor}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};
