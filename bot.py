"""
Main entry point for the RainBot.

This script acts as a launcher for the modernized bot application,
allowing you to run the bot from the root directory using `python bot.py`.
"""

import asyncio
import sys
from pathlib import Path

if __name__ == "__main__":
    # Define the path to the modernized bot's directory.
    modernized_path = Path(__file__).parent / 'rainbot_modernized'

    # Add the modernized directory to the system path. This is crucial so that
    # all the imports within the modernized code (e.g., from core, from config)
    # can be found correctly by Python.
    sys.path.insert(0, str(modernized_path))

    try:
        # Import the main async function from the modernized entry point.
        from main import main

        # Run the main asynchronous function from main.py
        asyncio.run(main())

    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully for a clean shutdown.
        print("\nShutdown requested by user. Bot is closing.")
    except Exception as e:
        # Catch any other fatal errors during startup or runtime.
        print(f"A fatal error occurred: {e}")
        sys.exit(1)
