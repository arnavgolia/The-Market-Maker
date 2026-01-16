# The Market Maker Dashboard

A real-time web dashboard for monitoring The Market Maker trading bot.

## Features

- **Real-time Updates**: Live data updates every 2 seconds via WebSocket
- **Account Overview**: Equity, cash, buying power, and daily returns
- **Position Tracking**: View all open positions with P&L
- **Order History**: Recent orders with status tracking
- **Performance Metrics**: Cumulative returns, Sharpe ratio, drawdown
- **Market Regime**: Current market trend and volatility regime
- **System Status**: Bot, Redis, and Alpaca connection status

## Quick Start

### Start the Dashboard

```bash
# From project root
python scripts/run_dashboard.py

# Or directly
python dashboard/app.py
```

The dashboard will be available at: **http://localhost:8080**

### Start Both Bot and Dashboard

```bash
# Terminal 1: Start the bot
python scripts/run_bot.py

# Terminal 2: Start the dashboard
python scripts/run_dashboard.py
```

## Requirements

- Flask
- Flask-SocketIO
- psutil (for process monitoring)
- Redis (must be running)
- Alpaca API keys (configured in `.env`)

## Configuration

The dashboard uses the same configuration as the bot:
- Redis connection: `REDIS_HOST`, `REDIS_PORT` (from `.env` or `config/settings.yaml`)
- Alpaca API: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` (from `.env`)
- Dashboard port: `DASHBOARD_PORT` (default: 8080)

## API Endpoints

- `GET /` - Main dashboard page
- `GET /api/status` - System status
- `GET /api/account` - Account information
- `GET /api/positions` - All positions
- `GET /api/orders` - Recent orders
- `GET /api/metrics` - Performance metrics
- `GET /api/regime` - Market regime

## WebSocket Events

- `connect` - Client connects
- `update` - Real-time data updates (positions, account)
- `status` - Status messages

## Troubleshooting

### Port Already in Use

If port 8080 is in use, set a different port:

```bash
DASHBOARD_PORT=5001 python scripts/run_dashboard.py
```

### Redis Not Connected

Make sure Redis is running:

```bash
redis-server
```

### Alpaca Not Connected

Check your API keys in `.env`:

```bash
cat .env | grep ALPACA
```

## Development

The dashboard is built with:
- **Backend**: Flask + Flask-SocketIO
- **Frontend**: Vanilla JavaScript + Socket.IO client
- **Styling**: Modern CSS with gradient backgrounds

To modify the dashboard:
- Backend: `dashboard/app.py`
- Frontend: `dashboard/templates/dashboard.html`
