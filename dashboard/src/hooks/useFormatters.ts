import { useMemo } from 'react';
import numeral from 'numeral';
import { format, formatDistanceToNow } from 'date-fns';

export const useFormatters = () => {
  return useMemo(
    () => ({
      // Format currency
      currency: (value: number | string, decimals = 2): string => {
        return numeral(value).format(`$0,0.${'0'.repeat(decimals)}`);
      },

      // Format percentage
      percentage: (value: number | string, decimals = 2): string => {
        return numeral(Number(value) / 100).format(`0,0.${'0'.repeat(decimals)}%`);
      },

      // Format number with commas
      number: (value: number | string, decimals = 0): string => {
        return numeral(value).format(`0,0.${'0'.repeat(decimals)}`);
      },

      // Format price (more decimals for precision)
      price: (value: number | string): string => {
        return numeral(value).format('0,0.00000');
      },

      // Format date
      date: (date: string | Date | null | undefined, formatStr = 'MMM dd, yyyy HH:mm:ss'): string => {
        if (!date) return 'N/A';
        try {
          return format(new Date(date), formatStr);
        } catch {
          return 'Invalid date';
        }
      },

      // Format relative time
      relativeTime: (date: string | Date | null | undefined): string => {
        if (!date) return 'N/A';
        try {
          return formatDistanceToNow(new Date(date), { addSuffix: true });
        } catch {
          return 'Invalid date';
        }
      },

      // Format duration in seconds
      duration: (seconds: number): string => {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hours > 0) {
          return `${hours}h ${minutes}m`;
        } else if (minutes > 0) {
          return `${minutes}m ${secs}s`;
        } else {
          return `${secs}s`;
        }
      },

      // Format P&L with color
      pnl: (value: number | string): { text: string; color: string } => {
        const numValue = Number(value);
        const text = numeral(numValue).format('$0,0.00');
        const color = numValue >= 0 ? 'text-success-500' : 'text-danger-500';
        return { text, color };
      },
    }),
    []
  );
};
