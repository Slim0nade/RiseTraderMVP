import React, { useEffect, useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Calendar, AlertCircle, CheckCircle, Info, TrendingUp, BarChart3 } from 'lucide-react';
import { apiClient } from '@/api/client';
import {
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';

interface DataAvailability {
  symbol: string;
  timeframe: string;
  first_date: string;
  last_date: string;
  recommended_start: string;
  recommended_end: string;
  total_candles: number;
  trading_days: string[];
  has_data: boolean;
  summary: {
    total_days_with_data: number;
    avg_candles_per_day: number;
    data_quality: 'good' | 'limited';
  };
}

interface CandleData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface CandlePreview {
  symbol: string;
  timeframe: string;
  total_candles: number;
  sampled_candles: number;
  candles: CandleData[];
}

interface IntelligentDatePickerProps {
  symbol: string;
  timeframe: string;
  startDate: string;
  endDate: string;
  onStartDateChange: (date: string) => void;
  onEndDateChange: (date: string) => void;
  onValidationChange?: (isValid: boolean) => void;
}

export const IntelligentDatePicker: React.FC<IntelligentDatePickerProps> = ({
  symbol,
  timeframe,
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
  onValidationChange,
}) => {
  const [validationMessage, setValidationMessage] = useState<string | null>(null);
  const [validationLevel, setValidationLevel] = useState<'success' | 'warning' | 'error' | null>(null);

  // Fetch data availability
  const { data: availability, isLoading, error } = useQuery<DataAvailability>({
    queryKey: ['data-availability', symbol, timeframe],
    queryFn: async () => {
      const response = await apiClient.get(
        `/api/market-data/availability/${symbol}?timeframe=${timeframe}`
      );
      return response;
    },
    enabled: !!symbol && !!timeframe,
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
  });

  // Validate selected dates against available data (MUST be before candle preview query)
  const validation = useMemo(() => {
    if (!availability || !startDate || !endDate) {
      return { isValid: false, message: null, level: null };
    }

    const start = new Date(startDate);
    const end = new Date(endDate);
    const firstData = new Date(availability.first_date);
    const lastData = new Date(availability.last_date);

    // Check if dates are in valid range
    if (start < firstData) {
      return {
        isValid: false,
        message: `Start date is before first available data (${firstData.toLocaleDateString()})`,
        level: 'error' as const,
      };
    }

    if (end > lastData) {
      return {
        isValid: false,
        message: `End date is after last available data (${lastData.toLocaleDateString()})`,
        level: 'error' as const,
      };
    }

    if (start >= end) {
      return {
        isValid: false,
        message: 'End date must be after start date',
        level: 'error' as const,
      };
    }

    // Check if period is too short
    const daysDiff = Math.floor((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24));
    if (daysDiff < 7) {
      return {
        isValid: true,
        message: `Short backtest period (${daysDiff} days). Consider at least 30 days for meaningful results.`,
        level: 'warning' as const,
      };
    }

    // Check if period is very long
    if (daysDiff > 730) {  // 2 years
      return {
        isValid: true,
        message: `Long backtest period (${daysDiff} days). May take significant time to process.`,
        level: 'warning' as const,
      };
    }

    // Optimal range
    return {
      isValid: true,
      message: `Good backtest period: ${daysDiff} days with ${Math.floor(
        daysDiff * availability.summary.avg_candles_per_day
      ).toLocaleString()} expected candles`,
      level: 'success' as const,
    };
  }, [availability, startDate, endDate]);

  // Fetch candle preview for selected date range (AFTER validation is defined)
  const { data: candlePreview, isLoading: candlesLoading } = useQuery<CandlePreview>({
    queryKey: ['candle-preview', symbol, timeframe, startDate, endDate],
    queryFn: async () => {
      const response = await apiClient.get(
        `/api/market-data/preview/${symbol}?start_date=${startDate}&end_date=${endDate}&timeframe=${timeframe}&max_candles=100`
      );
      return response;
    },
    enabled: !!symbol && !!timeframe && !!startDate && !!endDate && validation.isValid,
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
  });

  // Update parent component with validation status
  useEffect(() => {
    if (onValidationChange) {
      onValidationChange(validation.isValid);
    }
    setValidationMessage(validation.message);
    setValidationLevel(validation.level);
  }, [validation, onValidationChange]);

  // Auto-fill with recommended dates
  const useRecommendedDates = () => {
    if (availability) {
      onStartDateChange(availability.recommended_start.split('T')[0]);
      onEndDateChange(availability.recommended_end.split('T')[0]);
    }
  };

  // Format date for input (YYYY-MM-DD)
  const formatDateForInput = (isoString: string) => {
    return isoString.split('T')[0];
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-sm text-dark-400">
          <div className="w-4 h-4 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
          <span>Checking data availability...</span>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">
              Start Date
            </label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => onStartDateChange(e.target.value)}
              className="w-full bg-dark-800 border border-dark-600 rounded-lg px-4 py-2.5 text-dark-50 focus:outline-none focus:border-primary-500 transition-colors"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">
              End Date
            </label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => onEndDateChange(e.target.value)}
              className="w-full bg-dark-800 border border-dark-600 rounded-lg px-4 py-2.5 text-dark-50 focus:outline-none focus:border-primary-500 transition-colors"
            />
          </div>
        </div>
      </div>
    );
  }

  if (error || !availability) {
    return (
      <div className="space-y-4">
        <div className="bg-warning-500/10 border border-warning-500/30 rounded-lg p-4">
          <div className="flex items-center gap-2 text-sm text-warning-400">
            <AlertCircle className="w-4 h-4" />
            <span>Could not verify data availability. Dates may not be validated.</span>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">
              Start Date
            </label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => onStartDateChange(e.target.value)}
              className="w-full bg-dark-800 border border-dark-600 rounded-lg px-4 py-2.5 text-dark-50 focus:outline-none focus:border-primary-500 transition-colors"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">
              End Date
            </label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => onEndDateChange(e.target.value)}
              className="w-full bg-dark-800 border border-dark-600 rounded-lg px-4 py-2.5 text-dark-50 focus:outline-none focus:border-primary-500 transition-colors"
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Data Availability Info */}
      <div className="bg-dark-800/50 border border-dark-700 rounded-lg p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-primary-500" />
            <h4 className="text-sm font-medium text-dark-200">Data Availability</h4>
          </div>
          <button
            onClick={useRecommendedDates}
            className="text-xs text-primary-500 hover:text-primary-400 transition-colors flex items-center gap-1"
          >
            <TrendingUp className="w-3 h-3" />
            Use Recommended
          </button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <div>
            <p className="text-dark-500 mb-1">First Data</p>
            <p className="text-dark-200 font-medium">
              {new Date(availability.first_date).toLocaleDateString()}
            </p>
          </div>
          <div>
            <p className="text-dark-500 mb-1">Last Data</p>
            <p className="text-dark-200 font-medium">
              {new Date(availability.last_date).toLocaleDateString()}
            </p>
          </div>
          <div>
            <p className="text-dark-500 mb-1">Total Candles</p>
            <p className="text-dark-200 font-medium">
              {availability.total_candles.toLocaleString()}
            </p>
          </div>
          <div>
            <p className="text-dark-500 mb-1">Quality</p>
            <div className="flex items-center gap-1">
              {availability.summary.data_quality === 'good' ? (
                <CheckCircle className="w-3 h-3 text-success-500" />
              ) : (
                <AlertCircle className="w-3 h-3 text-warning-500" />
              )}
              <p className={`font-medium capitalize ${
                availability.summary.data_quality === 'good' ? 'text-success-500' : 'text-warning-500'
              }`}>
                {availability.summary.data_quality}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Date Inputs */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-dark-300 mb-2">
            Start Date
          </label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => onStartDateChange(e.target.value)}
            min={formatDateForInput(availability.first_date)}
            max={formatDateForInput(availability.last_date)}
            className={`w-full bg-dark-800 border rounded-lg px-4 py-2.5 text-dark-50 focus:outline-none transition-colors ${
              validationLevel === 'error'
                ? 'border-danger-500 focus:border-danger-400'
                : validationLevel === 'success'
                ? 'border-success-500/50 focus:border-success-500'
                : 'border-dark-600 focus:border-primary-500'
            }`}
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-dark-300 mb-2">
            End Date
          </label>
          <input
            type="date"
            value={endDate}
            onChange={(e) => onEndDateChange(e.target.value)}
            min={formatDateForInput(availability.first_date)}
            max={formatDateForInput(availability.last_date)}
            className={`w-full bg-dark-800 border rounded-lg px-4 py-2.5 text-dark-50 focus:outline-none transition-colors ${
              validationLevel === 'error'
                ? 'border-danger-500 focus:border-danger-400'
                : validationLevel === 'success'
                ? 'border-success-500/50 focus:border-success-500'
                : 'border-dark-600 focus:border-primary-500'
            }`}
          />
        </div>
      </div>

      {/* Validation Message */}
      {validationMessage && (
        <div className={`border rounded-lg p-3 ${
          validationLevel === 'error'
            ? 'bg-danger-500/10 border-danger-500/30'
            : validationLevel === 'warning'
            ? 'bg-warning-500/10 border-warning-500/30'
            : 'bg-success-500/10 border-success-500/30'
        }`}>
          <div className="flex items-start gap-2">
            {validationLevel === 'error' ? (
              <AlertCircle className="w-4 h-4 text-danger-400 flex-shrink-0 mt-0.5" />
            ) : validationLevel === 'warning' ? (
              <Info className="w-4 h-4 text-warning-400 flex-shrink-0 mt-0.5" />
            ) : (
              <CheckCircle className="w-4 h-4 text-success-400 flex-shrink-0 mt-0.5" />
            )}
            <p className={`text-sm ${
              validationLevel === 'error'
                ? 'text-danger-300'
                : validationLevel === 'warning'
                ? 'text-warning-300'
                : 'text-success-300'
            }`}>
              {validationMessage}
            </p>
          </div>
        </div>
      )}

      {/* Candle Chart Preview */}
      {validation.isValid && candlePreview && candlePreview.candles.length > 0 && (
        <div className="bg-dark-800/50 border border-dark-700 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-primary-500" />
              <h4 className="text-sm font-medium text-dark-200">Price Preview</h4>
            </div>
            <p className="text-xs text-dark-500">
              Showing {candlePreview.sampled_candles} of {candlePreview.total_candles.toLocaleString()} candles
            </p>
          </div>

          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={candlePreview.candles}>
                <XAxis
                  dataKey="time"
                  tick={{ fill: '#6B7280', fontSize: 10 }}
                  tickFormatter={(time) => new Date(time).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  stroke="#374151"
                />
                <YAxis
                  domain={['auto', 'auto']}
                  tick={{ fill: '#6B7280', fontSize: 10 }}
                  tickFormatter={(value) => typeof value === 'number' ? value.toFixed(2) : String(value)}
                  stroke="#374151"
                  width={60}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1F2937',
                    border: '1px solid #374151',
                    borderRadius: '8px',
                    fontSize: '12px',
                  }}
                  labelStyle={{ color: '#9CA3AF' }}
                  itemStyle={{ color: '#E5E7EB' }}
                  formatter={(value: any) => {
                    if (Array.isArray(value)) {
                      return `${value[0]?.toFixed(2)} - ${value[1]?.toFixed(2)}`;
                    }
                    return typeof value === 'number' ? value.toFixed(2) : String(value);
                  }}
                  labelFormatter={(time) => new Date(time).toLocaleString()}
                />
                <Bar
                  dataKey={(candle: CandleData) => [candle.low, candle.high]}
                  fill="#6366F1"
                  radius={[4, 4, 4, 4]}
                >
                  {candlePreview.candles.map((candle, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={candle.close >= candle.open ? '#10B981' : '#EF4444'}
                      opacity={0.8}
                    />
                  ))}
                </Bar>
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <p className="text-xs text-dark-500 mt-2 text-center">
            Green = Bullish candle, Red = Bearish candle
          </p>
        </div>
      )}

      {candlesLoading && validation.isValid && (
        <div className="bg-dark-800/50 border border-dark-700 rounded-lg p-4">
          <div className="flex items-center justify-center gap-2 text-sm text-dark-400">
            <div className="w-4 h-4 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
            <span>Loading price preview...</span>
          </div>
        </div>
      )}
    </div>
  );
};
