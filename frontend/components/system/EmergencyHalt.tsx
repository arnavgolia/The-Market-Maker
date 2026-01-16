/**
 * Emergency Halt Button
 * 
 * Gemini recommendation: "A 'panic' button that sends a POST /emergency-halt
 * to the backend is a standard safety feature for monitoring dashboards."
 * 
 * Features:
 * - Two-click confirmation (prevents accidental triggers)
 * - Clear visual feedback
 * - Calls backend endpoint to halt trading
 * - Displays halt status
 */

import { useState } from 'react';
import { cn } from '@/lib/utils';

interface EmergencyHaltProps {
  className?: string;
  apiEndpoint?: string;
}

export function EmergencyHalt({ 
  className,
  apiEndpoint = 'http://localhost:8000/api/v1/system/emergency-halt'
}: EmergencyHaltProps) {
  const [confirming, setConfirming] = useState(false);
  const [halted, setHalted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const triggerHalt = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(apiEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to halt: ${response.statusText}`);
      }

      setHalted(true);
      setConfirming(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const cancelConfirm = () => {
    setConfirming(false);
    setError(null);
  };

  if (halted) {
    return (
      <div className={cn('p-6 rounded-lg bg-red-900 text-white', className)}>
        <div className="flex items-center gap-3 mb-4">
          <div className="w-3 h-3 bg-white rounded-full animate-pulse" />
          <h3 className="text-xl font-bold">SYSTEM HALTED</h3>
        </div>
        <p className="text-red-100 mb-4">
          Trading has been suspended. All open orders have been cancelled.
          The trading bot is no longer processing signals.
        </p>
        <p className="text-sm text-red-200">
          To resume trading, restart the Market Maker backend process.
        </p>
      </div>
    );
  }

  return (
    <div className={cn('p-6 rounded-lg bg-white border-2 border-gray-200', className)}>
      <h3 className="text-lg font-semibold mb-2">Emergency Controls</h3>
      <p className="text-sm text-gray-600 mb-4">
        Use this button to immediately stop all trading activity.
        This will cancel open orders and prevent new signals from executing.
      </p>

      {!confirming ? (
        <button
          onClick={() => setConfirming(true)}
          className={cn(
            'px-6 py-3 rounded font-bold transition-colors',
            'bg-red-600 text-white hover:bg-red-700',
            'focus:outline-none focus:ring-4 focus:ring-red-300'
          )}
        >
          🛑 Emergency Halt
        </button>
      ) : (
        <div className="p-6 bg-red-50 border-2 border-red-500 rounded">
          <p className="font-bold text-red-900 mb-2">
            ⚠️ Confirm Emergency Halt?
          </p>
          <p className="text-sm text-red-800 mb-4">
            This will immediately:
          </p>
          <ul className="text-sm text-red-800 mb-4 ml-4 list-disc space-y-1">
            <li>Stop all trading strategies</li>
            <li>Cancel all open orders</li>
            <li>Prevent new signals from executing</li>
            <li>Require backend restart to resume</li>
          </ul>

          {error && (
            <div className="p-3 bg-red-100 border border-red-300 rounded mb-4">
              <p className="text-sm text-red-900 font-medium">Error: {error}</p>
            </div>
          )}

          <div className="flex gap-4">
            <button
              onClick={triggerHalt}
              disabled={loading}
              className={cn(
                'flex-1 px-6 py-3 rounded font-bold transition-colors',
                'bg-red-600 text-white hover:bg-red-700',
                'focus:outline-none focus:ring-4 focus:ring-red-300',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              {loading ? 'HALTING...' : 'YES, HALT NOW'}
            </button>
            <button
              onClick={cancelConfirm}
              disabled={loading}
              className={cn(
                'flex-1 px-6 py-3 rounded font-bold transition-colors',
                'bg-gray-300 text-gray-800 hover:bg-gray-400',
                'focus:outline-none focus:ring-4 focus:ring-gray-200',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
