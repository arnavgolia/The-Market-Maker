/**
 * Cash Drag Analysis Panel
 * 
 * Critical feature from Gemini review:
 * "44% cash in a paper account looks fine. In reality, it destroys Sharpe."
 * 
 * Shows:
 * - Current cash %
 * - Cash yield (sweep rate or 0%)
 * - Performance drag from uninvested capital
 * - Opportunity cost vs benchmark
 */

import { cn } from '@/lib/utils';
import { formatPercent } from '@/lib/utils';

export interface CashDragMetrics {
  cashPct: number;                    // Current cash %
  cashYield: number;                  // Assumed yield (0% or sweep rate)
  performanceDrag: number;            // Lost return from holding cash
  opportunityCost: number;            // Return lost vs benchmark
  uninvestedDays: number;             // Days where cash > 20%
}

interface CashDragPanelProps {
  metrics: CashDragMetrics;
  className?: string;
}

export function CashDragPanel({ metrics, className }: CashDragPanelProps) {
  const isProblematic = metrics.cashPct > 0.25; // >25% cash is a warning
  const isCritical = metrics.cashPct > 0.40;     // >40% cash is critical

  return (
    <div 
      className={cn(
        'p-6 rounded-lg bg-white',
        isProblematic && 'border-2 border-yellow-500',
        isCritical && 'border-2 border-red-500',
        className
      )}
    >
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">Cash Drag Analysis</h3>
        {isProblematic && (
          <span className={cn(
            'px-2 py-1 rounded text-xs font-medium',
            isCritical ? 'bg-red-100 text-red-700' : 'bg-yellow-100 text-yellow-700'
          )}>
            {isCritical ? '⚠️ CRITICAL' : '⚠️ WARNING'}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <MetricCard
          label="Cash %"
          value={`${(metrics.cashPct * 100).toFixed(1)}%`}
          tooltip="Current percentage of portfolio in cash"
          color={metrics.cashPct > 0.25 ? 'warning' : 'neutral'}
        />
        <MetricCard
          label="Cash Yield"
          value={`${(metrics.cashYield * 100).toFixed(2)}%`}
          tooltip="Annual yield on cash (sweep account or 0%)"
          color="neutral"
        />
        <MetricCard
          label="Performance Drag"
          value={`${(metrics.performanceDrag * 100).toFixed(2)}%`}
          tooltip="Return lost due to holding cash instead of being fully invested"
          color={Math.abs(metrics.performanceDrag) > 0.01 ? 'danger' : 'neutral'}
        />
        <MetricCard
          label="Opportunity Cost"
          value={`${(metrics.opportunityCost * 100).toFixed(2)}%`}
          tooltip="Return you would have earned if cash matched benchmark (SPY)"
          color={Math.abs(metrics.opportunityCost) > 0.01 ? 'danger' : 'neutral'}
        />
      </div>

      {metrics.uninvestedDays > 0 && (
        <div className="mb-4 p-3 bg-gray-50 rounded">
          <div className="text-sm text-gray-600">
            Portfolio has held &gt;20% cash for{' '}
            <span className="font-semibold">{metrics.uninvestedDays} days</span>
          </div>
        </div>
      )}

      {isProblematic && (
        <div className={cn(
          'p-4 rounded',
          isCritical ? 'bg-red-50 border border-red-200' : 'bg-yellow-50 border border-yellow-200'
        )}>
          <p className={cn(
            'text-sm font-medium mb-2',
            isCritical ? 'text-red-800' : 'text-yellow-800'
          )}>
            {isCritical ? '🔴 Critical Cash Allocation' : '⚠️ High Cash Allocation'}
          </p>
          <p className={cn(
            'text-sm',
            isCritical ? 'text-red-700' : 'text-yellow-700'
          )}>
            {(metrics.cashPct * 100).toFixed(0)}% of your portfolio is in cash,
            which is dragging down performance. Consider:
          </p>
          <ul className={cn(
            'text-sm mt-2 ml-4 list-disc',
            isCritical ? 'text-red-700' : 'text-yellow-700'
          )}>
            <li>Deploying capital into trading strategies</li>
            <li>Reducing position sizes to increase deployment frequency</li>
            <li>Reviewing strategy signal generation rates</li>
            {metrics.cashYield === 0 && (
              <li>Moving cash to a sweep account (currently earning 0%)</li>
            )}
          </ul>
        </div>
      )}

      {!isProblematic && metrics.cashPct > 0.10 && (
        <div className="p-3 bg-blue-50 border border-blue-200 rounded">
          <p className="text-sm text-blue-700">
            ✓ Cash allocation is within acceptable range ({(metrics.cashPct * 100).toFixed(0)}%).
            Maintains flexibility for new opportunities while staying mostly invested.
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
  color?: 'neutral' | 'warning' | 'danger';
}

function MetricCard({ label, value, tooltip, color = 'neutral' }: MetricCardProps) {
  const colorClasses = {
    neutral: 'bg-gray-50',
    warning: 'bg-yellow-50',
    danger: 'bg-red-50',
  };

  return (
    <div className={cn('p-4 rounded border', colorClasses[color])} title={tooltip}>
      <div className="text-sm text-gray-600 mb-1">{label}</div>
      <div className="text-2xl font-bold font-mono">{value}</div>
      <div className="text-xs text-gray-500 mt-1">{tooltip}</div>
    </div>
  );
}

/**
 * Calculate cash drag metrics from portfolio data.
 */
export function calculateCashDragMetrics(
  cash: number,
  equity: number,
  portfolioReturn: number,
  benchmarkReturn: number,
  cashYieldRate: number = 0,
  equityHistory?: Array<{ timestamp: number; cash: number; equity: number }>
): CashDragMetrics {
  const cashPct = cash / equity;

  // Performance drag: What we would have earned if fully invested
  const fullyInvestedReturn = portfolioReturn / (1 - cashPct);
  const performanceDrag = portfolioReturn - fullyInvestedReturn;

  // Opportunity cost: What we would have earned at benchmark return
  const opportunityCost = cashPct * benchmarkReturn;

  // Count days with >20% cash
  let uninvestedDays = 0;
  if (equityHistory) {
    uninvestedDays = equityHistory.filter(
      point => (point.cash / point.equity) > 0.20
    ).length;
  }

  return {
    cashPct,
    cashYield: cashYieldRate,
    performanceDrag,
    opportunityCost,
    uninvestedDays,
  };
}
