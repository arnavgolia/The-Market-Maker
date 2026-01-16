/**
 * Data Freshness Indicator
 * 
 * Critical feature: Detects upstream feed death.
 * 
 * Scenario: WebSocket to backend is connected (green),
 * but upstream Alpaca feed died. User sees "Live" but data is 5 minutes old.
 * 
 * Solution: Compare last_tick_time to client system time during market hours.
 * If data age > 60s during market hours, force "STALE" even if WS connected.
 */

import { useState, useEffect } from 'react';
import { useIsMarketHours } from '@/hooks/useMarketHours';
import { cn } from '@/lib/utils';

export type FreshnessStatus = 'live' | 'delayed' | 'stale' | 'market_closed';

export interface FreshnessState {
  status: FreshnessStatus;
  lastTickTime: Date | null;
  ageSeconds: number;
  message: string;
}

interface DataFreshnessProps {
  channel: string;
  lastUpdate: Date | null;
  className?: string;
}

/**
 * Hook to calculate data freshness.
 */
export function useDataFreshness(lastUpdate: Date | null): FreshnessState {
  const [ageSeconds, setAgeSeconds] = useState(0);
  const isMarketHours = useIsMarketHours();

  // Update age every second
  useEffect(() => {
    if (!lastUpdate) {
      setAgeSeconds(Infinity);
      return;
    }

    const interval = setInterval(() => {
      const age = (Date.now() - lastUpdate.getTime()) / 1000;
      setAgeSeconds(age);
    }, 1000);

    // Initial calculation
    const age = (Date.now() - lastUpdate.getTime()) / 1000;
    setAgeSeconds(age);

    return () => clearInterval(interval);
  }, [lastUpdate]);

  // Determine status
  let status: FreshnessStatus;
  let message: string;

  if (!lastUpdate) {
    status = 'stale';
    message = 'No data';
  } else if (!isMarketHours) {
    status = 'market_closed';
    message = 'Market closed';
  } else if (ageSeconds < 5) {
    status = 'live';
    message = 'Live';
  } else if (ageSeconds < 60) {
    status = 'delayed';
    message = `${Math.round(ageSeconds)}s ago`;
  } else {
    // CRITICAL: Data is stale during market hours
    status = 'stale';
    message = ageSeconds < 300 
      ? `${Math.round(ageSeconds / 60)}m ago` 
      : 'STALE';
  }

  return {
    status,
    lastTickTime: lastUpdate,
    ageSeconds,
    message,
  };
}

/**
 * Visual indicator component.
 */
export function DataFreshnessIndicator({ 
  channel, 
  lastUpdate,
  className 
}: DataFreshnessProps) {
  const { status, message, ageSeconds } = useDataFreshness(lastUpdate);

  const config = {
    live: {
      color: 'bg-green-500',
      textColor: 'text-white',
      label: 'LIVE',
      pulse: true,
      icon: '●',
    },
    delayed: {
      color: 'bg-yellow-500',
      textColor: 'text-black',
      label: message,
      pulse: false,
      icon: '◐',
    },
    stale: {
      color: 'bg-red-500',
      textColor: 'text-white',
      label: message,
      pulse: true,  // Pulsing red = danger
      icon: '○',
    },
    market_closed: {
      color: 'bg-gray-500',
      textColor: 'text-white',
      label: 'CLOSED',
      pulse: false,
      icon: '■',
    },
  }[status];

  return (
    <div
      className={cn(
        'inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-mono',
        config.color,
        config.textColor,
        config.pulse && 'animate-pulse',
        className
      )}
      title={`${channel}: Last update ${ageSeconds.toFixed(1)}s ago`}
    >
      <span className="text-[10px]">{config.icon}</span>
      <span>{config.label}</span>
    </div>
  );
}

/**
 * Detailed freshness display with tooltip.
 */
export function DataFreshnessDetail({
  channel,
  lastUpdate,
}: {
  channel: string;
  lastUpdate: Date | null;
}) {
  const { status, message, ageSeconds, lastTickTime } = useDataFreshness(lastUpdate);

  const statusEmoji = {
    live: '🟢',
    delayed: '🟡',
    stale: '🔴',
    market_closed: '⚫',
  }[status];

  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-lg">{statusEmoji}</span>
      <div>
        <div className="font-medium">
          {channel} - {message}
        </div>
        {lastTickTime && (
          <div className="text-xs text-gray-500">
            Last update: {lastTickTime.toLocaleTimeString()}
          </div>
        )}
        {status === 'stale' && ageSeconds > 60 && (
          <div className="text-xs text-red-600 font-medium">
            ⚠️ Data may be stale. Check connection.
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Banner alert for stale data.
 */
export function StalenessAlert({
  channels,
}: {
  channels: Array<{ name: string; lastUpdate: Date | null }>;
}) {
  const isMarketHours = useIsMarketHours();
  
  const staleChannels = channels.filter(channel => {
    if (!isMarketHours || !channel.lastUpdate) return false;
    const ageSeconds = (Date.now() - channel.lastUpdate.getTime()) / 1000;
    return ageSeconds > 60;  // Stale if >60s during market hours
  });

  if (staleChannels.length === 0) return null;

  return (
    <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-4">
      <div className="flex items-center">
        <div className="flex-shrink-0">
          <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
        </div>
        <div className="ml-3">
          <p className="text-sm font-medium text-red-800">
            Data may be outdated
          </p>
          <p className="text-sm text-red-700 mt-1">
            {staleChannels.length} data source{staleChannels.length > 1 ? 's' : ''} not updating:
            {' '}
            {staleChannels.map(c => c.name).join(', ')}.
            Last update: &gt;1 minute ago.
          </p>
        </div>
      </div>
    </div>
  );
}
