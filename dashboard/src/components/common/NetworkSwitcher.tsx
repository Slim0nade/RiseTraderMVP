import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Wifi, WifiOff, Home, Globe } from 'lucide-react';
import { systemApi } from '@/api/endpoints';
import toast from 'react-hot-toast';

export const NetworkSwitcher: React.FC = () => {
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);

  // Get current network location
  const { data: networkConfig, isLoading } = useQuery({
    queryKey: ['network-location'],
    queryFn: systemApi.getNetworkLocation,
    refetchInterval: 30000, // Refresh every 30s
  });

  // Switch network location
  const switchMutation = useMutation({
    mutationFn: (location: 'local' | 'remote') =>
      systemApi.setNetworkLocation(location),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['network-location'] });
      toast.success(
        `Switched to ${data.location.toUpperCase()} network (${data.mt4_host})`,
        { duration: 3000 }
      );
      setIsOpen(false);
    },
    onError: (error: any) => {
      // Extract detailed error message
      const errorMessage = error?.response?.data?.detail
        || error?.response?.data?.message
        || error?.message
        || 'Unknown error';

      const statusCode = error?.response?.status;
      const fullMessage = statusCode
        ? `Failed to switch network (${statusCode}): ${errorMessage}`
        : `Failed to switch network: ${errorMessage}`;

      console.error('Network switch error:', error);
      toast.error(fullMessage, { duration: 5000 });
    },
  });

  const handleSwitch = (location: 'local' | 'remote') => {
    if (networkConfig?.location === location) {
      setIsOpen(false);
      return;
    }
    switchMutation.mutate(location);
  };

  const isLocal = networkConfig?.location === 'local';
  const currentHost = networkConfig?.mt4_host || '...';

  return (
    <div className="relative">
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-all ${
          isLocal
            ? 'bg-success-500/10 border-success-500/30 text-success-400 hover:bg-success-500/20'
            : 'bg-primary-500/10 border-primary-500/30 text-primary-400 hover:bg-primary-500/20'
        } ${isLoading ? 'opacity-50 cursor-wait' : ''}`}
        disabled={isLoading || switchMutation.isPending}
        title={`Network: ${networkConfig?.location || 'loading'} (${currentHost})`}
      >
        {isLocal ? (
          <Home className="w-4 h-4" />
        ) : (
          <Globe className="w-4 h-4" />
        )}
        <span className="text-sm font-medium hidden sm:inline">
          {isLocal ? 'Home' : 'Remote'}
        </span>
        {switchMutation.isPending && (
          <div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
        )}
      </button>

      {/* Dropdown Menu */}
      {isOpen && !isLoading && (
        <div className="absolute right-0 mt-2 w-80 bg-dark-900 border border-dark-700 rounded-lg shadow-xl z-50">
          <div className="p-4">
            <h3 className="text-sm font-semibold text-dark-50 mb-3">
              Network Location
            </h3>

            {/* Local Option */}
            <button
              onClick={() => handleSwitch('local')}
              disabled={switchMutation.isPending}
              className={`w-full text-left p-3 rounded-lg border mb-2 transition-all ${
                isLocal
                  ? 'bg-success-500/10 border-success-500/50'
                  : 'border-dark-700 hover:border-dark-600 hover:bg-dark-800'
              } ${switchMutation.isPending ? 'opacity-50 cursor-wait' : ''}`}
            >
              <div className="flex items-start gap-3">
                <Home
                  className={`w-5 h-5 mt-0.5 ${
                    isLocal ? 'text-success-500' : 'text-dark-400'
                  }`}
                />
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <span
                      className={`font-medium ${
                        isLocal ? 'text-success-400' : 'text-dark-200'
                      }`}
                    >
                      Home Network
                    </span>
                    {isLocal && (
                      <span className="text-xs bg-success-500/20 text-success-400 px-2 py-0.5 rounded">
                        Active
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-dark-500">192.168.0.123</p>
                  <p className="text-xs text-dark-600 mt-1">
                    Fast local connection • Low latency
                  </p>
                </div>
              </div>
            </button>

            {/* Remote Option */}
            <button
              onClick={() => handleSwitch('remote')}
              disabled={switchMutation.isPending}
              className={`w-full text-left p-3 rounded-lg border transition-all ${
                !isLocal
                  ? 'bg-primary-500/10 border-primary-500/50'
                  : 'border-dark-700 hover:border-dark-600 hover:bg-dark-800'
              } ${switchMutation.isPending ? 'opacity-50 cursor-wait' : ''}`}
            >
              <div className="flex items-start gap-3">
                <Globe
                  className={`w-5 h-5 mt-0.5 ${
                    !isLocal ? 'text-primary-500' : 'text-dark-400'
                  }`}
                />
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <span
                      className={`font-medium ${
                        !isLocal ? 'text-primary-400' : 'text-dark-200'
                      }`}
                    >
                      Internet
                    </span>
                    {!isLocal && (
                      <span className="text-xs bg-primary-500/20 text-primary-400 px-2 py-0.5 rounded">
                        Active
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-dark-500">75.154.254.186</p>
                  <p className="text-xs text-dark-600 mt-1">
                    Remote access • Available anywhere
                  </p>
                </div>
              </div>
            </button>

            {/* Current Config Info */}
            {networkConfig && (
              <div className="mt-3 pt-3 border-t border-dark-800">
                <p className="text-xs text-dark-500 mb-2">Current Configuration:</p>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-dark-600">MT4 Host:</span>
                    <span className="text-dark-400 font-mono">
                      {networkConfig.mt4_host}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-dark-600">Ollama:</span>
                    <span className="text-dark-400 font-mono text-right break-all">
                      {networkConfig.ollama_base_url.replace('http://', '')}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Close button */}
          <button
            onClick={() => setIsOpen(false)}
            className="w-full py-2 text-xs text-dark-500 hover:text-dark-300 border-t border-dark-800"
          >
            Close
          </button>
        </div>
      )}

      {/* Click outside to close */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setIsOpen(false)}
        />
      )}
    </div>
  );
};
