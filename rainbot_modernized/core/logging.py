import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from config.config import config


def setup_logging():
    """Setup logging configuration"""
    # Create logs directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, config.logging.level))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler
    file_handler = RotatingFileHandler(
        config.logging.file_path,
        maxBytes=config.logging.max_file_size,
        backupCount=config.logging.backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Reduce discord.py logging noise
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)

    return logger


def get_logger(name: str):
    """Get a logger with the specified name"""
    return logging.getLogger(f"rainbot.{name}")


class ModLogger:
    """Logger for moderation actions"""

    def __init__(self):
        self.logger = get_logger("moderation")

    def moderation_action(
        self, action: str, user_id: int, moderator_id: int, guild_id: int, reason: str
    ):
        """Log a moderation action"""
        self.logger.info(
            f"Moderation action: {action} | User: {user_id} | Moderator: {moderator_id} | Guild: {guild_id} | Reason: {reason}"
        )
