/**
 * Comprehensive tests for Ring Buffer implementation.
 * 
 * Tests:
 * - Capacity enforcement
 * - Circular overwriting
 * - Memory safety
 * - toArray() ordering
 * - Specialized buffer methods
 * - Edge cases
 */

import { describe, it, expect, beforeEach } from '@jest/globals';
import { 
  RingBuffer, 
  CandleRingBuffer, 
  EquityRingBuffer,
  type CandleData,
  type EquityPoint
} from '../../frontend/lib/ring-buffer';

describe('RingBuffer', () => {
  describe('Basic Operations', () => {
    it('should initialize with correct capacity', () => {
      const buffer = new RingBuffer<number>(100);
      expect(buffer.capacity()).toBe(100);
      expect(buffer.length()).toBe(0);
    });

    it('should push items and track length', () => {
      const buffer = new RingBuffer<number>(10);
      
      buffer.push(1);
      expect(buffer.length()).toBe(1);
      
      buffer.push(2);
      expect(buffer.length()).toBe(2);
    });

    it('should not exceed max capacity', () => {
      const buffer = new RingBuffer<number>(5);
      
      for (let i = 0; i < 10; i++) {
        buffer.push(i);
      }
      
      expect(buffer.length()).toBe(5);
      expect(buffer.isFull()).toBe(true);
    });

    it('should overwrite oldest data when full', () => {
      const buffer = new RingBuffer<number>(3);
      
      buffer.push(1);
      buffer.push(2);
      buffer.push(3);
      buffer.push(4);  // Should overwrite 1
      
      const data = buffer.toArray();
      expect(data).toEqual([2, 3, 4]);
    });

    it('should maintain correct order after wrapping', () => {
      const buffer = new RingBuffer<number>(5);
      
      // Fill buffer
      for (let i = 0; i < 5; i++) {
        buffer.push(i);
      }
      
      // Wrap around
      for (let i = 5; i < 10; i++) {
        buffer.push(i);
      }
      
      const data = buffer.toArray();
      expect(data).toEqual([5, 6, 7, 8, 9]);
    });

    it('should get items by index', () => {
      const buffer = new RingBuffer<number>(5);
      
      buffer.push(10);
      buffer.push(20);
      buffer.push(30);
      
      expect(buffer.get(0)).toBe(10);
      expect(buffer.get(1)).toBe(20);
      expect(buffer.get(2)).toBe(30);
    });

    it('should return undefined for out of bounds index', () => {
      const buffer = new RingBuffer<number>(5);
      
      buffer.push(1);
      
      expect(buffer.get(-1)).toBeUndefined();
      expect(buffer.get(10)).toBeUndefined();
    });

    it('should get last N items with tail()', () => {
      const buffer = new RingBuffer<number>(10);
      
      for (let i = 0; i < 10; i++) {
        buffer.push(i);
      }
      
      const last3 = buffer.tail(3);
      expect(last3).toEqual([7, 8, 9]);
    });

    it('should clear all data', () => {
      const buffer = new RingBuffer<number>(5);
      
      buffer.push(1);
      buffer.push(2);
      buffer.push(3);
      
      buffer.clear();
      
      expect(buffer.length()).toBe(0);
      expect(buffer.toArray()).toEqual([]);
    });

    it('should estimate memory usage', () => {
      const buffer = new RingBuffer<number>(1000);
      
      for (let i = 0; i < 500; i++) {
        buffer.push(i);
      }
      
      const memory = buffer.estimatedMemoryBytes();
      expect(memory).toBeGreaterThan(0);
      expect(memory).toBe(500 * 80);  // 80 bytes per item estimate
    });
  });

  describe('Edge Cases', () => {
    it('should handle single item capacity', () => {
      const buffer = new RingBuffer<number>(1);
      
      buffer.push(1);
      expect(buffer.toArray()).toEqual([1]);
      
      buffer.push(2);
      expect(buffer.toArray()).toEqual([2]);
    });

    it('should handle empty buffer operations', () => {
      const buffer = new RingBuffer<number>(5);
      
      expect(buffer.toArray()).toEqual([]);
      expect(buffer.tail(5)).toEqual([]);
      expect(buffer.get(0)).toBeUndefined();
    });

    it('should handle tail() with count > length', () => {
      const buffer = new RingBuffer<number>(10);
      
      buffer.push(1);
      buffer.push(2);
      
      const tail = buffer.tail(5);
      expect(tail).toEqual([1, 2]);
    });

    it('should handle large capacity', () => {
      const buffer = new RingBuffer<number>(10000);
      
      for (let i = 0; i < 10000; i++) {
        buffer.push(i);
      }
      
      expect(buffer.length()).toBe(10000);
      expect(buffer.isFull()).toBe(true);
    });
  });

  describe('Memory Safety', () => {
    it('should not grow beyond max capacity (memory leak test)', () => {
      const buffer = new RingBuffer<number>(1000);
      
      // Push 10x the capacity
      for (let i = 0; i < 10000; i++) {
        buffer.push(i);
      }
      
      expect(buffer.length()).toBe(1000);
      expect(buffer.estimatedMemoryBytes()).toBeLessThanOrEqual(1000 * 80);
    });

    it('should handle rapid pushes without memory issues', () => {
      const buffer = new RingBuffer<number>(5000);
      
      // Simulate 1 hour of 10fps updates
      const updates = 10 * 60 * 60;  // 36,000 updates
      
      for (let i = 0; i < updates; i++) {
        buffer.push(i);
      }
      
      expect(buffer.length()).toBe(5000);
    });
  });
});

describe('CandleRingBuffer', () => {
  let buffer: CandleRingBuffer;

  beforeEach(() => {
    buffer = new CandleRingBuffer(100);
  });

  const createCandle = (timestamp: number, close: number): CandleData => ({
    timestamp,
    open: close - 1,
    high: close + 1,
    low: close - 2,
    close,
    volume: 1000,
  });

  it('should store candle data', () => {
    const candle = createCandle(Date.now(), 100);
    buffer.push(candle);
    
    expect(buffer.length()).toBe(1);
  });

  it('should return last price', () => {
    buffer.push(createCandle(1000, 100));
    buffer.push(createCandle(2000, 105));
    buffer.push(createCandle(3000, 103));
    
    expect(buffer.lastPrice()).toBe(103);
  });

  it('should return null for empty buffer last price', () => {
    expect(buffer.lastPrice()).toBeNull();
  });

  it('should calculate price range', () => {
    buffer.push(createCandle(1000, 100));  // high=101, low=98
    buffer.push(createCandle(2000, 110));  // high=111, low=108
    buffer.push(createCandle(3000, 95));   // high=96, low=93
    
    const range = buffer.priceRange();
    expect(range).not.toBeNull();
    expect(range!.min).toBe(93);
    expect(range!.max).toBe(111);
  });

  it('should return null for empty buffer price range', () => {
    expect(buffer.priceRange()).toBeNull();
  });

  it('should convert to chart data format', () => {
    const candle1 = createCandle(1000, 100);
    const candle2 = createCandle(2000, 105);
    
    buffer.push(candle1);
    buffer.push(candle2);
    
    const chartData = buffer.toChartData();
    expect(chartData).toHaveLength(2);
    expect(chartData[0]).toEqual(candle1);
    expect(chartData[1]).toEqual(candle2);
  });

  it('should handle OHLC validation', () => {
    // Valid candle
    const validCandle = createCandle(1000, 100);
    expect(validCandle.high).toBeGreaterThanOrEqual(validCandle.low);
    expect(validCandle.close).toBeGreaterThanOrEqual(validCandle.low);
    expect(validCandle.close).toBeLessThanOrEqual(validCandle.high);
  });
});

describe('EquityRingBuffer', () => {
  let buffer: EquityRingBuffer;

  beforeEach(() => {
    buffer = new EquityRingBuffer(100);
  });

  const createEquityPoint = (timestamp: number, equity: number): EquityPoint => ({
    timestamp,
    equity,
    cash: equity * 0.3,
    positions_value: equity * 0.7,
  });

  it('should store equity points', () => {
    const point = createEquityPoint(Date.now(), 100000);
    buffer.push(point);
    
    expect(buffer.length()).toBe(1);
  });

  it('should return current equity', () => {
    buffer.push(createEquityPoint(1000, 100000));
    buffer.push(createEquityPoint(2000, 102000));
    buffer.push(createEquityPoint(3000, 101500));
    
    expect(buffer.currentEquity()).toBe(101500);
  });

  it('should return null for empty buffer current equity', () => {
    expect(buffer.currentEquity()).toBeNull();
  });

  it('should calculate returns', () => {
    buffer.push(createEquityPoint(1000, 100000));
    buffer.push(createEquityPoint(2000, 102000));  // +2%
    buffer.push(createEquityPoint(3000, 101000));  // -0.98%
    
    const returns = buffer.calculateReturns();
    
    expect(returns).toHaveLength(2);
    expect(returns[0]).toBeCloseTo(0.02, 4);
    expect(returns[1]).toBeCloseTo(-0.0098, 4);
  });

  it('should calculate drawdown series', () => {
    buffer.push(createEquityPoint(1000, 100000));
    buffer.push(createEquityPoint(2000, 105000));  // Peak
    buffer.push(createEquityPoint(3000, 103000));  // -1.9% from peak
    buffer.push(createEquityPoint(4000, 100000));  // -4.76% from peak
    
    const drawdowns = buffer.calculateDrawdown();
    
    expect(drawdowns).toHaveLength(4);
    expect(drawdowns[0].drawdown).toBe(0);
    expect(drawdowns[1].drawdown).toBe(0);
    expect(drawdowns[2].drawdown).toBeCloseTo(-0.019, 3);
    expect(drawdowns[3].drawdown).toBeCloseTo(-0.0476, 3);
  });

  it('should calculate max drawdown', () => {
    buffer.push(createEquityPoint(1000, 100000));
    buffer.push(createEquityPoint(2000, 110000));  // Peak
    buffer.push(createEquityPoint(3000, 100000));  // -9.09% from peak
    buffer.push(createEquityPoint(4000, 95000));   // -13.64% from peak
    buffer.push(createEquityPoint(5000, 105000));  // Recovering
    
    const maxDD = buffer.maxDrawdown();
    
    expect(maxDD).toBeCloseTo(-0.1364, 3);
  });

  it('should convert to chart data format', () => {
    const point1 = createEquityPoint(1000, 100000);
    const point2 = createEquityPoint(2000, 102000);
    
    buffer.push(point1);
    buffer.push(point2);
    
    const chartData = buffer.toChartData();
    
    expect(chartData).toHaveLength(2);
    expect(chartData[0]).toEqual({ time: 1000, value: 100000 });
    expect(chartData[1]).toEqual({ time: 2000, value: 102000 });
  });

  it('should handle zero equity edge case', () => {
    buffer.push(createEquityPoint(1000, 100000));
    buffer.push(createEquityPoint(2000, 0));  // Account blown up
    
    const returns = buffer.calculateReturns();
    expect(returns[0]).toBe(-1);  // -100% return
  });

  it('should handle negative equity (margin call)', () => {
    buffer.push(createEquityPoint(1000, 100000));
    buffer.push(createEquityPoint(2000, -10000));
    
    const returns = buffer.calculateReturns();
    expect(returns[0]).toBe(-1.1);  // -110% return
  });
});

describe('Performance & Stress Tests', () => {
  it('should handle 5000 pushes in <100ms', () => {
    const buffer = new RingBuffer<number>(5000);
    
    const start = performance.now();
    for (let i = 0; i < 5000; i++) {
      buffer.push(i);
    }
    const duration = performance.now() - start;
    
    expect(duration).toBeLessThan(100);
  });

  it('should handle toArray() on full buffer in <10ms', () => {
    const buffer = new RingBuffer<number>(5000);
    
    for (let i = 0; i < 5000; i++) {
      buffer.push(i);
    }
    
    const start = performance.now();
    const data = buffer.toArray();
    const duration = performance.now() - start;
    
    expect(duration).toBeLessThan(10);
    expect(data).toHaveLength(5000);
  });

  it('should handle wrapped buffer toArray() correctly', () => {
    const buffer = new RingBuffer<number>(10);
    
    // Fill and wrap multiple times
    for (let i = 0; i < 25; i++) {
      buffer.push(i);
    }
    
    const data = buffer.toArray();
    expect(data).toEqual([15, 16, 17, 18, 19, 20, 21, 22, 23, 24]);
  });

  it('should handle concurrent pushes (simulated)', async () => {
    const buffer = new RingBuffer<number>(1000);
    
    // Simulate concurrent pushes
    const promises = [];
    for (let i = 0; i < 100; i++) {
      promises.push(Promise.resolve().then(() => buffer.push(i)));
    }
    
    await Promise.all(promises);
    
    expect(buffer.length()).toBe(100);
  });
});
