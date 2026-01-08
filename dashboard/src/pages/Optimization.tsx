import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  Play,
  RefreshCw,
  TrendingUp,
  BarChart3,
  Settings2,
  Zap,
  Timer,
  Target,
  Shuffle,
  ChevronDown,
  ChevronUp,
  Loader2,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { optimizerApi } from '@/api/endpoints';
import { format, subMonths } from 'date-fns';

interface ParamRange {
  name: string;
  values: any[];
  type: 'number' | 'boolean';
  min?: number;
  max?: number;
  step?: number;
}

interface OptimizationResult {
  success: boolean;
  optimization_id: string;
  strategy: string;
  best_params: Record<string, any>;
  best_return_pct: number;
  best_sharpe: number;
  best_profit_factor: number;
  total_time_seconds: number;
  combinations_tested: number;
  total_combinations: number;
  top_results: any[];
}

export const Optimization: React.FC = () => {
  // Form state
  const [symbol, setSymbol] = useState('CrudeOIL');
  const [timeframe, setTimeframe] = useState('M5');
  const [startDate, setStartDate] = useState(format(subMonths(new Date(), 6), 'yyyy-MM-dd'));
  const [endDate, setEndDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [strategy, setStrategy] = useState('crude_oil_v3');
  const [optimizationTarget, setOptimizationTarget] = useState('sharpe_ratio');
  const [optimizationType, setOptimizationType] = useState<'quick' | 'full' | 'walk-forward' | 'rolling' | 'sensitivity' | 'monte-carlo'>('quick');
  const [maxCombinations, setMaxCombinations] = useState(100);
  const [initialCapital, setInitialCapital] = useState(10000);
  
  // Advanced settings
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [trainMonths, setTrainMonths] = useState(3);
  const [testMonths, setTestMonths] = useState(1);
  const [numFolds, setNumFolds] = useState(4);
  const [numSimulations, setNumSimulations] = useState(100);
  
  // Results
  const [result, setResult] = useState<OptimizationResult | null>(null);
  const [enhancedResult, setEnhancedResult] = useState<any>(null);
  
  // Fetch strategies
  const { data: strategiesData } = useQuery({
    queryKey: ['optimizer-strategies'],
    queryFn: () => optimizerApi.getStrategies(),
  });
  
  // Fetch param grid for selected strategy
  const { data: paramGridData } = useQuery({
    queryKey: ['param-grid', strategy],
    queryFn: () => optimizerApi.getParamGrid(strategy),
    enabled: !!strategy,
  });
  
  // Mutations for different optimization types
  const quickScanMutation = useMutation({
    mutationFn: () => optimizerApi.quickScan({
      symbol,
      timeframe,
      start_date: startDate,
      end_date: endDate,
      strategy,
      num_samples: maxCombinations,
      initial_capital: initialCapital,
    }),
    onSuccess: (data) => setResult(data),
  });
  
  const fullOptimizationMutation = useMutation({
    mutationFn: () => optimizerApi.runOptimization({
      symbol,
      timeframe,
      start_date: startDate,
      end_date: endDate,
      strategy,
      optimization_target: optimizationTarget,
      initial_capital: initialCapital,
      max_combinations: maxCombinations,
    }),
    onSuccess: (data) => setResult(data),
  });
  
  const walkForwardMutation = useMutation({
    mutationFn: () => optimizerApi.walkForward({
      symbol,
      timeframe,
      start_date: startDate,
      end_date: endDate,
      strategy,
      optimization_target: optimizationTarget,
      initial_capital: initialCapital,
      num_folds: numFolds,
    }),
    onSuccess: (data) => setEnhancedResult(data),
  });
  
  const rollingWindowMutation = useMutation({
    mutationFn: () => optimizerApi.rollingWindow({
      symbol,
      timeframe,
      start_date: startDate,
      end_date: endDate,
      strategy,
      optimization_target: optimizationTarget,
      initial_capital: initialCapital,
      train_months: trainMonths,
      test_months: testMonths,
      max_combinations: maxCombinations,
    }),
    onSuccess: (data) => setEnhancedResult(data),
  });
  
  const sensitivityMutation = useMutation({
    mutationFn: () => optimizerApi.sensitivity({
      symbol,
      timeframe,
      start_date: startDate,
      end_date: endDate,
      strategy,
      initial_capital: initialCapital,
    }),
    onSuccess: (data) => setEnhancedResult(data),
  });
  
  const monteCarloMutation = useMutation({
    mutationFn: () => {
      // Need best params from previous optimization
      const params = result?.best_params || paramGridData?.param_grid 
        ? Object.fromEntries(
            Object.entries(paramGridData?.param_grid || {}).map(([k, v]) => [k, Array.isArray(v) ? v[0] : v])
          )
        : {};
      return optimizerApi.monteCarlo({
        symbol,
        timeframe,
        start_date: startDate,
        end_date: endDate,
        strategy,
        params,
        num_simulations: numSimulations,
        initial_capital: initialCapital,
      });
    },
    onSuccess: (data) => setEnhancedResult(data),
  });
  
  const isRunning = 
    quickScanMutation.isPending ||
    fullOptimizationMutation.isPending ||
    walkForwardMutation.isPending ||
    rollingWindowMutation.isPending ||
    sensitivityMutation.isPending ||
    monteCarloMutation.isPending;
  
  const handleRunOptimization = () => {
    setResult(null);
    setEnhancedResult(null);
    
    switch (optimizationType) {
      case 'quick':
        quickScanMutation.mutate();
        break;
      case 'full':
        fullOptimizationMutation.mutate();
        break;
      case 'walk-forward':
        walkForwardMutation.mutate();
        break;
      case 'rolling':
        rollingWindowMutation.mutate();
        break;
      case 'sensitivity':
        sensitivityMutation.mutate();
        break;
      case 'monte-carlo':
        monteCarloMutation.mutate();
        break;
    }
  };
  
  const optimizationTypes = [
    { id: 'quick', name: 'Quick Scan', icon: Zap, description: 'Fast random search' },
    { id: 'full', name: 'Full Grid', icon: Target, description: 'Test all combinations' },
    { id: 'walk-forward', name: 'Walk Forward', icon: TrendingUp, description: 'Train/test validation' },
    { id: 'rolling', name: 'Rolling Window', icon: Timer, description: 'Periodic re-optimization' },
    { id: 'sensitivity', name: 'Sensitivity', icon: BarChart3, description: 'Parameter impact analysis' },
    { id: 'monte-carlo', name: 'Monte Carlo', icon: Shuffle, description: 'Luck vs skill analysis' },
  ];
  
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Strategy Optimizer</h1>
          <p className="text-gray-400 mt-1">Find optimal parameters for maximum returns</p>
        </div>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Configuration Panel */}
        <div className="lg:col-span-1 space-y-4">
          <div className="bg-gray-800 rounded-lg p-4 space-y-4">
            <h3 className="text-lg font-semibold text-white flex items-center gap-2">
              <Settings2 className="w-5 h-5" />
              Configuration
            </h3>
            
            {/* Symbol */}
            <div>
              <label className="block text-sm text-gray-400 mb-1">Symbol</label>
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full bg-gray-700 text-white rounded px-3 py-2"
              >
                <option value="CrudeOIL">CrudeOIL</option>
                <option value="XAUUSD">XAUUSD (Gold)</option>
                <option value="EURUSD">EURUSD</option>
              </select>
            </div>
            
            {/* Timeframe */}
            <div>
              <label className="block text-sm text-gray-400 mb-1">Timeframe</label>
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="w-full bg-gray-700 text-white rounded px-3 py-2"
              >
                <option value="M1">M1 (1 minute)</option>
                <option value="M5">M5 (5 minutes)</option>
                <option value="M15">M15 (15 minutes)</option>
                <option value="H1">H1 (1 hour)</option>
                <option value="H4">H4 (4 hours)</option>
                <option value="D1">D1 (Daily)</option>
              </select>
            </div>
            
            {/* Date Range */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Start Date</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full bg-gray-700 text-white rounded px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">End Date</label>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="w-full bg-gray-700 text-white rounded px-3 py-2"
                />
              </div>
            </div>
            
            {/* Strategy */}
            <div>
              <label className="block text-sm text-gray-400 mb-1">Strategy</label>
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                className="w-full bg-gray-700 text-white rounded px-3 py-2"
              >
                {strategiesData?.strategies?.map((s: any) => (
                  <option key={s.name} value={s.name}>
                    {s.name} ({s.total_combinations.toLocaleString()} combinations)
                  </option>
                )) || (
                  <>
                    <option value="crude_oil_v3">crude_oil_v3</option>
                    <option value="ma_crossover">ma_crossover</option>
                    <option value="rsi">rsi</option>
                    <option value="mean_reversion">mean_reversion</option>
                  </>
                )}
              </select>
            </div>
            
            {/* Optimization Target */}
            <div>
              <label className="block text-sm text-gray-400 mb-1">Optimization Target</label>
              <select
                value={optimizationTarget}
                onChange={(e) => setOptimizationTarget(e.target.value)}
                className="w-full bg-gray-700 text-white rounded px-3 py-2"
              >
                <option value="sharpe_ratio">Sharpe Ratio (risk-adjusted)</option>
                <option value="total_return_pct">Total Return %</option>
                <option value="profit_factor">Profit Factor</option>
                <option value="risk_adjusted_return">Risk-Adjusted Return</option>
              </select>
            </div>
            
            {/* Initial Capital & Max Combinations */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Capital ($)</label>
                <input
                  type="number"
                  value={initialCapital}
                  onChange={(e) => setInitialCapital(Number(e.target.value))}
                  className="w-full bg-gray-700 text-white rounded px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Max Tests</label>
                <input
                  type="number"
                  value={maxCombinations}
                  onChange={(e) => setMaxCombinations(Number(e.target.value))}
                  className="w-full bg-gray-700 text-white rounded px-3 py-2"
                />
              </div>
            </div>
            
            {/* Advanced Settings Toggle */}
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center gap-2 text-sm text-blue-400 hover:text-blue-300"
            >
              {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              Advanced Settings
            </button>
            
            {showAdvanced && (
              <div className="space-y-3 pt-2 border-t border-gray-700">
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Train Months</label>
                    <input
                      type="number"
                      value={trainMonths}
                      onChange={(e) => setTrainMonths(Number(e.target.value))}
                      className="w-full bg-gray-700 text-white rounded px-3 py-2"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Test Months</label>
                    <input
                      type="number"
                      value={testMonths}
                      onChange={(e) => setTestMonths(Number(e.target.value))}
                      className="w-full bg-gray-700 text-white rounded px-3 py-2"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Walk-Forward Folds</label>
                    <input
                      type="number"
                      value={numFolds}
                      onChange={(e) => setNumFolds(Number(e.target.value))}
                      className="w-full bg-gray-700 text-white rounded px-3 py-2"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">MC Simulations</label>
                    <input
                      type="number"
                      value={numSimulations}
                      onChange={(e) => setNumSimulations(Number(e.target.value))}
                      className="w-full bg-gray-700 text-white rounded px-3 py-2"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
          
          {/* Optimization Type Selection */}
          <div className="bg-gray-800 rounded-lg p-4">
            <h3 className="text-lg font-semibold text-white mb-3">Optimization Type</h3>
            <div className="grid grid-cols-2 gap-2">
              {optimizationTypes.map((type) => (
                <button
                  key={type.id}
                  onClick={() => setOptimizationType(type.id as any)}
                  className={`p-3 rounded-lg border transition-all ${
                    optimizationType === type.id
                      ? 'border-blue-500 bg-blue-500/20'
                      : 'border-gray-700 hover:border-gray-600'
                  }`}
                >
                  <type.icon className={`w-5 h-5 mb-1 ${optimizationType === type.id ? 'text-blue-400' : 'text-gray-400'}`} />
                  <div className="text-sm font-medium text-white">{type.name}</div>
                  <div className="text-xs text-gray-500">{type.description}</div>
                </button>
              ))}
            </div>
          </div>
          
          {/* Run Button */}
          <button
            onClick={handleRunOptimization}
            disabled={isRunning}
            className={`w-full py-3 rounded-lg font-semibold flex items-center justify-center gap-2 ${
              isRunning
                ? 'bg-gray-600 cursor-not-allowed'
                : 'bg-blue-600 hover:bg-blue-700'
            }`}
          >
            {isRunning ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Running Optimization...
              </>
            ) : (
              <>
                <Play className="w-5 h-5" />
                Run Optimization
              </>
            )}
          </button>
        </div>
        
        {/* Results Panel */}
        <div className="lg:col-span-2 space-y-4">
          {/* Parameter Grid Preview */}
          {paramGridData && (
            <div className="bg-gray-800 rounded-lg p-4">
              <h3 className="text-lg font-semibold text-white mb-3">
                Parameter Grid ({paramGridData.total_combinations.toLocaleString()} combinations)
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {Object.entries(paramGridData.param_grid).map(([name, values]) => (
                  <div key={name} className="bg-gray-700 rounded p-2">
                    <div className="text-sm text-gray-400">{name}</div>
                    <div className="text-white font-mono text-sm truncate">
                      {Array.isArray(values) ? `[${values.slice(0, 3).join(', ')}${values.length > 3 ? ', ...' : ''}]` : String(values)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {/* Basic Optimization Results */}
          {result && (
            <div className="bg-gray-800 rounded-lg p-4 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-white">Optimization Results</h3>
                <div className="flex items-center gap-2 text-sm text-gray-400">
                  <Timer className="w-4 h-4" />
                  {result.total_time_seconds.toFixed(1)}s
                </div>
              </div>
              
              {/* Summary Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-gray-700 rounded p-3">
                  <div className="text-sm text-gray-400">Best Return</div>
                  <div className={`text-xl font-bold ${result.best_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {result.best_return_pct.toFixed(2)}%
                  </div>
                </div>
                <div className="bg-gray-700 rounded p-3">
                  <div className="text-sm text-gray-400">Best Sharpe</div>
                  <div className={`text-xl font-bold ${result.best_sharpe >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {result.best_sharpe.toFixed(2)}
                  </div>
                </div>
                <div className="bg-gray-700 rounded p-3">
                  <div className="text-sm text-gray-400">Profit Factor</div>
                  <div className={`text-xl font-bold ${result.best_profit_factor >= 1 ? 'text-green-400' : 'text-red-400'}`}>
                    {result.best_profit_factor.toFixed(2)}
                  </div>
                </div>
                <div className="bg-gray-700 rounded p-3">
                  <div className="text-sm text-gray-400">Tests Run</div>
                  <div className="text-xl font-bold text-white">
                    {result.combinations_tested}
                  </div>
                </div>
              </div>
              
              {/* Best Parameters */}
              <div>
                <h4 className="text-sm font-semibold text-gray-400 mb-2">Best Parameters</h4>
                <div className="bg-gray-900 rounded p-3 font-mono text-sm overflow-x-auto">
                  <pre className="text-green-400">{JSON.stringify(result.best_params, null, 2)}</pre>
                </div>
              </div>
              
              {/* Top Results Table */}
              <div>
                <h4 className="text-sm font-semibold text-gray-400 mb-2">Top Results</h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-gray-400 border-b border-gray-700">
                        <th className="text-left py-2 px-2">#</th>
                        <th className="text-right py-2 px-2">Return %</th>
                        <th className="text-right py-2 px-2">Sharpe</th>
                        <th className="text-right py-2 px-2">Profit Factor</th>
                        <th className="text-right py-2 px-2">Win Rate</th>
                        <th className="text-right py-2 px-2">Trades</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.top_results?.slice(0, 10).map((r: any, idx: number) => (
                        <tr key={idx} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                          <td className="py-2 px-2 text-gray-400">{idx + 1}</td>
                          <td className={`py-2 px-2 text-right ${r.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {r.total_return_pct?.toFixed(2)}%
                          </td>
                          <td className={`py-2 px-2 text-right ${r.sharpe_ratio >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {r.sharpe_ratio?.toFixed(2)}
                          </td>
                          <td className={`py-2 px-2 text-right ${r.profit_factor >= 1 ? 'text-green-400' : 'text-red-400'}`}>
                            {r.profit_factor?.toFixed(2)}
                          </td>
                          <td className="py-2 px-2 text-right text-white">
                            {r.win_rate?.toFixed(1)}%
                          </td>
                          <td className="py-2 px-2 text-right text-gray-400">
                            {r.total_trades}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
          
          {/* Enhanced Results (Walk-Forward, Rolling, etc.) */}
          {enhancedResult && (
            <div className="bg-gray-800 rounded-lg p-4 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-white">
                  {optimizationType === 'walk-forward' && 'Walk-Forward Analysis'}
                  {optimizationType === 'rolling' && 'Rolling Window Analysis'}
                  {optimizationType === 'sensitivity' && 'Sensitivity Analysis'}
                  {optimizationType === 'monte-carlo' && 'Monte Carlo Validation'}
                </h3>
                {enhancedResult.recommendation && (
                  <span className={`text-sm px-2 py-1 rounded ${
                    enhancedResult.recommendation?.includes('STRONG') ? 'bg-green-500/20 text-green-400' :
                    enhancedResult.recommendation?.includes('MODERATE') ? 'bg-yellow-500/20 text-yellow-400' :
                    'bg-red-500/20 text-red-400'
                  }`}>
                    {enhancedResult.recommendation?.split(':')[0]}
                  </span>
                )}
              </div>
              
              {/* Walk-Forward / Rolling Results */}
              {(optimizationType === 'walk-forward' || optimizationType === 'rolling') && enhancedResult.aggregate && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="bg-gray-700 rounded p-3">
                    <div className="text-sm text-gray-400">Total Return</div>
                    <div className={`text-xl font-bold ${enhancedResult.aggregate.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {enhancedResult.aggregate.total_return_pct?.toFixed(2)}%
                    </div>
                  </div>
                  <div className="bg-gray-700 rounded p-3">
                    <div className="text-sm text-gray-400">Robustness</div>
                    <div className={`text-xl font-bold ${enhancedResult.aggregate.robustness_ratio >= 0.5 ? 'text-green-400' : 'text-red-400'}`}>
                      {(enhancedResult.aggregate.robustness_ratio * 100).toFixed(0)}%
                    </div>
                  </div>
                  <div className="bg-gray-700 rounded p-3">
                    <div className="text-sm text-gray-400">Final Capital</div>
                    <div className="text-xl font-bold text-white">
                      ${enhancedResult.aggregate.final_capital?.toLocaleString()}
                    </div>
                  </div>
                  <div className="bg-gray-700 rounded p-3">
                    <div className="text-sm text-gray-400">Total Trades</div>
                    <div className="text-xl font-bold text-white">
                      {enhancedResult.aggregate.total_trades}
                    </div>
                  </div>
                </div>
              )}
              
              {/* Sensitivity Results */}
              {optimizationType === 'sensitivity' && enhancedResult.sensitivity_rankings && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-400 mb-2">Parameter Sensitivity Ranking</h4>
                  <div className="space-y-2">
                    {enhancedResult.sensitivity_rankings.map((param: any, idx: number) => (
                      <div key={param.param_name} className="flex items-center gap-3 bg-gray-700 rounded p-2">
                        <span className="text-gray-400 w-6">{idx + 1}.</span>
                        <span className="text-white font-medium flex-1">{param.param_name}</span>
                        <span className="text-sm text-gray-400">Sensitivity: {param.sensitivity_score.toFixed(2)}</span>
                        <span className="text-sm text-green-400">Optimal: {String(param.optimal_value)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Monte Carlo Results */}
              {optimizationType === 'monte-carlo' && enhancedResult.monte_carlo && (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="bg-gray-700 rounded p-3">
                      <div className="text-sm text-gray-400">Actual Return</div>
                      <div className={`text-xl font-bold ${enhancedResult.base_result?.return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {enhancedResult.base_result?.return_pct?.toFixed(2)}%
                      </div>
                    </div>
                    <div className="bg-gray-700 rounded p-3">
                      <div className="text-sm text-gray-400">Mean (MC)</div>
                      <div className="text-xl font-bold text-white">
                        {enhancedResult.monte_carlo.return_pct.mean?.toFixed(2)}%
                      </div>
                    </div>
                    <div className="bg-gray-700 rounded p-3">
                      <div className="text-sm text-gray-400">5th Percentile</div>
                      <div className="text-xl font-bold text-red-400">
                        {enhancedResult.monte_carlo.return_pct.p5?.toFixed(2)}%
                      </div>
                    </div>
                    <div className="bg-gray-700 rounded p-3">
                      <div className="text-sm text-gray-400">95th Percentile</div>
                      <div className="text-xl font-bold text-green-400">
                        {enhancedResult.monte_carlo.return_pct.p95?.toFixed(2)}%
                      </div>
                    </div>
                  </div>
                  
                  {enhancedResult.interpretation && (
                    <div className="bg-blue-500/10 border border-blue-500/30 rounded p-3">
                      <div className="text-blue-400">{enhancedResult.interpretation}</div>
                    </div>
                  )}
                </div>
              )}
              
              {/* Recommendation */}
              {enhancedResult.recommendation && (
                <div className="bg-gray-700 rounded p-3">
                  <div className="text-sm text-gray-400 mb-1">Recommendation</div>
                  <div className="text-white">{enhancedResult.recommendation}</div>
                </div>
              )}
            </div>
          )}
          
          {/* Empty State */}
          {!result && !enhancedResult && !isRunning && (
            <div className="bg-gray-800 rounded-lg p-12 text-center">
              <BarChart3 className="w-16 h-16 text-gray-600 mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-white mb-2">No Results Yet</h3>
              <p className="text-gray-400">
                Configure your optimization parameters and click "Run Optimization" to find the best strategy settings.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Optimization;
