/**
 * Market hours utility hook.
 * 
 * Determines if current time is during market hours (9:30 AM - 4:00 PM ET).
 * Critical for staleness detection - data can age during market hours but not after close.
 */

import { useState, useEffect } from 'react';
import { toExchangeTime, isMarketHours as checkMarketHours } from '@/lib/time';

/**
 * Hook that returns true if market is currently open.
 * Updates every minute.
 */
export function useIsMarketHours(): boolean {
  const [isOpen, setIsOpen] = useState(() => checkMarketHours());

  useEffect(() => {
    // Check every minute
    const interval = setInterval(() => {
      setIsOpen(checkMarketHours());
    }, 60000);

    // Initial check
    setIsOpen(checkMarketHours());

    return () => clearInterval(interval);
  }, []);

  return isOpen;
}

/**
 * Hook that returns market status with details.
 */
export interface MarketStatus {
  isOpen: boolean;
  status: 'pre_market' | 'open' | 'closed' | 'weekend';
  nextOpen: Date | null;
  nextClose: Date | null;
  message: string;
}

export function useMarketStatus(): MarketStatus {
  const [status, setStatus] = useState<MarketStatus>(() => calculateMarketStatus());

  useEffect(() => {
    // Update every minute
    const interval = setInterval(() => {
      setStatus(calculateMarketStatus());
    }, 60000);

    return () => clearInterval(interval);
  }, []);

  return status;
}

function calculateMarketStatus(): MarketStatus {
  const now = new Date();
  const et = toExchangeTime(now);
  const hours = et.getHours();
  const minutes = et.getMinutes();
  const dayOfWeek = et.getDay();
  
  // Weekend
  if (dayOfWeek === 0 || dayOfWeek === 6) {
    return {
      isOpen: false,
      status: 'weekend',
      nextOpen: getNextMonday930AM(et),
      nextClose: null,
      message: 'Market closed (weekend)',
    };
  }
  
  const marketMinutes = hours * 60 + minutes;
  const openMinutes = 9 * 60 + 30;  // 9:30 AM
  const closeMinutes = 16 * 60;     // 4:00 PM
  
  if (marketMinutes < openMinutes) {
    // Pre-market
    return {
      isOpen: false,
      status: 'pre_market',
      nextOpen: new Date(et.getFullYear(), et.getMonth(), et.getDate(), 9, 30, 0),
      nextClose: new Date(et.getFullYear(), et.getMonth(), et.getDate(), 16, 0, 0),
      message: 'Pre-market',
    };
  } else if (marketMinutes >= openMinutes && marketMinutes < closeMinutes) {
    // Open
    return {
      isOpen: true,
      status: 'open',
      nextOpen: null,
      nextClose: new Date(et.getFullYear(), et.getMonth(), et.getDate(), 16, 0, 0),
      message: 'Market open',
    };
  } else {
    // After hours
    return {
      isOpen: false,
      status: 'closed',
      nextOpen: getNextTradingDay930AM(et),
      nextClose: null,
      message: 'After hours',
    };
  }
}

function getNextMonday930AM(et: Date): Date {
  const next = new Date(et);
  next.setDate(next.getDate() + (8 - next.getDay()) % 7);
  next.setHours(9, 30, 0, 0);
  return next;
}

function getNextTradingDay930AM(et: Date): Date {
  const next = new Date(et);
  const dayOfWeek = next.getDay();
  
  if (dayOfWeek === 5) {
    // Friday -> Monday
    next.setDate(next.getDate() + 3);
  } else if (dayOfWeek === 6) {
    // Saturday -> Monday
    next.setDate(next.getDate() + 2);
  } else {
    // Weekday -> next day
    next.setDate(next.getDate() + 1);
  }
  
  next.setHours(9, 30, 0, 0);
  return next;
}
