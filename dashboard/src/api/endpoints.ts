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

  getHistoricalData: async (symbol: string, timeframe: string, limit?: number) => {
    const response = await apiClient.get<{ data: MarketData[] }>(`/api/market-data/${symbol}`, {
      timeframe,
      limit: limit || 500,
    });
    return response.data;
  },

  getSymbols: async () => {
    const response = await apiClient.get<{ symbols: Array<{ symbol: string }> }>('/api/market-data/symbols');
    return response.symbols.map(s => s.symbol);
  },

  getAvailableTimeframes: () =>
    apiClient.get<Record<string, string[]>>('/api/market-data/timeframes/available'),
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

  getRunSnapshots: (runId: string, params?: { limit?: number; offset?: number }) =>
    apiClient.get<{ total: number; items: { timestamp: string; total_value: number; cash_balance: number; unrealized_pnl: number; realized_pnl: number }[] }>(
      `/api/backtesting/runs/${runId}/snapshots`,
      params
    ),

  getLiveStats: (runId: string) =>
    apiClient.get<{
      run_id: string;
      status: string;
      progress: { candles_processed: number; agent_decisions: number };
      trade_counts: { total: number; closed: number; open: number; buy: number; sell: number; win: number; loss: number };
      performance: { win_rate: number; realized_pnl: number; unrealized_pnl: number; total_pnl: number; gross_pnl: number; total_fees: number; current_equity: number };
    }>(`/api/backtesting/runs/${runId}/live-stats`),

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

// Strategy Optimizer
export const optimizerApi = {
  // Basic optimization
  runOptimization: (params: {
    symbol: string;
    timeframe: string;
    start_date: string;
    end_date: string;
    strategy: string;
    param_grid?: Record<string, any[]>;
    optimization_target?: string;
    initial_capital?: number;
    max_combinations?: number;
  }) =>
    apiClient.post<any>('/api/optimizer/run', params),

  quickScan: (params: {
    symbol: string;
    timeframe: string;
    start_date: string;
    end_date: string;
    strategy: string;
    num_samples?: number;
    initial_capital?: number;
  }) =>
    apiClient.post<any>('/api/optimizer/quick-scan', params),

  walkForward: (params: {
    symbol: string;
    timeframe: string;
    start_date: string;
    end_date: string;
    strategy: string;
    param_grid?: Record<string, any[]>;
    optimization_target?: string;
    train_pct?: number;
    num_folds?: number;
    initial_capital?: number;
  }) =>
    apiClient.post<any>('/api/optimizer/walk-forward', params),

  // Enhanced optimization
  rollingWindow: (params: {
    symbol: string;
    timeframe: string;
    start_date: string;
    end_date: string;
    strategy: string;
    param_grid?: Record<string, any[]>;
    optimization_target?: string;
    train_months?: number;
    test_months?: number;
    step_months?: number;
    initial_capital?: number;
    max_combinations?: number;
  }) =>
    apiClient.post<any>('/api/optimizer/rolling-window', params),

  timeIntervals: (params: {
    symbol: string;
    timeframe: string;
    start_date: string;
    end_date: string;
    strategy: string;
    intervals: { name: string; start_date: string; end_date: string }[];
    param_grid?: Record<string, any[]>;
    optimization_target?: string;
    initial_capital?: number;
    max_combinations?: number;
  }) =>
    apiClient.post<any>('/api/optimizer/time-intervals', params),

  sensitivity: (params: {
    symbol: string;
    timeframe: string;
    start_date: string;
    end_date: string;
    strategy: string;
    base_params?: Record<string, any>;
    initial_capital?: number;
  }) =>
    apiClient.post<any>('/api/optimizer/sensitivity', params),

  monteCarlo: (params: {
    symbol: string;
    timeframe: string;
    start_date: string;
    end_date: string;
    strategy: string;
    params: Record<string, any>;
    num_simulations?: number;
    initial_capital?: number;
  }) =>
    apiClient.post<any>('/api/optimizer/monte-carlo', params),

  // Metadata
  getStrategies: () =>
    apiClient.get<{ strategies: any[]; optimization_targets: string[] }>('/api/optimizer/strategies'),

  getParamGrid: (strategy: string) =>
    apiClient.get<{ strategy: string; param_grid: Record<string, any[]>; total_combinations: number }>(
      `/api/optimizer/param-grids/${strategy}`
    ),
};

// EDA - Automated Data Quality Analysis
export const edaApi = {
  // Data quality summary with score
  getDataQuality: (symbol: string, timeframe: string = 'M5', startDate?: string, endDate?: string) =>
    apiClient.get<{
      status: string;
      symbol: string;
      timeframe: string;
      data_points: number;
      date_range: { start: string; end: string };
      checks: {
        missing_values: { status: string; details: Record<string, number>; total_missing: number };
        duplicate_timestamps: { status: string; count: number };
        price_consistency: { status: string; inconsistent_candles: number };
        outliers: { status: string; count: number; percentage: number; bounds: { lower: number; upper: number } };
        volume_anomalies: { status: string; zero_volume_candles: number; extreme_volume_candles: number };
        data_gaps: { status: string; gap_count: number; largest_gaps: { start: string; duration_minutes: number }[] };
      };
      issues: { type: string; severity: string; message: string }[];
      score: number;
    }>(`/api/eda/quality/${symbol}`, {
      timeframe,
      ...(startDate && { start_date: startDate }),
      ...(endDate && { end_date: endDate }),
    }),

  // Distribution analysis for OHLCV and derived features
  getDistributions: (symbol: string, timeframe: string = 'M5', startDate?: string, endDate?: string) =>
    apiClient.get<{
      status: string;
      symbol: string;
      timeframe: string;
      data_points: number;
      distributions: Record<string, {
        count: number;
        mean: number;
        median: number;
        std: number;
        min: number;
        max: number;
        q25: number;
        q75: number;
        skewness: number;
        kurtosis: number;
        histogram: { counts: number[]; bin_edges: number[] };
      }>;
    }>(`/api/eda/distributions/${symbol}`, {
      timeframe,
      ...(startDate && { start_date: startDate }),
      ...(endDate && { end_date: endDate }),
    }),

  // Correlation matrix
  getCorrelations: (symbol: string, timeframe: string = 'M5', includeIndicators: boolean = true) =>
    apiClient.get<{
      status: string;
      symbol: string;
      timeframe: string;
      data_points: number;
      features: string[];
      matrix: number[][];
      high_correlations: { feature_1: string; feature_2: string; correlation: number }[];
    }>(`/api/eda/correlations/${symbol}`, { timeframe, include_indicators: includeIndicators }),

  // Compare two periods (train/test validation)
  comparePeriods: (
    symbol: string,
    timeframe: string,
    period1Start: string,
    period1End: string,
    period2Start: string,
    period2End: string
  ) =>
    apiClient.get<{
      status: string;
      symbol: string;
      timeframe: string;
      period1: { start: string; end: string; data_points: number };
      period2: { start: string; end: string; data_points: number };
      comparisons: Record<string, {
        period1: { mean: number; std: number; min: number; max: number };
        period2: { mean: number; std: number; min: number; max: number };
        mean_shift_std: number;
        std_ratio: number;
      }>;
      warnings: { type: string; feature: string; message: string }[];
    }>(`/api/eda/compare-periods/${symbol}`, {
      timeframe,
      period1_start: period1Start,
      period1_end: period1End,
      period2_start: period2Start,
      period2_end: period2End,
    }),

  // Full automated EDA report
  getFullReport: (symbol: string, timeframe: string = 'M5', startDate?: string, endDate?: string) =>
    apiClient.get<{
      status: string;
      symbol: string;
      timeframe: string;
      generated_at: string;
      quality_summary: any;
      distributions: any;
      correlations: any;
      recommendations: { priority: string; category: string; action: string }[];
    }>(`/api/eda/report/${symbol}`, {
      timeframe,
      ...(startDate && { start_date: startDate }),
      ...(endDate && { end_date: endDate }),
    }),

  // Quick overview of all symbols
  getSymbolsOverview: (timeframe: string = 'M5') =>
    apiClient.get<{
      status: string;
      timeframe: string;
      symbols: { symbol: string; timeframe: string; score: number; status: string; data_points: number; issue_count: number }[];
    }>('/api/eda/symbols-overview', { timeframe }),
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
