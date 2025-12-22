import { create } from 'zustand';
import type {
  BacktestConfiguration,
  BacktestRun,
  SimulatedTrade,
  AgentDecision,
} from '@/types';

interface BacktestState {
  configurations: BacktestConfiguration[];
  runs: BacktestRun[];
  selectedRun: BacktestRun | null;
  selectedConfig: BacktestConfiguration | null;
  trades: SimulatedTrade[];
  decisions: AgentDecision[];
  isPolling: boolean;

  // Configuration actions
  setConfigurations: (configs: BacktestConfiguration[]) => void;
  addConfiguration: (config: BacktestConfiguration) => void;
  setSelectedConfig: (config: BacktestConfiguration | null) => void;

  // Run actions
  setRuns: (runs: BacktestRun[]) => void;
  addRun: (run: BacktestRun) => void;
  updateRun: (run: BacktestRun) => void;
  setSelectedRun: (run: BacktestRun | null) => void;

  // Trade actions
  setTrades: (trades: SimulatedTrade[]) => void;

  // Decision actions
  setDecisions: (decisions: AgentDecision[]) => void;

  // Polling control
  setIsPolling: (polling: boolean) => void;

  // Utility actions
  clearAll: () => void;
}

export const useBacktestStore = create<BacktestState>((set) => ({
  configurations: [],
  runs: [],
  selectedRun: null,
  selectedConfig: null,
  trades: [],
  decisions: [],
  isPolling: false,

  setConfigurations: (configurations) => set({ configurations }),

  addConfiguration: (config) =>
    set((state) => ({
      configurations: [config, ...state.configurations],
    })),

  setSelectedConfig: (config) => set({ selectedConfig: config }),

  setRuns: (runs) => set({ runs }),

  addRun: (run) =>
    set((state) => ({
      runs: [run, ...state.runs],
    })),

  updateRun: (run) =>
    set((state) => ({
      runs: state.runs.map((r) => (r.run_id === run.run_id ? run : r)),
      selectedRun:
        state.selectedRun?.run_id === run.run_id ? run : state.selectedRun,
    })),

  setSelectedRun: (run) => set({ selectedRun: run }),

  setTrades: (trades) => set({ trades }),

  setDecisions: (decisions) => set({ decisions }),

  setIsPolling: (isPolling) => set({ isPolling }),

  clearAll: () =>
    set({
      configurations: [],
      runs: [],
      selectedRun: null,
      selectedConfig: null,
      trades: [],
      decisions: [],
      isPolling: false,
    }),
}));
