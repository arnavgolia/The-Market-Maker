/**
 * Benchmark Attribution Panel
 * 
 * Critical feature from Gemini review:
 * "+2% return means nothing if SPY is +5%. Users need to know if they're just levered beta."
 * 
 * Shows:
 * - Beta to SPY (rolling 60-day)
 * - Jensen's Alpha (excess return after adjusting for market risk)
 * - Information Ratio (alpha per unit of tracking error)
 * - Visual comparison to benchmark
 */

import { cn } from '@/lib/utils';
import { formatPercent } from '@/lib/utils';

export interface BenchmarkAttribution {
  portfolioReturn: number;            // Your return
  benchmarkReturn: number;            // SPY return
  beta: number;                       // Rolling 60-day beta to SPY
  expectedReturn: number;             // beta * benchmarkReturn
  alpha: number;                      // portfolioReturn - expectedReturn (Jensen's Alpha)
  trackingError: number;              // Std dev of (portfolio - benchmark) returns
  informationRatio: number;           // alpha / trackingError
}

interface BenchmarkPanelProps {
  attribution: BenchmarkAttribution;
  className?: string;
}

export function BenchmarkPanel({ attribution, className }: BenchmarkPanelProps) {
  const alphaPositive = attribution.alpha > 0;
  const irGood = Math.abs(attribution.informationRatio) > 0.5;

  return (
    <div className={cn('p-6 rounded-lg bg-white', className)}>
      <h3 className="text-lg font-semibold mb-4">Benchmark Attribution (vs SPY)</h3>

      {/* Visual comparison bars */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <span className="w-28 text-sm text-gray-600">Your Return</span>
          <div className="flex-1 h-8 bg-gray-100 rounded relative">
            <div
              className={cn(
                'h-full rounded transition-all',
                alphaPositive ? 'bg-green-500' : 'bg-red-500'
              )}
              style={{
                width: `${Math.min(Math.abs(attribution.portfolioReturn) * 200, 100)}%`
              }}
            />
            <span className="absolute right-2 top-1 text-sm font-mono font-bold text-gray-700">
              {formatPercent(attribution.portfolioReturn)}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="w-28 text-sm text-gray-600">SPY Return</span>
          <div className="flex-1 h-8 bg-gray-100 rounded relative">
            <div
              className="h-full bg-blue-500 rounded transition-all"
              style={{
                width: `${Math.min(Math.abs(attribution.benchmarkReturn) * 200, 100)}%`
              }}
            />
            <span className="absolute right-2 top-1 text-sm font-mono font-bold text-gray-700">
              {formatPercent(attribution.benchmarkReturn)}
            </span>
          </div>
        </div>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        <MetricCard
          label="Beta"
          value={attribution.beta.toFixed(2)}
          tooltip="Portfolio sensitivity to SPY. 1.0 = moves with market, >1.0 = more volatile"
          color={attribution.beta > 1.5 ? 'warning' : 'neutral'}
        />
        <MetricCard
          label="Jensen's Alpha"
          value={formatPercent(attribution.alpha)}
          tooltip="Excess return after adjusting for market risk. Positive = outperformance"
          color={alphaPositive ? 'success' : 'danger'}
        />
        <MetricCard
          label="Information Ratio"
          value={attribution.informationRatio.toFixed(2)}
          tooltip="Alpha per unit of tracking error. >0.5 is good, >1.0 is excellent"
          color={irGood ? 'success' : 'neutral'}
        />
      </div>

      {/* Breakdown */}
      <div className="p-4 bg-gray-50 rounded mb-4">
        <div className="text-sm space-y-2">
          <div className="flex justify-between">
            <span className="text-gray-600">Expected Return (based on beta):</span>
            <span className="font-mono font-medium">{formatPercent(attribution.expectedReturn)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">Actual Return:</span>
            <span className="font-mono font-medium">{formatPercent(attribution.portfolioReturn)}</span>
          </div>
          <div className="flex justify-between border-t pt-2">
            <span className="text-gray-600 font-semibold">Alpha (Actual - Expected):</span>
            <span className={cn(
              'font-mono font-bold',
              alphaPositive ? 'text-green-600' : 'text-red-600'
            )}>
              {formatPercent(attribution.alpha)}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">Tracking Error:</span>
            <span className="font-mono text-sm">{formatPercent(attribution.trackingError)}</span>
          </div>
        </div>
      </div>

      {/* Interpretation */}
      {!alphaPositive && (
        <div className="p-4 bg-red-50 border border-red-200 rounded">
          <p className="text-sm font-medium text-red-800 mb-2">
            🔴 Negative Alpha
          </p>
          <p className="text-sm text-red-700">
            Your risk-adjusted return is worse than holding SPY.
            After accounting for your beta of {attribution.beta.toFixed(2)},
            you are underperforming the market by {formatPercent(Math.abs(attribution.alpha))}.
          </p>
          <p className="text-sm text-red-700 mt-2">
            <strong>Implication:</strong> You are paying for complexity (trading, monitoring, risk)
            without generating excess returns. Consider reducing activity or holding the benchmark.
          </p>
        </div>
      )}

      {alphaPositive && irGood && (
        <div className="p-4 bg-green-50 border border-green-200 rounded">
          <p className="text-sm font-medium text-green-800 mb-2">
            ✅ Positive Alpha & Strong IR
          </p>
          <p className="text-sm text-green-700">
            You are generating {formatPercent(attribution.alpha)} of excess return
            with an Information Ratio of {attribution.informationRatio.toFixed(2)}.
            This indicates consistent, risk-adjusted outperformance.
          </p>
        </div>
      )}

      {alphaPositive && !irGood && (
        <div className="p-4 bg-yellow-50 border border-yellow-200 rounded">
          <p className="text-sm font-medium text-yellow-800 mb-2">
            ⚠️ Positive Alpha, Low Consistency
          </p>
          <p className="text-sm text-yellow-700">
            While you have positive alpha ({formatPercent(attribution.alpha)}),
            your Information Ratio of {attribution.informationRatio.toFixed(2)} suggests
            the outperformance is inconsistent. High tracking error indicates
            you are taking significant active risk.
          </p>
        </div>
      )}
    </div>
  );
}

interface MetricCardProps {
  label: string;
  value: string;
  tooltip: string;
  color?: 'neutral' | 'success' | 'warning' | 'danger';
}

function MetricCard({ label, value, tooltip, color = 'neutral' }: MetricCardProps) {
  const colorClasses = {
    neutral: 'bg-gray-50 border-gray-200',
    success: 'bg-green-50 border-green-200',
    warning: 'bg-yellow-50 border-yellow-200',
    danger: 'bg-red-50 border-red-200',
  };

  return (
    <div className={cn('p-4 rounded border', colorClasses[color])} title={tooltip}>
      <div className="text-sm text-gray-600 mb-1">{label}</div>
      <div className="text-3xl font-bold font-mono">{value}</div>
      <div className="text-xs text-gray-500 mt-2">{tooltip}</div>
    </div>
  );
}

/**
 * Calculate benchmark attribution metrics.
 * 
 * @param portfolioReturns - Array of daily portfolio returns
 * @param benchmarkReturns - Array of daily SPY returns (aligned with portfolio)
 * @returns BenchmarkAttribution metrics
 */
export function calculateBenchmarkAttribution(
  portfolioReturns: number[],
  benchmarkReturns: number[]
): BenchmarkAttribution {
  if (portfolioReturns.length !== benchmarkReturns.length || portfolioReturns.length === 0) {
    throw new Error('Portfolio and benchmark returns must have equal length');
  }

  // Calculate cumulative returns
  const portfolioReturn = portfolioReturns.reduce((cum, r) => cum * (1 + r), 1) - 1;
  const benchmarkReturn = benchmarkReturns.reduce((cum, r) => cum * (1 + r), 1) - 1;

  // Calculate beta (covariance / variance)
  const portfolioMean = portfolioReturns.reduce((sum, r) => sum + r, 0) / portfolioReturns.length;
  const benchmarkMean = benchmarkReturns.reduce((sum, r) => sum + r, 0) / benchmarkReturns.length;

  let covariance = 0;
  let benchmarkVariance = 0;

  for (let i = 0; i < portfolioReturns.length; i++) {
    const portDev = portfolioReturns[i] - portfolioMean;
    const benchDev = benchmarkReturns[i] - benchmarkMean;
    covariance += portDev * benchDev;
    benchmarkVariance += benchDev * benchDev;
  }

  covariance /= portfolioReturns.length;
  benchmarkVariance /= benchmarkReturns.length;

  const beta = benchmarkVariance !== 0 ? covariance / benchmarkVariance : 1.0;

  // Calculate alpha (Jensen's Alpha)
  const expectedReturn = beta * benchmarkReturn;
  const alpha = portfolioReturn - expectedReturn;

  // Calculate tracking error (std dev of excess returns)
  const excessReturns = portfolioReturns.map((r, i) => r - benchmarkReturns[i]);
  const excessMean = excessReturns.reduce((sum, r) => sum + r, 0) / excessReturns.length;
  const trackingVariance = excessReturns.reduce((sum, r) => sum + Math.pow(r - excessMean, 2), 0) / excessReturns.length;
  const trackingError = Math.sqrt(trackingVariance);

  // Calculate information ratio
  const informationRatio = trackingError !== 0 ? alpha / trackingError : 0;

  return {
    portfolioReturn,
    benchmarkReturn,
    beta,
    expectedReturn,
    alpha,
    trackingError,
    informationRatio,
  };
}
