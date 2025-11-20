import { apiClient } from './client';
import type {
  Position,
  Trade,
  MarketData,
  Agent,
  Forecast,
  Strategy,
  StrategyPerformance,
  PerformanceMetrics,
  SystemStatus,
  BacktestResult,
  NewsEvent,
  PaginatedResponse,
} from '@/types';

// Health & System
export const healthApi = {
  getHealth: () => apiClient.get<{ status: string; timestamp: string }>('/health'),
  getSystemStatus: () => apiClient.get<SystemStatus>('/api/system/status'),
};

// Market Data
export const marketDataApi = {
  getLatestTick: (symbol: string) =>
    apiClient.get<MarketData>(`/api/market-data/${symbol}/latest`),

  getHistoricalData: (symbol: string, timeframe: string, limit?: number) =>
    apiClient.get<MarketData[]>(`/api/market-data/${symbol}`, {
      timeframe,
      limit: limit || 500,
    }),

  getSymbols: () =>
    apiClient.get<string[]>('/api/market-data/symbols'),
};

// Trading
export const tradingApi = {
  getOpenPositions: () =>
    apiClient.get<Position[]>('/api/trading/positions'),

  getPosition: (positionId: string) =>
    apiClient.get<Position>(`/api/trading/positions/${positionId}`),

  closePosition: (positionId: string) =>
    apiClient.post<{ success: boolean; message: string }>(
      `/api/trading/positions/${positionId}/close`
    ),

  getTradeHistory: (params?: {
    start_date?: string;
    end_date?: string;
    symbol?: string;
    page?: number;
    page_size?: number;
  }) =>
    apiClient.get<PaginatedResponse<Trade>>('/api/trading/history', params),

  executeTrade: (data: {
    symbol: string;
    action: 'BUY' | 'SELL';
    quantity: number;
    stop_loss?: number;
    take_profit?: number;
  }) =>
    apiClient.post<Trade>('/api/trading/execute', data),
};

// Agents
export const agentsApi = {
  getAllAgents: () =>
    apiClient.get<Agent[]>('/api/agents/status'),

  getAgent: (agentName: string) =>
    apiClient.get<Agent>(`/api/agents/${agentName}/status`),

  startAgent: (agentName: string) =>
    apiClient.post<{ success: boolean; message: string }>(
      `/api/agents/${agentName}/start`
    ),

  stopAgent: (agentName: string) =>
    apiClient.post<{ success: boolean; message: string }>(
      `/api/agents/${agentName}/stop`
    ),

  restartAgent: (agentName: string) =>
    apiClient.post<{ success: boolean; message: string }>(
      `/api/agents/${agentName}/restart`
    ),

  getAgentMetrics: (agentName: string) =>
    apiClient.get<any>(`/api/agents/${agentName}/metrics`),
};

// Forecasts
export const forecastsApi = {
  getLatestForecasts: (symbol?: string) =>
    apiClient.get<Forecast[]>('/api/forecasts/latest', symbol ? { symbol } : undefined),

  getForecastHistory: (symbol: string, hours?: number) =>
    apiClient.get<Forecast[]>(`/api/forecasts/${symbol}/history`, {
      hours: hours || 24,
    }),

  generateForecast: (symbol: string) =>
    apiClient.post<Forecast>('/api/forecasts/generate', { symbol }),
};

// Strategies
export const strategiesApi = {
  getAllStrategies: () =>
    apiClient.get<Strategy[]>('/api/strategies'),

  getStrategy: (strategyId: string) =>
    apiClient.get<Strategy>(`/api/strategies/${strategyId}`),

  createStrategy: (data: Partial<Strategy>) =>
    apiClient.post<Strategy>('/api/strategies', data),

  updateStrategy: (strategyId: string, data: Partial<Strategy>) =>
    apiClient.put<Strategy>(`/api/strategies/${strategyId}`, data),

  deleteStrategy: (strategyId: string) =>
    apiClient.delete<{ success: boolean }>(`/api/strategies/${strategyId}`),

  toggleStrategy: (strategyId: string, active: boolean) =>
    apiClient.patch<Strategy>(`/api/strategies/${strategyId}/toggle`, { active }),

  getStrategyPerformance: (strategyName: string) =>
    apiClient.get<StrategyPerformance>(`/api/strategies/${strategyName}/performance`),
};

// Performance
export const performanceApi = {
  getMetrics: (params?: { start_date?: string; end_date?: string }) =>
    apiClient.get<PerformanceMetrics>('/api/performance/metrics', params),

  getEquityCurve: (params?: { start_date?: string; end_date?: string }) =>
    apiClient.get<{ timestamp: string; equity: number; drawdown: number }[]>(
      '/api/performance/equity-curve',
      params
    ),

  getDailyPnL: (days?: number) =>
    apiClient.get<{ date: string; pnl: number }[]>('/api/performance/daily-pnl', {
      days: days || 30,
    }),
};

// Backtesting
export const backtestApi = {
  getBacktests: () =>
    apiClient.get<BacktestResult[]>('/api/backtests'),

  getBacktest: (backtestId: string) =>
    apiClient.get<BacktestResult>(`/api/backtests/${backtestId}`),

  runBacktest: (data: {
    strategy_name: string;
    start_date: string;
    end_date: string;
    initial_capital?: number;
    symbols?: string[];
  }) =>
    apiClient.post<BacktestResult>('/api/backtests/run', data),
};

// News & Events
export const newsApi = {
  getUpcomingEvents: (hours?: number) =>
    apiClient.get<NewsEvent[]>('/api/news/upcoming', {
      hours: hours || 24,
    }),

  getRecentEvents: (hours?: number) =>
    apiClient.get<NewsEvent[]>('/api/news/recent', {
      hours: hours || 24,
    }),
};

// Risk Management
export const riskApi = {
  getRiskMetrics: () =>
    apiClient.get<{
      current_exposure: number;
      max_exposure: number;
      utilization_pct: number;
      open_positions: number;
      max_positions: number;
    }>('/api/risk/metrics'),

  getVaR: (confidence?: number) =>
    apiClient.get<{ var_daily: number; confidence: number }>('/api/risk/var', {
      confidence: confidence || 0.95,
    }),
};
