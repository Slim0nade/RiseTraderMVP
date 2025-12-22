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
}

export const EquityCurveChart: React.FC<EquityCurveChartProps> = ({
  data,
  height = 400,
  initialCapital,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

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

    // Add baseline at initial capital
    const baselineSeries = chart.addLineSeries({
      color: '#6b7280',
      lineWidth: 1,
      lineStyle: 2, // Dashed
      priceLineVisible: false,
    });

    if (data.length > 0) {
      const minTime = data[0].time;
      const maxTime = data[data.length - 1].time;
      baselineSeries.setData([
        { time: minTime as any, value: initialCapital },
        { time: maxTime as any, value: initialCapital },
      ]);
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
  }, [height, initialCapital]);

  useEffect(() => {
    if (seriesRef.current && data.length > 0) {
      seriesRef.current.setData(
        data.map((point) => ({
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

  const currentEquity = data.length > 0 ? data[data.length - 1].value : initialCapital;
  const returnPct = ((currentEquity - initialCapital) / initialCapital) * 100;
  const returnAmount = currentEquity - initialCapital;

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
