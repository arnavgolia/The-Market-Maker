/**
 * Throttled updates hook to prevent React render overload.
 * 
 * During volatility spikes, WebSocket can send 50+ updates/sec.
 * This hook:
 * - Limits renders to max FPS (default 10fps = every 100ms)
 * - Uses requestAnimationFrame for smooth updates
 * - Batches rapid updates to prevent UI freeze
 * 
 * Critical for maintaining 60fps UI during market hours.
 */

import { useState, useEffect, useRef } from 'react';

export interface ThrottledConfig {
  maxFps?: number;           // Maximum renders per second (default: 10)
  leading?: boolean;         // Render immediately on first update (default: true)
  trailing?: boolean;        // Render final update after quiet period (default: true)
}

/**
 * Throttle updates to prevent React render overload.
 * 
 * Example:
 * ```ts
 * const throttledPrice = useThrottledUpdates(livePrice, { maxFps: 10 });
 * ```
 */
export function useThrottledUpdates<T>(
  value: T,
  config: ThrottledConfig = {}
): T {
  const {
    maxFps = 10,
    leading = true,
    trailing = true,
  } = config;

  const [throttledValue, setThrottledValue] = useState<T>(value);
  const lastRender = useRef<number>(0);
  const pendingValue = useRef<T>(value);
  const frameId = useRef<number>();
  const timeoutId = useRef<ReturnType<typeof setTimeout>>();

  const minInterval = 1000 / maxFps;  // Minimum ms between renders

  useEffect(() => {
    pendingValue.current = value;
    const now = performance.now();
    const timeSinceLastRender = now - lastRender.current;

    // Leading edge: render immediately if enough time has passed
    if (leading && timeSinceLastRender >= minInterval) {
      setThrottledValue(value);
      lastRender.current = now;
      
      // Cancel any pending frame
      if (frameId.current) {
        cancelAnimationFrame(frameId.current);
        frameId.current = undefined;
      }
      if (timeoutId.current) {
        clearTimeout(timeoutId.current);
        timeoutId.current = undefined;
      }
      return;
    }

    // Schedule update for next available frame
    if (!frameId.current) {
      frameId.current = requestAnimationFrame(() => {
        const frameNow = performance.now();
        const frameTimeSinceLastRender = frameNow - lastRender.current;

        if (frameTimeSinceLastRender >= minInterval) {
          // Enough time has passed, render now
          setThrottledValue(pendingValue.current);
          lastRender.current = frameNow;
          frameId.current = undefined;
        } else {
          // Still too soon, schedule timeout for exact time
          const remaining = minInterval - frameTimeSinceLastRender;
          frameId.current = undefined;
          
          if (trailing) {
            timeoutId.current = setTimeout(() => {
              setThrottledValue(pendingValue.current);
              lastRender.current = performance.now();
              timeoutId.current = undefined;
            }, remaining);
          }
        }
      });
    }

    // Cleanup
    return () => {
      if (frameId.current) {
        cancelAnimationFrame(frameId.current);
      }
      if (timeoutId.current) {
        clearTimeout(timeoutId.current);
      }
    };
  }, [value, minInterval, leading, trailing]);

  return throttledValue;
}

/**
 * Throttle function calls (not React renders).
 * 
 * Useful for throttling WebSocket message processing.
 * 
 * Example:
 * ```ts
 * const throttledHandler = useThrottledCallback(
 *   (msg) => processMessage(msg),
 *   { maxFps: 10 }
 * );
 * ```
 */
export function useThrottledCallback<T extends (...args: any[]) => void>(
  callback: T,
  config: ThrottledConfig = {}
): T {
  const {
    maxFps = 10,
    leading = true,
    trailing = true,
  } = config;

  const lastCall = useRef<number>(0);
  const pendingArgs = useRef<any[]>();
  const timeoutId = useRef<ReturnType<typeof setTimeout>>();

  const minInterval = 1000 / maxFps;

  const throttled = ((...args: any[]) => {
    const now = performance.now();
    const timeSinceLastCall = now - lastCall.current;

    pendingArgs.current = args;

    if (leading && timeSinceLastCall >= minInterval) {
      // Call immediately
      callback(...args);
      lastCall.current = now;
      
      if (timeoutId.current) {
        clearTimeout(timeoutId.current);
        timeoutId.current = undefined;
      }
      return;
    }

    // Schedule trailing call
    if (trailing && !timeoutId.current) {
      const remaining = minInterval - timeSinceLastCall;
      timeoutId.current = setTimeout(() => {
        if (pendingArgs.current) {
          callback(...pendingArgs.current);
          lastCall.current = performance.now();
        }
        timeoutId.current = undefined;
      }, Math.max(0, remaining));
    }
  }) as T;

  useEffect(() => {
    return () => {
      if (timeoutId.current) {
        clearTimeout(timeoutId.current);
      }
    };
  }, []);

  return throttled;
}

/**
 * Batched state updates with throttling.
 * 
 * Collects rapid updates and flushes them in batches.
 * 
 * Example:
 * ```ts
 * const [prices, addPrice] = useBatchedUpdates<number>([], { maxFps: 10 });
 * ```
 */
export function useBatchedUpdates<T>(
  initialValue: T[] = [],
  config: ThrottledConfig = {}
): [T[], (item: T) => void, () => void] {
  const {
    maxFps = 10,
  } = config;

  const [state, setState] = useState<T[]>(initialValue);
  const batch = useRef<T[]>([]);
  const lastFlush = useRef<number>(0);
  const frameId = useRef<number>();

  const minInterval = 1000 / maxFps;

  const flush = () => {
    if (batch.current.length > 0) {
      setState(prev => [...prev, ...batch.current]);
      batch.current = [];
      lastFlush.current = performance.now();
    }
  };

  const add = (item: T) => {
    batch.current.push(item);

    if (!frameId.current) {
      frameId.current = requestAnimationFrame(() => {
        const now = performance.now();
        const timeSinceLastFlush = now - lastFlush.current;

        if (timeSinceLastFlush >= minInterval) {
          flush();
          frameId.current = undefined;
        } else {
          // Schedule exact time
          const remaining = minInterval - timeSinceLastFlush;
          setTimeout(() => {
            flush();
            frameId.current = undefined;
          }, remaining);
        }
      });
    }
  };

  const clear = () => {
    batch.current = [];
    setState([]);
  };

  useEffect(() => {
    return () => {
      if (frameId.current) {
        cancelAnimationFrame(frameId.current);
      }
    };
  }, []);

  return [state, add, clear];
}

/**
 * Performance monitor for debugging throttling.
 * 
 * Tracks actual render FPS and warns if too high.
 */
export function useRenderFPS(componentName: string = 'Component') {
  const renderCount = useRef(0);
  const lastCheck = useRef(Date.now());

  useEffect(() => {
    renderCount.current++;

    const now = Date.now();
    const elapsed = now - lastCheck.current;

    if (elapsed >= 1000) {
      // Check every second
      const fps = renderCount.current / (elapsed / 1000);
      
      if (fps > 20) {
        console.warn(
          `${componentName} rendering at ${fps.toFixed(1)} FPS. Consider throttling.`
        );
      }

      renderCount.current = 0;
      lastCheck.current = now;
    }
  });
}
