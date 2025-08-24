"""
Main entry point for the RainBot.

This script acts as a launcher for the modernized bot application,
allowing you to run the bot from the root directory using `python bot.py`.
"""

import asyncio
import sys
from pathlib import Path

if __name__ == "__main__":
    # --- Path Setup ---
    # Get the directory where this launcher script is located (the project root).
    project_root = Path(__file__).parent
    
    # Define the path to the modernized bot's directory.
    modernized_path = project_root / 'rainbot_modernized'
    
    # Define the absolute path to the .env file, located in the project root.
    dotenv_path = project_root / '.env'

    # Add the modernized directory to the system path. This is crucial so that
    # all the imports within the modernized code (e.g., from core, from config)
    # can be found correctly by Python.
    sys.path.insert(0, str(modernized_path))

    try:
        # Import the main async function from the modernized entry point.
        from main import main

        # Run the main asynchronous function and explicitly pass the root .env path.
        asyncio.run(main(dotenv_path=dotenv_path))

    except FileNotFoundError as e:
        print(f"[FATAL LAUNCHER ERROR] The .env file could not be found.")
        print(f"Please ensure a .env file exists at: {dotenv_path}")
        sys.exit(1)
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully for a clean shutdown.
        print("\nShutdown requested by user. Bot is closing.")
    except Exception as e:
        # Catch any other fatal errors during startup or runtime.
        print(f"A fatal error occurred during bot execution: {e}")
        sys.exit(1)
