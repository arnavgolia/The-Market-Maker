/**
 * Execution Latency Histogram
 * 
 * Gemini recommendation: "Don't just show 'Avg Latency.' Show the tail.
 * '95% filled in <100ms, but 5% took >2s.' That's where you die."
 * 
 * Shows:
 * - Distribution of fill latencies across buckets
 * - P95, P99 latency metrics
 * - Visual histogram with color coding
 * - Warnings for slow fills
 */

import { useMemo } from 'react';
import { cn } from '@/lib/utils';

export interface Trade {
  order_id: string;
  symbol: string;
  submit_time: number;    // Timestamp (ms) when order submitted
  fill_time: number;      // Timestamp (ms) when order filled
  qty: number;
  price: number;
}

interface LatencyHistogramProps {
  trades: Trade[];
  className?: string;
}

export function LatencyHistogram({ trades, className }: LatencyHistogramProps) {
  const { buckets, p50, p95, p99, avg } = useMemo(() => {
    if (trades.length === 0) {
      return {
        buckets: { '<50ms': 0, '50-100ms': 0, '100-500ms': 0, '500ms-1s': 0, '>1s': 0 },
        p50: 0,
        p95: 0,
        p99: 0,
        avg: 0,
      };
    }

    // Calculate latencies
    const latencies = trades
      .map(t => t.fill_time - t.submit_time)
      .filter(l => l > 0)  // Filter out invalid latencies
      .sort((a, b) => a - b);

    if (latencies.length === 0) {
      return {
        buckets: { '<50ms': 0, '50-100ms': 0, '100-500ms': 0, '500ms-1s': 0, '>1s': 0 },
        p50: 0,
        p95: 0,
        p99: 0,
        avg: 0,
      };
    }

    // Bucket latencies
    const b: Record<string, number> = {
      '<50ms': 0,
      '50-100ms': 0,
      '100-500ms': 0,
      '500ms-1s': 0,
      '>1s': 0,
    };

    latencies.forEach(l => {
      if (l < 50) b['<50ms']++;
      else if (l < 100) b['50-100ms']++;
      else if (l < 500) b['100-500ms']++;
      else if (l < 1000) b['500ms-1s']++;
      else b['>1s']++;
    });

    // Calculate percentiles
    const p50Idx = Math.floor(latencies.length * 0.50);
    const p95Idx = Math.floor(latencies.length * 0.95);
    const p99Idx = Math.floor(latencies.length * 0.99);
    const avgLatency = latencies.reduce((sum, l) => sum + l, 0) / latencies.length;

    return {
      buckets: b,
      p50: latencies[p50Idx] ?? 0,
      p95: latencies[p95Idx] ?? 0,
      p99: latencies[p99Idx] ?? 0,
      avg: avgLatency,
    };
  }, [trades]);

  const maxCount = Math.max(...Object.values(buckets));
  const p95Warning = p95 > 500;
  const p99Critical = p99 > 2000;

  return (
    <div className={cn('p-6 rounded-lg bg-white', className)}>
      <h3 className="text-lg font-semibold mb-4">Execution Latency Distribution</h3>

      {trades.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          No trades yet
        </div>
      ) : (
        <>
          {/* Histogram */}
          <div className="mb-6">
            <div className="flex gap-2 h-32 items-end">
              {Object.entries(buckets).map(([label, count]) => {
                const heightPct = maxCount > 0 ? (count / maxCount) * 100 : 0;
                const isSlow = label === '>1s';
                const isCaution = label === '500ms-1s';

                return (
                  <div key={label} className="flex-1 flex flex-col items-center">
                    <div 
                      className={cn(
                        'w-full rounded transition-all',
                        isSlow ? 'bg-red-500' : isCaution ? 'bg-yellow-500' : 'bg-blue-500'
                      )}
                      style={{ height: `${heightPct}%` }}
                      title={`${count} trades (${((count / trades.length) * 100).toFixed(1)}%)`}
                    />
                    <span className="text-xs text-gray-600 mt-2 text-center">
                      {label}
                    </span>
                    <span className="text-xs font-bold text-gray-800">
                      {count}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Percentile Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <StatCard label="P50 (Median)" value={`${p50.toFixed(0)}ms`} color="neutral" />
            <StatCard label="P95" value={`${p95.toFixed(0)}ms`} color={p95Warning ? 'warning' : 'neutral'} />
            <StatCard label="P99" value={`${p99.toFixed(0)}ms`} color={p99Critical ? 'danger' : 'neutral'} />
            <StatCard label="Average" value={`${avg.toFixed(0)}ms`} color="neutral" />
          </div>

          {/* Warnings */}
          {p99Critical && (
            <div className="p-4 bg-red-50 border border-red-200 rounded mb-4">
              <p className="text-sm font-medium text-red-800">
                🔴 Critical: P99 Latency &gt;2s
              </p>
              <p className="text-sm text-red-700 mt-1">
                1% of fills are taking over 2 seconds. This is where alpha dies.
                Check network connectivity, broker API health, and order types.
              </p>
            </div>
          )}

          {p95Warning && !p99Critical && (
            <div className="p-4 bg-yellow-50 border border-yellow-200 rounded mb-4">
              <p className="text-sm font-medium text-yellow-800">
                ⚠️ Warning: P95 Latency &gt;500ms
              </p>
              <p className="text-sm text-yellow-700 mt-1">
                5% of fills are taking over 500ms. Monitor execution quality
                and consider reducing order sizes or switching brokers for faster fills.
              </p>
            </div>
          )}

          {!p95Warning && !p99Critical && (
            <div className="p-3 bg-green-50 border border-green-200 rounded">
              <p className="text-sm text-green-700">
                ✅ Execution latency is healthy. 95% of fills in &lt;{p95.toFixed(0)}ms.
              </p>
            </div>
          )}

          {/* Trade Count */}
          <div className="text-center text-xs text-gray-500 mt-4">
            Based on {trades.length} trade{trades.length !== 1 ? 's' : ''}
          </div>
        </>
      )}
    </div>
  );
}

interface StatCardProps {
  label: string;
  value: string;
  color?: 'neutral' | 'warning' | 'danger';
}

function StatCard({ label, value, color = 'neutral' }: StatCardProps) {
  const bgColors = {
    neutral: 'bg-gray-50',
    warning: 'bg-yellow-50',
    danger: 'bg-red-50',
  };

  return (
    <div className={cn('p-3 rounded border', bgColors[color])}>
      <div className="text-xs text-gray-600 mb-1">{label}</div>
      <div className="text-xl font-bold font-mono">{value}</div>
    </div>
  );
}
