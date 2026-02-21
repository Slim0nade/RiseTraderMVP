// Core Trading Types
export interface Position {
  id: string;
  symbol: string;
  action: 'BUY' | 'SELL';
  entry_price: number;
  current_price: number;
  quantity: number;
  unrealized_pnl: number;
  stop_loss?: number;
  take_profit?: number;
  entry_time: string;
  strategy_name?: string;
}

export interface Trade {
  id: string;
  symbol: string;
  action: 'BUY' | 'SELL';
  entry_price: number;
  exit_price?: number;
  quantity: number;
  realized_pnl?: number;
  entry_time: string;
  exit_time?: string;
  strategy_name?: string;
  status: 'OPEN' | 'CLOSED' | 'CANCELLED';
}

export interface MarketData {
  symbol: string;
  timeframe: string;
  time: string;  // API returns 'time' not 'timestamp'
  timestamp?: string;  // Keep for backwards compatibility
  open: number | string;  // API returns strings, we convert to numbers
  high: number | string;
  low: number | string;
  close: number | string;
  volume: number | string;
  tick_volume?: number;
  spread?: number;
  source?: string;  // Data source (MT4, CSV, DUKASCOPY, BARCHART, etc.)
  import_symbol?: string;
}

// Agent Types
export type AgentStatus = 'active' | 'idle' | 'error' | 'stopped' | 'initializing';

export interface Agent {
  name: string;
  status: AgentStatus;
  last_active: string;
  last_event?: string;
  state: Record<string, any>;
  error_message?: string;
  metrics?: {
    events_processed: number;
    avg_response_time_ms: number;
    success_rate: number;
  };
}

export interface AgentEvent {
  agent_name: string;
  event_type: string;
  timestamp: string;
  data: Record<string, any>;
  success: boolean;
}

// ML Forecast Types
export interface Forecast {
  id: string;
  symbol: string;
  timestamp: string;
  forecast_horizon: number; // minutes
  predicted_price: number;
  confidence: number;
  model_name: string;
  features?: Record<string, number>;
}

// Strategy Types
export interface Strategy {
  id: string;
  name: string;
  description: string;
  is_active: boolean;
  allocation_pct: number;
  symbols: string[];
  parameters: Record<string, any>;
  performance?: StrategyPerformance;
}

export interface StrategyPerformance {
  strategy_name: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  total_pnl: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  sharpe_ratio?: number;
  max_drawdown?: number;
}

// Performance Metrics
export interface PerformanceMetrics {
  total_pnl: number;
  daily_pnl: number;
  weekly_pnl: number;
  monthly_pnl: number;
  open_positions: number;
  total_trades: number;
  win_rate: number;
  sharpe_ratio: number;
  max_drawdown: number;
  max_drawdown_pct: number;
  avg_trade_duration_minutes: number;
  best_trade: number;
  worst_trade: number;
  profit_factor?: number;
}

export interface EquityCurvePoint {
  timestamp: string;
  equity: number;
  drawdown: number;
}

// Risk Management
export interface RiskMetrics {
  current_exposure: number;
  max_exposure: number;
  utilization_pct: number;
  var_daily: number; // Value at Risk
  sharpe_ratio: number;
  open_positions_count: number;
  max_positions: number;
}

// System Status
export interface SystemStatus {
  status: 'healthy' | 'degraded' | 'down';
  uptime_seconds: number;
  api_version: string;
  database_connected: boolean;
  redis_connected: boolean;
  mt4_connected: boolean;
  agents_running: number;
  total_agents: number;
  last_health_check: string;
}

// WebSocket Message Types
export interface WebSocketMessage {
  event_type:
    | 'new_tick'
    | 'position_opened'
    | 'position_closed'
    | 'position_updated'
    | 'agent_status_changed'
    | 'forecast_generated'
    | 'pnl_updated'
    | 'risk_alert'
    | 'system_alert';
  data: any;
  timestamp: string;
}

// API Response Types
export interface ApiResponse<T> {
  data: T;
  message?: string;
  timestamp: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// Chart Data Types
export interface OHLCData {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface IndicatorData {
  timestamp: string;
  value: number;
  indicator_name: string;
}

// Settings Types
export interface UserSettings {
  api_key?: string;
  theme: 'light' | 'dark';
  default_symbol: string;
  default_timeframe: string;
  notifications_enabled: boolean;
  alert_settings: {
    pnl_threshold: number;
    risk_alerts: boolean;
    agent_errors: boolean;
  };
}

// Backtest Types
export type ExecutionMode = 'full_pipeline' | 'synthetic_fast';
export type RunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface BacktestConfiguration {
  id: string;
  name: string;
  symbol: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  execution_mode: ExecutionMode;
  agent_config_ref?: string;
  slippage_pct?: number;
  commission_pct?: number;
  commission_fixed?: number;
  max_leverage?: number;
  allow_short_selling: boolean;
  config_params?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface BacktestRun {
  run_id: string;
  config_id: string;
  status: RunStatus;
  start_time: string;
  end_time?: string;
  candles_processed: number;
  total_trades: number;
  agent_decisions_count: number;
  final_capital?: number;
  error_message?: string;
  metrics?: BacktestMetrics;
}

export interface BacktestMetrics {
  total_return: number;
  total_return_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  max_drawdown?: number;       // Legacy field name
  max_drawdown_abs?: number;   // Backend field name (absolute dollar value)
  max_drawdown_pct: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  avg_win: number;
  avg_loss: number;
  avg_trade_duration_minutes?: number;
  largest_win: number;
  largest_loss: number;
}

export interface SimulatedTrade {
  id: string;
  backtest_run_id: string; // Matches backend field name
  run_id?: string; // Legacy field, kept for backwards compatibility
  symbol: string;
  action: 'BUY' | 'SELL';
  entry_timestamp: string;
  entry_price: number;
  quantity: number;
  exit_timestamp?: string;
  exit_price?: number;
  gross_pnl?: number; // P&L before fees
  net_pnl?: number; // P&L after fees (use this for calculations)
  pnl?: number; // Legacy field, kept for backwards compatibility
  commission?: number;
  slippage?: number;
  stop_loss?: number;
  take_profit?: number;
  decision_id?: string;
}

export interface AgentDecision {
  id: string;
  run_id?: string;
  timestamp: string;
  decision_type: 'BUY' | 'SELL' | 'HOLD';
  symbol: string;
  conviction_score: number;
  quantity?: number;
  stop_loss?: number;
  take_profit?: number;
  risk_assessment: string;
  reasoning?: string;
  market_context?: Record<string, any>;
}

export interface BacktestResult {
  id: string;
  strategy_name: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_equity: number;
  total_return_pct: number;
  total_trades: number;
  win_rate: number;
  sharpe_ratio: number;
  max_drawdown: number;
  profit_factor: number;
  created_at: string;
}

// News/Events
export interface NewsEvent {
  id: string;
  timestamp: string;
  title: string;
  currency: string;
  impact: 'low' | 'medium' | 'high';
  forecast?: string;
  previous?: string;
  actual?: string;
}
