import React from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { format } from 'date-fns';

interface EquityCurveData {
  timestamp: string;
  equity: number;
  drawdown: number;
}

interface EquityCurveChartProps {
  data: EquityCurveData[];
  height?: number;
}

export const EquityCurveChart: React.FC<EquityCurveChartProps> = ({ data, height = 400 }) => {
  // Validate data is an array
  if (!Array.isArray(data) || data.length === 0) {
    return (
      <div
        className="bg-dark-900 rounded-lg border border-dark-700 flex items-center justify-center"
        style={{ height }}
      >
        <p className="text-dark-500">No equity data available</p>
      </div>
    );
  }

  // FIXED: Deduplicate data by timestamp (keep last value for each timestamp)
  const deduplicatedData = data.reduce((acc: EquityCurveData[], point) => {
    const existingIndex = acc.findIndex(p => p.timestamp === point.timestamp);
    if (existingIndex >= 0) {
      acc[existingIndex] = point; // Replace with newer value
    } else {
      acc.push(point);
    }
    return acc;
  }, []);

  return (
    <div className="bg-dark-900 rounded-lg border border-dark-700 p-4">
      <h3 className="text-lg font-semibold text-dark-50 mb-4">Equity Curve</h3>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={deduplicatedData}>
          <defs>
            <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={(time) => format(new Date(time), 'MMM dd')}
            stroke="#64748b"
            style={{ fontSize: 12 }}
          />
          <YAxis
            stroke="#64748b"
            style={{ fontSize: 12 }}
            tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1e293b',
              border: '1px solid #334155',
              borderRadius: '8px',
              padding: '8px 12px',
            }}
            labelStyle={{ color: '#cbd5e1', marginBottom: 4 }}
            labelFormatter={(time) => format(new Date(time), 'MMM dd, yyyy')}
            formatter={(value: number, name: string) => {
              if (name === 'equity') {
                return [`$${value.toFixed(2)}`, 'Equity'];
              }
              return [`${value.toFixed(2)}%`, 'Drawdown'];
            }}
          />
          <Area
            type="monotone"
            dataKey="equity"
            stroke="#22c55e"
            strokeWidth={2}
            fillOpacity={1}
            fill="url(#equityGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};
