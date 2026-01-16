/**
 * Audio Alert Controls Component
 * 
 * Allows users to enable/disable audio alerts and adjust volume.
 */

import { useState, useEffect } from 'react';
import { audioAlerts, AlertSound } from '@/lib/audio-alerts';
import { cn } from '@/lib/utils';

export function AudioControls({ className }: { className?: string }) {
  const [enabled, setEnabled] = useState(audioAlerts.isEnabled());
  const [volume, setVolume] = useState(audioAlerts.getVolume());

  const toggleEnabled = () => {
    const newState = audioAlerts.toggle();
    setEnabled(newState);
  };

  const handleVolumeChange = (newVolume: number) => {
    audioAlerts.setVolume(newVolume);
    setVolume(newVolume);
  };

  const testSound = () => {
    audioAlerts.play(AlertSound.ORDER_FILLED);
  };

  // Unlock audio on first interaction
  useEffect(() => {
    const unlock = () => audioAlerts.unlockAudio();
    document.addEventListener('click', unlock, { once: true });
    return () => document.removeEventListener('click', unlock);
  }, []);

  return (
    <div className={cn('p-4 rounded-lg bg-white border', className)}>
      <div className="flex items-center justify-between mb-4">
        <h4 className="font-semibold">Audio Alerts</h4>
        <button
          onClick={toggleEnabled}
          className={cn(
            'px-3 py-1 rounded text-sm font-medium transition-colors',
            enabled
              ? 'bg-green-500 text-white hover:bg-green-600'
              : 'bg-gray-300 text-gray-700 hover:bg-gray-400'
          )}
        >
          {enabled ? '🔊 ON' : '🔇 OFF'}
        </button>
      </div>

      {enabled && (
        <div className="space-y-3">
          {/* Volume Slider */}
          <div>
            <label className="text-sm text-gray-600 mb-1 block">
              Volume: {Math.round(volume * 100)}%
            </label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={volume}
              onChange={(e) => handleVolumeChange(parseFloat(e.target.value))}
              className="w-full"
            />
          </div>

          {/* Test Button */}
          <button
            onClick={testSound}
            className="w-full px-3 py-2 rounded bg-blue-500 text-white text-sm hover:bg-blue-600 transition-colors"
          >
            Test Sound
          </button>
        </div>
      )}

      {!enabled && (
        <p className="text-xs text-gray-500">
          Enable audio to receive sound notifications for order fills and critical alerts.
        </p>
      )}
    </div>
  );
}
