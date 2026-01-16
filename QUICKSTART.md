# The Market Maker - Quick Start Guide

## Prerequisites

- Python 3.11+
- Redis server
- Alpaca paper trading account (free)

## Installation

```bash
# Clone repository
git clone <your-repo-url>
cd the-market-maker

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
make install-dev

# Or manually:
pip install -r requirements.txt
pip install -e ".[dev]"
```

## Configuration

1. **Copy environment template**:
   ```bash
   cp .env.example .env
   ```

2. **Get Alpaca API credentials**:
   - Sign up at https://alpaca.markets
   - Go to Paper Trading dashboard
   - Generate API keys

3. **Edit `.env`**:
   ```bash
   ALPACA_API_KEY=your_paper_api_key
   ALPACA_SECRET_KEY=your_paper_secret_key
   
   # For watchdog (recommended: create separate API key pair)
   WATCHDOG_ALPACA_API_KEY=your_watchdog_api_key
   WATCHDOG_ALPACA_SECRET_KEY=your_watchdog_secret_key
   ```

4. **Start Redis**:
   ```bash
   # macOS
   brew install redis
   brew services start redis
   
   # Or use Makefile
   make redis-start
   ```

## Running the System

### Option 1: Paper Trading (Live)

**Terminal 1 - Watchdog** (REQUIRED):
```bash
python scripts/run_watchdog.py
```

**Terminal 2 - Trading Bot**:
```bash
python scripts/run_bot.py
```

The bot will:
- Connect to Alpaca paper trading
- Run strategies (EMA, RSI)
- Execute paper trades
- Monitor performance
- Send heartbeats to watchdog

### Option 2: Backtesting

**Walk-Forward Validation**:
```bash
python scripts/run_backtest.py \
  --strategy ema_crossover \
  --symbol AAPL \
  --start 2020-01-01 \
  --end 2023-12-31 \
  --walk-forward
```

**Stress Testing (10x Spreads)**:
```bash
python scripts/stress_test_strategy.py \
  --strategy ema_crossover \
  --symbol AAPL
```

## Monitoring

### Check Logs

Logs are written to:
- `logs/events.jsonl` - All events (append-only)
- `logs/watchdog.log` - Watchdog logs
- Console output (structured JSON)

### Check Metrics

Metrics are stored in DuckDB:
```python
from src.storage.duckdb_store import DuckDBStore

db = DuckDBStore("data/market_maker.duckdb")
metrics = db.get_performance_history(
    start=datetime(2024, 1, 1),
    end=datetime.now(),
)
```

### Check Redis State

```python
from src.storage.redis_state import RedisStateStore

redis = RedisStateStore()
positions = redis.get_all_positions()
orders = redis.get_open_orders()
```

## Troubleshooting

### Watchdog Not Starting

- Check Redis is running: `make redis-status`
- Verify API credentials in `.env`
- Check logs: `tail -f logs/watchdog.log`

### Bot Not Trading

- Check market is open: Market hours are 9:30 AM - 4:00 PM EST
- Check strategies are enabled in `config/settings.yaml`
- Check regime: Strategies disabled in CHOPPY/CRISIS regimes
- Check logs for errors

### Backtest Failing

- Verify data tier: Must use TIER_1 (Alpaca), not TIER_0 (yfinance)
- Check transaction costs are applied
- Verify walk-forward folds are non-overlapping

## Next Steps

1. **Validate Strategies**:
   - Run walk-forward validation
   - Run stress tests (10x spreads)
   - Only deploy strategies that pass

2. **Calibrate Sentiment** (Optional):
   ```bash
   python scripts/calibrate_sentiment.py --symbol AAPL
   ```

3. **Monitor Performance**:
   - Check metrics daily
   - Watch for strategy decay
   - Review alerts

4. **Research** (Optional):
   - Experiment with ML models (research only)
   - Test new strategies
   - Analyze regime patterns

## Safety Reminders

⚠️ **CRITICAL**: 
- Always run watchdog in separate terminal
- Never disable kill rules
- Monitor drawdowns daily
- Review logs weekly

The system is designed to **survive**, not maximize returns.
If you see consistent losses, that's data - not a bug.
