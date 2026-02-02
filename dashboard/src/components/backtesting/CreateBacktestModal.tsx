import React, { useState, useEffect } from 'react';
import { X, Plus, Calendar, DollarSign, Settings, Sparkles } from 'lucide-react';
import { backtestApi } from '@/api/endpoints';
import { IntelligentDatePicker } from './IntelligentDatePicker';
import type { ExecutionMode } from '@/types';

interface CreateBacktestModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (runId: string) => void;
  initialConfig?: any; // Configuration to copy from
}

interface BacktestFormData {
  name: string;
  symbol: string;
  startDate: string;
  endDate: string;
  initialCapital: string;
  executionMode: ExecutionMode;
  model: string;
  syntheticStrategy: string;
  timeframe: string;
  slippagePct: string;
  commissionPct: string;
}

const SYMBOLS = [
  { value: 'CrudeOIL', label: 'Crude Oil' },
  { value: 'Gold', label: 'Gold' },
  { value: 'EURUSD', label: 'EUR/USD' },
  { value: 'GBPUSD', label: 'GBP/USD' },
  { value: 'USDJPY', label: 'USD/JPY' },
];

const MODELS = [
  // Open-Source Models (Free - Local/Ollama)
  { value: 'mistral:7b-instruct', label: 'Mistral 7B Instruct (Recommended - Free)' },
  { value: 'qwen2.5:14b', label: 'Qwen 2.5 14B (Fast, Efficient - Free)' },
  { value: 'deepseek-r1:14b', label: 'DeepSeek R1 14B (Better Reasoning - Free)' },
  { value: 'llama3.1:70b', label: 'Llama 3.1 70B (Most Capable - Free)' },
  { value: 'phi3:mini', label: 'Phi-3 Mini (Ultra Fast - Free)' },
  { value: 'phi4-mini', label: 'Phi-4 Mini (Latest Small Model - Free)' },
  { value: 'mistral-small3.1', label: 'Mistral Small 3.1 (Balanced - Free)' },
  { value: 'qwen3:14b', label: 'Qwen3 14B (Alternative - Free)' },

  // Proprietary Models (Paid - Best Quality)
  { value: 'gpt-4o', label: 'GPT-4o (Best Overall - OpenAI - Paid)' },
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini (Fast & Affordable - OpenAI - Paid)' },
  { value: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet (Best Reasoning - Anthropic - Paid)' },
  { value: 'claude-3-5-haiku-20241022', label: 'Claude 3.5 Haiku (Fast - Anthropic - Paid)' },
  { value: 'mistral-large-latest', label: 'Mistral Large (Proprietary - High Quality - Paid)' },
  { value: 'mistral-small-latest', label: 'Mistral Small (Proprietary - Efficient - Paid)' },
];

const TIMEFRAMES = [
  { value: 'M1', label: '1 Minute (Recommended - Data until Nov 2025)' },
  { value: 'M5', label: '5 Minutes (Data until Dec 2024)' },
  { value: 'M15', label: '15 Minutes' },
  { value: 'H1', label: '1 Hour' },
  { value: 'H4', label: '4 Hours' },
  { value: 'D1', label: 'Daily' },
];

const SYNTHETIC_STRATEGIES = [
  { value: 'crude_oil_v3', label: 'Crude Oil V3 (EMA + RSI + CCI)' },
  { value: 'crude_oil_v2', label: 'Crude Oil V2 (Legacy)' },
  { value: 'crude_oil_v1', label: 'Crude Oil V1 (Basic)' },
  { value: 'ma_crossover', label: 'MA Crossover (Simple)' },
];

export const CreateBacktestModal: React.FC<CreateBacktestModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  initialConfig,
}) => {
  const [formData, setFormData] = useState<BacktestFormData>({
    name: '',
    symbol: 'CrudeOIL',
    startDate: '2025-01-01',
    endDate: '2025-12-31',
    initialCapital: '10000',
    executionMode: 'synthetic_fast',
    model: 'mistral:7b-instruct',
    syntheticStrategy: 'crude_oil_v3',
    timeframe: 'M1', // Changed to M1 - we have data until Nov 2025
    slippagePct: '0.001',
    commissionPct: '0.0002',
  });

  // Pre-fill form when copying a configuration
  useEffect(() => {
    if (initialConfig) {
      setFormData({
        name: initialConfig.name || '',
        symbol: initialConfig.symbol || 'CrudeOIL',
        startDate: initialConfig.start_date ? new Date(initialConfig.start_date).toISOString().split('T')[0] : '2025-01-01',
        endDate: initialConfig.end_date ? new Date(initialConfig.end_date).toISOString().split('T')[0] : '2025-12-31',
        initialCapital: initialConfig.initial_capital?.toString() || '10000',
        executionMode: initialConfig.execution_mode || 'synthetic_fast',
        model: initialConfig.config_params?.agent_config?.model || 'mistral:7b-instruct',
        syntheticStrategy: initialConfig.config_params?.synthetic_strategy || 'crude_oil_v3',
        timeframe: initialConfig.config_params?.timeframe || 'M1',
        slippagePct: initialConfig.slippage_pct?.toString() || '0.001',
        commissionPct: initialConfig.commission_pct?.toString() || '0.0002',
      });
    }
  }, [initialConfig]);

  // Auto-generate backtest name based on configuration
  const generateBacktestName = (data: BacktestFormData): string => {
    const symbolLabel = SYMBOLS.find(s => s.value === data.symbol)?.label || data.symbol;
    const startMonth = new Date(data.startDate).toLocaleDateString('en-US', { month: 'short' });
    const endMonth = new Date(data.endDate).toLocaleDateString('en-US', { month: 'short' });
    const startYear = new Date(data.startDate).getFullYear();
    const endYear = new Date(data.endDate).getFullYear();
    const yearRange = startYear === endYear ? startYear : `${startYear}-${endYear}`;
    const modeLabel = data.executionMode === 'synthetic_fast' ? 'Synthetic' : 'Agent';

    return `${symbolLabel} ${data.timeframe} ${modeLabel} ${startMonth}-${endMonth} ${yearRange}`;
  };

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDatesValid, setIsDatesValid] = useState(true);

  const handleChange = (field: keyof BacktestFormData, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    setError(null); // Clear error on input change
  };

  // Auto-generate name when modal opens or key config changes
  useEffect(() => {
    if (isOpen && !formData.name) {
      const generatedName = generateBacktestName(formData);
      setFormData((prev) => ({ ...prev, name: generatedName }));
    }
  }, [isOpen]);

  // Manual regenerate name function
  const handleRegenerateName = () => {
    const generatedName = generateBacktestName(formData);
    setFormData((prev) => ({ ...prev, name: generatedName }));
  };

  const validateForm = (): string | null => {
    if (!formData.name.trim()) return 'Name is required';
    if (!formData.symbol) return 'Symbol is required';
    if (!formData.startDate) return 'Start date is required';
    if (!formData.endDate) return 'End date is required';

    const start = new Date(formData.startDate);
    const end = new Date(formData.endDate);
    if (start >= end) return 'End date must be after start date';

    const capital = parseFloat(formData.initialCapital);
    if (isNaN(capital) || capital <= 0) return 'Initial capital must be greater than 0';

    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const validationError = validateForm();
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      // Step 1: Create configuration
      const configData: any = {
        name: formData.name,
        symbol: formData.symbol,
        start_date: new Date(formData.startDate).toISOString(),
        end_date: new Date(formData.endDate).toISOString(),
        initial_capital: formData.initialCapital,
        execution_mode: formData.executionMode,
        slippage_pct: parseFloat(formData.slippagePct),
        commission_pct: parseFloat(formData.commissionPct),
        allow_short_selling: true,
        config_params: {},
      };

      // Add agent config if using full pipeline mode
      if (formData.executionMode === 'full_pipeline') {
        configData.config_params = {
          agent_config: {
            model: formData.model,
            ollama_base_url: 'http://75.154.254.174:11434/v1',
            temperature: 0.7,
            max_tokens: 500,
          },
        };
      }

      // Add synthetic strategy if using synthetic mode
      if (formData.executionMode === 'synthetic_fast') {
        // Define params based on selected strategy
        let synthetic_params: any = {};

        switch (formData.syntheticStrategy) {
          case 'ma_crossover':
            synthetic_params = {
              fast_period: 10,
              slow_period: 30,
              quantity: 1.0,
            };
            break;
          case 'crude_oil_v1':
            synthetic_params = {
              fast_period: 5,
              slow_period: 20,
              quantity: 1.0,
            };
            break;
          case 'crude_oil_v2':
            synthetic_params = {
              ema_fast: 12,
              ema_slow: 26,
              rsi_period: 14,
              quantity: 1.0,
            };
            break;
          case 'crude_oil_v3':
          default:
            synthetic_params = {
              ema_fast: 8,
              ema_slow: 29,
              rsi_period: 10,
              rsi_overbought: 68,
              rsi_oversold: 32,
              cci_period: 20,
              cci_overbought: 100,
              cci_oversold: -80,
              atr_period: 10,
              atr_multiplier: 2.0,
              risk_reward_ratio: 2.5,
              momentum_period: 10,
              use_cci_filter: true,
              use_strict_filter: false,
              use_time_filter: true,
              trading_start_hour: 8,
              trading_end_hour: 20,
              quantity: 1.0,
            };
        }

        configData.config_params = {
          synthetic_strategy: formData.syntheticStrategy,
          synthetic_params,
        };
      }

      const config = await backtestApi.createConfiguration(configData);

      // Step 2: Start backtest run
      const run = await backtestApi.runBacktest({
        config_id: config.id,
        timeframe: formData.timeframe,
      });

      // Success - close modal and call onSuccess callback
      onClose();
      if (onSuccess) {
        onSuccess(run.run_id);
      }
    } catch (err: any) {
      console.error('Failed to create backtest:', err);
      setError(err.message || 'Failed to create backtest. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-dark-900 rounded-lg border border-dark-700 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-dark-700">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary-500/10 rounded-lg">
              <Plus className="w-5 h-5 text-primary-500" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-dark-50">Create New Backtest</h2>
              <p className="text-sm text-dark-400 mt-1">
                Configure and run a new backtest simulation
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="p-2 hover:bg-dark-800 rounded-lg transition-colors disabled:opacity-50"
          >
            <X className="w-5 h-5 text-dark-400" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Error Message */}
          {error && (
            <div className="bg-danger-500/10 border border-danger-500/50 rounded-lg p-4">
              <p className="text-sm text-danger-400">{error}</p>
            </div>
          )}

          {/* Basic Information */}
          <div className="space-y-4">
            <h3 className="text-sm font-medium text-dark-300 flex items-center gap-2">
              <Settings className="w-4 h-4" />
              Basic Information
            </h3>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-dark-300">
                  Backtest Name
                </label>
                <button
                  type="button"
                  onClick={handleRegenerateName}
                  className="text-xs text-primary-500 hover:text-primary-400 transition-colors flex items-center gap-1"
                  disabled={isSubmitting}
                >
                  <Sparkles className="w-3 h-3" />
                  Regenerate
                </button>
              </div>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => handleChange('name', e.target.value)}
                placeholder="e.g., CrudeOIL Swing Strategy Test"
                className="w-full bg-dark-800 border border-dark-600 rounded-lg px-4 py-2.5 text-dark-50 placeholder-dark-500 focus:outline-none focus:border-primary-500 transition-colors"
                disabled={isSubmitting}
              />
              <p className="text-xs text-dark-500 mt-1">
                Auto-generated based on symbol, dates, and settings. Click to customize.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-dark-300 mb-2">
                  Symbol
                </label>
                <select
                  value={formData.symbol}
                  onChange={(e) => handleChange('symbol', e.target.value)}
                  className="w-full bg-dark-800 border border-dark-600 rounded-lg px-4 py-2.5 text-dark-50 focus:outline-none focus:border-primary-500 transition-colors"
                  disabled={isSubmitting}
                >
                  {SYMBOLS.map((sym) => (
                    <option key={sym.value} value={sym.value}>
                      {sym.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-dark-300 mb-2">
                  Timeframe
                </label>
                <select
                  value={formData.timeframe}
                  onChange={(e) => handleChange('timeframe', e.target.value)}
                  className="w-full bg-dark-800 border border-dark-600 rounded-lg px-4 py-2.5 text-dark-50 focus:outline-none focus:border-primary-500 transition-colors"
                  disabled={isSubmitting}
                >
                  {TIMEFRAMES.map((tf) => (
                    <option key={tf.value} value={tf.value}>
                      {tf.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Date Range - Intelligent Picker */}
          <div className="space-y-4">
            <h3 className="text-sm font-medium text-dark-300 flex items-center gap-2">
              <Calendar className="w-4 h-4" />
              Date Range
            </h3>

            <IntelligentDatePicker
              symbol={formData.symbol}
              timeframe={formData.timeframe}
              startDate={formData.startDate}
              endDate={formData.endDate}
              onStartDateChange={(date) => handleChange('startDate', date)}
              onEndDateChange={(date) => handleChange('endDate', date)}
              onValidationChange={setIsDatesValid}
            />
          </div>

          {/* Capital & Execution */}
          <div className="space-y-4">
            <h3 className="text-sm font-medium text-dark-300 flex items-center gap-2">
              <DollarSign className="w-4 h-4" />
              Capital & Execution
            </h3>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-dark-300 mb-2">
                  Initial Capital ($)
                </label>
                <input
                  type="number"
                  value={formData.initialCapital}
                  onChange={(e) => handleChange('initialCapital', e.target.value)}
                  min="100"
                  step="100"
                  className="w-full bg-dark-800 border border-dark-600 rounded-lg px-4 py-2.5 text-dark-50 focus:outline-none focus:border-primary-500 transition-colors"
                  disabled={isSubmitting}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-dark-300 mb-2">
                  Execution Mode
                </label>
                <select
                  value={formData.executionMode}
                  onChange={(e) =>
                    handleChange('executionMode', e.target.value as ExecutionMode)
                  }
                  className="w-full bg-dark-800 border border-dark-600 rounded-lg px-4 py-2.5 text-dark-50 focus:outline-none focus:border-primary-500 transition-colors"
                  disabled={isSubmitting}
                >
                  <option value="synthetic_fast">Synthetic (Fast)</option>
                  <option value="full_pipeline">Agent Pipeline (with LLM)</option>
                </select>
              </div>
            </div>
          </div>

          {/* Synthetic Strategy Configuration - Only show if synthetic_fast mode */}
          {formData.executionMode === 'synthetic_fast' && (
            <div className="space-y-4 bg-success-500/5 border border-success-500/20 rounded-lg p-4">
              <h3 className="text-sm font-medium text-success-400">Synthetic Strategy Configuration</h3>
              <div>
                <label className="block text-sm font-medium text-dark-300 mb-2">
                  Strategy
                </label>
                <select
                  value={formData.syntheticStrategy}
                  onChange={(e) => handleChange('syntheticStrategy', e.target.value)}
                  className="w-full bg-dark-800 border border-dark-600 rounded-lg px-4 py-2.5 text-dark-50 focus:outline-none focus:border-primary-500 transition-colors"
                  disabled={isSubmitting}
                >
                  {SYNTHETIC_STRATEGIES.map((strategy) => (
                    <option key={strategy.value} value={strategy.value}>
                      {strategy.label}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-dark-500 mt-2">
                  Choose a pre-configured trading strategy for synthetic backtesting.
                </p>
              </div>
            </div>
          )}

          {/* Agent Configuration - Only show if full_pipeline mode */}
          {formData.executionMode === 'full_pipeline' && (
            <div className="space-y-4 bg-primary-500/5 border border-primary-500/20 rounded-lg p-4">
              <h3 className="text-sm font-medium text-primary-400">Agent Configuration</h3>
              <div>
                <label className="block text-sm font-medium text-dark-300 mb-2">
                  LLM Model
                </label>
                <select
                  value={formData.model}
                  onChange={(e) => handleChange('model', e.target.value)}
                  className="w-full bg-dark-800 border border-dark-600 rounded-lg px-4 py-2.5 text-dark-50 focus:outline-none focus:border-primary-500 transition-colors"
                  disabled={isSubmitting}
                >
                  {MODELS.map((model) => (
                    <option key={model.value} value={model.value}>
                      {model.label}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-dark-500 mt-2">
                  Note: Agents are currently disabled due to config mismatch. Synthetic mode
                  is recommended.
                </p>
              </div>
            </div>
          )}

          {/* Advanced Settings */}
          <div className="space-y-4">
            <details className="group">
              <summary className="text-sm font-medium text-dark-300 cursor-pointer list-none flex items-center justify-between">
                <span>Advanced Settings</span>
                <span className="text-dark-500 group-open:rotate-180 transition-transform">
                  ▼
                </span>
              </summary>
              <div className="mt-4 grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-dark-300 mb-2">
                    Slippage (%)
                  </label>
                  <input
                    type="number"
                    value={formData.slippagePct}
                    onChange={(e) => handleChange('slippagePct', e.target.value)}
                    min="0"
                    step="0.0001"
                    className="w-full bg-dark-800 border border-dark-600 rounded-lg px-4 py-2.5 text-dark-50 focus:outline-none focus:border-primary-500 transition-colors"
                    disabled={isSubmitting}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-dark-300 mb-2">
                    Commission (%)
                  </label>
                  <input
                    type="number"
                    value={formData.commissionPct}
                    onChange={(e) => handleChange('commissionPct', e.target.value)}
                    min="0"
                    step="0.0001"
                    className="w-full bg-dark-800 border border-dark-600 rounded-lg px-4 py-2.5 text-dark-50 focus:outline-none focus:border-primary-500 transition-colors"
                    disabled={isSubmitting}
                  />
                </div>
              </div>
            </details>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-dark-700">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-6 py-2.5 bg-dark-800 hover:bg-dark-700 text-dark-300 rounded-lg transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !isDatesValid}
              className="px-6 py-2.5 bg-primary-500 hover:bg-primary-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              title={!isDatesValid ? 'Please select valid dates with available data' : ''}
            >
              {isSubmitting ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Plus className="w-4 h-4" />
                  Create & Run Backtest
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
