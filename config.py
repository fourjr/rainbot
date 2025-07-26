"""
rainbot Configuration File
This file contains all the configurable settings for rainbot.
"""

import os
from typing import List, Optional

# Bot Configuration
BOT_NAME = "rainbot"
BOT_VERSION = "2.5.3"
BOT_DESCRIPTION = "A powerful moderation bot with automod and logging features"

# Default Settings
DEFAULT_PREFIX = "!"
DEFAULT_TIME_OFFSET = 0
DEFAULT_MUTE_ROLE = "Muted"

# Permission Levels
PERMISSION_LEVELS = {
    0: "Everyone",
    1: "Helper",
    2: "Moderator", 
    3: "Senior Moderator",
    4: "Admin",
    5: "Senior Admin",
    6: "Server Manager",
    7: "Server Owner",
    8: "Bot Admin",
    9: "Bot Owner",
    10: "Bot Developer"
}

# Emoji Configuration
EMOJIS = {
    "accept": "<:check:684169254618398735>",
    "deny": "<:xmark:684169254551158881>",
    "loading": "⏳",
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "question": "❓",
    "clock": "🕐",
    "user": "👤",
    "server": "🏠",
    "settings": "⚙️",
    "shield": "🛡️",
    "hammer": "🔨",
    "eye": "👁️",
    "book": "📚",
    "link": "🔗",
    "stats": "📊",
    "ping": "🏓",
    "help": "❓"
}

# Colors for embeds
COLORS = {
    "success": 0x2ECC71,  # Green
    "error": 0xE74C3C,    # Red
    "warning": 0xF39C12,  # Orange
    "info": 0x3498DB,     # Blue
    "purple": 0x9B59B6,   # Purple
    "dark": 0x2C3E50,     # Dark Blue
    "light": 0xECF0F1,    # Light Gray
    "default": 0x7289DA   # Discord Blue
}

# Cooldown Settings (in seconds)
COOLDOWNS = {
    "default": 3,
    "moderation": 5,
    "utility": 2,
    "admin": 1,
    "owner": 0
}

# Logging Configuration
LOGGING = {
    "level": "INFO",
    "format": "%(asctime)s:%(levelname)s:%(name)s: %(message)s",
    "file": "rainbot.log",
    "max_size": 10 * 1024 * 1024,  # 10MB
    "backup_count": 5
}

# Database Configuration
DATABASE = {
    "connection_timeout": 30000,
    "server_selection_timeout": 5000,
    "max_pool_size": 100,
    "min_pool_size": 0
}

# Auto-moderation Settings
AUTOMOD = {
    "max_messages_per_minute": 10,
    "max_mentions": 5,
    "max_emojis": 10,
    "max_caps_percentage": 70,
    "max_links_per_message": 3,
    "spam_threshold": 5,
    "duplicate_threshold": 3
}

# Welcome Message Configuration
WELCOME_MESSAGE = {
    "enabled": True,
    "channel_type": "system",  # system, random, specific
    "specific_channel_id": None,
    "embed_color": COLORS["success"],
    "show_quick_start": True,
    "show_features": True,
    "show_links": True
}

# Support and Links
LINKS = {
    "invite": "https://discord.com/oauth2/authorize?client_id=372748944448552961&scope=bot&permissions=2013785334",
    "support": "https://discord.gg/eXrDpGS",
    "documentation": "https://github.com/fourjr/rainbot/wiki",
    "github": "https://github.com/fourjr/rainbot",
    "top_gg": None,
    "discord_bots": None
}

# Required Permissions
REQUIRED_PERMISSIONS = [
    "manage_messages",
    "kick_members", 
    "ban_members",
    "manage_roles",
    "view_channel",
    "send_messages",
    "embed_links",
    "attach_files",
    "read_message_history",
    "use_external_emojis",
    "add_reactions"
]

# Optional Permissions (for enhanced features)
OPTIONAL_PERMISSIONS = [
    "manage_channels",
    "manage_guild",
    "view_audit_log",
    "move_members",
    "deafen_members",
    "mute_members",
    "priority_speaker",
    "stream",
    "connect",
    "speak"
]

# Feature Flags
FEATURES = {
    "slash_commands": False,
    "context_menus": False,
    "message_components": True,
    "threads": True,
    "stage_channels": True,
    "voice_states": True,
    "guild_scheduled_events": False,
    "auto_moderation": True,
    "logging": True,
    "custom_commands": True,
    "reaction_roles": True,
    "giveaways": True,
    "welcome_messages": True,
    "leave_messages": False,
    "birthday_announcements": False,
    "reminders": False,
    "polls": False,
    "suggestions": False,
    "tickets": False,
    "moderation_logs": True,
    "user_logs": True,
    "server_logs": True,
    "voice_logs": True
}

# Development Settings
DEV_MODE = os.name == 'nt'
DEBUG_MODE = os.getenv('DEBUG', 'false').lower() == 'true'

# Rate Limiting
RATE_LIMITS = {
    "commands_per_minute": 60,
    "messages_per_minute": 100,
    "api_calls_per_minute": 50,
    "database_queries_per_minute": 200
}

# Cache Settings
CACHE = {
    "guild_configs_ttl": 300,  # 5 minutes
    "user_data_ttl": 600,      # 10 minutes
    "command_usage_ttl": 3600, # 1 hour
    "max_cache_size": 1000
}

# Backup Settings
BACKUP = {
    "enabled": True,
    "interval_hours": 24,
    "max_backups": 7,
    "backup_path": "./backups/",
    "compress_backups": True
}

# Monitoring and Analytics
MONITORING = {
    "enabled": True,
    "track_command_usage": True,
    "track_errors": True,
    "track_performance": True,
    "track_guild_activity": True,
    "metrics_retention_days": 30
}

# Security Settings
SECURITY = {
    "max_failed_logins": 5,
    "lockout_duration_minutes": 15,
    "require_2fa_for_admin": False,
    "log_suspicious_activity": True,
    "rate_limit_sensitive_commands": True
}

# Localization
LOCALIZATION = {
    "default_language": "en",
    "supported_languages": ["en"],
    "fallback_language": "en",
    "date_format": "%Y-%m-%d %H:%M:%S",
    "timezone": "UTC"
}

# Webhook Settings (for external integrations)
WEBHOOKS = {
    "enabled": False,
    "urls": {},
    "events": ["guild_join", "guild_leave", "error", "command_usage"]
}

# API Settings (for future external API)
API = {
    "enabled": False,
    "port": 8080,
    "host": "0.0.0.0",
    "rate_limit": 100,
    "authentication_required": True
}

def get_emoji(name: str) -> str:
    """Get emoji by name"""
    return EMOJIS.get(name, "❓")

def get_color(name: str) -> int:
    """Get color by name"""
    return COLORS.get(name, COLORS["default"])

def get_permission_name(level: int) -> str:
    """Get permission level name"""
    return PERMISSION_LEVELS.get(level, "Unknown")

def is_feature_enabled(feature: str) -> bool:
    """Check if a feature is enabled"""
    return FEATURES.get(feature, False)

def get_required_permissions() -> List[str]:
    """Get list of required permissions"""
    return REQUIRED_PERMISSIONS.copy()

def get_optional_permissions() -> List[str]:
    """Get list of optional permissions"""
    return OPTIONAL_PERMISSIONS.copy() 