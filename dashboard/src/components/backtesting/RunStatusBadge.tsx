import React from 'react';
import { CheckCircle, Clock, XCircle, Loader, Ban } from 'lucide-react';
import type { RunStatus } from '@/types';

interface RunStatusBadgeProps {
  status: RunStatus;
  size?: 'sm' | 'md' | 'lg';
}

export const RunStatusBadge: React.FC<RunStatusBadgeProps> = ({ status, size = 'md' }) => {
  const getStatusConfig = (status: RunStatus) => {
    switch (status) {
      case 'pending':
        return {
          icon: Clock,
          label: 'Pending',
          className: 'bg-warning-500/10 text-warning-500 border-warning-500/20',
        };
      case 'running':
        return {
          icon: Loader,
          label: 'Running',
          className: 'bg-primary-500/10 text-primary-500 border-primary-500/20',
          animate: true,
        };
      case 'completed':
        return {
          icon: CheckCircle,
          label: 'Completed',
          className: 'bg-success-500/10 text-success-500 border-success-500/20',
        };
      case 'failed':
        return {
          icon: XCircle,
          label: 'Failed',
          className: 'bg-danger-500/10 text-danger-500 border-danger-500/20',
        };
      case 'cancelled':
        return {
          icon: Ban,
          label: 'Cancelled',
          className: 'bg-dark-500/10 text-dark-500 border-dark-500/20',
        };
      default:
        return {
          icon: Clock,
          label: status,
          className: 'bg-dark-500/10 text-dark-500 border-dark-500/20',
        };
    }
  };

  const config = getStatusConfig(status);
  const Icon = config.icon;

  const sizeClasses = {
    sm: 'text-xs px-2 py-1',
    md: 'text-sm px-3 py-1.5',
    lg: 'text-base px-4 py-2',
  };

  const iconSizes = {
    sm: 'w-3 h-3',
    md: 'w-4 h-4',
    lg: 'w-5 h-5',
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium ${config.className} ${sizeClasses[size]}`}
    >
      <Icon className={`${iconSizes[size]} ${config.animate ? 'animate-spin' : ''}`} />
      {config.label}
    </span>
  );
};
