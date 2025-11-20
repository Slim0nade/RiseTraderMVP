import { useMemo } from 'react';
import numeral from 'numeral';
import { format, formatDistanceToNow } from 'date-fns';

export const useFormatters = () => {
  return useMemo(
    () => ({
      // Format currency
      currency: (value: number, decimals = 2): string => {
        return numeral(value).format(`$0,0.${'0'.repeat(decimals)}`);
      },

      // Format percentage
      percentage: (value: number, decimals = 2): string => {
        return numeral(value / 100).format(`0,0.${'0'.repeat(decimals)}%`);
      },

      // Format number with commas
      number: (value: number, decimals = 0): string => {
        return numeral(value).format(`0,0.${'0'.repeat(decimals)}`);
      },

      // Format price (more decimals for precision)
      price: (value: number): string => {
        return numeral(value).format('0,0.00000');
      },

      // Format date
      date: (date: string | Date, formatStr = 'MMM dd, yyyy HH:mm:ss'): string => {
        return format(new Date(date), formatStr);
      },

      // Format relative time
      relativeTime: (date: string | Date): string => {
        return formatDistanceToNow(new Date(date), { addSuffix: true });
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
      pnl: (value: number): { text: string; color: string } => {
        const text = numeral(value).format('$0,0.00');
        const color = value >= 0 ? 'text-success-500' : 'text-danger-500';
        return { text, color };
      },
    }),
    []
  );
};
