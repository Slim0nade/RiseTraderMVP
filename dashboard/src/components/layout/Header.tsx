import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Bell, Wifi, WifiOff, AlertCircle } from 'lucide-react';
import { healthApi } from '@/api/endpoints';
import { useWebSocket } from '@/hooks/useWebSocket';
import { StatusBadge } from '@/components/common/StatusBadge';
import { cn } from '@/utils/cn';

export const Header: React.FC = () => {
  const { isConnected } = useWebSocket();

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: healthApi.getHealth,
    refetchInterval: 10000,
  });

  return (
    <header className="h-16 bg-dark-900 border-b border-dark-700 flex items-center justify-between px-6">
      {/* Left side - Status indicators */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          {isConnected ? (
            <Wifi className="w-4 h-4 text-success-500" />
          ) : (
            <WifiOff className="w-4 h-4 text-danger-500" />
          )}
          <span className="text-sm text-dark-400">
            {isConnected ? 'Live' : 'Disconnected'}
          </span>
        </div>

        {health && (
          <StatusBadge
            status={health.status === 'healthy' ? 'active' : 'error'}
            text={health.status === 'healthy' ? 'API Online' : 'API Error'}
          />
        )}
      </div>

      {/* Right side - Actions */}
      <div className="flex items-center gap-3">
        {/* Notifications */}
        <button className="p-2 hover:bg-dark-800 rounded-lg transition-colors relative">
          <Bell className="w-5 h-5 text-dark-400" />
          <span className="absolute top-1 right-1 w-2 h-2 bg-danger-500 rounded-full" />
        </button>

        {/* User info */}
        <div className="flex items-center gap-3 pl-3 border-l border-dark-700">
          <div className="text-right">
            <p className="text-sm font-medium text-dark-200">Admin User</p>
            <p className="text-xs text-dark-500">Administrator</p>
          </div>
          <div className="w-9 h-9 bg-gradient-to-br from-primary-500 to-primary-600 rounded-full flex items-center justify-center">
            <span className="text-white font-semibold text-sm">A</span>
          </div>
        </div>
      </div>
    </header>
  );
};
