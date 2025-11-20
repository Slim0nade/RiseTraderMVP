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
}

export const PriceChart: React.FC<PriceChartProps> = ({ data, height = 400 }) => {
  const chartData = useMemo(() => {
    return data.map((item) => ({
      timestamp: new Date(item.timestamp).getTime(),
      price: item.close,
      volume: item.volume,
    }));
  }, [data]);

  if (data.length === 0) {
    return (
      <div
        className="bg-dark-900 rounded-lg border border-dark-700 flex items-center justify-center"
        style={{ height }}
      >
        <p className="text-dark-500">No data available</p>
      </div>
    );
  }

  return (
    <div className="bg-dark-900 rounded-lg border border-dark-700 p-4">
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
            tickFormatter={(value) => value.toFixed(2)}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1e293b',
              border: '1px solid #334155',
              borderRadius: '8px',
              padding: '8px 12px',
            }}
            labelStyle={{ color: '#cbd5e1', marginBottom: 4 }}
            itemStyle={{ color: '#3b82f6' }}
            labelFormatter={(time) => format(new Date(time), 'MMM dd, yyyy HH:mm:ss')}
            formatter={(value: number) => [value.toFixed(5), 'Price']}
          />
          <Line
            type="monotone"
            dataKey="price"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: '#3b82f6' }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};
