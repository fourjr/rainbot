"""
Main entry point for the RainBot.

This script launches the modernized bot application, ensuring the
correct working directory for configuration and module loading.
"""

import os
import sys
import asyncio
from pathlib import Path

if __name__ == "__main__":
    # Get the directory where this script is located (the project root).
    project_root = Path(__file__).parent
    
    # Change the current working directory to the project root.
    # This ensures that load_dotenv() in main.py finds the root .env file.
    os.chdir(project_root)

    # Define the path to the modernized bot's code.
    modernized_path = project_root / 'rainbot_modernized'

    # Add the modernized directory to the system path for correct imports.
    sys.path.insert(0, str(modernized_path))

    try:
        # Import and run the main application.
        from main import main
        asyncio.run(main())

    except KeyboardInterrupt:
        print("\nShutdown requested by user.")
    except Exception as e:
        print(f"A fatal error occurred: {e}")
        sys.exit(1)
