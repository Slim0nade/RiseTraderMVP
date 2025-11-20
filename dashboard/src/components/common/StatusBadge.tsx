import React from 'react';
import { cn } from '@/utils/cn';

interface StatusBadgeProps {
  status: 'active' | 'idle' | 'error' | 'stopped' | 'initializing' | 'success' | 'warning';
  text?: string;
  showDot?: boolean;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  text,
  showDot = true,
  className,
}) => {
  const statusConfig = {
    active: {
      bg: 'bg-success-500/10',
      text: 'text-success-500',
      dot: 'bg-success-500',
      label: 'Active',
    },
    success: {
      bg: 'bg-success-500/10',
      text: 'text-success-500',
      dot: 'bg-success-500',
      label: 'Success',
    },
    idle: {
      bg: 'bg-dark-700',
      text: 'text-dark-300',
      dot: 'bg-dark-400',
      label: 'Idle',
    },
    error: {
      bg: 'bg-danger-500/10',
      text: 'text-danger-500',
      dot: 'bg-danger-500',
      label: 'Error',
    },
    stopped: {
      bg: 'bg-dark-700',
      text: 'text-dark-400',
      dot: 'bg-dark-500',
      label: 'Stopped',
    },
    initializing: {
      bg: 'bg-warning-500/10',
      text: 'text-warning-500',
      dot: 'bg-warning-500',
      label: 'Starting',
    },
    warning: {
      bg: 'bg-warning-500/10',
      text: 'text-warning-500',
      dot: 'bg-warning-500',
      label: 'Warning',
    },
  };

  const config = statusConfig[status];
  const displayText = text || config.label;

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium',
        config.bg,
        config.text,
        className
      )}
    >
      {showDot && (
        <span
          className={cn('w-1.5 h-1.5 rounded-full', config.dot, {
            'animate-pulse': status === 'active' || status === 'initializing',
          })}
        />
      )}
      {displayText}
    </span>
  );
};
