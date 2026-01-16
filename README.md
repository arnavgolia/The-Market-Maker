# The Market Maker

A failure-aware, research-driven paper trading system for US equities.

## Philosophy

This system is designed for **survivability over profitability**. It assumes:

- Backtests lie
- Markets are adversarial
- Most strategies die
- Most ML models fail

The goal is to run for 3 months, lose ~2% to transaction costs, and have perfect logs explaining why.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        INDEPENDENT WATCHDOG PROCESS                      │
│  (Separate credentials, direct broker access, SIGTERM before SIGKILL)   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ monitors
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          MAIN TRADING PROCESS                            │
│                                                                          │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐ │
│  │    Data     │──▶│   Signal    │──▶│  Decision   │──▶│  Execution  │ │
│  │   Layer     │   │   Layer     │   │   Layer     │   │   Layer     │ │
│  │             │   │             │   │             │   │             │ │
│  │ • Alpaca    │   │ • Regime    │   │ • Risk      │   │ • Orders    │ │
│  │ • yfinance  │   │ • Strategy  │   │ • Portfolio │   │ • Reconcile │ │
│  │ • Sentiment │   │ • Sentiment │   │ • Costs     │   │ • Paper     │ │
│  └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘ │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                         STORAGE LAYER                                ││
│  │  AppendOnlyLog (writes) ──▶ ETL ──▶ DuckDB (analytics)              ││
│  │  Redis (live state, positions, orders, heartbeats)                   ││
│  └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Safety Features

### Independent Watchdog
- Runs as a **separate process** with separate API credentials
- Direct broker access to liquidate positions
- SIGTERM first, SIGKILL only as fallback
- Human intervention required after 3 restart attempts

### Kill Rules (Hardcoded)
- **Daily Loss**: -5% triggers emergency shutdown
- **Max Drawdown**: -15% triggers permanent shutdown
- **Position Concentration**: >25% triggers shutdown
- **Zombie Orders**: >300 seconds triggers shutdown
- **Friday Force Close**: All positions closed at 3:55 PM EST

### Data Tier System
- **Tier 0** (yfinance): Universe selection ONLY - NEVER for backtesting
- **Tier 1** (Alpaca Historical): Strategy validation
- **Tier 2** (Synthetic): Spread modeling
- **Tier 3** (Alpaca Live): Production execution

## Quick Start

### Prerequisites
- Python 3.11+
- Redis server
- Alpaca paper trading account

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/the-market-maker.git
cd the-market-maker

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
make install-dev

# Copy environment template
cp .env.example .env
# Edit .env with your API credentials
```

### Configuration

Edit `.env` with your credentials:

```bash
# Alpaca Paper Trading
ALPACA_API_KEY=your_paper_api_key
ALPACA_SECRET_KEY=your_paper_secret_key

# Watchdog (should use SEPARATE credentials)
WATCHDOG_ALPACA_API_KEY=your_watchdog_api_key
WATCHDOG_ALPACA_SECRET_KEY=your_watchdog_secret_key

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
```

### Running

**CRITICAL: Run watchdog and bot in separate terminals**

Terminal 1 - Start Redis:
```bash
make redis-start
```

Terminal 2 - Start Watchdog:
```bash
python scripts/run_watchdog.py
```

Terminal 3 - Start Bot:
```bash
python scripts/run_bot.py
```

## Project Structure

```
the-market-maker/
├── config/
│   ├── settings.yaml           # Main bot configuration
│   └── watchdog_settings.yaml  # Watchdog configuration (SEPARATE)
├── src/
│   ├── data/                   # Data ingestion and tiers
│   ├── storage/                # AppendOnlyLog, DuckDB, Redis
│   ├── regime/                 # Market regime detection
│   ├── strategy/               # Trading strategies (Tier 1, 2, 3)
│   ├── sentiment/              # Sentiment analysis
│   ├── risk/                   # Risk management
│   ├── execution/              # Order execution
│   └── monitoring/             # Metrics and alerting
├── watchdog/                   # Independent watchdog process
├── research/                   # Backtesting and analysis
├── tests/                      # Test suite
└── scripts/                    # Entry point scripts
```

## Strategy Tiers

### Tier 1 - Deterministic (Baseline)
- EMA crossover with volatility filters
- RSI mean reversion
- Multi-timeframe confirmation
- Regime-gated (disabled in choppy markets)

### Tier 2 - Probabilistic
- Sentiment as regime filter (not signal)
- Two-stage validation (Bonferroni correction)
- Hype decay modeling
- Only enabled if calibration validates

### Tier 3 - Learned (Research Only)
- LSTM on stationary transforms
- Transformer attention analysis
- Walk-forward validation mandatory
- **NOT for production trading**

## What This System Cannot Solve

1. **Alpha Decay**: Parameters will stop working
2. **Black Swan Events**: Gap risk is unhedgeable
3. **Exchange Counterparty Risk**: If Alpaca goes down, nothing helps
4. **Latency Disadvantage**: Retail latency is structural
5. **Capacity Limits**: Strategies don't scale linearly

## Development

```bash
# Run tests
make test

# Run stress tests (10x spread scenarios)
make test-stress

# Format code
make format

# Type check
make typecheck
```

## License

MIT

## Acknowledgments

This system was designed with extensive adversarial review to identify and mitigate failure modes. Special thanks to the principles of quantitative research that informed the architecture:

- "Assume backtests deceive"
- "Design for failure, decay, and regime change"
- "Prefer correctness over cleverness"
