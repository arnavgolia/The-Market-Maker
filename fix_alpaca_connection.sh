#!/bin/bash
echo "🔧 Fixing Alpaca Connection"
echo "=========================="
echo ""
echo "1. Stopping bot..."
pkill -f "run_bot.py"
sleep 2
echo ""
echo "2. Testing API keys..."
python3 -c "
from dotenv import load_dotenv
import os
load_dotenv()
from alpaca.trading.client import TradingClient

api_key = os.getenv('ALPACA_API_KEY')
secret_key = os.getenv('ALPACA_SECRET_KEY')

try:
    client = TradingClient(api_key=api_key, secret_key=secret_key, paper=True)
    account = client.get_account()
    print('✅ SUCCESS! Keys are working!')
    print(f'   Equity: \${float(account.equity):,.2f}')
    print(f'   Status: {account.status}')
    print('')
    print('3. Starting bot...')
    print('   python scripts/run_bot.py --log-level INFO')
except Exception as e:
    print('❌ FAILED:', e)
    print('')
    print('Please:')
    print('1. Check your API keys in .env file')
    print('2. Verify keys in Alpaca dashboard')
    print('3. Make sure keys are activated')
"
