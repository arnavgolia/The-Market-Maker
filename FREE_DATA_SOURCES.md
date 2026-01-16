# 🆓 Free Data Sources Guide

The Market Maker supports multiple free data sources that **require NO personal information** (no SSN, no identity verification). All you need is an email address!

## Available Free Data Sources

### 1. yfinance (No API Key Required) ✅

**Best option if you want zero setup!**

- **Signup**: None required
- **Rate Limits**: None (reasonable use)
- **Data**: Historical OHLCV, real-time quotes (15-min delay)
- **Coverage**: US stocks, ETFs, indices
- **Pros**: 
  - Zero setup
  - Unlimited usage
  - Fast and reliable
- **Cons**: 
  - 15-minute delay on real-time data
  - Adjusted prices (we handle this)

**Status**: ✅ Always available - works out of the box!

### 2. Alpha Vantage (Free API Key) 📊

**Great for enhanced historical data!**

- **Signup**: https://www.alphavantage.co/support/#api-key
- **Requirements**: Email address only
- **Rate Limits**: 5 calls/minute, 500 calls/day
- **Data**: Historical daily bars, real-time quotes
- **Coverage**: Global stocks, forex, crypto
- **Pros**:
  - Real-time data
  - Reliable API
  - Good documentation
- **Cons**:
  - Rate limits (manageable with caching)
  - Daily bars only on free tier

**Setup**:
```bash
1. Go to https://www.alphavantage.co/support/#api-key
2. Enter your email
3. Get free API key
4. Run: python scripts/setup_free_apis.py
```

### 3. Finnhub (Free API Key) 📈

**Best for real-time quotes!**

- **Signup**: https://finnhub.io/register
- **Requirements**: Email address only
- **Rate Limits**: 60 calls/minute
- **Data**: Real-time quotes, candlesticks, news
- **Coverage**: Global stocks, forex, crypto
- **Pros**:
  - High rate limit (60/min)
  - Real-time data
  - Good for quotes
- **Cons**:
  - Requires API key setup

**Setup**:
```bash
1. Go to https://finnhub.io/register
2. Sign up with email
3. Get API key from dashboard
4. Run: python scripts/setup_free_apis.py
```

## Quick Setup

### Option 1: Zero Setup (yfinance only)

Just run the bot - it works immediately:
```bash
python scripts/run_bot_simulation.py
```

### Option 2: Enhanced Setup (with API keys)

1. Get free API keys (optional):
   ```bash
   python scripts/setup_free_apis.py
   ```

2. Run the bot:
   ```bash
   python scripts/run_bot_simulation.py
   ```

The bot automatically uses the best available data source!

## How It Works

The bot uses a **smart fallback system**:

1. **First tries yfinance** (always works, no key needed)
2. **Falls back to Alpha Vantage** (if key provided)
3. **Falls back to Finnhub** (if key provided)

This ensures the bot always has data, even if one source fails.

## Data Source Priority

```
┌─────────────────────────────────────────┐
│  Try yfinance (no key needed)          │
│  ✅ Fast, unlimited, always available  │
└──────────────┬──────────────────────────┘
               │ If fails or needs real-time
               ▼
┌─────────────────────────────────────────┐
│  Try Alpha Vantage (if key provided)    │
│  📊 Real-time, 5 calls/min              │
└──────────────┬──────────────────────────┘
               │ If fails
               ▼
┌─────────────────────────────────────────┐
│  Try Finnhub (if key provided)         │
│  📈 Real-time, 60 calls/min             │
└─────────────────────────────────────────┘
```

## Rate Limiting

The bot automatically handles rate limits:

- **yfinance**: No limits (reasonable use)
- **Alpha Vantage**: 5 calls/min, 500/day (auto-throttled)
- **Finnhub**: 60 calls/min (auto-throttled)

The bot caches data and respects all rate limits automatically.

## Comparison Table

| Feature | yfinance | Alpha Vantage | Finnhub |
|---------|----------|---------------|---------|
| **Setup Required** | None | Email + API key | Email + API key |
| **Personal Info** | None | None | None |
| **Rate Limit** | None | 5/min, 500/day | 60/min |
| **Real-time Data** | 15-min delay | Yes | Yes |
| **Historical Data** | Yes | Yes (daily only) | Yes |
| **Coverage** | US stocks | Global | Global |

## Privacy & Security

✅ **All services only require email**  
✅ **No SSN or identity verification**  
✅ **No credit card required**  
✅ **API keys stored in .env (not committed to git)**  
✅ **All data sources are legitimate and trusted**

## Troubleshooting

### "No data returned"
- Check internet connection
- Verify symbol is valid (e.g., "AAPL" not "apple")
- Try a different symbol

### "Rate limit exceeded"
- Bot automatically handles this
- Wait a few minutes and try again
- Consider adding more API keys for higher limits

### "API key invalid"
- Verify key is correct in `.env` file
- Check if key is active in provider dashboard
- Regenerate key if needed

## Next Steps

1. **Start with yfinance** (zero setup)
2. **Add API keys later** if you want enhanced features
3. **Run the bot** and enjoy free trading simulation!

All data sources are completely free and require no personal information beyond an email address. Perfect for learning and testing! 🚀
