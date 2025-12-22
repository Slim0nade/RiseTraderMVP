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
  getOpenPositions: async () => {
    // API returns PositionResponse with different field names than frontend Position type
    interface ApiPosition {
      id: string;
      number: string;
      type: 'BUY' | 'SELL';
      size: number;
      symbol: string;
      price: number;
      stop_loss?: number;
      take_profit?: number;
      commission: number;
      last_profit?: number;
      last_update: string;
      last_strategy: string;
      simulation: boolean;
    }

    const response = await apiClient.get<{ positions: ApiPosition[] }>('/api/trading/positions');

    // Transform API response to match frontend Position interface
    // API returns string numbers, convert to actual numbers
    return response.positions.map((apiPos): Position => ({
      id: apiPos.id,
      symbol: apiPos.symbol,
      action: apiPos.type,  // API: 'type', Frontend: 'action'
      entry_price: parseFloat(apiPos.price as any),  // API: 'price', Frontend: 'entry_price'
      current_price: parseFloat(apiPos.price as any),  // TODO: API doesn't send current_price yet, using entry for now
      quantity: parseFloat(apiPos.size as any),  // API: 'size', Frontend: 'quantity'
      unrealized_pnl: parseFloat(apiPos.last_profit as any) || 0,  // API: 'last_profit', Frontend: 'unrealized_pnl'
      stop_loss: apiPos.stop_loss ? parseFloat(apiPos.stop_loss as any) : undefined,
      take_profit: apiPos.take_profit ? parseFloat(apiPos.take_profit as any) : undefined,
      entry_time: apiPos.last_update,  // Using last_update as entry_time for now
      strategy_name: apiPos.last_strategy,
    }));
  },

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
  // Configurations
  getConfigurations: (params?: { symbol?: string; limit?: number; offset?: number }) =>
    apiClient.get<{ total: number; items: any[] }>('/api/backtesting/configurations', params),

  getConfiguration: (configId: string) =>
    apiClient.get<any>(`/api/backtesting/configurations/${configId}`),

  createConfiguration: (data: {
    name: string;
    symbol: string;
    start_date: string;
    end_date: string;
    initial_capital: string;
    execution_mode: 'full_pipeline' | 'synthetic_fast';
    agent_config_ref?: string;
    slippage_pct?: number;
    commission_pct?: number;
    commission_fixed?: number;
    max_leverage?: number;
    allow_short_selling?: boolean;
    config_params?: Record<string, any>;
  }) =>
    apiClient.post<any>('/api/backtesting/configurations', data),

  validateConfiguration: (configId: string, timeframe: string = 'M5') =>
    apiClient.post<any>(`/api/backtesting/configurations/${configId}/validate?timeframe=${timeframe}`),

  // Runs
  listRuns: (params?: { config_id?: string; status?: string; limit?: number; offset?: number }) =>
    apiClient.get<{ total: number; items: any[]; limit: number; offset: number }>('/api/backtesting/runs', params),

  runBacktest: (data: {
    config_id: string;
    timeframe: string;
    random_seed?: number;
    synthetic_strategy?: string;
    synthetic_params?: Record<string, any>;
  }) =>
    apiClient.post<any>('/api/backtesting/runs', data),

  getRunStatus: (runId: string) =>
    apiClient.get<any>(`/api/backtesting/runs/${runId}/status`),

  getRunMetrics: (runId: string) =>
    apiClient.get<any>(`/api/backtesting/runs/${runId}/metrics`),

  getRunTrades: (runId: string, params?: { limit?: number; offset?: number }) =>
    apiClient.get<{ total: number; closed_trades: number; open_trades: number; items: any[] }>(
      `/api/backtesting/runs/${runId}/trades`,
      params
    ),

  getRunDecisions: (runId: string, params?: { limit?: number; offset?: number }) =>
    apiClient.get<{ total: number; items: any[] }>(
      `/api/backtesting/runs/${runId}/decisions`,
      params
    ),

  cancelRun: (runId: string) =>
    apiClient.delete<{ success: boolean; message: string }>(`/api/backtesting/runs/${runId}`),

  // Legacy
  getBacktests: () =>
    apiClient.get<BacktestResult[]>('/api/backtests'),

  getBacktest: (backtestId: string) =>
    apiClient.get<BacktestResult>(`/api/backtests/${backtestId}`),
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

// System / Network Location
export const systemApi = {
  getNetworkLocation: () =>
    apiClient.get<{
      location: string;
      mt4_host: string;
      mt4_command_endpoint: string;
      mt4_stream_endpoint: string;
      ollama_base_url: string;
      ollama_timeout: number;
      ollama_max_retries: number;
    }>('/api/system/network-location'),

  setNetworkLocation: (location: 'local' | 'remote') =>
    apiClient.post<{
      location: string;
      mt4_host: string;
      mt4_command_endpoint: string;
      mt4_stream_endpoint: string;
      ollama_base_url: string;
      ollama_timeout: number;
      ollama_max_retries: number;
    }>('/api/system/network-location', { location }),
};
