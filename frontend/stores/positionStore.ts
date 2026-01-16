/**
 * Position store with timestamp-based state merging.
 * 
 * Prevents stale position data from overwriting fresh updates.
 * Critical for accurate P&L and risk calculations.
 */

import { create } from 'zustand';

export interface Position {
  symbol: string;
  qty: number;
  avg_price: number;
  market_value: number;
  unrealized_pnl: number;
  side: 'long' | 'short';
  updated_at: string;
}

interface PositionState {
  positions: Map<string, Position>;
  lastUpdated: Map<string, number>;  // symbol -> timestamp (ms)
  
  // Actions
  updatePosition: (position: Position, sourceTimestamp: number) => void;
  updatePositions: (positions: Position[], sourceTimestamp: number) => void;
  removePosition: (symbol: string) => void;
  clear: () => void;
  
  // Selectors
  getPosition: (symbol: string) => Position | undefined;
  getAllPositions: () => Position[];
  getTotalValue: () => number;
  getTotalPnL: () => number;
  getLongPositions: () => Position[];
  getShortPositions: () => Position[];
}

export const usePositionStore = create<PositionState>((set, get) => ({
  positions: new Map(),
  lastUpdated: new Map(),
  
  updatePosition: (position: Position, sourceTimestamp: number) => {
    const existing = get().lastUpdated.get(position.symbol) ?? 0;
    
    // Never overwrite newer data with older data
    if (sourceTimestamp <= existing) {
      console.debug(
        `[PositionStore] Ignoring stale position update for ${position.symbol}`,
        { existing, source: sourceTimestamp }
      );
      return;
    }
    
    set((state) => ({
      positions: new Map(state.positions).set(position.symbol, position),
      lastUpdated: new Map(state.lastUpdated).set(position.symbol, sourceTimestamp),
    }));
  },
  
  updatePositions: (positions: Position[], sourceTimestamp: number) => {
    set((state) => {
      const newPositions = new Map(state.positions);
      const newTimestamps = new Map(state.lastUpdated);
      
      for (const position of positions) {
        const existing = state.lastUpdated.get(position.symbol) ?? 0;
        
        if (sourceTimestamp > existing) {
          newPositions.set(position.symbol, position);
          newTimestamps.set(position.symbol, sourceTimestamp);
        }
      }
      
      return {
        positions: newPositions,
        lastUpdated: newTimestamps,
      };
    });
  },
  
  removePosition: (symbol: string) => {
    set((state) => {
      const newPositions = new Map(state.positions);
      const newTimestamps = new Map(state.lastUpdated);
      newPositions.delete(symbol);
      newTimestamps.delete(symbol);
      
      return {
        positions: newPositions,
        lastUpdated: newTimestamps,
      };
    });
  },
  
  clear: () => {
    set({ positions: new Map(), lastUpdated: new Map() });
  },
  
  // Selectors
  getPosition: (symbol: string) => {
    return get().positions.get(symbol);
  },
  
  getAllPositions: () => {
    return Array.from(get().positions.values());
  },
  
  getTotalValue: () => {
    return Array.from(get().positions.values()).reduce(
      (total, pos) => total + pos.market_value,
      0
    );
  },
  
  getTotalPnL: () => {
    return Array.from(get().positions.values()).reduce(
      (total, pos) => total + pos.unrealized_pnl,
      0
    );
  },
  
  getLongPositions: () => {
    return Array.from(get().positions.values()).filter(
      pos => pos.side === 'long'
    );
  },
  
  getShortPositions: () => {
    return Array.from(get().positions.values()).filter(
      pos => pos.side === 'short'
    );
  },
}));
