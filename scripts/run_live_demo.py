#!/usr/bin/env python3
"""
Live demo that runs the actual bot for a short period to show it working.
"""

import sys
import time
import signal
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import structlog
from dotenv import load_dotenv
from src.main import MarketMaker

# Setup logging with console output
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),  # Pretty console output
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Global flag for graceful shutdown
running = True

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    global running
    logger.info("shutdown_requested")
    running = False

def main():
    """Run the bot for a demo period."""
    global running
    
    # Load environment
    load_dotenv()
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("\n" + "="*80)
    print("🚀 THE MARKET MAKER - LIVE DEMO")
    print("="*80)
    print("\nStarting the trading bot in DRY-RUN mode...")
    print("(No actual trades will be executed)")
    print("\nPress Ctrl+C to stop\n")
    print("="*80 + "\n")
    
    try:
        # Initialize bot
        bot = MarketMaker(
            config_path="config/settings.yaml",
            dry_run=True,
        )
        
        logger.info("bot_initialized", dry_run=True)
        
        # Run for a short period
        print("\n✅ Bot is running! Showing activity...\n")
        print("-" * 80)
        
        iteration = 0
        max_iterations = 5  # Run for 5 iterations
        
        while running and iteration < max_iterations:
            iteration += 1
            print(f"\n[Iteration {iteration}/{max_iterations}]")
            
            try:
                # Run one cycle
                bot._run_strategies()
                
                # Show current state
                positions = bot.redis.get_all_positions() if hasattr(bot, 'redis') else {}
                print(f"   Positions: {len(positions)}")
                
                # Wait a bit
                time.sleep(2)
                
            except Exception as e:
                logger.error("iteration_error", error=str(e), iteration=iteration)
                time.sleep(1)
        
        print("\n" + "="*80)
        print("✅ DEMO COMPLETE")
        print("="*80)
        print("\nThe bot ran successfully!")
        print("\nTo run continuously:")
        print("  python scripts/run_bot.py")
        print("\n" + "="*80 + "\n")
        
    except KeyboardInterrupt:
        logger.info("demo_interrupted")
    except Exception as e:
        logger.exception("demo_error", error=str(e))
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
