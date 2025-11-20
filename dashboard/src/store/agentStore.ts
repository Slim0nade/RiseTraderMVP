import { create } from 'zustand';
import type { Agent, AgentEvent } from '@/types';

interface AgentState {
  agents: Agent[];
  selectedAgent: Agent | null;
  agentEvents: AgentEvent[];

  setAgents: (agents: Agent[]) => void;
  updateAgent: (agent: Agent) => void;
  setSelectedAgent: (agent: Agent | null) => void;

  addEvent: (event: AgentEvent) => void;
  clearEvents: () => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  agents: [],
  selectedAgent: null,
  agentEvents: [],

  setAgents: (agents) => set({ agents }),

  updateAgent: (agent) =>
    set((state) => ({
      agents: state.agents.some((a) => a.name === agent.name)
        ? state.agents.map((a) => (a.name === agent.name ? agent : a))
        : [...state.agents, agent],
    })),

  setSelectedAgent: (agent) => set({ selectedAgent: agent }),

  addEvent: (event) =>
    set((state) => ({
      agentEvents: [event, ...state.agentEvents].slice(0, 100),
    })),

  clearEvents: () => set({ agentEvents: [] }),
}));
