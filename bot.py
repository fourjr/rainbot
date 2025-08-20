#!/usr/bin/env python3
"""
RainBot - Discord Moderation Bot
Entry point for starting the bot from the root directory
"""

import sys
import os
from pathlib import Path

# Change to the modernized rainbot directory
rainbot_dir = Path(__file__).parent / "rainbot_modernized"
os.chdir(rainbot_dir)

# Add the modernized rainbot to the Python path
sys.path.insert(0, str(rainbot_dir))

# Import and run the main function from the modernized version
from main import main
import asyncio

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete!")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
