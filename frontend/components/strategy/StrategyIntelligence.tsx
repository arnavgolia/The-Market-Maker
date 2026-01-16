/**
 * Strategy Intelligence View
 * 
 * Addresses Gemini gap: "30-day Sharpe is ambiguous. Daily vs hourly changes the number dramatically."
 * 
 * Shows:
 * - Strategy health with explicit resolution specification
 * - Why strategies are disabled (regime gates)
 * - Performance metrics with clear time periods
 * - Signal strength (not "confidence" to avoid probability misinterpretation)
 */

import { cn } from '@/lib/utils';
import { formatPercent } from '@/lib/utils';

export interface RiskMetricConfig {
  resolution: 'daily' | 'hourly' | '15min';
  window: number;        // Number of periods
  annualizationFactor: number;
}

export const RISK_CONFIGS: Record<string, RiskMetricConfig> = {
  sharpe_daily_30d: {
    resolution: 'daily',
    window: 30,
    annualizationFactor: Math.sqrt(252),  // sqrt(trading days)
  },
  sharpe_hourly_5d: {
    resolution: 'hourly',
    window: 5 * 6.5,     // 5 days * 6.5 market hours
    annualizationFactor: Math.sqrt(252 * 6.5),
  },
  sortino_daily_30d: {
    resolution: 'daily',
    window: 30,
    annualizationFactor: Math.sqrt(252),
  },
};

export interface StrategyMetrics {
  strategy_name: string;
  enabled: boolean;
  disable_reason?: string;
  
  // Performance
  sharpe_30d: number;
  sharpe_config: RiskMetricConfig;
  sortino_30d: number;
  win_rate: number;
  profit_factor: number;
  
  // Activity
  signals_today: number;
  fills_today: number;
  avg_signal_strength: number;  // NOT "confidence"
  
  // Attribution
  pnl_contribution: number;
  trades_count: number;
}

interface StrategyIntelligenceProps {
  strategies: StrategyMetrics[];
  className?: string;
}

export function StrategyIntelligence({ strategies, className }: StrategyIntelligenceProps) {
  const activeStrategies = strategies.filter(s => s.enabled);
  const disabledStrategies = strategies.filter(s => !s.enabled);

  return (
    <div className={cn('space-y-6', className)}>
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Strategy Intelligence</h2>
        <div className="flex gap-2 text-sm">
          <span className="px-3 py-1 rounded bg-green-100 text-green-700 font-medium">
            {activeStrategies.length} Active
          </span>
          <span className="px-3 py-1 rounded bg-gray-100 text-gray-700">
            {disabledStrategies.length} Disabled
          </span>
        </div>
      </div>

      {/* Active Strategies */}
      {activeStrategies.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-lg font-semibold text-green-700">Active Strategies</h3>
          {activeStrategies.map(strategy => (
            <StrategyCard key={strategy.strategy_name} strategy={strategy} />
          ))}
        </div>
      )}

      {/* Disabled Strategies */}
      {disabledStrategies.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-lg font-semibold text-gray-600">Disabled Strategies</h3>
          {disabledStrategies.map(strategy => (
            <StrategyCard key={strategy.strategy_name} strategy={strategy} />
          ))}
        </div>
      )}

      {strategies.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          No strategies configured
        </div>
      )}
    </div>
  );
}

function StrategyCard({ strategy }: { strategy: StrategyMetrics }) {
  const sharpeGood = strategy.sharpe_30d > 1.0;
  const sharpeExcellent = strategy.sharpe_30d > 2.0;
  const winRateGood = strategy.win_rate > 0.5;

  return (
    <div className={cn(
      'p-6 rounded-lg border-2',
      strategy.enabled ? 'bg-white border-green-200' : 'bg-gray-50 border-gray-200'
    )}>
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <h4 className="text-lg font-bold">{strategy.strategy_name}</h4>
          {!strategy.enabled && strategy.disable_reason && (
            <div className="mt-1 flex items-center gap-2">
              <span className="text-sm text-gray-600">
                Disabled:
              </span>
              <span className="text-sm font-medium text-orange-600">
                {strategy.disable_reason}
              </span>
            </div>
          )}
        </div>
        <span className={cn(
          'px-3 py-1 rounded text-xs font-bold',
          strategy.enabled 
            ? 'bg-green-500 text-white' 
            : 'bg-gray-400 text-white'
        )}>
          {strategy.enabled ? 'ACTIVE' : 'DISABLED'}
        </span>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        {/* Sharpe with resolution */}
        <div>
          <div className="text-xs text-gray-500 mb-1">
            Sharpe Ratio
          </div>
          <div className={cn(
            'text-2xl font-bold',
            sharpeExcellent ? 'text-green-600' : sharpeGood ? 'text-blue-600' : 'text-gray-700'
          )}>
            {strategy.sharpe_30d.toFixed(2)}
          </div>
          <div className="text-xs text-gray-400">
            ({strategy.sharpe_config.resolution}, {strategy.sharpe_config.window} periods)
          </div>
        </div>

        {/* Sortino */}
        <div>
          <div className="text-xs text-gray-500 mb-1">
            Sortino Ratio
          </div>
          <div className="text-2xl font-bold text-gray-700">
            {strategy.sortino_30d.toFixed(2)}
          </div>
          <div className="text-xs text-gray-400">
            (downside-risk adjusted)
          </div>
        </div>

        {/* Win Rate */}
        <div>
          <div className="text-xs text-gray-500 mb-1">
            Win Rate
          </div>
          <div className={cn(
            'text-2xl font-bold',
            winRateGood ? 'text-green-600' : 'text-gray-700'
          )}>
            {(strategy.win_rate * 100).toFixed(1)}%
          </div>
          <div className="text-xs text-gray-400">
            ({strategy.fills_today} fills today)
          </div>
        </div>

        {/* Profit Factor */}
        <div>
          <div className="text-xs text-gray-500 mb-1">
            Profit Factor
          </div>
          <div className={cn(
            'text-2xl font-bold',
            strategy.profit_factor > 1.5 ? 'text-green-600' : 'text-gray-700'
          )}>
            {strategy.profit_factor.toFixed(2)}
          </div>
          <div className="text-xs text-gray-400">
            (gross profit / gross loss)
          </div>
        </div>
      </div>

      {/* Activity Bar */}
      <div className="flex items-center gap-4 p-3 bg-gray-50 rounded">
        <div className="flex-1">
          <div className="text-xs text-gray-600 mb-1">Signal Strength (avg)</div>
          <div className="flex items-center gap-2">
            <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
              <div 
                className="h-full bg-blue-500"
                style={{ width: `${strategy.avg_signal_strength * 100}%` }}
              />
            </div>
            <span className="text-sm font-mono font-medium">
              {(strategy.avg_signal_strength * 100).toFixed(0)}%
            </span>
          </div>
        </div>
        <div className="text-center">
          <div className="text-xs text-gray-600">Signals Today</div>
          <div className="text-lg font-bold">{strategy.signals_today}</div>
        </div>
        <div className="text-center">
          <div className="text-xs text-gray-600">P&L Contribution</div>
          <div className={cn(
            'text-lg font-bold',
            strategy.pnl_contribution >= 0 ? 'text-green-600' : 'text-red-600'
          )}>
            {strategy.pnl_contribution >= 0 ? '+' : ''}${strategy.pnl_contribution.toFixed(0)}
          </div>
        </div>
      </div>

      {/* Resolution Explanation */}
      {strategy.enabled && (
        <div className="mt-3 p-2 bg-blue-50 border border-blue-200 rounded text-xs text-blue-700">
          <strong>Note:</strong> Sharpe calculated on {strategy.sharpe_config.resolution} returns
          over {strategy.sharpe_config.window} periods, annualized by √{strategy.sharpe_config.annualizationFactor.toFixed(0)}.
        </div>
      )}
    </div>
  );
}

/**
 * Render Sharpe with resolution specification (standalone component).
 */
export function SharpeDisplay({ 
  value, 
  config 
}: { 
  value: number; 
  config: RiskMetricConfig;
}) {
  return (
    <div>
      <span className="text-2xl font-bold">{value.toFixed(2)}</span>
      <span className="text-xs text-gray-500 ml-2">
        ({config.resolution}, {config.window} periods)
      </span>
    </div>
  );
}
