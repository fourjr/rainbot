"""Constants used throughout the bot"""

UNICODE_EMOJI = r"(\U0001F1E0-\U0001F1FF)|(\U0001F300-\U0001F5FF)|(\U0001F600-\U0001F64F)|(\U0001F680-\U0001F6FF)|(\U0001F700-\U0001F77F)|(\U0001F780-\U0001F7FF)|(\U0001F800-\U0001F8FF)|(\U0001F900-\U0001F9FF)|(\U0001FA00-\U0001FA6F)|(\U0001FA70-\U0001FAFF)|(\U00002702-\U000027B0)|(\U000024C2-\U0001F251)"

EMOJIS = {
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "ban": "🔨",
    "kick": "👢",
    "mute": "🔇",
    "unmute": "🔊",
    "warn": "⚠️",
    "lock": "🔒",
    "unlock": "🔓",
    "clock": "⏰",
    "ping": "🏓",
    "invite": "📨",
    "loading": "⏳",
    "settings": "⚙️",
    "moderation": "🛡️",
    "help": "❓",
}

COLORS = {
    "primary": 0x5865F2,
    "success": 0x57F287,
    "error": 0xED4245,
    "warning": 0xFEE75C,
    "info": 0x5865F2,
    "secondary": 0x99AAB5,
}

PERMISSION_LEVELS = {
    0: "Everyone",
    1: "Helper",
    2: "Moderator",
    3: "Senior Moderator",
    4: "Administrator",
    5: "Senior Administrator",
    6: "Server Manager",
    7: "Server Owner",
    8: "Bot Developer",
    9: "Bot Owner",
    10: "System",
}
