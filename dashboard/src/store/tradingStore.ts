import { create } from 'zustand';
import type { Position, Trade } from '@/types';

interface TradingState {
  positions: Position[];
  recentTrades: Trade[];
  selectedPosition: Position | null;

  setPositions: (positions: Position[]) => void;
  updatePosition: (position: Position) => void;
  removePosition: (positionId: string) => void;
  setSelectedPosition: (position: Position | null) => void;

  setRecentTrades: (trades: Trade[]) => void;
  addTrade: (trade: Trade) => void;
}

export const useTradingStore = create<TradingState>((set) => ({
  positions: [],
  recentTrades: [],
  selectedPosition: null,

  setPositions: (positions) => set({ positions }),

  updatePosition: (position) =>
    set((state) => ({
      positions: state.positions.some((p) => p.id === position.id)
        ? state.positions.map((p) => (p.id === position.id ? position : p))
        : [...state.positions, position],
    })),

  removePosition: (positionId) =>
    set((state) => ({
      positions: state.positions.filter((p) => p.id !== positionId),
    })),

  setSelectedPosition: (position) => set({ selectedPosition: position }),

  setRecentTrades: (trades) => set({ recentTrades: trades }),

  addTrade: (trade) =>
    set((state) => ({
      recentTrades: [trade, ...state.recentTrades].slice(0, 50),
    })),
}));
