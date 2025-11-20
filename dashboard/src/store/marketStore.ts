import { create } from 'zustand';
import type { MarketData } from '@/types';

interface MarketState {
  currentSymbol: string;
  currentTimeframe: string;
  marketData: Record<string, MarketData[]>;
  latestTicks: Record<string, MarketData>;

  setCurrentSymbol: (symbol: string) => void;
  setCurrentTimeframe: (timeframe: string) => void;
  setMarketData: (symbol: string, data: MarketData[]) => void;
  updateLatestTick: (symbol: string, tick: MarketData) => void;
  appendMarketData: (symbol: string, tick: MarketData) => void;
}

export const useMarketStore = create<MarketState>((set) => ({
  currentSymbol: 'CrudeOIL',
  currentTimeframe: 'M1',
  marketData: {},
  latestTicks: {},

  setCurrentSymbol: (symbol) => set({ currentSymbol: symbol }),

  setCurrentTimeframe: (timeframe) => set({ currentTimeframe: timeframe }),

  setMarketData: (symbol, data) =>
    set((state) => ({
      marketData: {
        ...state.marketData,
        [symbol]: data,
      },
    })),

  updateLatestTick: (symbol, tick) =>
    set((state) => ({
      latestTicks: {
        ...state.latestTicks,
        [symbol]: tick,
      },
    })),

  appendMarketData: (symbol, tick) =>
    set((state) => ({
      marketData: {
        ...state.marketData,
        [symbol]: [...(state.marketData[symbol] || []).slice(-499), tick],
      },
    })),
}));
