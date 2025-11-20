import React from 'react';
import { LucideIcon, TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '@/utils/cn';
import { useFormatters } from '@/hooks/useFormatters';

interface MetricCardProps {
  title: string;
  value: number | string;
  format?: 'currency' | 'percentage' | 'number' | 'none';
  icon?: LucideIcon;
  trend?: 'up' | 'down' | 'neutral';
  change?: number;
  changeFormat?: 'currency' | 'percentage';
  className?: string;
  loading?: boolean;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  format = 'number',
  icon: Icon,
  trend,
  change,
  changeFormat = 'percentage',
  className,
  loading = false,
}) => {
  const formatters = useFormatters();

  const formatValue = (val: number | string): string => {
    if (typeof val === 'string') return val;

    switch (format) {
      case 'currency':
        return formatters.currency(val);
      case 'percentage':
        return formatters.percentage(val);
      case 'number':
        return formatters.number(val);
      default:
        return String(val);
    }
  };

  const formatChange = (val: number): string => {
    if (changeFormat === 'currency') {
      return formatters.currency(Math.abs(val));
    }
    return formatters.percentage(Math.abs(val));
  };

  const trendColor = trend === 'up' ? 'text-success-500' : trend === 'down' ? 'text-danger-500' : 'text-dark-400';

  return (
    <div
      className={cn(
        'bg-dark-900 rounded-lg p-6 border border-dark-700',
        'hover:border-dark-600 transition-colors',
        className
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-sm font-medium text-dark-400 mb-1">{title}</p>
          {loading ? (
            <div className="h-8 w-24 bg-dark-800 animate-pulse rounded" />
          ) : (
            <p className="text-3xl font-bold text-dark-50">{formatValue(value)}</p>
          )}

          {change !== undefined && !loading && (
            <div className={cn('flex items-center gap-1 mt-2 text-sm', trendColor)}>
              {trend === 'up' && <TrendingUp className="w-4 h-4" />}
              {trend === 'down' && <TrendingDown className="w-4 h-4" />}
              <span>{formatChange(change)}</span>
            </div>
          )}
        </div>

        {Icon && (
          <div className="p-3 bg-primary-500/10 rounded-lg">
            <Icon className="w-6 h-6 text-primary-500" />
          </div>
        )}
      </div>
    </div>
  );
};
