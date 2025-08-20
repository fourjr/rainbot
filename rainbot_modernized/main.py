"""
Main entry point for the modernized rainbot
"""

import asyncio
import sys
import signal
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from config.config import config
from core.logging import setup_logging
from core.bot import RainBot


async def main():
    """Main entry point"""
    # Setup logging
    logger = setup_logging()

    logger.info("Starting RainBot v3.0.0...")
    logger.info(f"Environment: {config.environment.value}")

    # Create bot instance
    bot = RainBot()

    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(bot.close())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Start the bot
        await bot.start(config.bot.token)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        if not bot.is_closed():
            await bot.close()
        logger.info("Bot shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete!")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
