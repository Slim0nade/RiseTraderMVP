import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  BarChart3,
  Activity,
  TrendingUp,
  Database,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Info,
} from 'lucide-react';
import { edaApi, marketDataApi } from '@/api/endpoints';
import { cn } from '@/utils/cn';

const TIMEFRAMES = ['M1', 'M5', 'M15', 'H1', 'H4', 'D1'];

// Score to color mapping
const getScoreColor = (score: number) => {
  if (score >= 90) return 'text-success-500';
  if (score >= 70) return 'text-warning-500';
  if (score >= 50) return 'text-orange-500';
  return 'text-danger-500';
};

const getScoreBgColor = (score: number) => {
  if (score >= 90) return 'bg-success-500/10 border-success-500/30';
  if (score >= 70) return 'bg-warning-500/10 border-warning-500/30';
  if (score >= 50) return 'bg-orange-500/10 border-orange-500/30';
  return 'bg-danger-500/10 border-danger-500/30';
};

const getStatusIcon = (status: string) => {
  switch (status) {
    case 'pass':
      return <CheckCircle className="w-5 h-5 text-success-500" />;
    case 'fail':
      return <XCircle className="w-5 h-5 text-danger-500" />;
    case 'warning':
      return <AlertTriangle className="w-5 h-5 text-warning-500" />;
    default:
      return <Info className="w-5 h-5 text-dark-400" />;
  }
};

const getSeverityColor = (severity: string) => {
  switch (severity) {
    case 'critical':
      return 'bg-danger-500/20 text-danger-400 border-danger-500/30';
    case 'high':
      return 'bg-orange-500/20 text-orange-400 border-orange-500/30';
    case 'medium':
      return 'bg-warning-500/20 text-warning-400 border-warning-500/30';
    case 'low':
      return 'bg-primary-500/20 text-primary-400 border-primary-500/30';
    default:
      return 'bg-dark-700 text-dark-300 border-dark-600';
  }
};

// Histogram component
const Histogram: React.FC<{ data: { counts: number[]; bin_edges: number[] }; label: string }> = ({
  data,
  label,
}) => {
  const maxCount = Math.max(...data.counts);

  return (
    <div className="mt-2">
      <p className="text-xs text-dark-500 mb-1">{label} Distribution</p>
      <div className="flex items-end gap-px h-16">
        {data.counts.map((count, i) => (
          <div
            key={i}
            className="flex-1 bg-primary-500 rounded-t"
            style={{ height: `${(count / maxCount) * 100}%` }}
            title={`${data.bin_edges[i].toFixed(2)} - ${data.bin_edges[i + 1].toFixed(2)}: ${count}`}
          />
        ))}
      </div>
      <div className="flex justify-between text-[10px] text-dark-500 mt-1">
        <span>{data.bin_edges[0].toFixed(2)}</span>
        <span>{data.bin_edges[data.bin_edges.length - 1].toFixed(2)}</span>
      </div>
    </div>
  );
};

// Correlation Heatmap component
const CorrelationHeatmap: React.FC<{
  features: string[];
  matrix: number[][];
}> = ({ features, matrix }) => {
  const getColor = (value: number) => {
    const absVal = Math.abs(value);
    if (absVal > 0.8) return value > 0 ? 'bg-success-600' : 'bg-danger-600';
    if (absVal > 0.5) return value > 0 ? 'bg-success-500/70' : 'bg-danger-500/70';
    if (absVal > 0.3) return value > 0 ? 'bg-success-500/40' : 'bg-danger-500/40';
    return 'bg-dark-700';
  };

  // Show only first 10 features to avoid overflow
  const displayFeatures = features.slice(0, 10);
  const displayMatrix = matrix.slice(0, 10).map((row) => row.slice(0, 10));

  return (
    <div className="overflow-x-auto">
      <div className="inline-block">
        <div className="flex">
          <div className="w-20" />
          {displayFeatures.map((f) => (
            <div
              key={f}
              className="w-12 h-20 flex items-end justify-center pb-1"
            >
              <span
                className="text-[10px] text-dark-400 transform -rotate-45 origin-bottom-left whitespace-nowrap"
              >
                {f}
              </span>
            </div>
          ))}
        </div>
        {displayMatrix.map((row, i) => (
          <div key={displayFeatures[i]} className="flex">
            <div className="w-20 text-xs text-dark-400 flex items-center pr-2 truncate">
              {displayFeatures[i]}
            </div>
            {row.map((val, j) => (
              <div
                key={j}
                className={cn(
                  'w-12 h-8 flex items-center justify-center text-[10px] font-mono',
                  getColor(val),
                  i === j && 'opacity-50'
                )}
                title={`${displayFeatures[i]} vs ${displayFeatures[j]}: ${val.toFixed(3)}`}
              >
                {i !== j && val.toFixed(2)}
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="flex items-center gap-4 mt-4 text-xs text-dark-400">
        <span className="flex items-center gap-1">
          <div className="w-3 h-3 bg-danger-600 rounded" /> Strong negative
        </span>
        <span className="flex items-center gap-1">
          <div className="w-3 h-3 bg-dark-700 rounded" /> Weak
        </span>
        <span className="flex items-center gap-1">
          <div className="w-3 h-3 bg-success-600 rounded" /> Strong positive
        </span>
      </div>
    </div>
  );
};

export const DataQuality: React.FC = () => {
  const [selectedSymbol, setSelectedSymbol] = useState('CrudeOIL');
  const [selectedTimeframe, setSelectedTimeframe] = useState('M5');
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['quality', 'distributions', 'correlations'])
  );

  // Fetch symbols
  const { data: symbols } = useQuery({
    queryKey: ['symbols'],
    queryFn: marketDataApi.getSymbols,
  });

  // Fetch full EDA report
  const {
    data: report,
    isLoading,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['eda-report', selectedSymbol, selectedTimeframe],
    queryFn: () => edaApi.getFullReport(selectedSymbol, selectedTimeframe),
    staleTime: 60000, // 1 minute
  });

  // Fetch symbols overview for comparison
  const { data: overview } = useQuery({
    queryKey: ['eda-overview', selectedTimeframe],
    queryFn: () => edaApi.getSymbolsOverview(selectedTimeframe),
    staleTime: 60000,
  });

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(section)) {
        next.delete(section);
      } else {
        next.add(section);
      }
      return next;
    });
  };

  const quality = report?.quality_summary;
  const distributions = report?.distributions;
  const correlations = report?.correlations;
  const recommendations = report?.recommendations || [];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-dark-50 mb-2">Data Quality</h1>
          <p className="text-dark-400">
            Automated EDA - 80% of insights with 20% of the effort
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors',
            'bg-primary-500 text-white hover:bg-primary-600',
            isFetching && 'opacity-50 cursor-not-allowed'
          )}
        >
          <RefreshCw className={cn('w-4 h-4', isFetching && 'animate-spin')} />
          Refresh Analysis
        </button>
      </div>

      {/* Symbol & Timeframe Selector */}
      <div className="bg-dark-900 rounded-lg border border-dark-700 p-4">
        <div className="flex flex-wrap items-center gap-6">
          {/* Symbol Selector */}
          <div>
            <label className="text-sm text-dark-500 mb-2 block">Symbol</label>
            <div className="flex gap-2">
              {(symbols || []).map((item) => {
                const sym = typeof item === 'string' ? item : item.symbol;
                return (
                  <button
                    key={sym}
                    onClick={() => setSelectedSymbol(sym)}
                    className={cn(
                      'px-4 py-2 rounded-lg font-medium transition-colors',
                      selectedSymbol === sym
                        ? 'bg-primary-500 text-white'
                        : 'bg-dark-800 text-dark-300 hover:bg-dark-700'
                    )}
                  >
                    {sym}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Timeframe Selector */}
          <div>
            <label className="text-sm text-dark-500 mb-2 block">Timeframe</label>
            <div className="flex gap-2">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  onClick={() => setSelectedTimeframe(tf)}
                  className={cn(
                    'px-4 py-2 rounded-lg font-medium transition-colors',
                    selectedTimeframe === tf
                      ? 'bg-primary-500 text-white'
                      : 'bg-dark-800 text-dark-300 hover:bg-dark-700'
                  )}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Symbols Overview Cards */}
      {overview?.symbols && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {overview.symbols.map((sym) => (
            <div
              key={sym.symbol}
              onClick={() => setSelectedSymbol(sym.symbol)}
              className={cn(
                'bg-dark-900 rounded-lg border p-4 cursor-pointer transition-all',
                selectedSymbol === sym.symbol
                  ? 'border-primary-500 ring-1 ring-primary-500/30'
                  : 'border-dark-700 hover:border-dark-600',
                getScoreBgColor(sym.score)
              )}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold text-dark-100">{sym.symbol}</span>
                <span className={cn('text-2xl font-bold', getScoreColor(sym.score))}>
                  {sym.score}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-dark-400">{sym.data_points.toLocaleString()} pts</span>
                <span
                  className={cn(
                    'px-2 py-0.5 rounded text-xs font-medium',
                    sym.status === 'excellent' && 'bg-success-500/20 text-success-400',
                    sym.status === 'good' && 'bg-primary-500/20 text-primary-400',
                    sym.status === 'fair' && 'bg-warning-500/20 text-warning-400',
                    sym.status === 'poor' && 'bg-danger-500/20 text-danger-400'
                  )}
                >
                  {sym.status}
                </span>
              </div>
              {sym.issue_count > 0 && (
                <p className="text-xs text-dark-500 mt-2">
                  {sym.issue_count} issue{sym.issue_count > 1 ? 's' : ''} found
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {isLoading ? (
        <div className="bg-dark-900 rounded-lg border border-dark-700 p-12 text-center">
          <RefreshCw className="w-8 h-8 text-primary-500 animate-spin mx-auto mb-4" />
          <p className="text-dark-400">Analyzing data quality...</p>
        </div>
      ) : (
        <>
          {/* Quality Score & Summary */}
          {quality && (
            <div className="bg-dark-900 rounded-lg border border-dark-700">
              <button
                onClick={() => toggleSection('quality')}
                className="w-full p-6 flex items-center justify-between hover:bg-dark-800/50 transition-colors"
              >
                <div className="flex items-center gap-4">
                  <Database className="w-6 h-6 text-primary-500" />
                  <div className="text-left">
                    <h2 className="text-xl font-semibold text-dark-50">Data Quality Score</h2>
                    <p className="text-sm text-dark-400">
                      {quality.data_points?.toLocaleString()} data points analyzed
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <span className={cn('text-4xl font-bold', getScoreColor(quality.score))}>
                      {quality.score}
                    </span>
                    <span className="text-dark-400 text-lg">/100</span>
                  </div>
                  {expandedSections.has('quality') ? (
                    <ChevronUp className="w-5 h-5 text-dark-400" />
                  ) : (
                    <ChevronDown className="w-5 h-5 text-dark-400" />
                  )}
                </div>
              </button>

              {expandedSections.has('quality') && (
                <div className="px-6 pb-6 border-t border-dark-800">
                  {/* Quality Checks Grid */}
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mt-6">
                    {quality.checks &&
                      Object.entries(quality.checks).map(([key, check]: [string, any]) => (
                        <div
                          key={key}
                          className="bg-dark-800 rounded-lg p-4 border border-dark-700"
                        >
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-sm text-dark-300 capitalize">
                              {key.replace(/_/g, ' ')}
                            </span>
                            {getStatusIcon(check.status)}
                          </div>
                          <div className="text-dark-400 text-xs">
                            {key === 'missing_values' && (
                              <span>{check.total_missing} missing values</span>
                            )}
                            {key === 'duplicate_timestamps' && (
                              <span>{check.count} duplicates</span>
                            )}
                            {key === 'price_consistency' && (
                              <span>{check.inconsistent_candles} invalid candles</span>
                            )}
                            {key === 'outliers' && (
                              <span>
                                {check.count} outliers ({check.percentage}%)
                              </span>
                            )}
                            {key === 'volume_anomalies' && (
                              <span>{check.zero_volume_candles} zero-volume</span>
                            )}
                            {key === 'data_gaps' && (
                              <span>{check.gap_count} gaps detected</span>
                            )}
                          </div>
                        </div>
                      ))}
                  </div>

                  {/* Issues List */}
                  {quality.issues && quality.issues.length > 0 && (
                    <div className="mt-6">
                      <h3 className="text-sm font-semibold text-dark-300 mb-3">Issues Found</h3>
                      <div className="space-y-2">
                        {quality.issues.map((issue: any, i: number) => (
                          <div
                            key={i}
                            className={cn(
                              'flex items-center gap-3 px-4 py-2 rounded-lg border',
                              getSeverityColor(issue.severity)
                            )}
                          >
                            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                            <span className="text-sm">{issue.message}</span>
                            <span className="ml-auto text-xs opacity-70 capitalize">
                              {issue.severity}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Distributions */}
          {distributions?.distributions && (
            <div className="bg-dark-900 rounded-lg border border-dark-700">
              <button
                onClick={() => toggleSection('distributions')}
                className="w-full p-6 flex items-center justify-between hover:bg-dark-800/50 transition-colors"
              >
                <div className="flex items-center gap-4">
                  <BarChart3 className="w-6 h-6 text-primary-500" />
                  <div className="text-left">
                    <h2 className="text-xl font-semibold text-dark-50">Distribution Analysis</h2>
                    <p className="text-sm text-dark-400">
                      Statistical summaries for OHLCV and derived features
                    </p>
                  </div>
                </div>
                {expandedSections.has('distributions') ? (
                  <ChevronUp className="w-5 h-5 text-dark-400" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-dark-400" />
                )}
              </button>

              {expandedSections.has('distributions') && (
                <div className="px-6 pb-6 border-t border-dark-800">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
                    {Object.entries(distributions.distributions).map(
                      ([feature, stats]: [string, any]) => (
                        <div
                          key={feature}
                          className="bg-dark-800 rounded-lg p-4 border border-dark-700"
                        >
                          <h4 className="font-semibold text-dark-200 capitalize mb-3">
                            {feature}
                          </h4>
                          <div className="grid grid-cols-2 gap-2 text-xs">
                            <div>
                              <span className="text-dark-500">Mean</span>
                              <p className="font-mono text-dark-200">
                                {stats.mean.toFixed(4)}
                              </p>
                            </div>
                            <div>
                              <span className="text-dark-500">Std</span>
                              <p className="font-mono text-dark-200">
                                {stats.std.toFixed(4)}
                              </p>
                            </div>
                            <div>
                              <span className="text-dark-500">Min</span>
                              <p className="font-mono text-dark-200">
                                {stats.min.toFixed(4)}
                              </p>
                            </div>
                            <div>
                              <span className="text-dark-500">Max</span>
                              <p className="font-mono text-dark-200">
                                {stats.max.toFixed(4)}
                              </p>
                            </div>
                            <div>
                              <span className="text-dark-500">Skew</span>
                              <p
                                className={cn(
                                  'font-mono',
                                  Math.abs(stats.skewness) > 1
                                    ? 'text-warning-400'
                                    : 'text-dark-200'
                                )}
                              >
                                {stats.skewness.toFixed(2)}
                              </p>
                            </div>
                            <div>
                              <span className="text-dark-500">Kurt</span>
                              <p
                                className={cn(
                                  'font-mono',
                                  Math.abs(stats.kurtosis) > 3
                                    ? 'text-warning-400'
                                    : 'text-dark-200'
                                )}
                              >
                                {stats.kurtosis.toFixed(2)}
                              </p>
                            </div>
                          </div>
                          {stats.histogram && (
                            <Histogram data={stats.histogram} label={feature} />
                          )}
                        </div>
                      )
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Correlations */}
          {correlations && (
            <div className="bg-dark-900 rounded-lg border border-dark-700">
              <button
                onClick={() => toggleSection('correlations')}
                className="w-full p-6 flex items-center justify-between hover:bg-dark-800/50 transition-colors"
              >
                <div className="flex items-center gap-4">
                  <Activity className="w-6 h-6 text-primary-500" />
                  <div className="text-left">
                    <h2 className="text-xl font-semibold text-dark-50">Correlation Matrix</h2>
                    <p className="text-sm text-dark-400">
                      Feature relationships and redundancy detection
                    </p>
                  </div>
                </div>
                {expandedSections.has('correlations') ? (
                  <ChevronUp className="w-5 h-5 text-dark-400" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-dark-400" />
                )}
              </button>

              {expandedSections.has('correlations') && (
                <div className="px-6 pb-6 border-t border-dark-800">
                  <div className="mt-6">
                    {correlations.features && correlations.matrix && (
                      <CorrelationHeatmap
                        features={correlations.features}
                        matrix={correlations.matrix}
                      />
                    )}

                    {/* High Correlations List */}
                    {correlations.high_correlations &&
                      correlations.high_correlations.length > 0 && (
                        <div className="mt-6">
                          <h3 className="text-sm font-semibold text-dark-300 mb-3">
                            Highly Correlated Pairs (|r| &gt; 0.8)
                          </h3>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                            {correlations.high_correlations.map(
                              (pair: any, i: number) => (
                                <div
                                  key={i}
                                  className="flex items-center justify-between bg-dark-800 rounded-lg px-4 py-2 border border-dark-700"
                                >
                                  <span className="text-sm text-dark-300">
                                    {pair.feature_1}{' '}
                                    <span className="text-dark-500">↔</span>{' '}
                                    {pair.feature_2}
                                  </span>
                                  <span
                                    className={cn(
                                      'font-mono text-sm',
                                      pair.correlation > 0
                                        ? 'text-success-400'
                                        : 'text-danger-400'
                                    )}
                                  >
                                    {pair.correlation.toFixed(3)}
                                  </span>
                                </div>
                              )
                            )}
                          </div>
                        </div>
                      )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Recommendations */}
          {recommendations.length > 0 && (
            <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
              <div className="flex items-center gap-4 mb-6">
                <TrendingUp className="w-6 h-6 text-primary-500" />
                <div>
                  <h2 className="text-xl font-semibold text-dark-50">Recommendations</h2>
                  <p className="text-sm text-dark-400">
                    Actionable insights based on the analysis
                  </p>
                </div>
              </div>

              <div className="space-y-3">
                {recommendations.map((rec: any, i: number) => (
                  <div
                    key={i}
                    className={cn(
                      'flex items-start gap-4 p-4 rounded-lg border',
                      rec.priority === 'high' &&
                        'bg-danger-500/10 border-danger-500/30',
                      rec.priority === 'medium' &&
                        'bg-warning-500/10 border-warning-500/30',
                      rec.priority === 'low' && 'bg-dark-800 border-dark-700'
                    )}
                  >
                    <div
                      className={cn(
                        'px-2 py-1 rounded text-xs font-medium uppercase',
                        rec.priority === 'high' && 'bg-danger-500/20 text-danger-400',
                        rec.priority === 'medium' &&
                          'bg-warning-500/20 text-warning-400',
                        rec.priority === 'low' && 'bg-dark-700 text-dark-300'
                      )}
                    >
                      {rec.priority}
                    </div>
                    <div className="flex-1">
                      <span className="text-xs text-dark-500 uppercase">
                        {rec.category}
                      </span>
                      <p className="text-dark-200">{rec.action}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};
