import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi } from 'lightweight-charts';

interface EquityCurvePoint {
  time: number;
  value: number;
}

interface EquityCurveChartProps {
  data: EquityCurvePoint[];
  height?: number;
  initialCapital: number;
  finalCapital?: number; // Optional authoritative final capital from run data
}

export const EquityCurveChart: React.FC<EquityCurveChartProps> = ({
  data,
  height = 400,
  initialCapital,
  finalCapital,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null);

  // Ensure initialCapital is always a number
  const initialCapitalNum = typeof initialCapital === 'string'
    ? parseFloat(initialCapital)
    : initialCapital;

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // FIXED: Deduplicate data by timestamp (keep last value for each timestamp)
    const deduplicatedData = data.reduce((acc: EquityCurvePoint[], point) => {
      const existingIndex = acc.findIndex(p => p.time === point.time);
      if (existingIndex >= 0) {
        acc[existingIndex] = point; // Replace with newer value
      } else {
        acc.push(point);
      }
      return acc;
    }, []);

    // Sort by time to ensure ascending order
    let sortedData = [...deduplicatedData].sort((a, b) => a.time - b.time);

    // PERFORMANCE FIX: Downsample if we have too many data points
    // Charts can't efficiently render more than ~2000 points
    const MAX_POINTS = 2000;
    if (sortedData.length > MAX_POINTS) {
      const step = Math.ceil(sortedData.length / MAX_POINTS);
      const downsampled: EquityCurvePoint[] = [];

      // Always include first point
      downsampled.push(sortedData[0]);

      // Sample every Nth point
      for (let i = step; i < sortedData.length - 1; i += step) {
        downsampled.push(sortedData[i]);
      }

      // Always include last point (most recent equity)
      if (sortedData.length > 1) {
        downsampled.push(sortedData[sortedData.length - 1]);
      }

      sortedData = downsampled;
    }

    // Create chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0f1419' },
        textColor: '#9ca3af',
      },
      grid: {
        vertLines: { color: '#1f2937' },
        horzLines: { color: '#1f2937' },
      },
      width: chartContainerRef.current.clientWidth,
      height,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: '#374151',
      },
      rightPriceScale: {
        borderColor: '#374151',
      },
    });

    chartRef.current = chart;

    // Create area series
    const areaSeries = chart.addAreaSeries({
      lineColor: '#3b82f6',
      topColor: 'rgba(59, 130, 246, 0.4)',
      bottomColor: 'rgba(59, 130, 246, 0.0)',
      lineWidth: 2,
    });

    seriesRef.current = areaSeries;

    // Set data (use sorted, deduplicated data)
    if (sortedData.length > 0) {
      areaSeries.setData(sortedData as any);
    }

    // Add baseline at initial capital
    const baselineSeries = chart.addLineSeries({
      color: '#6b7280',
      lineWidth: 1,
      lineStyle: 2, // Dashed
      priceLineVisible: false,
    });

    if (sortedData.length > 0) {
      const minTime = sortedData[0].time;
      const maxTime = sortedData[sortedData.length - 1].time;

      // Only add baseline if we have more than one unique timestamp
      if (minTime !== maxTime) {
        baselineSeries.setData([
          { time: minTime as any, value: initialCapitalNum },
          { time: maxTime as any, value: initialCapitalNum },
        ]);
      } else if (sortedData.length === 1) {
        // Single point - no baseline needed
        baselineSeries.setData([]);
      }
    }

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartRef.current) {
        chartRef.current.remove();
      }
    };
  }, [height, initialCapitalNum]);

  useEffect(() => {
    if (seriesRef.current && data.length > 0) {
      // Deduplicate timestamps by keeping the last value for each unique timestamp
      // TradingView Lightweight Charts requires strictly ascending timestamps
      const deduplicatedData = data.reduce((acc, point) => {
        const existingIndex = acc.findIndex((p) => p.time === point.time);
        if (existingIndex >= 0) {
          // Replace with newer value at same timestamp
          acc[existingIndex] = point;
        } else {
          acc.push(point);
        }
        return acc;
      }, [] as EquityCurvePoint[]);

      // Sort by time ascending (just in case)
      let sortedData = deduplicatedData.sort((a, b) => a.time - b.time);

      // PERFORMANCE FIX: Downsample if we have too many data points
      const MAX_POINTS = 2000;
      if (sortedData.length > MAX_POINTS) {
        const step = Math.ceil(sortedData.length / MAX_POINTS);
        const downsampled: EquityCurvePoint[] = [];

        // Always include first point
        downsampled.push(sortedData[0]);

        // Sample every Nth point
        for (let i = step; i < sortedData.length - 1; i += step) {
          downsampled.push(sortedData[i]);
        }

        // Always include last point (most recent equity)
        if (sortedData.length > 1) {
          downsampled.push(sortedData[sortedData.length - 1]);
        }

        sortedData = downsampled;
      }

      seriesRef.current.setData(
        sortedData.map((point) => ({
          time: point.time as any,
          value: point.value,
        }))
      );

      // Fit content
      if (chartRef.current) {
        chartRef.current.timeScale().fitContent();
      }
    }
  }, [data]);

  // Use finalCapital if provided (authoritative), otherwise derive from data
  const sortedData = [...data].sort((a, b) => a.time - b.time);
  const dataEquity = sortedData.length > 0 ? sortedData[sortedData.length - 1].value : initialCapitalNum;
  
  // Prefer finalCapital prop when available (accurate even with limited snapshot data)
  const finalCapitalNum = finalCapital !== undefined 
    ? (typeof finalCapital === 'string' ? parseFloat(finalCapital) : finalCapital)
    : null;
  const currentEquity = finalCapitalNum ?? dataEquity;
  
  const returnPct = ((currentEquity - initialCapitalNum) / initialCapitalNum) * 100;
  const returnAmount = currentEquity - initialCapitalNum;

  return (
    <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-dark-50">Equity Curve</h3>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-xs text-dark-500">Current Equity</p>
            <p className="text-sm font-bold text-dark-50">
              ${currentEquity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-dark-500">Return</p>
            <p className={`text-sm font-bold ${returnPct >= 0 ? 'text-success-500' : 'text-danger-500'}`}>
              {returnPct >= 0 ? '+' : ''}{returnPct.toFixed(2)}%
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-dark-500">P&L</p>
            <p className={`text-sm font-bold ${returnAmount >= 0 ? 'text-success-500' : 'text-danger-500'}`}>
              {returnAmount >= 0 ? '+' : ''}${returnAmount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          </div>
        </div>
      </div>

      {data.length === 0 ? (
        <div className="flex items-center justify-center h-[400px] bg-dark-800 rounded-lg border border-dark-700">
          <p className="text-dark-500">No equity data available</p>
        </div>
      ) : (
        <div ref={chartContainerRef} />
      )}

      <div className="flex items-center gap-4 mt-4 text-xs text-dark-500">
        <div className="flex items-center gap-2">
          <div className="w-3 h-0.5 bg-primary-500"></div>
          <span>Equity</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-0.5 bg-dark-600 border-t border-dashed border-dark-400"></div>
          <span>Initial Capital</span>
        </div>
      </div>
    </div>
  );
};
