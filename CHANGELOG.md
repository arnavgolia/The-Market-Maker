# Changelog

All notable changes to The Market Maker will be documented in this file.

## [0.1.0] - 2024-01-XX

### Added

#### Core Infrastructure
- Data ingestion with tiered quality system (Tier 0-3)
- Storage layer: AppendOnlyLog, DuckDB, Redis
- Independent watchdog process with graceful shutdown
- Configuration system with YAML files

#### Trading Components
- Regime detection (fast + slow volatility with crisis override)
- Tier 1 strategies: EMA crossover, RSI mean reversion
- Risk management: Position sizing, drawdown monitoring
- Execution engine: Order state machine, reconciliation
- Portfolio allocator: Correlation-aware allocation

#### Validation Framework
- Transaction cost modeling (spread + slippage)
- Backtesting engine with realistic costs
- Walk-forward validation (non-overlapping folds)
- Stress testing (10x spread scenarios)

#### Sentiment Pipeline
- Reddit scraper with manipulation detection
- NLP processing (FinBERT)
- Lead-lag calibration (Bonferroni + two-stage A/B validation)
- Decay modeling
- Tier 2 sentiment filter strategy

#### ML Research
- LSTM strategy (research only, disabled by default)

#### Monitoring
- Metrics collection (Sharpe, Sortino, drawdown)
- Alerting with deduplication
- Strategy decay detection

#### Safety Features
- Independent watchdog (separate process, separate credentials)
- Graceful shutdown (SIGTERM before SIGKILL)
- Zombie order detection (300s timeout)
- Friday force close (3:55 PM EST)
- Equity hard-stop (15% drawdown = permanent shutdown)
- Tier 0 data rejection (yfinance never for backtesting)

#### Scripts
- `run_bot.py` - Main trading bot
- `run_watchdog.py` - Independent watchdog
- `run_backtest.py` - Backtesting suite
- `stress_test_strategy.py` - Stress testing
- `calibrate_sentiment.py` - Sentiment calibration
- `run_etl.py` - ETL pipeline

#### Documentation
- README.md - Comprehensive documentation
- QUICKSTART.md - Quick start guide
- CONTRIBUTING.md - Contribution guidelines
- IMPLEMENTATION_STATUS.md - Implementation status

### Design Principles

- Failure-aware architecture
- Statistical rigor (walk-forward, Bonferroni)
- Stress testing (10x spreads)
- Regime awareness
- Safety first (watchdog, kill switches)

### Known Limitations

- ML models are research-only (not for production)
- Sentiment calibration requires historical data
- Some components are simplified (full implementation for production)

### Future Enhancements

- Twitter sentiment integration (requires API access)
- Transformer attention models (research)
- More sophisticated regime detection
- Real-time correlation matrix updates
- Advanced portfolio optimization
