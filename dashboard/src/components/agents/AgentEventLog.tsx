import React from 'react';
import { AgentEvent } from '@/types';
import { useFormatters } from '@/hooks/useFormatters';
import { CheckCircle2, XCircle } from 'lucide-react';
import { cn } from '@/utils/cn';

interface AgentEventLogProps {
  events: AgentEvent[];
  maxHeight?: string;
}

export const AgentEventLog: React.FC<AgentEventLogProps> = ({
  events,
  maxHeight = 'max-h-96',
}) => {
  const formatters = useFormatters();

  if (events.length === 0) {
    return (
      <div className="bg-dark-900 rounded-lg border border-dark-700 p-8 text-center text-dark-500">
        No events logged yet
      </div>
    );
  }

  return (
    <div className={cn('bg-dark-900 rounded-lg border border-dark-700 overflow-hidden', maxHeight)}>
      <div className="overflow-y-auto h-full">
        <div className="divide-y divide-dark-800">
          {events.map((event, index) => (
            <div
              key={index}
              className="p-3 hover:bg-dark-800/50 transition-colors"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  {event.success ? (
                    <CheckCircle2 className="w-4 h-4 text-success-500 flex-shrink-0" />
                  ) : (
                    <XCircle className="w-4 h-4 text-danger-500 flex-shrink-0" />
                  )}
                  <span className="text-sm font-medium text-dark-200">{event.agent_name}</span>
                </div>
                <span className="text-xs text-dark-500">
                  {formatters.date(event.timestamp, 'HH:mm:ss')}
                </span>
              </div>

              <div className="ml-6">
                <p className="text-sm text-primary-400 mb-1 font-mono">{event.event_type}</p>
                {Object.keys(event.data).length > 0 && (
                  <details className="text-xs text-dark-400">
                    <summary className="cursor-pointer hover:text-dark-300">
                      View data
                    </summary>
                    <pre className="mt-1 p-2 bg-dark-950 rounded overflow-auto">
                      {JSON.stringify(event.data, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
