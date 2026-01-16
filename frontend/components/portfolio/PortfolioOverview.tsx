/**
 * Portfolio Overview Component
 * 
 * Displays account summary, positions, and equity curve.
 * Uses timestamp-based state merging and ring buffers.
 */

import { useEffect } from 'react';
import { usePositionStore } from '@/stores/positionStore';
import { DataFreshnessIndicator } from '@/components/indicators/DataFreshness';
import { EquityCurve } from './EquityCurve';
import { formatPrice, formatPercent } from '@/lib/utils';

interface PortfolioOverviewProps {
  initialEquity?: number;
}

export function PortfolioOverview({ initialEquity = 100000 }: PortfolioOverviewProps) {
  const positions = usePositionStore(state => state.getAllPositions());
  const updatePositions = usePositionStore(state => state.updatePositions);
  const lastUpdate = positions.length > 0 
    ? new Date(positions[0].updated_at) 
    : null;

  // Fetch positions from API
  useEffect(() => {
    const fetchPositions = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/v1/portfolio/positions');
        const data = await response.json();
        
        if (data.positions) {
          updatePositions(data.positions, Date.now());
        }
      } catch (error) {
        console.error('Failed to fetch positions:', error);
      }
    };

    // Initial fetch
    fetchPositions();

    // Polling every 2 seconds
    const interval = setInterval(fetchPositions, 2000);

    return () => clearInterval(interval);
  }, [updatePositions]);

  const totalValue = positions.reduce((sum, pos) => sum + pos.market_value, 0);
  const totalPnL = positions.reduce((sum, pos) => sum + pos.unrealized_pnl, 0);
  const currentEquity = initialEquity + totalPnL;
  const cash = currentEquity - totalValue;

  return (
    <div className="space-y-6">
      {/* Account Summary */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold">Account Overview</h2>
          <DataFreshnessIndicator 
            channel="portfolio" 
            lastUpdate={lastUpdate}
          />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <div className="text-sm text-gray-500">Equity</div>
            <div className="text-2xl font-bold font-mono">
              ${formatPrice(currentEquity)}
            </div>
          </div>

          <div>
            <div className="text-sm text-gray-500">Cash</div>
            <div className="text-xl font-mono">
              ${formatPrice(cash)}
            </div>
            <div className="text-xs text-gray-400">
              {((cash / currentEquity) * 100).toFixed(1)}%
            </div>
          </div>

          <div>
            <div className="text-sm text-gray-500">Positions Value</div>
            <div className="text-xl font-mono">
              ${formatPrice(totalValue)}
            </div>
          </div>

          <div>
            <div className="text-sm text-gray-500">Unrealized P&L</div>
            <div className={`text-xl font-bold font-mono ${totalPnL >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {totalPnL >= 0 ? '+' : ''}${formatPrice(Math.abs(totalPnL))}
            </div>
            <div className={`text-xs ${totalPnL >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {formatPercent(totalPnL / initialEquity)}
            </div>
          </div>
        </div>
      </div>

      {/* Equity Curve */}
      <div className="bg-white rounded-lg shadow p-6">
        <EquityCurve initialEquity={initialEquity} />
      </div>

      {/* Positions Table */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Open Positions</h3>
        
        {positions.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            No open positions
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b text-left text-sm text-gray-500">
                  <th className="pb-2">Symbol</th>
                  <th className="pb-2 text-right">Qty</th>
                  <th className="pb-2 text-right">Avg Price</th>
                  <th className="pb-2 text-right">Market Value</th>
                  <th className="pb-2 text-right">Unrealized P&L</th>
                  <th className="pb-2 text-right">Return %</th>
                </tr>
              </thead>
              <tbody>
                {positions.map(pos => {
                  const returnPct = ((pos.market_value - (pos.qty * pos.avg_price)) / (pos.qty * pos.avg_price)) * 100;
                  
                  return (
                    <tr key={pos.symbol} className="border-b hover:bg-gray-50">
                      <td className="py-3 font-semibold">{pos.symbol}</td>
                      <td className="py-3 text-right font-mono">
                        {pos.side === 'long' ? '+' : '-'}{Math.abs(pos.qty)}
                      </td>
                      <td className="py-3 text-right font-mono">
                        ${formatPrice(pos.avg_price)}
                      </td>
                      <td className="py-3 text-right font-mono">
                        ${formatPrice(pos.market_value)}
                      </td>
                      <td className={`py-3 text-right font-mono font-bold ${pos.unrealized_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                        {pos.unrealized_pnl >= 0 ? '+' : ''}${formatPrice(Math.abs(pos.unrealized_pnl))}
                      </td>
                      <td className={`py-3 text-right font-mono ${returnPct >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                        {returnPct >= 0 ? '+' : ''}{returnPct.toFixed(2)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
