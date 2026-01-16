#!/usr/bin/env python3
"""
Setup script for free API keys (no personal information required).

This script helps you get free API keys from:
- Alpha Vantage (alphavantage.co) - Email only
- Finnhub (finnhub.io) - Email only

Both only require email signup, no SSN or identity verification.
"""

import os
import sys
from pathlib import Path

def print_header():
    print("=" * 70)
    print("🔑 Free API Keys Setup (No Personal Info Required)")
    print("=" * 70)
    print()
    print("This script helps you get free API keys for enhanced market data.")
    print("Both services only require email signup - no SSN or verification!")
    print()

def setup_alpha_vantage():
    print("📊 Alpha Vantage Setup")
    print("-" * 70)
    print("1. Go to: https://www.alphavantage.co/support/#api-key")
    print("2. Enter your email address")
    print("3. Click 'GET FREE API KEY'")
    print("4. Check your email for the API key")
    print("5. Copy the API key")
    print()
    
    key = input("Enter your Alpha Vantage API key (or press Enter to skip): ").strip()
    
    if key:
        return key
    return None

def setup_finnhub():
    print("📈 Finnhub Setup")
    print("-" * 70)
    print("1. Go to: https://finnhub.io/register")
    print("2. Sign up with your email (no personal info required)")
    print("3. Go to: https://finnhub.io/dashboard")
    print("4. Copy your API key from the dashboard")
    print()
    
    key = input("Enter your Finnhub API key (or press Enter to skip): ").strip()
    
    if key:
        return key
    return None

def update_env_file(alpha_vantage_key, finnhub_key):
    """Update .env file with API keys."""
    env_path = Path(".env")
    
    # Read existing .env if it exists
    env_vars = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
    
    # Update with new keys
    if alpha_vantage_key:
        env_vars["ALPHA_VANTAGE_API_KEY"] = alpha_vantage_key
    if finnhub_key:
        env_vars["FINNHUB_API_KEY"] = finnhub_key
    
    # Write back to .env
    with open(env_path, "w") as f:
        f.write("# Free Data Source API Keys (No Personal Info Required)\n")
        f.write("# These are optional - bot works without them using yfinance\n\n")
        
        if alpha_vantage_key:
            f.write(f"ALPHA_VANTAGE_API_KEY={alpha_vantage_key}\n")
        else:
            f.write("# ALPHA_VANTAGE_API_KEY=your_key_here\n")
        
        if finnhub_key:
            f.write(f"FINNHUB_API_KEY={finnhub_key}\n")
        else:
            f.write("# FINNHUB_API_KEY=your_key_here\n")
        
        # Write other existing vars
        for key, value in env_vars.items():
            if key not in ["ALPHA_VANTAGE_API_KEY", "FINNHUB_API_KEY"]:
                f.write(f"{key}={value}\n")
    
    print(f"✅ Updated .env file with API keys")

def test_keys(alpha_vantage_key, finnhub_key):
    """Test the API keys."""
    print()
    print("🧪 Testing API Keys...")
    print("-" * 70)
    
    if alpha_vantage_key:
        try:
            from alpha_vantage.timeseries import TimeSeries
            ts = TimeSeries(key=alpha_vantage_key, output_format='pandas')
            data, meta = ts.get_daily(symbol='AAPL', outputsize='compact')
            if not data.empty:
                print("✅ Alpha Vantage: Working!")
            else:
                print("⚠️  Alpha Vantage: Key accepted but no data returned")
        except Exception as e:
            print(f"❌ Alpha Vantage: Failed - {e}")
    else:
        print("⏭️  Alpha Vantage: Skipped (no key provided)")
    
    if finnhub_key:
        try:
            import finnhub
            client = finnhub.Client(api_key=finnhub_key)
            quote = client.quote('AAPL')
            if quote and 'c' in quote:
                print("✅ Finnhub: Working!")
            else:
                print("⚠️  Finnhub: Key accepted but no data returned")
        except Exception as e:
            print(f"❌ Finnhub: Failed - {e}")
    else:
        print("⏭️  Finnhub: Skipped (no key provided)")

def main():
    print_header()
    
    print("You can skip both if you want - the bot works with just yfinance!")
    print("(yfinance requires no API key at all)")
    print()
    
    alpha_vantage_key = setup_alpha_vantage()
    print()
    finnhub_key = setup_finnhub()
    print()
    
    if alpha_vantage_key or finnhub_key:
        update_env_file(alpha_vantage_key, finnhub_key)
        test_keys(alpha_vantage_key, finnhub_key)
    else:
        print("ℹ️  No API keys provided - bot will use yfinance only (still works!)")
        print("   You can run this script again later to add keys.")
    
    print()
    print("=" * 70)
    print("✅ Setup Complete!")
    print("=" * 70)
    print()
    print("The bot will now use:")
    if alpha_vantage_key:
        print("  ✅ Alpha Vantage (enhanced data)")
    if finnhub_key:
        print("  ✅ Finnhub (real-time quotes)")
    print("  ✅ yfinance (always available, no key needed)")
    print()
    print("Run the bot with: python scripts/run_bot_simulation.py")

if __name__ == "__main__":
    main()
