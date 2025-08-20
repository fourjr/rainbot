"""
Utility functions and helpers for rainbot
"""

from .helpers import *
from .errors import *
from .decorators import *
from .converters import *
from .paginator import *

__all__ = [
    # Helpers
    "format_duration",
    "format_timestamp",
    "truncate_text",
    "get_user_avatar",
    "create_embed",
    "safe_send",
    # Errors
    "RainBotError",
    "PermissionError",
    "ConfigurationError",
    "ModerationError",
    # Decorators
    "require_permission",
    "cooldown",
    "guild_only",
    "owner_only",
    # Converters
    "MemberOrUser",
    "Duration",
    "BooleanConverter",
    # Paginator
    "Paginator",
    "EmbedPaginator",
]
