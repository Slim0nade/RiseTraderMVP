import React from 'react';
import { AgentMessage } from './AgentMessage';
import type { AgentDecision } from '@/types';

interface AgentConversationProps {
  decisions: AgentDecision[];
}

export const AgentConversation: React.FC<AgentConversationProps> = ({ decisions }) => {
  // Sort decisions by timestamp
  const sortedDecisions = React.useMemo(() => {
    return [...decisions].sort((a, b) =>
      new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );
  }, [decisions]);

  return (
    <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-dark-50">Agent Decision Log</h2>
        <span className="text-sm text-dark-500">
          {decisions.length} decision{decisions.length !== 1 ? 's' : ''}
        </span>
      </div>

      <div className="space-y-4 max-h-[700px] overflow-y-auto pr-2">
        {sortedDecisions.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-dark-400">No agent decisions recorded</p>
          </div>
        ) : (
          sortedDecisions.map((decision, index) => (
            <AgentMessage
              key={decision.id || index}
              decision={decision}
              isFirst={index === 0}
            />
          ))
        )}
      </div>
    </div>
  );
};
