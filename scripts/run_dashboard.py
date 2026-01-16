#!/usr/bin/env python3
"""
Start the Market Maker Dashboard.

This script starts the web dashboard for monitoring the trading bot.
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Change to project root
os.chdir(project_root)

# Import and run dashboard
from dashboard.app import app, socketio, init_connections, broadcast_updates

if __name__ == '__main__':
    init_connections()
    broadcast_updates()
    
    port = int(os.environ.get('DASHBOARD_PORT', 8080))
    print(f"""
🚀 Starting The Market Maker Dashboard
=======================================

Dashboard will be available at:
   http://localhost:{port}

Press Ctrl+C to stop the dashboard.
""")
    
    socketio.run(app, host='0.0.0.0', port=port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
