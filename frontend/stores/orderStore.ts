/**
 * Order store with timestamp-based state merging.
 * 
 * Critical: Never overwrite newer data with older data.
 * 
 * Scenario: REST "Pending" response arrives AFTER WS "Filled" event.
 * Without timestamps, UI would flicker: Filled -> Pending (incorrect).
 * With timestamps, stale "Pending" is ignored.
 */

import { create } from 'zustand';

export interface Order {
  order_id: string;
  client_order_id: string;
  symbol: string;
  side: 'buy' | 'sell';
  qty: number;
  order_type: 'market' | 'limit';
  status: 'pending' | 'submitted' | 'partial_fill' | 'filled' | 'cancelled' | 'failed';
  limit_price?: number;
  filled_qty?: number;
  filled_price?: number;
  created_at: string;
  updated_at: string;
  strategy_name?: string;
  signal_id?: string;
}

interface OrderState {
  orders: Map<string, Order>;
  lastUpdated: Map<string, number>;  // order_id -> timestamp (ms)
  
  // Actions
  updateOrder: (order: Order, sourceTimestamp: number) => void;
  updateOrders: (orders: Order[], sourceTimestamp: number) => void;
  removeOrder: (order_id: string) => void;
  clear: () => void;
  
  // Selectors
  getOrder: (order_id: string) => Order | undefined;
  getOpenOrders: () => Order[];
  getFilledOrders: () => Order[];
  getOrdersBySymbol: (symbol: string) => Order[];
  getOrdersByStatus: (status: Order['status']) => Order[];
}

export const useOrderStore = create<OrderState>((set, get) => ({
  orders: new Map(),
  lastUpdated: new Map(),
  
  updateOrder: (order: Order, sourceTimestamp: number) => {
    const existing = get().lastUpdated.get(order.order_id) ?? 0;
    
    // CRITICAL: Never overwrite newer data with older data
    if (sourceTimestamp <= existing) {
      console.debug(
        `[OrderStore] Ignoring stale order update for ${order.order_id}`,
        { existing, source: sourceTimestamp }
      );
      return;
    }
    
    set((state) => ({
      orders: new Map(state.orders).set(order.order_id, order),
      lastUpdated: new Map(state.lastUpdated).set(order.order_id, sourceTimestamp),
    }));
  },
  
  updateOrders: (orders: Order[], sourceTimestamp: number) => {
    set((state) => {
      const newOrders = new Map(state.orders);
      const newTimestamps = new Map(state.lastUpdated);
      
      for (const order of orders) {
        const existing = state.lastUpdated.get(order.order_id) ?? 0;
        
        if (sourceTimestamp > existing) {
          newOrders.set(order.order_id, order);
          newTimestamps.set(order.order_id, sourceTimestamp);
        }
      }
      
      return {
        orders: newOrders,
        lastUpdated: newTimestamps,
      };
    });
  },
  
  removeOrder: (order_id: string) => {
    set((state) => {
      const newOrders = new Map(state.orders);
      const newTimestamps = new Map(state.lastUpdated);
      newOrders.delete(order_id);
      newTimestamps.delete(order_id);
      
      return {
        orders: newOrders,
        lastUpdated: newTimestamps,
      };
    });
  },
  
  clear: () => {
    set({ orders: new Map(), lastUpdated: new Map() });
  },
  
  // Selectors
  getOrder: (order_id: string) => {
    return get().orders.get(order_id);
  },
  
  getOpenOrders: () => {
    return Array.from(get().orders.values()).filter(
      order => ['pending', 'submitted', 'partial_fill'].includes(order.status)
    );
  },
  
  getFilledOrders: () => {
    return Array.from(get().orders.values()).filter(
      order => order.status === 'filled'
    );
  },
  
  getOrdersBySymbol: (symbol: string) => {
    return Array.from(get().orders.values()).filter(
      order => order.symbol === symbol
    );
  },
  
  getOrdersByStatus: (status: Order['status']) => {
    return Array.from(get().orders.values()).filter(
      order => order.status === status
    );
  },
}));
