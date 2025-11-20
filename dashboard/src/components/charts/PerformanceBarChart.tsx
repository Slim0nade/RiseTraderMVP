import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from 'recharts';

interface PerformanceData {
  date: string;
  pnl: number;
}

interface PerformanceBarChartProps {
  data: PerformanceData[];
  height?: number;
}

export const PerformanceBarChart: React.FC<PerformanceBarChartProps> = ({
  data,
  height = 300,
}) => {
  if (data.length === 0) {
    return (
      <div
        className="bg-dark-900 rounded-lg border border-dark-700 flex items-center justify-center"
        style={{ height }}
      >
        <p className="text-dark-500">No performance data available</p>
      </div>
    );
  }

  return (
    <div className="bg-dark-900 rounded-lg border border-dark-700 p-4">
      <h3 className="text-lg font-semibold text-dark-50 mb-4">Daily P&L</h3>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="date"
            stroke="#64748b"
            style={{ fontSize: 12 }}
          />
          <YAxis
            stroke="#64748b"
            style={{ fontSize: 12 }}
            tickFormatter={(value) => `$${value}`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1e293b',
              border: '1px solid #334155',
              borderRadius: '8px',
              padding: '8px 12px',
            }}
            labelStyle={{ color: '#cbd5e1', marginBottom: 4 }}
            formatter={(value: number) => [`$${value.toFixed(2)}`, 'P&L']}
            cursor={{ fill: 'rgba(148, 163, 184, 0.1)' }}
          />
          <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.pnl >= 0 ? '#22c55e' : '#ef4444'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};
