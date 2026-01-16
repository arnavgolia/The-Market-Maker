# 🎮 Simulation Mode - No API Required!

The Market Maker can now run in **FULL SIMULATION MODE** without any external APIs!

## ✅ What Works in Simulation Mode

- **No Alpaca API needed** - Uses free data sources
- **Free market data** - Multiple sources (yfinance, Alpha Vantage, Finnhub)
- **No personal info required** - Only email for optional API keys
- **Simulated trading** - PaperBroker handles all trades
- **Full dashboard** - All features work
- **Real strategies** - EMA, RSI strategies run normally
- **Risk management** - All safety features active
- **Smart fallback** - Automatically uses best available data source

## 🚀 How to Run

### Option 1: Simulation Mode Script (Recommended)

```bash
python scripts/run_bot_simulation.py
```

### Option 2: Environment Variable

```bash
SIMULATION_MODE=true python scripts/run_bot.py --dry-run
```

## 📊 What You'll See

The dashboard at `http://localhost:8080` will show:
- **Equity**: $100,000 (simulated)
- **Cash**: $50,000
- **Buying Power**: $200,000
- **Positions**: Will populate as bot trades
- **Orders**: Will show simulated trades
- **Charts**: Equity curve updates in real-time

## 🔄 How It Works

1. **Market Data**: Uses free data sources with smart fallback:
   - Primary: yfinance (no API key needed)
   - Secondary: Alpha Vantage (optional, email only)
   - Tertiary: Finnhub (optional, email only)
2. **Trading**: PaperBroker simulates order execution
3. **Account**: Mock account with $100k starting equity
4. **Strategies**: Run normally, generate real signals
5. **Execution**: Simulated fills with realistic slippage

## 📊 Enhanced Data Sources (Optional)

You can enhance the bot with free API keys (email only, no personal info):

```bash
# Setup free API keys
python scripts/setup_free_apis.py
```

This adds:
- **Alpha Vantage**: Real-time data, 5 calls/min
- **Finnhub**: Real-time quotes, 60 calls/min

Both are completely free and only require email signup!

## ⚙️ Configuration

Simulation mode uses the same `config/settings.yaml` file. All strategies and risk settings work normally.

## 🆚 Simulation vs Real API

| Feature | Simulation Mode | Real API Mode |
|---------|----------------|---------------|
| Market Data | yfinance (free) | Alpaca API |
| Trading | PaperBroker | Alpaca Paper Trading |
| Account | Mock ($100k) | Real Alpaca Account |
| API Keys | Not needed | Required |
| Cost | Free | Free (paper trading) |

## 🎯 When to Use Simulation Mode

- **Testing strategies** without API setup
- **Learning the system** without external dependencies
- **Development** when APIs are down
- **Demonstration** without exposing API keys
- **Backtesting** with live-like execution

## 🔧 Troubleshooting

### Bot won't start
- Make sure Redis is running: `redis-cli ping`
- Check logs: `tail -f bot_simulation.log`

### No trades happening
- Market might be closed (simulation respects market hours)
- Check strategy configuration in `config/settings.yaml`
- Verify regime detector isn't blocking trades

### Dashboard shows no data
- Restart dashboard: `pkill -f dashboard/app.py && python dashboard/app.py`
- Check Redis connection: `redis-cli ping`

## 📝 Notes

- Simulation mode is **perfect for learning and testing**
- All safety features (drawdown limits, etc.) still work
- Strategies run exactly as they would with real API
- You can switch to real API mode anytime by removing `SIMULATION_MODE=true`

Enjoy trading without API hassles! 🎉
