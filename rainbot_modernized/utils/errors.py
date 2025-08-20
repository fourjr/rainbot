"""
Custom exception classes for rainbot
"""

from discord.ext import commands


class RainBotError(commands.CommandError):
    """Base exception for all rainbot errors"""

    pass


class PermissionError(RainBotError):
    """Raised when user lacks required permissions"""

    pass


class ConfigurationError(RainBotError):
    """Raised when there's a configuration issue"""

    pass


class ModerationError(RainBotError):
    """Raised when moderation action fails"""

    pass


class DatabaseError(RainBotError):
    """Raised when database operation fails"""

    pass


class ValidationError(RainBotError):
    """Raised when input validation fails"""

    pass


class AutoModError(RainBotError):
    """Raised when auto-moderation encounters an error"""

    pass


class SetupError(RainBotError):
    """Raised during bot setup/configuration"""

    pass
