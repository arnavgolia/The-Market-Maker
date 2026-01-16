/**
 * Equity Curve Chart Component
 * 
 * Uses ring buffer for memory-safe data storage.
 * Renders in Exchange Time to prevent midnight bug.
 * Throttled updates at 10fps to prevent render overload.
 */

import { useEffect, useRef, useState } from 'react';
import { EquityRingBuffer, type EquityPoint } from '@/lib/ring-buffer';
import { useThrottledUpdates } from '@/hooks/useThrottledUpdates';
import { formatExchangeTime } from '@/lib/time';
import { formatPrice, formatPercent } from '@/lib/utils';

interface EquityCurveProps {
  initialEquity: number;
  className?: string;
}

export function EquityCurve({ initialEquity, className }: EquityCurveProps) {
  const bufferRef = useRef(new EquityRingBuffer(5000));
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [latestPoint, setLatestPoint] = useState<EquityPoint | null>(null);
  
  // Throttle render updates to 10fps
  const throttledPoint = useThrottledUpdates(latestPoint, { maxFps: 10 });

  // Fetch equity data from API
  useEffect(() => {
    const fetchEquity = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/v1/portfolio/equity');
        const data = await response.json();
        
        if (data.equity_history) {
          // Load historical data into buffer
          for (const point of data.equity_history) {
            bufferRef.current.push({
              timestamp: new Date(point.timestamp).getTime(),
              equity: point.equity,
              cash: point.cash,
              positions_value: point.positions_value,
            });
          }
          
          if (data.equity_history.length > 0) {
            const latest = data.equity_history[data.equity_history.length - 1];
            setLatestPoint({
              timestamp: new Date(latest.timestamp).getTime(),
              equity: latest.equity,
              cash: latest.cash,
              positions_value: latest.positions_value,
            });
          }
        }
      } catch (error) {
        console.error('Failed to fetch equity:', error);
      }
    };

    // Initial fetch
    fetchEquity();

    // Polling every 2 seconds (will be replaced by WebSocket in full implementation)
    const interval = setInterval(fetchEquity, 2000);

    return () => clearInterval(interval);
  }, []);

  // Render chart when data updates (throttled)
  useEffect(() => {
    if (!throttledPoint || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas size
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    // Clear canvas
    ctx.clearRect(0, 0, rect.width, rect.height);

    // Get data from ring buffer
    const data = bufferRef.current.toArray();
    if (data.length < 2) return;

    // Calculate scales
    const padding = { top: 20, right: 60, bottom: 30, left: 10 };
    const chartWidth = rect.width - padding.left - padding.right;
    const chartHeight = rect.height - padding.top - padding.bottom;

    const minEquity = Math.min(...data.map(d => d.equity));
    const maxEquity = Math.max(...data.map(d => d.equity));
    const equityRange = maxEquity - minEquity;

    const minTime = data[0].timestamp;
    const maxTime = data[data.length - 1].timestamp;
    const timeRange = maxTime - minTime;

    // Draw grid lines
    ctx.strokeStyle = '#e5e7eb';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartHeight / 4) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(padding.left + chartWidth, y);
      ctx.stroke();

      // Y-axis labels
      const value = maxEquity - (equityRange / 4) * i;
      ctx.fillStyle = '#6b7280';
      ctx.font = '10px monospace';
      ctx.textAlign = 'left';
      ctx.fillText(`$${value.toFixed(0)}`, padding.left + chartWidth + 5, y + 3);
    }

    // Draw equity line
    ctx.strokeStyle = data[data.length - 1].equity >= initialEquity ? '#10b981' : '#ef4444';
    ctx.lineWidth = 2;
    ctx.beginPath();

    for (let i = 0; i < data.length; i++) {
      const x = padding.left + ((data[i].timestamp - minTime) / timeRange) * chartWidth;
      const y = padding.top + chartHeight - ((data[i].equity - minEquity) / equityRange) * chartHeight;

      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }

    ctx.stroke();

    // Draw initial equity reference line
    if (equityRange > 0) {
      const initialY = padding.top + chartHeight - ((initialEquity - minEquity) / equityRange) * chartHeight;
      ctx.strokeStyle = '#9ca3af';
      ctx.lineWidth = 1;
      ctx.setLineDash([5, 5]);
      ctx.beginPath();
      ctx.moveTo(padding.left, initialY);
      ctx.lineTo(padding.left + chartWidth, initialY);
      ctx.stroke();
      ctx.setLineDash([]);
    }

  }, [throttledPoint, initialEquity]);

  // Calculate metrics
  const currentEquity = latestPoint?.equity ?? initialEquity;
  const totalReturn = ((currentEquity - initialEquity) / initialEquity) * 100;
  const maxDD = bufferRef.current.maxDrawdown() * 100;

  return (
    <div className={className}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">Portfolio Equity</h3>
        <div className="flex gap-4 text-sm">
          <div>
            <span className="text-gray-500">Current: </span>
            <span className="font-mono font-bold">
              ${formatPrice(currentEquity)}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Return: </span>
            <span className={`font-mono font-bold ${totalReturn >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {formatPercent(totalReturn / 100)}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Max DD: </span>
            <span className="font-mono font-bold text-red-500">
              {maxDD.toFixed(2)}%
            </span>
          </div>
        </div>
      </div>
      <canvas
        ref={canvasRef}
        className="w-full h-64 border border-gray-200 rounded"
      />
    </div>
  );
}
